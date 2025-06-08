from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)

# Data storage
data = {
    'attendance': defaultdict(dict),
    'attendance_history': defaultdict(list),
    'users': {
        'admin': {'password': 'admin123', 'type': 'teacher', 'name': 'Admin'},
        'student1': {'password': 'pass123', 'type': 'student', 'name': 'John Doe'}
    },
    'students': {
        'student1': {'name': 'John Doe', 'class': '10A', 'active': True}
    },
    'settings': {
        'target_bssid': "ee:ee:6d:9d:6f:ba",
        'attendance_threshold': 15,
        'timer_duration': 20
    },
    'active_session': False,
    'session_start': None,
    'last_ring': None,
    'ring_students': []
}

# API Endpoints
@app.route("/login", methods=["POST"])
def login():
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
    if data['active_session']:
        return {"error": "Session already active"}, 400
    data['active_session'] = True
    data['session_start'] = datetime.now().isoformat()
    data['attendance'].clear()
    return {"status": "session_started"}, 200

@app.route("/end_attendance", methods=["POST"])
def end_attendance():
    if not data['active_session']:
        return {"error": "No active session"}, 400
    session_date = datetime.now().strftime("%Y-%m-%d")
    for student_id, info in data['attendance'].items():
        record = {
            'date': session_date,
            'status': info.get('status', 'absent'),
            'time_in': info.get('time_in', ''),
            'time_out': info.get('time_out', ''),
            'device_id': info.get('device_id', ''),
            'bssid': info.get('bssid', '')
        }
        data['attendance_history'][student_id].append(record)
    data['active_session'] = False
    return {"status": "session_ended"}, 200

@app.route("/update_attendance", methods=["POST"])
def update_attendance():
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
    record = data['attendance'].get(student_id, {})
    if status == 'present':
        record.update({
            'time_in': now.strftime("%H:%M:%S"),
            'status': 'present',
            'device_id': device_id,
            'bssid': bssid
        })
    elif status in ['absent', 'left']:
        record['status'] = status
        if 'time_out' not in record:
            record['time_out'] = now.strftime("%H:%M:%S")
            if 'time_in' in record:
                duration = (now - datetime.strptime(record['time_in'], "%H:%M:%S")).total_seconds() / 60
                record['duration'] = f"{int(duration)} minutes"
    data['attendance'][student_id] = record
    return {"status": "updated"}, 200

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    return jsonify({
        'students': data['attendance'],
        'active_session': data['active_session']
    })

@app.route("/random_ring", methods=["POST"])
def random_ring():
    if not data['active_session']:
        return {"error": "No active session"}, 400
    present_students = [s for s, info in data['attendance'].items() if info.get('status') == 'present']
    if not present_students:
        return {"error": "No present students"}, 400
    selected = random.sample(present_students, min(2, len(present_students)))
    data['last_ring'] = datetime.now().isoformat()
    data['ring_students'] = selected
    return {"status": "ring_sent", "students": selected}, 200

# Background task
def cleanup_attendance():
    while True:
        if data['active_session']:
            now = datetime.now()
            for student_id, info in list(data['attendance'].items()):
                if 'time_in' in info and 'time_out' not in info:
                    time_in = datetime.strptime(info['time_in'], "%H:%M:%S")
                    if (now - time_in).total_seconds() > data['settings']['attendance_threshold'] * 60:
                        info.update({
                            'status': 'left',
                            'time_out': now.strftime("%H:%M:%S"),
                            'duration': f"{data['settings']['attendance_threshold']} minutes"
                        })
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=cleanup_attendance, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
