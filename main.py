from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime
from gevent.pywsgi import WSGIServer

app = Flask(__name__)

# Thread-safe data storage
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

@app.route('/ping', methods=['POST'])
def ping():
    data = request.get_json()
    with data_lock:
        if data and 'type' in data and 'username' in data:
            connected_clients[data['type']][data['username']] = time.time()
            return jsonify({'status': 'ok'})
    return jsonify({'error': 'Invalid data'}), 400

@app.route('/attendance', methods=['POST'])
def update_attendance():
    data = request.get_json()
    if not data or 'username' not in data or 'status' not in data:
        return jsonify({'error': 'Missing data'}), 400
    
    with data_lock:
        now = time.time()
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
                'last_updated': data['last_updated']
            }
            for student, data in attendance_data.items()
        })

@app.route('/get_daily_attendance', methods=['GET'])
def get_daily_attendance():
    today = datetime.now().date()
    with data_lock:
        return jsonify({
            student: data['daily_log'][-1]['status']
            for student, data in attendance_data.items()
            if data['daily_log'] and 
            datetime.fromtimestamp(data['daily_log'][-1]['timestamp']).date() == today
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
            'timestamp': time.time(),
            'selected_students': selected
        })
        return jsonify({
            'selected_students': selected,
            'timestamp': time.time()
        })

def broadcast_attendance():
    with data_lock:
        data = {
            student: {
                'status': info['status'],
                'last_updated': info['last_updated']
            }
            for student, info in attendance_data.items()
        }
    # In production: Implement WebSocket broadcast here

def cleanup_clients():
    while True:
        time.sleep(30)
        current_time = time.time()
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

def update_attendance_internal(username, status):
    with data_lock:
        now = time.time()
        attendance_data[username]['status'] = status
        attendance_data[username]['last_updated'] = now
        attendance_data[username]['daily_log'].append({
            'status': status,
            'timestamp': now
        })
    broadcast_attendance()

if __name__ == '__main__':
    threading.Thread(target=cleanup_clients, daemon=True).start()
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    print("Server running on port 5000")
    http_server.serve_forever()
