# --- START OF FILE main.py ---
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import threading
import time
import uuid
import pytz

app = Flask(__name__)

# --- In-memory data store ---
data = {
    'users': {
        'teacher1': {
            'username': 'teacher',
            'password_hash': generate_password_hash('teacher123'),
            'type': 'teacher',
            'name': 'Admin Teacher'
        },
        'student1': {
            'username': 'student',
            'password_hash': generate_password_hash('student123'),
            'type': 'student',
            'name': 'Test Student',
            'class_id': '10A'
        }
    },
    'live_attendance': defaultdict(lambda: {
        'active': False,
        'current_lecture': None,
        'accumulated_time': 0,
        'last_ping': None,
        'attendance_timer': False,
        'attendance_start': None,
        'status': 'Absent',
        'wifi_connected': False
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
            },
            "Tuesday": {
                "09:40-10:40": "Physics",
                "10:40-11:40": "Chemistry",
                "11:40-12:40": "Maths",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            },
            "Wednesday": {
                "09:40-10:40": "Chemistry",
                "10:40-11:40": "Maths",
                "11:40-12:40": "Physics",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            },
            "Thursday": {
                "09:40-10:40": "Maths",
                "10:40-11:40": "Physics",
                "11:40-12:40": "Chemistry",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            },
            "Friday": {
                "09:40-10:40": "Physics",
                "10:40-11:40": "Chemistry",
                "11:40-12:40": "Maths",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            },
            "Saturday": {
                "09:40-10:40": "Chemistry",
                "10:40-11:40": "Maths",
                "11:40-12:40": "Physics",
                "12:40-13:40": "Lunch",
                "13:40-14:40": "English",
                "14:40-15:40": "Computer Science",
                "15:40-16:40": "Physical Education"
            }
        }
    },
    'settings': {
        'authorized_bssids': ["11:22:33:44:55:66"],
        'session_active': False,
        'random_rings': []
    },
    'messages': []
}

TIMEZONE = 'Asia/Kolkata'

# --- Utility Functions ---
def get_current_time():
    return datetime.now(pytz.timezone(TIMEZONE))

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def get_current_lecture(class_id):
    if not class_id: return None
    
    now = get_current_time()
    day_of_week = now.strftime('%A')
    current_time = now.time()

    class_timetable = data['timetable'].get(class_id, {}).get(day_of_week, {})
    for time_slot, subject in class_timetable.items():
        try:
            start_str, end_str = time_slot.split('-')
            start_time = parse_time(start_str.strip())
            end_time = parse_time(end_str.strip())
            if start_time <= current_time <= end_time:
                return f"{time_slot} ({subject})"
        except ValueError:
            continue
    return None

def calculate_attendance_status(student_id, lecture):
    live_info = data['live_attendance'][student_id]
    
    if not lecture:
        return 'Absent'
    
    if live_info.get('attendance_timer', False):
        return 'Pending'
    
    time_slot = lecture.split(' (')[0]
    start_str, end_str = time_slot.split('-')
    start_time = parse_time(start_str.strip())
    end_time = parse_time(end_str.strip())
    lecture_duration = (datetime.combine(datetime.today(), end_time) - 
                       datetime.combine(datetime.today(), start_time)).total_seconds()
    required_time = lecture_duration * 0.85
    
    if live_info.get('accumulated_time', 0) >= required_time:
        return 'Present'
    return 'Absent'

