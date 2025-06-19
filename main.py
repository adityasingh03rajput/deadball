# server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
import random
from datetime import datetime
import hashlib
import secrets

app = Flask(__name__)
CORS(app)

# =========================
# IN-MEMORY DATABASE
# =========================
db = {
    "students": {},          # student_id: {details}
    "teachers": {},          # teacher_id: {details, password_hash, salt}
    "authorized_bssids": [], # List of authorized WiFi BSSIDs
    "current_session": None, # Current active session
    "session_log": [],       # History of past sessions
    "random_rings": {}       # Track random student selections
}

lock = threading.Lock()

# =========================
# UTILITIES
# =========================
def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt, hashed.hex()

def verify_password(stored_salt, stored_hash, password):
    _, new_hash = hash_password(password, stored_salt)
    return new_hash == stored_hash

def initialize_student(student_id):
    return {
        "name": f"Student {student_id}",
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
        "last_seen": None,
        "device_id": None
    }

def initialize_teacher(teacher_id, name, password):
    salt, password_hash = hash_password(password)
    return {
        "name": name,
        "password_hash": password_hash,
        "salt": salt,
        "registered": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# =========================
# BACKGROUND TIMER THREAD
# =========================
def update_timers():
    while True:
        with lock:
            current_time = time.time()
            for student_id, student in db["students"].items():
                timer = student.get("timer", {})
                if timer.get("running"):
                    elapsed = current_time - timer["last_update"]
                    timer["remaining"] = max(0, timer["remaining"] - elapsed)
                    timer["last_update"] = current_time
                    
                    if timer["remaining"] <= 0:
                        timer.update({
                            "remaining": 0,
                            "running": False,
                            "status": "completed"
                        })
                        student["attendance_status"] = "Attended"
                        student["leave_time"] = current_time_str()
                        
                        if db["current_session"] and student_id not in db["current_session"]["students_present"]:
                            db["current_session"]["students_present"].append(student_id)
            
            # Clean up old random rings
            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            to_delete = []
            for ring_id, ring_data in db["random_rings"].items():
                ring_time = datetime.strptime(ring_data["time"], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - ring_time).total_seconds() > 300:  # 5 minutes expiration
                    to_delete.append(ring_id)
            
            for ring_id in to_delete:
                del db["random_rings"][ring_id]
                
        time.sleep(1)

# Start the timer thread
timer_thread = threading.Thread(target=update_timers, daemon=True)
timer_thread.start()

# =========================
# AUTHENTICATION ENDPOINTS
# =========================
@app.route('/register_teacher', methods=['POST'])
def register_teacher():
    try:
        data = request.json
        teacher_id = data.get("teacher_id")
        name = data.get("name")
        password = data.get("password")
        
        if not all([teacher_id, name, password]):
            return jsonify({"error": "teacher_id, name and password are required"}), 400
            
        with lock:
            if teacher_id in db["teachers"]:
                return jsonify({"error": "Teacher already exists"}), 400
                
            db["teachers"][teacher_id] = initialize_teacher(teacher_id, name, password)
            
        return jsonify({"message": "Teacher registered successfully"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get("username")
        password = data.get("password")
        user_type = data.get("type")
        device_id = data.get("device_id", "")
        
        if not all([username, password, user_type]):
            return jsonify({"error": "username, password and type are required"}), 400
            
        with lock:
            if user_type == "teacher":
                if username not in db["teachers"]:
                    return jsonify({"error": "Teacher not found"}), 404
                    
                teacher = db["teachers"][username]
                if not verify_password(teacher["salt"], teacher["password_hash"], password):
                    return jsonify({"error": "Invalid password"}), 401
                    
                return jsonify({
                    "message": "Login successful",
                    "type": "teacher",
                    "name": teacher["name"]
                })
                
            elif user_type == "student":
                if username not in db["students"]:
                    db["students"][username] = initialize_student(username)
                    
                # Update student device info
                db["students"][username]["device_id"] = device_id
                db["students"][username]["last_seen"] = current_time_str()
                
                return jsonify({
                    "message": "Login successful",
                    "type": "student"
                })
                
            else:
                return jsonify({"error": "Invalid user type"}), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# TEACHER ENDPOINTS
# =========================
@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    try:
        bssids = request.json.get("bssids", [])
        if not isinstance(bssids, list):
            return jsonify({"error": "bssids should be an array"}), 400
            
        with lock:
            db["authorized_bssids"] = bssids
        return jsonify({"message": "BSSIDs updated", "bssids": bssids})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/start_session', methods=['POST'])
def start_session():
    try:
        session_name = request.json.get("session_name")
        if not session_name:
            return jsonify({"error": "session_name is required"}), 400
            
        with lock:
            db["current_session"] = {
                "name": session_name,
                "start_time": current_time_str(),
                "end_time": None,
                "students_present": []
            }
            
            # Reset all student attendance for new session
            for student in db["students"].values():
                student["attendance_status"] = "Absent"
                student["join_time"] = None
                student["leave_time"] = None
                student["timer"] = {
                    "duration": 120,
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                }
                
        return jsonify({"message": f"Session '{session_name}' started"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/end_session', methods=['POST'])
def end_session():
    try:
        with lock:
            if not db["current_session"]:
                return jsonify({"error": "No active session to end"}), 400
                
            db["current_session"]["end_time"] = current_time_str()
            db["session_log"].append(db["current_session"])
            db["current_session"] = None
            
        return jsonify({"message": "Session ended successfully"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/random_ring', methods=['POST'])
def random_ring():
    try:
        with lock:
            if not db["current_session"]:
                return jsonify({"error": "No active session"}), 400
                
            students = list(db["students"].items())
            if not students:
                return jsonify({"error": "No students registered"}), 400
                
            attended = [sid for sid, s in students if s.get("attendance_status") == "Attended"]
            absent = [sid for sid, s in students if s.get("attendance_status") == "Absent"]
            
            selection = []
            if attended:
                selection.append(random.choice(attended))
            if absent:
                selection.append(random.choice(absent))
                
            # Store the random selection
            ring_id = secrets.token_hex(8)
            db["random_rings"][ring_id] = {
                "students": selection,
                "time": current_time_str()
            }
            
        return jsonify({
            "message": "Random selection complete",
            "selected_students": selection,
            "ring_id": ring_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# STUDENT ENDPOINTS
# =========================
@app.route('/student/connect', methods=['POST'])
def student_connect():
    try:
        student_id = request.json.get("student_id")
        bssid = request.json.get("bssid")
        device_id = request.json.get("device_id", "")
        
        if not student_id:
            return jsonify({"error": "student_id is required"}), 400
        if not bssid:
            return jsonify({"error": "bssid is required"}), 400
            
        with lock:
            # Initialize student if not exists
            if student_id not in db["students"]:
                db["students"][student_id] = initialize_student(student_id)
                
            student = db["students"][student_id]
            is_authorized = bssid in db["authorized_bssids"]
            
            student.update({
                "connected": True,
                "authorized": is_authorized,
                "last_seen": current_time_str(),
                "device_id": device_id
            })
            
            if is_authorized and db["current_session"]:
                if student["attendance_status"] == "Absent":
                    student["attendance_status"] = "Pending"
                    student["join_time"] = current_time_str()
                    
        return jsonify({
            "message": "Connection successful",
            "authorized": is_authorized,
            "attendance_status": db["students"][student_id]["attendance_status"]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/student/timer/start', methods=['POST'])
def start_timer():
    try:
        student_id = request.json.get("student_id")
        if not student_id:
            return jsonify({"error": "student_id is required"}), 400
            
        with lock:
            if student_id not in db["students"]:
                return jsonify({"error": "Student not found"}), 404
                
            student = db["students"][student_id]
            
            if not student["authorized"]:
                return jsonify({"error": "Student not authorized"}), 403
                
            if not db["current_session"]:
                return jsonify({"error": "No active session"}), 400
                
            student["timer"] = {
                "duration": 120,
                "remaining": 120,
                "running": True,
                "last_update": time.time(),
                "status": "running"
            }
            student["attendance_status"] = "Pending"
            student["last_seen"] = current_time_str()
            
        return jsonify({"message": "Timer started successfully"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mark_present', methods=['POST'])
def mark_present():
    try:
        student_id = request.json.get("student_id")
        if not student_id:
            return jsonify({"error": "student_id is required"}), 400
            
        with lock:
            if student_id not in db["students"]:
                return jsonify({"error": "Student not found"}), 404
                
            student = db["students"][student_id]
            
            if not db["current_session"]:
                return jsonify({"error": "No active session"}), 400
                
            student["attendance_status"] = "Attended"
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "completed"
            }
            student["leave_time"] = current_time_str()
            student["last_seen"] = current_time_str()
            
            if db["current_session"] and student_id not in db["current_session"]["students_present"]:
                db["current_session"]["students_present"].append(student_id)
                
        return jsonify({"message": "Student marked as present"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# STATUS ENDPOINTS
# =========================
@app.route('/get_status', methods=['GET'])
def get_status():
    try:
        with lock:
            students_status = {
                sid: {
                    "name": student["name"],
                    "timer": student["timer"],
                    "connected": student["connected"],
                    "authorized": student["authorized"],
                    "attendance_status": student["attendance_status"],
                    "join_time": student["join_time"],
                    "leave_time": student["leave_time"],
                    "last_seen": student["last_seen"]
                }
                for sid, student in db["students"].items()
            }
            
            current_session = db["current_session"]
            if current_session:
                session_data = current_session.copy()
                session_data["student_count"] = len(students_status)
                session_data["present_count"] = len([s for s in students_status.values() 
                                                   if s["attendance_status"] == "Attended"])
            else:
                session_data = None
                
        return jsonify({
            "status": "success",
            "authorized_bssids": db["authorized_bssids"],
            "students": students_status,
            "current_session": session_data,
            "past_sessions": len(db["session_log"])
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_random_rings', methods=['GET'])
def get_random_rings():
    try:
        student_id = request.args.get("student_id")
        with lock:
            active_rings = []
            for ring_id, ring_data in db["random_rings"].items():
                if student_id in ring_data["students"]:
                    active_rings.append({
                        "ring_id": ring_id,
                        "time": ring_data["time"]
                    })
                    
            return jsonify({
                "ring_active": len(active_rings) > 0,
                "last_ring": active_rings[0]["time"] if active_rings else None
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# DEBUG/DEVELOPMENT ENDPOINTS
# =========================
@app.route('/reset', methods=['POST'])
def reset():
    try:
        with lock:
            db.update({
                "students": {},
                "teachers": {},
                "authorized_bssids": [],
                "current_session": None,
                "session_log": [],
                "random_rings": {}
            })
        return jsonify({"message": "System reset successfully"})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_sample_data', methods=['POST'])
def add_sample_data():
    try:
        with lock:
            # Add some sample BSSIDs
            db["authorized_bssids"] = ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]
            
            # Add some sample students
            for i in range(1, 6):
                student_id = f"student_{i}"
                db["students"][student_id] = initialize_student(student_id)
                db["students"][student_id]["name"] = f"Student {i}"
                
            # Add a sample teacher
            teacher_id = "teacher_1"
            db["teachers"][teacher_id] = initialize_teacher(teacher_id, "Professor Smith", "password123")
                
        return jsonify({
            "message": "Sample data added",
            "student_count": len(db["students"]),
            "teacher_count": len(db["teachers"]),
            "bssids": db["authorized_bssids"]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
