from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)

# =========================
# IN-MEMORY DATABASE
# =========================
db = {
    "users": {
        # username: {password, type, name, class, device_id, last_seen}
        "teacher1": {"password": "pass1", "type": "teacher", "name": "Teacher One", "device_id": None, "last_seen": None},
        "student1": {"password": "pass1", "type": "student", "name": "Student One", "class": "Grade 1", "device_id": None, "last_seen": None},
    },
    "students": {
        # student_id: {details}
        "student1": {
            "name": "Student One",
            "class": "Grade 1",
            "timer": {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            },
            "connected": False,
            "authorized": False,
            "attendance_status": "Absent",
            "join_time": None,
            "leave_time": None,
            "attendance_history": []
        }
    },
    "teachers": {
        # teacher_id: {details}
        "teacher1": {
            "name": "Teacher One",
            "classes": ["Grade 1"]
        }
    },
    "authorized_bssids": ["aa:bb:cc:dd:ee:ff"],
    "current_session": None,
    "session_log": [],
    "timetable": {
        "Monday": {
            "09:40-10:40 AM": "Math",
            "10:40-11:40 AM": "Science",
            "Lunch Break": "",
            "12:10-01:10 PM": "History",
            "01:10-02:10 PM": "English",
            "Short Break": "",
            "02:20-03:10 PM": "Art",
            "03:10-04:10 PM": "Physical Education"
        },
        # ... similar for other days
    },
    "holidays": {
        "national_holidays": {
            "2023-01-26": {"name": "Republic Day"},
            "2023-08-15": {"name": "Independence Day"}
        },
        "custom_holidays": {}
    },
    "random_ring": {
        "active": False,
        "selected_students": []
    }
}

lock = threading.Lock()

# =========================
# UTILITIES
# =========================
def get_attendance_status(timer_status):
    return {
        "stopped": "Absent",
        "running": "Pending",
        "paused": "On Bunk",
        "completed": "Attended"
    }.get(timer_status, "Unknown")

def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def validate_user(username, password, user_type):
    user = db["users"].get(username)
    if user and user["password"] == password and user["type"] == user_type:
        return True
    return False

# =========================
# BACKGROUND TIMER THREAD
# =========================
def update_timers():
    while True:
        with lock:
            for student_id, student in db["students"].items():
                timer = student.get("timer", {})
                if timer.get("running"):
                    now = time.time()
                    elapsed = now - timer["last_update"]
                    timer["remaining"] -= elapsed
                    timer["last_update"] = now
                    if timer["remaining"] <= 0:
                        timer.update({
                            "remaining": 0,
                            "running": False,
                            "status": "completed"
                        })
                        student["attendance_status"] = "Attended"
                        student["leave_time"] = current_time_str()
                        # Add to attendance history
                        if db["current_session"]:
                            student["attendance_history"].append({
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "status": "present",
                                "session": db["current_session"]["name"],
                                "timestamp": current_time_str()
                            })
        time.sleep(1)

threading.Thread(target=update_timers, daemon=True).start()

# =========================
# AUTHENTICATION ENDPOINTS
# =========================
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    user_type = data.get("type")
    device_id = data.get("device_id")
    
    if not all([username, password, user_type]):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if validate_user(username, password, user_type):
            db["users"][username]["device_id"] = device_id
            db["users"][username]["last_seen"] = current_time_str()
            return jsonify({
                "message": "Login successful",
                "name": db["users"][username].get("name", ""),
                "class": db["users"][username].get("class", "")
            })
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get("name")
    username = data.get("username")
    password = data.get("password")
    user_type = data.get("type")
    
    if not all([name, username, password, user_type]):
        return jsonify({"error": "Missing required fields"}), 400
    
    with lock:
        if username in db["users"]:
            return jsonify({"error": "Username already exists"}), 400
        
        db["users"][username] = {
            "password": password,
            "type": user_type,
            "name": name,
            "device_id": None,
            "last_seen": None
        }
        
        if user_type == "student":
            class_name = data.get("class", "Grade 1")
            db["users"][username]["class"] = class_name
            db["students"][username] = {
                "name": name,
                "class": class_name,
                "timer": {
                    "duration": 120,
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                },
                "connected": False,
                "authorized": False,
                "attendance_status": "Absent",
                "join_time": None,
                "leave_time": None,
                "attendance_history": []
            }
        elif user_type == "teacher":
            db["teachers"][username] = {
                "name": name,
                "classes": [data.get("class", "Grade 1")]
            }
        
        return jsonify({"message": "Registration successful"}), 201

@app.route('/logout', methods=['POST'])
def logout():
    data = request.json
    username = data.get("username")
    
    with lock:
        if username in db["users"]:
            db["users"][username]["device_id"] = None
            db["users"][username]["last_seen"] = current_time_str()
    
    return jsonify({"message": "Logged out"})

# =========================
# TEACHER ACTIONS
# =========================
@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    bssids = request.json.get("bssids", [])
    with lock:
        db["authorized_bssids"] = bssids
    return jsonify({"message": "BSSIDs updated", "bssids": bssids})

