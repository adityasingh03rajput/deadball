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
import sqlite3
import json
from contextlib import contextmanager
import queue
from functools import wraps

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
MAX_DB_CONNECTIONS = 20
CHECKIN_TIMEOUT = 5  # seconds
DB_OPERATION_TIMEOUT = 3  # seconds
MAX_CHECKIN_RATE = 60  # max checkins per minute per student

class ConnectionPool:
    def __init__(self, db_name='attendance.db', max_connections=MAX_DB_CONNECTIONS):
        self.db_name = db_name
        self.max_connections = max_connections
        self.pool = queue.Queue(max_connections)
        self._initialize_pool()
        
    def _initialize_pool(self):
        for _ in range(self.max_connections):
            conn = sqlite3.connect(self.db_name, timeout=DB_OPERATION_TIMEOUT)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            self.pool.put(conn)
    
    @contextmanager
    def get_connection(self):
        conn = self.pool.get()
        try:
            yield conn
        finally:
            self.pool.put(conn)
    
    def close_all(self):
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except queue.Empty:
                break

class DatabaseManager:
    def __init__(self, connection_pool):
        self.pool = connection_pool
        self._init_db()
        
    def _init_db(self):
        with self.pool.get_connection() as conn:
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
                    attendance TEXT,
                    locked_device_id TEXT,
                    last_checkin TEXT
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
            
            # Checkins table with optimized indexes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    bssid TEXT,
                    device_id TEXT NOT NULL,
                    FOREIGN KEY (student_id) REFERENCES students (id)
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkins_student_device 
                ON checkins (student_id, device_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkins_timestamp 
                ON checkins (timestamp)
            ''')
            
            # Timers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS timers (
                    student_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    start_time REAL,
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    holidays TEXT NOT NULL,
                    special_schedules TEXT NOT NULL
                )
            ''')
            
            # Server settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS server_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    authorized_bssid TEXT,
                    checkin_interval INTEGER NOT NULL,
                    timer_duration INTEGER NOT NULL,
                    max_checkin_rate INTEGER NOT NULL
                )
            ''')
            
            # Initialize server settings if not exists
            cursor.execute('SELECT 1 FROM server_settings LIMIT 1')
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO server_settings 
                    (authorized_bssid, checkin_interval, timer_duration, max_checkin_rate)
                    VALUES (NULL, 5, 300, ?)
                ''', (MAX_CHECKIN_RATE,))
            
            conn.commit()
    
    def execute(self, query, params=(), commit=False):
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                if commit:
                    conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                logger.error(f"Database operation timed out: {e}")
                raise
    
    def fetch_one(self, query, params=()):
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchone()
            except sqlite3.OperationalError as e:
                logger.error(f"Database operation timed out: {e}")
                raise
    
    def fetch_all(self, query, params=()):
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
            except sqlite3.OperationalError as e:
                logger.error(f"Database operation timed out: {e}")
                raise

    def execute_many(self, query, params_list):
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                logger.error(f"Database operation timed out: {e}")
                raise

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
        self.connection_pool = ConnectionPool()
        self.db = DatabaseManager(self.connection_pool)
        self.running = True
        self.checkin_lock = threading.Lock()
        
        # Load server settings
        settings = self.db.fetch_one('SELECT * FROM server_settings')
        self.CHECKIN_INTERVAL = settings['checkin_interval']
        self.TIMER_DURATION = settings['timer_duration']
        self.MAX_CHECKIN_RATE = settings['max_checkin_rate']
        self.SERVER_PORT = int(os.getenv('PORT', 5000))
        
        # Initialize with admin if not exists
        if not self.db.fetch_one('SELECT 1 FROM teachers WHERE id = ?', ('admin',)):
            self._create_admin_account()
        
        # Start background threads
        self.start_background_threads()
    
    def _create_admin_account(self):
        self.db.execute(
            'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
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
                'INSERT INTO students (id, password, name, classroom, branch, semester, attendance, locked_device_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    's001',
                    generate_password_hash('student123'),
                    'John Doe',
                    'A101',
                    'CSE',
                    3,
                    json.dumps({}),
                    None
                ),
                commit=True
            )
            self.db.execute(
                'INSERT INTO students (id, password, name, classroom, branch, semester, attendance, locked_device_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    's002',
                    generate_password_hash('student123'),
                    'Jane Smith',
                    'A101',
                    'CSE',
                    3,
                    json.dumps({}),
                    None
                ),
                commit=True
            )
            
            # Create sample timetable
            self.db.execute(
                'INSERT INTO timetables (branch, semester, timetable) VALUES (?, ?, ?)',
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
        
        logger.info("Background threads started")
    
    def update_timers(self):
        """Background thread to update all student timers"""
        while self.running:
            current_time = datetime.now().timestamp()
            
            try:
                timers = self.db.fetch_all('SELECT * FROM timers WHERE status = ?', ('running',))
                updates = []
                completions = []
                
                for timer in timers:
                    elapsed = current_time - timer['start_time']
                    remaining = max(0, timer['duration'] - elapsed)
                    
                    if remaining <= 0:
                        completions.append(timer['student_id'])
                    else:
                        updates.append((remaining, timer['student_id']))
                
                # Batch update remaining times
                if updates:
                    self.db.execute_many(
                        'UPDATE timers SET remaining = ? WHERE student_id = ?',
                        updates
                    )
                
                # Process completions
                for student_id in completions:
                    self.db.execute(
                        'UPDATE timers SET status = ?, remaining = ? WHERE student_id = ?',
                        ('completed', 0, student_id),
                        commit=True
                    )
                    self.record_attendance(student_id)
                
            except Exception as e:
                logger.error(f"Error in timer update thread: {e}")
            
            time.sleep(1)
    
    def record_attendance(self, student_id):
        """Record attendance for completed timer"""
        try:
            student = self.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
            if not student:
                return
            
            timer = self.db.fetch_one('SELECT * FROM timers WHERE student_id = ?', (student_id,))
            if not timer or timer['status'] != 'completed':
                return
            
            # Check authorization
            checkin = self.db.fetch_one(
                '''SELECT * FROM checkins 
                WHERE student_id = ? 
                ORDER BY timestamp DESC LIMIT 1''',
                (student_id,)
            )
            
            authorized_bssid = self.db.fetch_one(
                'SELECT authorized_bssid FROM server_settings'
            )['authorized_bssid']
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
                'UPDATE students SET attendance = ? WHERE id = ?',
                (json.dumps(attendance), student_id),
                commit=True
            )
        except Exception as e:
            logger.error(f"Error recording attendance: {e}")
    
    def cleanup_checkins(self):
        """Background thread to clean up old checkins"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=10)).isoformat()
            
            try:
                self.db.execute(
                    'DELETE FROM checkins WHERE timestamp < ?',
                    (threshold,),
                    commit=True
                )
            except Exception as e:
                logger.error(f"Error cleaning up checkins: {e}")
            
            time.sleep(60)
    
    def cleanup_active_devices(self):
        """Background thread to clean up inactive devices"""
        while self.running:
            threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            try:
                inactive_devices = self.db.fetch_all(
                    'SELECT student_id FROM active_devices WHERE last_activity < ?',
                    (threshold,)
                )
                
                # Batch delete operations
                if inactive_devices:
                    student_ids = [d['student_id'] for d in inactive_devices]
                    
                    # Update students
                    self.db.execute(
                        'UPDATE students SET locked_device_id = NULL WHERE id IN (%s)' % 
                        ','.join(['?']*len(student_ids)),
                        student_ids,
                        commit=True
                    )
                    
                    # Delete from active_devices
                    self.db.execute(
                        'DELETE FROM active_devices WHERE student_id IN (%s)' % 
                        ','.join(['?']*len(student_ids)),
                        student_ids,
                        commit=True
                    )
                    
                    # Delete checkins
                    self.db.execute(
                        'DELETE FROM checkins WHERE student_id IN (%s)' % 
                        ','.join(['?']*len(student_ids)),
                        student_ids,
                        commit=True
                    )
                    
                    # Delete timers
                    self.db.execute(
                        'DELETE FROM timers WHERE student_id IN (%s)' % 
                        ','.join(['?']*len(student_ids)),
                        student_ids,
                        commit=True
                    )
                    
            except Exception as e:
                logger.error(f"Error cleaning up devices: {e}")
            
            time.sleep(60)
    
    def start_timer(self, student_id):
        """Start timer for a student"""
        try:
            if not self.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
                return False
            
            existing_timer = self.db.fetch_one(
                'SELECT 1 FROM timers WHERE student_id = ?', 
                (student_id,)
            )
            
            if existing_timer:
                self.db.execute(
                    '''UPDATE timers 
                    SET status = ?, start_time = ?, duration = ?, remaining = ? 
                    WHERE student_id = ?''',
                    ('running', datetime.now().timestamp(), self.TIMER_DURATION, 
                     self.TIMER_DURATION, student_id),
                    commit=True
                )
            else:
                self.db.execute(
                    '''INSERT INTO timers (student_id, status, start_time, duration, remaining) 
                    VALUES (?, ?, ?, ?, ?)''',
                    (student_id, 'running', datetime.now().timestamp(), 
                     self.TIMER_DURATION, self.TIMER_DURATION),
                    commit=True
                )
            
            return True
        except Exception as e:
            logger.error(f"Error starting timer: {e}")
            return False

# Initialize the server
connection_pool = ConnectionPool()
server = AttendanceServer()

# Cleanup on exit
def cleanup():
    server.running = False
    connection_pool.close_all()
    logger.info("Server shutting down...")

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())

# Student endpoints
@app.route('/student/checkin', methods=['POST'])
@rate_limited(server.MAX_CHECKIN_RATE)
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
        student = server.db.fetch_one(
            'SELECT * FROM students WHERE id = ?', 
            (student_id,)
        )
        if not student:
            return jsonify({'error': 'Student not found'}), 404

        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403

        # Check if this is a duplicate check-in (same device within checkin interval)
        last_checkin = server.db.fetch_one(
            '''SELECT timestamp FROM checkins 
            WHERE student_id = ? AND device_id = ? 
            ORDER BY timestamp DESC LIMIT 1''',
            (student_id, device_id)
        )
        
        if last_checkin:
            last_time = datetime.fromisoformat(last_checkin['timestamp'])
            if (datetime.now() - last_time).total_seconds() < server.CHECKIN_INTERVAL * 60:
                return jsonify({
                    'message': 'Duplicate check-in ignored',
                    'status': 'present' if bssid and bssid == student.get('last_bssid') else 'absent'
                }), 200

        # Update last activity and check-in
        with server.checkin_lock:
            # Upsert active device
            server.db.execute(
                '''INSERT OR REPLACE INTO active_devices 
                (student_id, device_id, last_activity) 
                VALUES (?, ?, ?)''',
                (student_id, device_id, datetime.now().isoformat()),
                commit=True
            )

            # Record checkin
            server.db.execute(
                '''INSERT INTO checkins 
                (student_id, timestamp, bssid, device_id) 
                VALUES (?, ?, ?, ?)''',
                (student_id, datetime.now().isoformat(), bssid, device_id),
                commit=True
            )

            # Update student's last check-in time
            server.db.execute(
                'UPDATE students SET last_checkin = ? WHERE id = ?',
                (datetime.now().isoformat(), student_id),
                commit=True
            )

        # Get authorized BSSID
        authorized_bssid = server.db.fetch_one(
            'SELECT authorized_bssid FROM server_settings'
        )['authorized_bssid']

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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not check_password_hash(student['password'], password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Check if student is locked to a different device
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'This account is locked to another device'}), 403
        
        # Lock student to this device if not already locked
        if not student['locked_device_id']:
            server.db.execute(
                'UPDATE students SET locked_device_id = ? WHERE id = ?',
                (device_id, student_id),
                commit=True
            )
        
        # Update or insert active device
        existing = server.db.fetch_one(
            'SELECT 1 FROM active_devices WHERE student_id = ?',
            (student_id,)
        )
        
        if existing:
            server.db.execute(
                'UPDATE active_devices SET device_id = ?, last_activity = ? WHERE student_id = ?',
                (device_id, datetime.now().isoformat(), student_id),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO active_devices (student_id, device_id, last_activity) VALUES (?, ?, ?)',
                (student_id, device_id, datetime.now().isoformat()),
                commit=True
            )
        
        # Find BSSID by checking classroom mapping
        classroom = student['classroom']
        teacher = server.db.fetch_one(
            'SELECT bssid_mapping FROM teachers WHERE json_extract(classrooms, ?) IS NOT NULL',
            (f'$."{classroom}"',)
        )
        
        classroom_bssid = None
        if teacher:
            bssid_mapping = json.loads(teacher['bssid_mapping'])
            classroom_bssid = bssid_mapping.get(classroom)
        
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
        logger.error(f"Student login error: {str(e)}")
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

@app.route('/student/get_status', methods=['GET'])
def student_get_status():
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    
    if not all([student_id, device_id]):
        return jsonify({'error': 'Student ID and device ID are required'}), 400
    
    try:
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = ? WHERE student_id = ?',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        # Get checkin
        checkin = server.db.fetch_one(
            'SELECT * FROM checkins WHERE student_id = ? ORDER BY timestamp DESC LIMIT 1',
            (student_id,)
        )
        
        # Get timer
        timer = server.db.fetch_one('SELECT * FROM timers WHERE student_id = ?', (student_id,))
        
        authorized_bssid = server.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid']
        is_authorized = checkin and checkin['bssid'] == authorized_bssid
        
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
            'expected_bssid': authorized_bssid
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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Update last activity
        server.db.execute(
            'UPDATE active_devices SET last_activity = ? WHERE student_id = ?',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
        return jsonify({
            'attendance': json.loads(student['attendance']) if student['attendance'] else {}
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        session = server.db.fetch_one(
            'SELECT * FROM sessions WHERE classroom = ? AND end_time IS NULL',
            (classroom,)
        )
        
        if session:
            return jsonify({
                'active': True,
                'session': dict(session)
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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        timetable = server.db.fetch_one(
            'SELECT timetable FROM timetables WHERE branch = ? AND semester = ?',
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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        server.db.execute(
            'UPDATE active_devices SET last_activity = ? WHERE student_id = ?',
            (datetime.now().isoformat(), student_id),
            commit=True
        )
        
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
        student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check device binding
        if student['locked_device_id'] and student['locked_device_id'] != device_id:
            return jsonify({'error': 'Unauthorized device'}), 403
        
        # Only cleanup if the device matches
        device = server.db.fetch_one(
            'SELECT * FROM active_devices WHERE student_id = ? AND device_id = ?',
            (student_id, device_id)
        )
        if device:
            server.db.execute(
                'UPDATE students SET locked_device_id = NULL WHERE id = ?',
                (student_id,),
                commit=True
            )
            server.db.execute(
                'DELETE FROM active_devices WHERE student_id = ?',
                (student_id,),
                commit=True
            )
        
        server.db.execute(
            'DELETE FROM checkins WHERE student_id = ?',
            (student_id,),
            commit=True
        )
        
        server.db.execute(
            'DELETE FROM timers WHERE student_id = ?',
            (student_id,),
            commit=True
        )
    
        return jsonify({'message': 'Session cleanup completed'}), 200
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {str(e)}")
        return jsonify({'error': 'Cleanup failed', 'details': str(e)}), 500

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
        if server.db.fetch_one('SELECT 1 FROM teachers WHERE id = ?', (teacher_id,)):
            return jsonify({'error': 'Teacher ID already exists'}), 400
        
        if server.db.fetch_one('SELECT 1 FROM teachers WHERE email = ?', (email,)):
            return jsonify({'error': 'Email already registered'}), 400
        
        server.db.execute(
            'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
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
        teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
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
        if server.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
            return jsonify({'error': 'Student ID already exists'}), 400
        
        server.db.execute(
            'INSERT INTO students (id, password, name, classroom, branch, semester, attendance, locked_device_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                student_id,
                generate_password_hash(password),
                name,
                classroom,
                branch,
                semester,
                json.dumps({}),
                None
            ),
            commit=True
        )
        
        return jsonify({'message': 'Student registered successfully'}), 201
    except Exception as e:
        logger.error(f"Error registering student: {str(e)}")
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500

@app.route('/teacher/get_students', methods=['GET'])
def get_students():
    classroom = request.args.get('classroom')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    query = 'SELECT * FROM students'
    params = []
    conditions = []
    
    if classroom:
        conditions.append('classroom = ?')
        params.append(classroom)
    if branch:
        conditions.append('branch = ?')
        params.append(branch)
    if semester:
        conditions.append('semester = ?')
        params.append(semester)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    try:
        students = server.db.fetch_all(query, params)
        
        # Convert to list of dicts and parse attendance
        students_list = []
        for student in students:
            student_dict = dict(student)
            student_dict['attendance'] = json.loads(student_dict['attendance']) if student_dict['attendance'] else {}
            students_list.append(student_dict)
    
        return jsonify({'students': students_list}), 200
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in new_data.items():
            if key in ['name', 'classroom', 'branch', 'semester', 'locked_device_id']:
                set_clauses.append(f'{key} = ?')
                params.append(value)
            elif key == 'attendance':
                set_clauses.append('attendance = ?')
                params.append(json.dumps(value))
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        query = f'UPDATE students SET {", ".join(set_clauses)} WHERE id = ?'
        params.append(student_id)
        
        server.db.execute(query, params, commit=True)
        
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Delete all related data
        server.db.execute('DELETE FROM students WHERE id = ?', (student_id,))
        server.db.execute('DELETE FROM checkins WHERE student_id = ?', (student_id,))
        server.db.execute('DELETE FROM timers WHERE student_id = ?', (student_id,))
        server.db.execute('DELETE FROM active_devices WHERE student_id = ?', (student_id,))
        server.db.execute('DELETE FROM manual_overrides WHERE student_id = ?', (student_id,))
        server.db.commit()
        
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
        if not server.db.fetch_one('SELECT 1 FROM teachers WHERE id = ?', (teacher_id,)):
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Build update query
        set_clauses = []
        params = []
        
        for key, value in new_data.items():
            if key in ['email', 'name']:
                set_clauses.append(f'{key} = ?')
                params.append(value)
            elif key in ['classrooms', 'bssid_mapping', 'branches', 'semesters']:
                set_clauses.append(f'{key} = ?')
                params.append(json.dumps(value))
        
        if not set_clauses:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        query = f'UPDATE teachers SET {", ".join(set_clauses)} WHERE id = ?'
        params.append(teacher_id)
        
        server.db.execute(query, params, commit=True)
        
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
        teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        if not check_password_hash(teacher['password'], old_password):
            return jsonify({'error': 'Incorrect current password'}), 401
        
        server.db.execute(
            'UPDATE teachers SET password = ? WHERE id = ?',
            (generate_password_hash(new_password), teacher_id),
            commit=True
        )
        
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
        teacher = server.db.fetch_one('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404        
        # Get current bssid_mapping
        bssid_mapping = json.loads(teacher['bssid_mapping'])
        
        # Update the mapping
        bssid_mapping[classroom] = bssid
        
        # Update teacher record
        server.db.execute(
            'UPDATE teachers SET bssid_mapping = ? WHERE id = ?',
            (json.dumps(bssid_mapping), teacher_id),
            commit=True
        )
        
        # Add classroom to teacher's classrooms if not present
        classrooms = json.loads(teacher['classrooms'])
        if classroom not in classrooms:
            classrooms.append(classroom)
            server.db.execute(
                'UPDATE teachers SET classrooms = ? WHERE id = ?',
                (json.dumps(classrooms), teacher_id),
                commit=True
            )
        
        # Update authorized BSSID if it matches this classroom's previous BSSID
        settings = server.db.fetch_one('SELECT authorized_bssid FROM server_settings')
        if settings['authorized_bssid'] == bssid_mapping.get(classroom):
            server.db.execute(
                'UPDATE server_settings SET authorized_bssid = ?',
                (bssid,),
                commit=True
            )
        
        return jsonify({
            'message': 'BSSID mapping updated successfully',
            'bssid_mapping': bssid_mapping
        }), 200
    except Exception as e:
        logger.error(f"Error updating BSSID mapping: {str(e)}")
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500

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
        if not server.db.fetch_one('SELECT 1 FROM teachers WHERE id = ?', (teacher_id,)):
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Check for existing active session in this classroom
        active_session = server.db.fetch_one(
            'SELECT 1 FROM sessions WHERE classroom = ? AND end_time IS NULL',
            (classroom,)
        )
        if active_session:
            return jsonify({'error': 'There is already an active session for this classroom'}), 400
        
        session_id = str(uuid.uuid4())
        start_time = datetime.now().isoformat()
        
        server.db.execute(
            'INSERT INTO sessions (id, teacher_id, classroom, subject, branch, semester, start_time, ad_hoc) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
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
        teacher = server.db.fetch_one('SELECT bssid_mapping FROM teachers WHERE id = ?', (teacher_id,))
        bssid_mapping = json.loads(teacher['bssid_mapping'])
        authorized_bssid = bssid_mapping.get(classroom)
        
        if authorized_bssid:
            server.db.execute(
                'UPDATE server_settings SET authorized_bssid = ?',
                (authorized_bssid,),
                commit=True
            )
        
        return jsonify({
            'message': 'Session started successfully',
            'session_id': session_id,
            'authorized_bssid': authorized_bssid
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
        session = server.db.fetch_one('SELECT * FROM sessions WHERE id = ?', (session_id,))
        if not session or session['end_time']:
            return jsonify({'error': 'Session not found or already ended'}), 404
        
        end_time = datetime.now().isoformat()
        
        # Update session
        server.db.execute(
            'UPDATE sessions SET end_time = ? WHERE id = ?',
            (end_time, session_id),
            commit=True
        )
        
        # Record attendance for checked-in students
        classroom = session['classroom']
        session_start = datetime.fromisoformat(session['start_time'])
        session_end = datetime.now()
        
        checkins = server.db.fetch_all(
            'SELECT * FROM checkins WHERE student_id IN '
            '(SELECT id FROM students WHERE classroom = ?) '
            'AND timestamp BETWEEN ? AND ?',
            (classroom, session['start_time'], end_time)
        )
        
        for checkin in checkins:
            student_id = checkin['student_id']
            student = server.db.fetch_one('SELECT * FROM students WHERE id = ?', (student_id,))
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
                'UPDATE students SET attendance = ? WHERE id = ?',
                (json.dumps(attendance), student_id),
                commit=True
            )
        
        # Clear authorized BSSID
        server.db.execute(
            'UPDATE server_settings SET authorized_bssid = NULL',
            commit=True
        )
        
        return jsonify({'message': 'Session ended successfully'}), 200
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        return jsonify({'error': 'Failed to end session', 'details': str(e)}), 500

@app.route('/teacher/get_sessions', methods=['GET'])
def get_sessions():
    teacher_id = request.args.get('teacher_id')
    classroom = request.args.get('classroom')
    
    query = 'SELECT * FROM sessions'
    params = []
    conditions = []
    
    if teacher_id:
        conditions.append('teacher_id = ?')
        params.append(teacher_id)
    if classroom:
        conditions.append('classroom = ?')
        params.append(classroom)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    try:
        sessions = server.db.fetch_all(query, params)
        sessions_list = [dict(session) for session in sessions]
    
        return jsonify({'sessions': sessions_list}), 200
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        return jsonify({'error': 'Failed to get sessions', 'details': str(e)}), 500

@app.route('/teacher/get_active_sessions', methods=['GET'])
def get_active_sessions():
    teacher_id = request.args.get('teacher_id')
    
    query = 'SELECT * FROM sessions WHERE end_time IS NULL'
    params = []
    
    if teacher_id:
        query += ' AND teacher_id = ?'
        params.append(teacher_id)
    
    try:
        sessions = server.db.fetch_all(query, params)
        sessions_list = [dict(session) for session in sessions]
    
        return jsonify({'sessions': sessions_list}), 200
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
        server.db.execute(
            'UPDATE server_settings SET authorized_bssid = ?',
            (bssid,),
            commit=True
        )
    
        return jsonify({'message': 'Authorized BSSID set successfully'}), 200
    except Exception as e:
        logger.error(f"Error setting BSSID: {str(e)}")
        return jsonify({'error': 'Failed to set BSSID', 'details': str(e)}), 500

@app.route('/teacher/get_status', methods=['GET'])
def get_status():
    classroom = request.args.get('classroom')
    
    try:
        status = {
            'authorized_bssid': server.db.fetch_one('SELECT authorized_bssid FROM server_settings')['authorized_bssid'],
            'students': {}
        }
        
        query = 'SELECT * FROM students'
        params = []
        if classroom:
            query += ' WHERE classroom = ?'
            params.append(classroom)
        
        students = server.db.fetch_all(query, params)
        
        for student in students:
            student_id = student['id']
            
            # Get checkin
            checkin = server.db.fetch_one(
                'SELECT * FROM checkins WHERE student_id = ? ORDER BY timestamp DESC LIMIT 1',
                (student_id,)
            )
            
            # Get timer
            timer = server.db.fetch_one('SELECT * FROM timers WHERE student_id = ?', (student_id,))
            
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
        if not server.db.fetch_one('SELECT 1 FROM students WHERE id = ?', (student_id,)):
            return jsonify({'error': 'Student not found'}), 404
        
        # Check if override exists
        existing = server.db.fetch_one('SELECT 1 FROM manual_overrides WHERE student_id = ?', (student_id,))
        
        if existing:
            server.db.execute(
                'UPDATE manual_overrides SET status = ? WHERE student_id = ?',
                (status, student_id),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO manual_overrides (student_id, status) VALUES (?, ?)',
                (student_id, status),
                commit=True
            )
        
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
        students = server.db.fetch_all(
            'SELECT id, name, attendance FROM students WHERE classroom = ?',
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
    except Exception as e:
        logger.error(f"Error performing random ring: {str(e)}")
        return jsonify({'error': 'Failed to perform random ring', 'details': str(e)}), 500

@app.route('/teacher/get_special_dates', methods=['GET'])
def get_special_dates():
    try:
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
    except Exception as e:
        logger.error(f"Error getting special dates: {str(e)}")
        return jsonify({'error': 'Failed to get special dates', 'details': str(e)}), 500

@app.route('/teacher/update_special_dates', methods=['POST'])
def update_special_dates():
    data = request.json
    holidays = data.get('holidays', [])
    special_dates = data.get('special_dates', [])
    
    try:
        server.db.execute(
            'INSERT INTO special_dates (holidays, special_schedules) VALUES (?, ?)',
            (json.dumps(holidays), json.dumps(special_dates)),
            commit=True
        )
    
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
        timetable = server.db.fetch_one(
            'SELECT timetable FROM timetables WHERE branch = ? AND semester = ?',
            (branch, semester)
        )
        
        if timetable:
            return jsonify({'timetable': json.loads(timetable['timetable'])}), 200
        else:
            return jsonify({'timetable': []}), 200
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
        existing = server.db.fetch_one(
            'SELECT 1 FROM timetables WHERE branch = ? AND semester = ?',
            (branch, semester)
        )
        
        if existing:
            server.db.execute(
                'UPDATE timetables SET timetable = ? WHERE branch = ? AND semester = ?',
                (json.dumps(timetable), branch, semester),
                commit=True
            )
        else:
            server.db.execute(
                'INSERT INTO timetables (branch, semester, timetable) VALUES (?, ?, ?)',
                (branch, semester, json.dumps(timetable)),
                commit=True
            )
    
        return jsonify({'message': 'Timetable updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error updating timetable: {str(e)}")
        return jsonify({'error': 'Failed to update timetable', 'details': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"Starting server on port {server.SERVER_PORT}")
    app.run(host='0.0.0.0', port=server.SERVER_PORT)
