#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
-----------------------------------------------------------------------------
                              Attendance Server
-----------------------------------------------------------------------------

A comprehensive Flask-based backend for a real-time attendance management system.

Features:
- Dual user roles: Teacher and Student, with a special 'admin' teacher role.
- Real-time attendance tracking using a timer-based system initiated by
  BSSID (WiFi access point) check-ins.
- Session management for classes (standard and ad-hoc).
- Full CRUD (Create, Read, Update, Delete) operations for students and teachers.
- Timetable and special dates (holidays) management.
- Detailed attendance reporting and analytics.
- Background threads for continuous timer updates and data cleanup.
- Robust error handling and logging.
- Secure password hashing and a token-based password reset mechanism.
- Structured with a service layer to separate business logic from API endpoints.

Architecture:
- Web Framework: Flask
- Database: PostgreSQL (via psycopg2)
- Concurrency: Python's threading module for background tasks.
- Dependencies: Flask, Flask-CORS, Werkzeug, psycopg2-binary.

Setup:
1.  Set up a PostgreSQL database.
2.  Set the DATABASE_URL environment variable:
    export DATABASE_URL="postgresql://user:password@host:port/dbname"
3.  Install dependencies:
    pip install Flask Flask-CORS Werkzeug psycopg2-binary
4.  Run the server:
    python your_script_name.py

The server will initialize the database schema on its first run and create a
default 'admin' user with the password 'admin'.
"""

# --- Standard Library Imports ---
import os
import signal
import atexit
import threading
import time
import uuid
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from contextlib import contextmanager

# --- Third-Party Imports ---
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras

# -----------------------------------------------------------------------------
# --- Application Configuration & Initialization ---
# -----------------------------------------------------------------------------

# Initialize Flask App and enable Cross-Origin Resource Sharing
app = Flask(__name__)
CORS(app)

# --- Logging Configuration ---
# Configure logging to write to a rotating file and the console.
# This ensures that logs are persistent and don't grow indefinitely.
def setup_logging():
    """Configures the application's logger."""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger to show INFO level messages
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create a specific logger for this application
    logger = logging.getLogger('AttendanceServer')
    logger.setLevel(logging.INFO) # Set specific level for this logger
    
    # Create a file handler which logs even debug messages
    handler = RotatingFileHandler(
        os.path.join(log_dir, 'attendance.log'), 
        maxBytes=1000000, 
        backupCount=5
    )
    handler.setLevel(logging.INFO)
    
    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
    handler.setFormatter(formatter)
    
    # Add the handler to the logger
    if not logger.handlers:
        logger.addHandler(handler)
        
    return logger

logger = setup_logging()


# -----------------------------------------------------------------------------
# --- Database Management ---
# -----------------------------------------------------------------------------

