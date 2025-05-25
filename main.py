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
    'wifi_status': defaultdict(dict),
    'last_ring': None,
    'ring_students': [],
    'users': {},
    'timetable': {},
    'holidays': {},
    'national_holidays': {
        '2023-01-26': 'Republic Day',
        '2023-08-15': 'Independence Day',
        '2023-10-02': 'Gandhi Jayanti',
        '2023-12-25': 'Christmas Day'
    }
}

# Configuration
RING_INTERVAL = 300  # 5 minutes

@app.route("/register", methods=["POST"])
def register():
    """Handle user registration (teacher only)"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    user_type = req_data.get('type')
    
    if user_type != 'teacher':
        return {"error": "Only teachers can register"}, 400
    
    if username in data['users']:
        return {"error": "Username already exists"}, 400
        
    data['users'][username] = {
        'password': password,
        'type': user_type
    }
    return {"status": "registered"}, 201

@app.route("/register_student", methods=["POST"])
def register_student():
    """Handle student registration (teacher only)"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    user_type = 'student'
    
    if username in data['users']:
        return {"error": "Username already exists"}, 400
        
    data['users'][username] = {
        'password': password,
        'type': user_type
    }
    return {"status": "registered"}, 201

@app.route("/get_students", methods=["GET"])
def get_students():
    """Get list of all registered students"""
    students = [
        username for username, info in data['users'].items() 
        if info.get('type') == 'student'
    ]
    return jsonify(students)

@app.route("/login", methods=["POST"])
def login():
    """Handle user login"""
    req_data = request.json
    username = req_data.get('username')
    password = req_data.get('password')
    
    if username not in data['users']:
        return {"error": "User not found"}, 404
        
    if data['users'][username]['password'] != password:
        return {"error": "Invalid password"}, 401
        
    return {
        "status": "authenticated",
        "type": data['users'][username]['type']
    }, 200

@app.route("/timetable", methods=["GET", "POST"])
def timetable():
    """Handle timetable operations"""
    if request.method == "POST":
        req_data = request.json
        data['timetable'] = req_data.get('timetable', {})
        return {"status": "updated"}, 200
    else:
        return jsonify(data['timetable'])

@app.route("/attendance", methods=["POST"])
def update_attendance():
    """Update attendance status"""
    req_data = request.json
    username = req_data.get('username')
    status = req_data.get('status')
    action = req_data.get('action')
    
    if action == "random_ring":
        present_students = [
            student for student, info in data['attendance'].items() 
            if info.get('status') == 'present'
        ]
        selected = random.sample(present_students, min(2, len(present_students)))
        data['last_ring'] = datetime.now().isoformat()
        data['ring_students'] = selected
        return {"status": "ring_sent", "students": selected}, 200
    
    if username and status:
        data['attendance'][username] = {
            'status': status,
            'last_update': datetime.now().isoformat()
        }
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/update_wifi_status", methods=["POST"])
def update_wifi_status():
    """Update WiFi connection status"""
    req_data = request.json
    username = req_data.get('username')
    status = req_data.get('status')
    
    if username and status:
        data['wifi_status'][username] = {
            'status': status,
            'last_update': datetime.now().isoformat()
        }
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    # Combine attendance and wifi status
    combined = {}
    for username in set(data['attendance'].keys()).union(data['wifi_status'].keys()):
        combined[username] = {
            **data['attendance'].get(username, {}),
            **data['wifi_status'].get(username, {})
        }
    
    return jsonify({
        'students': combined,
        'last_ring': data['last_ring'],
        'ring_students': data['ring_students']
    })

@app.route("/get_attendance_history", methods=["GET"])
def get_attendance_history():
    """Get attendance history for a student"""
    username = request.args.get('username')
    if not username:
        return {"error": "Username required"}, 400
    
    # In a real app, this would query a database
    # For now, return sample data
    present_dates = []
    absent_dates = []
    today = datetime.now().date()
    
    for i in range(30):  # Last 30 days
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        if date_str in data['national_holidays'] or date_str in data['holidays']:
            continue
        if random.random() > 0.2:  # 80% chance present
            present_dates.append(date_str)
        else:
            absent_dates.append(date_str)
    
    return jsonify({
        'present': present_dates,
        'absent': absent_dates,
        'holidays': {**data['national_holidays'], **data['holidays']}
    })

@app.route("/update_holidays", methods=["POST"])
def update_holidays():
    """Update custom holidays"""
    req_data = request.json
    date = req_data.get('date')
    name = req_data.get('name')
    action = req_data.get('action')
    
    if action == "delete":
        if date in data['holidays']:
            del data['holidays'][date]
            return {"status": "deleted"}, 200
        return {"error": "Holiday not found"}, 404
    
    if date and name:
        data['holidays'][date] = name
        return {"status": "updated"}, 200
    
    return {"error": "Missing data"}, 400

@app.route("/get_holidays", methods=["GET"])
def get_holidays():
    """Get all holidays (national + custom)"""
    return jsonify({
        'national_holidays': data['national_holidays'],
        'custom_holidays': data['holidays']
    })

@app.route("/ping", methods=["POST"])
def ping():
    """Handle ping from clients"""
    req_data = request.json
    username = req_data.get('username')
    user_type = req_data.get('type')
    
    if username and user_type == 'student':
        if username in data['attendance']:
            data['attendance'][username]['last_update'] = datetime.now().isoformat()
        else:
            data['attendance'][username] = {
                'status': 'present',
                'last_update': datetime.now().isoformat()
            }
    
    return {"status": "pong"}, 200

def cleanup_clients():
    """Periodically clean up disconnected clients"""
    while True:
        current_time = time.time()
        for username, info in list(data['attendance'].items()):
            last_update = datetime.fromisoformat(info['last_update'])
            if (datetime.now() - last_update).total_seconds() > 60:
                data['attendance'][username]['status'] = 'left'
                data['attendance'][username]['last_update'] = datetime.now().isoformat()
        time.sleep(30)

def start_random_rings():
    """Start periodic random rings"""
    while True:
        time.sleep(random.randint(120, 600))  # 2-10 minutes
        present_students = [
            student for student, info in data['attendance'].items() 
            if info.get('status') == 'present'
        ]
        if len(present_students) >= 2:
            selected = random.sample(present_students, min(2, len(present_students)))
            data['last_ring'] = datetime.now().isoformat()
            data['ring_students'] = selected

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Start random ring thread
    threading.Thread(target=start_random_rings, daemon=True).start()
    
    app.run(host="0.0.0.0", port=5000)
