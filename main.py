from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading
import hashlib
import json
import os
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
CORS(app)

# In-memory database structure
data = {
    "teachers": {},
    "students": {},
    "sessions": {},
    "authorized_bssid": {},
    "random_rings": {},
    "timetables": {},
    "holidays": {}
}

lock = threading.Lock()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def update_timers():
    """Background thread to update all active timers"""
    while True:
        with lock:
            for student_id, student in data["students"].items():
                if "timer" in student and student["timer"]["running"]:
                    elapsed = time.time() - student["timer"]["last_update"]
                    student["timer"]["remaining"] = max(0, student["timer"]["remaining"] - elapsed)
                    student["timer"]["last_update"] = time.time()
                    
                    if student["timer"]["remaining"] <= 0:
                        student["timer"]["running"] = False
                        student["timer"]["status"] = "completed"
                        # Mark attendance as present when timer completes
                        if "current_session" in student:
                            session_id = student["current_session"]
                            if session_id in data["sessions"]:
                                date = datetime.now().strftime("%Y-%m-%d")
                                if "attendance" not in student:
                                    student["attendance"] = {}
                                if date not in student["attendance"]:
                                    student["attendance"][date] = {}
                                
                                session_key = f"session_{session_id}"
                                student["attendance"][date][session_key] = {
                                    "status": "present",
                                    "subject": data["sessions"][session_id]["subject"],
                                    "classroom": data["sessions"][session_id]["classroom"],
                                    "start_time": datetime.fromtimestamp(data["sessions"][session_id]["start_time"]).strftime("%H:%M:%S"),
                                    "end_time": datetime.now().strftime("%H:%M:%S"),
                                    "branch": data["sessions"][session_id].get("branch"),
                                    "semester": data["sessions"][session_id].get("semester")
                                }
        time.sleep(1)

# Start background timer thread
threading.Thread(target=update_timers, daemon=True).start()

