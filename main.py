from flask import Flask, request, jsonify
import time
import threading
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

# Store attendance data with timestamps and daily logs
attendance_data = {
    'students': defaultdict(lambda: {
        'status': 'absent',
        'last_updated': None,
        'daily_log': []
    })
}

# Store connected clients
connected_clients = {
    'students': {},
    'teachers': {}
}

# Store random ring history
random_ring_history = []

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
    """Update attendance status with timestamp"""
    data = request.json
    username = data.get('username')
    status = data.get('status')
    
    if username and status:
        now = time.time()
        attendance_data['students'][username]['status'] = status
        attendance_data['students'][username]['last_updated'] = now
        attendance_data['students'][username]['daily_log'].append({
            'status': status,
            'timestamp': now
        })
        broadcast_attendance()
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data with timestamps"""
    response = {
        student: {
            'status': data['status'],
            'last_updated': data['last_updated']
        }
        for student, data in attendance_data['students'].items()
    }
    return jsonify(response)

@app.route("/get_daily_attendance", methods=["GET"])
def get_daily_attendance():
    """Get today's attendance data for random ring feature"""
    today = datetime.now().date()
    daily_data = {}
    
    for student, data in attendance_data['students'].items():
        today_entries = [
            entry for entry in data['daily_log']
            if datetime.fromtimestamp(entry['timestamp']).date() == today
        ]
        if today_entries:
            daily_data[student] = today_entries[-1]['status']  # Get latest status
    
    return jsonify(daily_data)

@app.route("/random_ring", methods=["POST"])
def random_ring():
    """Select random students for the random ring feature"""
    today = datetime.now().date()
    present_students = [
        student for student, data in attendance_data['students'].items()
        if any(
            entry['status'] == 'present' and 
            datetime.fromtimestamp(entry['timestamp']).date() == today
            for entry in data['daily_log']
        )
    ]
    
    if len(present_students) < 2:
        return {"error": "Not enough present students"}, 400
    
    selected = random.sample(present_students, min(2, len(present_students)))
    random_ring_history.append({
        'timestamp': time.time(),
        'selected_students': selected
    })
    
    return jsonify({
        "selected_students": selected,
        "timestamp": time.time()
    })

def broadcast_attendance():
    """Send attendance updates to all connected teachers"""
    data = {
        "action": "update_attendance",
        "data": {
            student: {
                'status': data['status'],
                'last_updated': data['last_updated']
            }
            for student, data in attendance_data['students'].items()
        }
    }
    for teacher in list(connected_clients['teachers'].keys()):
        try:
            # In a real implementation, we'd send this to the teacher's socket
            pass
        except:
            # Remove disconnected teachers
            connected_clients['teachers'].pop(teacher, None)

def cleanup_clients():
    """Periodically clean up disconnected clients"""
    while True:
        current_time = time.time()
        for client_type in ['students', 'teachers']:
            for username, last_seen in list(connected_clients[client_type].items()):
                if current_time - last_seen > 60:  # 1 minute timeout
                    connected_clients[client_type].pop(username, None)
                    if client_type == 'students':
                        # Mark student as absent if they timeout
                        attendance_data['students'][username]['status'] = 'absent'
                        attendance_data['students'][username]['last_updated'] = current_time
                        broadcast_attendance()
        time.sleep(30)

if __name__ == "__main__":
    # Start cleanup thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
