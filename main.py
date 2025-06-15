from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, time
from collections import defaultdict
import threading
import uuid
import pytz
import os
import time
import calendar
from typing import Dict, List, Optional, Tuple

app = Flask(__name__)

TIMEZONE = 'Asia/Kolkata'
data = {
    'users': {},
    'live_attendance': defaultdict(lambda: {
        'active': False, 
        'current_lecture': None, 
        'accumulated_time': 0, 
        'last_ping': None, 
        'attendance_timer': False, 
        'attendance_start': None,
        'wifi_connected': False
    }),
    'attendance_history': defaultdict(list),
    'active_sessions': {},
    'timetable': {},
    'settings': {
        'authorized_bssids': [], 
        'session_active': False, 
        'random_rings': []
    },
    'messages': [],
}

# --- Utility Functions ---
def get_current_time() -> datetime:
    """Get current time in configured timezone."""
    return datetime.now(pytz.timezone(TIMEZONE))

def parse_time(time_str: str) -> time:
    """Parse time string (HH:MM) into time object."""
    return datetime.strptime(time_str, "%H:%M").time()

def get_current_lecture(class_id: str) -> Optional[str]:
    """
    Determine the current lecture for a given class based on timetable.
    Returns formatted lecture string if found, None otherwise.
    """
    now = get_current_time()
    day = now.strftime('%A')
    time_now = now.time()
    
    if class_id not in data['timetable']:
        return None
        
    class_tt = data['timetable'][class_id].get(day, {})
    for slot, subject in class_tt.items():
        try:
            start, end = map(str.strip, slot.split('-'))
            s_time, e_time = parse_time(start), parse_time(end)
            if s_time <= time_now <= e_time:
                return f"{slot} ({subject})"
        except (ValueError, AttributeError):
            continue
    return None

def calc_attendance_status(student_id: str, lecture: Optional[str]) -> str:
    """
    Calculate attendance status based on accumulated time and lecture duration.
    Returns 'Present', 'Absent', or 'in_progress'.
    """
    if not lecture:
        return 'Absent'
        
    info = data['live_attendance'][student_id]
    if not info['attendance_timer']:
        return 'Absent'
    
    try:
        # Extract time slot from lecture string (e.g., "09:00-10:00 (Math)")
        time_slot = lecture.split(' (')[0]
        start_str, end_str = time_slot.split('-')
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)
        
        # Calculate total duration in seconds
        duration = (datetime.combine(datetime.today(), end_time) - 
                   datetime.combine(datetime.today(), start_time)).total_seconds()
        
        if info['accumulated_time'] >= 0.85 * duration:
            return 'Present'
        elif info['accumulated_time'] > 0:
            return 'in_progress'
        return 'Absent'
    except:
        return 'Absent'

def validate_teacher_auth() -> Tuple[bool, str]:
    """Validate teacher authorization from request headers."""
    auth = request.headers.get('Authorization')
    if not auth:
        return False, "Missing authorization"
    
    try:
        token_type, token = auth.split()
        if token_type.lower() != 'bearer':
            return False, "Invalid token type"
            
        user_id = next((uid for uid, sess in data['active_sessions'].items() 
                       if uid == token), None)
        if not user_id or data['users'].get(user_id, {}).get('type') != 'teacher':
            return False, "Invalid or expired token"
            
        return True, user_id
    except:
        return False, "Invalid authorization header"

