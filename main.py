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
    'attendance_history': defaultdict(list),
    'wifi_status': defaultdict(dict),
    'last_ring': None,
    'ring_students': [],
    'users': {
        'admin': {
            'password': 'admin123',
            'type': 'teacher',
            'name': 'Admin Teacher',
            'email': 'admin@school.edu'
        }
    },
    'students': {},
    'timetable': {},
    'holidays': {
        'national_holidays': {
            '2023-01-26': {'name': 'Republic Day', 'description': 'Indian Republic Day'},
            '2023-08-15': {'name': 'Independence Day', 'description': 'Indian Independence Day'},
            '2023-10-02': {'name': 'Gandhi Jayanti', 'description': 'Mahatma Gandhi\'s birthday'},
            '2023-12-25': {'name': 'Christmas Day', 'description': 'Christmas celebration'}
        },
        'custom_holidays': {}
    },
    'settings': {
        'wifi_range': 50,
        'attendance_threshold': 15  # minutes
    },
    'active_session': False,
    'session_start': None
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
        return {"error": "Only teachers can register here"}, 400
    
    if username in data['users']:
        return {"error": "Username already exists"}, 400
        
    data['users'][username] = {
        'password': password,
        'type': user_type,
        'name': req_data.get('name', ''),
        'email': req_data.get('email', '')
    }
    return {"status": "registered"}, 201

@app.route("/register_student", methods=["POST"])
def register_student():
    """Handle student registration (teacher only)"""
    req_data = request.json
    student_id = req_data.get('student_id')
    name = req_data.get('name')
    student_class = req_data.get('class')
    password = req_data.get('password')
    
    if not all([student_id, name, student_class, password]):
        return {"error": "Missing required fields"}, 400
        
    if student_id in data['students']:
        return {"error": "Student ID already exists"}, 400
        
    # Create both student record and user account
    data['students'][student_id] = {
        'name': name,
        'class': student_class,
        'active': True,
        'email': req_data.get('email', ''),
        'phone': req_data.get('phone', ''),
        'address': req_data.get('address', '')
    }
    
    data['users'][student_id] = {
        'password': password,
        'type': 'student'
    }
    
    return {"status": "registered"}, 201

@app.route("/get_students", methods=["GET"])
def get_students():
    """Get list of all registered students with details"""
    students = []
    for student_id, info in data['students'].items():
        if info.get('active', True):
            last_seen = None
            if student_id in data['attendance_history'] and data['attendance_history'][student_id]:
                last_seen = data['attendance_history'][student_id][-1].get('date', 'Never')
            
            students.append({
                'id': student_id,
                'name': info.get('name', ''),
                'class': info.get('class', ''),
                'last_seen': last_seen or 'Never',
                'active': info.get('active', True)
            })
    
    return jsonify(students)

@app.route("/student_details/<student_id>", methods=["GET"])
def student_details(student_id):
    """Get detailed information about a student"""
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    student_info = data['students'][student_id].copy()
    
    # Calculate attendance stats
    present = 0
    absent = 0
    left = 0
    total = 0
    
    if student_id in data['attendance_history']:
        for record in data['attendance_history'][student_id]:
            if record['status'] == 'present':
                present += 1
            elif record['status'] == 'absent':
                absent += 1
            elif record['status'] == 'left':
                left += 1
            total += 1
    
    attendance_percent = (present / total * 100) if total > 0 else 0
    
    student_info['attendance_stats'] = {
        'total_classes': total,
        'present': present,
        'absent': absent,
        'left': left,
        'attendance_percent': attendance_percent
    }
    
    return jsonify(student_info)

@app.route("/student_attendance/<student_id>", methods=["GET"])
def student_attendance(student_id):
    """Get attendance history for a specific student"""
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    history = data['attendance_history'].get(student_id, [])
    
    if from_date and to_date:
        try:
            from_date = datetime.strptime(from_date, "%Y-%m-%d")
            to_date = datetime.strptime(to_date, "%Y-%m-%d")
            
            filtered_history = [
                record for record in history 
                if from_date <= datetime.strptime(record['date'], "%Y-%m-%d") <= to_date
            ]
            return jsonify(filtered_history)
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400
    
    return jsonify(history)

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
        "type": data['users'][username]['type'],
        "name": data['users'][username].get('name', username)
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

@app.route("/start_attendance", methods=["POST"])
def start_attendance():
    """Start a new attendance session"""
    data['active_session'] = True
    data['session_start'] = datetime.now().isoformat()
    # Clear previous attendance for the new session
    data['attendance'].clear()
    return {"status": "session_started"}, 200

