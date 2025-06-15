from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import threading
import time
import uuid
import pytz

app = Flask(__name__)

data = {
    'users': {
        'teacher1': {
            'username': 'teacher',
            'password_hash': generate_password_hash('teacher123'),
            'type': 'teacher',
            'name': 'Admin Teacher'
        }
    },
    'live_attendance': defaultdict(lambda: {
        'active': False, 
        'current_lecture': None, 
        'accumulated_time': 0, 
        'last_ping': None,
        'attendance_timer': False,
        'attendance_start': None
    }),
    'attendance_history': defaultdict(list),
    'active_sessions': {},
    'timetable': {
        "10A": {
            "Monday": {
                "09:40-10:40": "Maths",
                "10:40-11:40": "Physics",
                "11:40-12:40": "Chemistry",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            }
        }
    },
    'settings': {
        'authorized_bssids': [],
        'session_active': False,
        'random_rings': []
    }
}

TIMEZONE = 'Asia/Kolkata'

def get_current_time():
    return datetime.now(pytz.timezone(TIMEZONE))

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def get_current_lecture(class_id):
    if not class_id: return None
    now = get_current_time()
    day = now.strftime('%A')
    time_now = now.time()
    class_tt = data['timetable'].get(class_id, {}).get(day, {})
    for slot, subject in class_tt.items():
        try:
            start, end = map(str.strip, slot.split('-'))
            s_time = parse_time(start)
            e_time = parse_time(end)
            if s_time <= time_now <= e_time:
                return f"{slot} ({subject})"
        except:
            continue
    return None

def calculate_attendance_status(student_id, lecture):
    info = data['live_attendance'][student_id]
    if not lecture or not info['attendance_timer']:
        return 'Absent'
    start_str, end_str = lecture.split(' (')[0].split('-')
    s = parse_time(start_str.strip())
    e = parse_time(end_str.strip())
    duration = (datetime.combine(datetime.today(), e) - datetime.combine(datetime.today(), s)).total_seconds()
    required = duration * 0.85
    return 'Present' if info['accumulated_time'] >= required else 'Absent'

@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    req = request.json
    if not req.get('username') or not req.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    if any(u['username'] == req['username'] for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400
    user_id = str(uuid.uuid4())
    data['users'][user_id] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'teacher',
        'name': req.get('name', req['username'])
    }
    return jsonify({'message': 'Teacher registered successfully'}), 201

@app.route('/student/register', methods=['POST'])
def student_register():
    req = request.json
    if not all(k in req for k in ['username', 'password', 'name', 'class_id']):
        return jsonify({'error': 'Missing required fields'}), 400
    if any(u['username'] == req['username'] for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400
    user_id = str(uuid.uuid4())
    data['users'][user_id] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'student',
        'name': req['name'],
        'class_id': req['class_id']
    }
    return jsonify({'message': 'Student registered successfully', 'user_id': user_id}), 201

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    username, password, device_id = req.get('username'), req.get('password'), req.get('device_id')
    if not all([username, password, device_id]):
        return jsonify({'error': 'Missing credentials'}), 400
    user_id, info = next(((uid, u) for uid, u in data['users'].items() if u['username'] == username), (None, None))
    if not user_id or not check_password_hash(info['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    if info['type'] == 'student' and user_id in data['active_sessions'].values():
        active_device = next((d for d, uid in data['active_sessions'].items() if uid == user_id), None)
        if active_device != device_id:
            return jsonify({'error': 'Already logged in elsewhere'}), 403
    data['active_sessions'][device_id] = user_id
    return jsonify({
        'message': 'Login successful',
        'user_id': user_id,
        'type': info['type'],
        'name': info['name'],
        'class_id': info.get('class_id')
    })

@app.route('/logout', methods=['POST'])
def logout():
    req = request.json
    device_id = req.get('device_id')
    student_id = req.get('student_id')
    if device_id in data['active_sessions']:
        if student_id in data['live_attendance']:
            data['live_attendance'][student_id]['active'] = False
            data['live_attendance'][student_id]['attendance_timer'] = False
        del data['active_sessions'][device_id]
    return jsonify({'message': 'Logged out'}), 200

@app.route('/ping', methods=['POST'])
def ping():
    device_id = request.json.get('device_id')
    student_id = request.json.get('student_id')
    if data['active_sessions'].get(device_id) != student_id:
        return jsonify({'error': 'Invalid session'}), 401
    lecture = get_current_lecture(data['users'][student_id].get('class_id'))
    info = data['live_attendance'][student_id]
    info['last_ping'] = get_current_time()
    if lecture:
        if info['current_lecture'] != lecture:
            info['current_lecture'] = lecture
            info['accumulated_time'] = 0
        info['active'] = True
        info['accumulated_time'] += 10
        if not info['attendance_timer']:
            info['attendance_timer'] = True
            info['attendance_start'] = get_current_time()
    else:
        info.update({'active': False, 'current_lecture': None, 'attendance_timer': False})
    return jsonify({'status': 'pong', 'current_lecture': info['current_lecture'], 'accumulated_time': info['accumulated_time']}), 200

@app.route('/student/attendance_history/<student_id>', methods=['GET'])
def attendance_history(student_id):
    return jsonify(data['attendance_history'].get(student_id, []))

@app.route('/student/academic_info/<student_id>', methods=['GET'])
def academic_info(student_id):
    if student_id not in data['users']:
        return jsonify({'error': 'Student not found'}), 404
    records = data['attendance_history'].get(student_id, [])
    present = sum(1 for r in records if r['status'] == 'Present')
    percent = (present / len(records) * 100) if records else 0
    today = get_current_time().strftime('%Y-%m-%d')
    today_rec = [r for r in records if r['date'] == today]
    today_status = "Present" if any(r['status'] == 'Present' for r in today_rec) else "Absent"
    return jsonify({
        'class_id': data['users'][student_id].get('class_id'),
        'attendance_percentage': percent,
        'current_lecture': data['live_attendance'][student_id].get('current_lecture'),
        'today_status': today_status
    })

def attendance_processor():
    while True:
        now = get_current_time()
        today_str = now.strftime('%Y-%m-%d')
        for class_id, timetable in data['timetable'].items():
            slots = timetable.get(now.strftime('%A'), {})
            for slot, subject in slots.items():
                try:
                    s_str, e_str = slot.split('-')
                    s, e = parse_time(s_str), parse_time(e_str)
                    if now.time() > e:
                        duration = (datetime.combine(now.date(), e) - datetime.combine(now.date(), s)).total_seconds()
                        required = duration * 0.85
                        for student_id, info in data['users'].items():
                            if info.get('class_id') != class_id: continue
                            live = data['live_attendance'][student_id]
                            lecture_str = f"{slot} ({subject})"
                            already_recorded = any(r['lecture'] == lecture_str and r['date'] == today_str for r in data['attendance_history'][student_id])
                            if not already_recorded:
                                status = 'Present' if live.get('accumulated_time', 0) >= required else 'Absent'
                                data['attendance_history'][student_id].append({
                                    'date': today_str,
                                    'lecture': lecture_str,
                                    'status': status,
                                    'timestamp': now.isoformat()
                                })
                except:
                    continue
        time.sleep(60)

def session_cleanup():
    while True:
        now = get_current_time()
        for student_id, info in data['live_attendance'].items():
            if info.get('last_ping') and (now - info['last_ping']).total_seconds() > 30:
                info['active'] = False
                info['attendance_timer'] = False
        time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=attendance_processor, daemon=True).start()
    threading.Thread(target=session_cleanup, daemon=True).start()
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
