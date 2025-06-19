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
    "students": {},  # student_id: {details}
    "teachers": {},  # teacher_id: {details}
    "authorized_bssids": [],
    "current_session": None,
    "session_log": []
}

lock = threading.Lock()

# =========================
# UTILITIES
# =========================
def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        "leave_time": None
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
                        
                        # Add to session's present students if session exists
                        if db["current_session"]:
                            if student_id not in db["current_session"]["students_present"]:
                                db["current_session"]["students_present"].append(student_id)
        time.sleep(1)

# Start the timer thread
timer_thread = threading.Thread(target=update_timers, daemon=True)
timer_thread.start()

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
                
        return jsonify({
            "message": "Random selection complete",
            "selected_students": selection
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
                "authorized": is_authorized
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
                    "leave_time": student["leave_time"]
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
                "session_log": []
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
                
        return jsonify({
            "message": "Sample data added",
            "student_count": len(db["students"]),
            "bssids": db["authorized_bssids"]
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