# --- User & Session Management ---
@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    req = request.json
    if not req or not req.get('username') or not req.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    username = req['username']
    if any(u['username'] == username for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400

    user_id = str(uuid.uuid4())
    data['users'][user_id] = {
        'username': username,
        'password_hash': generate_password_hash(req['password']),
        'type': 'teacher',
        'name': req.get('name', username)
    }
    return jsonify({'message': 'Teacher registered successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    username = req.get('username')
    password = req.get('password')
    device_id = req.get('device_id')
    
    if not all([username, password, device_id]):
        return jsonify({'error': 'Missing credentials or device ID'}), 400

    user_id, user_info = next(((uid, uinfo) for uid, uinfo in data['users'].items() 
                             if uinfo['username'] == username), (None, None))
            
    if not user_id or not check_password_hash(user_info.get('password_hash', ''), password):
        return jsonify({'error': 'Invalid credentials'}), 401

    if user_info['type'] == 'student' and user_id in data['active_sessions'].values():
        active_device = next((dev for dev, uid in data['active_sessions'].items() if uid == user_id), None)
        if active_device != device_id:
            return jsonify({'error': 'This account is already logged in on another device.'}), 403

    data['active_sessions'][device_id] = user_id
    
    response = {
        'message': 'Login successful', 
        'user_id': user_id, 
        'type': user_info['type'], 
        'name': user_info.get('name', username)
    }
    if user_info['type'] == 'student':
        response['class_id'] = user_info.get('class_id')
        
    return jsonify(response), 200

@app.route('/logout', methods=['POST'])
def logout():
    device_id = request.json.get('device_id')
    student_id = request.json.get('student_id')
    
    if device_id in data['active_sessions']:
        if student_id in data['live_attendance']:
            data['live_attendance'][student_id]['active'] = False
            data['live_attendance'][student_id]['attendance_timer'] = False
            data['live_attendance'][student_id]['status'] = 'Absent'
        del data['active_sessions'][device_id]
    return jsonify({'message': 'Logged out'}), 200

# --- Teacher Endpoints ---
@app.route('/student/register', methods=['POST'])
def student_register():
    req = request.json
    if not all(key in req for key in ['username', 'password', 'name', 'class_id']):
        return jsonify({'error': 'Missing required fields'}), 400
        
    username = req['username']
    if any(u['username'] == username for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400

    user_id = str(uuid.uuid4())
    data['users'][user_id] = {
        'username': username,
        'password_hash': generate_password_hash(req['password']),
        'type': 'student',
        'name': req['name'],
        'class_id': req['class_id']
    }
    return jsonify({
        'message': 'Student registered successfully',
        'user_id': user_id,
        'name': req['name'],
        'class_id': req['class_id']
    }), 201

@app.route('/timetable', methods=['GET', 'POST'])
def manage_timetable():
    if request.method == 'POST':
        data['timetable'] = request.json
        return jsonify({'message': 'Timetable updated'}), 200
    return jsonify(data['timetable'])

@app.route('/settings/bssid', methods=['GET', 'POST'])
def manage_bssid():
    if request.method == 'POST':
        bssids = request.json.get('bssids', [])
        valid_bssids = []
        for bssid in bssids:
            if len(bssid.split(':')) == 6:
                valid_bssids.append(bssid.lower())
        data['settings']['authorized_bssids'] = valid_bssids
        return jsonify({'message': 'BSSID list updated'}), 200
    return jsonify({'bssids': data['settings']['authorized_bssids']})

@app.route('/students', methods=['GET'])
def get_all_students():
    students = [{
        'id': uid,
        'name': uinfo['name'],
        'username': uinfo['username'],
        'class_id': uinfo.get('class_id')
    } for uid, uinfo in data['users'].items() if uinfo['type'] == 'student']
    return jsonify(students)

@app.route('/classmates/<class_id>', methods=['GET'])
def get_classmates(class_id):
    classmates = [{
        'id': uid,
        'name': uinfo['name'],
        'username': uinfo['username']
    } for uid, uinfo in data['users'].items() 
     if uinfo['type'] == 'student' and uinfo.get('class_id') == class_id]
    return jsonify({'students': classmates})

@app.route('/student/profile/<student_id>', methods=['GET'])
def get_student_profile(student_id):
    if student_id not in data['users'] or data['users'][student_id]['type'] != 'student':
        return jsonify({'error': 'Student not found'}), 404
        
    history = data['attendance_history'].get(student_id, [])
    present_count = sum(1 for r in history if r['status'] == 'Present')
    total_count = len(history)
    
    lecture_stats = defaultdict(int)
    for record in history:
        if record['status'] == 'Absent':
            lecture_stats[record['lecture']] += 1
    
    most_missed = sorted(lecture_stats.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return jsonify({
        'name': data['users'][student_id]['name'],
        'class_id': data['users'][student_id].get('class_id'),
        'present_lectures': present_count,
        'total_lectures': total_count,
        'attendance_percent': (present_count / total_count * 100) if total_count > 0 else 0,
        'most_missed': most_missed,
        'detailed_report': history
    })

# --- Session Management ---
@app.route('/session/status', methods=['GET'])
def get_session_status():
    return jsonify({
        'session_active': data['settings']['session_active'],
        'random_rings': data['settings']['random_rings']
    })

@app.route('/session/start', methods=['POST'])
def start_session():
    data['settings']['session_active'] = True
    return jsonify({'message': 'Session started'})

@app.route('/session/end', methods=['POST'])
def end_session():
    data['settings']['session_active'] = False
    return jsonify({'message': 'Session ended'})

@app.route('/random_ring', methods=['POST'])
def random_ring():
    if not data['settings']['session_active']:
        return jsonify({'error': 'No active session'}), 400
        
    students = [uid for uid, uinfo in data['users'].items() if uinfo['type'] == 'student']
    if len(students) < 2:
        return jsonify({'error': 'Not enough students'}), 400
    
    attendance_stats = []
    for student_id in students:
        history = data['attendance_history'].get(student_id, [])
        present_count = sum(1 for r in history if r['status'] == 'Present')
        total_count = len(history)
        attendance_percent = (present_count / total_count * 100) if total_count > 0 else 0
        attendance_stats.append((student_id, attendance_percent))
    
    attendance_stats.sort(key=lambda x: x[1])
    
    selected = [
        attendance_stats[0][0],
        attendance_stats[-1][0]
    ]
    
    data['settings']['random_rings'] = selected
    return jsonify({
        'message': 'Random ring sent',
        'students': selected
    })

# --- Attendance Management ---
@app.route('/update_status', methods=['POST'])
def update_status():
    req = request.json
    student_id = req.get('student_id')
    status = req.get('status')
    
    if student_id not in data['users'] or data['users'][student_id]['type'] != 'student':
        return jsonify({'error': 'Invalid student ID'}), 400
    
    valid_statuses = ['Absent', 'Pending', 'Present']
    if status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    data['live_attendance'][student_id]['status'] = status
    
    if status == 'Present':
        lecture = data['live_attendance'][student_id].get('current_lecture')
        if lecture:
            today = get_current_time().strftime('%Y-%m-%d')
            data['attendance_history'][student_id].append({
                'date': today,
                'lecture': lecture,
                'status': 'Present',
                'timestamp': get_current_time().isoformat()
            })
    
    return jsonify({'message': 'Status updated'}), 200

@app.route('/ping', methods=['POST'])
def ping():
    PING_INTERVAL = 10
    device_id = request.json.get('device_id')
    student_id = request.json.get('student_id')
    wifi_status = request.json.get('wifi_status', False)
    
    if device_id not in data['active_sessions']:
        return jsonify({'error': 'Session expired. Please log in again.'}), 401
    
    if student_id != data['active_sessions'][device_id]:
        return jsonify({'error': 'Invalid student ID'}), 401
    
    student_info = data['users'][student_id]
    lecture = get_current_lecture(student_info.get('class_id'))
    
    live_data = data['live_attendance'][student_id]
    live_data['last_ping'] = get_current_time()
    live_data['wifi_connected'] = wifi_status
    
    if lecture:
        if live_data['current_lecture'] != lecture:
            live_data['current_lecture'] = lecture
            live_data['accumulated_time'] = 0
            
        live_data['active'] = True
        live_data['accumulated_time'] += PING_INTERVAL
        
        if live_data.get('attendance_timer', False):
            live_data['status'] = 'Pending'
        else:
            live_data['status'] = calculate_attendance_status(student_id, lecture)
    else:
        live_data['active'] = False
        live_data['current_lecture'] = None
        live_data['attendance_timer'] = False
        live_data['status'] = 'Absent'
    
    return jsonify({
        'status': 'pong',
        'current_lecture': live_data['current_lecture'],
        'accumulated_time': live_data['accumulated_time'],
        'attendance_status': live_data['status']
    }), 200

@app.route('/complete_attendance', methods=['POST'])
def complete_attendance():
    req = request.json
    student_id = req.get('student_id')
    lecture = req.get('lecture')
    duration = req.get('duration', 0)
    
    if student_id not in data['users']:
        return jsonify({'error': 'Invalid student ID'}), 400
        
    live_data = data['live_attendance'][student_id]
    live_data['accumulated_time'] += duration
    live_data['attendance_timer'] = False
    live_data['status'] = 'Present'
    
    today = get_current_time().strftime('%Y-%m-%d')
    data['attendance_history'][student_id].append({
        'date': today,
        'lecture': lecture,
        'status': 'Present',
        'timestamp': get_current_time().isoformat()
    })
    
    return jsonify({'message': 'Attendance marked'}), 200

@app.route('/mark_present', methods=['POST'])
def mark_present():
    student_id = request.json.get('student_id')
    if student_id not in data['users']:
        return jsonify({'error': 'Invalid student ID'}), 400
        
    today = get_current_time().strftime('%Y-%m-%d')
    lecture = get_current_lecture(data['users'][student_id].get('class_id'))
    
    if not lecture:
        return jsonify({'error': 'No active lecture'}), 400
        
    data['attendance_history'][student_id].append({
        'date': today,
        'lecture': lecture,
        'status': 'Present',
        'timestamp': get_current_time().isoformat()
    })
    
    # Update live status
    data['live_attendance'][student_id]['status'] = 'Present'
    
    return jsonify({'message': 'Student marked present'}), 200

@app.route('/live_data', methods=['GET'])
def get_live_data():
    response = {'students': [], 'random_rings': data['settings']['random_rings']}
    
    for user_id, user_info in data['users'].items():
        if user_info['type'] == 'student':
            live_info = data['live_attendance'][user_id]
            
            status = live_info.get('status', 'Absent')
            
            last_update = live_info.get('last_ping')
            if last_update:
                last_update_str = last_update.strftime('%Y-%m-%d %H:%M:%S')
            else:
                last_update_str = "Never"
                
            response['students'].append({
                'id': user_id,
                'name': user_info['name'],
                'class_id': user_info.get('class_id'),
                'status': status,
                'current_lecture': live_info['current_lecture'],
                'accumulated_time': live_info.get('accumulated_time', 0),
                'last_update': last_update_str,
                'wifi_connected': live_info.get('wifi_connected', False),
                'attendance_timer': live_info.get('attendance_timer', False)
            })
    
    return jsonify(response)

@app.route('/student/attendance_history/<student_id>', methods=['GET'])
def get_student_history(student_id):
    return jsonify(data['attendance_history'].get(student_id, []))

@app.route('/student/academic_info/<student_id>', methods=['GET'])
def get_academic_info(student_id):
    if student_id not in data['users']:
        return jsonify({'error': 'Student not found'}), 404
        
    history = data['attendance_history'].get(student_id, [])
    present_count = sum(1 for r in history if r['status'] == 'Present')
    total_count = len(history)
    
    today = get_current_time().strftime('%Y-%m-%d')
    today_status = "Unknown"
    today_records = [r for r in history if r['date'] == today]
    if today_records:
        present_today = sum(1 for r in today_records if r['status'] == 'Present')
        today_status = f"Present for {present_today}/{len(today_records)} lectures"
    
    return jsonify({
        'class_id': data['users'][student_id].get('class_id'),
        'attendance_percentage': (present_count / total_count * 100) if total_count > 0 else 0,
        'current_lecture': data['live_attendance'][student_id].get('current_lecture'),
        'today_status': today_status
    })

@app.route('/report', methods=['GET'])
def generate_report():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    try:
        from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
    
    report = defaultdict(dict)
    all_student_ids = [uid for uid, uinfo in data['users'].items() if uinfo['type'] == 'student']
    
    for day_delta in range((to_date - from_date).days + 1):
        current_date = from_date + timedelta(days=day_delta)
        date_str = current_date.strftime('%Y-%m-%d')
        
        for student_id in all_student_ids:
            history_for_day = [rec for rec in data['attendance_history'].get(student_id, []) 
                            if rec['date'] == date_str]
            
            if not history_for_day:
                report[date_str][student_id] = 'Absent'
            else:
                present_count = sum(1 for r in history_for_day if r['status'] == 'Present')
                if present_count > 0:
                    report[date_str][student_id] = 'Present'
                else:
                    report[date_str][student_id] = 'Absent'
    
    return jsonify(dict(sorted(report.items())))

# --- Messaging System ---
@app.route('/send_message', methods=['POST'])
def send_message():
    req = request.json
    from_id = req.get('from_id')
    to_username = req.get('to_username')
    content = req.get('content')
    
    if not all([from_id, to_username, content]):
        return jsonify({'error': 'Missing required fields'}), 400
        
    recipient_id, recipient_info = next(((uid, uinfo) for uid, uinfo in data['users'].items() 
                                      if uinfo['username'] == to_username), (None, None))
    if not recipient_id:
        return jsonify({'error': 'Recipient not found'}), 404
        
    data['messages'].append({
        'from_id': from_id,
        'from_name': data['users'][from_id]['name'],
        'to_id': recipient_id,
        'content': content,
        'timestamp': get_current_time().isoformat()
    })
    
    return jsonify({'message': 'Message sent'}), 200

@app.route('/messages/<user_id>', methods=['GET'])
def get_messages(user_id):
    if user_id not in data['users']:
        return jsonify({'error': 'User not found'}), 404
        
    messages = [msg for msg in data['messages'] if msg['to_id'] == user_id or msg['from_id'] == user_id]
    
    return jsonify({'messages': messages})

# --- Background Processing ---
def attendance_processor():
    while True:
        now = get_current_time()
        today_date_str = now.strftime('%Y-%m-%d')
        
        for class_id, timetable in data['timetable'].items():
            day_schedule = timetable.get(now.strftime('%A'), {})
            
            for time_slot, subject in day_schedule.items():
                try:
                    start_str, end_str = time_slot.split('-')
                    start_time = parse_time(start_str.strip())
                    end_time = parse_time(end_str.strip())
                    
                    if now.time() > end_time:
                        lecture_duration = (datetime.combine(now.date(), end_time) - 
                                         datetime.combine(now.date(), start_time)).total_seconds()
                        required_time = lecture_duration * 0.85
                        
                        for student_id, user_info in data['users'].items():
                            if user_info.get('class_id') == class_id:
                                live_info = data['live_attendance'][student_id]
                                lecture_str = f"{time_slot} ({subject})"
                                
                                existing_records = [r for r in data['attendance_history'].get(student_id, []) 
                                                  if r['date'] == today_date_str and r['lecture'] == lecture_str]
                                
                                if not existing_records:
                                    status = 'Present' if live_info.get('accumulated_time', 0) >= required_time else 'Absent'
                                    data['attendance_history'][student_id].append({
                                        'date': today_date_str,
                                        'lecture': lecture_str,
                                        'status': status,
                                        'timestamp': now.isoformat()
                                    })
                except ValueError:
                    continue
        
        time.sleep(60)

def session_cleanup():
    while True:
        now = get_current_time()
        for student_id, live_info in list(data['live_attendance'].items()):
            if live_info.get('last_ping') and (now - live_info['last_ping']).total_seconds() > 30:
                live_info['active'] = False
                live_info['attendance_timer'] = False
                live_info['status'] = 'Absent'
        time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=attendance_processor, daemon=True).start()
    threading.Thread(target=session_cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)
# --- END OF FILE main.py ---
