from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)

# Store all data
data = {
    'attendance': defaultdict(dict),
    'attendance_history': defaultdict(list),
    'wifi_status': defaultdict(dict),
    'last_ring': None,
    'ring_students': [],
    'users': {
        'admin': {
            'password': 'admin123',
            'type': 'teacher',
            'name': 'Admin Teacher',
            'email': 'admin@school.edu'
        }
    },
    'students': {},
    'timetable': {},
    'holidays': {
        'national_holidays': {
            '2023-01-26': {'name': 'Republic Day', 'description': 'Indian Republic Day'},
            '2023-08-15': {'name': 'Independence Day', 'description': 'Indian Independence Day'},
            '2023-10-02': {'name': 'Gandhi Jayanti', 'description': 'Mahatma Gandhi\'s birthday'},
            '2023-12-25': {'name': 'Christmas Day', 'description': 'Christmas celebration'}
        },
        'custom_holidays': {}
    },
    'settings': {
        'wifi_range': 50,
        'attendance_threshold': 15,
        'target_bssid': "ee:ee:6d:9d:6f:ba"
    },
    'active_session': False,
    'session_start': None,
    'random_rings': {}
}

@app.route("/register", methods=["POST"])
def register():
    """Handle user registration"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    user_type = req_data.get('type', 'student')
    
    if username in data['users']:
        return {"error": "Username already exists"}, 400
        
    data['users'][username] = {
        'password': password,
        'type': user_type,
        'name': req_data.get('name', ''),
        'email': req_data.get('email', '')
    }
    
    if user_type == 'student':
        data['students'][username] = {
            'name': req_data.get('name', ''),
            'class': req_data.get('class', ''),
            'active': True
        }
    
    return {"status": "registered"}, 201

@app.route("/login", methods=["POST"])
def login():
    """Handle user login"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    user_type = req_data.get('type')
    
    if username not in data['users']:
        return {"error": "User not found"}, 404
        
    if data['users'][username]['password'] != password:
        return {"error": "Invalid password"}, 401
        
    if user_type and data['users'][username]['type'] != user_type:
        return {"error": f"User is not a {user_type}"}, 403
        
    return {
        "status": "authenticated",
        "type": data['users'][username]['type'],
        "name": data['users'][username].get('name', username)
    }, 200

@app.route("/start_attendance", methods=["POST"])
def start_attendance():
    """Start a new attendance session"""
    req_data = request.json
    if data['active_session']:
        return {"error": "Session already active"}, 400
    
    data['active_session'] = True
    data['session_start'] = datetime.now().isoformat()
    data['attendance'].clear()
    return {"status": "session_started"}, 200

@app.route("/end_attendance", methods=["POST"])
def end_attendance():
    """End the current attendance session"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
    
    # Archive attendance to history
    session_date = datetime.now().strftime("%Y-%m-%d")
    for student_id, info in data['attendance'].items():
        record = {
            'date': session_date,
            'status': info.get('status', 'absent'),
            'time_in': info.get('time_in', ''),
            'time_out': info.get('time_out', ''),
            'duration': info.get('duration', ''),
            'device_id': info.get('device_id', ''),
            'bssid': info.get('bssid', '')
        }
        data['attendance_history'][student_id].append(record)
    
    data['active_session'] = False
    data['session_start'] = None
    return {"status": "session_ended"}, 200

@app.route("/update_attendance", methods=["POST"])
def update_attendance():
    """Update student attendance status"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
        
    req_data = request.json
    student_id = req_data.get('student_id')
    status = req_data.get('status')
    device_id = req_data.get('device_id')
    bssid = req_data.get('bssid')
    
    if not student_id or not status:
        return {"error": "Missing student_id or status"}, 400
    
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    now = datetime.now()
    current_record = data['attendance'].get(student_id, {})
    
    if status == 'present':
        current_record['time_in'] = now.strftime("%H:%M:%S")
        current_record['status'] = 'present'
        current_record['device_id'] = device_id
        current_record['bssid'] = bssid
    elif status in ['absent', 'left']:
        current_record['status'] = status
        if 'time_out' not in current_record:
            current_record['time_out'] = now.strftime("%H:%M:%S")
            if 'time_in' in current_record:
                time_in = datetime.strptime(current_record['time_in'], "%H:%M:%S")
                duration = (now - time_in).total_seconds() / 60
                current_record['duration'] = f"{int(duration)} minutes"
    
    data['attendance'][student_id] = current_record
    return {"status": "updated"}, 200