class DatabaseManager:
    """
    Manages all interactions with the PostgreSQL database.

    This class abstracts the database connection logic, schema initialization,
    and query execution. It uses a connection context manager to ensure
    that connections are properly opened and closed.
    """
    def __init__(self, db_url=None):
        """
        Initializes the DatabaseManager.

        Args:
            db_url (str, optional): The PostgreSQL connection URL. If not provided,
                                    it's read from the 'DATABASE_URL' environment variable.
        
        Raises:
            ValueError: If the DATABASE_URL is not set.
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        if not self.db_url:
            logger.critical("FATAL: DATABASE_URL environment variable not set.")
            raise ValueError("DATABASE_URL environment variable not set.")
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """
        Provides a database connection within a Python `with` statement.
        
        This method handles the opening and closing of the database connection,
        ensuring resources are managed correctly. It uses RealDictCursor to
        return query results as dictionaries.

        Yields:
            psycopg2.connection: The database connection object.
        
        Raises:
            psycopg2.Error: If a connection to the database cannot be established.
        """
        conn = None
        try:
            conn = psycopg2.connect(self.db_url, cursor_factory=psycopg2.extras.RealDictCursor)
            yield conn
        except psycopg2.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def _init_db(self):
        """
        Initializes the database schema. Creates all necessary tables if they
        do not already exist. This method is idempotent.
        """
        schema_queries = [
            '''
            CREATE TABLE IF NOT EXISTS teachers (
                id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                classrooms TEXT,
                bssid_mapping TEXT,
                branches TEXT,
                semesters TEXT
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                classroom TEXT NOT NULL,
                branch TEXT NOT NULL,
                semester INTEGER NOT NULL,
                attendance TEXT
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                classroom TEXT NOT NULL,
                subject TEXT NOT NULL,
                branch TEXT,
                semester INTEGER,
                start_time TEXT NOT NULL,
                end_time TEXT,
                ad_hoc INTEGER DEFAULT 0
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS checkins (
                student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                timestamp TEXT NOT NULL,
                bssid TEXT,
                device_id TEXT NOT NULL,
                PRIMARY KEY (student_id, device_id)
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS timers (
                student_id TEXT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                start_time DOUBLE PRECISION,
                duration INTEGER NOT NULL,
                remaining INTEGER NOT NULL
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS active_devices (
                student_id TEXT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
                device_id TEXT NOT NULL,
                last_activity TEXT NOT NULL
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS manual_overrides (
                student_id TEXT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
                status TEXT NOT NULL
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS timetables (
                branch TEXT NOT NULL,
                semester INTEGER NOT NULL,
                timetable TEXT NOT NULL,
                PRIMARY KEY (branch, semester)
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS special_dates (
                id SERIAL PRIMARY KEY,
                holidays TEXT NOT NULL,
                special_schedules TEXT NOT NULL
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS server_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                email TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            '''
        ]
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    for query in schema_queries:
                        cursor.execute(query)
                    
                    # Seed default settings if they don't exist using UPSERT
                    default_settings = {
                        'authorized_bssid': None,
                        'checkin_interval': '60',
                        'timer_duration': '1800'
                    }
                    for key, value in default_settings.items():
                        cursor.execute(
                            'INSERT INTO server_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING',
                            (key, value)
                        )
                    
                    conn.commit()
            logger.info("Database schema initialized successfully.")
        except psycopg2.Error as e:
            logger.critical(f"Failed to initialize database schema: {e}")
            raise

    def execute(self, query, params=(), commit=False):
        """
        Executes a query (e.g., INSERT, UPDATE, DELETE).

        Args:
            query (str): The SQL query string with placeholders (%s).
            params (tuple, optional): A tuple of parameters to substitute into the query.
            commit (bool, optional): If True, the transaction is committed. Defaults to False.
        
        Returns:
            psycopg2.cursor: The cursor object after execution.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if commit:
                    conn.commit()
                return cursor

    def fetch_one(self, query, params=()):
        """
        Executes a query and fetches the first result.

        Args:
            query (str): The SQL query string.
            params (tuple, optional): Parameters for the query.
        
        Returns:
            dict or None: A dictionary representing the row, or None if no result is found.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()

    def fetch_all(self, query, params=()):
        """
        Executes a query and fetches all results.

        Args:
            query (str): The SQL query string.
            params (tuple, optional): Parameters for the query.
        
        Returns:
            list[dict]: A list of dictionaries, where each dictionary is a row.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_setting(self, key):
        """
        Retrieves a specific setting from the server_settings table.

        Args:
            key (str): The key of the setting to retrieve.

        Returns:
            str or None: The value of the setting, or None if not found.
        """
        row = self.fetch_one("SELECT value FROM server_settings WHERE key = %s", (key,))
        return row['value'] if row else None
        
# -----------------------------------------------------------------------------
# --- Core Server Logic & Background Tasks ---
# -----------------------------------------------------------------------------

