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
        # Reset all student timers at session start
        for student in db["students"].values():
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            }
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
        attended = [sid for sid, s in students if s.get("timer", {}).get("status") == "completed"]
        absent = [sid for sid, s in students if s.get("timer", {}).get("status") == "stopped"]
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
            "last_update": None
        })

        is_authorized = bssid in db["authorized_bssids"]
        student["connected"] = True
        student["authorized"] = is_authorized
        student["last_update"] = current_time_str()

        return jsonify({
            "authorized": is_authorized,
            "current_session": db["current_session"] is not None
        })

@app.route('/student/timer/update', methods=['POST'])
def update_timer():
    student_id = request.json.get("student_id")
    timer_status = request.json.get("status")  # "running", "stopped", "completed"
    remaining = request.json.get("remaining", 120)
    
    with lock:
        student = db["students"].get(student_id)
        if not student:
            return jsonify({"error": "Student not found"}), 404
            
        if timer_status == "running":
            student["timer"] = {
                "duration": 120,
                "remaining": remaining,
                "running": True,
                "last_update": time.time(),
                "status": "running"
            }
        elif timer_status == "stopped":
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            }
        elif timer_status == "completed":
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "completed"
            }
            if db["current_session"]:
                db["current_session"]["students_present"].append(student_id)
        
        student["last_update"] = current_time_str()
        
    return jsonify({"message": "Timer updated"})

@app.route('/mark_present', methods=['POST'])
def mark_present():
    student_id = request.json.get("student_id")
    with lock:
        student = db["students"].get(student_id)
        if student:
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "completed"
            }
            if db["current_session"]:
                db["current_session"]["students_present"].append(student_id)
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
            students_status[sid] = {
                "name": student["name"],
                "timer": timer,
                "connected": student["connected"],
                "authorized": student["authorized"],
                "last_update": student.get("last_update")
            }

        return jsonify({
            "authorized_bssids": db["authorized_bssids"],
            "students": students_status,
            "current_session": db["current_session"]
        })

@app.route('/session/status', methods=['GET'])
def session_status():
    with lock:
        return jsonify({
            "session_active": db["current_session"] is not None,
            "session_name": db["current_session"]["name"] if db["current_session"] else None
        })

@app.route('/settings/bssid', methods=['GET'])
def get_bssids():
    with lock:
        return jsonify({"bssids": db["authorized_bssids"]})

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
