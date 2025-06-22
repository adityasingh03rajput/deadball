from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import threading
import time
import random
import json
import os
import uuid

app = Flask(__name__)
CORS(app)

class AttendanceServer:
    def __init__(self):
        self.teachers = {}
        self.students = {}
        self.sessions = {}
        self.student_checkins = {}
        self.student_timers = {}
        self.manual_overrides = {}
        self.active_devices = {}
        self.authorized_bssid = None
        self.holidays = []
        self.special_schedules = []
        self.timetables = {}
        self.lock = threading.Lock()
        
        # Configuration
        self.CHECKIN_INTERVAL = 5  # seconds
        self.TIMER_DURATION = 300  # 5 minutes in seconds
        self.SERVER_PORT = 5000
        
        # Load initial data
        self.load_initial_data()
        
        # Start background threads
        self.start_background_threads()
    
    def load_initial_data(self):
        """Load initial data from files if they exist"""
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # Load teachers
        if os.path.exists('data/teachers.json'):
            try:
                with open('data/teachers.json', 'r') as f:
                    self.teachers = json.load(f)
            except:
                self.teachers = {}
        
        # Load students
        if os.path.exists('data/students.json'):
            try:
                with open('data/students.json', 'r') as f:
                    self.students = json.load(f)
            except:
                self.students = {}
        
        # Load holidays and special dates
        if os.path.exists('data/special_dates.json'):
            try:
                with open('data/special_dates.json', 'r') as f:
                    special_data = json.load(f)
                    self.holidays = special_data.get('holidays', [])
                    self.special_schedules = special_data.get('special_schedules', [])
            except:
                self.holidays = []
                self.special_schedules = []
        
        # Load timetables
        if os.path.exists('data/timetables.json'):
            try:
                with open('data/timetables.json', 'r') as f:
                    self.timetables = json.load(f)
            except:
                self.timetables = {}
    
    def save_data(self):
        """Save all data to files"""
        with open('data/teachers.json', 'w') as f:
            json.dump(self.teachers, f)
        
        with open('data/students.json', 'w') as f:
            json.dump(self.students, f)
        
        with open('data/special_dates.json', 'w') as f:
            json.dump({
                'holidays': self.holidays,
                'special_schedules': self.special_schedules
            }, f)
        
        with open('data/timetables.json', 'w') as f:
            json.dump(self.timetables, f)
    
    def start_background_threads(self):
        """Start all background maintenance threads"""
        timer_thread = threading.Thread(target=self.update_timers, daemon=True)
        timer_thread.start()
        
        cleanup_thread = threading.Thread(target=self.cleanup_checkins, daemon=True)
        cleanup_thread.start()
        
        device_cleanup_thread = threading.Thread(target=self.cleanup_active_devices, daemon=True)
        device_cleanup_thread.start()
        
        save_thread = threading.Thread(target=self.periodic_save, daemon=True)
        save_thread.start()
    
    def periodic_save(self):
        """Periodically save data to disk"""
        while True:
            time.sleep(300)  # Save every 5 minutes
            with self.lock:
                self.save_data()
    
    def update_timers(self):
        """Background thread to update all student timers"""
        while True:
            current_time = datetime.now().timestamp()
            
            with self.lock:
                for student_id, timer in list(self.student_timers.items()):
                    if timer['status'] == 'running':
                        elapsed = current_time - timer['start_time']
                        remaining = max(0, timer['duration'] - elapsed)
                        
                        if remaining <= 0:
                            timer['status'] = 'completed'
                            self.record_attendance(student_id)
                        
                        self.student_timers[student_id]['remaining'] = remaining
            
            time.sleep(1)
    
    def record_attendance(self, student_id):
        """Record attendance for completed timer"""
        with self.lock:
            if student_id not in self.students or student_id not in self.student_timers:
                return
            
            timer = self.student_timers[student_id]
            if timer['status'] != 'completed':
                return
            
            # Check authorization
            checkin = self.student_checkins.get(student_id, {})
            is_authorized = checkin.get('bssid') == self.authorized_bssid
            
            date_str = datetime.fromtimestamp(timer['start_time']).date().isoformat()
            session_key = f"timer_{int(timer['start_time'])}"
            
            if date_str not in self.students[student_id]['attendance']:
                self.students[student_id]['attendance'][date_str] = {}
            
            self.students[student_id]['attendance'][date_str][session_key] = {
                'status': 'present' if is_authorized else 'absent',
                'subject': 'Timer Session',
                'classroom': self.students[student_id]['classroom'],
                'start_time': datetime.fromtimestamp(timer['start_time']).isoformat(),
                'end_time': datetime.fromtimestamp(timer['start_time'] + timedelta(seconds=self.TIMER_DURATION)).isoformat(),
                'branch': self.students[student_id]['branch'],
                'semester': self.students[student_id]['semester']
            }
    
    def cleanup_checkins(self):
        """Background thread to clean up old checkins"""
        while True:
            current_time = datetime.now()
            threshold = current_time - timedelta(minutes=10)
            
            with self.lock:
                for student_id in list(self.student_checkins.keys()):
                    last_checkin = self.student_checkins[student_id].get('timestamp')
                    if last_checkin and datetime.fromisoformat(last_checkin) < threshold:
                        del self.student_checkins[student_id]
            
            time.sleep(60)
    
    def cleanup_active_devices(self):
        """Background thread to clean up inactive devices"""
        while True:
            current_time = datetime.now()
            threshold = current_time - timedelta(minutes=5)
            
            with self.lock:
                for student_id in list(self.active_devices.keys()):
                    last_activity = self.active_devices[student_id].get('last_activity')
                    if last_activity and datetime.fromisoformat(last_activity) < threshold:
                        del self.active_devices[student_id]
            
            time.sleep(60)
    
    def start_timer(self, student_id):
        """Start timer for a student"""
        with self.lock:
            if student_id not in self.students:
                return False
            
            self.student_timers[student_id] = {
                'status': 'running',
                'start_time': datetime.now().timestamp(),
                'duration': self.TIMER_DURATION,
                'remaining': self.TIMER_DURATION
            }
            
            return True

