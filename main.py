# -----------------------------
# main_server.py
# -----------------------------

from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time
import uuid
import pytz

app = Flask(__name__)

TIMEZONE = 'Asia/Kolkata'
PING_INTERVAL = 10

# In-memory data store
store = {
    'users': {},
    'active_sessions': {},
    'live_attendance': defaultdict(lambda: {
        'active': False,
        'current_lecture': None,
        'accumulated_time': 0,
        'last_ping': None,
        'attendance_timer': False,
        'attendance_start': None
    }),
    'attendance_history': defaultdict(list),
    'timetable': {},
    'settings': {
        'authorized_bssids': [],
        'session_active': False,
        'random_rings': []
    }
}

def get_current_time():
    return datetime.now(pytz.timezone(TIMEZONE))

def parse_time(tstr):
    return datetime.strptime(tstr, "%H:%M").time()

def get_current_lecture(class_id):
    now = get_current_time()
    today = now.strftime('%A')
    current_time = now.time()
    for slot, subject in store['timetable'].get(class_id, {}).get(today, {}).items():
        start, end = slot.split('-')
        if parse_time(start) <= current_time <= parse_time(end):
            return f"{slot} ({subject})"
    return None

def calculate_status(sid, lecture):
    info = store['live_attendance'][sid]
    if not lecture or not info['attendance_timer']:
        return 'Absent'
    slot = lecture.split(' (')[0]
    s, e = slot.split('-')
    duration = (datetime.combine(datetime.today(), parse_time(e)) - datetime.combine(datetime.today(), parse_time(s))).total_seconds()
    return 'Present' if info['accumulated_time'] >= duration * 0.85 else 'Absent'

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    username = req.get('username')
    password = req.get('password')
    device_id = req.get('device_id')
    user = next(((uid, u) for uid, u in store['users'].items() if u['username'] == username), (None, None))
    if not user[0] or not check_password_hash(user[1]['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    uid, info = user
    store['active_sessions'][device_id] = uid
    res = {'message': 'Login successful', 'user_id': uid, 'type': info['type'], 'name': info['name']}
    if info['type'] == 'student':
        res['class_id'] = info['class_id']
    return jsonify(res)

@app.route('/teacher/register', methods=['POST'])
def register_teacher():
    req = request.json
    uid = str(uuid.uuid4())
    store['users'][uid] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'teacher',
        'name': req.get('name', req['username'])
    }
    return jsonify({'message': 'Registered'}), 201

@app.route('/student/register', methods=['POST'])
def register_student():
    req = request.json
    uid = str(uuid.uuid4())
    store['users'][uid] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'student',
        'name': req['name'],
        'class_id': req['class_id']
    }
    return jsonify({'message': 'Student registered', 'user_id': uid}), 201

@app.route('/ping', methods=['POST'])
def ping():
    sid = request.json.get('student_id')
    device = request.json.get('device_id')
    status = request.json.get('status')
    if device not in store['active_sessions']:
        return jsonify({'error': 'Session expired'}), 401
    if sid != store['active_sessions'][device]:
        return jsonify({'error': 'Invalid ID'}), 401
    info = store['live_attendance'][sid]
    info['last_ping'] = get_current_time()
    lec = get_current_lecture(store['users'][sid].get('class_id'))
    if lec:
        if info['current_lecture'] != lec:
            info['current_lecture'] = lec
            info['accumulated_time'] = 0
        info['active'] = True
        info['accumulated_time'] += PING_INTERVAL
        if status == 'present':
            info['attendance_timer'] = True
            info['attendance_start'] = get_current_time()
    else:
        info['active'] = False
        info['current_lecture'] = None
        info['attendance_timer'] = False
    return jsonify({
        'status': 'pong',
        'current_lecture': info['current_lecture'],
        'accumulated_time': info['accumulated_time']
    })

@app.route('/complete_attendance', methods=['POST'])
def complete_attendance():
    req = request.json
    sid = req['student_id']
    lec = get_current_lecture(store['users'][sid]['class_id'])
    store['attendance_history'][sid].append({
        'date': get_current_time().strftime('%Y-%m-%d'),
        'lecture': lec,
        'status': 'Present',
        'timestamp': get_current_time().isoformat()
    })
    return jsonify({'message': 'Marked'}), 200

@app.route('/student/profile/<sid>', methods=['GET'])
def student_profile(sid):
    history = store['attendance_history'].get(sid, [])
    pcount = sum(1 for r in history if r['status'] == 'Present')
    total = len(history)
    return jsonify({
        'name': store['users'][sid]['name'],
        'class_id': store['users'][sid].get('class_id'),
        'present_lectures': pcount,
        'total_lectures': total,
        'attendance_percent': (pcount / total * 100) if total > 0 else 0,
        'detailed_report': history
    })

@app.route('/timetable', methods=['GET', 'POST'])
def timetable():
    if request.method == 'POST':
        store['timetable'] = request.json
        return jsonify({'message': 'Updated'}), 200
    return jsonify(store['timetable'])

@app.route('/live_data', methods=['GET'])
def live_data():
    output = {'students': []}
    for sid, info in store['live_attendance'].items():
        user = store['users'].get(sid, {})
        status = calculate_status(sid, info.get('current_lecture'))
        last = info.get('last_ping')
        output['students'].append({
            'id': sid,
            'name': user.get('name'),
            'class_id': user.get('class_id'),
            'status': status,
            'current_lecture': info.get('current_lecture'),
            'accumulated_time': info.get('accumulated_time', 0),
            'last_update': last.strftime('%Y-%m-%d %H:%M:%S') if last else 'Never'
        })
    return jsonify(output)

@app.route('/session/status', methods=['GET'])
def session_status():
    return jsonify({'session_active': store['settings']['session_active']})

@app.route('/session/start', methods=['POST'])
def session_start():
    store['settings']['session_active'] = True
    return jsonify({'message': 'Session started'})

@app.route('/session/end', methods=['POST'])
def session_end():
    store['settings']['session_active'] = False
    return jsonify({'message': 'Session ended'})

if __name__ == '__main__':
    app.run(debug=True)