# --- Authentication Endpoints ---
@app.route('/login', methods=['POST'])
def login():
    """Handle user login for both teachers and students."""
    req = request.json
    username = req.get('username')
    password = req.get('password')
    device_id = req.get('device_id')
    
    if not all([username, password, device_id]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Find user by username
    user = next(((uid, u) for uid, u in data['users'].items() 
                if u['username'] == username), (None, None))
    
    if not user[0] or not check_password_hash(user[1]['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Store active session
    data['active_sessions'][device_id] = user[0]
    
    response = {
        'user_id': user[0],
        'type': user[1]['type'],
        'name': user[1]['name']
    }
    
    if user[1]['type'] == 'student':
        response['class_id'] = user[1]['class_id']
    
    return jsonify(response)

@app.route('/logout', methods=['POST'])
def logout():
    """Handle user logout."""
    req = request.json
    device_id = req.get('device_id')
    student_id = req.get('student_id')
    
    if not device_id:
        return jsonify({'error': 'Device ID required'}), 400
    
    # Remove session
    data['active_sessions'].pop(device_id, None)
    
    # Update student status if provided
    if student_id and student_id in data['live_attendance']:
        data['live_attendance'][student_id]['active'] = False
        data['live_attendance'][student_id]['attendance_timer'] = False
    
    return jsonify({'message': 'Logged out successfully'})

@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    """Register a new teacher account."""
    req = request.json
    username = req.get('username')
    password = req.get('password')
    
    if not all([username, password]):
        return jsonify({'error': 'Username and password required'}), 400
    
    # Check if username exists
    if any(u['username'] == username for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400
    
    # Create new teacher
    teacher_id = str(uuid.uuid4())
    data['users'][teacher_id] = {
        'username': username,
        'password_hash': generate_password_hash(password),
        'type': 'teacher',
        'name': req.get('name', username)
    }
    
    return jsonify({'message': 'Teacher registered successfully', 'user_id': teacher_id}), 201

@app.route('/student/register', methods=['POST'])
def student_register():
    """Register a new student account."""
    req = request.json
    username = req.get('username')
    password = req.get('password')
    name = req.get('name')
    class_id = req.get('class_id')
    
    if not all([username, password, name, class_id]):
        return jsonify({'error': 'All fields are required'}), 400
    
    # Check if username exists
    if any(u['username'] == username for u in data['users'].values()):
        return jsonify({'error': 'Username already exists'}), 400
    
    # Create new student
    student_id = str(uuid.uuid4())
    data['users'][student_id] = {
        'username': username,
        'password_hash': generate_password_hash(password),
        'type': 'student',
        'name': name,
        'class_id': class_id
    }
    
    return jsonify({'message': 'Student registered successfully', 'user_id': student_id}), 201

# --- Student Endpoints ---
@app.route('/student/connect', methods=['POST'])
def student_connect():
    """Handle student device connection and attendance tracking."""
    req = request.json
    student_id = req.get('student_id')
    bssid = req.get('bssid')
    
    if not student_id or student_id not in data['users']:
        return jsonify({'error': 'Invalid student ID'}), 400
    
    # Get student info
    student = data['users'][student_id]
    class_id = student.get('class_id')
    
    # Check WiFi authorization if BSSID provided
    is_authorized = False
    if bssid:
        is_authorized = bssid.lower() in data['settings']['authorized_bssids']
    
    # Get current lecture
    current_lecture = get_current_lecture(class_id)
    info = data['live_attendance'][student_id]
    
    # Update student status
    info['last_ping'] = get_current_time()
    info['wifi_connected'] = is_authorized
    
    if current_lecture:
        # If lecture changed, reset timer
        if info['current_lecture'] != current_lecture:
            info['current_lecture'] = current_lecture
            info['accumulated_time'] = 0
        
        info['active'] = True
        info['accumulated_time'] += 10  # Increment by ping interval
        
        # Only mark attendance timer if authorized WiFi
        info['attendance_timer'] = is_authorized
    else:
        info['active'] = False
        info['attendance_timer'] = False
        info['current_lecture'] = None
    
    # Calculate attendance status
    attendance_status = calc_attendance_status(student_id, current_lecture)
    
    return jsonify({
        'class_started': bool(current_lecture),
        'lecture': current_lecture,
        'timer': {
            'duration': 3600,  # Default 1 hour lecture
            'remaining': max(0, 3600 - info['accumulated_time']),
            'status': 'running' if info['attendance_timer'] else 'stopped'
        },
        'attendance': attendance_status,
        'wifi_authorized': is_authorized
    })

@app.route('/student/timer/start', methods=['POST'])
def start_timer():
    """Manually start attendance timer for a student."""
    req = request.json
    student_id = req.get('student_id')
    
    if not student_id or student_id not in data['users']:
        return jsonify({'error': 'Invalid student ID'}), 400
    
    info = data['live_attendance'][student_id]
    info['attendance_timer'] = True
    info['attendance_start'] = get_current_time()
    
    current_lecture = info['current_lecture']
    attendance_status = calc_attendance_status(student_id, current_lecture)
    
    return jsonify({
        'timer': {
            'duration': 3600,
            'remaining': max(0, 3600 - info['accumulated_time']),
            'status': 'running'
        },
        'attendance': attendance_status,
        'message': 'Attendance timer started'
    })

# --- Information Endpoints ---
@app.route('/students', methods=['GET'])
def get_students():
    """Get list of all students."""
    students = []
    for uid, user in data['users'].items():
        if user['type'] == 'student':
            students.append({
                'id': uid,
                'name': user['name'],
                'username': user['username'],
                'class_id': user.get('class_id', 'N/A')
            })
    return jsonify(students)

@app.route('/student/profile/<student_id>', methods=['GET'])
def get_student_profile(student_id: str):
    """Get detailed profile and attendance stats for a student."""
    if student_id not in data['users'] or data['users'][student_id]['type'] != 'student':
        return jsonify({'error': 'Student not found'}), 404
    
    records = data['attendance_history'].get(student_id, [])
    present_count = sum(1 for r in records if r['status'] == 'Present')
    total_lectures = len(records)
    
    # Calculate most missed lectures
    most_missed = defaultdict(int)
    for r in records:
        if r['status'] == 'Absent':
            most_missed[r['lecture']] += 1
    
    return jsonify({
        'name': data['users'][student_id]['name'],
        'class_id': data['users'][student_id].get('class_id', 'N/A'),
        'present_lectures': present_count,
        'total_lectures': total_lectures,
        'attendance_percent': (present_count / total_lectures * 100) if total_lectures else 0,
        'most_missed': sorted(most_missed.items(), key=lambda x: x[1], reverse=True)[:5],
        'detailed_report': records
    })

@app.route('/classmates/<class_id>', methods=['GET'])
def get_classmates(class_id: str):
    """Get list of classmates for a given class."""
    classmates = []
    for uid, user in data['users'].items():
        if user['type'] == 'student' and user.get('class_id') == class_id:
            classmates.append({
                'id': uid,
                'name': user['name'],
                'username': user['username']
            })
    return jsonify({'students': classmates})

@app.route('/live_data', methods=['GET'])
def get_live_data():
    """Get live attendance data for all students."""
    live_data = {
        'students': [],
        'random_rings': data['settings']['random_rings'],
        'session_active': data['settings']['session_active']
    }
    
    for student_id, user in data['users'].items():
        if user['type'] != 'student':
            continue
            
        info = data['live_attendance'][student_id]
        last_update = info['last_ping'].timestamp() if info['last_ping'] else None
        
        live_data['students'].append({
            'id': student_id,
            'name': user['name'],
            'class_id': user.get('class_id', 'N/A'),
            'status': calc_attendance_status(student_id, info['current_lecture']),
            'current_lecture': info['current_lecture'],
            'timer': {
                'duration': 3600,
                'remaining': max(0, 3600 - info['accumulated_time']),
                'status': 'running' if info['attendance_timer'] else 'stopped'
            },
            'last_update': last_update,
            'wifi_connected': info['wifi_connected']
        })
    
    return jsonify(live_data)

# --- Timetable Management ---
@app.route('/timetable', methods=['GET', 'POST'])
def manage_timetable():
    """Get or update the timetable."""
    if request.method == 'POST':
        # Validate teacher auth
        valid, msg = validate_teacher_auth()
        if not valid:
            return jsonify({'error': msg}), 401
        
        try:
            timetable_data = request.json
            if not isinstance(timetable_data, dict):
                return jsonify({'error': 'Invalid timetable format'}), 400
                
            data['timetable'] = timetable_data
            return jsonify({'message': 'Timetable updated successfully'})
        except:
            return jsonify({'error': 'Invalid timetable data'}), 400
    
    # GET request - return timetable
    return jsonify(data['timetable'])

# --- Settings Management ---
@app.route('/settings/bssid', methods=['GET', 'POST'])
def manage_bssids():
    """Get or update authorized WiFi BSSIDs."""
    if request.method == 'POST':
        # Validate teacher auth
        valid, msg = validate_teacher_auth()
        if not valid:
            return jsonify({'error': msg}), 401
        
        try:
            bssids = request.json.get('bssids', [])
            if not isinstance(bssids, list):
                return jsonify({'error': 'BSSIDs must be a list'}), 400
                
            # Validate BSSID format (MAC address)
            valid_bssids = []
            for bssid in bssids:
                if isinstance(bssid, str) and len(bssid.split(':')) == 6:
                    valid_bssids.append(bssid.lower())
            
            data['settings']['authorized_bssids'] = valid_bssids
            return jsonify({'message': 'BSSIDs updated successfully'})
        except:
            return jsonify({'error': 'Invalid BSSID data'}), 400
    
    # GET request - return current BSSIDs
    return jsonify({'bssids': data['settings']['authorized_bssids']})

# --- Session Management ---
@app.route('/session/start', methods=['POST'])
def start_session():
    """Start an attendance session."""
    valid, msg = validate_teacher_auth()
    if not valid:
        return jsonify({'error': msg}), 401
    
    data['settings']['session_active'] = True
    return jsonify({'message': 'Attendance session started'})

@app.route('/session/end', methods=['POST'])
def end_session():
    """End an attendance session."""
    valid, msg = validate_teacher_auth()
    if not valid:
        return jsonify({'error': msg}), 401
    
    data['settings']['session_active'] = False
    return jsonify({'message': 'Attendance session ended'})

@app.route('/session/status', methods=['GET'])
def session_status():
    """Get current session status."""
    return jsonify({
        'session_active': data['settings']['session_active'],
        'random_rings': data['settings']['random_rings']
    })

@app.route('/random_ring', methods=['POST'])
def random_ring():
    """Send random ring to students."""
    valid, msg = validate_teacher_auth()
    if not valid:
        return jsonify({'error': msg}), 401
    
    if not data['settings']['session_active']:
        return jsonify({'error': 'No active session'}), 400
    
    # Get all students with their attendance percentages
    students = []
    for student_id, user in data['users'].items():
        if user['type'] != 'student':
            continue
            
        records = data['attendance_history'].get(student_id, [])
        total = len(records)
        present = sum(1 for r in records if r['status'] == 'Present')
        percent = (present / total * 100) if total else 0
        students.append((student_id, percent, user['name']))
    
    if len(students) < 2:
        return jsonify({'error': 'Not enough students'}), 400
    
    # Sort by attendance percentage
    students.sort(key=lambda x: x[1])
    
    # Select one with lowest and one with highest attendance
    selected = [students[0][0], students[-1][0]]
    data['settings']['random_rings'] = selected
    
    return jsonify({
        'students': selected,
        'names': [students[0][2], students[-1][2]],
        'message': 'Random ring sent successfully'
    })

# --- Reports ---
@app.route('/report', methods=['GET'])
def generate_report():
    """Generate attendance report for a date range."""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    if not from_date or not to_date:
        return jsonify({'error': 'Both from_date and to_date required'}), 400
    
    try:
        # Parse dates
        start = datetime.strptime(from_date, '%Y-%m-%d').date()
        end = datetime.strptime(to_date, '%Y-%m-%d').date()
        
        if start > end:
            return jsonify({'error': 'from_date must be before to_date'}), 400
        
        # Build report
        report = defaultdict(dict)
        for delta in range((end - start).days + 1):
            date = (start + timedelta(days=delta)).strftime('%Y-%m-%d')
            for student_id, user in data['users'].items():
                if user['type'] != 'student':
                    continue
                
                # Check attendance records for this date
                records = [r for r in data['attendance_history'].get(student_id, []) 
                          if r['date'] == date]
                
                if records:
                    # If any present records, mark as present
                    status = 'Present' if any(r['status'] == 'Present' for r in records) else 'Absent'
                else:
                    # No records - check if date is in future
                    record_date = datetime.strptime(date, '%Y-%m-%d').date()
                    status = 'Future' if record_date > get_current_time().date() else 'Absent'
                
                report[date][student_id] = {
                    'status': status,
                    'name': user['name'],
                    'class_id': user.get('class_id', 'N/A')
                }
        
        return jsonify(report)
    except ValueError:
        return jsonify({'error': 'Invalid date format (use YYYY-MM-DD)'}), 400

# --- Background Tasks ---
def auto_mark_attendance():
    """Background task to automatically mark attendance based on timetable."""
    while True:
        try:
            now = get_current_time()
            today_str = now.strftime('%Y-%m-%d')
            
            # Check each class in timetable
            for class_id, timetable in data['timetable'].items():
                day_schedule = timetable.get(now.strftime('%A'), {})
                
                for time_slot, subject in day_schedule.items():
                    try:
                        # Parse time slot (e.g., "09:00-10:00")
                        start_str, end_str = time_slot.split('-')
                        start_time = parse_time(start_str)
                        end_time = parse_time(end_str)
                        
                        # Check if current time is after lecture end time
                        if now.time() > end_time:
                            # Calculate total duration in seconds
                            duration = (datetime.combine(now.date(), end_time) - 
                                      datetime.combine(now.date(), start_time)).total_seconds()
                            
                            # Required time for attendance (85% of duration)
                            req_time = duration * 0.85
                            
                            # Check all students in this class
                            for student_id, user in data['users'].items():
                                if user.get('class_id') != class_id or user['type'] != 'student':
                                    continue
                                
                                # Skip if already has record for this lecture
                                lecture_str = f"{time_slot} ({subject})"
                                if any(r['date'] == today_str and r['lecture'] == lecture_str 
                                      for r in data['attendance_history'][student_id]):
                                    continue
                                
                                # Check accumulated time
                                live_info = data['live_attendance'][student_id]
                                status = 'Present' if live_info['accumulated_time'] >= req_time else 'Absent'
                                
                                # Add to attendance history
                                data['attendance_history'][student_id].append({
                                    'date': today_str,
                                    'lecture': lecture_str,
                                    'status': status,
                                    'timestamp': now.isoformat()
                                })
                    except (ValueError, AttributeError):
                        continue
            
            time.sleep(60)  # Check every minute
        except Exception as e:
            print(f"Error in auto_mark_attendance: {e}")
            time.sleep(60)

def clear_inactive_students():
    """Background task to clear inactive student connections."""
    while True:
        try:
            now = get_current_time()
            for student_id, info in list(data['live_attendance'].items()):
                if info['last_ping'] and (now - info['last_ping']).total_seconds() > 30:
                    info['active'] = False
                    info['attendance_timer'] = False
            time.sleep(15)  # Check every 15 seconds
        except Exception as e:
            print(f"Error in clear_inactive_students: {e}")
            time.sleep(15)

if __name__ == '__main__':
    # Start background tasks
    threading.Thread(target=auto_mark_attendance, daemon=True).start()
    threading.Thread(target=clear_inactive_students, daemon=True).start()
    
    # Start Flask app
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