# Initialize the server
server = AttendanceServer()

# Teacher endpoints
@app.route('/teacher/signup', methods=['POST'])
def teacher_signup():
    data = request.json
    teacher_id = data.get('id')
    password = data.get('password')
    email = data.get('email')
    name = data.get('name')
    
    if not all([teacher_id, password, email, name]):
        return jsonify({'error': 'All fields are required'}), 400
    
    with server.lock:
        if teacher_id in server.teachers:
            return jsonify({'error': 'Teacher ID already exists'}), 400
        
        if any(t['email'] == email for t in server.teachers.values()):
            return jsonify({'error': 'Email already registered'}), 400
        
        server.teachers[teacher_id] = {
            'id': teacher_id,
            'password': password,  # No hashing for simplicity
            'email': email,
            'name': name,
            'classrooms': [],
            'bssid_mapping': {},
            'branches': ["CSE", "ECE", "EEE", "ME", "CE"],
            'semesters': list(range(1, 9))
        }
        
        return jsonify({'message': 'Registration successful'}), 201

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    data = request.json
    teacher_id = data.get('id')
    password = data.get('password')
    
    if not all([teacher_id, password]):
        return jsonify({'error': 'ID and password are required'}), 400
    
    teacher = server.teachers.get(teacher_id)
    if not teacher:
        return jsonify({'error': 'Teacher not found'}), 404
    
    if teacher['password'] != password:
        return jsonify({'error': 'Incorrect password'}), 401
    
    return jsonify({
        'message': 'Login successful',
        'teacher': teacher
    }), 200

@app.route('/teacher/register_student', methods=['POST'])
def register_student():
    data = request.json
    student_id = data.get('id')
    password = data.get('password')
    name = data.get('name')
    classroom = data.get('classroom')
    branch = data.get('branch')
    semester = data.get('semester')
    
    if not all([student_id, password, name, classroom, branch, semester]):
        return jsonify({'error': 'All fields are required'}), 400
    
    with server.lock:
        if student_id in server.students:
            return jsonify({'error': 'Student ID already exists'}), 400
        
        server.students[student_id] = {
            'id': student_id,
            'password': password,  # No hashing for simplicity
            'name': name,
            'classroom': classroom,
            'branch': branch,
            'semester': semester,
            'attendance': {}
        }
        
        return jsonify({'message': 'Student registered successfully'}), 201

