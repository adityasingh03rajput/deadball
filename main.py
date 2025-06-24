from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import hashlib
import uuid
import time
from functools import wraps
import threading
import json
import os

app = Flask(__name__)

# Database structure
db = {
    'teachers': {
        'admin': {
            'id': 'admin',
            'password': '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',  # 'password' hashed
            'name': 'Admin Teacher',
            'bssid_mapping': {}  # Will store classroom to BSSID mappings
        }
    },
    'students': {
        'student1': {
            'id': 'student1',
            'password': '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',  # 'password' hashed
            'name': 'John Doe',
            'branch': 'Computer Science',
            'semester': '3',
            'classroom': 'A'
        }
    },
    'sessions': {},
    'attendance': {},
    'timetable': {
        'Computer Science': {
            '3': [
                ['Monday', '09:00', '10:30', 'Data Structures', 'A'],
                ['Monday', '11:00', '12:30', 'Algorithms', 'A'],
                ['Tuesday', '09:00', '10:30', 'Database Systems', 'A'],
                ['Wednesday', '09:00', '10:30', 'Operating Systems', 'A'],
                ['Thursday', '09:00', '10:30', 'Computer Networks', 'A'],
                ['Friday', '09:00', '10:30', 'Software Engineering', 'A']
            ]
        }
    },
    'active_timers': {},
    'active_sessions': {}
}

