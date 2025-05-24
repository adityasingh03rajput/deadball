from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

# Store all data
data = {
    'attendance': defaultdict(dict),
    'last_ring': None,
    'ring_students': [],
    'users': {},
    'timetable': {}
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
        # Teacher updating timetable
        req_data = request.json
        data['timetable'] = req_data.get('timetable', {})
        return {"status": "updated"}, 200
    else:
        # Anyone can view timetable
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

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    return jsonify({
        'students': data['attendance'],
        'last_ring': data['last_ring'],
        'ring_students': data['ring_students']
    })

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

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Start random ring thread
    threading.Thread(target=start_random_rings, daemon=True).start()
    
    app.run(host="0.0.0.0", port=5000)