@app.route('/teacher/get_students', methods=['GET'])
def get_students():
    classroom = request.args.get('classroom')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    filtered = list(server.students.values())
    
    if classroom:
        filtered = [s for s in filtered if s['classroom'] == classroom]
    if branch:
        filtered = [s for s in filtered if s['branch'] == branch]
    if semester:
        filtered = [s for s in filtered if str(s['semester']) == str(semester)]
    
    return jsonify({'students': filtered}), 200

@app.route('/teacher/update_student', methods=['POST'])
def update_student():
    data = request.json
    student_id = data.get('id')
    new_data = data.get('new_data')
    
    if not student_id or not new_data:
        return jsonify({'error': 'Student ID and new data are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        for key, value in new_data.items():
            if key in server.students[student_id] and key != 'id':
                server.students[student_id][key] = value
        
        return jsonify({'message': 'Student updated successfully'}), 200

@app.route('/teacher/delete_student', methods=['POST'])
def delete_student():
    data = request.json
    student_id = data.get('id')
    
    if not student_id:
        return jsonify({'error': 'Student ID is required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        del server.students[student_id]
        
        # Clean up related data
        if student_id in server.student_checkins:
            del server.student_checkins[student_id]
        if student_id in server.student_timers:
            del server.student_timers[student_id]
        if student_id in server.active_devices:
            del server.active_devices[student_id]
        
        return jsonify({'message': 'Student deleted successfully'}), 200

@app.route('/teacher/update_profile', methods=['POST'])
def update_teacher_profile():
    data = request.json
    teacher_id = data.get('id')
    new_data = data.get('new_data')
    
    if not teacher_id or not new_data:
        return jsonify({'error': 'Teacher ID and new data are required'}), 400
    
    with server.lock:
        if teacher_id not in server.teachers:
            return jsonify({'error': 'Teacher not found'}), 404
        
        for key, value in new_data.items():
            if key in server.teachers[teacher_id] and key != 'id':
                server.teachers[teacher_id][key] = value
        
        return jsonify({'message': 'Profile updated successfully'}), 200

@app.route('/teacher/change_password', methods=['POST'])
def change_teacher_password():
    data = request.json
    teacher_id = data.get('id')
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not all([teacher_id, old_password, new_password]):
        return jsonify({'error': 'All fields are required'}), 400
    
    with server.lock:
        if teacher_id not in server.teachers:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if server.teachers[teacher_id]['password'] != old_password:
            return jsonify({'error': 'Incorrect current password'}), 401
        
        server.teachers[teacher_id]['password'] = new_password
        return jsonify({'message': 'Password changed successfully'}), 200

@app.route('/teacher/update_bssid', methods=['POST'])
def update_bssid_mapping():
    data = request.json
    teacher_id = data.get('teacher_id')
    classroom = data.get('classroom')
    bssid = data.get('bssid')
    
    if not all([teacher_id, classroom]):
        return jsonify({'error': 'Teacher ID and classroom are required'}), 400
    
    with server.lock:
        if teacher_id not in server.teachers:
            return jsonify({'error': 'Teacher not found'}), 404
        
        server.teachers[teacher_id]['bssid_mapping'][classroom] = bssid
        
        if classroom not in server.teachers[teacher_id]['classrooms']:
            server.teachers[teacher_id]['classrooms'].append(classroom)
        
        return jsonify({'message': 'BSSID mapping updated successfully'}), 200

@app.route('/teacher/start_session', methods=['POST'])
def start_session():
    data = request.json
    teacher_id = data.get('teacher_id')
    classroom = data.get('classroom')
    subject = data.get('subject')
    branch = data.get('branch')
    semester = data.get('semester')
    
    if not all([teacher_id, classroom, subject]):
        return jsonify({'error': 'Teacher ID, classroom and subject are required'}), 400
    
    with server.lock:
        if teacher_id not in server.teachers:
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Check for existing active session
        for session in server.sessions.values():
            if session['classroom'] == classroom and not session.get('end_time'):
                return jsonify({'error': 'There is already an active session for this classroom'}), 400
        
        session_id = f"session_{len(server.sessions) + 1}"
        server.sessions[session_id] = {
            'id': session_id,
            'teacher_id': teacher_id,
            'classroom': classroom,
            'subject': subject,
            'branch': branch,
            'semester': semester,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'ad_hoc': data.get('ad_hoc', False)
        }
        
        return jsonify({
            'message': 'Session started successfully',
            'session_id': session_id
        }), 201

@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    with server.lock:
        if session_id not in server.sessions or server.sessions[session_id].get('end_time'):
            return jsonify({'error': 'Session not found or already ended'}), 404
        
        server.sessions[session_id]['end_time'] = datetime.now().isoformat()
        
        # Record attendance for checked-in students
        classroom = server.sessions[session_id]['classroom']
        session_start = datetime.fromisoformat(server.sessions[session_id]['start_time'])
        session_end = datetime.now()
        
        for student_id, checkin in server.student_checkins.items():
            if server.students.get(student_id, {}).get('classroom') == classroom:
                checkin_time = datetime.fromisoformat(checkin['timestamp'])
                
                if session_start <= checkin_time <= session_end:
                    date_str = session_start.date().isoformat()
                    session_key = f"{server.sessions[session_id]['subject']}_{session_id}"
                    
                    if date_str not in server.students[student_id]['attendance']:
                        server.students[student_id]['attendance'][date_str] = {}
                    
                    server.students[student_id]['attendance'][date_str][session_key] = {
                        'status': 'present' if checkin.get('bssid') == server.authorized_bssid else 'absent',
                        'subject': server.sessions[session_id]['subject'],
                        'classroom': classroom,
                        'start_time': server.sessions[session_id]['start_time'],
                        'end_time': server.sessions[session_id]['end_time'],
                        'branch': server.sessions[session_id].get('branch'),
                        'semester': server.sessions[session_id].get('semester')
                    }
        
        return jsonify({'message': 'Session ended successfully'}), 200

@app.route('/teacher/get_sessions', methods=['GET'])
def get_sessions():
    teacher_id = request.args.get('teacher_id')
    classroom = request.args.get('classroom')
    
    filtered = list(server.sessions.values())
    
    if teacher_id:
        filtered = [s for s in filtered if s['teacher_id'] == teacher_id]
    if classroom:
        filtered = [s for s in filtered if s['classroom'] == classroom]
    
    return jsonify({'sessions': filtered}), 200

@app.route('/teacher/get_active_sessions', methods=['GET'])
def get_active_sessions():
    teacher_id = request.args.get('teacher_id')
    
    active_sessions = []
    with server.lock:
        for session in server.sessions.values():
            if not session.get('end_time'):
                if not teacher_id or session['teacher_id'] == teacher_id:
                    active_sessions.append(session)
    
    return jsonify({'sessions': active_sessions}), 200

@app.route('/teacher/set_bssid', methods=['POST'])
def set_bssid():
    data = request.json
    bssid = data.get('bssid')
    
    if not bssid:
        return jsonify({'error': 'BSSID is required'}), 400
    
    server.authorized_bssid = bssid
    
    return jsonify({'message': 'Authorized BSSID set successfully'}), 200

@app.route('/teacher/get_status', methods=['GET'])
def get_status():
    classroom = request.args.get('classroom')
    
    status = {
        'authorized_bssid': server.authorized_bssid,
        'students': {}
    }
    
    with server.lock:
        for student_id, student in server.students.items():
            if classroom and student['classroom'] != classroom:
                continue
            
            checkin = server.student_checkins.get(student_id, {})
            timer = server.student_timers.get(student_id, {})
            
            status['students'][student_id] = {
                'name': student['name'],
                'classroom': student['classroom'],
                'branch': student['branch'],
                'semester': student['semester'],
                'connected': student_id in server.student_checkins,
                'authorized': checkin.get('bssid') == server.authorized_bssid,
                'timestamp': checkin.get('timestamp'),
                'timer': {
                    'status': timer.get('status', 'stop'),
                    'remaining': timer.get('remaining', 0),
                    'start_time': timer.get('start_time')
                }
            }
    
    return jsonify(status), 200

@app.route('/teacher/manual_override', methods=['POST'])
def manual_override():
    data = request.json
    student_id = data.get('student_id')
    status = data.get('status')
    
    if not all([student_id, status]):
        return jsonify({'error': 'Student ID and status are required'}), 400
    
    if status not in ['present', 'absent']:
        return jsonify({'error': 'Status must be "present" or "absent"'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        server.manual_overrides[student_id] = status
        
        if status == 'present':
            server.start_timer(student_id)
        
        return jsonify({'message': f'Student {student_id} marked as {status}'}), 200

@app.route('/teacher/random_ring', methods=['POST'])
def random_ring():
    classroom = request.args.get('classroom')
    
    if not classroom:
        return jsonify({'error': 'Classroom is required'}), 400
    
    with server.lock:
        # Get all students in the classroom with attendance data
        classroom_students = []
        for student_id, student in server.students.items():
            if student['classroom'] == classroom:
                attendance_records = []
                for date, sessions in student.get('attendance', {}).items():
                    for session in sessions.values():
                        attendance_records.append(session['status'])
                
                total = len(attendance_records)
                present = sum(1 for s in attendance_records if s == 'present')
                percentage = round((present / total) * 100) if total > 0 else 0
                
                classroom_students.append({
                    'id': student_id,
                    'name': student['name'],
                    'attendance_percentage': percentage
                })
        
        if len(classroom_students) < 2:
            return jsonify({'error': 'Need at least 2 students for random ring'}), 400
        
        # Sort students by attendance
        sorted_students = sorted(classroom_students, key=lambda x: x['attendance_percentage'])
        
        # Select one from top 30% and one from bottom 30%
        split_point = max(1, len(sorted_students) // 3)
        low_attendance = sorted_students[:split_point]
        high_attendance = sorted_students[-split_point:]
        
        selected_low = random.choice(low_attendance)
        selected_high = random.choice(high_attendance)
        
        return jsonify({
            'message': 'Random ring selection complete',
            'low_attendance_student': selected_low,
            'high_attendance_student': selected_high
        }), 200

@app.route('/teacher/get_special_dates', methods=['GET'])
def get_special_dates():
    return jsonify({
        'holidays': server.holidays,
        'special_schedules': server.special_schedules
    }), 200

@app.route('/teacher/update_special_dates', methods=['POST'])
def update_special_dates():
    data = request.json
    holidays = data.get('holidays', [])
    special_schedules = data.get('special_schedules', [])
    
    with server.lock:
        server.holidays = holidays
        server.special_schedules = special_schedules
    
    return jsonify({'message': 'Special dates updated successfully'}), 200

@app.route('/teacher/get_timetable', methods=['GET'])
def get_timetable():
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    timetable_key = f"{branch}_{semester}" if branch and semester else "default"
    
    with server.lock:
        timetable = server.timetables.get(timetable_key, {})
    
    return jsonify({'timetable': timetable}), 200

@app.route('/teacher/update_timetable', methods=['POST'])
def update_timetable():
    data = request.json
    branch = data.get('branch')
    semester = data.get('semester')
    timetable = data.get('timetable', {})
    
    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400
    
    timetable_key = f"{branch}_{semester}"
    
    with server.lock:
        server.timetables[timetable_key] = timetable
    
    return jsonify({'message': 'Timetable updated successfully'}), 200

# Student endpoints
@app.route('/student/login', methods=['POST'])
def student_login():
    data = request.json
    student_id = data.get('id')
    password = data.get('password')
    device_id = data.get('device_id')
    
    if not all([student_id, password, device_id]):
        return jsonify({'error': 'ID, password and device ID are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        if server.students[student_id]['password'] != password:
            return jsonify({'error': 'Incorrect password'}), 401
        
        if student_id in server.active_devices and server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'This account is already logged in on another device'}), 403
        
        server.active_devices[student_id] = {
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        }
        
        classroom_bssid = None
        for teacher in server.teachers.values():
            if server.students[student_id]['classroom'] in teacher['bssid_mapping']:
                classroom_bssid = teacher['bssid_mapping'][server.students[student_id]['classroom']]
                break
        
        return jsonify({
            'message': 'Login successful',
            'student': {
                'id': server.students[student_id]['id'],
                'name': server.students[student_id]['name'],
                'classroom': server.students[student_id]['classroom'],
                'branch': server.students[student_id]['branch'],
                'semester': server.students[student_id]['semester']
            },
            'classroom_bssid': classroom_bssid
        }), 200

@app.route('/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    student_id = data.get('student_id')
    bssid = data.get('bssid')
    device_id = data.get('device_id')

    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400

    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404

        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403

        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()

        server.student_checkins[student_id] = {
            'timestamp': datetime.now().isoformat(),
            'bssid': bssid if bssid else None,
            'device_id': device_id
        }

        # BSSID Verification (per-classroom)
        student = server.students.get(student_id)
        classroom = student.get('classroom')
        authorized_bssid = None
        for teacher in server.teachers.values():
            if classroom in teacher['bssid_mapping']:
                authorized_bssid = teacher['bssid_mapping'][classroom]
                break

        if bssid and bssid == authorized_bssid:
            server.start_timer(student_id)

        return jsonify({
            'message': 'Check-in successful',
            'status': 'present' if bssid and bssid == authorized_bssid else 'absent'
        }), 200

@app.route('/student/timer/start', methods=['POST'])
def student_start_timer():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')

    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400

    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404

        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403

        checkin = server.student_checkins.get(student_id, {})

        # BSSID Verification (per-classroom)
        classroom = server.students[student_id]['classroom']
        authorized_bssid = None
        for teacher in server.teachers.values():
            if classroom in teacher['bssid_mapping']:
                authorized_bssid = teacher['bssid_mapping'][classroom]
                break

        if checkin.get('bssid') != authorized_bssid:
            return jsonify({'error': 'Not authorized to start timer - BSSID mismatch'}), 403

        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()

        server.start_timer(student_id)

        return jsonify({
            'message': 'Timer started successfully',
            'status': 'running'
        }), 200

@app.route('/student/timer/stop', methods=['POST'])
def student_stop_timer():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        if student_id not in server.student_timers or server.student_timers[student_id]['status'] == 'stop':
            return jsonify({'error': 'No active timer to stop'}), 400
        
        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        if server.student_timers[student_id]['status'] == 'running':
            server.record_attendance(student_id)
        
        server.student_timers[student_id]['status'] = 'stop'
        server.student_timers[student_id]['remaining'] = 0
        
        return jsonify({
            'message': 'Timer stopped successfully',
            'status': 'stop'
        }), 200

@app.route('/student/get_status', methods=['GET'])
def student_get_status():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        checkin = server.student_checkins.get(student_id, {})
        timer = server.student_timers.get(student_id, {})
        
        status = {
            'student_id': student_id,
            'name': server.students[student_id]['name'],
            'classroom': server.students[student_id]['classroom'],
            'connected': student_id in server.student_checkins,
            'authorized': checkin.get('bssid') == server.authorized_bssid,
            'timestamp': checkin.get('timestamp'),
            'timer': {
                'status': timer.get('status', 'stop'),
                'remaining': timer.get('remaining', 0),
                'start_time': timer.get('start_time')
            }
        }
        
        return jsonify(status), 200

@app.route('/student/get_attendance', methods=['GET'])
def student_get_attendance():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        return jsonify({
            'attendance': server.students[student_id].get('attendance', {})
        }), 200

@app.route('/student/get_active_session', methods=['GET'])
def get_active_session():
    student_id = request.args.get('student_id')
    classroom = request.args.get('classroom')
    
    if not student_id or not classroom:
        return jsonify({'error': 'Student ID and classroom are required'}), 400
    
    with server.lock:
        # Check if student exists
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check for active session in the student's classroom
        active_session = None
        for session in server.sessions.values():
            if session['classroom'] == classroom and not session.get('end_time'):
                active_session = session
                break
        
        if active_session:
            return jsonify({
                'active': True,
                'session': active_session
            }), 200
        else:
            return jsonify({'active': False}), 200

@app.route('/student/get_timetable', methods=['GET'])
def student_get_timetable():
    student_id = request.args.get('student_id')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    if not student_id or not branch or not semester:
        return jsonify({'error': 'Student ID, branch and semester are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        timetable_key = f"{branch}_{semester}"
        timetable = server.timetables.get(timetable_key, {})
        
        return jsonify({
            'timetable': timetable
        }), 200

@app.route('/student/get_special_dates', methods=['GET'])
def student_get_special_dates():
    return jsonify({
        'holidays': server.holidays,
        'special_schedules': server.special_schedules
    }), 200

@app.route('/student/ping', methods=['POST'])
def student_ping():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if student_id not in server.students:
            return jsonify({'error': 'Student not found'}), 404
        
        if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        return jsonify({'message': 'Ping successful'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=server.SERVER_PORT, debug=True)