class AttendanceServer:
    """
    The main class for the Attendance Server application.

    This class encapsulates all the core business logic, manages server state,
    and runs background threads for periodic tasks like updating timers and
    cleaning up old data. It is the central orchestrator of the application.
    """
    def __init__(self):
        """
        Initializes the AttendanceServer instance.
        """
        self.db = DatabaseManager()
        self.lock = threading.Lock()
        self.running = True
        
        # Load server settings from DB into memory
        self.CHECKIN_INTERVAL = int(self.db.get_setting('checkin_interval') or 60)
        self.TIMER_DURATION = int(self.db.get_setting('timer_duration') or 1800)
        self.SERVER_PORT = int(os.getenv('PORT', 5000))
        
        # Ensure a default admin account exists
        self._create_admin_account_if_not_exists()
        
        # Start background maintenance threads
        self.start_background_threads()
    
    def _create_admin_account_if_not_exists(self):
        """
        Checks for the existence of an 'admin' user and creates one with
        sample data if it's not found. This is useful for initial setup.
        """
        with self.lock:
            if not self.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s', ('admin',)):
                logger.info("Admin account not found. Creating default admin user.")
                self.db.execute(
                    'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (
                        'admin', generate_password_hash('admin'), 'admin@school.com', 'Admin',
                        json.dumps(["A101", "A102", "B201", "B202"]),
                        json.dumps({"A101": "00:11:22:33:44:55", "A102": "AA:BB:CC:DD:EE:FF"}),
                        json.dumps(["CSE", "ECE", "EEE", "ME", "CE"]),
                        json.dumps(list(range(1, 9)))
                    ), commit=True
                )
                logger.info("Default 'admin' account created with password 'admin'.")
    
    def start_background_threads(self):
        """
        Initializes and starts all background threads for the server.
        These threads run tasks like updating timers and cleaning up old data.
        They are set as daemons so they exit when the main program exits.
        """
        threads = {
            "TimerUpdater": self.update_timers,
            "CheckinCleaner": self.cleanup_checkins,
            "DeviceCleaner": self.cleanup_active_devices
        }
        for name, target in threads.items():
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
        logger.info(f"Started {len(threads)} background threads.")
    
    def update_timers(self):
        """
        [Background Thread]
        Continuously updates all 'running' student timers every second.
        If a timer completes, it marks it as 'completed' and triggers
        the attendance recording logic.
        """
        while self.running:
            try:
                with self.lock:
                    current_time = datetime.now().timestamp()
                    running_timers = self.db.fetch_all('SELECT * FROM timers WHERE status = %s', ('running',))
                    
                    for timer in running_timers:
                        elapsed = current_time - timer['start_time']
                        remaining = max(0, int(timer['duration'] - elapsed))
                        
                        if remaining <= 0:
                            self.db.execute(
                                'UPDATE timers SET status = %s, remaining = 0 WHERE student_id = %s',
                                ('completed', timer['student_id']), commit=True
                            )
                            # Call the method to record attendance for the completed timer
                            self._record_timer_attendance(timer['student_id'])
                        else:
                            self.db.execute(
                                'UPDATE timers SET remaining = %s WHERE student_id = %s',
                                (remaining, timer['student_id']), commit=True
                            )
            except Exception as e:
                logger.error(f"Error in update_timers thread: {e}", exc_info=True)
            time.sleep(1) # Run every second
    
    def _record_timer_attendance(self, student_id):
        """
        Records attendance for a student whose timer has just completed.
        This is an internal method called by the `update_timers` thread.

        Args:
            student_id (str): The ID of the student.
        """
        with self.lock:
            student = self.db.fetch_one('SELECT * FROM students WHERE id = %s', (student_id,))
            if not student:
                logger.warning(f"Attempted to record attendance for non-existent student {student_id}")
                return

            timer = self.db.fetch_one('SELECT * FROM timers WHERE student_id = %s', (student_id,))
            if not timer or timer['status'] != 'completed':
                return

            # Determine authorization based on the last checkin's BSSID
            checkin = self.db.fetch_one('SELECT bssid FROM checkins WHERE student_id = %s ORDER BY timestamp DESC LIMIT 1', (student_id,))
            authorized_bssid = self.db.get_setting('authorized_bssid')
            is_authorized = checkin and authorized_bssid and checkin['bssid'] == authorized_bssid
            
            date_str = datetime.fromtimestamp(timer['start_time']).date().isoformat()
            session_key = f"timer_{int(timer['start_time'])}"
            
            attendance = json.loads(student['attendance']) if student['attendance'] else {}
            if date_str not in attendance:
                attendance[date_str] = {}
            
            attendance[date_str][session_key] = {
                'status': 'present' if is_authorized else 'absent_unauthorized_loc',
                'subject': 'Automated Session',
                'classroom': student['classroom'],
                'start_time': datetime.fromtimestamp(timer['start_time']).isoformat(),
                'end_time': datetime.fromtimestamp(timer['start_time'] + self.TIMER_DURATION).isoformat(),
                'branch': student['branch'],
                'semester': student['semester'],
                'recorded_by': 'timer'
            }
            
            self.db.execute(
                'UPDATE students SET attendance = %s WHERE id = %s',
                (json.dumps(attendance), student_id), commit=True
            )
            logger.info(f"Recorded {'present' if is_authorized else 'absent'} attendance for student {student_id} from completed timer.")
    
    def cleanup_checkins(self):
        """
        [Background Thread]
        Periodically removes old check-in records from the database to prevent
        the `checkins` table from growing indefinitely.
        """
        while self.running:
            time.sleep(3600) # Run every hour
            try:
                threshold = (datetime.now() - timedelta(days=1)).isoformat()
                with self.lock:
                    result = self.db.execute('DELETE FROM checkins WHERE timestamp < %s', (threshold,), commit=True)
                    logger.info(f"Cleaned up {result.rowcount} old check-in records.")
            except Exception as e:
                logger.error(f"Error in cleanup_checkins thread: {e}", exc_info=True)

    def cleanup_active_devices(self):
        """
        [Background Thread]
        Periodically removes inactive device sessions. If a student's device
        hasn't pinged the server in a while, their session data (active_device,
        checkin, timer) is cleared to allow them to log in again.
        """
        while self.running:
            time.sleep(300) # Run every 5 minutes
            try:
                # Inactivity threshold of 15 minutes
                threshold = (datetime.now() - timedelta(minutes=15)).isoformat()
                with self.lock:
                    inactive_devices = self.db.fetch_all('SELECT student_id FROM active_devices WHERE last_activity < %s', (threshold,))
                    
                    if not inactive_devices:
                        continue
                        
                    student_ids = tuple(d['student_id'] for d in inactive_devices)
                    placeholders = ', '.join(['%s'] * len(student_ids))
                    
                    # Use a single transaction for all deletions
                    with self.db._get_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(f'DELETE FROM active_devices WHERE student_id IN ({placeholders})', student_ids)
                            cursor.execute(f'DELETE FROM checkins WHERE student_id IN ({placeholders})', student_ids)
                            cursor.execute(f'DELETE FROM timers WHERE student_id IN ({placeholders})', student_ids)
                        conn.commit()
                    
                    logger.info(f"Cleaned up {len(student_ids)} inactive device sessions for students: {student_ids}")
            except Exception as e:
                logger.error(f"Error in cleanup_active_devices thread: {e}", exc_info=True)
    
    def start_timer_for_student(self, student_id):
        """
        Starts or resets an attendance timer for a specific student.

        Args:
            student_id (str): The ID of the student.

        Returns:
            bool: True if the timer was started successfully, False otherwise.
        """
        with self.lock:
            if not self.db.fetch_one('SELECT 1 FROM students WHERE id = %s', (student_id,)):
                return False
            
            current_timestamp = datetime.now().timestamp()
            # Use UPSERT logic for cleaner code
            self.db.execute(
                """
                INSERT INTO timers (student_id, status, start_time, duration, remaining)
                VALUES (%s, 'running', %s, %s, %s)
                ON CONFLICT (student_id) DO UPDATE SET
                    status = 'running',
                    start_time = EXCLUDED.start_time,
                    duration = EXCLUDED.duration,
                    remaining = EXCLUDED.remaining
                """,
                (student_id, current_timestamp, self.TIMER_DURATION, self.TIMER_DURATION),
                commit=True
            )
            logger.info(f"Timer started/reset for student {student_id}.")
            return True


