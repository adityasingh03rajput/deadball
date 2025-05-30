import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
import platform
import subprocess
import os
import ctypes
from datetime import datetime, timedelta
import calendar
import re
import json
import time

# Server configuration
SERVER_URL = "https://deadball.onrender.com"  # Replace with your server URL
PING_INTERVAL = 30

class StudentClient:
    def __init__(self):
        self.username = None
        self.device_id = self.get_device_id()
        self.current_wifi = None
        self.current_bssid = None
        self.holidays = {}
        self.present_dates = []
        self.absent_dates = []
        self.last_wifi_status = None
        self.timetable = {}
        self.attendance_session_active = False
        self.setup_wifi_checker()
        self.root = tk.Tk()
        self.setup_login_ui()
        self.start_ping_thread()
        self.hide_console()
        self.root.mainloop()

    def get_device_id(self):
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

    def hide_console(self):
        if os.name == 'nt':
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

    def setup_wifi_checker(self):
        self.os_type = platform.system()
        if self.os_type == "Windows":
            self.check_wifi = self._check_wifi_windows
            self.get_bssid = self._get_bssid_windows
        elif self.os_type == "Linux":
            self.check_wifi = self._check_wifi_linux
            self.get_bssid = self._get_bssid_linux
        else:
            self.check_wifi = lambda: False
            self.get_bssid = lambda: None

    def _check_wifi_windows(self):
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    self.current_wifi = line.split(":")[1].strip()
                    return True
            return False
        except:
            return False

    def _get_bssid_windows(self):
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                if "BSSID" in line:
                    bssid = line.split(":")[1].strip().lower()
                    if re.match(r"^([0-9a-f]{2}[:]){5}([0-9a-f]{2})$", bssid):
                        self.current_bssid = bssid
                        return bssid
            return None
        except:
            return None

    def _check_wifi_linux(self):
        try:
            result = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True, text=True
            )
            self.current_wifi = result.stdout.strip()
            return bool(self.current_wifi)
        except:
            return False

    def _get_bssid_linux(self):
        try:
            result = subprocess.run(
                ["iwgetid", "-ar"],
                capture_output=True, text=True
            )
            bssid = result.stdout.strip().lower()
            if re.match(r"^([0-9a-f]{2}[:]){5}([0-9a-f]{2})$", bssid):
                self.current_bssid = bssid
                return bssid
            return None
        except:
            return None

    def is_authorized_wifi(self):
        """Check if connected to an authorized WiFi network"""
        if not self.check_wifi():
            return True
        
        try:
            # Get authorized BSSIDs from server
            response = requests.get(
                f"{SERVER_URL}/get_authorized_bssids",
                timeout=5
            )
            
            if response.status_code == 200:
                authorized_bssids = response.json().get('bssids', [])
                current_bssid = self.get_bssid()
                return current_bssid in authorized_bssids
        except:
            return False
        
        return False

    def setup_login_ui(self):
        self.root.title("Student Portal")
        self.root.geometry("350x250")
        self.root.resizable(False, False)
        
        # Main frame
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(expand=True)
        
        # Title
        tk.Label(main_frame, text="Student Portal", font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
        
        # Username
        tk.Label(main_frame, text="Student ID:").grid(row=1, column=0, sticky="e", pady=5)
        self.entry_username = tk.Entry(main_frame)
        self.entry_username.grid(row=1, column=1, pady=5, ipadx=20)
        
        # Password
        tk.Label(main_frame, text="Password:").grid(row=2, column=0, sticky="e", pady=5)
        self.entry_password = tk.Entry(main_frame, show="*")
        self.entry_password.grid(row=2, column=1, pady=5, ipadx=20)
        
        # Login Button
        tk.Button(
            main_frame,
            text="Login",
            command=self.login,
            width=15,
            bg="#4CAF50",
            fg="white"
        ).grid(row=3, column=0, columnspan=2, pady=15)

    def login(self):
        username = self.entry_username.get()
        password = self.entry_password.get()
        
        if not username or not password:
            messagebox.showwarning("Error", "Please enter both username and password")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/login",
                json={"username": username, "password": password},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('type') == 'student':
                    messagebox.showinfo("Success", "Login successful!")
                    self.username = username
                    self.root.destroy()
                    self.start_main_application()
                else:
                    messagebox.showerror("Error", "Teachers must use the teacher portal")
            else:
                messagebox.showerror("Error", data.get('error', 'Login failed'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def start_ping_thread(self):
        def ping():
            while True:
                if self.username:
                    try:
                        wifi_status = "connected" if self.check_wifi() else "disconnected"
                        
                        # Send attendance ping
                        requests.post(
                            f"{SERVER_URL}/ping",
                            json={
                                "username": self.username,
                                "type": "student",
                                "device_id": self.device_id,
                                "status": "active"
                            },
                            timeout=5
                        )
                        
                        # Send WiFi status if changed
                        if wifi_status != self.last_wifi_status:
                            requests.post(
                                f"{SERVER_URL}/update_wifi_status",
                                json={
                                    "username": self.username,
                                    "status": wifi_status,
                                    "bssid": self.current_bssid,
                                    "ssid": self.current_wifi,
                                    "device": self.device_id
                                },
                                timeout=5
                            )
                            self.last_wifi_status = wifi_status
                    except:
                        pass
                time.sleep(PING_INTERVAL)
        
        threading.Thread(target=ping, daemon=True).start()

    def start_main_application(self):
        self.main_window = tk.Tk()
        self.main_window.title(f"Student Portal - {self.username}")
        self.main_window.geometry("1000x700")
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.main_window)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Attendance Tab
        self.attendance_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.attendance_tab, text="Attendance")
        self.setup_attendance_tab()
        
        # Timetable Tab
        self.timetable_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.timetable_tab, text="Timetable")
        self.setup_timetable_tab()
        
        # Calendar Tab
        self.calendar_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.calendar_tab, text="Calendar")
        self.setup_calendar_tab()
        
        # Status Bar
        self.status_bar = tk.Label(
            self.main_window,
            text="Status: Not Connected",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X)
        
        # Start threads
        threading.Thread(target=self.check_attendance_session, daemon=True).start()
        threading.Thread(target=self.check_rings, daemon=True).start()
        threading.Thread(target=self.check_wifi_status, daemon=True).start()
        threading.Thread(target=self.update_timetable, daemon=True).start()
        threading.Thread(target=self.update_attendance_data, daemon=True).start()
        
        self.main_window.mainloop()

    def setup_attendance_tab(self):
        # Timer frame
        timer_frame = tk.Frame(self.attendance_tab)
        timer_frame.pack(pady=20)
        
        self.timer_label = tk.Label(
            timer_frame,
            text="Waiting for attendance session...",
            font=("Arial", 14),
            pady=20
        )
        self.timer_label.pack()
        
        self.start_button = tk.Button(
            timer_frame,
            text="Mark Attendance",
            command=self.start_attendance,
            font=("Arial", 12),
            bg="#4CAF50",
            fg="white",
            padx=20,
            pady=10,
            state=tk.DISABLED
        )
        self.start_button.pack(pady=20)
        
        # Notification frame
        notification_frame = tk.Frame(self.attendance_tab)
        notification_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.ring_label = tk.Label(
            notification_frame,
            text="",
            font=("Arial", 10, "bold"),
            fg="red",
            anchor="w"
        )
        self.ring_label.pack(fill=tk.X)
        
        # WiFi info frame
        wifi_frame = tk.Frame(self.attendance_tab)
        wifi_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.wifi_label = tk.Label(
            wifi_frame,
            text="WiFi: Not Connected",
            font=("Arial", 10),
            anchor="w"
        )
        self.wifi_label.pack(fill=tk.X)

    def setup_timetable_tab(self):
        # Create a frame with scrollbars
        container = tk.Frame(self.timetable_tab)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Create a canvas
        canvas = tk.Canvas(container)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create a frame inside the canvas
        self.timetable_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.timetable_frame, anchor="nw")
        
        # Configure the canvas scrolling
        self.timetable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        # Initial loading message
        tk.Label(self.timetable_frame, text="Loading timetable...", font=("Arial", 12)).pack()

    def setup_calendar_tab(self):
        # Month and year selection
        control_frame = tk.Frame(self.calendar_tab)
        control_frame.pack(pady=10)
        
        self.current_month = datetime.now().month
        self.current_year = datetime.now().year
        
        tk.Button(control_frame, text="<", command=self.prev_month).grid(row=0, column=0)
        self.month_label = tk.Label(control_frame, text="", font=("Arial", 12))
        self.month_label.grid(row=0, column=1)
        tk.Button(control_frame, text=">", command=self.next_month).grid(row=0, column=2)
        
        # Calendar display
        self.calendar_frame = tk.Frame(self.calendar_tab)
        self.calendar_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Days of week header
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            tk.Label(self.calendar_frame, text=day, width=10, height=2, 
                    relief=tk.RIDGE, bg="#f0f0f0").grid(row=0, column=i, sticky="nsew")
        
        # Update calendar display
        self.update_calendar()

    def update_calendar(self):
        # Clear previous calendar days (keep header)
        for widget in self.calendar_frame.winfo_children()[7:]:
            widget.destroy()
        
        # Set month label
        self.month_label.config(text=f"{calendar.month_name[self.current_month]} {self.current_year}")
        
        # Get calendar data
        cal = calendar.monthcalendar(self.current_year, self.current_month)
        
        # Create calendar days
        for week_num, week in enumerate(cal, 1):
            for day_num, day in enumerate(week):
                if day != 0:
                    date_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"
                    
                    # Create day frame
                    day_frame = tk.Frame(
                        self.calendar_frame, 
                        width=10, 
                        height=8,
                        borderwidth=1, 
                        relief=tk.RIDGE
                    )
                    day_frame.grid(row=week_num, column=day_num, sticky="nsew")
                    day_frame.grid_propagate(False)
                    
                    # Day number
                    tk.Label(day_frame, text=str(day), font=("Arial", 10, "bold")).pack(anchor="nw")
                    
                    # Check if holiday or attendance status
                    if date_str in self.holidays.get('national_holidays', {}):
                        holiday = self.holidays['national_holidays'][date_str]
                        tk.Label(
                            day_frame, 
                            text=holiday.get('name', 'Holiday'), 
                            fg="red", 
                            font=("Arial", 8),
                            wraplength=80
                        ).pack(fill=tk.X)
                        day_frame.config(bg="#ffdddd")
                    elif date_str in self.holidays.get('custom_holidays', {}):
                        holiday = self.holidays['custom_holidays'][date_str]
                        tk.Label(
                            day_frame, 
                            text=holiday.get('name', 'Holiday'), 
                            fg="red", 
                            font=("Arial", 8),
                            wraplength=80
                        ).pack(fill=tk.X)
                        day_frame.config(bg="#ffdddd")
                    elif date_str in self.absent_dates:
                        tk.Label(
                            day_frame, 
                            text="Absent", 
                            fg="white",
                            font=("Arial", 8)
                        ).pack(fill=tk.X)
                        day_frame.config(bg="#ff9999")
                    elif date_str in self.present_dates:
                        tk.Label(
                            day_frame, 
                            text="Present", 
                            fg="white",
                            font=("Arial", 8)
                        ).pack(fill=tk.X)
                        day_frame.config(bg="#99ff99")

    def prev_month(self):
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self.update_calendar()

    def next_month(self):
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self.update_calendar()

    def update_timetable(self):
        while True:
            try:
                response = requests.get(f"{SERVER_URL}/timetable", timeout=5)
                if response.status_code == 200:
                    self.timetable = response.json()
                    self.main_window.after(0, self.display_timetable)
            except:
                pass
            time.sleep(3600)  # Update every hour

    def display_timetable(self):
        # Clear previous timetable
        for widget in self.timetable_frame.winfo_children():
            widget.destroy()
        
        if not self.timetable:
            tk.Label(self.timetable_frame, text="No timetable available").pack()
            return
        
        # Create timetable in Excel-like format
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        periods = [
            "09:40-10:40 AM", "10:40-11:40 AM", 
            "Lunch Break", "12:10-01:10 PM", 
            "01:10-02:10 PM", "Short Break", 
            "02:20-03:10 PM", "03:10-04:10 PM"
        ]
        
        # Create header row
        header_frame = tk.Frame(self.timetable_frame)
        header_frame.pack(fill=tk.X)
        
        tk.Label(header_frame, text="Period/Day", width=15, relief=tk.RIDGE, 
                bg="#f0f0f0").grid(row=0, column=0, sticky="nsew")
        
        for col, day in enumerate(days, 1):
            tk.Label(header_frame, text=day, width=15, relief=tk.RIDGE, 
                    bg="#f0f0f0").grid(row=0, column=col, sticky="nsew")
        
        # Create timetable rows
        for row, period in enumerate(periods, 1):
            row_frame = tk.Frame(self.timetable_frame)
            row_frame.pack(fill=tk.X)
            
            tk.Label(row_frame, text=period, width=15, relief=tk.RIDGE).grid(
                row=row, column=0, sticky="nsew")
            
            for col, day in enumerate(days, 1):
                subject = self.timetable.get(day, {}).get(period, "")
                tk.Label(row_frame, text=subject, width=15, relief=tk.RIDGE).grid(
                    row=row, column=col, sticky="nsew")

    def update_attendance_data(self):
        while True:
            try:
                response = requests.get(
                    f"{SERVER_URL}/student_attendance/{self.username}",
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    self.holidays = data.get('holidays', {})
                    
                    # Update present/absent dates
                    self.present_dates = []
                    self.absent_dates = []
                    if 'attendance_history' in data:
                        for record in data['attendance_history']:
                            if record['status'] == 'present':
                                self.present_dates.append(record['date'])
                            elif record['status'] == 'absent':
                                self.absent_dates.append(record['date'])
                    
                    self.main_window.after(0, self.update_calendar)
            except:
                pass
            time.sleep(3600)  # Update every hour

    def check_attendance_session(self):
        """Check if there's an active attendance session"""
        while True:
            try:
                response = requests.get(
                    f"{SERVER_URL}/get_attendance_session",
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    self.attendance_session_active = data.get('active', False)
                    
                    if self.attendance_session_active:
                        self.main_window.after(0, self.timer_label.config, 
                            {"text": "Attendance session active - you can mark attendance", "fg": "blue"})
                        self.main_window.after(0, self.start_button.config, {"state": tk.NORMAL})
                    else:
                        self.main_window.after(0, self.timer_label.config, 
                            {"text": "No active attendance session", "fg": "black"})
                        self.main_window.after(0, self.start_button.config, {"state": tk.DISABLED})
            except:
                pass
            time.sleep(30)  # Check every 30 seconds

    def start_attendance(self):
        """Start the attendance marking process"""
        if not self.attendance_session_active:
            messagebox.showwarning("No Session", "No active attendance session")
            return
            
        if not self.is_authorized_wifi():
            messagebox.showwarning("Unauthorized WiFi", 
                "You must be connected to the school WiFi to mark attendance")
            return
            
        self.timer = 120  # 2 minutes for attendance
        self.timer_running = True
        self.start_button.config(state=tk.DISABLED)
        
        try:
            # Send initial attendance mark
            requests.post(
                f"{SERVER_URL}/update_attendance",
                json={
                    "student_id": self.username,
                    "status": "present",
                    "time_in": datetime.now().strftime("%H:%M:%S"),
                    "device_id": self.device_id,
                    "bssid": self.current_bssid
                },
                timeout=5
            )
        except:
            pass
        
        self.update_timer()

    def update_timer(self):
        if self.timer_running and self.timer > 0:
            if self.is_authorized_wifi():
                mins, secs = divmod(self.timer, 60)
                timer_text = f"Time remaining: {mins:02d}:{secs:02d}"
                self.timer_label.config(text=timer_text, fg="blue")
                self.timer -= 1
                self.main_window.after(1000, self.update_timer)
            else:
                self.timer_label.config(text="WiFi disconnected! Timer paused.", fg="red")
                try:
                    # Update status to left if disconnected
                    requests.post(
                        f"{SERVER_URL}/update_attendance",
                        json={
                            "student_id": self.username,
                            "status": "left",
                            "time_out": datetime.now().strftime("%H:%M:%S"),
                            "device_id": self.device_id
                        },
                        timeout=5
                    )
                except:
                    pass
                self.check_wifi_reconnect()
        elif self.timer_running:
            self.timer_label.config(text="Attendance Marked Successfully!", fg="green")
            self.timer_running = False
            self.start_button.config(state=tk.NORMAL)

    def check_wifi_reconnect(self):
        if not self.is_authorized_wifi():
            self.main_window.after(1000, self.check_wifi_reconnect)
        else:
            self.timer_label.config(text="WiFi reconnected! Resuming timer.", fg="blue")
            self.update_timer()

    def check_rings(self):
        """Check for random rings from teacher"""
        last_ring = ""
        while True:
            try:
                response = requests.get(
                    f"{SERVER_URL}/get_random_rings",
                    params={"student_id": self.username},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('last_ring') != last_ring:
                        last_ring = data.get('last_ring')
                        if data.get('ring_active', False):
                            self.ring_label.config(
                                text="RANDOM RING ALERT! Teacher has called on you!",
                                fg="red"
                            )
                            self.main_window.bell()  # System beep
                        else:
                            self.ring_label.config(text="")
            except:
                pass
            time.sleep(10)

    def check_wifi_status(self):
        """Continuously check and update WiFi status"""
        while True:
            current_status = self.check_wifi()
            current_bssid = self.get_bssid()
            
            # Update WiFi info display
            if current_status:
                wifi_text = f"WiFi: Connected to {self.current_wifi}"
                if self.is_authorized_wifi():
                    wifi_text += " (Authorized)"
                    self.wifi_label.config(text=wifi_text, fg="green")
                else:
                    wifi_text += " (Unauthorized)"
                    self.wifi_label.config(text=wifi_text, fg="orange")
            else:
                self.wifi_label.config(text="WiFi: Not Connected", fg="red")
            
            # Update status bar
            if current_status:
                self.status_bar.config(
                    text=f"Status: Connected to {self.current_wifi}",
                    fg="green" if self.is_authorized_wifi() else "orange"
                )
            else:
                self.status_bar.config(
                    text="Status: Not Connected to WiFi",
                    fg="red"
                )
            
            # Send update if status changed
            if current_status != self.last_wifi_status:
                try:
                    requests.post(
                        f"{SERVER_URL}/update_wifi_status",
                        json={
                            "username": self.username,
                            "status": "connected" if current_status else "disconnected",
                            "bssid": current_bssid,
                            "ssid": self.current_wifi,
                            "device": self.device_id
                        },
                        timeout=5
                    )
                except:
                    pass
                
                self.last_wifi_status = current_status
            
            time.sleep(5)

if __name__ == "__main__":
    StudentClient()
