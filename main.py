from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading
from datetime import datetime, timezone
import random
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-here'

# Enhanced in-memory database with persistence option
class Database:
    def __init__(self):
        self.data = {
            "students": {},
            "authorized_bssids": set(),
            "sessions": {},
            "current_session": None,
            "teachers": {
                "admin": generate_password_hash("admin123")
            }
        }
        self.lock = threading.Lock()

db = Database()

# Authentication decorator
def teacher_required(f):
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            return jsonify({"error": "Authentication required"}), 401
        
        with db.lock:
            if auth.username not in db.data["teachers"]:
                return jsonify({"error": "Invalid credentials"}), 403
            
            if not check_password_hash(db.data["teachers"][auth.username], auth.password):
                return jsonify({"error": "Invalid credentials"}), 403
        
        return f(*args, **kwargs)
    return wrapper

# Background timer thread
def update_timers():
    while True:
        with db.lock:
            current_time = time.time()
            for student_id, student in db.data["students"].items():
                if student["timer"]["running"]:
                    elapsed = current_time - student["timer"]["last_update"]
                    remaining = max(0, student["timer"]["remaining"] - elapsed)
                    
                    # Only update if significant change (reduce lock contention)
                    if abs(remaining - student["timer"]["remaining"]) >= 1:
                        student["timer"]["remaining"] = remaining
                        student["timer"]["last_update"] = current_time
                        
                        if student["timer"]["remaining"] <= 0:
                            student["timer"]["running"] = False
                            student["timer"]["status"] = "completed"
                            student["attendance_status"] = "present"
        time.sleep(0.5)

threading.Thread(target=update_timers, daemon=True).start()

@app.route('/set_bssid', methods=['POST'])
@teacher_required
def set_bssid():
    bssids = request.json.get('bssids', [])
    if not isinstance(bssids, list):
        return jsonify({"error": "BSSIDs must be an array"}), 400
    
    with db.lock:
        db.data["authorized_bssids"] = set(bssids)
    return jsonify({"message": f"Authorized BSSIDs updated", "count": len(bssids)})

# Add similar @teacher_required decorator to other teacher endpoints

@app.route('/student/status/<student_id>', methods=['GET'])
def student_status(student_id):
    with db.lock:
        if student_id not in db.data["students"]:
            return jsonify({"error": "Student not found"}), 404
        
        student = db.data["students"][student_id]
        return jsonify({
            "timer_status": student["timer"]["status"],
            "time_remaining": student["timer"]["remaining"],
            "wifi_status": "authorized" if student["authorized"] else "unauthorized" if student["connected"] else "disconnected",
            "attendance": student["attendance_status"]
        })

# Add endpoint for bulk operations
@app.route('/students/bulk_action', methods=['POST'])
@teacher_required
def bulk_action():
    action = request.json.get('action')
    student_ids = request.json.get('student_ids', [])
    
    if action not in ["start_timer", "stop_timer", "mark_present"]:
        return jsonify({"error": "Invalid action"}), 400
    
    results = {}
    with db.lock:
        for student_id in student_ids:
            if student_id in db.data["students"]:
                student = db.data["students"][student_id]
                
                if action == "start_timer":
                    if student["authorized"]:
                        student["timer"] = {
                            "duration": 120,
                            "remaining": 120,
                            "running": True,
                            "last_update": time.time(),
                            "status": "running"
                        }
                        results[student_id] = "success"
                # Implement other actions...
    
    return jsonify({"results": results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
