# Enhanced Flask Attendance Server with TechU Features

from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import uuid
import pytz
import os

app = Flask(__name__)

TIMEZONE = 'Asia/Kolkata'
data = {
    'users': {},
    'live_attendance': defaultdict(lambda: {
        'active': False, 'current_lecture': None, 'accumulated_time': 0, 
        'last_ping': None, 'attendance_timer': False, 'attendance_start': None
    }),
    'attendance_history': defaultdict(list),
    'active_sessions': {},
    'timetable': {},
    'settings': {
        'authorized_bssids': [], 'session_active': False, 'random_rings': []
    },
    'messages': [],
}

# --- Utility Functions ---
def get_current_time():
    return datetime.now(pytz.timezone(TIMEZONE))

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def get_current_lecture(class_id):
    now = get_current_time()
    day = now.strftime('%A')
    time_now = now.time()
    class_tt = data['timetable'].get(class_id, {}).get(day, {})
    for slot, subject in class_tt.items():
        try:
            start, end = map(str.strip, slot.split('-'))
            s_time, e_time = parse_time(start), parse_time(end)
            if s_time <= time_now <= e_time:
                return f"{slot} ({subject})"
        except:
            continue
    return None

def calc_attendance_status(student_id, lecture):
    info = data['live_attendance'][student_id]
    if not lecture or not info['attendance_timer']:
        return 'Absent'
    s_str, e_str = lecture.split(' (')[0].split('-')
    s, e = parse_time(s_str), parse_time(e_str)
    duration = (datetime.combine(datetime.today(), e) - datetime.combine(datetime.today(), s)).total_seconds()
    return 'Present' if info['accumulated_time'] >= 0.85 * duration else 'Absent'

# --- API Endpoints ---
@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    req = request.json
    username = req.get('username')
    if username in [u['username'] for u in data['users'].values()]:
        return jsonify({'error': 'Username exists'}), 400
    uid = str(uuid.uuid4())
    data['users'][uid] = {
        'username': username,
        'password_hash': generate_password_hash(req['password']),
        'type': 'teacher',
        'name': req.get('name', username)
    }
    return jsonify({'message': 'Registered'}), 201

