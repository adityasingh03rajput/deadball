from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading

app = Flask(__name__)
CORS(app)

# In-memory database
data = {
    "students": {},
    "authorized_bssid": None
}

lock = threading.Lock()

def update_timers():
    while True:
        with lock:
            for student_id, student in data["students"].items():
                if student["timer"]["running"]:
                    elapsed = time.time() - student["timer"]["last_update"]
                    student["timer"]["remaining"] = max(0, student["timer"]["remaining"] - elapsed)
                    student["timer"]["last_update"] = time.time()
                    
                    if student["timer"]["remaining"] <= 0:
                        student["timer"]["running"] = False
                        student["timer"]["status"] = "completed"
        time.sleep(1)

# Start background timer thread
threading.Thread(target=update_timers, daemon=True).start()

@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    bssid = request.json.get('bssid')
    if not bssid:
        return jsonify({"error": "BSSID required"}), 400
    
    with lock:
        data["authorized_bssid"] = bssid
    return jsonify({"message": f"Authorized BSSID set to {bssid}"})

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
                    "duration": 300,
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                },
                "connected": False,
                "authorized": False
            }
        
        # Check BSSID authorization
        authorized = (data["authorized_bssid"] == bssid)
        data["students"][student_id]["connected"] = True
        data["students"][student_id]["authorized"] = authorized
        
        return jsonify({
            "authorized": authorized,
            "message": "Connected"
        })

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
                "duration": 300,
                "remaining": 300,
                "running": True,
                "last_update": time.time(),
                "status": "running"
            }
        elif action == "pause":
            if not student["timer"]["running"]:
                return jsonify({"error": "Timer not running"}), 400
            student["timer"]["running"] = False
            student["timer"]["status"] = "paused"
        elif action == "stop":
            student["timer"] = {
                "duration": 300,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            }
    
    return jsonify({"message": f"Timer {action}ed"})

@app.route('/get_status', methods=['GET'])
def get_status():
    with lock:
        return jsonify({
            "authorized_bssid": data["authorized_bssid"],
            "students": data["students"]
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
