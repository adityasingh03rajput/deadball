from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import hashlib
import json
import os
import threading

app = Flask(__name__)
CORS(app)

# Database setup
def get_db():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        
        # Teachers table
        c.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                classrooms TEXT DEFAULT '[]',
                bssid_mapping TEXT DEFAULT '{}'
            )
        ''')
        
        # Students table
        c.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                classroom TEXT NOT NULL,
                branch TEXT NOT NULL,
                semester INTEGER NOT NULL,
                attendance TEXT DEFAULT '{}'
            )
        ''')
        
        # Sessions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                classroom TEXT NOT NULL,
                subject TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Add admin if not exists
        c.execute("SELECT id FROM teachers WHERE id = 'admin'")
        if not c.fetchone():
            c.execute('''
                INSERT INTO teachers (id, password, email, name, classrooms, bssid_mapping)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                'admin',
                hashlib.sha256('admin'.encode()).hexdigest(),
                'admin@school.com',
                'Admin',
                json.dumps(['A101', 'A102']),
                json.dumps({'A101': '00:11:22:33:44:55'})
            ))
        
        conn.commit()

init_db()

# In-memory data
active_sessions = {}
student_checkins = {}
student_timers = {}
authorized_bssid = None
lock = threading.Lock()

# Helper functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Teacher endpoints
@app.route('/teacher/signup', methods=['POST'])
def teacher_signup():
    data = request.json
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO teachers (id, password, email, name)
                VALUES (?, ?, ?, ?)
            ''', (
                data['id'],
                hash_password(data['password']),
                data['email'],
                data['name']
            ))
            conn.commit()
        return jsonify({'message': 'Teacher registered successfully'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Teacher ID or email already exists'}), 400

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    data = request.json
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM teachers WHERE id = ?', (data['id'],))
        teacher = c.fetchone()
        
        if not teacher or teacher['password'] != hash_password(data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
            
        teacher_data = dict(teacher)
        teacher_data['classrooms'] = json.loads(teacher['classrooms'])
        teacher_data['bssid_mapping'] = json.loads(teacher['bssid_mapping'])
        return jsonify({'teacher': teacher_data}), 200

@app.route('/teacher/register_student', methods=['POST'])
def register_student():
    data = request.json
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO students (id, password, name, classroom, branch, semester)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data['id'],
                hash_password(data['password']),
                data['name'],
                data['classroom'],
                data['branch'],
                data['semester']
            ))
            conn.commit()
        return jsonify({'message': 'Student registered successfully'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Student ID already exists'}), 400

@app.route('/teacher/start_session', methods=['POST'])
def start_session():
    data = request.json
    session_id = f"session_{datetime.now().timestamp()}"
    
    with lock:
        global authorized_bssid
        with get_db() as conn:
            c = conn.cursor()
            
            # Get classroom BSSID
            c.execute('SELECT bssid_mapping FROM teachers WHERE id = ?', (data['teacher_id'],))
            bssid_mapping = json.loads(c.fetchone()['bssid_mapping'])
            authorized_bssid = bssid_mapping.get(data['classroom'])
            
            # Create session
            c.execute('''
                INSERT INTO sessions (id, teacher_id, classroom, subject, start_time, active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                data['teacher_id'],
                data['classroom'],
                data['subject'],
                datetime.now().isoformat(),
                True
            ))
            conn.commit()
            
            active_sessions[session_id] = {
                'classroom': data['classroom'],
                'teacher_id': data['teacher_id']
            }
            
        return jsonify({
            'message': 'Session started',
            'session_id': session_id,
            'authorized_bssid': authorized_bssid
        }), 201

@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    data = request.json
    with lock:
        global authorized_bssid
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE sessions 
                SET end_time = ?, active = ?
                WHERE id = ?
            ''', (
                datetime.now().isoformat(),
                False,
                data['session_id']
            ))
            conn.commit()
            
            if data['session_id'] in active_sessions:
                del active_sessions[data['session_id']]
            authorized_bssid = None
            
        return jsonify({'message': 'Session ended'}), 200

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
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute(query, params)
        students = [dict(row) for row in c.fetchall()]
        
    return jsonify({'students': students}), 200

# Student endpoints
@app.route('/student/login', methods=['POST'])
def student_login():
    data = request.json
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM students WHERE id = ?', (data['id'],))
        student = c.fetchone()
        
        if not student or student['password'] != hash_password(data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
            
        # Get classroom BSSID
        c.execute('SELECT bssid_mapping FROM teachers')
        bssid_mapping = {}
        for row in c.fetchall():
            bssid_mapping.update(json.loads(row['bssid_mapping']))
        
        return jsonify({
            'student': dict(student),
            'classroom_bssid': bssid_mapping.get(student['classroom'])
        }), 200

@app.route('/student/checkin', methods=['POST'])
def student_checkin():
    data = request.json
    with lock:
        student_checkins[data['student_id']] = {
            'timestamp': datetime.now().isoformat(),
            'bssid': data.get('bssid')
        }
        
        # Start timer if BSSID matches
        if data.get('bssid') == authorized_bssid:
            student_timers[data['student_id']] = {
                'status': 'running',
                'start_time': datetime.now().timestamp(),
                'remaining': 300  # 5 minutes
            }
            
        return jsonify({
            'message': 'Checked in',
            'status': 'present' if data.get('bssid') == authorized_bssid else 'absent'
        }), 200

@app.route('/student/get_status', methods=['GET'])
def get_status():
    student_id = request.args.get('student_id')
    
    with lock:
        checkin = student_checkins.get(student_id, {})
        timer = student_timers.get(student_id, {})
        
        return jsonify({
            'connected': student_id in student_checkins,
            'authorized': checkin.get('bssid') == authorized_bssid,
            'timer': {
                'status': timer.get('status', 'stop'),
                'remaining': timer.get('remaining', 0)
            }
        }), 200

# Background timer updater
def update_timers():
    while True:
        with lock:
            current_time = datetime.now().timestamp()
            for student_id, timer in list(student_timers.items()):
                if timer['status'] == 'running':
                    elapsed = current_time - timer['start_time']
                    timer['remaining'] = max(0, 300 - elapsed)
                    
                    if timer['remaining'] <= 0:
                        timer['status'] = 'completed'
                        # Record attendance
                        with get_db() as conn:
                            c = conn.cursor()
                            c.execute('SELECT * FROM students WHERE id = ?', (student_id,))
                            student = dict(c.fetchone())
                            
                            attendance = json.loads(student['attendance'])
                            date = datetime.fromtimestamp(timer['start_time']).date().isoformat()
                            
                            if date not in attendance:
                                attendance[date] = {}
                                
                            attendance[date][f"timer_{timer['start_time']}"] = {
                                'status': 'present' if student_checkins.get(student_id, {}).get('bssid') == authorized_bssid else 'absent',
                                'timestamp': datetime.fromtimestamp(timer['start_time']).isoformat()
                            }
                            
                            c.execute('''
                                UPDATE students
                                SET attendance = ?
                                WHERE id = ?
                            ''', (json.dumps(attendance), student_id))
                            conn.commit()
        
        time.sleep(1)

# Start background thread
threading.Thread(target=update_timers, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
