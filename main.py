from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time

app = Flask(__name__)

# Cloud Database
db = {
    'users': {
        'admin': {'password': 'admin123', 'type': 'teacher', 'name': 'Admin'},
        's1': {'password': 's1pass', 'type': 'student', 'name': 'John', 'class': '10A'},
        's2': {'password': 's2pass', 'type': 'student', 'name': 'Sarah', 'class': '10B'}
    },
    'attendance': defaultdict(list),
    'settings': {
        'authorized_bssids': ['aa:bb:cc:dd:ee:ff'],
        'active_session': False,
        'session_start': None,
        'attendance_duration': 120  # seconds
    },
    'timetable': {
        'Monday': {'9:00': 'Math', '10:00': 'Science'},
        'Tuesday': {'9:00': 'History', '10:00': 'English'}
    },
    'random_rings': {
        'active': False,
        'students': []
    }
}

# API Endpoints
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = db['users'].get(username)
    if user and user['password'] == password:
        return jsonify({
            'success': True,
            'user_type': user['type'],
            'name': user.get('name', username)
        })
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/session', methods=['POST'])
def manage_session():
    if request.json.get('action') == 'start':
        db['settings']['active_session'] = True
        db['settings']['session_start'] = datetime.now().isoformat()
        return jsonify({'success': True})
    elif request.json.get('action') == 'end':
        db['settings']['active_session'] = False
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid action'}), 400

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    if not db['settings']['active_session']:
        return jsonify({'success': False, 'error': 'No active session'}), 400
    
    data = request.json
    student_id = data.get('student_id')
    bssid = data.get('bssid')
    
    if bssid not in db['settings']['authorized_bssids']:
        return jsonify({'success': False, 'error': 'Unauthorized network'}), 403
    
    db['attendance'][student_id].append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M:%S'),
        'status': 'present',
        'bssid': bssid
    })
    return jsonify({'success': True})

@app.route('/api/bssid', methods=['POST'])
def manage_bssid():
    action = request.json.get('action')
    bssid = request.json.get('bssid')
    
    if action == 'add' and bssid not in db['settings']['authorized_bssids']:
        db['settings']['authorized_bssids'].append(bssid)
        return jsonify({'success': True})
    elif action == 'remove' and bssid in db['settings']['authorized_bssids']:
        db['settings']['authorized_bssids'].remove(bssid)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid request'}), 400

@app.route('/api/random_ring', methods=['POST'])
def random_ring():
    if request.json.get('action') == 'start':
        students = list({uid: info for uid, info in db['users'].items() if info['type'] == 'student'}.keys())
        db['random_rings'] = {
            'active': True,
            'students': students[:2]  # Select 2 random students
        }
        return jsonify({'success': True, 'students': db['random_rings']['students']})
    elif request.json.get('action') == 'end':
        db['random_rings']['active'] = False
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/api/data', methods=['GET'])
def get_data():
    endpoint = request.args.get('type')
    if endpoint == 'students':
        students = {uid: info for uid, info in db['users'].items() if info['type'] == 'student'}
        return jsonify(students)
    elif endpoint == 'timetable':
        return jsonify(db['timetable'])
    elif endpoint == 'session':
        return jsonify({
            'active': db['settings']['active_session'],
            'start_time': db['settings']['session_start']
        })
    elif endpoint == 'bssids':
        return jsonify(db['settings']['authorized_bssids'])
    elif endpoint == 'random_ring':
        return jsonify(db['random_rings'])
    return jsonify({'success': False}), 404

def cleanup_sessions():
    while True:
        if db['settings']['active_session']:
            start_time = datetime.fromisoformat(db['settings']['session_start'])
            if (datetime.now() - start_time) > timedelta(minutes=120):
                db['settings']['active_session'] = False
        time.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=cleanup_sessions, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
