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
import psycopg2
import psycopg2.extras
import json
from contextlib import contextmanager

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AttendanceServer')
handler = RotatingFileHandler('attendance.log', maxBytes=1000000, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class DatabaseManager:
    def __init__(self, db_url=None):
        self.db_url = db_url or os.getenv('DATABASE_URL')
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Teachers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teachers (
                    id TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL,
                    classrooms TEXT,
                    bssid_mapping TEXT,
                    branches TEXT,
                    semesters TEXT
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
                    attendance TEXT
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
                    ad_hoc INTEGER DEFAULT 0,
                    FOREIGN KEY (teacher_id) REFERENCES teachers (id)
                )
            ''')
            # Checkins table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkins (
                    student_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    bssid TEXT,
                    device_id TEXT NOT NULL,
                    PRIMARY KEY (student_id, device_id),
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            ''')
            # Timers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS timers (
                    student_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    start_time DOUBLE PRECISION,
                    duration INTEGER NOT NULL,
                    remaining INTEGER NOT NULL,
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            ''')
            # Active devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_devices (
                    student_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            ''')
            # Manual overrides table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS manual_overrides (
                    student_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            ''')
            # Timetables table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS timetables (
                    branch TEXT NOT NULL,
                    semester INTEGER NOT NULL,
                    timetable TEXT NOT NULL,
                    PRIMARY KEY (branch, semester)
                )
            ''')
            # Special dates table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS special_dates (
                    id SERIAL PRIMARY KEY,
                    holidays TEXT NOT NULL,
                    special_schedules TEXT NOT NULL
                )
            ''')
            # Server settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS server_settings (
                    id SERIAL PRIMARY KEY,
                    authorized_bssid TEXT,
                    checkin_interval INTEGER NOT NULL,
                    timer_duration INTEGER NOT NULL
                )
            ''')
            cursor.execute('SELECT 1 FROM server_settings LIMIT 1')
            if not cursor.fetchone():
                cursor.execute('INSERT INTO server_settings (authorized_bssid, checkin_interval, timer_duration) VALUES (%s, %s, %s)', (None, 60, 1800))
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = psycopg2.connect(self.db_url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, query, params=(), commit=False):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            return cursor

    def fetch_one(self, query, params=()):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query, params=()):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