# Helper functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_teacher(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json()
        if not data or 'id' not in data or 'password' not in data:
            return jsonify({'error': 'Missing credentials'}), 400
        
        teacher_id = data['id']
        password = data['password']
        
        if teacher_id not in db['teachers']:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if db['teachers'][teacher_id]['password'] != hash_password(password):
            return jsonify({'error': 'Invalid password'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def authenticate_student(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json()
        if not data or 'student_id' not in data or 'device_id' not in data:
            return jsonify({'error': 'Missing student ID or device ID'}), 400
        
        student_id = data['student_id']
        device_id = data['device_id']
        
        if student_id not in db['students']:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check if session exists and is valid
        if student_id in db['active_sessions']:
            session = db['active_sessions'][student_id]
            if session['device_id'] != device_id:
                return jsonify({'error': 'Session expired or invalid device'}), 401
        else:
            return jsonify({'error': 'No active session found'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def cleanup_expired_sessions():
    while True:
        current_time = time.time()
        expired_sessions = []
        
        for student_id, session in db['active_sessions'].items():
            if current_time - session['last_ping'] > 60:  # 1 minute timeout
                expired_sessions.append(student_id)
        
        for student_id in expired_sessions:
            if student_id in db['active_sessions']:
                del db['active_sessions'][student_id]
        
        time.sleep(30)  # Check every 30 seconds

# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_expired_sessions, daemon=True)
cleanup_thread.start()

# Routes
@app.route('/teacher/login', methods=['POST'])
@authenticate_teacher
def teacher_login():
    data = request.get_json()
    teacher_id = data['id']
    
    # Create a session token
    session_token = str(uuid.uuid4())
    
    return jsonify({
        'message': 'Login successful',
        'teacher': db['teachers'][teacher_id],
        'session_token': session_token
    })

@app.route('/teacher/set_bssid', methods=['POST'])
@authenticate_teacher
def set_bssid():
    data = request.get_json()
    
    if 'classroom' not in data or 'bssid' not in data:
        return jsonify({'error': 'Missing classroom or BSSID'}), 400
    
    classroom = data['classroom']
    bssid = data['bssid']
    
    # Validate BSSID format (simple check)
    if len(bssid) != 17 or bssid.count(':') != 5:
        return jsonify({'error': 'Invalid BSSID format'}), 400
    
    # Update the BSSID mapping
    teacher_id = data['id']
    db['teachers'][teacher_id]['bssid_mapping'][classroom] = bssid
    
    return jsonify({
        'message': f'BSSID for classroom {classroom} updated successfully',
        'bssid_mapping': db['teachers'][teacher_id]['bssid_mapping']
    })

@app.route('/student/login', methods=['POST'])
def student_login():
    data = request.get_json()
    
    if not data or 'id' not in data or 'password' not in data or 'device_id' not in data:
        return jsonify({'error': 'Missing credentials or device ID'}), 400
    
    student_id = data['id']
    password = data['password']
    device_id = data['device_id']
    
    if student_id not in db['students']:
        return jsonify({'error': 'Student not found'}), 404
    
    if db['students'][student_id]['password'] != hash_password(password):
        return jsonify({'error': 'Invalid password'}), 401
    
    # Create a session
    db['active_sessions'][student_id] = {
        'device_id': device_id,
        'last_ping': time.time(),
        'login_time': datetime.now().isoformat()
    }
    
    return jsonify({
        'message': 'Login successful',
        'student': db['students'][student_id]
    })

@app.route('/student/checkin', methods=['POST'])
@authenticate_student
def student_checkin():
    data = request.get_json()
    student_id = data['student_id']
    bssid = data.get('bssid', None)
    
    student = db['students'][student_id]
    classroom = student['classroom']
    
    # Get teacher's BSSID mapping for this classroom
    expected_bssid = None
    for teacher in db['teachers'].values():
        if classroom in teacher['bssid_mapping']:
            expected_bssid = teacher['bssid_mapping'][classroom]
            break
    
    # Check if BSSID matches expected
    status = "present"
    if expected_bssid and bssid:
        if bssid.lower() != expected_bssid.lower():
            status = "wrong_location"
    elif expected_bssid and not bssid:
        status = "no_bssid"
    
    # Record attendance
    today = datetime.now().strftime('%Y-%m-%d')
    session_id = str(uuid.uuid4())
    
    if today not in db['attendance']:
        db['attendance'][today] = {}
    
    db['attendance'][today][session_id] = {
        'student_id': student_id,
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'bssid': bssid,
        'expected_bssid': expected_bssid,
        'classroom': classroom
    }
    
    return jsonify({
        'message': 'Check-in recorded successfully',
        'status': status
    })

@app.route('/student/timer/start', methods=['POST'])
@authenticate_student
def start_timer():
    data = request.get_json()
    student_id = data['student_id']
    
    if student_id in db['active_timers']:
        return jsonify({'error': 'Timer already running'}), 400
    
    db['active_timers'][student_id] = {
        'start_time': time.time(),
        'duration': 3600  # 1 hour default duration
    }
    
    return jsonify({
        'message': 'Timer started successfully',
        'remaining': 3600
    })

@app.route('/student/timer/stop', methods=['POST'])
@authenticate_student
def stop_timer():
    data = request.get_json()
    student_id = data['student_id']
    
    if student_id not in db['active_timers']:
        return jsonify({'error': 'No active timer found'}), 404
    
    timer = db['active_timers'][student_id]
    elapsed = time.time() - timer['start_time']
    remaining = max(0, timer['duration'] - elapsed)
    
    del db['active_timers'][student_id]
    
    return jsonify({
        'message': 'Timer stopped successfully',
        'elapsed': elapsed,
        'remaining': remaining
    })

@app.route('/student/get_status', methods=['GET'])
@authenticate_student
def get_status():
    student_id = request.args.get('student_id')
    
    # Check timer status
    timer_status = {}
    if student_id in db['active_timers']:
        timer = db['active_timers'][student_id]
        elapsed = time.time() - timer['start_time']
        remaining = max(0, timer['duration'] - elapsed)
        
        timer_status = {
            'status': 'running',
            'remaining': remaining
        }
    else:
        timer_status = {
            'status': 'stopped',
            'remaining': 0
        }
    
    # Get expected BSSID for student's classroom
    student = db['students'][student_id]
    classroom = student['classroom']
    expected_bssid = None
    
    for teacher in db['teachers'].values():
        if classroom in teacher['bssid_mapping']:
            expected_bssid = teacher['bssid_mapping'][classroom]
            break
    
    return jsonify({
        'connected': True,
        'timer': timer_status,
        'expected_bssid': expected_bssid
    })

@app.route('/student/get_attendance', methods=['GET'])
@authenticate_student
def get_attendance():
    student_id = request.args.get('student_id')
    
    # Filter attendance records for this student
    student_attendance = {}
    for date, sessions in db['attendance'].items():
        for session_id, session in sessions.items():
            if session['student_id'] == student_id:
                if date not in student_attendance:
                    student_attendance[date] = {}
                
                # Format the session data
                start_time = datetime.fromisoformat(session['timestamp'])
                end_time = start_time + timedelta(hours=1)  # Assuming 1 hour sessions
                
                student_attendance[date][session_id] = {
                    'subject': 'Class Session',  # Would normally come from timetable
                    'status': session['status'],
                    'start_time': start_time.strftime('%H:%M'),
                    'end_time': end_time.strftime('%H:%M')
                }
    
    return jsonify({
        'attendance': student_attendance
    })

@app.route('/student/get_timetable', methods=['GET'])
@authenticate_student
def get_timetable():
    student_id = request.args.get('student_id')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    if branch not in db['timetable'] or semester not in db['timetable'][branch]:
        return jsonify({'error': 'Timetable not found for this branch/semester'}), 404
    
    return jsonify({
        'timetable': db['timetable'][branch][semester]
    })

@app.route('/student/ping', methods=['POST'])
@authenticate_student
def student_ping():
    data = request.get_json()
    student_id = data['student_id']
    
    if student_id in db['active_sessions']:
        db['active_sessions'][student_id]['last_ping'] = time.time()
        return jsonify({'message': 'Ping received'})
    
    return jsonify({'error': 'No active session found'}), 401

@app.route('/student/cleanup_dead_sessions', methods=['POST'])
def cleanup_dead_sessions():
    data = request.get_json()
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if student_id in db['active_sessions']:
        if db['active_sessions'][student_id]['device_id'] == device_id:
            del db['active_sessions'][student_id]
            return jsonify({'message': 'Session cleaned up'})
    
    return jsonify({'message': 'No matching session found'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
