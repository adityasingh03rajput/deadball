from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading
from datetime import datetime, timezone
import random

app = Flask(__name__)
CORS(app)

# In-memory database
data = {
    "students": {},
    "authorized_bssids": set(),
    "sessions": {},
    "current_session": None
}

lock = threading.Lock()

def update_timers():
    while True:
        with lock:
            current_time = time.time()
            for student_id, student in data["students"].items():
                if student["timer"]["running"]:
                    elapsed = current_time - student["timer"]["last_update"]
                    student["timer"]["remaining"] = max(0, student["timer"]["remaining"] - elapsed)
                    student["timer"]["last_update"] = current_time
                    
                    if student["timer"]["remaining"] <= 0:
                        student["timer"]["running"] = False
                        student["timer"]["status"] = "completed"
                        student["attendance_status"] = "present"
        time.sleep(1)

# Start background timer thread
threading.Thread(target=update_timers, daemon=True).start()

@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    bssids = request.json.get('bssids')
    if not bssids:
        return jsonify({"error": "BSSIDs required"}), 400
    
    with lock:
        data["authorized_bssids"] = set(bssids)
    return jsonify({"message": f"Authorized BSSIDs updated"})

@app.route('/student/connect', methods=['POST'])
def student_connect():
    student_id = request.json.get('student_id')
    bssid = request.json.get('bssid')
    
    if not student_id or not bssid:
        return jsonify({"error": "Student ID and BSSID required"}), 400
    
    with lock:
        # Create student if not exists
        if student_id not in data["students"]:
            data["students"][student_id] = {
                "timer": {
                    "duration": 120,  # 2 minutes
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                },
                "connected": False,
                "authorized": False,
                "attendance_status": "absent",
                "last_seen": None,
                "join_time": None
            }
        
        # Check BSSID authorization
        authorized = bssid in data["authorized_bssids"]
        data["students"][student_id]["connected"] = True
        data["students"][student_id]["authorized"] = authorized
        data["students"][student_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
        
        if data["students"][student_id]["join_time"] is None:
            data["students"][student_id]["join_time"] = datetime.now(timezone.utc).isoformat()
        
        return jsonify({
            "authorized": authorized,
            "message": "Connected"
        })

@app.route('/student/disconnect', methods=['POST'])
def student_disconnect():
    student_id = request.json.get('student_id')
    
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id in data["students"]:
            data["students"][student_id]["connected"] = False
            data["students"][student_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
    
    return jsonify({"message": "Disconnected"})

@app.route('/student/timer/<action>', methods=['POST'])
def timer_action(action):
    student_id = request.json.get('student_id')
    
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    if action not in ["start", "pause", "stop"]:
        return jsonify({"error": "Invalid action"}), 400
    
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
            
        student = data["students"][student_id]
        
        if action == "start":
            if not student["authorized"]:
                return jsonify({"error": "Not authorized"}), 403
            student["timer"] = {
                "duration": 120,
                "remaining": 120,
                "running": True,
                "last_update": time.time(),
                "status": "running"
            }
            student["attendance_status"] = "pending"
        elif action == "pause":
            if not student["timer"]["running"]:
                return jsonify({"error": "Timer not running"}), 400
            student["timer"]["running"] = False
            student["timer"]["status"] = "paused"
        elif action == "stop":
            student["timer"] = {
                "duration": 120,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            }
            if student["attendance_status"] == "pending":
                student["attendance_status"] = "absent"
    
    return jsonify({"message": f"Timer {action}ed"})

@app.route('/mark_present', methods=['POST'])
def mark_present():
    student_id = request.json.get('student_id')
    
    if not student_id:
        return jsonify({"error": "Student ID required"}), 400
    
    with lock:
        if student_id in data["students"]:
            data["students"][student_id]["attendance_status"] = "present"
    
    return jsonify({"message": "Marked present"})

@app.route('/start_session', methods=['POST'])
def start_session():
    session_name = request.json.get('session_name')
    
    if not session_name:
        return jsonify({"error": "Session name required"}), 400
    
    with lock:
        data["current_session"] = {
            "name": session_name,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": None
        }
    
    return jsonify({"message": f"Session {session_name} started"})

@app.route('/end_session', methods=['POST'])
def end_session():
    with lock:
        if data["current_session"]:
            data["current_session"]["end_time"] = datetime.now(timezone.utc).isoformat()
            session_data = data["current_session"].copy()
            
            # Save session data
            session_id = f"session_{int(time.time())}"
            data["sessions"][session_id] = {
                "name": session_data["name"],
                "start_time": session_data["start_time"],
                "end_time": session_data["end_time"],
                "attendance": {
                    student_id: student["attendance_status"]
                    for student_id, student in data["students"].items()
                }
            }
            
            data["current_session"] = None
            return jsonify({"message": "Session ended", "session_id": session_id})
        else:
            return jsonify({"error": "No active session"}), 400

@app.route('/get_status', methods=['GET'])
def get_status():
    with lock:
        return jsonify({
            "authorized_bssids": list(data["authorized_bssids"]),
            "students": data["students"],
            "current_session": data["current_session"],
            "sessions": data["sessions"]
        })

@app.route('/random_ring', methods=['POST'])
def random_ring():
    with lock:
        present_students = [
            s_id for s_id, s in data["students"].items() 
            if s["attendance_status"] == "present"
        ]
        absent_students = [
            s_id for s_id, s in data["students"].items() 
            if s["attendance_status"] != "present"
        ]
        
        selected = []
        if present_students:
            selected.append(random.choice(present_students))
        if absent_students:
            selected.append(random.choice(absent_students))
        
        return jsonify({"selected_students": selected})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
