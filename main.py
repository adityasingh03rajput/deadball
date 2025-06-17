from flask import Flask, request, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import threading
import time
import uuid
import random
import os
import face_recognition
import cv2
import numpy as np
from io import BytesIO
import json

app = Flask(__name__)

# Database simulation
class Database:
    def __init__(self):
        self.users = {}
        self.live_attendance = defaultdict(lambda: {
            'active': False,
            'current_lecture': None,
            'accumulated_time': 0,
            'last_ping': None
        })
        self.attendance_history = defaultdict(list)
        self.active_sessions = {}
        self.timetable = {}
        self.settings = {
            'authorized_bssids': ['ee:ee:6d:9d:6f:ba'],
            'class_locations': {
                'default': {'lat': 28.7041, 'lon': 77.1025, 'radius': 100}
            }
        }
        self.random_ring_selections = {}
        self.face_encodings = {}
        self.penalties = {}

db = Database()

# Helper functions
def get_utc_now():
    return datetime.now(timezone.utc)

def validate_location(student_lat, student_lon, class_id='default'):
    class_loc = db.settings['class_locations'].get(class_id)
    if not class_loc:
        return False
    distance = ((student_lat - class_loc['lat'])**2 + 
               (student_lon - class_loc['lon'])**2)**0.5 * 111000
    return distance <= class_loc['radius']

def get_current_lecture(class_id):
    now = get_utc_now()
    day_of_week = now.strftime('%A')
    current_time = now.time()
    
    class_timetable = db.timetable.get(class_id, {}).get(day_of_week, {})
    for time_slot, subject in class_timetable.items():
        try:
            start_str, end_str = time_slot.split('-')
            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
            if start_time <= current_time <= end_time:
                return f"{time_slot} ({subject})"
        except ValueError:
            continue
    return None

# User Management Endpoints
@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    req = request.json
    if not req or not req.get('username') or not req.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    if any(u['username'] == req['username'] for u in db.users.values()):
        return jsonify({'error': 'Username exists'}), 400

    user_id = str(uuid.uuid4())
    db.users[user_id] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'teacher',
        'name': req.get('name', req['username'])
    }
    return jsonify({'message': 'Teacher registered'}), 201

@app.route('/student/register', methods=['POST'])
def student_register():
    req = request.json
    if not req or not req.get('username') or not req.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    if any(u['username'] == req['username'] for u in db.users.values()):
        return jsonify({'error': 'Username exists'}), 400

    user_id = str(uuid.uuid4())
    db.users[user_id] = {
        'username': req['username'],
        'password_hash': generate_password_hash(req['password']),
        'type': 'student',
        'name': req.get('name', req['username']),
        'class_id': req.get('class_id')
    }
    return jsonify({'message': 'Student registered', 'user_id': user_id}), 201

@app.route('/login', methods=['POST'])
def login():
    req = request.json
    username = req.get('username')
    password = req.get('password')
    device_id = req.get('device_id')
    
    if not all([username, password, device_id]):
        return jsonify({'error': 'Missing credentials'}), 400

    user = next((u for u in db.users.values() if u['username'] == username), None)
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401

    user_id = next(uid for uid, u in db.users.items() if u['username'] == username)
    
    # One device per user enforcement
    if user_id in db.active_sessions.values():
        active_device = next(d for d, uid in db.active_sessions.items() if uid == user_id)
        if active_device != device_id:
            return jsonify({'error': 'Account in use on another device'}), 403

    db.active_sessions[device_id] = user_id
    
    response = {
        'message': 'Login successful',
        'user_id': user_id,
        'type': user['type'],
        'name': user.get('name')
    }
    if user['type'] == 'student':
        response['class_id'] = user.get('class_id')
        
    return jsonify(response), 200

# Attendance Endpoints
@app.route('/ping', methods=['POST'])
def ping():
    req = request.json
    device_id = req.get('device_id')
    student_lat = req.get('latitude')
    student_lon = req.get('longitude')
    
    if device_id not in db.active_sessions:
        return jsonify({'error': 'Session expired'}), 401
    
    student_id = db.active_sessions[device_id]
    student_info = db.users[student_id]
    
    # Geo-fencing check
    if student_lat and student_lon:
        if not validate_location(student_lat, student_lon, student_info.get('class_id')):
            return jsonify({'error': 'Not in authorized location'}), 403
    
    lecture = get_current_lecture(student_info.get('class_id'))
    live_data = db.live_attendance[student_id]
    live_data['last_ping'] = get_utc_now()
    
    if lecture:
        if live_data['current_lecture'] != lecture:
            live_data['current_lecture'] = lecture
            live_data['accumulated_time'] = 0
        
        live_data['active'] = True
        live_data['accumulated_time'] += 10  # Ping interval
    else:
        live_data['active'] = False
        live_data['current_lecture'] = None

    return jsonify({
        'status': 'pong',
        'current_lecture': live_data['current_lecture'],
        'accumulated_time': live_data['accumulated_time']
    }), 200