class AttendanceServer:
    def __init__(self):
        self.db = DatabaseManager()
        self.lock = threading.Lock()
        self.running = True
        
        # Load server settings
        settings = self.db.fetch_one('SELECT * FROM server_settings')
        self.CHECKIN_INTERVAL = settings['checkin_interval']
        self.TIMER_DURATION = settings['timer_duration']
        self.SERVER_PORT = int(os.getenv('PORT', 5000))
        
        # Initialize with admin if not exists
        if not self.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s', ('admin',)):
            self._create_admin_account()
        
        # Start background threads
        self.start_background_threads()
    
    def _create_admin_account(self):
        self.db.execute(
            'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (
                'admin',
                generate_password_hash('admin'),
                'admin@school.com',
                'Admin',
                json.dumps(["A101", "A102", "B201", "B202"]),
                json.dumps({"A101": "00:11:22:33:44:55", "A102": "AA:BB:CC:DD:EE:FF"}),
                json.dumps(["CSE", "ECE", "EEE", "ME", "CE"]),
                json.dumps(list(range(1, 9)))
            ),
            commit=True
        )
        
        # Create sample students if none exist
        if not self.db.fetch_one('SELECT 1 FROM students LIMIT 1'):
            self.db.execute(
                'INSERT INTO students (id, password, name, classroom, branch, semester, attendance) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (
                    's001',
                    generate_password_hash('student123'),
                    'John Doe',
                    'A101',
                    'CSE',
                    3,
                    json.dumps({})
                ),
                commit=True
            )
            self.db.execute(
                'INSERT INTO students (id, password, name, classroom, branch, semester, attendance) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (
                    's002',
                    generate_password_hash('student123'),
                    'Jane Smith',
                    'A101',
                    'CSE',
                    3,
                    json.dumps({})
                ),
                commit=True
            )
            
            # Create sample timetable
            self.db.execute(
                'INSERT INTO timetables (branch, semester, timetable) VALUES (%s, %s, %s)',
                (
                    'CSE',
                    3,
                    json.dumps([
                        ["Monday", "09:00", "10:00", "Mathematics", "A101"],
                        ["Monday", "10:00", "11:00", "Physics", "A101"]
                    ])
                ),
                commit=True
            )
    
    def start_background_threads(self):
        """Start all background maintenance threads"""
        timer_thread = threading.Thread(target=self.update_timers, daemon=True)
        timer_thread.start()
        
        cleanup_thread = threading.Thread(target=self.cleanup_checkins, daemon=True)
        cleanup_thread.start()
        
        device_cleanup_thread = threading.Thread(target=self.cleanup_active_devices, daemon=True)
        device_cleanup_thread.start()
    
    def update_timers(self):
        """Background thread to update all student timers"""
        while self.running:
            current_time = datetime.now().timestamp()
            
            with self.lock:
                timers = self.db.fetch_all('SELECT * FROM timers WHERE status = %s', ('running',))
                for timer in timers:
                    elapsed = current_time - timer['start_time']
                    remaining = max(0, timer['duration'] - elapsed)
                    
                    if remaining <= 0:
                        self.db.execute(
                            'UPDATE timers SET status = %s, remaining = %s WHERE student_id = %s',
                            ('completed', 0, timer['student_id']),
                            commit=True
                        )
                        self.record_attendance(timer['student_id'])
                    else:
                        self.db.execute(
                            'UPDATE timers SET remaining = %s WHERE student_id = %s',
                            (remaining, timer['student_id']),
                            commit=True
                        )
            
            time.sleep(1)
    
    def record_attendance(self, student_id):
        """Record attendance for completed timer"""
        with self.lock:
            student = self.db.fetch_one('SELECT * FROM students WHERE id = %s', (student_id,))
            if not student:
                return
            
            timer = self.db.fetch_one('SELECT * FROM timers WHERE student_id = %s', (student_id,))
            if not timer or timer['status'] != 'completed':
                return
            
            # Check authorization
            checkin = self.db.fetch_one(
                'SELECT * FROM checkins WHERE student_id = %s ORDER BY timestamp DESC LIMIT 1',
                (student_id,)
            )
            
            authorized_bssid = self.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid']
            is_authorized = checkin and checkin['bssid'] == authorized_bssid
            
            date_str = datetime.fromtimestamp(timer['start_time']).date().isoformat()
            session_key = f"timer_{int(timer['start_time'])}"
            
            attendance = json.loads(student['attendance']) if student['attendance'] else {}
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
            
            self.db.execute(
                'UPDATE students SET attendance = %s WHERE id = %s',
                (json.dumps(attendance), student_id),
                commit=True
            )
    
    def cleanup_checkins(self):
        """Background thread to clean up old checkins"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=10)).isoformat()
            
            with self.lock:
                self.db.execute(
                    'DELETE FROM checkins WHERE timestamp < %s',
                    (threshold,),
                    commit=True
                )
            
            time.sleep(60)
    
    def cleanup_active_devices(self):
        """Background thread to clean up inactive devices"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            with self.lock:
                inactive_devices = self.db.fetch_all(
                    'SELECT student_id FROM active_devices WHERE last_activity < %s',
                    (threshold,)
                )
                
                for device in inactive_devices:
                    student_id = device['student_id']
                    self.db.execute(
                        'DELETE FROM active_devices WHERE student_id = %s',
                        (student_id,),
                        commit=True
                    )
                    self.db.execute(
                        'DELETE FROM checkins WHERE student_id = %s',
                        (student_id,),
                        commit=True
                    )
                    self.db.execute(
                        'DELETE FROM timers WHERE student_id = %s',
                        (student_id,),
                        commit=True
                    )
            
            time.sleep(60)
    
    def start_timer(self, student_id):
        """Start timer for a student"""
        with self.lock:
            if not self.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
                return False
            
            existing_timer = self.db.fetch_one('SELECT 1 FROM timers WHERE student_id = %s', (student_id,))
            if existing_timer:
                self.db.execute(
                    'UPDATE timers SET status = %s, start_time = %s, duration = %s, remaining = %s WHERE student_id = %s',
                    ('running', datetime.now().timestamp(), self.TIMER_DURATION, self.TIMER_DURATION, student_id),
                    commit=True
                )
            else:
                self.db.execute(
                    'INSERT INTO timers (student_id, status, start_time, duration, remaining) VALUES (%s, %s, %s, %s, %s)',
                    (student_id, 'running', datetime.now().timestamp(), self.TIMER_DURATION, self.TIMER_DURATION),
                    commit=True
                )
            
            return True