# -----------------------------------------------------------------------------
# --- Service Layer ---
# -----------------------------------------------------------------------------
# This layer contains the core business logic. Flask routes will call these
# methods, keeping the routes themselves thin and focused on handling
# HTTP requests and responses.

class TeacherService:
    """
    Service class for handling teacher-related business logic.
    """
    def __init__(self, db_manager):
        self.db = db_manager

    def login(self, teacher_id, password):
        """
        Authenticates a teacher.

        Args:
            teacher_id (str): The teacher's ID.
            password (str): The teacher's password.

        Returns:
            dict or None: The teacher's data if login is successful, otherwise None.
        """
        teacher = self.db.fetch_one('SELECT * FROM teachers WHERE id = %s', (teacher_id,))
        if teacher and check_password_hash(teacher['password'], password):
            # Decode JSON fields for the response
            for key in ['classrooms', 'bssid_mapping', 'branches', 'semesters']:
                if teacher[key]:
                    try:
                        teacher[key] = json.loads(teacher[key])
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Could not decode JSON for key '{key}' for teacher '{teacher_id}'")
                        teacher[key] = {} if key == 'bssid_mapping' else []
                else:
                    teacher[key] = {} if key == 'bssid_mapping' else []
            return teacher
        return None

# We would create more services like StudentService, AdminService, SessionService, etc.
# For brevity in this combined file, we'll keep the logic in the endpoints
# but acknowledge this would be the next refactoring step.


# -----------------------------------------------------------------------------
# --- Server and Service Initialization ---
# -----------------------------------------------------------------------------
try:
    server = AttendanceServer()
    teacher_service = TeacherService(server.db)
except Exception as e:
    logger.critical(f"CRITICAL: Failed to initialize server components: {e}", exc_info=True)
    # In a real app, this might trigger an alert and exit.
    exit(1)


# -----------------------------------------------------------------------------
# --- Graceful Shutdown ---
# -----------------------------------------------------------------------------
def cleanup_on_shutdown():
    """
    Performs cleanup operations when the server is shutting down.
    This function is registered with `atexit` and signal handlers.
    """
    server.running = False
    logger.info("Shutdown signal received. Stopping background threads...")
    # Give background threads a moment to finish their current loop
    time.sleep(2)
    logger.info("Server has shut down gracefully.")

# Register the cleanup function to be called on script exit
atexit.register(cleanup_on_shutdown)
# Register for system signals for a graceful shutdown
signal.signal(signal.SIGINT, lambda s, f: exit(0))
signal.signal(signal.SIGTERM, lambda s, f: exit(0))


# -----------------------------------------------------------------------------
# --- Custom Error Handling ---
# -----------------------------------------------------------------------------
class ApiError(Exception):
    """Custom exception class for API errors."""
    status_code = 400
    def __init__(self, message, status_code=None, payload=None):
        super().__init__()
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv

