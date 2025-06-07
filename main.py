from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading
import random
from collections import defaultdict
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# In-memory data store
data = {
    'attendance': defaultdict(dict),
    'attendance_history': defaultdict(list),
    'users': {
        'admin': {
            'password': 'admin123',
            'type': 'teacher',
            'name': 'Admin Teacher',
            'email': 'admin@school.edu'
        }
    },
    'students': {},
    'active_session': False,
    'session_start': None
}

@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "service": "teacher-attendance-api"})

@app.route('/register', methods=['POST'])
def register():
    """Teacher registration endpoint"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    
    if not username or not password:
        return {"error": "Username and password required"}, 400
        
    if username in data['users']:
        return {"error": "Username already exists"}, 400
        
    data['users'][username] = {
        'password': password,
        'type': 'teacher',
        'name': req_data.get('name', ''),
        'email': req_data.get('email', '')
    }
    return {"status": "registered"}, 201

@app.route('/login', methods=['POST'])
def login():
    """Login endpoint for both teachers and students"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    
    if username not in data['users']:
        return {"error": "User not found"}, 404
        
    if data['users'][username]['password'] != password:
        return {"error": "Invalid password"}, 401
        
    return {
        "status": "authenticated",
        "type": data['users'][username]['type'],
        "name": data['users'][username].get('name', username)
    }, 200

@app.route('/start_attendance', methods=['POST'])
def start_attendance():
    """Start a new attendance session"""
    if data['active_session']:
        return {"error": "Session already active"}, 400
        
    data['active_session'] = True
    data['session_start'] = datetime.now().isoformat()
    data['attendance'].clear()
    return {"status": "session_started"}, 200

@app.route('/end_attendance', methods=['POST'])
def end_attendance():
    """End current attendance session"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
        
    session_date = datetime.now().strftime("%Y-%m-%d")
    for student_id, info in data['attendance'].items():
        record = {
            'date': session_date,
            'status': info.get('status', 'absent'),
            'time_in': info.get('time_in', ''),
            'time_out': info.get('time_out', ''),
            'duration': info.get('duration', '')
        }
        data['attendance_history'][student_id].append(record)
    
    data['active_session'] = False
    data['session_start'] = None
    return {"status": "session_ended"}, 200

@app.route('/get_attendance', methods=['GET'])
def get_attendance():
    """Get current attendance data"""
    return jsonify({
        'students': data['attendance'],
        'active_session': data['active_session'],
        'session_start': data['session_start']
    })

@app.route('/update_attendance_status', methods=['POST'])
def update_attendance_status():
    """Update student attendance status"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
        
    req_data = request.json
    student_id = req_data.get('student_id')
    status = req_data.get('status')
    
    if not student_id or not status:
        return {"error": "Missing student_id or status"}, 400
        
    now = datetime.now()
    current_record = data['attendance'].get(student_id, {})
    
    if status == 'present' and 'time_in' not in current_record:
        current_record['time_in'] = now.strftime("%H:%M:%S")
    elif status in ['absent', 'left'] and 'time_out' not in current_record:
        current_record['time_out'] = now.strftime("%H:%M:%S")
        if 'time_in' in current_record:
            time_in = datetime.strptime(current_record['time_in'], "%H:%M:%S")
            duration = (now - time_in).total_seconds() / 60
            current_record['duration'] = f"{int(duration)} minutes"
    
    current_record['status'] = status
    data['attendance'][student_id] = current_record
    return {"status": "updated"}, 200

def cleanup_inactive_students():
    """Background thread to mark inactive students"""
    while True:
        if data['active_session']:
            current_time = datetime.now()
            for student_id, info in list(data['attendance'].items()):
                if 'last_update' in info:
                    last_update = datetime.fromisoformat(info['last_update'])
                    if (current_time - last_update).total_seconds() > 900:  # 15 minutes
                        info['status'] = 'left'
                        info['time_out'] = current_time.strftime("%H:%M:%S")
        time.sleep(60)

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_inactive_students, daemon=True).start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
