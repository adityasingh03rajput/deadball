from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import threading
import time
import random
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import atexit
import json
from functools import wraps
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AttendanceServer')
handler = RotatingFileHandler('attendance.log', maxBytes=1000000, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Configuration
CHECKIN_TIMEOUT = 5  # seconds
MAX_CHECKIN_RATE = 60  # max checkins per minute per student

class JSONDatabase:
    def __init__(self):
        self.data = {
            'teachers': {},
            'students': {},
            'sessions': {},
            'checkins': [],
            'timers': {},
            'active_devices': {},
            'manual_overrides': {},
            'timetables': defaultdict(dict),
            'special_dates': {'holidays': [], 'special_schedules': []},
            'server_settings': {
                'authorized_bssid': None,
                'checkin_interval': 5,
                'timer_duration': 300,
                'max_checkin_rate': MAX_CHECKIN_RATE
            },
            'bssid_mappings': {}  # Separate storage for classroom to BSSID mappings
        }
        self.lock = threading.Lock()
        self._initialize_data()

    def _initialize_data(self):
        # Create admin account if not exists
        if 'admin' not in self.data['teachers']:
            self.data['teachers']['admin'] = {
                'id': 'admin',
                'password': generate_password_hash('admin'),
                'email': 'admin@school.com',
                'name': 'Admin',
                'classrooms': ["A101", "A102", "B201", "B202"],
                'bssid_mapping': {"A101": "00:11:22:33:44:55", "A102": "AA:BB:CC:DD:EE:FF"},
                'branches': ["CSE", "ECE", "EEE", "ME", "CE"],
                'semesters': list(range(1, 9))
            }

        # Create sample students if none exist
        if not self.data['students']:
            self.data['students']['s001'] = {
                'id': 's001',
                'password': generate_password_hash('student123'),
                'name': 'John Doe',
                'classroom': 'A101',
                'branch': 'CSE',
                'semester': 3,
                'attendance': {},
                'locked_device_id': None,
                'last_checkin': None
            }
            self.data['students']['s002'] = {
                'id': 's002',
                'password': generate_password_hash('student123'),
                'name': 'Jane Smith',
                'classroom': 'A101',
                'branch': 'CSE',
                'semester': 3,
                'attendance': {},
                'locked_device_id': None,
                'last_checkin': None
            }

            # Create sample timetable
            self.data['timetables']['CSE'][3] = [
                ["Monday", "09:00", "10:00", "Mathematics", "A101"],
                ["Monday", "10:00", "11:00", "Physics", "A101"]
            ]

    def get_teacher(self, teacher_id):
        with self.lock:
            return self.data['teachers'].get(teacher_id)

    def get_student(self, student_id):
        with self.lock:
            return self.data['students'].get(student_id)

    def get_session(self, session_id):
        with self.lock:
            return self.data['sessions'].get(session_id)

    def get_active_session_for_classroom(self, classroom):
        with self.lock:
            for session in self.data['sessions'].values():
                if session['classroom'] == classroom and not session.get('end_time'):
                    return session
            return None

    def get_last_checkin(self, student_id, device_id=None):
        with self.lock:
            checkins = [c for c in self.data['checkins'] if c['student_id'] == student_id]
            if device_id:
                checkins = [c for c in checkins if c['device_id'] == device_id]
            return max(checkins, key=lambda x: x['timestamp']) if checkins else None

    def get_timer(self, student_id):
        with self.lock:
            return self.data['timers'].get(student_id)

    def get_active_device(self, student_id):
        with self.lock:
            return self.data['active_devices'].get(student_id)

    def get_manual_override(self, student_id):
        with self.lock:
            return self.data['manual_overrides'].get(student_id)

    def get_timetable(self, branch, semester):
        with self.lock:
            return self.data['timetables'].get(branch, {}).get(semester, [])

    def get_special_dates(self):
        with self.lock:
            return self.data['special_dates']

    def get_server_settings(self):
        with self.lock:
            return self.data['server_settings']

    def get_expected_bssid(self, classroom):
        with self.lock:
            # Check all teachers' mappings for this classroom
            for teacher in self.data['teachers'].values():
                if 'bssid_mapping' in teacher and classroom in teacher['bssid_mapping']:
                    return teacher['bssid_mapping'][classroom]
            return None

    def get_bssid_mappings(self, teacher_id):
        with self.lock:
            teacher = self.data['teachers'].get(teacher_id)
            if teacher:
                return teacher.get('bssid_mapping', {})
            return {}

    def add_teacher(self, teacher_data):
        with self.lock:
            self.data['teachers'][teacher_data['id']] = teacher_data

    def add_student(self, student_data):
        with self.lock:
            self.data['students'][student_data['id']] = student_data

    def add_session(self, session_data):
        with self.lock:
            self.data['sessions'][session_data['id']] = session_data

    def add_checkin(self, checkin_data):
        with self.lock:
            self.data['checkins'].append(checkin_data)

    def add_timer(self, timer_data):
        with self.lock:
            self.data['timers'][timer_data['student_id']] = timer_data

    def add_active_device(self, device_data):
        with self.lock:
            self.data['active_devices'][device_data['student_id']] = device_data

    def add_manual_override(self, override_data):
        with self.lock:
            self.data['manual_overrides'][override_data['student_id']] = override_data

    def update_teacher(self, teacher_id, updates):
        with self.lock:
            if teacher_id in self.data['teachers']:
                self.data['teachers'][teacher_id].update(updates)

    def update_student(self, student_id, updates):
        with self.lock:
            if student_id in self.data['students']:
                self.data['students'][student_id].update(updates)

    def update_session(self, session_id, updates):
        with self.lock:
            if session_id in self.data['sessions']:
                self.data['sessions'][session_id].update(updates)

    def update_timer(self, student_id, updates):
        with self.lock:
            if student_id in self.data['timers']:
                self.data['timers'][student_id].update(updates)

    def update_server_settings(self, updates):
        with self.lock:
            self.data['server_settings'].update(updates)

    def update_special_dates(self, holidays, special_schedules):
        with self.lock:
            self.data['special_dates'] = {
                'holidays': holidays,
                'special_schedules': special_schedules
            }

    def update_timetable(self, branch, semester, timetable):
        with self.lock:
            self.data['timetables'][branch][semester] = timetable

    def set_bssid_mapping(self, teacher_id, classroom, bssid):
        with self.lock:
            if teacher_id in self.data['teachers']:
                teacher = self.data['teachers'][teacher_id]
                if 'bssid_mapping' not in teacher:
                    teacher['bssid_mapping'] = {}
                teacher['bssid_mapping'][classroom] = bssid

    def delete_student(self, student_id):
        with self.lock:
            self.data['students'].pop(student_id, None)
            self.data['active_devices'].pop(student_id, None)
            self.data['timers'].pop(student_id, None)
            self.data['manual_overrides'].pop(student_id, None)
            self.data['checkins'] = [c for c in self.data['checkins'] if c['student_id'] != student_id]

    def get_students_by_classroom(self, classroom):
        with self.lock:
            return [s for s in self.data['students'].values() if s['classroom'] == classroom]

    def get_students_by_branch_semester(self, branch, semester):
        with self.lock:
            return [s for s in self.data['students'].values() 
                   if s['branch'] == branch and s['semester'] == semester]

    def get_sessions_by_teacher(self, teacher_id):
        with self.lock:
            return [s for s in self.data['sessions'].values() if s['teacher_id'] == teacher_id]

    def get_active_sessions(self, teacher_id=None):
        with self.lock:
            sessions = [s for s in self.data['sessions'].values() if not s.get('end_time')]
            if teacher_id:
                sessions = [s for s in sessions if s['teacher_id'] == teacher_id]
            return sessions

    def get_checkins_for_classroom(self, classroom, start_time, end_time):
        with self.lock:
            student_ids = [s['id'] for s in self.data['students'].values() if s['classroom'] == classroom]
            return [c for c in self.data['checkins'] 
                   if c['student_id'] in student_ids and start_time <= c['timestamp'] <= end_time]

    def cleanup_old_checkins(self, threshold):
        with self.lock:
            self.data['checkins'] = [c for c in self.data['checkins'] if c['timestamp'] >= threshold]

    def cleanup_inactive_devices(self, threshold):
        with self.lock:
            inactive = [d['student_id'] for d in self.data['active_devices'].values() 
                       if d['last_activity'] < threshold]
            
            for student_id in inactive:
                self.data['active_devices'].pop(student_id, None)
                if student_id in self.data['students']:
                    self.data['students'][student_id]['locked_device_id'] = None
                self.data['timers'].pop(student_id, None)
                self.data['checkins'] = [c for c in self.data['checkins'] if c['student_id'] != student_id]

def rate_limited(max_per_minute):
    def decorator(f):
        times = {}
        
        @wraps(f)
        def wrapper(*args, **kwargs):
            student_id = request.json.get('student_id')
            now = time.time()
            
            if student_id in times:
                last_time, count = times[student_id]
                if now - last_time < 60:
                    if count >= max_per_minute:
                        return jsonify({
                            'error': 'Rate limit exceeded',
                            'retry_after': 60 - (now - last_time)
                        }), 429
                    times[student_id] = (last_time, count + 1)
                else:
                    times[student_id] = (now, 1)
            else:
                times[student_id] = (now, 1)
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

class AttendanceServer:
    def __init__(self):
        self.db = JSONDatabase()
        self.running = True
        
        # Start background threads
        self.start_background_threads()
    
    def start_background_threads(self):
        """Start all background maintenance threads"""
        timer_thread = threading.Thread(target=self.update_timers, daemon=True)
        timer_thread.start()
        
        cleanup_thread = threading.Thread(target=self.cleanup_checkins, daemon=True)
        cleanup_thread.start()
        
        device_cleanup_thread = threading.Thread(target=self.cleanup_active_devices, daemon=True)
        device_cleanup_thread.start()
        
        logger.info("Background threads started")
    
    def update_timers(self):
        """Background thread to update all student timers"""
        while self.running:
            current_time = datetime.now().timestamp()
            
            try:
                timers = [t for t in self.db.data['timers'].values() if t['status'] == 'running']
                completions = []
                
                for timer in timers:
                    elapsed = current_time - timer['start_time']
                    remaining = max(0, timer['duration'] - elapsed)
                    
                    if remaining <= 0:
                        completions.append(timer['student_id'])
                    else:
                        self.db.update_timer(timer['student_id'], {'remaining': remaining})
                
                # Process completions
                for student_id in completions:
                    self.db.update_timer(student_id, {
                        'status': 'completed',
                        'remaining': 0
                    })
                    self.record_attendance(student_id)
                
            except Exception as e:
                logger.error(f"Error in timer update thread: {e}")
            
            time.sleep(1)
    
    def record_attendance(self, student_id):
        """Record attendance for completed timer"""
        try:
            student = self.db.get_student(student_id)
            if not student:
                return
            
            timer = self.db.get_timer(student_id)
            if not timer or timer['status'] != 'completed':
                return
            
            # Check authorization
            checkin = self.db.get_last_checkin(student_id)
            
            authorized_bssid = self.db.get_server_settings()['authorized_bssid']
            is_authorized = checkin and checkin['bssid'] == authorized_bssid
            
            date_str = datetime.fromtimestamp(timer['start_time']).date().isoformat()
            session_key = f"timer_{int(timer['start_time'])}"
            
            attendance = student.get('attendance', {})
            if date_str not in attendance:
                attendance[date_str] = {}
            
            attendance[date_str][session_key] = {
                'status': 'present' if is_authorized else 'absent',
                'subject': 'Timer Session',
                'classroom': student['classroom'],
                'start_time': datetime.fromtimestamp(timer['start_time']).isoformat(),
                'end_time': datetime.fromtimestamp(timer['start_time'] + 
                    self.db.get_server_settings()['timer_duration']).isoformat(),
                'branch': student['branch'],
                'semester': student['semester']
            }
            
            self.db.update_student(student_id, {'attendance': attendance})
        except Exception as e:
            logger.error(f"Error recording attendance: {e}")
    
    def cleanup_checkins(self):
        """Background thread to clean up old checkins"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=10)).isoformat()
            
            try:
                self.db.cleanup_old_checkins(threshold)
            except Exception as e:
                logger.error(f"Error cleaning up checkins: {e}")
            
            time.sleep(60)
    
    def cleanup_active_devices(self):
        """Background thread to clean up inactive devices"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            try:
                self.db.cleanup_inactive_devices(threshold)
            except Exception as e:
                logger.error(f"Error cleaning up devices: {e}")
            
            time.sleep(60)
    
    def start_timer(self, student_id):
        """Start timer for a student"""
        try:
            if not self.db.get_student(student_id):
                return False
            
            existing_timer = self.db.get_timer(student_id)
            settings = self.db.get_server_settings()
            
            if existing_timer:
                self.db.update_timer(student_id, {
                    'status': 'running',
                    'start_time': datetime.now().timestamp(),
                    'duration': settings['timer_duration'],
                    'remaining': settings['timer_duration']
                })
            else:
                self.db.add_timer({
                    'student_id': student_id,
                    'status': 'running',
                    'start_time': datetime.now().timestamp(),
                    'duration': settings['timer_duration'],
                    'remaining': settings['timer_duration']
                })
            
            return True
        except Exception as e:
            logger.error(f"Error starting timer: {e}")
            return False

# Initialize the server
server = AttendanceServer()

# Cleanup on exit
def cleanup():
    server.running = False
    logger.info("Server shutting down...")

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())

