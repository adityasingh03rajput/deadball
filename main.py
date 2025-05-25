from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime, timedelta
import requests
import json
import os

app = Flask(__name__)

# Store all data
data = {
    'attendance': defaultdict(dict),
    'last_ring': None,
    'ring_students': [],
    'users': {},
    'timetable': {},
    'holidays': {},
    'attendance_history': defaultdict(dict)
}

# Configuration
RING_INTERVAL = 300  # 5 minutes
CALENDAR_API_KEY = os.getenv('CALENDAR_API_KEY', 'your_api_key_here')
HOLIDAY_API_URL = "https://calendarific.com/api/v2/holidays"

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
    students = {
        username: info 
        for username, info in data['users'].items() 
        if info.get('type') == 'student'
    }
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
        today = datetime.now().date().isoformat()
        data['attendance'][username] = {
            'status': status,
            'last_update': datetime.now().isoformat()
        }
        data['attendance_history'][username][today] = status
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    return jsonify({
        'students': data['attendance'],
        'last_ring': data['last_ring'],
        'ring_students': data['ring_students']
    })

@app.route("/get_attendance_history", methods=["GET"])
def get_attendance_history():
    """Get attendance history for a student"""
    username = request.args.get('username')
    if not username:
        return {"error": "Username required"}, 400
    
    holidays = list(data['holidays'].keys())
    present_dates = []
    absent_dates = []
    
    for date, status in data['attendance_history'].get(username, {}).items():
        if status == 'present':
            present_dates.append(date)
        elif status == 'absent':
            absent_dates.append(date)
    
    return jsonify({
        'holidays': holidays,
        'present': present_dates,
        'absent': absent_dates
    })

@app.route("/update_holidays", methods=["POST"])
def update_holidays():
    """Update holidays from external API"""
    try:
        year = datetime.now().year
        params = {
            'api_key': CALENDAR_API_KEY,
            'country': 'IN',
            'year': year,
            'type': 'national'
        }
        response = requests.get(HOLIDAY_API_URL, params=params)
        if response.status_code == 200:
            holidays = response.json().get('response', {}).get('holidays', [])
            data['holidays'] = {
                holiday['date']['iso']: holiday['name']
                for holiday in holidays
            }
            return {"status": "updated", "count": len(data['holidays'])}, 200
        return {"error": "Failed to fetch holidays"}, 400
    except Exception as e:
        return {"error": str(e)}, 500

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
        with app.app_context():
            present_students = [
                student for student, info in data['attendance'].items() 
                if info.get('status') == 'present'
            ]
            if len(present_students) >= 2:
                selected = random.sample(present_students, min(2, len(present_students)))
                data['last_ring'] = datetime.now().isoformat()
                data['ring_students'] = selected

def update_holidays_periodically():
    """Update holidays periodically"""
    while True:
        with app.app_context():
            try:
                requests.post(f"{SERVER_URL}/update_holidays")
            except:
                pass
        time.sleep(86400)  # Update once per day

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Start random ring thread
    threading.Thread(target=start_random_rings, daemon=True).start()
    
    # Start holiday update thread
    threading.Thread(target=update_holidays_periodically, daemon=True).start()
    
    app.run(host="0.0.0.0", port=5000)