@app.route('/student/register', methods=['POST'])
def student_register():
    req = request.json
    username = req['username']
    if username in [u['username'] for u in data['users'].values()]:
        return jsonify({'error': 'Username exists'}), 400
    uid = str(uuid.uuid4())
    data['users'][uid] = {
        'username': username,
        'password_hash': generate_password_hash(req['password']),
        'type': 'student', 'name': req['name'], 'class_id': req['class_id']
    }
    return jsonify({'user_id': uid}), 201

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    username, password, device_id = req['username'], req['password'], req['device_id']
    user = next(((uid, u) for uid, u in data['users'].items() if u['username'] == username), (None, None))
    if not user[0] or not check_password_hash(user[1]['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    data['active_sessions'][device_id] = user[0]
    response = {'user_id': user[0], 'type': user[1]['type'], 'name': user[1]['name']}
    if user[1]['type'] == 'student':
        response['class_id'] = user[1]['class_id']
    return jsonify(response)

@app.route('/logout', methods=['POST'])
def logout():
    req = request.json
    device_id = req['device_id']
    student_id = req.get('student_id')
    data['active_sessions'].pop(device_id, None)
    if student_id:
        data['live_attendance'][student_id]['active'] = False
        data['live_attendance'][student_id]['attendance_timer'] = False
    return jsonify({'message': 'Logged out'})

@app.route('/ping', methods=['POST'])
def ping():
    req = request.json
    sid, dev_id = req['student_id'], req['device_id']
    if data['active_sessions'].get(dev_id) != sid:
        return jsonify({'error': 'Invalid session'}), 401
    lec = get_current_lecture(data['users'][sid]['class_id'])
    info = data['live_attendance'][sid]
    info['last_ping'] = get_current_time()
    if lec:
        if info['current_lecture'] != lec:
            info['current_lecture'] = lec
            info['accumulated_time'] = 0
        info['active'] = True
        info['accumulated_time'] += 10
        info['attendance_timer'] = True
    else:
        info.update({'active': False, 'attendance_timer': False, 'current_lecture': None})
    return jsonify({'current_lecture': lec, 'accumulated_time': info['accumulated_time']})

@app.route('/timetable', methods=['GET', 'POST'])
def timetable():
    if request.method == 'POST':
        data['timetable'] = request.json
        return jsonify({'message': 'Updated'})
    return jsonify(data['timetable'])

@app.route('/settings/bssid', methods=['GET', 'POST'])
def bssid():
    if request.method == 'POST':
        bssids = request.json.get('bssids', [])
        data['settings']['authorized_bssids'] = [b.lower() for b in bssids if len(b.split(':')) == 6]
        return jsonify({'message': 'Updated'})
    return jsonify({'bssids': data['settings']['authorized_bssids']})

@app.route('/students', methods=['GET'])
def students():
    return jsonify([{**v, 'id': k} for k, v in data['users'].items() if v['type'] == 'student'])

@app.route('/student/profile/<sid>', methods=['GET'])
def profile(sid):
    records = data['attendance_history'].get(sid, [])
    present = sum(1 for r in records if r['status'] == 'Present')
    most_missed = defaultdict(int)
    for r in records:
        if r['status'] == 'Absent':
            most_missed[r['lecture']] += 1
    return jsonify({
        'name': data['users'][sid]['name'],
        'class_id': data['users'][sid]['class_id'],
        'present_lectures': present,
        'total_lectures': len(records),
        'attendance_percent': (present / len(records) * 100) if records else 0,
        'most_missed': sorted(most_missed.items(), key=lambda x: x[1], reverse=True),
        'detailed_report': records
    })

@app.route('/report', methods=['GET'])
def report():
    start = datetime.strptime(request.args['from_date'], '%Y-%m-%d').date()
    end = datetime.strptime(request.args['to_date'], '%Y-%m-%d').date()
    result = defaultdict(dict)
    for delta in range((end - start).days + 1):
        date = (start + timedelta(days=delta)).strftime('%Y-%m-%d')
        for uid, info in data['users'].items():
            if info['type'] != 'student': continue
            records = [r for r in data['attendance_history'][uid] if r['date'] == date]
            result[date][uid] = 'Present' if any(r['status'] == 'Present' for r in records) else 'Absent'
    return jsonify(result)

# --- Background Threads ---
def auto_mark_attendance():
    while True:
        now = get_current_time()
        date_str = now.strftime('%Y-%m-%d')
        for cid, timetable in data['timetable'].items():
            slots = timetable.get(now.strftime('%A'), {})
            for slot, subject in slots.items():
                try:
                    s_str, e_str = slot.split('-')
                    s, e = parse_time(s_str), parse_time(e_str)
                    if now.time() > e:
                        duration = (datetime.combine(now.date(), e) - datetime.combine(now.date(), s)).total_seconds()
                        req_time = duration * 0.85
                        for sid, user in data['users'].items():
                            if user.get('class_id') == cid:
                                lec = f"{slot} ({subject})"
                                records = data['attendance_history'][sid]
                                if any(r['date'] == date_str and r['lecture'] == lec for r in records):
                                    continue
                                status = 'Present' if data['live_attendance'][sid]['accumulated_time'] >= req_time else 'Absent'
                                records.append({
                                    'date': date_str, 'lecture': lec, 'status': status,
                                    'timestamp': now.isoformat()
                                })
                except:
                    continue
        time.sleep(60)

def clear_inactive():
    while True:
        now = get_current_time()
        for sid, info in list(data['live_attendance'].items()):
            if info.get('last_ping') and (now - info['last_ping']).total_seconds() > 30:
                info['active'] = False
                info['attendance_timer'] = False
        time.sleep(15)

# --- Server Init ---
if __name__ == '__main__':
    threading.Thread(target=auto_mark_attendance, daemon=True).start()
    threading.Thread(target=clear_inactive, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
