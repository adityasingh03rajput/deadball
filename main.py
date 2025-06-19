# -*- coding: utf-8 -*-
#
# server.py
# The backend server for the Let's Bunk Attendance Management System.
#
# This server uses Flask to provide a REST API for the PyQt6 client. It manages
# all application state in memory, including users, sessions, and attendance timers.
# A background thread is used to handle real-time timer countdowns.
#
import time
import threading
import logging
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

# =============================================================================
# CONFIGURATION
# =============================================================================
# The duration in seconds a student must be connected to mark attendance.
ATTENDANCE_TIMER_DURATION = 120  # 2 minutes
# The number of students to select for a "random ring".
RANDOM_RING_COUNT = 2

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Flask App
app = Flask(__name__)
# Enable CORS for all routes, allowing the client to connect from any origin.
CORS(app)

# =============================================================================
# IN-MEMORY "DATABASE" AND STATE MANAGEMENT
# =============================================================================
# In a production environment, this data would be stored in a persistent database
# like PostgreSQL or SQLite. For this example, we use global dictionaries.

# --- Thread-Safety Lock ---
# This lock is crucial to prevent race conditions when multiple requests or
# the background timer thread access shared data simultaneously.
data_lock = threading.Lock()

# --- Persistent Data (Simulating a DB) ---
# NOTE: The client's login/signup is currently a placeholder. This server doesn't
# perform real authentication, but the structure is here.
teachers_db = {
    "teacher1": {"name": "Prof. Alan Turing", "password": "password123"},
}
students_db = {
    "S001": {"name": "Ada Lovelace"},
    "S002": {"name": "Grace Hopper"},
    "S003": {"name": "Charles Babbage"},
    "S004": {"name": "John von Neumann"},
}
authorized_bssids = [
    "c0:3e:ba:d1:9b:f1", # Example BSSID, change to your own for testing
]

# --- Session State (Resets when a new session starts) ---
# This dictionary holds the active state of the current attendance session.
# It is set to None when no session is active.
current_session = None

# This dictionary holds the dynamic data for each student within the active session.
# It is keyed by student_id.
students_session_data = {}


def format_time(dt_obj):
    """Helper function to format datetime objects into a consistent string."""
    if not dt_obj:
        return None
    return dt_obj.strftime("%H:%M:%S")

def reset_session_data():
    """
    Resets all session-related state. Called when a new session is started
    to ensure a clean slate.
    """
    global current_session, students_session_data
    current_session = None
    students_session_data.clear()
    logging.info("Session data has been reset.")