@app.route("/end_attendance", methods=["POST"])
def end_attendance():
    """End the current attendance session"""
    if not data['active_session']:
        return {"error": "No active session"}, 400
    
    # Archive the current attendance to history
    session_date = datetime.now().strftime("%Y-%m-%d")
    for student_id, info in data['attendance'].items():
        record = {
            'date': session_date,
            'status': info.get('status', 'absent'),
            'time_in': info.get('time_in', ''),
            'time_out': info.get('time_out', ''),
            'duration': info.get('duration', ''),
            'class': data['students'].get(student_id, {}).get('class', '')
        }
        data['attendance_history'][student_id].append(record)
    
    data['active_session'] = False
    data['session_start'] = None
    return {"status": "session_ended"}, 200

@app.route("/update_attendance", methods=["POST"])
def update_attendance():
    """Update attendance status"""
    if not data['active_session']:
        return {"error": "No active attendance session"}, 400
    
    req_data = request.json
    student_id = req_data.get('student_id')
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
    
    if student_id and status:
        if student_id not in data['students']:
            return {"error": "Student not found"}, 404
        
        now = datetime.now()
        current_record = data['attendance'].get(student_id, {})
        
        if status == 'present' and 'time_in' not in current_record:
            current_record['time_in'] = now.strftime("%H:%M:%S")
            current_record['status'] = 'present'
        elif status in ['absent', 'left']:
            current_record['status'] = status
            if 'time_out' not in current_record:
                current_record['time_out'] = now.strftime("%H:%M:%S")
                if 'time_in' in current_record:
                    time_in = datetime.strptime(current_record['time_in'], "%H:%M:%S")
                    time_out = datetime.strptime(current_record['time_out'], "%H:%M:%S")
                    duration = (time_out - time_in).total_seconds() / 60  # in minutes
                    current_record['duration'] = f"{int(duration)} minutes"
        
        data['attendance'][student_id] = current_record
        return {"status": "updated"}, 200
    
    return {"error": "Missing data"}, 400

@app.route("/update_attendance_status", methods=["POST"])
def update_attendance_status():
    """Manually update a student's attendance status"""
    if not data['active_session']:
        return {"error": "No active attendance session"}, 400
    
    req_data = request.json
    student_id = req_data.get('student_id')
    status = req_data.get('status')
    
    if not student_id or not status:
        return {"error": "Missing student_id or status"}, 400
    
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    data['attendance'][student_id]['status'] = status
    return {"status": "updated"}, 200

@app.route("/update_wifi_status", methods=["POST"])
def update_wifi_status():
    """Update WiFi connection status"""
    req_data = request.json
    student_id = req_data.get('student_id')
    status = req_data.get('status')
    device = req_data.get('device', 'Unknown')
    
    if student_id and status:
        data['wifi_status'][student_id] = {
            'status': status,
            'last_update': datetime.now().isoformat(),
            'device': device
        }
        return {"status": "updated"}, 200
    return {"error": "Missing data"}, 400

@app.route("/get_attendance", methods=["GET"])
def get_attendance():
    """Get current attendance data"""
    # Combine attendance and wifi status
    combined = {}
    for student_id in set(data['attendance'].keys()).union(data['wifi_status'].keys()):
        student_info = data['students'].get(student_id, {})
        combined[student_id] = {
            'name': student_info.get('name', student_id),
            'class': student_info.get('class', ''),
            **data['attendance'].get(student_id, {}),
            **data['wifi_status'].get(student_id, {})
        }
    
    return jsonify({
        'students': combined,
        'last_ring': data['last_ring'],
        'ring_students': data['ring_students'],
        'active_session': data['active_session'],
        'session_start': data['session_start']
    })

@app.route("/update_holidays", methods=["POST"])
def update_holidays():
    """Update custom holidays"""
    req_data = request.json
    date = req_data.get('date')
    name = req_data.get('name')
    description = req_data.get('description', '')
    action = req_data.get('action')
    holiday_type = req_data.get('type', 'custom')
    
    if action == "delete":
        if date in data['holidays']['custom_holidays']:
            del data['holidays']['custom_holidays'][date]
            return {"status": "deleted"}, 200
        return {"error": "Holiday not found"}, 404
    
    if date and name:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400
        
        if holiday_type == 'national':
            data['holidays']['national_holidays'][date] = {
                'name': name,
                'description': description
            }
        else:
            data['holidays']['custom_holidays'][date] = {
                'name': name,
                'description': description
            }
        return {"status": "updated"}, 200
    
    return {"error": "Missing date or name"}, 400

@app.route("/get_holidays", methods=["GET"])
def get_holidays():
    """Get all holidays (national + custom)"""
    return jsonify(data['holidays'])