@app.route('/start_session', methods=['POST'])
def start_session():
    session_name = request.json.get("session_name")
    teacher = request.json.get("teacher")
    
    if not session_name:
        return jsonify({"error": "Session name required"}), 400
    
    with lock:
        db["current_session"] = {
            "name": session_name,
            "teacher": teacher,
            "start_time": current_time_str(),
            "students_present": []
        }
        for student in db["students"].values():
            student["attendance_status"] = "Absent"
            student["join_time"] = None
            student["leave_time"] = None
    return jsonify({"message": f"Session '{session_name}' started"})

@app.route('/end_session', methods=['POST'])
def end_session():
    with lock:
        session = db["current_session"]
        if session:
            session["end_time"] = current_time_str()
            db["session_log"].append(session)
            db["current_session"] = None
            return jsonify({"message": "Session ended"})
        else:
            return jsonify({"error": "No active session"}), 400

@app.route('/random_ring', methods=['POST'])
def random_ring():
    with lock:
        students = list(db["students"].items())
        attended = [sid for sid, s in students if s.get("attendance_status") == "Attended"]
        absent = [sid for sid, s in students if s.get("attendance_status") == "Absent"]
        selection = []
        if attended:
            selection.append(random.choice(attended))
        if absent:
            selection.append(random.choice(absent))
        
        db["random_ring"] = {
            "active": True,
            "selected_students": selection
        }
    return jsonify({"selected_students": selection})

@app.route('/check_random_ring', methods=['GET'])
def check_random_ring_status():
    with lock:
        return jsonify(db["random_ring"])

@app.route('/check_random_ring_student', methods=['GET'])
def check_random_ring_student():
    student_id = request.args.get("student_id")
    with lock:
        if db["random_ring"]["active"] and student_id in db["random_ring"]["selected_students"]:
            return jsonify({
                "ring_active": True,
                "message": f"Teacher has called on you, {db['students'][student_id]['name']}!"
            })
        return jsonify({"ring_active": False})

@app.route('/mark_present', methods=['POST'])
def mark_present():
    student_id = request.json.get("student_id")
    teacher = request.json.get("teacher")
    
    with lock:
        student = db["students"].get(student_id)
        if student:
            student["attendance_status"] = "Attended"
            student["timer"]["status"] = "completed"
            student["timer"]["running"] = False
            student["timer"]["remaining"] = 0
            student["leave_time"] = current_time_str()
            
            if db["current_session"]:
                db["current_session"]["students_present"].append(student_id)
                student["attendance_history"].append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "status": "present",
                    "session": db["current_session"]["name"],
                    "timestamp": current_time_str()
                })
            
            return jsonify({"message": "Marked present"})
        return jsonify({"error": "Student not found"}), 404

# =========================
# STUDENT ACTIONS
# =========================
@app.route('/student/connect', methods=['POST'])
def student_connect():
    student_id = request.json.get("student_id")
    bssid = request.json.get("bssid")

    if not student_id or not bssid:
        return jsonify({"error": "student_id and bssid required"}), 400

    with lock:
        student = db["students"].setdefault(student_id, {
            "name": f"Student {student_id}",
            "class": "Grade 1",
            "timer": {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            },
            "connected": False,
            "authorized": False,
            "attendance_status": "Absent",
            "join_time": None,
            "leave_time": None,
            "attendance_history": []
        })

        is_authorized = bssid.lower() in [b.lower() for b in db["authorized_bssids"]]
        student["connected"] = True
        student["authorized"] = is_authorized

        if is_authorized:
            student["attendance_status"] = "Pending"
            student["join_time"] = current_time_str()

        return jsonify({
            "authorized": is_authorized,
            "attendance_status": student["attendance_status"]
        })

@app.route('/student/timer/start', methods=['POST'])
def start_timer():
    student_id = request.json.get("student_id")
    with lock:
        student = db["students"].get(student_id)
        if not student:
            return jsonify({"error": "Student not found"}), 404
        if not student["authorized"]:
            return jsonify({"error": "Not authorized"}), 403

        student["timer"] = {
            "duration": 120,
            "remaining": 120,
            "running": True,
            "last_update": time.time(),
            "status": "running"
        }
        student["attendance_status"] = "Pending"
    return jsonify({"message": "Timer started"})

# =========================
# DATA FETCHING ENDPOINTS
# =========================
@app.route('/get_status', methods=['GET'])
def get_status():
    with lock:
        students_status = {}
        for sid, student in db["students"].items():
            timer = student.get("timer", {})
            attendance = student.get("attendance_status", "Unknown")
            students_status[sid] = {
                "name": student["name"],
                "timer": timer,
                "connected": student["connected"],
                "authorized": student["authorized"],
                "attendance_status": attendance,
                "join_time": student.get("join_time"),
                "leave_time": student.get("leave_time")
            }

        return jsonify({
            "authorized_bssids": db["authorized_bssids"],
            "students": students_status,
            "current_session": db["current_session"]
        })

@app.route('/check_attendance_session', methods=['GET'])
def check_attendance_session():
    with lock:
        return jsonify({
            "active": db["current_session"] is not None,
            "session": db["current_session"]
        })

