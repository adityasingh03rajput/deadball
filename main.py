
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import threading
import time
import random
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
import logging
from logging.handlers import RotatingFileHandler
import json
import sqlite3
from contextlib import contextmanager
import signal
import sys

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        RotatingFileHandler('attendance_server.log', maxBytes=10485760, backupCount=3),
        logging.StreamHandler()
    ]
)

app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app, origins=["*"])

class AttendanceDatabase:
    def __init__(self, db_path='attendance.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with all necessary tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Teachers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teachers (
                    id TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    classrooms TEXT DEFAULT '[]',
                    bssid_mapping TEXT DEFAULT '{}',
                    branches TEXT DEFAULT '["CSE", "ECE", "EEE", "ME", "CE"]',
                    semesters TEXT DEFAULT '[1,2,3,4,5,6,7,8]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Students table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    name TEXT NOT NULL,
                    classroom TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    semester INTEGER NOT NULL,
                    attendance TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    classroom TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    branch TEXT,
                    semester INTEGER,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    ad_hoc BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # System config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Initialize default admin if not exists
            cursor.execute('SELECT id FROM teachers WHERE id = ?', ('admin',))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    'admin',
                    generate_password_hash('admin'),
                    'admin@school.com',
                    'Admin',
                    json.dumps(["A101", "A102", "B201", "B202"]),
                    json.dumps({"A101": "00:11:22:33:44:55", "A102": "AA:BB:CC:DD:EE:FF"})
                ))
            
            # Initialize sample students if not exists
            cursor.execute('SELECT COUNT(*) FROM students')
            if cursor.fetchone()[0] == 0:
                sample_students = [
                    ("s001", "student123", "John Doe", "A101", "CSE", 3),
                    ("s002", "student123", "Jane Smith", "A101", "CSE", 3)
                ]
                for student in sample_students:
                    cursor.execute('''
                        INSERT INTO students (id, password, name, classroom, branch, semester)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (student[0], generate_password_hash(student[1]), *student[2:]))
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

class AttendanceServer:
    def __init__(self):
        self.db = AttendanceDatabase()
        
        # In-memory data for real-time operations
        self.student_checkins = {}
        self.student_timers = {}
        self.manual_overrides = {}
        self.active_devices = {}
        self.authorized_bssid = None
        self.active_sessions = {}
        
        # Thread-safe locks
        self.checkins_lock = threading.RLock()
        self.timers_lock = threading.RLock()
        self.devices_lock = threading.RLock()
        
        # Configuration
        self.CHECKIN_INTERVAL = 5  # seconds
        self.TIMER_DURATION = 300  # 5 minutes in seconds
        self.MAX_CONCURRENT_USERS = 300
        self.SESSION_TIMEOUT = 3600  # 1 hour
        
        # Start background threads
        self.running = True
        self.start_background_threads()
        
        # Setup graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle graceful shutdown"""
        logging.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        sys.exit(0)
    
    def start_background_threads(self):
        """Start all background maintenance threads"""
        threads = [
            threading.Thread(target=self.update_timers, daemon=True, name="TimerUpdater"),
            threading.Thread(target=self.cleanup_checkins, daemon=True, name="CheckinCleaner"),
            threading.Thread(target=self.cleanup_active_devices, daemon=True, name="DeviceCleaner"),
            threading.Thread(target=self.persist_data, daemon=True, name="DataPersister")
        ]
        
        for thread in threads:
            thread.start()
            logging.info(f"Started background thread: {thread.name}")
    
    def update_timers(self):
        """Background thread to update all student timers"""
        while self.running:
            try:
                current_time = datetime.now().timestamp()
                
                with self.timers_lock:
                    for student_id, timer in list(self.student_timers.items()):
                        if timer['status'] == 'running':
                            elapsed = current_time - timer['start_time']
                            remaining = max(0, timer['duration'] - elapsed)
                            
                            if remaining <= 0:
                                timer['status'] = 'completed'
                                self.record_attendance(student_id)
                            
                            self.student_timers[student_id]['remaining'] = remaining
                
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error in update_timers: {e}")
                time.sleep(5)
    
    def record_attendance(self, student_id):
        """Record attendance for completed timer"""
        try:
            with self.timers_lock:
                if student_id not in self.student_timers:
                    return
                
                timer = self.student_timers[student_id]
                if timer['status'] != 'completed':
                    return
                
                # Check authorization
                with self.checkins_lock:
                    checkin = self.student_checkins.get(student_id, {})
                    is_authorized = checkin.get('bssid') == self.authorized_bssid
                
                # Get student data
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
                    student = cursor.fetchone()
                    
                    if not student:
                        return
                    
                    # Update attendance in database
                    attendance = json.loads(student['attendance'] or '{}')
                    date_str = datetime.fromtimestamp(timer['start_time']).date().isoformat()
                    session_key = f"timer_{int(timer['start_time'])}"
                    
                    if date_str not in attendance:
                        attendance[date_str] = {}
                    
                    attendance[date_str][session_key] = {
                        'status': 'present' if is_authorized else 'absent',
                        'subject': 'Timer Session',
                        'classroom': student['classroom'],
                        'start_time': datetime.fromtimestamp(timer['start_time']).isoformat(),
                        'end_time': datetime.fromtimestamp(timer['start_time'] + self.TIMER_DURATION).isoformat(),
                        'branch': student['branch'],
                        'semester': student['semester']
                    }
                    
                    cursor.execute(
                        'UPDATE students SET attendance = ? WHERE id = ?',
                        (json.dumps(attendance), student_id)
                    )
                    conn.commit()
                    
        except Exception as e:
            logging.error(f"Error recording attendance for {student_id}: {e}")
    
    def cleanup_checkins(self):
        """Background thread to clean up old checkins"""
        while self.running:
            try:
                current_time = datetime.now()
                threshold = current_time - timedelta(minutes=10)
                
                with self.checkins_lock:
                    for student_id in list(self.student_checkins.keys()):
                        last_checkin = self.student_checkins[student_id].get('timestamp')
                        if last_checkin and datetime.fromisoformat(last_checkin) < threshold:
                            del self.student_checkins[student_id]
                
                time.sleep(60)
            except Exception as e:
                logging.error(f"Error in cleanup_checkins: {e}")
                time.sleep(60)
    
    def cleanup_active_devices(self):
        """Background thread to clean up inactive devices"""
        while self.running:
            try:
                current_time = datetime.now()
                threshold = current_time - timedelta(minutes=5)
                
                with self.devices_lock:
                    for student_id in list(self.active_devices.keys()):
                        last_activity = self.active_devices[student_id].get('last_activity')
                        if last_activity and datetime.fromisoformat(last_activity) < threshold:
                            del self.active_devices[student_id]
                
                time.sleep(60)
            except Exception as e:
                logging.error(f"Error in cleanup_active_devices: {e}")
                time.sleep(60)
    
    def persist_data(self):
        """Background thread to persist in-memory data periodically"""
        while self.running:
            try:
                # This could be used to backup critical in-memory state
                time.sleep(300)  # Every 5 minutes
            except Exception as e:
                logging.error(f"Error in persist_data: {e}")
                time.sleep(300)
    
    def start_timer(self, student_id):
        """Start timer for a student"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM students WHERE id = ?', (student_id,))
                if not cursor.fetchone():
                    return False
            
            with self.timers_lock:
                self.student_timers[student_id] = {
                    'status': 'running',
                    'start_time': datetime.now().timestamp(),
                    'duration': self.TIMER_DURATION,
                    'remaining': self.TIMER_DURATION
                }
            
            return True
        except Exception as e:
            logging.error(f"Error starting timer for {student_id}: {e}")
            return False

# Initialize the server
server = AttendanceServer()

# Serve React app
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_users': len(server.active_devices),
        'active_timers': len([t for t in server.student_timers.values() if t['status'] == 'running'])
    }), 200

# Teacher endpoints
@app.route('/api/teacher/signup', methods=['POST'])
def teacher_signup():
    try:
        data = request.json
        teacher_id = data.get('id', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        name = data.get('name', '').strip()
        
        if not all([teacher_id, password, email, name]):
            return jsonify({'error': 'All fields are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if teacher ID or email exists
            cursor.execute('SELECT id FROM teachers WHERE id = ? OR email = ?', (teacher_id, email))
            if cursor.fetchone():
                return jsonify({'error': 'Teacher ID or email already exists'}), 400
            
            cursor.execute('''
                INSERT INTO teachers (id, password, email, name)
                VALUES (?, ?, ?, ?)
            ''', (teacher_id, generate_password_hash(password), email, name))
            conn.commit()
            
            return jsonify({'message': 'Registration successful'}), 201
            
    except Exception as e:
        logging.error(f"Error in teacher_signup: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/login', methods=['POST'])
def teacher_login():
    try:
        data = request.json
        teacher_id = data.get('id', '').strip()
        password = data.get('password', '')
        
        if not all([teacher_id, password]):
            return jsonify({'error': 'ID and password are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
            teacher = cursor.fetchone()
            
            if not teacher:
                return jsonify({'error': 'Teacher not found'}), 404
            
            if not check_password_hash(teacher['password'], password):
                return jsonify({'error': 'Incorrect password'}), 401
            
            teacher_data = {
                'id': teacher['id'],
                'name': teacher['name'],
                'email': teacher['email'],
                'classrooms': json.loads(teacher['classrooms'] or '[]'),
                'bssid_mapping': json.loads(teacher['bssid_mapping'] or '{}'),
                'branches': json.loads(teacher['branches'] or '[]'),
                'semesters': json.loads(teacher['semesters'] or '[]')
            }
            
            return jsonify({
                'message': 'Login successful',
                'teacher': teacher_data
            }), 200
            
    except Exception as e:
        logging.error(f"Error in teacher_login: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/register_student', methods=['POST'])
def register_student():
    try:
        data = request.json
        student_id = data.get('id', '').strip()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        classroom = data.get('classroom', '').strip()
        branch = data.get('branch', '').strip()
        semester = data.get('semester')
        
        if not all([student_id, password, name, classroom, branch]) or semester is None:
            return jsonify({'error': 'All fields are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if student ID exists
            cursor.execute('SELECT id FROM students WHERE id = ?', (student_id,))
            if cursor.fetchone():
                return jsonify({'error': 'Student ID already exists'}), 400
            
            cursor.execute('''
                INSERT INTO students (id, password, name, classroom, branch, semester)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (student_id, generate_password_hash(password), name, classroom, branch, int(semester)))
            conn.commit()
            
            return jsonify({'message': 'Student registered successfully'}), 201
            
    except Exception as e:
        logging.error(f"Error in register_student: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/get_students', methods=['GET'])
def get_students():
    try:
        classroom = request.args.get('classroom')
        branch = request.args.get('branch')
        semester = request.args.get('semester')
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT id, name, classroom, branch, semester FROM students WHERE 1=1'
            params = []
            
            if classroom:
                query += ' AND classroom = ?'
                params.append(classroom)
            if branch:
                query += ' AND branch = ?'
                params.append(branch)
            if semester:
                query += ' AND semester = ?'
                params.append(int(semester))
            
            cursor.execute(query, params)
            students = [dict(row) for row in cursor.fetchall()]
            
            return jsonify({'students': students}), 200
            
    except Exception as e:
        logging.error(f"Error in get_students: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/start_session', methods=['POST'])
def start_session():
    try:
        data = request.json
        teacher_id = data.get('teacher_id', '').strip()
        classroom = data.get('classroom', '').strip()
        subject = data.get('subject', '').strip()
        branch = data.get('branch', '').strip()
        semester = data.get('semester')
        
        if not all([teacher_id, classroom, subject]):
            return jsonify({'error': 'Teacher ID, classroom and subject are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if teacher exists
            cursor.execute('SELECT bssid_mapping FROM teachers WHERE id = ?', (teacher_id,))
            teacher = cursor.fetchone()
            if not teacher:
                return jsonify({'error': 'Teacher not found'}), 404
            
            # Check for existing active session
            cursor.execute('''
                SELECT id FROM sessions 
                WHERE classroom = ? AND end_time IS NULL
            ''', (classroom,))
            if cursor.fetchone():
                return jsonify({'error': 'There is already an active session for this classroom'}), 400
            
            session_id = f"session_{int(datetime.now().timestamp())}"
            cursor.execute('''
                INSERT INTO sessions (id, teacher_id, classroom, subject, branch, semester, start_time, ad_hoc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, teacher_id, classroom, subject, branch, semester, 
                  datetime.now().isoformat(), data.get('ad_hoc', False)))
            conn.commit()
            
            # Set the authorized BSSID for this classroom
            bssid_mapping = json.loads(teacher['bssid_mapping'] or '{}')
            server.authorized_bssid = bssid_mapping.get(classroom)
            server.active_sessions[session_id] = {
                'classroom': classroom,
                'teacher_id': teacher_id,
                'start_time': datetime.now().isoformat()
            }
            
            return jsonify({
                'message': 'Session started successfully',
                'session_id': session_id,
                'authorized_bssid': server.authorized_bssid
            }), 201
            
    except Exception as e:
        logging.error(f"Error in start_session: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/end_session', methods=['POST'])
def end_session():
    try:
        data = request.json
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM sessions WHERE id = ? AND end_time IS NULL', (session_id,))
            session = cursor.fetchone()
            if not session:
                return jsonify({'error': 'Session not found or already ended'}), 404
            
            cursor.execute(
                'UPDATE sessions SET end_time = ? WHERE id = ?',
                (datetime.now().isoformat(), session_id)
            )
            
            # Record attendance for checked-in students
            classroom = session['classroom']
            session_start = datetime.fromisoformat(session['start_time'])
            session_end = datetime.now()
            
            with server.checkins_lock:
                for student_id, checkin in server.student_checkins.items():
                    cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
                    student = cursor.fetchone()
                    
                    if student and student['classroom'] == classroom:
                        checkin_time = datetime.fromisoformat(checkin['timestamp'])
                        
                        if session_start <= checkin_time <= session_end:
                            attendance = json.loads(student['attendance'] or '{}')
                            date_str = session_start.date().isoformat()
                            session_key = f"{session['subject']}_{session_id}"
                            
                            if date_str not in attendance:
                                attendance[date_str] = {}
                            
                            attendance[date_str][session_key] = {
                                'status': 'present' if checkin.get('bssid') == server.authorized_bssid else 'absent',
                                'subject': session['subject'],
                                'classroom': classroom,
                                'start_time': session['start_time'],
                                'end_time': datetime.now().isoformat(),
                                'branch': session.get('branch'),
                                'semester': session.get('semester')
                            }
                            
                            cursor.execute(
                                'UPDATE students SET attendance = ? WHERE id = ?',
                                (json.dumps(attendance), student_id)
                            )
            
            conn.commit()
            
            # Clear the authorized BSSID and active session
            server.authorized_bssid = None
            if session_id in server.active_sessions:
                del server.active_sessions[session_id]
            
            return jsonify({'message': 'Session ended successfully'}), 200
            
    except Exception as e:
        logging.error(f"Error in end_session: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/teacher/get_status', methods=['GET'])
def get_teacher_status():
    try:
        classroom = request.args.get('classroom')
        
        status = {
            'authorized_bssid': server.authorized_bssid,
            'students': {}
        }
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM students WHERE 1=1'
            params = []
            if classroom:
                query += ' AND classroom = ?'
                params.append(classroom)
            
            cursor.execute(query, params)
            students = cursor.fetchall()
            
            with server.checkins_lock, server.timers_lock:
                for student in students:
                    student_id = student['id']
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
        
    except Exception as e:
        logging.error(f"Error in get_teacher_status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Student endpoints
@app.route('/api/student/login', methods=['POST'])
def student_login():
    try:
        data = request.json
        student_id = data.get('id', '').strip()
        password = data.get('password', '')
        device_id = data.get('device_id', '').strip()
        
        if not all([student_id, password, device_id]):
            return jsonify({'error': 'ID, password and device ID are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
            student = cursor.fetchone()
            
            if not student:
                return jsonify({'error': 'Student not found'}), 404
            
            if not check_password_hash(student['password'], password):
                return jsonify({'error': 'Incorrect password'}), 401
            
            with server.devices_lock:
                if student_id in server.active_devices and server.active_devices[student_id]['device_id'] != device_id:
                    return jsonify({'error': 'This account is already logged in on another device'}), 403
                
                server.active_devices[student_id] = {
                    'device_id': device_id,
                    'last_activity': datetime.now().isoformat()
                }
            
            # Get classroom BSSID
            classroom_bssid = None
            cursor.execute('SELECT bssid_mapping FROM teachers')
            for teacher in cursor.fetchall():
                bssid_mapping = json.loads(teacher['bssid_mapping'] or '{}')
                if student['classroom'] in bssid_mapping:
                    classroom_bssid = bssid_mapping[student['classroom']]
                    break
            
            return jsonify({
                'message': 'Login successful',
                'student': {
                    'id': student['id'],
                    'name': student['name'],
                    'classroom': student['classroom'],
                    'branch': student['branch'],
                    'semester': student['semester']
                },
                'classroom_bssid': classroom_bssid
            }), 200
            
    except Exception as e:
        logging.error(f"Error in student_login: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/student/checkin', methods=['POST'])
def student_checkin():
    try:
        data = request.json
        student_id = data.get('student_id', '').strip()
        bssid = data.get('bssid', '')
        device_id = data.get('device_id', '').strip()
        
        if not all([student_id, device_id]):
            return jsonify({'error': 'Student ID and device ID are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
            student = cursor.fetchone()
            
            if not student:
                return jsonify({'error': 'Student not found'}), 404
        
        with server.devices_lock:
            if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
                return jsonify({'error': 'Unauthorized device'}), 403
            
            server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        with server.checkins_lock:
            server.student_checkins[student_id] = {
                'timestamp': datetime.now().isoformat(),
                'bssid': bssid if bssid else None,
                'device_id': device_id
            }
        
        # Get authorized BSSID for classroom
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT bssid_mapping FROM teachers')
            authorized_bssid = None
            for teacher in cursor.fetchall():
                bssid_mapping = json.loads(teacher['bssid_mapping'] or '{}')
                if student['classroom'] in bssid_mapping:
                    authorized_bssid = bssid_mapping[student['classroom']]
                    break
        
        # Start timer if BSSID matches
        if bssid and bssid == authorized_bssid:
            server.start_timer(student_id)
        
        return jsonify({
            'message': 'Check-in successful',
            'status': 'present' if bssid and bssid == authorized_bssid else 'absent',
            'authorized_bssid': authorized_bssid
        }), 200
        
    except Exception as e:
        logging.error(f"Error in student_checkin: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/student/get_status', methods=['GET'])
def student_get_status():
    try:
        student_id = request.args.get('student_id', '').strip()
        device_id = request.args.get('device_id', '').strip()
        
        if not all([student_id, device_id]):
            return jsonify({'error': 'Student ID and device ID are required'}), 400
        
        with server.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
            student = cursor.fetchone()
            
            if not student:
                return jsonify({'error': 'Student not found'}), 404
        
        with server.devices_lock:
            if student_id not in server.active_devices or server.active_devices[student_id]['device_id'] != device_id:
                return jsonify({'error': 'Unauthorized device'}), 403
            
            server.active_devices[student_id]['last_activity'] = datetime.now().isoformat()
        
        with server.checkins_lock, server.timers_lock:
            checkin = server.student_checkins.get(student_id, {})
            timer = server.student_timers.get(student_id, {})
        
        status = {
            'student_id': student_id,
            'name': student['name'],
            'classroom': student['classroom'],
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
        
    except Exception as e:
        logging.error(f"Error in student_get_status: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