# Student endpoints
@app.route('/student/checkin', methods=['POST'])
@rate_limited(server.db.get_server_settings()['max_checkin_rate'])
def student_checkin():
    start_time = time.time()
    data = request.json
    student_id = data.get('student_id')
    bssid = data.get('bssid')
    device_id = data.get('device_id')

    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400

    try:
        # Verify student exists and device is authorized
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403

        # Check if this is a duplicate check-in (same device within checkin interval)
        last_checkin = server.db.get_last_checkin(student_id, device_id)
        
        if last_checkin:
            last_time = datetime.fromisoformat(last_checkin['timestamp'])
            if (datetime.now() - last_time).total_seconds() < server.db.get_server_settings()['checkin_interval'] * 60:
                return jsonify({
                    'message': 'Duplicate check-in ignored',
                    'status': 'present' if bssid and bssid == student.get('last_bssid') else 'absent'
                }), 200

        # Record checkin
        server.db.add_checkin({
            'student_id': student_id,
            'timestamp': datetime.now().isoformat(),
            'bssid': bssid,
            'device_id': device_id
        })

        # Update active device
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })

        # Update student's last check-in time
        server.db.update_student(student_id, {'last_checkin': datetime.now().isoformat()})

        # Get authorized BSSID
        authorized_bssid = server.db.get_server_settings()['authorized_bssid']

        # Start timer if authorized
        timer_started = False
        if bssid and bssid == authorized_bssid:
            timer_started = server.start_timer(student_id)

        logger.info(f"Checkin processed for {student_id} in {time.time() - start_time:.3f}s")
        return jsonify({
            'message': 'Check-in successful',
            'status': 'present' if bssid and bssid == authorized_bssid else 'absent',
            'timer_started': timer_started,
            'authorized_bssid': authorized_bssid
        }), 200

    except Exception as e:
        logger.error(f"Checkin error for {student_id}: {str(e)}")
        return jsonify({
            'error': 'Check-in failed',
            'details': str(e)
        }), 500