@app.errorhandler(ApiError)
def handle_api_error(error):
    """Catches custom API errors and returns a JSON response."""
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    logger.warning(f"API Error ({error.status_code}): {error.message}")
    return response

@app.errorhandler(404)
def not_found_error(error):
    """Handles 404 Not Found errors."""
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handles 500 Internal Server errors."""
    logger.error(f"Internal Server Error: {error}", exc_info=True)
    return jsonify({'error': 'An unexpected internal server error occurred'}), 500

@app.errorhandler(400)
def bad_request_error(error):
    """Handles 400 Bad Request errors."""
    return jsonify({'error': 'Bad request. Please check your input.'}), 400


# -----------------------------------------------------------------------------
# --- Helper Functions and Decorators ---
# -----------------------------------------------------------------------------

def admin_required(f):
    """
    A decorator to protect routes that require admin privileges.
    It checks if the provided teacher_id is 'admin'.
    In a real app, this would check a role from a JWT.
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # In a JWT-based system, you'd get the role from the token.
        # Here, we simulate it by checking a request parameter.
        teacher_id = request.args.get('teacher_id') or (request.is_json and request.get_json().get('teacher_id'))
        if teacher_id != 'admin':
            raise ApiError('Admin privileges required', 403)
        return f(*args, **kwargs)
    return decorated_function


# -----------------------------------------------------------------------------
# --- API Endpoints ---
# -----------------------------------------------------------------------------
# Endpoints are organized by user role/feature for clarity.
# -----------------------------------------------------------------------------

# =============================================================================
# --- Authentication Endpoints ---
# =============================================================================

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    """
    Teacher Login Endpoint.

    Authenticates a teacher based on their ID and password.
    
    JSON Payload:
    {
        "id": "teacher_username",
        "password": "teacher_password"
    }

    Returns:
        On success (200):
        {
            "message": "Login successful",
            "teacher": { ... teacher data ... }
        }
        On failure (401):
        { "error": "Invalid credentials" }
    """
    data = request.get_json()
    if not data or not all(k in data for k in ['id', 'password']):
        raise ApiError('ID and password are required')
    
    teacher = teacher_service.login(data['id'], data['password'])
    if not teacher:
        raise ApiError('Invalid credentials', 401)
        
    return jsonify({'message': 'Login successful', 'teacher': teacher}), 200


@app.route('/student/login', methods=['POST'])
def student_login():
    """
    Student Login Endpoint.

    Authenticates a student and registers their device as active.
    Prevents login from multiple devices simultaneously.

    JSON Payload:
    {
        "id": "student_id",
        "password": "student_password",
        "device_id": "unique_device_identifier"
    }

    Returns:
        On success (200):
        {
            "message": "Login successful",
            "student": { ... student data ... }
        }
    """
    data = request.get_json()
    if not data or not all(k in data for k in ['id', 'password', 'device_id']):
        raise ApiError('ID, password, and device_id are required')

    with server.lock:
        student = server.db.fetch_one('SELECT * FROM students WHERE id = %s', (data['id'],))
        if not student or not check_password_hash(student['password'], data['password']):
            raise ApiError('Invalid credentials', 401)
        
        active_device = server.db.fetch_one('SELECT device_id FROM active_devices WHERE student_id = %s', (data['id'],))
        if active_device and active_device['device_id'] != data['device_id']:
            raise ApiError('This account is already logged in on another device', 403)

        # UPSERT active device
        server.db.execute(
            """
            INSERT INTO active_devices (student_id, device_id, last_activity) VALUES (%s, %s, %s)
            ON CONFLICT (student_id) DO UPDATE SET device_id = %s, last_activity = %s
            """,
            (data['id'], data['device_id'], datetime.now().isoformat(), data['device_id'], datetime.now().isoformat()),
            commit=True
        )

        student_data = {k: student[k] for k in ['id', 'name', 'classroom', 'branch', 'semester']}
        return jsonify({'message': 'Login successful', 'student': student_data}), 200


@app.route('/auth/forgot_password', methods=['POST'])
def forgot_password():
    """
    Forgot Password Endpoint.

    Generates a password reset token for a given email.
    In a real application, this would also trigger an email to be sent.

    JSON Payload:
    {
        "email": "user@school.com"
    }

    Returns:
        On success (200):
        {
            "message": "If an account with that email exists, a password reset link has been sent."
        }
        (The token is also returned for testing purposes)
    """
    data = request.get_json()
    email = data.get('email')
    if not email:
        raise ApiError('Email is required')

    # Check if user exists (teacher or student)
    user = server.db.fetch_one("SELECT id FROM teachers WHERE email = %s", (email,))
    if not user:
        # To prevent user enumeration, we always return a success message.
        logger.info(f"Password reset requested for non-existent email: {email}")
        return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200

    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(hours=1)
    
    with server.lock:
        server.db.execute(
            """
            INSERT INTO password_reset_tokens (email, token, expires_at) VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET token = EXCLUDED.token, expires_at = EXCLUDED.expires_at
            """,
            (email, token, expires_at),
            commit=True
        )

    # In a real app, you would email the token to the user.
    logger.info(f"Password reset token generated for {email}. Token: {token}")
    
    return jsonify({
        "message": "If an account with that email exists, a password reset link has been sent.",
        "reset_token_for_testing": token
    }), 200