# Initialize the server
server = AttendanceServer()

# Cleanup on exit
def cleanup():
    server.running = False
    logger.info("Server shutting down...")

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())

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
        if server.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s', (teacher_id,)):
            return jsonify({'error': 'Teacher ID already exists'}), 400
        if server.db.fetch_one('SELECT 1 FROM teachers WHERE email = %s', (email,)):
            return jsonify({'error': 'Email already registered'}), 400
        server.db.execute(
            'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (
                teacher_id,
                generate_password_hash(password),
                email,
                name,
                json.dumps([]),
                json.dumps({}),
                json.dumps(["CSE", "ECE", "EEE", "ME", "CE"]),
                json.dumps(list(range(1, 9)))
            ),
            commit=True
        )
        
        return jsonify({'message': 'Registration successful'}), 201

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    data = request.json
    teacher_id = data.get('id')
    password = data.get('password')
    
    if not all([teacher_id, password]):
        return jsonify({'error': 'ID and password are required'}), 400
    
    teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = %s', (teacher_id,))
    if not teacher:
        return jsonify({'error': 'Teacher not found'}), 404
    
    if not check_password_hash(teacher['password'], password):
        return jsonify({'error': 'Incorrect password'}), 401
    
    # Convert database row to dict and parse JSON fields
    teacher_dict = dict(teacher)
    teacher_dict['classrooms'] = json.loads(teacher_dict['classrooms'])
    teacher_dict['bssid_mapping'] = json.loads(teacher_dict['bssid_mapping'])
    teacher_dict['branches'] = json.loads(teacher_dict['branches'])
    teacher_dict['semesters'] = json.loads(teacher_dict['semesters'])
    
    return jsonify({
        'message': 'Login successful',
        'teacher': teacher_dict
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
        if server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student ID already exists'}), 400
        
        server.db.execute(
            'INSERT INTO students (id, password, name, classroom, branch, semester, attendance) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (
                student_id,
                generate_password_hash(password),
                name,
                classroom,
                branch,
                semester,
                json.dumps({})
            ),
            commit=True
        )
        
        return jsonify({'message': 'Student registered successfully'}), 201

@app.route('/teacher/get_students', methods=['GET'])
def get_students():
    classroom = request.args.get('classroom')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    query = 'SELECT * FROM students'
    params = []
    conditions = []
    
    if classroom:
        conditions.append('classroom = %s')
        params.append(classroom)
    if branch:
        conditions.append('branch = %s')
        params.append(branch)
    if semester:
        conditions.append('semester = %s')
        params.append(semester)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    with server.lock:
        students = server.db.fetch_all(query, params)
        
        # Convert to list of dicts and parse attendance
        students_list = []
        for student in students:
            student_dict = dict(student)
            student_dict['attendance'] = json.loads(student_dict['attendance']) if student_dict['attendance'] else {}
            students_list.append(student_dict)
    
    return jsonify({'students': students_list}), 200

@app.route('/teacher/update_student', methods=['POST'])
def update_student():
    data = request.json
    student_id = data.get('id')
    new_data = data.get('new_data')
    
    if not student_id or not new_data:
        return jsonify({'error': 'Student ID and new data are required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in new_data.items():
            if key in ['name', 'classroom', 'branch', 'semester']:
                set_clauses.append(f'{key} = %s')
                params.append(value)
            elif key == 'attendance':
                set_clauses.append('attendance = %s')
                params.append(json.dumps(value))
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        query = f'UPDATE students SET {", ".join(set_clauses)} WHERE id = %s'
        params.append(student_id)
        server.db.execute(query, params, commit=True)
        
        return jsonify({'message': 'Student updated successfully'}), 200

@app.route('/teacher/delete_student', methods=['POST'])
def delete_student():
    data = request.json
    student_id = data.get('id')
    
    if not student_id:
        return jsonify({'error': 'Student ID is required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Delete all related data
        server.db.execute('DELETE FROM students WHERE id = %s', (student_id,), commit=True)
        server.db.execute('DELETE FROM checkins WHERE student_id = %s', (student_id,), commit=True)
        server.db.execute('DELETE FROM timers WHERE student_id = %s', (student_id,), commit=True)
        server.db.execute('DELETE FROM active_devices WHERE student_id = %s', (student_id,), commit=True)
        server.db.execute('DELETE FROM manual_overrides WHERE student_id = %s', (student_id,), commit=True)
        
        return jsonify({'message': 'Student deleted successfully'}), 200

@app.route('/teacher/update_profile', methods=['POST'])
def update_teacher_profile():
    data = request.json
    teacher_id = data.get('id')
    new_data = data.get('new_data')
    
    if not teacher_id or not new_data:
        return jsonify({'error': 'Teacher ID and new data are required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s', (teacher_id,)):
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in new_data.items():
            if key in ['email', 'name']:
                set_clauses.append(f'{key} = %s')
                params.append(value)
            elif key in ['classrooms', 'bssid_mapping', 'branches', 'semesters']:
                set_clauses.append(f'{key} = %s')
                params.append(json.dumps(value))
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        query = f'UPDATE teachers SET {", ".join(set_clauses)} WHERE id = %s'
        params.append(teacher_id)
        server.db.execute(query, params, commit=True)
        
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
        teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = %s', (teacher_id,))
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if not check_password_hash(teacher['password'], old_password):
            return jsonify({'error': 'Incorrect current password'}), 401
        server.db.execute(
            'UPDATE teachers SET password = %s WHERE id = %s',
            (generate_password_hash(new_password), teacher_id),
            commit=True
        )
        
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
        teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = %s', (teacher_id,))
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404        
        # Get current bssid_mapping
        bssid_mapping = json.loads(teacher['bssid_mapping'])
        
        # Update the mapping
        bssid_mapping[classroom] = bssid
        
        # Update teacher record
        server.db.execute(
            'UPDATE teachers SET bssid_mapping = %s WHERE id = %s',
            (json.dumps(bssid_mapping), teacher_id),
            commit=True
        )
        
        # Add classroom to teacher's classrooms if not present
        classrooms = json.loads(teacher['classrooms'])
        if classroom not in classrooms:
            classrooms.append(classroom)
            server.db.execute(
                'UPDATE teachers SET classrooms = %s WHERE id = %s',
                (json.dumps(classrooms), teacher_id),
                commit=True
            )
        
        # Update authorized BSSID if it matches this classroom's previous BSSID
        settings = server.db.fetch_one('SELECT authorized_bssid FROM server_settings')
        if settings['authorized_bssid'] == bssid_mapping.get(classroom):
            server.db.execute(
                'UPDATE server_settings SET authorized_bssid = %s',
                (bssid,),
                commit=True
            )
        
        return jsonify({
            'message': 'BSSID mapping updated successfully',
            'bssid_mapping': bssid_mapping
        }), 200

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
        if not server.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s', (teacher_id,)):
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Check for existing active session in this classroom
        active_session = server.db.fetch_one(
            'SELECT 1 FROM sessions WHERE classroom = %s AND end_time IS NULL',
            (classroom,)
        )
        if active_session:
            return jsonify({'error': 'There is already an active session for this classroom'}), 400
        
        session_id = str(uuid.uuid4())
        start_time = datetime.now().isoformat()
        
        server.db.execute(
            'INSERT INTO sessions (id, teacher_id, classroom, subject, branch, semester, start_time, ad_hoc) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (
                session_id,
                teacher_id,
                classroom,
                subject,
                branch,
                semester,
                start_time,
                int(data.get('ad_hoc', False))
            ),
            commit=True
        )
        
        # Set authorized BSSID from teacher's mapping
        teacher = server.db.fetch_one('SELECT bssid_mapping FROM teachers WHERE id = %s', (teacher_id,))
        bssid_mapping = json.loads(teacher['bssid_mapping'])
        authorized_bssid = bssid_mapping.get(classroom)
        
        if authorized_bssid:
            server.db.execute(
                'UPDATE server_settings SET authorized_bssid = %s',
                (authorized_bssid,),
                commit=True
            )
        
        return jsonify({
            'message': 'Session started successfully',
            'session_id': session_id,
            'authorized_bssid': authorized_bssid
        }), 201

@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    with server.lock:
        session = server.db.fetch_one('SELECT * FROM sessions WHERE id = %s', (session_id,))
        if not session or session['end_time']:
            return jsonify({'error': 'Session not found or already ended'}), 404
        
        end_time = datetime.now().isoformat()
        
        # Update session
        server.db.execute(
            'UPDATE sessions SET end_time = %s WHERE id = %s',
            (end_time, session_id),
            commit=True
        )
        
        # Record attendance for checked-in students
        classroom = session['classroom']
        session_start = datetime.fromisoformat(session['start_time'])
        session_end = datetime.now()
        
        checkins = server.db.fetch_all(
            'SELECT * FROM checkins WHERE student_id IN '
            '(SELECT id FROM students WHERE classroom = %s) '
            'AND timestamp BETWEEN %s AND %s',
            (classroom, session['start_time'], end_time)
        )
        
        for checkin in checkins:
            student_id = checkin['student_id']
            student = server.db.fetch_one('SELECT * FROM students WHERE id = %s', (student_id,))
            if not student:
                continue
            
            authorized_bssid = server.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid']
            is_authorized = checkin['bssid'] == authorized_bssid
            
            date_str = session_start.date().isoformat()
            session_key = f"{session['subject']}_{session_id}"
            
            attendance = json.loads(student['attendance']) if student['attendance'] else {}
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
            
            server.db.execute(
                'UPDATE students SET attendance = %s WHERE id = %s',
                (json.dumps(attendance), student_id),
                commit=True
            )
        
        # Clear authorized BSSID
        server.db.execute(
            'UPDATE server_settings SET authorized_bssid = NULL',
            commit=True
        )
        
        return jsonify({'message': 'Session ended successfully'}), 200

@app.route('/teacher/get_sessions', methods=['GET'])
def get_sessions():
    teacher_id = request.args.get('teacher_id')
    classroom = request.args.get('classroom')
    
    query = 'SELECT * FROM sessions'
    params = []
    conditions = []
    
    if teacher_id:
        conditions.append('teacher_id = %s')
        params.append(teacher_id)
    if classroom:
        conditions.append('classroom = %s')
        params.append(classroom)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    with server.lock:
        sessions = server.db.fetch_all(query, params)
        sessions_list = [dict(session) for session in sessions]
    
    return jsonify({'sessions': sessions_list}), 200

@app.route('/teacher/get_active_sessions', methods=['GET'])
def get_active_sessions():
    teacher_id = request.args.get('teacher_id')
    
    query = 'SELECT * FROM sessions WHERE end_time IS NULL'
    params = []
    
    if teacher_id:
        query += ' AND teacher_id = %s'
        params.append(teacher_id)
    
    with server.lock:
        sessions = server.db.fetch_all(query, params)
        sessions_list = [dict(session) for session in sessions]
    
    return jsonify({'sessions': sessions_list}), 200

@app.route('/teacher/set_bssid', methods=['POST'])
def set_bssid():
    data = request.json
    bssid = data.get('bssid')
    
    if not bssid:
        return jsonify({'error': 'BSSID is required'}), 400
    
    with server.lock:
        server.db.execute(
            'UPDATE server_settings SET authorized_bssid = %s',
            (bssid,),
            commit=True
        )
    
    return jsonify({'message': 'Authorized BSSID set successfully'}), 200

@app.route('/teacher/get_status', methods=['GET'])
def get_status():
    classroom = request.args.get('classroom')
    
    status = {
        'authorized_bssid': server.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid'],
        'students': {}
    }
    
    query = 'SELECT * FROM students'
    params = []
    if classroom:
        query += ' WHERE classroom = %s'
        params.append(classroom)
    
    with server.lock:
        students = server.db.fetch_all(query, params)
        
        for student in students:
            student_id = student['id']
            
            # Get checkin
            checkin = server.db.fetch_one(
                'SELECT * FROM checkins WHERE student_id = %s ORDER BY timestamp DESC LIMIT 1',
                (student_id,)
            )
            
            # Get timer
            timer = server.db.fetch_one('SELECT * FROM timers WHERE student_id = %s', (student_id,))
            
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Check if override exists
        existing = server.db.fetch_one('SELECT 1 FROM manual_overrides WHERE student_id = %s', (student_id,))
        
        if existing:
            server.db.execute(
                'UPDATE manual_overrides SET status = %s WHERE student_id = %s',
                (status, student_id),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO manual_overrides (student_id, status) VALUES (%s, %s)',
                (student_id, status),
                commit=True
            )
        
        if status == 'present':
            server.start_timer(student_id)
        
        return jsonify({'message': f'Student {student_id} marked as {status}'}), 200

@app.route('/teacher/random_ring', methods=['POST'])
def random_ring():
    classroom = request.args.get('classroom')
    
    if not classroom:
        return jsonify({'error': 'Classroom is required'}), 400
    
    with server.lock:
        # Get all students in classroom with attendance data
        students = server.db.fetch_all(
            'SELECT id, name, attendance FROM students WHERE classroom = %s',
            (classroom,)
        )
        
        if len(students) < 2:
            return jsonify({'error': 'Need at least 2 students for random ring'}), 400
        
        # Calculate attendance percentages
        student_stats = []
        for student in students:
            attendance = json.loads(student['attendance']) if student['attendance'] else {}
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

@app.route('/teacher/get_special_dates', methods=['GET'])
def get_special_dates():
    with server.lock:
        special_dates = server.db.fetch_one('SELECT * FROM special_dates ORDER BY id DESC LIMIT 1')
        
        if special_dates:
            return jsonify({
                'holidays': json.loads(special_dates['holidays']),
                'special_schedules': json.loads(special_dates['special_schedules'])
            }), 200
        else:
            return jsonify({
                'holidays': [],
                'special_schedules': []
            }), 200

@app.route('/teacher/update_special_dates', methods=['POST'])
def update_special_dates():
    data = request.json
    holidays = data.get('holidays', [])
    special_schedules = data.get('special_schedules', [])
    
    with server.lock:
        server.db.execute(
            'INSERT INTO special_dates (holidays, special_schedules) VALUES (%s, %s)',
            (json.dumps(holidays), json.dumps(special_schedules)),
            commit=True
        )
    
    return jsonify({'message': 'Special dates updated successfully'}), 200

@app.route('/teacher/get_timetable', methods=['GET'])
def get_timetable():
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400
    
    with server.lock:
        timetable = server.db.fetch_one(
            'SELECT timetable FROM timetables WHERE branch = %s AND semester = %s',
            (branch, semester)
        )
        
        if timetable:
            return jsonify({'timetable': json.loads(timetable['timetable'])}), 200
        else:
            return jsonify({'timetable': []}), 200

@app.route('/teacher/update_timetable', methods=['POST'])
def update_timetable():
    data = request.json
    branch = data.get('branch')
    semester = data.get('semester')
    timetable = data.get('timetable', [])
    
    if not branch or not semester:
        return jsonify({'error': 'Branch and semester are required'}), 400
    
    with server.lock:
        existing = server.db.fetch_one(
            'SELECT 1 FROM timetables WHERE branch = %s AND semester = %s',
            (branch, semester)
        )
        
        if existing:
            server.db.execute(
                'UPDATE timetables SET timetable = %s WHERE branch = %s AND semester = %s',
                (json.dumps(timetable), branch, semester),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO timetables (branch, semester, timetable) VALUES (%s, %s, %s)',
                (branch, semester, json.dumps(timetable)),
                commit=True
            )
    
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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = %s', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not check_password_hash(student['password'], password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Check if already logged in on another device
        active_device = server.db.fetch_one(
            'SELECT * FROM active_devices WHERE student_id = %s AND device_id != %s',
            (student_id, device_id)
        )
        if active_device:
            return jsonify({'error': 'This account is already logged in on another device'}), 403
        
        # Update or insert active device
        existing = server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s',
            (student_id,)
        )
        
        if existing:
            server.db.execute(
                'UPDATE active_devices SET device_id = %s, last_activity = %s WHERE student_id = %s',
                (device_id, datetime.now().isoformat(), student_id),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO active_devices (student_id, device_id, last_activity) VALUES (%s, %s, %s)',
                (student_id, device_id, datetime.now().isoformat()),
                commit=True
            )
        
        # Get classroom BSSID from any teacher
        teacher = server.db.fetch_one(
            'SELECT bssid_mapping FROM teachers WHERE classrooms::jsonb ? %s',
            (student['classroom'],)
        )
        
        classroom_bssid = None
        if teacher:
            bssid_mapping = json.loads(teacher['bssid_mapping'])
            classroom_bssid = bssid_mapping.get(student['classroom'])
        
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

@app.route('/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    student_id = data.get('student_id')
    bssid = data.get('bssid')
    device_id = data.get('device_id')

    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400

    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404

        active_device = server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        )
        if not active_device:
            return jsonify({'error': 'Unauthorized device'}), 403

        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )

        # Record checkin
        existing_checkin = server.db.fetch_one(
            'SELECT 1 FROM checkins WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        )
        
        if existing_checkin:
            server.db.execute(
                'UPDATE checkins SET timestamp = %s, bssid = %s WHERE student_id = %s AND device_id = %s',
                (datetime.now().isoformat(), bssid, student_id, device_id),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO checkins (student_id, timestamp, bssid, device_id) VALUES (%s, %s, %s, %s)',
                (student_id, datetime.now().isoformat(), bssid, device_id),
                commit=True
            )

        # Get authorized BSSID for student's classroom
        student = server.db.fetch_one('SELECT classroom FROM students WHERE id = %s', (student_id,))
        classroom = student['classroom']
        
        teacher = server.db.fetch_one(
            'SELECT bssid_mapping FROM teachers WHERE classrooms::jsonb ? %s',
            (classroom,)
        )
        
        authorized_bssid = None
        if teacher:
            bssid_mapping = json.loads(teacher['bssid_mapping'])
            authorized_bssid = bssid_mapping.get(classroom)

        if bssid and bssid == authorized_bssid:
            server.start_timer(student_id)

        return jsonify({
            'message': 'Check-in successful',
            'status': 'present' if bssid and bssid == authorized_bssid else 'absent',
            'authorized_bssid': authorized_bssid
        }), 200

@app.route('/student/timer/start', methods=['POST'])
def student_start_timer():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')

    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400

    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404

        if not server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        ):
            return jsonify({'error': 'Unauthorized device'}), 403

        # Check authorization via latest checkin
        checkin = server.db.fetch_one(
            'SELECT * FROM checkins WHERE student_id = %s ORDER BY timestamp DESC LIMIT 1',
            (student_id,)
        )

        # Get authorized BSSID for student's classroom
        student = server.db.fetch_one('SELECT classroom FROM students WHERE id = %s', (student_id,))
        classroom = student['classroom']
        
        teacher = server.db.fetch_one(
            'SELECT bssid_mapping FROM teachers WHERE classrooms::jsonb ? %s',
            (classroom,)
        )
        
        authorized_bssid = None
        if teacher:
            bssid_mapping = json.loads(teacher['bssid_mapping'])
            authorized_bssid = bssid_mapping.get(classroom)

        if not checkin or checkin['bssid'] != authorized_bssid:
            return jsonify({'error': 'Not authorized to start timer - BSSID mismatch'}), 403

        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )

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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        if not server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        ):
            return jsonify({'error': 'Unauthorized device'}), 403
        
        timer = server.db.fetch_one('SELECT * FROM timers WHERE student_id = %s', (student_id,))
        if not timer or timer['status'] == 'stop':
            return jsonify({'error': 'No active timer to stop'}), 400
        
        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        if timer['status'] == 'running':
            server.record_attendance(student_id)
        
        server.db.execute(
            'UPDATE timers SET status = %s, remaining = 0 WHERE student_id = %s',
            ('stop', student_id),
            commit=True
        )
        
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        if not server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        ):
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        # Get checkin
        checkin = server.db.fetch_one(
            'SELECT * FROM checkins WHERE student_id = %s ORDER BY timestamp DESC LIMIT 1',
            (student_id,)
        )
        
        # Get timer
        timer = server.db.fetch_one('SELECT * FROM timers WHERE student_id = %s', (student_id,))
        
        authorized_bssid = server.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid']
        is_authorized = checkin and checkin['bssid'] == authorized_bssid
        
        status = {
            'student_id': student_id,
            'name': server.db.fetch_one('SELECT name FROM students WHERE id = %s', (student_id,))['name'],
            'classroom': server.db.fetch_one('SELECT classroom FROM students WHERE id = %s', (student_id,))['classroom'],
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

@app.route('/student/get_attendance', methods=['GET'])
def student_get_attendance():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        if not server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        ):
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        student = server.db.fetch_one('SELECT attendance FROM students WHERE id = %s', (student_id,))
        
        return jsonify({
            'attendance': json.loads(student['attendance']) if student['attendance'] else {}
        }), 200