@app.route("/complete_attendance", methods=["POST"])
def complete_attendance():
    """Mark attendance as completed"""
    req_data = request.json
    student_id = req_data.get('student_id')
    
    if student_id in data['attendance']:
        data['attendance'][student_id]['completed'] = True
    return {"status": "completed"}, 200

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    return jsonify({
        'students': data['attendance'],
        'active_session': data['active_session'],
        'session_start': data['session_start']
    })

@app.route("/get_attendance_session", methods=["GET"])
def get_attendance_session():
    """Check attendance session status"""
    return jsonify({
        'active': data['active_session'],
        'session_start': data['session_start']
    })

@app.route("/get_random_rings", methods=["GET"])
def get_random_rings():
    """Check for random rings"""
    student_id = request.args.get('student_id')
    return jsonify({
        'last_ring': data['last_ring'],
        'ring_active': student_id in data['ring_students'] if student_id else False,
        'ring_students': data['ring_students']
    })

@app.route("/random_ring", methods=["POST"])
def random_ring():
    """Trigger random ring"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
    
    present_students = [
        student for student, info in data['attendance'].items() 
        if info.get('status') == 'present'
    ]
    
    if len(present_students) >= 2:
        selected = random.sample(present_students, min(2, len(present_students)))
        data['last_ring'] = datetime.now().isoformat()
        data['ring_students'] = selected
        return {"status": "ring_sent", "students": selected}, 200
    
    return {"error": "Not enough present students"}, 400

@app.route("/get_students", methods=["GET"])
def get_students():
    """Get list of all students"""
    return jsonify([
        {
            'id': student_id,
            'name': info.get('name', ''),
            'class': info.get('class', ''),
            'active': info.get('active', True)
        }
        for student_id, info in data['students'].items()
    ])

@app.route("/student_details/<student_id>", methods=["GET"])
def student_details(student_id):
    """Get student details"""
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    student_info = data['students'][student_id].copy()
    
    # Calculate attendance stats
    present = sum(1 for r in data['attendance_history'].get(student_id, []) if r['status'] == 'present')
    absent = sum(1 for r in data['attendance_history'].get(student_id, []) if r['status'] == 'absent')
    left = sum(1 for r in data['attendance_history'].get(student_id, []) if r['status'] == 'left')
    total = present + absent + left
    
    student_info['attendance_stats'] = {
        'total_classes': total,
        'present': present,
        'absent': absent,
        'left': left,
        'attendance_percent': (present / total * 100) if total > 0 else 0
    }
    
    return jsonify(student_info)

@app.route("/get_settings", methods=["GET"])
def get_settings():
    """Get system settings"""
    return jsonify(data['settings'])

def cleanup_attendance():
    """Periodically clean up attendance records"""
    while True:
        if data['active_session']:
            threshold = data['settings']['attendance_threshold']
            now = datetime.now()
            
            for student_id, info in list(data['attendance'].items()):
                if 'time_in' in info and 'time_out' not in info:
                    time_in = datetime.strptime(info['time_in'], "%H:%M:%S")
                    if (now - time_in).total_seconds() > threshold * 60:
                        info['status'] = 'left'
                        info['time_out'] = now.strftime("%H:%M:%S")
                        info['duration'] = f"{threshold} minutes"
        
        time.sleep(60)

if __name__ == "__main__":
    # Start background threads
    threading.Thread(target=cleanup_attendance, daemon=True).start()
    
    app.run(host="0.0.0.0", port=5000)
