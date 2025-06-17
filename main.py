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
def get_attendance_status(timer_status):
    return {
        "stopped": "Absent",
        "running": "Pending",
        "paused": "On Bunk",
        "completed": "Attended"
    }.get(timer_status, "Unknown")

def current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        time.sleep(1)

threading.Thread(target=update_timers, daemon=True).start()

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
    with lock:
        db["current_session"] = {
            "name": session_name,
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
    return jsonify({"selected_students": selection})

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
        })

        is_authorized = bssid in db["authorized_bssids"]
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

@app.route('/mark_present', methods=['POST'])
def mark_present():
    student_id = request.json.get("student_id")
    with lock:
        student = db["students"].get(student_id)
        if student:
            student["attendance_status"] = "Attended"
            student["timer"]["status"] = "completed"
            student["timer"]["running"] = False
            student["timer"]["remaining"] = 0
            student["leave_time"] = current_time_str()
            return jsonify({"message": "Marked present"})
        return jsonify({"error": "Student not found"}), 404

# =========================
# STATUS FOR FRONTEND
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

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
