# --- START OF FILE main.py ---

from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import threading
import time
import uuid

app = Flask(__name__)

# --- In-memory data store (simulating a database) ---
data = {
    'users': {},
    'live_attendance': defaultdict(lambda: {'active': False, 'current_lecture': None, 'accumulated_time': 0, 'last_ping': None}),
    'attendance_history': defaultdict(list),
    'active_sessions': {},
    'timetable': {"10A": {"Monday": {"09:40-10:40": "Maths", "10:40-11:40": "Physics"}}},
    'settings': {
        'authorized_bssids': ['ee:ee:6d:9d:6f:ba'],
        'session_active': False
    }
}

# --- Utility Functions ---
def get_utc_now(): return datetime.now(timezone.utc)
def parse_time(time_str): return datetime.strptime(time_str, "%H:%M").time()

def get_current_lecture_details(class_id):
    if not class_id: return None, 0
    now = get_utc_now()
    day_of_week = now.strftime('%A')
    current_time = now.time()
    class_timetable = data['timetable'].get(class_id, {}).get(day_of_week, {})
    for time_slot, subject in class_timetable.items():
        try:
            start_str, end_str = time_slot.split('-')
            start_time, end_time = parse_time(start_str.strip()), parse_time(end_str.strip())
            if start_time <= current_time <= end_time:
                duration = (datetime.combine(now.date(), end_time) - datetime.combine(now.date(), start_time)).total_seconds()
                return f"{time_slot} ({subject})", duration
        except ValueError: continue
    return None, 0