# Teacher Endpoints
@app.route('/teacher/signup', methods=['POST'])
def teacher_signup():
    teacher_data = request.json
    if not all(key in teacher_data for key in ['id', 'password', 'email', 'name']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if teacher_data['id'] in data["teachers"]:
            return jsonify({"error": "Teacher ID already exists"}), 400
        
        data["teachers"][teacher_data['id']] = {
            "id": teacher_data['id'],
            "password": hash_password(teacher_data['password']),
            "email": teacher_data['email'],
            "name": teacher_data['name'],
            "classrooms": [],
            "branches": [],
            "semesters": [],
            "bssid_mapping": {}
        }
        
    return jsonify({"message": "Teacher registered successfully"}), 201

@app.route('/teacher/login', methods=['POST'])
def teacher_login():
    login_data = request.json
    if not all(key in login_data for key in ['id', 'password']):
        return jsonify({"error": "ID and password required"}), 400
    
    with lock:
        if login_data['id'] not in data["teachers"]:
            return jsonify({"error": "Teacher not found"}), 404
        
        teacher = data["teachers"][login_data['id']]
        if teacher["password"] != hash_password(login_data['password']):
            return jsonify({"error": "Invalid password"}), 401
        
        # Return teacher data without password
        teacher_data = teacher.copy()
        del teacher_data["password"]
        return jsonify({"teacher": teacher_data}), 200

@app.route('/teacher/register_student', methods=['POST'])
def register_student():
    student_data = request.json
    if not all(key in student_data for key in ['id', 'password', 'name', 'classroom', 'branch', 'semester']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if student_data['id'] in data["students"]:
            return jsonify({"error": "Student ID already exists"}), 400
        
        # Add classroom, branch, semester to teacher's lists if not exists
        teacher_id = student_data.get('teacher_id')
        if teacher_id and teacher_id in data["teachers"]:
            teacher = data["teachers"][teacher_id]
            if student_data['classroom'] not in teacher["classrooms"]:
                teacher["classrooms"].append(student_data['classroom'])
            if student_data['branch'] not in teacher["branches"]:
                teacher["branches"].append(student_data['branch'])
            if student_data['semester'] not in teacher["semesters"]:
                teacher["semesters"].append(student_data['semester'])
        
        data["students"][student_data['id']] = {
            "id": student_data['id'],
            "password": student_data['password'],  # Already hashed by client
            "name": student_data['name'],
            "classroom": student_data['classroom'],
            "branch": student_data['branch'],
            "semester": student_data['semester'],
            "attendance": {},
            "devices": {},
            "last_login": time.time()
        }
        
    return jsonify({"message": "Student registered successfully"}), 201

@app.route('/teacher/get_students', methods=['GET'])
def get_students():
    classroom = request.args.get('classroom')
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    
    filtered_students = []
    with lock:
        for student_id, student in data["students"].items():
            if (not classroom or student["classroom"] == classroom) and \
               (not branch or student["branch"] == branch) and \
               (not semester or student["semester"] == semester):
                filtered_students.append(student)
    
    return jsonify({"students": filtered_students}), 200

@app.route('/teacher/update_student', methods=['POST'])
def update_student():
    update_data = request.json
    if not all(key in update_data for key in ['id', 'new_data']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if update_data['id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        data["students"][update_data['id']].update(update_data['new_data'])
        return jsonify({"message": "Student updated successfully"}), 200

@app.route('/teacher/delete_student', methods=['POST'])
def delete_student():
    student_id = request.json.get('id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        del data["students"][student_id]
        return jsonify({"message": "Student deleted successfully"}), 200

@app.route('/teacher/update_profile', methods=['POST'])
def update_teacher_profile():
    update_data = request.json
    if not all(key in update_data for key in ['id', 'new_data']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if update_data['id'] not in data["teachers"]:
            return jsonify({"error": "Teacher not found"}), 404
        
        data["teachers"][update_data['id']].update(update_data['new_data'])
        return jsonify({"message": "Profile updated successfully"}), 200

@app.route('/teacher/change_password', methods=['POST'])
def change_teacher_password():
    password_data = request.json
    if not all(key in password_data for key in ['id', 'old_password', 'new_password']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if password_data['id'] not in data["teachers"]:
            return jsonify({"error": "Teacher not found"}), 404
        
        teacher = data["teachers"][password_data['id']]
        if teacher["password"] != hash_password(password_data['old_password']):
            return jsonify({"error": "Current password is incorrect"}), 401
        
        teacher["password"] = hash_password(password_data['new_password'])
        return jsonify({"message": "Password changed successfully"}), 200

@app.route('/teacher/update_bssid', methods=['POST'])
def update_bssid_mapping():
    bssid_data = request.json
    if not all(key in bssid_data for key in ['teacher_id', 'classroom', 'bssid']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if bssid_data['teacher_id'] not in data["teachers"]:
            return jsonify({"error": "Teacher not found"}), 404
        
        teacher = data["teachers"][bssid_data['teacher_id']]
        if "bssid_mapping" not in teacher:
            teacher["bssid_mapping"] = {}
        
        teacher["bssid_mapping"][bssid_data['classroom']] = bssid_data['bssid']
        
        # Also update global authorized BSSIDs
        if "authorized_bssid" not in data:
            data["authorized_bssid"] = {}
        data["authorized_bssid"][bssid_data['classroom']] = bssid_data['bssid']
        
        return jsonify({"message": "BSSID mapping updated successfully"}), 200

@app.route('/teacher/start_session', methods=['POST'])
def start_session():
    session_data = request.json
    if not all(key in session_data for key in ['teacher_id', 'classroom', 'subject']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        # Check if teacher exists
        if session_data['teacher_id'] not in data["teachers"]:
            return jsonify({"error": "Teacher not found"}), 404
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        data["sessions"][session_id] = {
            "id": session_id,
            "teacher_id": session_data['teacher_id'],
            "classroom": session_data['classroom'],
            "subject": session_data['subject'],
            "branch": session_data.get('branch'),
            "semester": session_data.get('semester'),
            "start_time": time.time(),
            "end_time": None,
            "active": True,
            "ad_hoc": session_data.get('ad_hoc', False)
        }
        
        return jsonify({"session_id": session_id, "message": "Session started successfully"}), 201

@app.route('/teacher/end_session', methods=['POST'])
def end_session():
    session_data = request.json
    if not session_data.get('session_id'):
        return jsonify({"error": "Session ID required"}), 400
    
    with lock:
        if session_data['session_id'] not in data["sessions"]:
            return jsonify({"error": "Session not found"}), 404
        
        data["sessions"][session_data['session_id']]["end_time"] = time.time()
        data["sessions"][session_data['session_id']]["active"] = False
        
        # Clear current session from students
        for student_id, student in data["students"].items():
            if "current_session" in student and student["current_session"] == session_data['session_id']:
                del student["current_session"]
        
        return jsonify({"message": "Session ended successfully"}), 200

@app.route('/teacher/get_active_sessions', methods=['GET'])
def get_active_sessions():
    teacher_id = request.args.get('teacher_id')
    
    active_sessions = []
    with lock:
        for session_id, session in data["sessions"].items():
            if session["active"] and (not teacher_id or session["teacher_id"] == teacher_id):
                active_sessions.append({
                    "id": session_id,
                    "subject": session["subject"],
                    "classroom": session["classroom"],
                    "branch": session.get("branch"),
                    "semester": session.get("semester"),
                    "start_time": datetime.fromtimestamp(session["start_time"]).strftime("%Y-%m-%d %H:%M:%S")
                })
    
    return jsonify({"sessions": active_sessions}), 200

@app.route('/teacher/set_bssid', methods=['POST'])
def set_bssid():
    bssid_data = request.json
    if not bssid_data.get('bssid'):
        return jsonify({"error": "BSSID required"}), 400
    
    with lock:
        if "authorized_bssid" not in data:
            data["authorized_bssid"] = {}
        
        # This is a global setting (for quick server demo)
        data["authorized_bssid"]["default"] = bssid_data['bssid']
        
        return jsonify({"message": f"Authorized BSSID set to {bssid_data['bssid']}"}), 200

@app.route('/teacher/get_status', methods=['GET'])
def get_status():
    classroom = request.args.get('classroom')
    
    status_data = {
        "authorized_bssid": data["authorized_bssid"].get(classroom or "default") if data["authorized_bssid"] else None,
        "students": {}
    }
    
    with lock:
        for student_id, student in data["students"].items():
            if not classroom or student.get("classroom") == classroom:
                status_data["students"][student_id] = {
                    "name": student.get("name", ""),
                    "timer": student.get("timer", {
                        "duration": 300,
                        "remaining": 0,
                        "running": False,
                        "last_update": None,
                        "status": "stopped"
                    }),
                    "connected": "current_bssid" in student,
                    "authorized": student.get("current_bssid") == data["authorized_bssid"].get(classroom or "default"),
                    "current_bssid": student.get("current_bssid")
                }
    
    return jsonify(status_data), 200

@app.route('/teacher/manual_override', methods=['POST'])
def manual_override():
    override_data = request.json
    if not all(key in override_data for key in ['student_id', 'status']):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if override_data['student_id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][override_data['student_id']]
        
        if override_data['status'] == "present":
            # Mark student as present
            if "current_session" in student:
                session_id = student["current_session"]
                if session_id in data["sessions"]:
                    date = datetime.now().strftime("%Y-%m-%d")
                    if "attendance" not in student:
                        student["attendance"] = {}
                    if date not in student["attendance"]:
                        student["attendance"][date] = {}
                    
                    session_key = f"session_{session_id}"
                    student["attendance"][date][session_key] = {
                        "status": "present",
                        "subject": data["sessions"][session_id]["subject"],
                        "classroom": data["sessions"][session_id]["classroom"],
                        "start_time": datetime.fromtimestamp(data["sessions"][session_id]["start_time"]).strftime("%H:%M:%S"),
                        "end_time": datetime.now().strftime("%H:%M:%S"),
                        "branch": data["sessions"][session_id].get("branch"),
                        "semester": data["sessions"][session_id].get("semester")
                    }
        elif override_data['status'] == "absent":
            # Mark student as absent
            if "current_session" in student:
                session_id = student["current_session"]
                if session_id in data["sessions"]:
                    date = datetime.now().strftime("%Y-%m-%d")
                    if "attendance" not in student:
                        student["attendance"] = {}
                    if date not in student["attendance"]:
                        student["attendance"][date] = {}
                    
                    session_key = f"session_{session_id}"
                    student["attendance"][date][session_key] = {
                        "status": "absent",
                        "subject": data["sessions"][session_id]["subject"],
                        "classroom": data["sessions"][session_id]["classroom"],
                        "start_time": datetime.fromtimestamp(data["sessions"][session_id]["start_time"]).strftime("%H:%M:%S"),
                        "end_time": datetime.now().strftime("%H:%M:%S"),
                        "branch": data["sessions"][session_id].get("branch"),
                        "semester": data["sessions"][session_id].get("semester")
                    }
        
        return jsonify({"message": f"Student marked as {override_data['status']}"}), 200

@app.route('/teacher/random_ring', methods=['POST'])
def random_ring():
    classroom = request.args.get('classroom')
    if not classroom:
        return jsonify({"error": "Classroom required"}), 400
    
    with lock:
        # Get all students in the classroom
        classroom_students = []
        for student_id, student in data["students"].items():
            if student.get("classroom") == classroom and "attendance" in student:
                # Calculate attendance percentage
                total_sessions = 0
                present_sessions = 0
                
                for date, sessions in student["attendance"].items():
                    for session_key, session in sessions.items():
                        if session.get("status") == "present":
                            present_sessions += 1
                        total_sessions += 1
                
                attendance_percent = round((present_sessions / total_sessions * 100)) if total_sessions > 0 else 0
                
                classroom_students.append({
                    "id": student_id,
                    "name": student.get("name", ""),
                    "attendance_percentage": attendance_percent
                })
        
        if len(classroom_students) < 2:
            return jsonify({"error": "Not enough students in classroom"}), 400
        
        # Sort by attendance percentage
        classroom_students.sort(key=lambda x: x["attendance_percentage"])
        
        # Select one with lowest and one with highest attendance
        low_student = classroom_students[0]
        high_student = classroom_students[-1]
        
        # Store the random ring selection
        ring_id = str(uuid.uuid4())
        data["random_rings"][ring_id] = {
            "low_student": low_student["id"],
            "high_student": high_student["id"],
            "timestamp": time.time()
        }
        
        return jsonify({
            "low_attendance_student": low_student,
            "high_attendance_student": high_student
        }), 200

# Student Endpoints
@app.route('/student/login', methods=['POST'])
def student_login():
    login_data = request.json
    if not all(key in login_data for key in ['id', 'password', 'device_id']):
        return jsonify({"error": "ID, password and device ID required"}), 400
    
    with lock:
        if login_data['id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][login_data['id']]
        if student["password"] != login_data['password']:  # Password is already hashed
            return jsonify({"error": "Invalid password"}), 401
        
        # Register device
        if "devices" not in student:
            student["devices"] = {}
        student["devices"][login_data['device_id']] = {
            "last_login": time.time(),
            "ip": request.remote_addr
        }
        student["last_login"] = time.time()
        
        # Return student data without password
        student_data = {
            "id": student["id"],
            "name": student["name"],
            "classroom": student["classroom"],
            "branch": student["branch"],
            "semester": student["semester"]
        }
        
        return jsonify(student_data), 200

@app.route('/student/connect', methods=['POST'])
def student_connect():
    connect_data = request.json
    if not all(key in connect_data for key in ['student_id', 'bssid']):
        return jsonify({"error": "Student ID and BSSID required"}), 400
    
    with lock:
        if connect_data['student_id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][connect_data['student_id']]
        student["current_bssid"] = connect_data['bssid']
        
        # Check if connected to authorized BSSID
        authorized = False
        classroom_bssid = data["authorized_bssid"].get(student["classroom"])
        if classroom_bssid and connect_data['bssid'].lower() == classroom_bssid.lower():
            authorized = True
        
        # Check for active session in student's classroom
        active_session = None
        for session_id, session in data["sessions"].items():
            if session["active"] and session["classroom"] == student["classroom"]:
                active_session = session_id
                break
        
        if active_session:
            student["current_session"] = active_session
        
        return jsonify({
            "authorized": authorized,
            "active_session": bool(active_session),
            "message": "Connected successfully"
        }), 200

@app.route('/student/start_timer', methods=['POST'])
def start_timer():
    timer_data = request.json
    if not all(key in timer_data for key in ['student_id', 'device_id', 'bssid']):
        return jsonify({"error": "Student ID, device ID and BSSID required"}), 400
    
    with lock:
        if timer_data['student_id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][timer_data['student_id']]
        
        # Verify BSSID
        classroom_bssid = data["authorized_bssid"].get(student["classroom"])
        if not classroom_bssid or timer_data['bssid'].lower() != classroom_bssid.lower():
            return jsonify({"error": "Not connected to authorized WiFi"}), 403
        
        # Check for active session
        if "current_session" not in student:
            return jsonify({"error": "No active session"}), 400
        
        # Start timer
        student["timer"] = {
            "duration": 300,  # 5 minutes
            "remaining": 300,
            "running": True,
            "last_update": time.time(),
            "status": "running"
        }
        
        return jsonify({"message": "Timer started successfully"}), 200

@app.route('/student/timer/<action>', methods=['POST'])
def timer_action(action):
    timer_data = request.json
    if not timer_data.get('student_id'):
        return jsonify({"error": "Student ID required"}), 400
    
    if action not in ["start", "pause", "stop"]:
        return jsonify({"error": "Invalid action"}), 400
    
    with lock:
        if timer_data['student_id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][timer_data['student_id']]
        
        if "timer" not in student:
            return jsonify({"error": "No timer active"}), 400
        
        if action == "start":
            if student["timer"]["running"]:
                return jsonify({"error": "Timer already running"}), 400
            
            student["timer"]["running"] = True
            student["timer"]["last_update"] = time.time()
            student["timer"]["status"] = "running"
        elif action == "pause":
            if not student["timer"]["running"]:
                return jsonify({"error": "Timer not running"}), 400
            
            student["timer"]["running"] = False
            student["timer"]["status"] = "paused"
        elif action == "stop":
            student["timer"]["running"] = False
            student["timer"]["remaining"] = 0
            student["timer"]["status"] = "stopped"
        
        return jsonify({"message": f"Timer {action}ed successfully"}), 200

@app.route('/student/get_active_session', methods=['GET'])
def get_active_session():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][student_id]
        
        # Check if student has an active session
        if "current_session" in student and student["current_session"] in data["sessions"]:
            session = data["sessions"][student["current_session"]]
            if session["active"]:
                return jsonify({
                    "active": True,
                    "subject": session["subject"],
                    "classroom": session["classroom"]
                }), 200
        
        return jsonify({"active": False}), 200

@app.route('/student/get_authorized_bssid', methods=['GET'])
def get_authorized_bssid():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][student_id]
        bssid = data["authorized_bssid"].get(student["classroom"])
        
        return jsonify({"bssid": bssid}), 200

@app.route('/student/get_random_ring', methods=['GET'])
def get_random_ring():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        # Check if this student was recently selected in a random ring
        active_ring = None
        for ring_id, ring in data["random_rings"].items():
            if time.time() - ring["timestamp"] < 300:  # 5 minute window
                if student_id in [ring["low_student"], ring["high_student"]]:
                    active_ring = ring_id
                    break
        
        if active_ring:
            return jsonify({
                "active": True,
                "ring_id": active_ring
            }), 200
        
        return jsonify({"active": False}), 200

@app.route('/student/get_attendance', methods=['GET'])
def get_attendance():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][student_id]
        
        # Get holidays from global data
        holidays = data.get("holidays", {})
        
        return jsonify({
            "attendance": student.get("attendance", {}),
            "holidays": holidays
        }), 200

@app.route('/student/get_timetable', methods=['GET'])
def get_timetable():
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][student_id]
        timetable_key = f"{student['branch']}_{student['semester']}"
        
        return jsonify({
            "timetable": data["timetables"].get(timetable_key, {})
        }), 200

@app.route('/student/ping', methods=['POST'])
def student_ping():
    ping_data = request.json
    if not all(key in ping_data for key in ['student_id', 'device_id']):
        return jsonify({"error": "Student ID and device ID required"}), 400
    
    with lock:
        if ping_data['student_id'] not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = data["students"][ping_data['student_id']]
        if "devices" not in student:
            student["devices"] = {}
        
        student["devices"][ping_data['device_id']] = {
            "last_ping": time.time(),
            "ip": request.remote_addr
        }
        
        return jsonify({"message": "Ping received"}), 200

# Common Endpoints
@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    bssid_data = request.json
    if not bssid_data.get('bssid'):
        return jsonify({"error": "BSSID required"}), 400
    
    with lock:
        if "authorized_bssid" not in data:
            data["authorized_bssid"] = {}
        
        # This is a global setting (for quick server demo)
        data["authorized_bssid"]["default"] = bssid_data['bssid']
        
        return jsonify({"message": f"Authorized BSSID set to {bssid_data['bssid']}"}), 200

@app.route('/get_status', methods=['GET'])
def get_status_quick():
    with lock:
        status_data = {
            "authorized_bssid": data["authorized_bssid"].get("default") if data["authorized_bssid"] else None,
            "students": {}
        }
        
        for student_id, student in data["students"].items():
            status_data["students"][student_id] = {
                "name": student.get("name", ""),
                "timer": student.get("timer", {
                    "duration": 300,
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                }),
                "connected": "current_bssid" in student,
                "authorized": student.get("current_bssid") == data["authorized_bssid"].get("default"),
                "current_bssid": student.get("current_bssid")
            }
        
        return jsonify(status_data), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