@app.route('/student/get_active_session', methods=['GET'])
def get_active_session():
    student_id = request.args.get('student_id')
    classroom = request.args.get('classroom')
    
    if not student_id or not classroom:
        return jsonify({'error': 'Student ID and classroom are required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        session = server.db.fetch_one(
            'SELECT * FROM sessions WHERE classroom = %s AND end_time IS NULL',
            (classroom,)
        )
        
        if session:
            return jsonify({
                'active': True,
                'session': dict(session)
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404        
        timetable = server.db.fetch_one(
            'SELECT timetable FROM timetables WHERE branch = %s AND semester = %s',
            (branch, semester)
        )
        
        if timetable:
            return jsonify({
                'timetable': json.loads(timetable['timetable'])
            }), 200
        else:
            return jsonify({
                'timetable': []
            }), 200

@app.route('/student/ping', methods=['POST'])
def student_ping():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        if not server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        ):
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.db.execute(
            'UPDATE active_devices SET last_activity = %s WHERE student_id = %s',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        return jsonify({'message': 'Ping successful'}), 200

@app.route('/student/cleanup_dead_sessions', methods=['POST'])
def cleanup_dead_sessions():
    data = request.json
    student_id = data.get('student_id')
    device_id = data.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    with server.lock:
        # Only cleanup if the device matches
        device = server.db.fetch_one(
            'SELECT * FROM active_devices WHERE student_id = %s AND device_id = %s',
            (student_id, device_id)
        )
        if device:
            server.db.execute(
                'DELETE FROM active_devices WHERE student_id = %s',
                (student_id,),
                commit=True
            )
        
        server.db.execute(
            'DELETE FROM checkins WHERE student_id = %s',
            (student_id,),
            commit=True
        )
        
        server.db.execute(
            'DELETE FROM timers WHERE student_id = %s',
            (student_id,),
            commit=True
        )
    
    return jsonify({'message': 'Session cleanup completed'}), 200

if __name__ == '__main__':
    logger.info(f"Starting server on port {server.SERVER_PORT}")
    app.run(host='0.0.0.0', port=server.SERVER_PORT)