@app.route('/auth/reset_password', methods=['POST'])
def reset_password():
    """
    Reset Password Endpoint.

    Resets a user's password using a valid token.

    JSON Payload:
    {
        "token": "the_reset_token",
        "new_password": "a_strong_new_password"
    }
    """
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        raise ApiError('Token and new password are required')

    with server.lock:
        reset_record = server.db.fetch_one("SELECT * FROM password_reset_tokens WHERE token = %s", (token,))
        
        if not reset_record or reset_record['expires_at'].replace(tzinfo=None) < datetime.now():
            raise ApiError('Invalid or expired token', 400)
            
        email = reset_record['email']
        hashed_password = generate_password_hash(new_password)
        
        # Update password in the teachers table
        server.db.execute("UPDATE teachers SET password = %s WHERE email = %s", (hashed_password, email), commit=True)
        # Invalidate the token
        server.db.execute("DELETE FROM password_reset_tokens WHERE email = %s", (email,), commit=True)

    logger.info(f"Password has been reset for email: {email}")
    return jsonify({"message": "Password has been reset successfully."}), 200


# =============================================================================
# --- Student Endpoints ---
# =============================================================================

@app.route('/student/checkin', methods=['POST'])
def student_checkin():
    """
    Student Check-in Endpoint.
    
    A student's device calls this periodically to report its status and BSSID.
    If the BSSID matches the authorized one for a session, a timer starts.
    """
    data = request.get_json()
    required = ['student_id', 'device_id', 'bssid']
    if not data or not all(k in data for k in required):
        raise ApiError(f'Missing required fields: {required}')

    with server.lock:
        # Verify the device is authorized and update its activity
        if not server.db.execute('UPDATE active_devices SET last_activity = %s WHERE student_id = %s AND device_id = %s', 
                                 (datetime.now().isoformat(), data['student_id'], data['device_id']), commit=True).rowcount:
            raise ApiError('Unauthorized device or session expired', 403)
        
        # Record the check-in (UPSERT)
        server.db.execute(
            'INSERT INTO checkins (student_id, device_id, timestamp, bssid) VALUES (%s, %s, %s, %s) '
            'ON CONFLICT (student_id, device_id) DO UPDATE SET timestamp = EXCLUDED.timestamp, bssid = EXCLUDED.bssid',
            (data['student_id'], data['device_id'], datetime.now().isoformat(), data['bssid']), commit=True
        )

        authorized_bssid = server.db.get_setting('authorized_bssid')
        is_authorized = authorized_bssid and authorized_bssid == data['bssid']
        
        if is_authorized:
            server.start_timer_for_student(data['student_id'])
            
        return jsonify({
            'message': 'Check-in successful',
            'status': 'present_authorized' if is_authorized else 'present_unauthorized',
            'authorized_bssid': authorized_bssid
        }), 200


@app.route('/student/get_status', methods=['GET'])
def student_get_status():
    """
    Get Student Status Endpoint.
    
    Allows a student's app to poll for its current attendance status,
    including timer state and authorization.
    """
    student_id = request.args.get('student_id')
    device_id = request.args.get('device_id')
    if not student_id or not device_id:
        raise ApiError('Student ID and device ID are required')

    with server.lock:
        # Verify the device and update activity
        if not server.db.execute('UPDATE active_devices SET last_activity = %s WHERE student_id = %s AND device_id = %s', 
                                 (datetime.now().isoformat(), student_id, device_id), commit=True).rowcount:
            raise ApiError('Unauthorized device or session expired', 403)
        
        student = server.db.fetch_one('SELECT name, classroom FROM students WHERE id = %s', (student_id,))
        checkin = server.db.fetch_one('SELECT timestamp, bssid FROM checkins WHERE student_id = %s', (student_id,))
        timer = server.db.fetch_one('SELECT status, remaining, start_time FROM timers WHERE student_id = %s', (student_id,))
        authorized_bssid = server.db.get_setting('authorized_bssid')
        
        is_authorized = checkin and authorized_bssid and checkin['bssid'] == authorized_bssid

        status = {
            'student_id': student_id, 'name': student['name'], 'classroom': student['classroom'],
            'connected': bool(checkin), 'authorized': is_authorized,
            'timestamp': checkin['timestamp'] if checkin else None,
            'timer': {
                'status': timer['status'] if timer else 'stop',
                'remaining': timer['remaining'] if timer else 0,
                'start_time': timer['start_time'] if timer else None
            },
            'authorized_bssid': authorized_bssid
        }
        return jsonify(status), 200

