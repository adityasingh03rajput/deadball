import threading
import time
import random
from datetime import datetime
import platform
import subprocess
import os
import json
from collections import defaultdict

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
# TEACHER COMMANDS
# =========================
def set_bssid(bssids):
    with lock:
        db["authorized_bssids"] = bssids
    print(f"BSSIDs updated to: {bssids}")

def start_session(session_name):
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
    print(f"Session '{session_name}' started")

def end_session():
    with lock:
        session = db["current_session"]
        if session:
            session["end_time"] = current_time_str()
            db["session_log"].append(session)
            db["current_session"] = None
            print("Session ended")
        else:
            print("Error: No active session")

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
        
        db["random_rings"]["last_ring"] = datetime.now().isoformat()
        db["random_rings"]["selected_students"] = selection
        db["random_rings"]["ring_active"] = True
        
    print(f"Randomly selected students: {selection}")

# =========================
# STUDENT COMMANDS
# =========================
def student_connect(student_id, bssid):
    if not student_id or not bssid:
        print("Error: student_id and bssid required")
        return

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

        print(f"Student {student_id} connected. Authorized: {is_authorized}")

def start_timer(student_id):
    with lock:
        student = db["students"].get(student_id)
        if not student:
            print("Error: Student not found")
            return
        if not student["authorized"]:
            print("Error: Not authorized")
            return

        student["timer"] = {
            "duration": 120,
            "remaining": 120,
            "running": True,
            "last_update": time.time(),
            "status": "running"
        }
        student["attendance_status"] = "Pending"
    print(f"Timer started for student {student_id}")

def mark_present(student_id):
    with lock:
        student = db["students"].get(student_id)
        if student:
            student["attendance_status"] = "Attended"
            student["timer"]["status"] = "completed"
            student["timer"]["running"] = False
            student["timer"]["remaining"] = 0
            student["leave_time"] = current_time_str()
            print(f"Marked student {student_id} as present")
        else:
            print("Error: Student not found")

def update_wifi_status(student_id, status, bssid=None, ssid=None, device=None):
    with lock:
        student = db["students"].get(student_id)
        if student:
            student["wifi_status"] = status
            student["bssid"] = bssid
            student["ssid"] = ssid
            student["device_id"] = device
            student["authorized"] = bssid in db["authorized_bssids"] if bssid else False
            student["connected"] = status == "connected"
            print(f"Updated WiFi status for {student_id}: {status}")
        else:
            print(f"Error: Student {student_id} not found")

# =========================
# STATUS COMMANDS
# =========================
def get_status():
    with lock:
        print("\n=== CURRENT STATUS ===")
        print(f"Authorized BSSIDs: {db['authorized_bssids']}")
        
        if db["current_session"]:
            print(f"\nActive Session: {db['current_session']['name']} (started at {db['current_session']['start_time']})")
        else:
            print("\nNo active session")
            
        print("\nStudents:")
        for sid, student in db["students"].items():
            timer = student.get("timer", {})
            print(f"{sid}: {student['name']}")
            print(f"  Status: {student['attendance_status']}")
            print(f"  Connected: {student['connected']} (Authorized: {student['authorized']})")
            print(f"  Timer: {timer.get('status', 'stopped')} ({timer.get('remaining', 0)}s remaining)")
            print(f"  WiFi: {student.get('wifi_status', 'unknown')} (BSSID: {student.get('bssid')})")
            
        if db["random_rings"].get("ring_active"):
            print(f"\nRandom Ring active (selected at {db['random_rings']['last_ring']}):")
            print(f"Selected students: {db['random_rings']['selected_students']}")

def get_attendance_report():
    with lock:
        if not db["session_log"]:
            print("No attendance sessions recorded yet")
            return
            
        print("\n=== ATTENDANCE HISTORY ===")
        for i, session in enumerate(db["session_log"], 1):
            print(f"\nSession {i}: {session['name']}")
            print(f"  From {session['start_time']} to {session['end_time']}")
            
            # Count attendance statuses
            status_count = defaultdict(int)
            for student in db["students"].values():
                status_count[student.get("attendance_status", "Unknown")] += 1
                
            for status, count in status_count.items():
                print(f"  {status}: {count}")

# =========================
# COMMAND PROCESSOR
# =========================
def process_command(command):
    parts = command.strip().split()
    if not parts:
        return
    
    cmd = parts[0].lower()
    
    try:
        if cmd == "set_bssid" and len(parts) > 1:
            set_bssid(parts[1:])
        elif cmd == "start_session" and len(parts) > 1:
            start_session(" ".join(parts[1:]))
        elif cmd == "end_session":
            end_session()
        elif cmd == "random_ring":
            random_ring()
        elif cmd == "connect" and len(parts) > 2:
            student_connect(parts[1], parts[2])
        elif cmd == "start_timer" and len(parts) > 1:
            start_timer(parts[1])
        elif cmd == "mark_present" and len(parts) > 1:
            mark_present(parts[1])
        elif cmd == "wifi_status" and len(parts) > 2:
            update_wifi_status(parts[1], parts[2], 
                             bssid=parts[3] if len(parts) > 3 else None,
                             ssid=parts[4] if len(parts) > 4 else None,
                             device=parts[5] if len(parts) > 5 else None)
        elif cmd == "status":
            get_status()
        elif cmd == "attendance":
            get_attendance_report()
        elif cmd == "help":
            print_help()
        elif cmd == "exit":
            return False
        else:
            print("Unknown command. Type 'help' for available commands.")
    except Exception as e:
        print(f"Error executing command: {e}")
    
    return True

def print_help():
    print("\nAvailable commands:")
    print("  set_bssid <bssid1> [bssid2...] - Set authorized BSSIDs")
    print("  start_session <name> - Start a new attendance session")
    print("  end_session - End the current session")
    print("  random_ring - Randomly select students")
    print("  connect <student_id> <bssid> - Connect a student")
    print("  start_timer <student_id> - Start attendance timer for student")
    print("  mark_present <student_id> - Manually mark student present")
    print("  wifi_status <student_id> <status> [bssid] [ssid] [device] - Update WiFi status")
    print("  status - Show current system status")
    print("  attendance - Show attendance history")
    print("  help - Show this help")
    print("  exit - Exit the program")

# =========================
# MAIN LOOP
# =========================
def main():
    print("Attendance System Console")
    print("Type 'help' for available commands")
    
    running = True
    while running:
        try:
            command = input("\n> ")
            running = process_command(command)
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit the program")
        except EOFError:
            running = False
    
    print("Shutting down...")

if __name__ == '__main__':
    main()