@app.route('/student/login', methods=['POST'])
def student_login():
    data = request.json
    student_id = data.get('id')
    password = data.get('password')
    device_id = data.get('device_id')
    
    if not all([student_id, password, device_id]):
        return jsonify({'error': 'ID, password and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not check_password_hash(student['password'], password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Check if student is locked to a different device
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'This account is locked to another device'}), 403
        
        # Lock student to this device if not already locked
        if not student['locked_device_id']:
            server.db.update_student(student_id, {'locked_device_id': device_id})
        
        # Update or insert active device
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })
        
        # Find BSSID by checking classroom mapping
        classroom = student['classroom']
        expected_bssid = server.db.get_expected_bssid(classroom)
        
        return jsonify({
            'message': 'Login successful',
            'student': {
                'id': student['id'],
                'name': student['name'],
                'classroom': student['classroom'],
                'branch': student['branch'],
                'semester': student['semester']
            },
            'expected_bssid': expected_bssid
        }), 200
    except Exception as e:
        logger.error(f"Student login error: {str(e)}")
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

@app.route('/student/get_status', methods=['GET'])
def student_get_status():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })
        
        # Get checkin
        checkin = server.db.get_last_checkin(student_id)
        
        # Get timer
        timer = server.db.get_timer(student_id)
        
        authorized_bssid = server.db.get_server_settings()['authorized_bssid']
        is_authorized = checkin and checkin['bssid'] == authorized_bssid
        
        # Get expected BSSID for student's classroom
        expected_bssid = server.db.get_expected_bssid(student['classroom'])
        
        status = {
            'student_id': student_id,
            'name': student['name'],
            'classroom': student['classroom'],
            'connected': checkin is not None,
            'authorized': is_authorized,
            'timestamp': checkin['timestamp'] if checkin else None,
            'timer': {
                'status': timer['status'] if timer else 'stop',
                'remaining': timer['remaining'] if timer else 0,
                'start_time': timer['start_time'] if timer else None
            },
            'expected_bssid': expected_bssid,
            'is_connected_to_correct_bssid': checkin and checkin['bssid'] == expected_bssid
        }
        
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting student status: {str(e)}")
        return jsonify({'error': 'Failed to get status', 'details': str(e)}), 500

