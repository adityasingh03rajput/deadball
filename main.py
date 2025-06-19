# app.py (merged version)
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import threading
import time
import random
from datetime import datetime
import platform
import subprocess
import os
import ctypes
import calendar
import re
import json

app = Flask(__name__)
CORS(app)

# =========================
# IN-MEMORY DATABASE
# =========================
db = {
    "students": {},  # student_id: {details}
    "teachers": {},  # teacher_id: {details}
    "authorized_bssids": ["ee:ee:6d:9d:6f:ba"],
    "current_session": None,
    "session_log": [],
    "timetable": {},
    "holidays": {
        "national_holidays": {},
        "custom_holidays": {}
    },
    "random_rings": {}
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

def get_device_id():
    """Generate a unique device ID for this student"""
    if os.name == 'nt':
        # Windows - use volume serial number
        try:
            output = subprocess.check_output("wmic csproduct get uuid", shell=True)
            return output.decode().split('\n')[1].strip()
        except:
            return "unknown_device"
    else:
        # Linux/Mac - use machine-id
        try:
            with open('/etc/machine-id') as f:
                return f.read().strip()
        except:
            return "unknown_device"

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
# ROUTES
# =========================
@app.route('/')
def index():
    return render_template('index.html')

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
        
        # Store the selection with timestamp
        db["random_rings"]["last_ring"] = datetime.now().isoformat()
        db["random_rings"]["selected_students"] = selection
        db["random_rings"]["ring_active"] = True
        
    return jsonify({"selected_students": selection})

@app.route('/get_random_rings', methods=['GET'])
def get_random_rings():
    student_id = request.args.get("student_id")
    with lock:
        rings = db["random_rings"].copy()
        
        # Check if this student was selected
        if student_id and rings.get("selected_students"):
            rings["student_selected"] = student_id in rings["selected_students"]
        else:
            rings["student_selected"] = False
            
    return jsonify(rings)

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
            "leave_time": None,
            "wifi_status": "disconnected",
            "bssid": None,
            "ssid": None,
            "device_id": get_device_id()
        })

        is_authorized = bssid in db["authorized_bssids"]
        student["connected"] = True
        student["authorized"] = is_authorized
        student["bssid"] = bssid
        student["wifi_status"] = "connected"

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

@app.route('/update_wifi_status', methods=['POST'])
def update_wifi_status():
    data = request.json
    student_id = data.get("username")
    status = data.get("status")
    bssid = data.get("bssid")
    ssid = data.get("ssid")
    device = data.get("device")

    with lock:
        student = db["students"].get(student_id)
        if student:
            student["wifi_status"] = status
            student["bssid"] = bssid
            student["ssid"] = ssid
            student["device_id"] = device
            student["authorized"] = bssid in db["authorized_bssids"]
            student["connected"] = status == "connected"
            
    return jsonify({"message": "WiFi status updated"})

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
                "leave_time": student.get("leave_time"),
                "wifi_status": student.get("wifi_status", "unknown"),
                "bssid": student.get("bssid"),
                "ssid": student.get("ssid"),
                "device_id": student.get("device_id")
            }

        return jsonify({
            "authorized_bssids": db["authorized_bssids"],
            "students": students_status,
            "current_session": db["current_session"],
            "random_rings": db["random_rings"]
        })

@app.route('/get_authorized_bssids', methods=['GET'])
def get_authorized_bssids():
    with lock:
        return jsonify({"bssids": db["authorized_bssids"]})

@app.route('/get_attendance_session', methods=['GET'])
def get_attendance_session():
    with lock:
        return jsonify({
            "active": db["current_session"] is not None,
            "session": db["current_session"]
        })

# =========================
# AUTHENTICATION
# =========================
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")  # In a real app, use proper password hashing
    
    # This is a simplified version - in production, use proper authentication
    if username.startswith("teacher"):
        return jsonify({
            "message": "Login successful",
            "type": "teacher"
        })
    elif username.startswith("student"):
        return jsonify({
            "message": "Login successful",
            "type": "student"
        })
    else:
        return jsonify({"error": "Invalid credentials"}), 401

# =========================
# START APP
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