@app.route('/get_students', methods=['GET'])
def get_students():
    teacher = request.args.get("teacher")
    with lock:
        students = []
        for sid, student in db["students"].items():
            students.append({
                "id": sid,
                "name": student["name"],
                "class": student.get("class", "N/A"),
                "last_seen": db["users"].get(sid, {}).get("last_seen", "Never")
            })
        return jsonify(students)

@app.route('/student_details/<student_id>', methods=['GET'])
def student_details(student_id):
    with lock:
        student = db["students"].get(student_id)
        if not student:
            return jsonify({"error": "Student not found"}), 404
        
        user_info = db["users"].get(student_id, {})
        
        details = {
            "id": student_id,
            "name": student["name"],
            "class": student.get("class", "N/A"),
            "email": user_info.get("email", "N/A"),
            "phone": user_info.get("phone", "N/A"),
            "last_seen": user_info.get("last_seen", "Never")
        }
        return jsonify(details)

@app.route('/student_attendance/<student_id>', methods=['GET'])
def student_attendance(student_id):
    with lock:
        student = db["students"].get(student_id)
        if not student:
            return jsonify({"error": "Student not found"}), 404
        
        present = len([r for r in student["attendance_history"] if r["status"] == "present"])
        absent = len([r for r in student["attendance_history"] if r["status"] == "absent"])
        total = present + absent
        percent = (present / total * 100) if total > 0 else 0
        
        return jsonify({
            "total_classes": total,
            "present": present,
            "absent": absent,
            "attendance_percent": percent,
            "attendance_history": student["attendance_history"]
        })

@app.route('/get_timetable', methods=['GET'])
def get_timetable():
    with lock:
        return jsonify(db["timetable"])

@app.route('/save_timetable', methods=['POST'])
def save_timetable():
    timetable = request.json.get("timetable")
    teacher = request.json.get("teacher")
    
    if not timetable:
        return jsonify({"error": "Timetable data required"}), 400
    
    with lock:
        db["timetable"] = timetable
        return jsonify({"message": "Timetable saved"})

@app.route('/get_bssids', methods=['GET'])
def get_bssids():
    with lock:
        return jsonify({"bssids": db["authorized_bssids"]})

@app.route('/add_bssid', methods=['POST'])
def add_bssid():
    bssid = request.json.get("bssid")
    teacher = request.json.get("teacher")
    
    if not bssid:
        return jsonify({"error": "BSSID required"}), 400
    
    with lock:
        if bssid not in db["authorized_bssids"]:
            db["authorized_bssids"].append(bssid)
        return jsonify({"message": "BSSID added"})

@app.route('/remove_bssid', methods=['POST'])
def remove_bssid():
    bssid = request.json.get("bssid")
    teacher = request.json.get("teacher")
    
    if not bssid:
        return jsonify({"error": "BSSID required"}), 400
    
    with lock:
        if bssid in db["authorized_bssids"]:
            db["authorized_bssids"].remove(bssid)
        return jsonify({"message": "BSSID removed"})

@app.route('/update_wifi_status', methods=['POST'])
def update_wifi_status():
    data = request.json
    username = data.get("username")
    status = data.get("status")
    bssid = data.get("bssid")
    ssid = data.get("ssid")
    device = data.get("device_id")
    
    with lock:
        if username in db["users"]:
            db["users"][username]["device_id"] = device
            db["users"][username]["last_seen"] = current_time_str()
        
        if username in db["students"]:
            db["students"][username]["connected"] = (status == "connected")
            if bssid:
                db["students"][username]["authorized"] = bssid.lower() in [b.lower() for b in db["authorized_bssids"]]
    
    return jsonify({"message": "Status updated"})

@app.route('/generate_report', methods=['POST'])
def generate_report():
    report_type = request.json.get("type")
    from_date = request.json.get("from_date")
    to_date = request.json.get("to_date")
    class_filter = request.json.get("class")
    teacher = request.json.get("teacher")
    
    # Simple report generation - in a real app this would query the database
    with lock:
        report = f"Attendance Report ({report_type})\n"
        report += f"Period: {from_date} to {to_date}\n"
        report += f"Class: {class_filter}\n\n"
        
        if report_type == "Daily Attendance Summary":
            report += "Daily Summary:\n"
            # Add sample data
            report += "2023-01-01: 20/25 students present (80%)\n"
            report += "2023-01-02: 22/25 students present (88%)\n"
        elif report_type == "Monthly Attendance Report":
            report += "Monthly Summary for January 2023:\n"
            report += "Total classes: 20\n"
            report += "Average attendance: 85%\n"
        elif report_type == "Student Attendance History":
            report += "Student Attendance History:\n"
            # Add sample data
            report += "Student1: 18/20 (90%)\n"
            report += "Student2: 15/20 (75%)\n"
        elif report_type == "Class Attendance Statistics":
            report += "Class Statistics:\n"
            report += "Total students: 25\n"
            report += "Average attendance: 82%\n"
            report += "Top student: Student1 (95%)\n"
            report += "Lowest student: Student5 (65%)\n"
        
        return jsonify({"report": report})

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
