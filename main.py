from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import threading

app = Flask(__name__)
CORS(app)

# In-memory database
data = {
    "students": {},  # student_id -> {...}
    "authorized_bssid": None
}

lock = threading.Lock()

# Timer update thread
def update_timers():
    while True:
        with lock:
            for student in data["students"].values():
                timer = student["timer"]
                if timer["running"]:
                    now = time.time()
                    elapsed = now - timer["last_update"]
                    timer["remaining"] = max(0, timer["remaining"] - elapsed)
                    timer["last_update"] = now
                    if timer["remaining"] <= 0:
                        timer["running"] = False
                        timer["status"] = "completed"
        time.sleep(1)

threading.Thread(target=update_timers, daemon=True).start()

@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    bssid = request.json.get('bssid')
    if not bssid:
        return jsonify({"error": "BSSID required"}), 400
    with lock:
        data["authorized_bssid"] = bssid
    return jsonify({"message": f"Authorized BSSID set to {bssid}"}), 200

@app.route('/student/connect', methods=['POST'])
def student_connect():
    student_id = request.json.get('student_id')
    bssid = request.json.get('bssid')

    if not student_id or not bssid:
        return jsonify({"error": "Student ID and BSSID required"}), 400

    with lock:
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

        student = data["students"][student_id]
        student["connected"] = True
        student["authorized"] = (bssid == data["authorized_bssid"])

        return jsonify({
            "authorized": student["authorized"],
            "message": "Connected"
        }), 200

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
        timer = student["timer"]

        if action == "start":
            if not student["authorized"]:
                return jsonify({"error": "Not authorized"}), 403
            timer.update({
                "duration": 300,
                "remaining": 300,
                "running": True,
                "last_update": time.time(),
                "status": "running"
            })
        elif action == "pause":
            if not timer["running"]:
                return jsonify({"error": "Timer not running"}), 400
            timer["running"] = False
            timer["status"] = "paused"
        elif action == "stop":
            timer.update({
                "duration": 300,
                "remaining": 0,
                "running": False,
                "last_update": None,
                "status": "stopped"
            })

    return jsonify({"message": f"Timer {action}ed"}), 200

@app.route('/get_status', methods=['GET'])
def get_status():
    with lock:
        return jsonify({
            "authorized_bssid": data["authorized_bssid"],
            "students": data["students"]
        }), 200

@app.route('/student/<student_id>', methods=['GET'])
def get_student(student_id):
    with lock:
        if student_id not in data["students"]:
            return jsonify({"error": "Student not found"}), 404
        return jsonify(data["students"][student_id]), 200

@app.route('/reset_all', methods=['POST'])
def reset_all():
    with lock:
        for student in data["students"].values():
            student.update({
                "connected": False,
                "authorized": False,
                "timer": {
                    "duration": 300,
                    "remaining": 0,
                    "running": False,
                    "last_update": None,
                    "status": "stopped"
                }
            })
    return jsonify({"message": "All students reset"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