@app.route("/import_holidays", methods=["POST"])
def import_holidays():
    """Import holidays from a list"""
    req_data = request.json
    holidays = req_data.get('holidays', [])
    
    if not isinstance(holidays, list):
        return {"error": "Invalid format. Expected list of holidays"}, 400
    
    imported = 0
    for holiday in holidays:
        date = holiday.get('date')
        name = holiday.get('name')
        if date and name:
            data['holidays']['custom_holidays'][date] = {
                'name': name,
                'description': holiday.get('description', '')
            }
            imported += 1
    
    return {"status": "imported", "count": imported}, 200

@app.route("/update_student/<student_id>", methods=["POST"])
def update_student(student_id):
    """Update student information"""
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    req_data = request.json
    data['students'][student_id].update({
        'name': req_data.get('name', data['students'][student_id]['name']),
        'class': req_data.get('class', data['students'][student_id]['class']),
        'email': req_data.get('email', data['students'][student_id].get('email', '')),
        'phone': req_data.get('phone', data['students'][student_id].get('phone', '')),
        'address': req_data.get('address', data['students'][student_id].get('address', ''))
    })
    
    return {"status": "updated"}, 200

@app.route("/reset_student_password/<student_id>", methods=["POST"])
def reset_student_password(student_id):
    """Reset a student's password"""
    if student_id not in data['users'] or data['users'][student_id]['type'] != 'student':
        return {"error": "Student not found"}, 404
    
    req_data = request.json
    new_password = req_data.get('new_password')
    
    if not new_password:
        return {"error": "New password required"}, 400
    
    data['users'][student_id]['password'] = new_password
    return {"status": "updated"}, 200

@app.route("/deactivate_student/<student_id>", methods=["POST"])
def deactivate_student(student_id):
    """Deactivate a student account"""
    if student_id not in data['students']:
        return {"error": "Student not found"}, 404
    
    data['students'][student_id]['active'] = False
    return {"status": "deactivated"}, 200

@app.route("/change_password", methods=["POST"])
def change_password():
    """Change user password"""
    req_data = request.json
    username = req_data.get('username')
    current_password = req_data.get('current_password')
    new_password = req_data.get('new_password')
    
    if username not in data['users']:
        return {"error": "User not found"}, 404
    
    if data['users'][username]['password'] != current_password:
        return {"error": "Current password is incorrect"}, 401
    
    if not new_password:
        return {"error": "New password required"}, 400
    
    data['users'][username]['password'] = new_password
    return {"status": "updated"}, 200

@app.route("/update_settings", methods=["POST"])
def update_settings():
    """Update system settings"""
    req_data = request.json
    wifi_range = req_data.get('wifi_range')
    attendance_threshold = req_data.get('attendance_threshold')
    
    if wifi_range is not None:
        try:
            data['settings']['wifi_range'] = int(wifi_range)
        except ValueError:
            return {"error": "Invalid WiFi range value"}, 400
    
    if attendance_threshold is not None:
        try:
            data['settings']['attendance_threshold'] = int(attendance_threshold)
        except ValueError:
            return {"error": "Invalid attendance threshold value"}, 400
    
    return {"status": "updated", "settings": data['settings']}, 200

@app.route("/get_settings", methods=["GET"])
def get_settings():
    """Get current system settings"""
    return jsonify(data['settings'])