class TimerManager(threading.Thread):
    """
    A background thread that manages all student attendance timers.
    It runs every second to decrement the timers of 'running' students.
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        logging.info("TimerManager thread started.")
        while not self.stop_event.is_set():
            with data_lock:
                # The timer only runs if there's an active session
                if current_session:
                    for sid, data in students_session_data.items():
                        timer = data.get("timer", {})
                        if timer.get("status") == "running":
                            # Calculate elapsed time since the timer was last started/resumed
                            now = time.time()
                            elapsed_since_start = now - timer.get("start_time_unix", now)

                            # The new remaining time is the old remaining time minus the new elapsed chunk
                            new_remaining = timer.get("initial_remaining", 0) - elapsed_since_start

                            if new_remaining <= 0:
                                timer["remaining"] = 0
                                timer["status"] = "completed"
                                data["attendance_status"] = "Attended"
                                logging.info(f"Student {sid} completed attendance timer.")
                            else:
                                timer["remaining"] = new_remaining

            # Sleep for one second before the next update cycle
            time.sleep(1)
        logging.info("TimerManager thread stopped.")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/get_status', methods=['GET'])
def get_status():
    """
    The primary endpoint for the client to fetch the entire application state.
    It combines static student info with dynamic session data.
    """
    with data_lock:
        # Create a deep copy to send, preventing modification of the original data.
        full_student_status = {}
        for sid, student_info in students_db.items():
            session_info = students_session_data.get(sid, {})
            # Merge static info (name) with dynamic session info
            full_student_status[sid] = {**student_info, **session_info}

        response = {
            "current_session": current_session,
            "students": full_student_status,
            "authorized_bssids": authorized_bssids
        }
        return jsonify(response)

@app.route('/start_session', methods=['POST'])
def start_session():
    """
    Endpoint for a teacher to start a new attendance session.
    This clears all previous session data and initializes a new one.
    """
    with data_lock:
        reset_session_data()  # Clear any old data first

        global current_session
        data = request.json
        now = datetime.now()
        current_session = {
            "name": data.get("session_name", "Unnamed Session"),
            "start_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "active"
        }

        # Initialize session data for all registered students
        for sid, student_info in students_db.items():
            students_session_data[sid] = {
                "attendance_status": "Absent",
                "join_time": None,
                "leave_time": None,
                "is_connected_authorized": False,
                "timer": {
                    "status": "stopped",  # can be 'stopped', 'running', 'paused', 'completed'
                    "remaining": ATTENDANCE_TIMER_DURATION,
                    "start_time_unix": 0,
                    "initial_remaining": ATTENDANCE_TIMER_DURATION, # Tracks time left before a pause
                }
            }
        logging.info(f"New session started: {current_session['name']}")
    return jsonify({"status": "success", "message": "Session started."})

@app.route('/end_session', methods=['POST'])
def end_session():
    """
    Endpoint for a teacher to end the current session.
    """
    with data_lock:
        if not current_session:
            return jsonify({"status": "error", "message": "No active session to end."}), 400

        # Effectively stops all timers and finalizes the state.
        reset_session_data()
        logging.info("Session ended by teacher.")
    return jsonify({"status": "success", "message": "Session ended."})

@app.route('/set_bssid', methods=['POST'])
def set_bssid():
    """
    Endpoint for a teacher to update the list of authorized BSSIDs.
    """
    with data_lock:
        global authorized_bssids
        data = request.json
        new_bssids = data.get("bssids", [])
        if isinstance(new_bssids, list):
            authorized_bssids = [b.strip().lower() for b in new_bssids]
            logging.info(f"Authorized BSSIDs updated: {authorized_bssids}")
            return jsonify({"status": "success", "message": "BSSID list updated."})
        return jsonify({"status": "error", "message": "Invalid data format."}), 400

@app.route('/student/connect', methods=['POST'])
def student_connect():
    """
    Called by the student client's WifiChecker. Updates the student's
    connection status and pauses/resumes their timer accordingly.
    """
    with data_lock:
        if not current_session:
            return jsonify({"status": "ignored", "message": "No active session."})

        data = request.json
        student_id = data.get("student_id")
        bssid = data.get("bssid")

        student_data = students_session_data.get(student_id)
        if not student_data:
            return jsonify({"status": "error", "message": "Student not found in session."}), 404

        now = datetime.now()
        is_authorized = bssid in authorized_bssids if bssid else False
        student_data["is_connected_authorized"] = is_authorized

        timer = student_data["timer"]

        if is_authorized:
            student_data["join_time"] = format_time(now)
            student_data["leave_time"] = None
            # If the timer was paused, resume it
            if timer["status"] == "paused":
                timer["status"] = "running"
                timer["start_time_unix"] = time.time() # Reset start time for the current running chunk
                timer["initial_remaining"] = timer["remaining"] # The new "full" duration is what was left
                logging.info(f"Student {student_id} reconnected to authorized WiFi. Timer resumed.")
        else:
            student_data["leave_time"] = format_time(now)
            # If the timer was running, pause it
            if timer["status"] == "running":
                timer["status"] = "paused"
                # The remaining time is already calculated by the background thread,
                # so we just need to stop it from decrementing further.
                logging.info(f"Student {student_id} disconnected from authorized WiFi. Timer paused.")

    return jsonify({"status": "success", "message": "Connection status updated."})

@app.route('/student/timer/start', methods=['POST'])
def start_student_timer():
    """
    Called when a student clicks the "Mark My Attendance" button.
    Starts their timer if they are connected to an authorized network.
    """
    with data_lock:
        if not current_session:
            return jsonify({"status": "error", "message": "No active session."}), 400

        data = request.json
        student_id = data.get("student_id")

        student_data = students_session_data.get(student_id)
        if not student_data:
            return jsonify({"status": "error", "message": "Student not found."}), 404

        if not student_data.get("is_connected_authorized"):
            return jsonify({"status": "error", "message": "Must be connected to an authorized WiFi network."}), 403

        timer = student_data["timer"]
        if timer["status"] in ["running", "completed"]:
            return jsonify({"status": "ignored", "message": "Timer is already running or completed."})

        timer["status"] = "running"
        timer["start_time_unix"] = time.time()
        timer["initial_remaining"] = timer["remaining"]
        logging.info(f"Student {student_id} started their attendance timer.")

    return jsonify({"status": "success", "message": "Timer started."})


@app.route('/random_ring', methods=['POST'])
def random_ring():
    """
    Selects a few students who have already marked attendance and
    sets their status to "On Bunk", requiring them to be physically present.
    """
    with data_lock:
        if not current_session:
            return jsonify({"status": "error", "message": "No active session."}), 400

        # Find students eligible for the random ring (i.e., status is Attended)
        eligible_students = [
            sid for sid, data in students_session_data.items()
            if data["attendance_status"] == "Attended"
        ]

        # Determine how many students to select
        count = min(RANDOM_RING_COUNT, len(eligible_students))
        if count == 0:
            return jsonify({"status": "success", "message": "No attended students to select.", "selected_students": []})

        # Randomly select students
        selected_students = random.sample(eligible_students, count)

        # Update the status of selected students
        for sid in selected_students:
            students_session_data[sid]["attendance_status"] = "On Bunk"

        logging.info(f"Random ring initiated. Selected students: {selected_students}")
        return jsonify({"status": "success", "selected_students": selected_students})

# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Initialize and start the background timer manager thread
    timer_thread = TimerManager()
    timer_thread.start()

    logging.info("Starting Flask server...")
    # Run the Flask app.
    # host='0.0.0.0' makes the server accessible from other devices on the same network.
    # debug=True provides helpful error pages but should be False in production.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