# Random Ring Endpoints
@app.route('/random_ring', methods=['POST'])
def random_ring():
    teacher_id = request.json.get('teacher_id')
    if not teacher_id or teacher_id not in db.users or db.users[teacher_id]['type'] != 'teacher':
        return jsonify({'error': 'Invalid teacher'}), 400

    active_students = [
        uid for uid, info in db.live_attendance.items() 
        if info['active'] and db.users[uid]['type'] == 'student'
    ]
    selected = random.sample(active_students, min(2, len(active_students)))
    
    db.random_ring_selections = {
        'students': selected,
        'time': get_utc_now().isoformat(),
        'responded': []
    }
    return jsonify({
        'selected': [db.users[uid]['name'] for uid in selected],
        'timeout': 300  # 5 minutes to respond
    })

@app.route('/verify_face', methods=['POST'])
def verify_face():
    student_id = request.form.get('student_id')
    if 'image' not in request.files or not student_id:
        return jsonify({'error': 'Image and ID required'}), 400
    
    img_bytes = request.files['image'].read()
    img_array = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb_image)
    
    if not encodings:
        return jsonify({'error': 'No face detected'}), 400
    
    if student_id not in db.face_encodings:
        db.face_encodings[student_id] = encodings[0].tolist()
        return jsonify({'verified': True, 'message': 'Face registered'})
    
    matches = face_recognition.compare_faces(
        [np.array(db.face_encodings[student_id])], 
        encodings[0]
    )
    return jsonify({'verified': matches[0]})

# Teacher Dashboard Endpoints
@app.route('/live_data', methods=['GET'])
def get_live_data():
    response = []
    for user_id, user_info in db.users.items():
        if user_info['type'] == 'student':
            live_info = db.live_attendance[user_id]
            response.append({
                'id': user_id,
                'name': user_info['name'],
                'class_id': user_info.get('class_id'),
                'status': 'Active' if live_info['active'] else 'Inactive',
                'current_lecture': live_info['current_lecture'],
                'accumulated_time': live_info.get('accumulated_time', 0)
            })
    return jsonify(response)

@app.route('/override_attendance', methods=['POST'])
def override_attendance():
    req = request.json
    teacher_id = req.get('teacher_id')
    student_id = req.get('student_id')
    status = req.get('status')
    
    if (teacher_id not in db.users or 
        db.users[teacher_id]['type'] != 'teacher' or
        student_id not in db.users):
        return jsonify({'error': 'Invalid request'}), 400

    db.attendance_history[student_id].append({
        'date': get_utc_now().date().isoformat(),
        'lecture': 'MANUAL_OVERRIDE',
        'status': status,
        'by': teacher_id
    })
    return jsonify({'message': 'Attendance updated'})

# Background Services
def attendance_processor():
    """Process attendance at lecture end"""
    while True:
        now = get_utc_now()
        today = now.date().isoformat()
        
        for class_id, timetable in db.timetable.items():
            day_schedule = timetable.get(now.strftime('%A'), {})
            for time_slot, subject in day_schedule.items():
                start_str, end_str = time_slot.split('-')
                end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                
                if now.time() > end_time:
                    lecture_id = f"{today}-{class_id}-{time_slot}"
                    
                    # Calculate required attendance time (85% of lecture)
                    start_dt = datetime.combine(now.date(), 
                        datetime.strptime(start_str.strip(), "%H:%M").time())
                    end_dt = datetime.combine(now.date(), end_time)
                    lecture_duration = (end_dt - start_dt).total_seconds()
                    required_time = lecture_duration * 0.85
                    
                    # Process attendance for class students
                    for student_id, user_info in db.users.items():
                        if (user_info['type'] == 'student' and 
                            user_info.get('class_id') == class_id):
                            
                            live_info = db.live_attendance[student_id]
                            status = 'Present' if live_info['accumulated_time'] >= required_time else 'Absent'
                            
                            db.attendance_history[student_id].append({
                                'date': today,
                                'lecture': f"{time_slot} ({subject})",
                                'status': status
                            })
        time.sleep(60)

def session_cleanup():
    """Clean inactive sessions"""
    while True:
        now = get_utc_now()
        inactive = []
        
        for device_id, user_id in db.active_sessions.items():
            if user_id in db.live_attendance:
                last_ping = db.live_attendance[user_id]['last_ping']
                if last_ping and (now - last_ping).total_seconds() > 300:  # 5 min timeout
                    inactive.append(device_id)
        
        for device_id in inactive:
            db.active_sessions.pop(device_id, None)
        
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=attendance_processor, daemon=True).start()
    threading.Thread(target=session_cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=10000, debug=False)