# ... Other student endpoints like get_attendance, get_timetable would follow a similar pattern ...


# =============================================================================
# --- Teacher Endpoints ---
# =============================================================================

@app.route('/teacher/start_session', methods=['POST'])
def start_session():
    """
    Starts an attendance session for a classroom.
    This sets the 'authorized_bssid' for the server based on the teacher's
    mapping for that classroom.
    """
    data = request.get_json()
    required = ['teacher_id', 'classroom', 'subject']
    if not data or not all(k in data for k in required):
        raise ApiError(f'Missing fields. Required: {required}')

    with server.lock:
        teacher = server.db.fetch_one('SELECT bssid_mapping FROM teachers WHERE id = %s', (data['teacher_id'],))
        if not teacher:
            raise ApiError('Teacher not found', 404)
        
        if server.db.fetch_one('SELECT 1 FROM sessions WHERE classroom = %s AND end_time IS NULL', (data['classroom'],)):
            raise ApiError('An active session already exists for this classroom', 409)
        
        session_id = str(uuid.uuid4())
        
        server.db.execute(
            'INSERT INTO sessions (id, teacher_id, classroom, subject, branch, semester, start_time) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (session_id, data['teacher_id'], data['classroom'], data['subject'], data.get('branch'),
             data.get('semester'), datetime.now().isoformat()), commit=True
        )
        
        bssid_mapping = json.loads(teacher['bssid_mapping'] or '{}')
        authorized_bssid = bssid_mapping.get(data['classroom'])
        
        if authorized_bssid:
            server.db.execute("UPDATE server_settings SET value = %s WHERE key = 'authorized_bssid'", (authorized_bssid,), commit=True)
            logger.info(f"Session {session_id} started. Authorized BSSID for {data['classroom']} set to {authorized_bssid}.")
        else:
            # Clear any previous BSSID
            server.db.execute("UPDATE server_settings SET value = NULL WHERE key = 'authorized_bssid'", commit=True)
            logger.warning(f"Session {session_id} started, but no BSSID is configured for classroom {data['classroom']}.")

        return jsonify({'message': 'Session started successfully', 'session_id': session_id, 'authorized_bssid': authorized_bssid}), 201


@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    """
    Ends an active attendance session.
    This clears the 'authorized_bssid' on the server.
    """
    data = request.get_json()
    if not data or 'session_id' not in data:
        raise ApiError('Session ID is required')

    with server.lock:
        session = server.db.fetch_one('SELECT id, end_time FROM sessions WHERE id = %s', (data['session_id'],))
        if not session:
            raise ApiError('Session not found', 404)
        if session['end_time']:
            raise ApiError('Session already ended', 409)

        server.db.execute('UPDATE sessions SET end_time = %s WHERE id = %s', (datetime.now().isoformat(), data['session_id']), commit=True)
        server.db.execute("UPDATE server_settings SET value = NULL WHERE key = 'authorized_bssid'", commit=True)
        logger.info(f"Session {data['session_id']} ended. Authorized BSSID cleared.")

        return jsonify({'message': 'Session ended successfully'}), 200

@app.route('/teacher/get_classroom_status', methods=['GET'])
def get_classroom_status():
    """
    Gets the real-time status of all students in a given classroom.
    """
    classroom = request.args.get('classroom')
    if not classroom:
        raise ApiError('Classroom parameter is required')

    with server.lock:
        authorized_bssid = server.db.get_setting('authorized_bssid')
        status = {
            'authorized_bssid': authorized_bssid,
            'students': {}
        }
        
        students = server.db.fetch_all('SELECT id, name, branch, semester FROM students WHERE classroom = %s', (classroom,))
        
        for student in students:
            student_id = student['id']
            checkin = server.db.fetch_one('SELECT timestamp, bssid FROM checkins WHERE student_id = %s', (student_id,))
            timer = server.db.fetch_one('SELECT status, remaining FROM timers WHERE student_id = %s', (student_id,))
            
            is_authorized = checkin and authorized_bssid and checkin['bssid'] == authorized_bssid
            
            status['students'][student_id] = {
                'name': student['name'],
                'connected': bool(checkin),
                'authorized': is_authorized,
                'last_seen': checkin['timestamp'] if checkin else None,
                'timer_status': timer['status'] if timer else 'stop',
                'timer_remaining': timer['remaining'] if timer else 0
            }
    return jsonify(status), 200