@app.route('/student/get_attendance', methods=['GET'])
def student_get_attendance():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })
        
        return jsonify({
            'attendance': student.get('attendance', {})
        }), 200
    except Exception as e:
        logger.error(f"Error getting attendance: {str(e)}")
        return jsonify({'error': 'Failed to get attendance', 'details': str(e)}), 500

@app.route('/student/get_active_session', methods=['GET'])
def get_active_session():
    student_id = request.args.get('student_id')
    classroom = request.args.get('classroom')
    
    if not student_id or not classroom:
        return jsonify({'error': 'Student ID and classroom are required'}), 400
    
    try:
        if not server.db.get_student(student_id):
            return jsonify({'error': 'Student not found'}), 404
        
        session = server.db.get_active_session_for_classroom(classroom)
        
        if session:
            return jsonify({
                'active': True,
                'session': session
            }), 200
        else:
            return jsonify({'active': False}), 200
    except Exception as e:
        logger.error(f"Error getting active session: {str(e)}")
        return jsonify({'error': 'Failed to get active session', 'details': str(e)}), 500

@app.route('/student/get_timetable', methods=['GET'])
def student_get_timetable():
    student_id = request.args.get('student_id')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    if not student_id or not branch or not semester:
        return jsonify({'error': 'Student ID, branch and semester are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        timetable = server.db.get_timetable(branch, semester)
        
        return jsonify({
            'timetable': timetable
        }), 200
    except Exception as e:
        logger.error(f"Error getting timetable: {str(e)}")
        return jsonify({'error': 'Failed to get timetable', 'details': str(e)}), 500

@app.route('/student/ping', methods=['POST'])
def student_ping():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })
        
        return jsonify({'message': 'Ping successful'}), 200
    except Exception as e:
        logger.error(f"Error processing ping: {str(e)}")
        return jsonify({'error': 'Ping failed', 'details': str(e)}), 500

