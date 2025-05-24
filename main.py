from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

# Store attendance data
attendance_data = {
    'students': defaultdict(dict),
    'last_ring': None,
    'ring_students': []
}

# Store connected clients
connected_clients = {
    'students': {},
    'teachers': {}
}

# Configuration
RING_INTERVAL = 300  # 5 minutes

@app.route("/ping", methods=["POST"])
def ping():
    """Handle client heartbeats"""
    data = request.json
    client_type = data.get('type')
    username = data.get('username')
    
    if client_type and username:
        connected_clients[client_type][username] = time.time()
        return {"status": "ok"}, 200
    return {"error": "Invalid data"}, 400

@app.route("/attendance", methods=["POST"])
def update_attendance():
    """Update attendance status"""
    data = request.json
    username = data.get('username')
    status = data.get('status')
    action = data.get('action')
    
    if action == "random_ring":
        present_students = [
            student for student, info in attendance_data['students'].items() 
            if info.get('status') == 'present'
        ]
        selected = random.sample(present_students, min(2, len(present_students)))
        attendance_data['last_ring'] = datetime.now().isoformat()
        attendance_data['ring_students'] = selected
        return {"status": "ring_sent", "students": selected}, 200
    
    if username and status:
        attendance_data['students'][username] = {
            'status': status,
            'last_update': datetime.now().isoformat()
        }
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    return jsonify({
        'students': attendance_data['students'],
        'last_ring': attendance_data['last_ring'],
        'ring_students': attendance_data['ring_students']
    })

def cleanup_clients():
    """Periodically clean up disconnected clients"""
    while True:
        current_time = time.time()
        for client_type in ['students', 'teachers']:
            for username, last_seen in list(connected_clients[client_type].items()):
                if current_time - last_seen > 60:  # 1 minute timeout
                    connected_clients[client_type].pop(username, None)
                    if client_type == 'students':
                        attendance_data['students'][username]['status'] = 'left'
                        attendance_data['students'][username]['last_update'] = datetime.now().isoformat()
        time.sleep(30)

def start_random_rings():
    """Start periodic random rings"""
    while True:
        time.sleep(random.randint(120, 600))  # 2-10 minutes
        with app.app_context():
            present_students = [
                student for student, info in attendance_data['students'].items() 
                if info.get('status') == 'present'
            ]
            if len(present_students) >= 2:
                selected = random.sample(present_students, min(2, len(present_students)))
                attendance_data['last_ring'] = datetime.now().isoformat()
                attendance_data['ring_students'] = selected

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Start random ring thread
    threading.Thread(target=start_random_rings, daemon=True).start()
    
    app.run(host="0.0.0.0", port=5000)