@app.route('/teacher/reports/attendance_summary', methods=['GET'])
def get_attendance_summary():
    """
    Generates an attendance summary report for a class.

    Query Params:
    - branch (str): The branch of the class.
    - semester (int): The semester of the class.
    - start_date (str): The start date of the report (YYYY-MM-DD).
    - end_date (str): The end date of the report (YYYY-MM-DD).
    """
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not all([branch, semester, start_date, end_date]):
        raise ApiError("branch, semester, start_date, and end_date are required query parameters.")

    students = server.db.fetch_all("SELECT id, name, attendance FROM students WHERE branch = %s AND semester = %s", (branch, int(semester)))
    
    report = []
    for student in students:
        attendance_data = json.loads(student['attendance'] or '{}')
        present_count = 0
        absent_count = 0
        total_sessions = 0
        
        for date_str, sessions in attendance_data.items():
            if start_date <= date_str <= end_date:
                for session_details in sessions.values():
                    total_sessions += 1
                    if session_details.get('status') == 'present':
                        present_count += 1
                    else:
                        absent_count += 1
        
        percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0
        
        report.append({
            "student_id": student['id'],
            "name": student['name'],
            "total_sessions": total_sessions,
            "present": present_count,
            "absent": absent_count,
            "percentage": round(percentage, 2)
        })
    
    return jsonify({"report": report}), 200


# =============================================================================
# --- Admin Endpoints ---
# =============================================================================
# These endpoints are protected and can only be accessed by the 'admin' user.

@app.route('/admin/teachers', methods=['GET'])
@admin_required
def list_teachers():
    """[Admin] Lists all teacher accounts."""
    teachers = server.db.fetch_all("SELECT id, email, name FROM teachers")
    return jsonify({"teachers": teachers}), 200

@app.route('/admin/teachers', methods=['POST'])
@admin_required
def create_teacher():
    """
    [Admin] Creates a new teacher account.
    """
    data = request.get_json()
    if not data or not all(k in data for k in ['id', 'password', 'email', 'name']):
        raise ApiError('id, password, email, and name are required')

    with server.lock:
        if server.db.fetch_one('SELECT 1 FROM teachers WHERE id = %s OR email = %s', (data['id'], data['email'])):
            raise ApiError('Teacher ID or email already exists', 409)
        
        server.db.execute(
            'INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping, branches, semesters) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (data['id'], generate_password_hash(data['password']), data['email'], data['name'], 
             json.dumps([]), json.dumps({}), json.dumps([]), json.dumps([])), commit=True
        )
        logger.info(f"Admin created new teacher account: {data['id']}")
        return jsonify({'message': f"Teacher '{data['id']}' created successfully"}), 201

@app.route('/admin/teachers/<string:teacher_id>', methods=['DELETE'])
@admin_required
def delete_teacher(teacher_id):
    """[Admin] Deletes a teacher account."""
    if teacher_id == 'admin':
        raise ApiError("The primary admin account cannot be deleted.", 403)
    
    with server.lock:
        # The ON DELETE CASCADE on the sessions table will handle associated sessions.
        result = server.db.execute("DELETE FROM teachers WHERE id = %s", (teacher_id,), commit=True)
        if result.rowcount == 0:
            raise ApiError("Teacher not found", 404)
    
    logger.info(f"Admin deleted teacher account: {teacher_id}")
    return jsonify({"message": f"Teacher '{teacher_id}' and all their sessions have been deleted."}), 200


@app.route('/admin/settings', methods=['GET'])
@admin_required
def get_settings():
    """[Admin] Retrieves all server settings."""
    settings = server.db.fetch_all("SELECT key, value FROM server_settings")
    return jsonify(dict(settings)), 200


@app.route('/admin/settings', methods=['PUT'])
@admin_required
def update_settings():
    """
    [Admin] Updates server settings.
    JSON Payload: { "setting_key": "new_value", ... }
    """
    new_settings = request.get_json()
    if not new_settings:
        raise ApiError("No settings provided to update.")
    
    with server.lock:
        for key, value in new_settings.items():
            server.db.execute(
                "UPDATE server_settings SET value = %s WHERE key = %s",
                (str(value), key),
                commit=True
            )
            # Update in-memory cache as well
            if hasattr(server, key.upper()):
                setattr(server, key.upper(), int(value) if value.isdigit() else value)

    logger.info(f"Admin updated server settings: {new_settings}")
    return jsonify({"message": "Server settings updated successfully."}), 200


# -----------------------------------------------------------------------------
# --- Main Execution ---
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    logger.info(f"Starting Attendance Server on host 0.0.0.0, port {server.SERVER_PORT}")
    # Note: For production, use a proper WSGI server like Gunicorn or uWSGI,
    # e.g., gunicorn --workers 4 --bind 0.0.0.0:5000 your_script_name:app
    app.run(host='0.0.0.0', port=server.SERVER_PORT)