@app.route('/student/cleanup_dead_sessions', methods=['POST'])
def cleanup_dead_sessions():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Only cleanup if the device matches
        device = server.db.get_active_device(student_id)
        if device and device['device_id'] == device_id:
            server.db.update_student(student_id, {'locked_device_id': None})
            server.db.data['active_devices'].pop(student_id, None)
        
        server.db.data['checkins'] = [c for c in server.db.data['checkins'] if c['student_id'] != student_id]
        server.db.data['timers'].pop(student_id, None)
    
        return jsonify({'message': 'Session cleanup completed'}), 200
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {str(e)}")
        return jsonify({'error': 'Cleanup failed', 'details': str(e)}), 500

@app.route('/student/get_expected_bssid', methods=['GET'])
def get_expected_bssid():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.add_active_device({
            'student_id': student_id,
            'device_id': device_id,
            'last_activity': datetime.now().isoformat()
        })
        
        # Get expected BSSID for student's classroom
        classroom = student['classroom']
        expected_bssid = server.db.get_expected_bssid(classroom)
        
        return jsonify({
            'expected_bssid': expected_bssid,
            'classroom': classroom
        }), 200
    except Exception as e:
        logger.error(f"Error getting expected BSSID: {str(e)}")
        return jsonify({'error': 'Failed to get expected BSSID', 'details': str(e)}), 500

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
    
    try:
        if server.db.get_teacher(teacher_id):
            return jsonify({'error': 'Teacher ID already exists'}), 400
        
        if any(t['email'] == email for t in server.db.data['teachers'].values()):
            return jsonify({'error': 'Email already registered'}), 400
        
        server.db.add_teacher({
            'id': teacher_id,
            'password': generate_password_hash(password),
            'email': email,
            'name': name,
            'classrooms': [],
            'bssid_mapping': {},
            'branches': ["CSE", "ECE", "EEE", "ME", "CE"],
            'semesters': list(range(1, 9))
        })
        
        return jsonify({'message': 'Registration successful'}), 201
    except Exception as e:
        logger.error(f"Teacher signup error: {str(e)}")
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    data = request.json
    teacher_id = data.get('id')
    password = data.get('password')
    
    if not all([teacher_id, password]):
        return jsonify({'error': 'ID and password are required'}), 400
    
    try:
        teacher = server.db.get_teacher(teacher_id)
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if not check_password_hash(teacher['password'], password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        return jsonify({
            'message': 'Login successful',
            'teacher': teacher
        }), 200
    except Exception as e:
        logger.error(f"Teacher login error: {str(e)}")
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

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
    
    try:
        if server.db.get_student(student_id):
            return jsonify({'error': 'Student ID already exists'}), 400
        
        server.db.add_student({
            'id': student_id,
            'password': generate_password_hash(password),
            'name': name,
            'classroom': classroom,
            'branch': branch,
            'semester': semester,
            'attendance': {},
            'locked_device_id': None,
            'last_checkin': None
        })
        
        return jsonify({'message': 'Student registered successfully'}), 201
    except Exception as e:
        logger.error(f"Error registering student: {str(e)}")
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500

@app.route('/teacher/get_students', methods=['GET'])
def get_students():
    classroom = request.args.get('classroom')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    try:
        students = []
        if classroom:
            students = server.db.get_students_by_classroom(classroom)
        elif branch and semester:
            students = server.db.get_students_by_branch_semester(branch, semester)
        else:
            students = list(server.db.data['students'].values())
        
        return jsonify({'students': students}), 200
    except Exception as e:
        logger.error(f"Error getting students: {str(e)}")
        return jsonify({'error': 'Failed to get students', 'details': str(e)}), 500

@app.route('/teacher/update_student', methods=['POST'])
def update_student():
    data = request.json
    student_id = data.get('id')
    new_data = data.get('new_data')
    
    if not student_id or not new_data:
        return jsonify({'error': 'Student ID and new data are required'}), 400
    
    try:
        if not server.db.get_student(student_id):
            return jsonify({'error': 'Student not found'}), 404
        
        valid_fields = ['name', 'classroom', 'branch', 'semester', 'locked_device_id', 'attendance']
        updates = {k: v for k, v in new_data.items() if k in valid_fields}
        
        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        server.db.update_student(student_id, updates)
        
        return jsonify({'message': 'Student updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error updating student: {str(e)}")
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500

@app.route('/teacher/delete_student', methods=['POST'])
def delete_student():
    data = request.json
    student_id = data.get('id')
    
    if not student_id:
        return jsonify({'error': 'Student ID is required'}), 400
    
    try:
        if not server.db.get_student(student_id):
            return jsonify({'error': 'Student not found'}), 404
        
        server.db.delete_student(student_id)
        
        return jsonify({'message': 'Student deleted successfully'}), 200
    except Exception as e:
        logger.error(f"Error deleting student: {str(e)}")
        return jsonify({'error': 'Deletion failed', 'details': str(e)}), 500

@app.route('/teacher/update_profile', methods=['POST'])
def update_teacher_profile():
    data = request.json
    teacher_id = data.get('id')
    new_data = data.get('new_data')
    
    if not teacher_id or not new_data:
        return jsonify({'error': 'Teacher ID and new data are required'}), 400
    
    try:
        if not server.db.get_teacher(teacher_id):
            return jsonify({'error': 'Teacher not found'}), 404
        
        valid_fields = ['email', 'name', 'classrooms', 'bssid_mapping', 'branches', 'semesters']
        updates = {k: v for k, v in new_data.items() if k in valid_fields}
        
        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        server.db.update_teacher(teacher_id, updates)
        
        return jsonify({'message': 'Profile updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error updating teacher profile: {str(e)}")
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500

@app.route('/teacher/change_password', methods=['POST'])
def change_teacher_password():
    data = request.json
    teacher_id = data.get('id')
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not all([teacher_id, old_password, new_password]):
        return jsonify({'error': 'All fields are required'}), 400
    
    try:
        teacher = server.db.get_teacher(teacher_id)
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if not check_password_hash(teacher['password'], old_password):
            return jsonify({'error': 'Incorrect current password'}), 401
        
        server.db.update_teacher(teacher_id, {'password': generate_password_hash(new_password)})
        
        return jsonify({'message': 'Password changed successfully'}), 200
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        return jsonify({'error': 'Password change failed', 'details': str(e)}), 500

@app.route('/teacher/update_bssid', methods=['POST'])
def update_bssid_mapping():
    data = request.json
    teacher_id = data.get('teacher_id')
    classroom = data.get('classroom')
    bssid = data.get('bssid')
    
    if not all([teacher_id, classroom]):
        return jsonify({'error': 'Teacher ID and classroom are required'}), 400
    
    try:
        teacher = server.db.get_teacher(teacher_id)
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Update the global BSSID mapping
        server.db.set_bssid_mapping(teacher_id, classroom, bssid)
        
        # If this classroom is currently in session, update the authorized BSSID
        active_session = server.db.get_active_session_for_classroom(classroom)
        if active_session:
            server.db.update_server_settings({'authorized_bssid': bssid})
        
        return jsonify({
            'message': 'BSSID mapping updated successfully',
            'expected_bssid': bssid
        }), 200
    except Exception as e:
        logger.error(f"Error updating BSSID mapping: {str(e)}")
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500

@app.route('/teacher/get_bssid_mappings', methods=['GET'])
def get_bssid_mappings():
    teacher_id = request.args.get('teacher_id')
    
    if not teacher_id:
        return jsonify({'error': 'Teacher ID is required'}), 400
    
    try:
        teacher = server.db.get_teacher(teacher_id)
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        return jsonify({
            'bssid_mappings': teacher.get('bssid_mapping', {})
        }), 200
    except Exception as e:
        logger.error(f"Error getting BSSID mappings: {str(e)}")
        return jsonify({'error': 'Failed to get BSSID mappings', 'details': str(e)}), 500

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
    
    try:
        if not server.db.get_teacher(teacher_id):
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Check for existing active session in this classroom
        active_session = server.db.get_active_session_for_classroom(classroom)
        if active_session:
            return jsonify({'error': 'There is already an active session for this classroom'}), 400
        
        session_id = str(uuid.uuid4())
        start_time = datetime.now().isoformat()
        
        server.db.add_session({
            'id': session_id,
            'teacher_id': teacher_id,
            'classroom': classroom,
            'subject': subject,
            'branch': branch,
            'semester': semester,
            'start_time': start_time,
            'end_time': None,
            'ad_hoc': bool(data.get('ad_hoc', False))
        })
        
        # Set authorized BSSID from teacher's mapping
        teacher = server.db.get_teacher(teacher_id)
        authorized_bssid = teacher.get('bssid_mapping', {}).get(classroom)
        
        if authorized_bssid:
            server.db.update_server_settings({'authorized_bssid': authorized_bssid})
        
        # Get expected BSSID for this classroom
        expected_bssid = server.db.get_expected_bssid(classroom)
        
        return jsonify({
            'message': 'Session started successfully',
            'session_id': session_id,
            'authorized_bssid': authorized_bssid,
            'expected_bssid': expected_bssid
        }), 201
    except Exception as e:
        logger.error(f"Error starting session: {str(e)}")
        return jsonify({'error': 'Failed to start session', 'details': str(e)}), 500

@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    try:
        session = server.db.get_session(session_id)
        if not session or session.get('end_time'):
            return jsonify({'error': 'Session not found or already ended'}), 404
        
        end_time = datetime.now().isoformat()
        
        # Update session
        server.db.update_session(session_id, {'end_time': end_time})
        
        # Record attendance for checked-in students
        classroom = session['classroom']
        session_start = datetime.fromisoformat(session['start_time'])
        session_end = datetime.now()
        
        checkins = server.db.get_checkins_for_classroom(classroom, session['start_time'], end_time)
        
        for checkin in checkins:
            student_id = checkin['student_id']
            student = server.db.get_student(student_id)
            if not student:
                continue
            
            authorized_bssid = server.db.get_server_settings()['authorized_bssid']
            is_authorized = checkin['bssid'] == authorized_bssid
            
            date_str = session_start.date().isoformat()
            session_key = f"{session['subject']}_{session_id}"
            
            attendance = student.get('attendance', {})
            if date_str not in attendance:
                attendance[date_str] = {}
            
            attendance[date_str][session_key] = {
                'status': 'present' if is_authorized else 'absent',
                'subject': session['subject'],
                'classroom': classroom,
                'start_time': session['start_time'],
                'end_time': end_time,
                'branch': session['branch'],
                'semester': session['semester']
            }
            
            server.db.update_student(student_id, {'attendance': attendance})
        
        # Clear authorized BSSID
        server.db.update_server_settings({'authorized_bssid': None})
        
        return jsonify({'message': 'Session ended successfully'}), 200
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        return jsonify({'error': 'Failed to end session', 'details': str(e)}), 500

@app.route('/teacher/get_sessions', methods=['GET'])
def get_sessions():
    teacher_id = request.args.get('teacher_id')
    classroom = request.args.get('classroom')
    
    try:
        sessions = []
        if teacher_id:
            sessions = server.db.get_sessions_by_teacher(teacher_id)
        elif classroom:
            sessions = [s for s in server.db.data['sessions'].values() if s['classroom'] == classroom]
        else:
            sessions = list(server.db.data['sessions'].values())
        
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        return jsonify({'error': 'Failed to get sessions', 'details': str(e)}), 500

@app.route('/teacher/get_active_sessions', methods=['GET'])
def get_active_sessions():
    teacher_id = request.args.get('teacher_id')
    
    try:
        sessions = server.db.get_active_sessions(teacher_id)
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        logger.error(f"Error getting active sessions: {str(e)}")
        return jsonify({'error': 'Failed to get active sessions', 'details': str(e)}), 500

@app.route('/teacher/set_bssid', methods=['POST'])
def set_bssid():
    data = request.json
    bssid = data.get('bssid')
    
    if not bssid:
        return jsonify({'error': 'BSSID is required'}), 400
    
    try:
        server.db.update_server_settings({'authorized_bssid': bssid})
    
        return jsonify({'message': 'Authorized BSSID set successfully'}), 200
    except Exception as e:
        logger.error(f"Error setting BSSID: {str(e)}")
        return jsonify({'error': 'Failed to set BSSID', 'details': str(e)}), 500

@app.route('/teacher/get_status', methods=['GET'])
def get_status():
    classroom = request.args.get('classroom')
    
    try:
        status = {
            'authorized_bssid': server.db.get_server_settings()['authorized_bssid'],
            'students': {}
        }
        
        students = server.db.get_students_by_classroom(classroom) if classroom else server.db.data['students'].values()
        
        for student in students:
            student_id = student['id']
            
            # Get checkin
            checkin = server.db.get_last_checkin(student_id)
            
            # Get timer
            timer = server.db.get_timer(student_id)
            
            authorized_bssid = status['authorized_bssid']
            is_authorized = checkin and checkin['bssid'] == authorized_bssid
            
            status['students'][student_id] = {
                'name': student['name'],
                'classroom': student['classroom'],
                'branch': student['branch'],
                'semester': student['semester'],
                'connected': checkin is not None,
                'authorized': is_authorized,
                'timestamp': checkin['timestamp'] if checkin else None,
                'timer': {
                    'status': timer['status'] if timer else 'stop',
                    'remaining': timer['remaining'] if timer else 0,
                    'start_time': timer['start_time'] if timer else None
                }
            }
        
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({'error': 'Failed to get status', 'details': str(e)}), 500

@app.route('/teacher/manual_override', methods=['POST'])
def manual_override():
    data = request.json
    student_id = data.get('student_id')
    status = data.get('status')
    
    if not all([student_id, status]):
        return jsonify({'error': 'Student ID and status are required'}), 400
    
    if status not in ['present', 'absent']:
        return jsonify({'error': 'Status must be "present" or "absent"'}), 400
    
    try:
        if not server.db.get_student(student_id):
            return jsonify({'error': 'Student not found'}), 404
        
        server.db.add_manual_override({
            'student_id': student_id,
            'status': status
        })
        
        if status == 'present':
            server.start_timer(student_id)
        
        return jsonify({'message': f'Student {student_id} marked as {status}'}), 200
    except Exception as e:
        logger.error(f"Error applying manual override: {str(e)}")
        return jsonify({'error': 'Failed to apply override', 'details': str(e)}), 500

@app.route('/teacher/random_ring', methods=['POST'])
def random_ring():
    classroom = request.args.get('classroom')
    
    if not classroom:
        return jsonify({'error': 'Classroom is required'}), 400
    
    try:
        # Get all students in classroom with attendance data
        students = server.db.get_students_by_classroom(classroom)
        
        if len(students) < 2:
            return jsonify({'error': 'Need at least 2 students for random ring'}), 400
        
        # Calculate attendance percentages
        student_stats = []
        for student in students:
            attendance = student.get('attendance', {})
            total_sessions = sum(len(sessions) for sessions in attendance.values())
            present_sessions = sum(1 for sessions in attendance.values() 
                                 for session in sessions.values() if session.get('status') == 'present')
            percentage = round((present_sessions / total_sessions) * 100) if total_sessions > 0 else 0
            
            student_stats.append({
                'id': student['id'],
                'name': student['name'],
                'attendance_percentage': percentage
            })
        
        # Sort by attendance percentage
        student_stats.sort(key=lambda x: x['attendance_percentage'])
        
        # Select one from bottom 30% and one from top 30%
        split_point = max(1, len(student_stats) // 3)
        low_attendance = student_stats[:split_point]
        high_attendance = student_stats[-split_point:]
        
        selected_low = random.choice(low_attendance)
        selected_high = random.choice(high_attendance)
        
        return jsonify({
            'message': 'Random ring selection complete',
            'low_attendance_student': selected_low,
            'high_attendance_student': selected_high
        }), 200
    except Exception as e:
        logger.error(f"Error performing random ring: {str(e)}")
        return jsonify({'error': 'Failed to perform random ring', 'details': str(e)}), 500

@app.route('/teacher/get_special_dates', methods=['GET'])
def get_special_dates():
    try:
        special_dates = server.db.get_special_dates()
        return jsonify(special_dates), 200
    except Exception as e:
        logger.error(f"Error getting special dates: {str(e)}")
        return jsonify({'error': 'Failed to get special dates', 'details': str(e)}), 500

@app.route('/teacher/update_special_dates', methods=['POST'])
def update_special_dates():
    data = request.json
    holidays = data.get('holidays', [])
    special_schedules = data.get('special_schedules', [])
    
    try:
        server.db.update_special_dates(holidays, special_schedules)
        return jsonify({'message': 'Special dates updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error updating special dates: {str(e)}")
        return jsonify({'error': 'Failed to update special dates', 'details': str(e)}), 500

@app.route('/teacher/get_timetable', methods=['GET'])
def get_timetable():
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400
    
    try:
        timetable = server.db.get_timetable(branch, semester)
        return jsonify({'timetable': timetable}), 200
    except Exception as e:
        logger.error(f"Error getting timetable: {str(e)}")
        return jsonify({'error': 'Failed to get timetable', 'details': str(e)}), 500

@app.route('/teacher/update_timetable', methods=['POST'])
def update_timetable():
    data = request.json
    branch = data.get('branch')
    semester = data.get('semester')
    timetable = data.get('timetable', [])
    
    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400
    
    try:
        server.db.update_timetable(branch, semester, timetable)
        return jsonify({'message': 'Timetable updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error updating timetable: {str(e)}")
        return jsonify({'error': 'Failed to update timetable', 'details': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting server on port 5000")
    app.run(host='0.0.0.0', port=5000)
