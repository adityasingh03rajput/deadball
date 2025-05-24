from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime
from gevent.pywsgi import WSGIServer

app = Flask(__name__)

# Data storage with thread locks
attendance_data = defaultdict(lambda: {
    'status': 'absent',
    'last_updated': None,
    'daily_log': []
})
connected_clients = {
    'students': {},
    'teachers': {}
}
random_ring_history = []
data_lock = threading.Lock()

# Optimized helper functions
def get_current_timestamp():
    return int(time.time())

def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')

# Routes
@app.route('/ping', methods=['POST'])
def ping():
    data = request.get_json()
    with data_lock:
        if data and 'type' in data and 'username' in data:
            connected_clients[data['type']][data['username']] = get_current_timestamp()
            return jsonify({'status': 'ok'})
    return jsonify({'error': 'Invalid data'}), 400

@app.route('/attendance', methods=['POST'])
def update_attendance():
    data = request.get_json()
    if not data or 'username' not in data or 'status' not in data:
        return jsonify({'error': 'Missing data'}), 400
    
    with data_lock:
        now = get_current_timestamp()
        attendance_data[data['username']]['status'] = data['status']
        attendance_data[data['username']]['last_updated'] = now
        attendance_data[data['username']]['daily_log'].append({
            'status': data['status'],
            'timestamp': now
        })
        broadcast_attendance()
    return jsonify({'status': 'updated'})

@app.route('/get_attendance', methods=['GET'])
def get_attendance():
    with data_lock:
        return jsonify({
            student: {
                'status': data['status'],
                'last_updated': format_time(data['last_updated']) if data['last_updated'] else None
            }
            for student, data in attendance_data.items()
        })

@app.route('/random_ring', methods=['POST'])
def random_ring():
    today = datetime.now().date()
    with data_lock:
        present_students = [
            student for student, data in attendance_data.items()
            if any(
                entry['status'] == 'present' and 
                datetime.fromtimestamp(entry['timestamp']).date() == today
                for entry in data['daily_log']
            )
        ]
        
        if len(present_students) < 2:
            return jsonify({'error': 'Not enough present students'}), 400
        
        selected = random.sample(present_students, 2)
        random_ring_history.append({
            'timestamp': get_current_timestamp(),
            'selected_students': selected
        })
        
        return jsonify({
            'selected_students': selected,
            'timestamp': format_time(get_current_timestamp())
        })

# Background tasks
def broadcast_attendance():
    """Optimized broadcast using thread-safe data access"""
    with data_lock:
        data = {
            student: {
                'status': info['status'],
                'last_updated': format_time(info['last_updated'])
            }
            for student, info in attendance_data.items()
        }
    
    # In production, use WebSockets or SSE here
    # This is a placeholder for the broadcast logic

def cleanup_clients():
    """Optimized client cleanup"""
    while True:
        current_time = get_current_timestamp()
        with data_lock:
            for client_type in ['students', 'teachers']:
                to_remove = [
                    username for username, last_seen in connected_clients[client_type].items()
                    if current_time - last_seen > 60
                ]
                for username in to_remove:
                    connected_clients[client_type].pop(username, None)
                    if client_type == 'students':
                        update_attendance_internal(username, 'absent')
        time.sleep(30)

def update_attendance_internal(username, status):
    """Thread-safe internal update"""
    with data_lock:
        now = get_current_timestamp()
        attendance_data[username]['status'] = status
        attendance_data[username]['last_updated'] = now
        attendance_data[username]['daily_log'].append({
            'status': status,
            'timestamp': now
        })
    broadcast_attendance()

if __name__ == '__main__':
    # Start background thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Production-ready server
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    print("Server running on port 5000")
    http_server.serve_forever()