@app.route("/generate_report", methods=["GET"])
def generate_report():
    """Generate various attendance reports"""
    report_type = request.args.get('report_type')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    class_filter = request.args.get('class', '')
    output_format = request.args.get('format', 'json')
    
    try:
        # Parse dates if provided
        from_date_obj = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
        to_date_obj = datetime.strptime(to_date, "%Y-%m-%d") if to_date else None
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400
    
    # Initialize report data structure
    report_data = {
        'report_type': report_type,
        'date_range': f"{from_date} to {to_date}" if from_date and to_date else "All dates",
        'class_filter': class_filter if class_filter else "All classes",
        'generated_at': datetime.now().isoformat()
    }
    
    if report_type == 'daily_attendance_summary':
        # Generate daily summary report
        summary = defaultdict(lambda: {'present': 0, 'absent': 0, 'left': 0})
        
        for student_id, records in data['attendance_history'].items():
            student_class = data['students'].get(student_id, {}).get('class', '')
            if class_filter and student_class != class_filter:
                continue
                
            for record in records:
                record_date = record['date']
                if (from_date_obj and datetime.strptime(record_date, "%Y-%m-%d") < from_date_obj) or \
                   (to_date_obj and datetime.strptime(record_date, "%Y-%m-%d") > to_date_obj):
                    continue
                
                summary[record_date][record['status']] += 1
        
        report_data['summary'] = summary
    
    elif report_type == 'monthly_attendance_report':
        # Generate monthly report
        monthly = defaultdict(lambda: {'present': 0, 'absent': 0, 'left': 0})
        
        for student_id, records in data['attendance_history'].items():
            student_class = data['students'].get(student_id, {}).get('class', '')
            if class_filter and student_class != class_filter:
                continue
                
            for record in records:
                record_date = datetime.strptime(record['date'], "%Y-%m-%d")
                if (from_date_obj and record_date < from_date_obj) or \
                   (to_date_obj and record_date > to_date_obj):
                    continue
                
                month_key = record_date.strftime("%Y-%m")
                monthly[month_key][record['status']] += 1
        
        report_data['monthly'] = monthly
    
    elif report_type == 'student_attendance_history':
        # Generate detailed student attendance history
        student_history = []
        
        for student_id, records in data['attendance_history'].items():
            student_info = data['students'].get(student_id, {})
            student_class = student_info.get('class', '')
            
            if class_filter and student_class != class_filter:
                continue
                
            student_records = []
            for record in records:
                record_date = datetime.strptime(record['date'], "%Y-%m-%d")
                if (from_date_obj and record_date < from_date_obj) or \
                   (to_date_obj and record_date > to_date_obj):
                    continue
                
                student_records.append(record)
            
            if student_records:
                student_history.append({
                    'student_id': student_id,
                    'name': student_info.get('name', ''),
                    'class': student_class,
                    'records': student_records
                })
        
        report_data['student_history'] = student_history
    
    elif report_type == 'class_attendance_statistics':
        # Generate class-wise statistics
        class_stats = defaultdict(lambda: {'present': 0, 'absent': 0, 'left': 0, 'total': 0})
        
        for student_id, records in data['attendance_history'].items():
            student_class = data['students'].get(student_id, {}).get('class', '')
            if not student_class or (class_filter and student_class != class_filter):
                continue
                
            for record in records:
                record_date = datetime.strptime(record['date'], "%Y-%m-%d")
                if (from_date_obj and record_date < from_date_obj) or \
                   (to_date_obj and record_date > to_date_obj):
                    continue
                
                class_stats[student_class][record['status']] += 1
                class_stats[student_class]['total'] += 1
        
        # Calculate percentages
        for class_name, stats in class_stats.items():
            total = stats['total']
            if total > 0:
                stats['present_percent'] = round(stats['present'] / total * 100, 1)
                stats['absent_percent'] = round(stats['absent'] / total * 100, 1)
                stats['left_percent'] = round(stats['left'] / total * 100, 1)
        
        report_data['class_stats'] = class_stats
    
    else:
        return {"error": "Invalid report type"}, 400
    
    if output_format == 'csv':
        # Convert to CSV format (simplified for example)
        csv_data = []
        if 'summary' in report_data:
            for date, stats in report_data['summary'].items():
                csv_data.append([date, stats['present'], stats['absent'], stats['left']])
        elif 'monthly' in report_data:
            for month, stats in report_data['monthly'].items():
                csv_data.append([month, stats['present'], stats['absent'], stats['left']])
        # ... other report types
        
        return jsonify({'csv_data': csv_data})
    
    return jsonify(report_data)

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
                'last_update': datetime.now().isoformat(),
                'time_in': datetime.now().strftime("%H:%M:%S")
            }
    
    return {"status": "pong"}, 200

def cleanup_clients():
    """Periodically clean up disconnected clients"""
    while True:
        current_time = datetime.now()
        threshold_minutes = data['settings']['attendance_threshold']
        
        for student_id, info in list(data['attendance'].items()):
            if 'last_update' in info:
                last_update = datetime.fromisoformat(info['last_update'])
                if (current_time - last_update).total_seconds() > threshold_minutes * 60:
                    if info.get('status') == 'present':
                        info['status'] = 'left'
                        info['time_out'] = datetime.now().strftime("%H:%M:%S")
                        if 'time_in' in info:
                            time_in = datetime.strptime(info['time_in'], "%H:%M:%S")
                            duration = (datetime.now() - time_in).total_seconds() / 60
                            info['duration'] = f"{int(duration)} minutes"
        
        time.sleep(60)  # Check every minute

def start_random_rings():
    """Start periodic random rings"""
    while True:
        time.sleep(random.randint(120, 600))  # 2-10 minutes
        if data['active_session']:
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
    
    app.run(host="0.0.0.0", port=5000, debug=True)