# --- User & Session Management ---
@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    req = request.json
    if not req or not req.get('username') or not req.get('password'): return jsonify({'error': 'Username and password required'}), 400
    if any(u['username'] == req['username'] for u in data['users'].values()): return jsonify({'error': 'Username already exists'}), 400
    user_id = str(uuid.uuid4())
    data['users'][user_id] = {'username': req['username'], 'password_hash': generate_password_hash(req['password']), 'type': 'teacher', 'name': req.get('name', req['username'])}
    return jsonify({'message': 'Teacher registered successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    if not all(k in req for k in ['username', 'password', 'device_id']): return jsonify({'error': 'Missing credentials or device ID'}), 400
    user_id, user_info = next(((uid, uinfo) for uid, uinfo in data['users'].items() if uinfo['username'] == req['username']), (None, None))
    if not user_id or not check_password_hash(user_info.get('password_hash', ''), req['password']): return jsonify({'error': 'Invalid credentials'}), 401
    if user_info['type'] == 'student' and user_id in data['active_sessions'].values():
        active_device = next((dev for dev, uid in data['active_sessions'].items() if uid == user_id), None)
        if active_device != req['device_id']: return jsonify({'error': 'This account is already logged in on another device.'}), 403
    data['active_sessions'][req['device_id']] = user_id
    response = {'message': 'Login successful', 'user_id': user_id, 'type': user_info['type'], 'name': user_info.get('name')}
    if user_info['type'] == 'student': response['class_id'] = user_info.get('class_id')
    return jsonify(response), 200

@app.route('/logout', methods=['POST'])
def logout():
    device_id = request.json.get('device_id')
    if device_id in data['active_sessions']:
        student_id = data['active_sessions'][device_id]
        if student_id in data['live_attendance']: data['live_attendance'][student_id]['active'] = False
        del data['active_sessions'][device_id]
    return jsonify({'message': 'Logged out'}), 200

# --- Teacher Endpoints ---
@app.route('/student/register', methods=['POST'])
def student_register():
    req = request.json
    if any(u['username'] == req['username'] for u in data['users'].values()): return jsonify({'error': 'Username already exists'}), 400
    user_id = str(uuid.uuid4())
    data['users'][user_id] = {'username': req['username'], 'password_hash': generate_password_hash(req['password']), 'type': 'student', 'name': req.get('name', req['username']), 'class_id': req.get('class_id')}
    return jsonify({'message': 'Student registered successfully', 'user_id': user_id}), 201

@app.route('/session/start', methods=['POST'])
def start_session(): data['settings']['session_active'] = True; return jsonify({'message': 'Session started'}), 200
@app.route('/session/end', methods=['POST'])
def end_session(): data['settings']['session_active'] = False; return jsonify({'message': 'Session ended'}), 200
@app.route('/session/status', methods=['GET'])
def get_session_status(): return jsonify({'session_active': data['settings']['session_active']})

@app.route('/random_ring', methods=['POST'])
def random_ring():
    active_students = {sid: data['live_attendance'][sid] for sid, u in data['users'].items() if u['type'] == 'student' and data['live_attendance'][sid]['active']}
    if len(active_students) < 2: return jsonify({'error': 'Not enough active students'}), 400
    for sid in active_students:
        history = data['attendance_history'].get(sid, [])
        present = sum(1 for r in history if r['status'] == 'Present')
        total = len(history) if len(history) > 0 else 1
        active_students[sid]['score'] = (present / total) * 100
    sorted_students = sorted(active_students.items(), key=lambda item: item[1]['score'])
    low_performer, high_performer = sorted_students[0][0], sorted_students[-1][0]
    data['random_rings'] = {'students': [low_performer, high_performer]}
    return jsonify({'students': [data['users'][low_performer]['name'], data['users'][high_performer]['name']]})

@app.route('/timetable', methods=['GET', 'POST'])
def manage_timetable():
    if request.method == 'POST': data['timetable'] = request.json; return jsonify({'message': 'Timetable updated'}), 200
    return jsonify(data['timetable'])

@app.route('/settings/bssid', methods=['GET', 'POST'])
def manage_bssid():
    if request.method == 'POST': data['settings']['authorized_bssids'] = request.json.get('bssids', []); return jsonify({'message': 'BSSID list updated'}), 200
    return jsonify({'bssids': data['settings']['authorized_bssids']})

@app.route('/students', methods=['GET'])
def get_all_students():
    students = [{'id': uid, **uinfo} for uid, uinfo in data['users'].items() if uinfo['type'] == 'student']
    for s in students: s.pop('password_hash', None)
    return jsonify(students)

# --- Student & Live Data Endpoints ---
@app.route('/ping', methods=['POST'])
def ping():
    PING_INTERVAL = 10
    device_id = request.json.get('device_id')
    if device_id not in data['active_sessions']: return jsonify({'error': 'Session expired. Please log in again.'}), 401
    student_id = data['active_sessions'][device_id]
    lecture, _ = get_current_lecture_details(data['users'][student_id].get('class_id'))
    live_data = data['live_attendance'][student_id]
    live_data['last_ping'] = get_utc_now()
    if lecture and data['settings']['session_active']:
        if live_data['current_lecture'] != lecture: live_data['current_lecture'] = lecture; live_data['accumulated_time'] = 0
        live_data['active'] = True; live_data['accumulated_time'] += PING_INTERVAL
    else:
        live_data['active'] = False; live_data['current_lecture'] = None
    return jsonify({'status': 'pong', 'current_lecture': live_data['current_lecture']}), 200

@app.route('/live_data', methods=['GET'])
def get_live_data():
    response = {'students': [], 'random_rings': data.get('random_rings', {})}
    for user_id, user_info in data['users'].items():
        if user_info['type'] == 'student':
            live_info = data['live_attendance'][user_id]
            response['students'].append({'id': user_id, 'name': user_info['name'], 'class_id': user_info.get('class_id'), 'status': 'Active' if live_info['active'] else 'Inactive', 'current_lecture': live_info['current_lecture'], 'accumulated_time': live_info.get('accumulated_time', 0)})
    return jsonify(response)
    
@app.route('/student/profile/<student_id>', methods=['GET'])
def get_student_profile(student_id):
    history = data['attendance_history'].get(student_id, [])
    total = len(history)
    present = sum(1 for r in history if r['status'] == 'Present')
    missed_lectures = defaultdict(int)
    for r in history:
        if r['status'] == 'Absent': missed_lectures[r['lecture']] += 1
    return jsonify({
        'total_lectures': total, 'present_lectures': present,
        'attendance_percent': (present / total * 100) if total > 0 else 0,
        'most_missed': sorted(missed_lectures.items(), key=lambda x: x[1], reverse=True)
    })

@app.route('/report', methods=['GET'])
def generate_report():
    from_date = datetime.strptime(request.args.get('from_date'), "%Y-%m-%d").date()
    to_date = datetime.strptime(request.args.get('to_date'), "%Y-%m-%d").date()
    report = defaultdict(lambda: defaultdict(str))
    all_student_ids = {uid for uid, uinfo in data['users'].items() if uinfo['type'] == 'student'}
    for day_delta in range((to_date - from_date).days + 1):
        current_date = from_date + timedelta(days=day_delta)
        date_str = current_date.strftime('%Y-%m-%d')
        for student_id in all_student_ids:
            history_for_day = [rec for rec in data['attendance_history'].get(student_id, []) if rec['date'] == date_str]
            student_key = f"{data['users'][student_id]['name']} ({student_id[:8]})"
            if not history_for_day: report[date_str][student_key] = "Absent (No Records)"
            else:
                present_count = sum(1 for r in history_for_day if r['status'] == 'Present')
                report[date_str][student_key] = f"Present ({present_count}/{len(history_for_day)})" if present_count > 0 else "Absent (All Lectures)"
    return jsonify(dict(sorted(report.items())))

# --- Background Processing ---
def attendance_processor():
    processed_lectures = defaultdict(set)
    while True:
        time.sleep(60)
        if not data['settings']['session_active']: continue
        now = get_utc_now(); today_date_str = now.strftime('%Y-%m-%d')
        for class_id, timetable in data['timetable'].items():
            day_schedule = timetable.get(now.strftime('%A'), {})
            for time_slot, subject in day_schedule.items():
                lecture_id = f"{today_date_str}-{class_id}-{time_slot}"
                if lecture_id in processed_lectures.get(today_date_str, set()): continue
                start_str, end_str = time_slot.split('-')
                start_time, end_time = parse_time(start_str.strip()), parse_time(end_str.strip())
                if now.time() > end_time:
                    lecture_duration = (datetime.combine(now.date(), end_time) - datetime.combine(now.date(), start_time)).total_seconds()
                    required_time = lecture_duration * 0.85
                    for student_id, user_info in data['users'].items():
                        if user_info.get('class_id') == class_id:
                            live_info = data['live_attendance'].get(student_id, {})
                            status = 'Present' if live_info.get('accumulated_time', 0) >= required_time and live_info.get('current_lecture') == f"{time_slot} ({subject})" else 'Absent'
                            data['attendance_history'][student_id].append({'date': today_date_str, 'lecture': f"{time_slot} ({subject})", 'status': status})
                    processed_lectures[today_date_str].add(lecture_id)
        if now.hour == 0 and now.minute < 2: processed_lectures.clear()

def session_cleanup():
    while True:
        time.sleep(20)
        now = get_utc_now()
        for student_id, live_info in list(data['live_attendance'].items()):
            if live_info.get('active') and live_info.get('last_ping') and (now - live_info['last_ping']).total_seconds() > 45:
                live_info['active'] = False

if __name__ == "__main__":
    threading.Thread(target=attendance_processor, daemon=True).start()
    threading.Thread(target=session_cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=10000, debug=False)

# --- END OF FILE main.py ---
