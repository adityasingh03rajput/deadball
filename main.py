from flask import Flask, request, jsonify
import time
import threading
import random
from collections import defaultdict
from datetime import datetime
from gevent.pywsgi import WSGIServer

app = Flask(__name__)

# Configuration
PING_TIMEOUT = 60  # 1 minute
CLEANUP_INTERVAL = 30  # seconds

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
data_lock = threading.Lock()

@app.route('/ping', methods=['POST'])
def ping():
    try:
        data = request.get_json()
        with data_lock:
            if data and 'type' in data and 'username' in data:
                connected_clients[data['type']][data['username']] = time.time()
                return jsonify({'status': 'ok'})
        return jsonify({'error': 'Invalid data'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/attendance', methods=['POST'])
def update_attendance():
    try:
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
        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_attendance', methods=['GET'])
def get_attendance():
    try:
        with data_lock:
            return jsonify({
                student: {
                    'status': data['status'],
                    'last_updated': data['last_updated']
                }
                for student, data in attendance_data.items()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def cleanup_clients():
    """Periodically clean up inactive clients"""
    while True:
        current_time = time.time()
        with data_lock:
            for client_type in ['students', 'teachers']:
                to_remove = [
                    username for username, last_seen in connected_clients[client_type].items()
                    if current_time - last_seen > PING_TIMEOUT
                ]
                for username in to_remove:
                    connected_clients[client_type].pop(username, None)
                    if client_type == 'students':
                        update_attendance_internal(username, 'absent')
        time.sleep(CLEANUP_INTERVAL)

def update_attendance_internal(username, status):
    """Thread-safe internal update"""
    with data_lock:
        now = time.time()
        attendance_data[username]['status'] = status
        attendance_data[username]['last_updated'] = now
        attendance_data[username]['daily_log'].append({
            'status': status,
            'timestamp': now
        })

if __name__ == '__main__':
    # Start background thread
    threading.Thread(target=cleanup_clients, daemon=True).start()
    
    # Production-ready server
    print("Starting server on port 5000")
    http_server = WSGIServer(('0.0.0.0', 5000), app)
    http_server.serve_forever()
