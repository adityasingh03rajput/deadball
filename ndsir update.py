import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import threading
import requests
from datetime import datetime, timedelta
import json
import csv
import base64
from io import BytesIO
import time
import random
import pytz

# Configuration
SERVER_URL = "https://deadball.onrender.com"
UPDATE_INTERVAL = 5  # seconds
ATTENDANCE_THRESHOLD = 15  # minutes to consider student absent
TIMEZONE = 'Asia/Kolkata'  # Set your timezone here

class TeacherDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Teacher Dashboard - Attendance Management System")
        self.root.geometry("1400x900")
        
        # Style configuration
        self.configure_styles()
        
        # Login Frame
        self.setup_login_frame()
        
        # Main Frame (hidden initially)
        self.main_frame = tk.Frame(self.root)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Setup all tabs
        self.setup_attendance_tab()
        self.setup_timetable_tab()
        self.setup_student_tab()
        self.setup_holidays_tab()
        self.setup_reports_tab()
        self.setup_settings_tab()
        
        # Status Bar
        self.status_bar = tk.Label(
            self.main_frame,
            text="Status: Not Connected",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X)
        
        # Control buttons
        control_frame = tk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            control_frame,
            text="Refresh",
            command=self.manual_refresh,
            style='Control.TButton'
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            control_frame,
            text="Export Data",
            command=self.export_data,
            style='Control.TButton'
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            control_frame,
            text="Random Ring",
            command=self.random_ring,
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            control_frame,
            text="Take Attendance",
            command=self.start_attendance_session,
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        # Start update thread
        threading.Thread(target=self.update_data, daemon=True).start()
    
    def configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')  # Using a built-in Tkinter theme
        
        # Configure colors
        self.root.option_add('*TFrame*background', '#f5f5f5')
        self.root.option_add('*TLabel*background', '#f5f5f5')
        self.root.option_add('*TButton*background', '#e1e1e1')
        
        # Custom style configurations
        style.configure('Header.TLabel', 
                       background='#3F51B5', 
                       foreground='white', 
                       font=('Arial', 10, 'bold'),
                       padding=5)
        
        style.map('Primary.TButton',
                 background=[('active', '#3F51B5'), ('!active', '#5C6BC0')],
                 foreground=[('active', 'white'), ('!active', 'white')])
        
        style.map('Control.TButton',
                 background=[('active', '#757575'), ('!active', '#9E9E9E')],
                 foreground=[('active', 'white'), ('!active', 'white')])
        
        style.configure('Present.TLabel', 
                       background='#4CAF50', 
                       foreground='white',
                       padding=3)
        
        style.configure('Absent.TLabel', 
                       background='#F44336', 
                       foreground='white',
                       padding=3)
        
        style.configure('Left.TLabel', 
                       background='#FF9800', 
                       foreground='white',
                       padding=3)
        
        style.configure('Highlight.TLabel',
                      background='#FFEB3B',
                      foreground='black',
                      font=('Arial', 10, 'bold'))
    
    def setup_login_frame(self):
        self.login_frame = tk.Frame(self.root, bg='#f5f5f5')
        self.login_frame.pack(pady=50, fill=tk.BOTH, expand=True)
        
        # Logo using unicode characters
        logo_frame = tk.Frame(self.login_frame, bg='#f5f5f5')
        logo_frame.pack(pady=20)
        
        # ASCII art logo
        ascii_logo = """
          _____          _     _ _           ____              _    
         |_   _|        | |   | (_)         |  _ \            | |   
           | | ___  __ _| |__ | |_ _ __ ___ | |_) |_   _ _ __ | | __
           | |/ _ \/ _` | '_ \| | | '__/ _ \|  _ <| | | | '_ \| |/ /
           | |  __/ (_| | | | | | | | |  __/| |_) | |_| | | | |   < 
           \_/\___|\__,_|_| |_|_|_|_|  \___||____/ \__,_|_| |_|_|\_\\
        """
        tk.Label(logo_frame, text=ascii_logo, font=("Courier", 10), 
                bg='#f5f5f5', fg='#3F51B5').pack()
        
        # Login Form
        form_frame = tk.Frame(self.login_frame, bg='#ffffff', padx=20, pady=20, 
                             relief=tk.RAISED, borderwidth=2)
        form_frame.pack(pady=20)
        
        tk.Label(form_frame, text="Teacher Portal", font=("Arial", 16, 'bold'), 
                bg='#ffffff').grid(row=0, columnspan=2, pady=10)
        
        tk.Label(form_frame, text="Username:", bg='#ffffff').grid(row=1, column=0, 
                                                                padx=5, pady=5, sticky='e')
        self.username_entry = ttk.Entry(form_frame)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(form_frame, text="Password:", bg='#ffffff').grid(row=2, column=0, 
                                                                padx=5, pady=5, sticky='e')
        self.password_entry = ttk.Entry(form_frame, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)
        
        btn_frame = tk.Frame(form_frame, bg='#ffffff')
        btn_frame.grid(row=3, columnspan=2, pady=10)
        
        ttk.Button(
            btn_frame, 
            text="Login", 
            command=self.login,
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            btn_frame, 
            text="Register", 
            command=self.register,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=10)
        
        # Forgot password
        ttk.Button(
            form_frame,
            text="Forgot Password?",
            command=self.forgot_password,
            style='Link.TButton'
        ).grid(row=4, columnspan=2, pady=5)
    
    def setup_attendance_tab(self):
        self.attendance_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.attendance_tab, text="Attendance")
        
        # Top control panel
        control_frame = ttk.Frame(self.attendance_tab)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.attendance_status = ttk.Label(
            control_frame,
            text="Current Session: No active session",
            font=("Arial", 10, 'bold')
        )
        self.attendance_status.pack(side=tk.LEFT)
        
        ttk.Button(
            control_frame,
            text="End Session",
            command=self.end_attendance_session,
            style='Primary.TButton'
        ).pack(side=tk.RIGHT)
        
        # Attendance Treeview with scrollbar
        tree_frame = ttk.Frame(self.attendance_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scroll_y = ttk.Scrollbar(tree_frame)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        columns = ("Student", "Status", "Time In", "Time Out", "Duration", "WiFi Status", "Device")
        self.attendance_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show="headings",
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
            selectmode='browse'
        )
        
        for col in columns:
            self.attendance_tree.heading(col, text=col)
            self.attendance_tree.column(col, width=120, anchor=tk.CENTER)
        
        self.attendance_tree.column("Student", width=150)
        self.attendance_tree.column("Duration", width=100)
        
        self.attendance_tree.pack(fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.attendance_tree.yview)
        scroll_x.config(command=self.attendance_tree.xview)
        
        # Configure tags for attendance status
        self.attendance_tree.tag_configure('present', background='#E8F5E9')
        self.attendance_tree.tag_configure('absent', background='#FFEBEE')
        self.attendance_tree.tag_configure('left', background='#FFF3E0')
        self.attendance_tree.tag_configure('connected', foreground='#2E7D32')
        self.attendance_tree.tag_configure('disconnected', foreground='#C62828')
        self.attendance_tree.tag_configure('highlight', background='#FFF9C4')
        
        # Right-click menu
        self.attendance_menu = tk.Menu(self.root, tearoff=0)
        self.attendance_menu.add_command(label="Mark Present", command=lambda: self.mark_attendance_status("present"))
        self.attendance_menu.add_command(label="View Details", command=self.view_student_details)
        
        self.attendance_tree.bind("<Button-3>", self.show_attendance_menu)
        
        # Bottom summary
        summary_frame = ttk.Frame(self.attendance_tab)
        summary_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(summary_frame, text="Summary:", font=("Arial", 10, 'bold')).pack(side=tk.LEFT)
        
        self.present_count = ttk.Label(summary_frame, text="Present: 0", style='Present.TLabel')
        self.present_count.pack(side=tk.LEFT, padx=10)
        
        self.absent_count = ttk.Label(summary_frame, text="Absent: 0", style='Absent.TLabel')
        self.absent_count.pack(side=tk.LEFT, padx=10)
        
        self.left_count = ttk.Label(summary_frame, text="Left Early: 0", style='Left.TLabel')
        self.left_count.pack(side=tk.LEFT, padx=10)
        
        self.total_count = ttk.Label(summary_frame, text="Total: 0", font=("Arial", 10, 'bold'))
        self.total_count.pack(side=tk.LEFT, padx=10)
    
    def setup_timetable_tab(self):
        self.timetable_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.timetable_tab, text="Timetable")
        
        # Toolbar
        toolbar = ttk.Frame(self.timetable_tab)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            toolbar,
            text="Edit Timetable",
            command=self.edit_timetable,
            style='Primary.TButton'
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            toolbar,
            text="Print Timetable",
            command=self.print_timetable,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        # Timetable display
        self.timetable_display = tk.Text(
            self.timetable_tab,
            wrap=tk.NONE,
            font=("Courier New", 10),
            state=tk.DISABLED
        )
        
        scroll_y = ttk.Scrollbar(self.timetable_tab)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        scroll_x = ttk.Scrollbar(self.timetable_tab, orient=tk.HORIZONTAL)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.timetable_display.config(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set
        )
        
        self.timetable_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scroll_y.config(command=self.timetable_display.yview)
        scroll_x.config(command=self.timetable_display.xview)
    
    def setup_student_tab(self):
        self.student_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.student_tab, text="Student Management")
        
        # Notebook for student management subtabs
        student_notebook = ttk.Notebook(self.student_tab)
        student_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Registration subtab
        reg_frame = ttk.Frame(student_notebook)
        student_notebook.add(reg_frame, text="Registration")
        
        form_frame = ttk.LabelFrame(reg_frame, text="Register New Student", padding=10)
        form_frame.pack(padx=10, pady=10, fill=tk.BOTH)
        
        ttk.Label(form_frame, text="Student ID:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.student_id_entry = ttk.Entry(form_frame)
        self.student_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Full Name:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.student_name_entry = ttk.Entry(form_frame)
        self.student_name_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Class/Grade:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.student_class_entry = ttk.Combobox(form_frame, values=["Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5"])
        self.student_class_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Password:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.student_pass_entry = ttk.Entry(form_frame, show="*")
        self.student_pass_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Confirm Password:").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        self.student_confirm_pass_entry = ttk.Entry(form_frame, show="*")
        self.student_confirm_pass_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        
        btn_frame = ttk.Frame(form_frame)
        btn_frame.grid(row=5, columnspan=2, pady=10)
        
        ttk.Button(
            btn_frame,
            text="Register",
            command=self.register_student,
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Clear",
            command=self.clear_student_form,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        # Student List subtab
        list_frame = ttk.Frame(student_notebook)
        student_notebook.add(list_frame, text="Student Directory")
        
        # Search bar
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.student_search_entry = ttk.Entry(search_frame)
        self.student_search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.student_search_entry.bind("<KeyRelease>", self.search_students)
        
        ttk.Button(
            search_frame,
            text="Refresh",
            command=self.refresh_student_list,
            style='Control.TButton'
        ).pack(side=tk.RIGHT, padx=5)
        
        # Student list treeview
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scroll_y = ttk.Scrollbar(tree_frame)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("ID", "Name", "Class", "Last Seen", "Status")
        self.student_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show="headings",
            yscrollcommand=scroll_y.set,
            selectmode='browse'
        )
        
        for col in columns:
            self.student_tree.heading(col, text=col)
            self.student_tree.column(col, width=120)
        
        self.student_tree.column("Name", width=200)
        self.student_tree.column("ID", width=80)
        
        self.student_tree.pack(fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.student_tree.yview)
        
        # Configure tags for status
        self.student_tree.tag_configure('active', background='#E8F5E9')
        self.student_tree.tag_configure('inactive', background='#FFEBEE')
        
        # Right-click menu for student actions
        self.student_menu = tk.Menu(self.root, tearoff=0)
        self.student_menu.add_command(label="View Profile", command=self.view_student_profile)
        self.student_menu.add_command(label="Mark Present", command=lambda: self.mark_student_present_from_list())
        
        self.student_tree.bind("<Button-3>", self.show_student_menu)
    
    def setup_holidays_tab(self):
        self.holidays_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.holidays_tab, text="Holidays")
        
        # Toolbar
        toolbar = ttk.Frame(self.holidays_tab)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            toolbar,
            text="Add Holiday",
            command=self.add_holiday,
            style='Primary.TButton'
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            toolbar,
            text="Delete Selected",
            command=self.delete_holiday,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            toolbar,
            text="Import Holidays",
            command=self.import_holidays,
            style='Control.TButton'
        ).pack(side=tk.RIGHT)
        
        # Holidays Treeview
        tree_frame = ttk.Frame(self.holidays_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scroll_y = ttk.Scrollbar(tree_frame)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("Date", "Name", "Type", "Description")
        self.holidays_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show="headings",
            yscrollcommand=scroll_y.set,
            selectmode='browse'
        )
        
        for col in columns:
            self.holidays_tree.heading(col, text=col)
            self.holidays_tree.column(col, width=120)
        
        self.holidays_tree.column("Name", width=200)
        self.holidays_tree.column("Description", width=300)
        
        self.holidays_tree.pack(fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.holidays_tree.yview)
        
        # Configure tags for holiday types
        self.holidays_tree.tag_configure('national', background='#E3F2FD')
        self.holidays_tree.tag_configure('custom', background='#E8F5E9')
    
    def setup_reports_tab(self):
        self.reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text="Reports")
        
        # Report type selection
        report_frame = ttk.LabelFrame(self.reports_tab, text="Generate Report", padding=10)
        report_frame.pack(padx=10, pady=10, fill=tk.BOTH)
        
        ttk.Label(report_frame, text="Report Type:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.report_type = ttk.Combobox(
            report_frame, 
            values=[
                "Daily Attendance Summary",
                "Monthly Attendance Report",
                "Student Attendance History",
                "Class Attendance Statistics"
            ]
        )
        self.report_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.report_type.current(0)
        
        # Date range selection
        ttk.Label(report_frame, text="From:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.report_from_date = ttk.Entry(report_frame)
        self.report_from_date.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.report_from_date.insert(0, datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d"))
        
        ttk.Label(report_frame, text="To:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.report_to_date = ttk.Entry(report_frame)
        self.report_to_date.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.report_to_date.insert(0, datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d"))
        
        # Class selection
        ttk.Label(report_frame, text="Class:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.report_class = ttk.Combobox(report_frame, values=["All", "Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5"])
        self.report_class.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.report_class.current(0)
        
        # Generate button
        ttk.Button(
            report_frame,
            text="Generate Report",
            command=self.generate_report,
            style='Primary.TButton'
        ).grid(row=4, columnspan=2, pady=10)
        
        # Report display area
        self.report_display = tk.Text(
            self.reports_tab,
            wrap=tk.WORD,
            font=("Arial", 10),
            state=tk.DISABLED
        )
        
        scroll_y = ttk.Scrollbar(self.reports_tab)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.report_display.config(yscrollcommand=scroll_y.set)
        self.report_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scroll_y.config(command=self.report_display.yview)
        
        # Export buttons
        export_frame = ttk.Frame(self.reports_tab)
        export_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(
            export_frame,
            text="Print Report",
            command=self.print_report,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            export_frame,
            text="Export as PDF",
            command=self.export_pdf,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            export_frame,
            text="Export as CSV",
            command=self.export_csv,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)
    
    def setup_settings_tab(self):
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="Settings")
        
        # Personal settings
        personal_frame = ttk.LabelFrame(self.settings_tab, text="Personal Settings", padding=10)
        personal_frame.pack(padx=10, pady=10, fill=tk.X)
        
        ttk.Label(personal_frame, text="Change Password").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        
        ttk.Label(personal_frame, text="Current Password:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.current_pass_entry = ttk.Entry(personal_frame, show="*")
        self.current_pass_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(personal_frame, text="New Password:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.new_pass_entry = ttk.Entry(personal_frame, show="*")
        self.new_pass_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(personal_frame, text="Confirm New Password:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.confirm_pass_entry = ttk.Entry(personal_frame, show="*")
        self.confirm_pass_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Button(
            personal_frame,
            text="Update Password",
            command=self.change_password,
            style='Primary.TButton'
        ).grid(row=4, columnspan=2, pady=10)
        
        # System settings
        system_frame = ttk.LabelFrame(self.settings_tab, text="System Settings", padding=10)
        system_frame.pack(padx=10, pady=10, fill=tk.X)
        
        ttk.Label(system_frame, text="WiFi Detection Range (meters):").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.wifi_range = ttk.Entry(system_frame)
        self.wifi_range.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.wifi_range.insert(0, "50")
        
        ttk.Label(system_frame, text="Attendance Threshold (minutes):").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.attendance_threshold = ttk.Entry(system_frame)
        self.attendance_threshold.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.attendance_threshold.insert(0, str(ATTENDANCE_THRESHOLD))
        
        ttk.Button(
            system_frame,
            text="Save Settings",
            command=self.save_settings,
            style='Primary.TButton'
        ).grid(row=2, columnspan=2, pady=10)
    
    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
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
                if data.get('type') == 'teacher':
                    self.login_frame.pack_forget()
                    self.main_frame.pack(fill=tk.BOTH, expand=True)
                    self.update_status("Connected")
                    self.refresh_student_list()
                    self.refresh_holidays()
                    self.load_timetable()
                else:
                    messagebox.showerror("Error", "Students must use the student portal")
            else:
                messagebox.showerror("Error", data.get('error', 'Login failed'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def register(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Error", "Please enter both username and password")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/register",
                json={
                    "username": username,
                    "password": password,
                    "type": "teacher"
                },
                timeout=5
            )
            
            if response.status_code == 201:
                messagebox.showinfo("Success", "Teacher registered successfully!")
            else:
                messagebox.showerror("Error", response.json().get('error', 'Registration failed'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def forgot_password(self):
        username = simpledialog.askstring("Forgot Password", "Enter your username:")
        if username:
            messagebox.showinfo("Instructions", f"Password reset instructions will be sent to the email associated with {username}")

    def update_status(self, message, color="black"):
        self.status_bar.config(text=f"Status: {message}", fg=color)

    def manual_refresh(self):
        self.update_data(force=True)

    def update_data(self, force=False):
        while True:
            try:
                # Update attendance
                response = requests.get(f"{SERVER_URL}/get_attendance", timeout=5)
                
                if response.status_code == 200:
                    attendance_data = response.json()
                    self.root.after(0, self.update_attendance_table, attendance_data)
                
                # Update timetable if not loaded or forced
                if force or not hasattr(self, 'timetable_loaded'):
                    self.load_timetable()
                
                # Update holidays if not loaded or forced
                if force or not hasattr(self, 'holidays_loaded'):
                    self.refresh_holidays()
                
                self.update_status("Connected", "blue")
            except requests.RequestException:
                self.update_status("Connection Error", "red")
            
            time.sleep(UPDATE_INTERVAL)

    def update_attendance_table(self, data):
        for row in self.attendance_tree.get_children():
            self.attendance_tree.delete(row)
            
        students_data = data.get('students', {})
        current_time = datetime.now(pytz.timezone(TIMEZONE))
        
        present_count = 0
        absent_count = 0
        left_count = 0
        
        for student, info in students_data.items():
            status = info.get('status', 'absent').capitalize()
            time_in_str = info.get('time_in', '')
            time_out_str = info.get('time_out', '')
            duration = info.get('duration', '')
            wifi_status = info.get('wifi_status', 'unknown').capitalize()
            device = info.get('device', 'Unknown')
            
            # Update counters
            if status.lower() == 'present':
                present_count += 1
            elif status.lower() == 'absent':
                absent_count += 1
            elif status.lower() == 'left':
                left_count += 1
            
            item = self.attendance_tree.insert("", tk.END, values=(
                student, 
                status, 
                time_in_str, 
                time_out_str,
                duration,
                wifi_status,
                device
            ), tags=(status.lower(),))
            
            # Additional tag for wifi status
            if wifi_status.lower() == 'connected':
                self.attendance_tree.item(item, tags=(*self.attendance_tree.item(item)['tags'], 'connected'))
            elif wifi_status.lower() == 'disconnected':
                self.attendance_tree.item(item, tags=(*self.attendance_tree.item(item)['tags'], 'disconnected'))
        
        # Update summary counters
        self.present_count.config(text=f"Present: {present_count}")
        self.absent_count.config(text=f"Absent: {absent_count}")
        self.left_count.config(text=f"Left Early: {left_count}")
        self.total_count.config(text=f"Total: {present_count + absent_count + left_count}")

    def load_timetable(self):
        try:
            response = requests.get(f"{SERVER_URL}/timetable", timeout=5)
            if response.status_code == 200:
                timetable = response.json()
                self.display_timetable(timetable)
                self.timetable_loaded = True
        except requests.RequestException:
            messagebox.showerror("Error", "Could not load timetable")

    def display_timetable(self, timetable_data):
        self.timetable_display.config(state=tk.NORMAL)
        self.timetable_display.delete(1.0, tk.END)
        
        if not timetable_data:
            self.timetable_display.insert(tk.END, "No timetable available")
            self.timetable_display.config(state=tk.DISABLED)
            return
        
        # Create a formatted timetable display
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        periods = [
            "09:40-10:40 AM", "10:40-11:40 AM", 
            "Lunch Break", "12:10-01:10 PM", 
            "01:10-02:10 PM", "Short Break", 
            "02:20-03:10 PM", "03:10-04:10 PM"
        ]
        
        # Create header
        header = "Period/Day".ljust(20)
        for day in days:
            header += day.ljust(20)
        self.timetable_display.insert(tk.END, header + "\n")
        self.timetable_display.insert(tk.END, "-" * 140 + "\n")
        
        # Add timetable rows
        for period in periods:
            row = period.ljust(20)
            for day in days:
                subject = timetable_data.get(day, {}).get(period, "")
                row += subject.ljust(20)
            self.timetable_display.insert(tk.END, row + "\n")
        
        self.timetable_display.config(state=tk.DISABLED)

    def edit_timetable(self):
        # Get current timetable
        try:
            response = requests.get(f"{SERVER_URL}/timetable", timeout=5)
            current_timetable = response.json() if response.status_code == 200 else {}
        except:
            current_timetable = {}
        
        # Create edit dialog
        edit_window = tk.Toplevel(self.root)
        edit_window.title("Edit Timetable")
        edit_window.geometry("1000x700")
        
        # Days and periods
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        periods = [
            "09:40-10:40 AM", "10:40-11:40 AM", 
            "Lunch Break", "12:10-01:10 PM", 
            "01:10-02:10 PM", "Short Break", 
            "02:20-03:10 PM", "03:10-04:10 PM"
        ]
        
        # Create a frame with scrollbars
        container = ttk.Frame(edit_window)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Create a canvas
        canvas = tk.Canvas(container)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create a frame inside the canvas
        grid_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=grid_frame, anchor="nw")
        
        # Configure the canvas scrolling
        grid_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        # Store entry widgets for later access
        self.timetable_entries = {}
        
        # Create header row
        ttk.Label(grid_frame, text="Period/Day", width=20, relief=tk.RIDGE, 
                 style='Header.TLabel').grid(row=0, column=0, sticky="nsew")
        
        for col, day in enumerate(days, 1):
            ttk.Label(grid_frame, text=day, width=20, relief=tk.RIDGE, 
                     style='Header.TLabel').grid(row=0, column=col, sticky="nsew")
        
        # Create timetable rows with entry widgets
        for row, period in enumerate(periods, 1):
            # Period label
            ttk.Label(grid_frame, text=period, width=20, relief=tk.RIDGE).grid(
                row=row, column=0, sticky="nsew")
            
            # Entry widgets for each day
            for col, day in enumerate(days, 1):
                # Get current subject for this slot
                subject = current_timetable.get(day, {}).get(period, "")
                
                # Create entry widget
                entry = ttk.Entry(grid_frame, width=20)
                entry.insert(0, subject)
                entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
                
                # Store reference to the widget
                self.timetable_entries[(day, period)] = entry
        
        # Save button
        save_frame = ttk.Frame(edit_window)
        save_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            save_frame,
            text="Save Timetable",
            command=lambda: self.save_grid_timetable(days, periods, edit_window),
            style='Primary.TButton'
        ).pack(pady=5)

    def save_grid_timetable(self, days, periods, window):
        timetable = {}
        
        # Collect data from all entry widgets
        for day in days:
            day_schedule = {}
            for period in periods:
                entry = self.timetable_entries.get((day, period))
                if entry:
                    subject = entry.get().strip()
                    if subject:  # Only add if not empty
                        day_schedule[period] = subject
            
            if day_schedule:  # Only add day if it has schedules
                timetable[day] = day_schedule
        
        try:
            response = requests.post(
                f"{SERVER_URL}/timetable",
                json={"timetable": timetable},
                timeout=5
            )
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "Timetable updated successfully!")
                window.destroy()
                self.display_timetable(timetable)
            else:
                messagebox.showerror("Error", "Failed to update timetable")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def print_timetable(self):
        """Print the current timetable (simulated)"""
        messagebox.showinfo("Print", "Timetable printing initiated (simulated)")

    def register_student(self):
        student_id = self.student_id_entry.get()
        name = self.student_name_entry.get()
        student_class = self.student_class_entry.get()
        password = self.student_pass_entry.get()
        confirm_pass = self.student_confirm_pass_entry.get()
        
        if not all([student_id, name, student_class, password, confirm_pass]):
            messagebox.showwarning("Error", "Please fill all fields")
            return
            
        if password != confirm_pass:
            messagebox.showwarning("Error", "Passwords do not match")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/register_student",
                json={
                    "student_id": student_id,
                    "name": name,
                    "class": student_class,
                    "password": password
                },
                timeout=5
            )
            
            if response.status_code == 201:
                messagebox.showinfo("Success", f"Student {name} registered!")
                self.clear_student_form()
                self.refresh_student_list()
            else:
                messagebox.showerror("Error", response.json().get('error', 'Registration failed'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def clear_student_form(self):
        """Clear the student registration form"""
        self.student_id_entry.delete(0, tk.END)
        self.student_name_entry.delete(0, tk.END)
        self.student_class_entry.set('')
        self.student_pass_entry.delete(0, tk.END)
        self.student_confirm_pass_entry.delete(0, tk.END)

    def refresh_student_list(self):
        try:
            response = requests.get(f"{SERVER_URL}/get_students", timeout=5)
            if response.status_code == 200:
                students = response.json()
                self.update_student_tree(students)
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def update_student_tree(self, students):
        """Update the student treeview with new data"""
        for row in self.student_tree.get_children():
            self.student_tree.delete(row)
            
        for student in students:
            status = "Active" if student.get('active', True) else "Inactive"
            tags = ('active',) if student.get('active', True) else ('inactive',)
            
            self.student_tree.insert("", tk.END, values=(
                student.get('id', ''),
                student.get('name', ''),
                student.get('class', ''),
                student.get('last_seen', 'Never'),
                status
            ), tags=tags)

    def search_students(self, event=None):
        """Filter students based on search term"""
        search_term = self.student_search_entry.get().lower()
        
        for child in self.student_tree.get_children():
            values = self.student_tree.item(child)['values']
            if search_term in ' '.join(map(str, values)).lower():
                self.student_tree.item(child, tags=self.student_tree.item(child)['tags'])
            else:
                self.student_tree.item(child, tags=('hidden',))
        
        self.student_tree.tag_configure('hidden', foreground='gray')

    def view_student_profile(self):
        """View detailed profile of selected student"""
        selected = self.student_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a student first")
            return
        
        student_id = self.student_tree.item(selected[0])['values'][0]
        
        try:
            response = requests.get(
                f"{SERVER_URL}/student_details/{student_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                details = response.json()
                self.show_student_profile_window(details)
            else:
                messagebox.showerror("Error", "Failed to get student details")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def show_student_profile_window(self, details):
        """Display student profile in a new window"""
        profile_window = tk.Toplevel(self.root)
        profile_window.title(f"Student Profile - {details.get('name', '')}")
        profile_window.geometry("500x400")
        
        # Header with ASCII art placeholder
        header_frame = ttk.Frame(profile_window)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # ASCII art for profile picture
        ascii_art = """
          -----
         /     \\
        |  O O  |
        |   ∆   |
         \  --- /
          -----
        """
        photo_frame = ttk.Frame(header_frame, width=80, height=80, relief=tk.SUNKEN)
        photo_frame.pack(side=tk.LEFT)
        photo_frame.pack_propagate(False)
        tk.Label(photo_frame, text=ascii_art, font=("Courier", 6)).pack(expand=True)
        
        info_frame = ttk.Frame(header_frame)
        info_frame.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        tk.Label(info_frame, text=details.get('name', ''), font=("Arial", 14, 'bold')).pack(anchor='w')
        tk.Label(info_frame, text=f"ID: {details.get('id', '')} | Class: {details.get('class', '')}").pack(anchor='w')
        
        # Details notebook
        notebook = ttk.Notebook(profile_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Personal Info tab
        personal_frame = ttk.Frame(notebook)
        notebook.add(personal_frame, text="Personal Info")
        
        fields = [
            ("Name", details.get('name', '')),
            ("ID", details.get('id', '')),
            ("Class", details.get('class', '')),
            ("Email", details.get('email', 'Not provided')),
            ("Phone", details.get('phone', 'Not provided')),
            ("Address", details.get('address', 'Not provided'))
        ]
        
        for i, (label, value) in enumerate(fields):
            ttk.Label(personal_frame, text=label+":", font=("Arial", 10, 'bold')).grid(row=i, column=0, padx=5, pady=2, sticky='e')
            ttk.Label(personal_frame, text=value).grid(row=i, column=1, padx=5, pady=2, sticky='w')
        
        # Attendance Stats tab
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Attendance Stats")
        
        # Get attendance stats
        try:
            response = requests.get(
                f"{SERVER_URL}/student_attendance/{details.get('id', '')}",
                timeout=5
            )
            
            if response.status_code == 200:
                stats = response.json()
                
                attendance_fields = [
                    ("Total Classes", stats.get('total_classes', 0)),
                    ("Present", stats.get('present', 0)),
                    ("Absent", stats.get('absent', 0)),
                    ("Left Early", stats.get('left', 0)),
                    ("Attendance %", f"{stats.get('attendance_percent', 0):.1f}%")
                ]
                
                for i, (label, value) in enumerate(attendance_fields):
                    ttk.Label(stats_frame, text=label+":", font=("Arial", 10, 'bold')).grid(row=i, column=0, padx=5, pady=2, sticky='e')
                    ttk.Label(stats_frame, text=value).grid(row=i, column=1, padx=5, pady=2, sticky='w')
            else:
                ttk.Label(stats_frame, text="No attendance data available").pack(pady=20)
        except requests.RequestException:
            ttk.Label(stats_frame, text="Could not load attendance data").pack(pady=20)
        
        # Close button
        ttk.Button(
            profile_window,
            text="Close",
            command=profile_window.destroy,
            style='Control.TButton'
        ).pack(pady=10)

    def mark_student_present_from_list(self):
        """Mark a student as present from the student list"""
        selected = self.student_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a student first")
            return
        
        student_id = self.student_tree.item(selected[0])['values'][0]
        self.mark_attendance_status("present", student_id)

    def refresh_holidays(self):
        try:
            response = requests.get(f"{SERVER_URL}/get_holidays", timeout=5)
            if response.status_code == 200:
                holidays = response.json()
                self.update_holidays_display(holidays)
                self.holidays_loaded = True
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def update_holidays_display(self, holidays_data):
        for row in self.holidays_tree.get_children():
            self.holidays_tree.delete(row)
            
        national_holidays = holidays_data.get('national_holidays', {})
        custom_holidays = holidays_data.get('custom_holidays', {})
        
        # Add national holidays
        for date, info in national_holidays.items():
            self.holidays_tree.insert(
                "", tk.END, 
                values=(date, info.get('name', ''), "National", info.get('description', '')),
                tags=('national',)
            )
        
        # Add custom holidays
        for date, info in custom_holidays.items():
            self.holidays_tree.insert(
                "", tk.END, 
                values=(date, info.get('name', ''), "Custom", info.get('description', '')),
                tags=('custom',)
            )

    def add_holiday(self):
        """Add a new holiday"""
        add_window = tk.Toplevel(self.root)
        add_window.title("Add Holiday")
        add_window.geometry("400x300")
        
        form_frame = ttk.Frame(add_window, padding=10)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(form_frame, text="Date (YYYY-MM-DD):").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        date_entry = ttk.Entry(form_frame)
        date_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        date_entry.insert(0, datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d"))
        
        ttk.Label(form_frame, text="Holiday Name:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        name_entry = ttk.Entry(form_frame)
        name_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Description:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        desc_entry = tk.Text(form_frame, height=5, width=30)
        desc_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(form_frame, text="Type:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        type_var = tk.StringVar(value="custom")
        ttk.Radiobutton(form_frame, text="Custom", variable=type_var, value="custom").grid(row=3, column=1, padx=5, pady=5, sticky='w')
        ttk.Radiobutton(form_frame, text="National", variable=type_var, value="national").grid(row=4, column=1, padx=5, pady=5, sticky='w')
        
        btn_frame = ttk.Frame(form_frame)
        btn_frame.grid(row=5, columnspan=2, pady=10)
        
        ttk.Button(
            btn_frame,
            text="Add Holiday",
            command=lambda: self.save_new_holiday(
                date_entry.get(),
                name_entry.get(),
                desc_entry.get("1.0", tk.END).strip(),
                type_var.get(),
                add_window
            ),
            style='Primary.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=add_window.destroy,
            style='Control.TButton'
        ).pack(side=tk.LEFT, padx=5)

    def save_new_holiday(self, date, name, description, holiday_type, window):
        """Save the new holiday to the server"""
        if not all([date, name]):
            messagebox.showwarning("Error", "Date and name are required")
            return
            
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/update_holidays",
                json={
                    "date": date,
                    "name": name,
                    "description": description,
                    "type": holiday_type
                },
                timeout=5
            )
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "Holiday added successfully!")
                window.destroy()
                self.refresh_holidays()
            else:
                messagebox.showerror("Error", response.json().get('error', 'Failed to add holiday'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def delete_holiday(self):
        """Delete the selected holiday"""
        selected = self.holidays_tree.selection()
        if not selected:
            messagebox.showwarning("Error", "Please select a holiday to delete")
            return
            
        item = self.holidays_tree.item(selected[0])
        date = item['values'][0]
        holiday_type = item['values'][2]
        
        if holiday_type == "National":
            messagebox.showwarning("Error", "Cannot delete national holidays")
            return
            
        confirm = messagebox.askyesno("Confirm", f"Delete holiday on {date}?")
        if not confirm:
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/update_holidays",
                json={"date": date, "action": "delete"},
                timeout=5
            )
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "Holiday deleted successfully!")
                self.refresh_holidays()
            else:
                messagebox.showerror("Error", response.json().get('error', 'Failed to delete holiday'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def import_holidays(self):
        """Import holidays from a CSV file"""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Select Holidays CSV File"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                holidays = []
                
                for row in reader:
                    holidays.append({
                        "date": row.get('date', ''),
                        "name": row.get('name', ''),
                        "description": row.get('description', ''),
                        "type": row.get('type', 'custom')
                    })
                
                if not holidays:
                    messagebox.showwarning("Warning", "No holidays found in file")
                    return
                
                # Send to server
                response = requests.post(
                    f"{SERVER_URL}/import_holidays",
                    json={"holidays": holidays},
                    timeout=10
                )
                
                if response.status_code == 200:
                    messagebox.showinfo("Success", f"Imported {len(holidays)} holidays successfully!")
                    self.refresh_holidays()
                else:
                    messagebox.showerror("Error", response.json().get('error', 'Failed to import holidays'))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import holidays: {str(e)}")

    def generate_report(self):
        """Generate the selected report"""
        report_type = self.report_type.get()
        from_date = self.report_from_date.get()
        to_date = self.report_to_date.get()
        class_filter = self.report_class.get()
        
        try:
            # First check if dates are valid
            datetime.strptime(from_date, "%Y-%m-%d")
            datetime.strptime(to_date, "%Y-%m-%d")
            
            # Generate report locally since we don't have a real server
            report_text = self.generate_local_report(report_type, from_date, to_date, class_filter)
            
            self.report_display.config(state=tk.NORMAL)
            self.report_display.delete(1.0, tk.END)
            self.report_display.insert(tk.END, report_text)
            self.report_display.config(state=tk.DISABLED)
            
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Please use YYYY-MM-DD")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")

    def generate_local_report(self, report_type, from_date, to_date, class_filter):
        """Generate a report locally with sample data"""
        # This is a simulation since we don't have a real server
        report_lines = []
        report_lines.append(f"Report Type: {report_type}")
        report_lines.append(f"Date Range: {from_date} to {to_date}")
        report_lines.append(f"Class Filter: {class_filter}")
        report_lines.append("\n=== Attendance Summary ===")
        
        # Sample data for demonstration
        if report_type == "Daily Attendance Summary":
            report_lines.append("\nDate: 2023-10-01")
            report_lines.append("Present: 25")
            report_lines.append("Absent: 5")
            report_lines.append("Left Early: 2")
            report_lines.append("\nDate: 2023-10-02")
            report_lines.append("Present: 27")
            report_lines.append("Absent: 3")
            report_lines.append("Left Early: 1")
        elif report_type == "Monthly Attendance Report":
            report_lines.append("\nMonth: October 2023")
            report_lines.append("Total Classes: 20")
            report_lines.append("Average Attendance: 85%")
            report_lines.append("Top Attendees: Student1 (100%), Student2 (98%)")
            report_lines.append("Lowest Attendees: Student30 (65%), Student25 (70%)")
        elif report_type == "Student Attendance History":
            report_lines.append("\nStudent: John Doe (ID: S1001)")
            report_lines.append("Total Classes: 20")
            report_lines.append("Present: 18 (90%)")
            report_lines.append("Absent: 2 (10%)")
            report_lines.append("Left Early: 0 (0%)")
        elif report_type == "Class Attendance Statistics":
            report_lines.append("\nClass: Grade 5")
            report_lines.append("Total Students: 30")
            report_lines.append("Average Attendance: 88%")
            report_lines.append("Best Day: 2023-10-15 (95% attendance)")
            report_lines.append("Worst Day: 2023-10-30 (75% attendance)")
        
        report_lines.append("\n=== End of Report ===")
        return "\n".join(report_lines)

    def print_report(self):
        """Print the current report (simulated)"""
        messagebox.showinfo("Print", "Report printing initiated (simulated)")

    def export_pdf(self):
        """Export report as PDF (simulated)"""
        messagebox.showinfo("Export", "PDF export would be implemented here")

    def export_csv(self):
        """Export report as CSV"""
        report_text = self.report_display.get("1.0", tk.END)
        if not report_text.strip():
            messagebox.showwarning("Warning", "No report to export")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Save Report As"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='') as csvfile:
                # Simple CSV export - could be enhanced based on report structure
                writer = csv.writer(csvfile)
                for line in report_text.split('\n'):
                    if line.strip():
                        writer.writerow([line])
            
            messagebox.showinfo("Success", f"Report exported to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

    def change_password(self):
        """Change the teacher's password"""
        current_pass = self.current_pass_entry.get()
        new_pass = self.new_pass_entry.get()
        confirm_pass = self.confirm_pass_entry.get()
        
        if not all([current_pass, new_pass, confirm_pass]):
            messagebox.showwarning("Error", "Please fill all fields")
            return
            
        if new_pass != confirm_pass:
            messagebox.showwarning("Error", "New passwords do not match")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/change_password",
                json={
                    "username": self.username_entry.get(),
                    "current_password": current_pass,
                    "new_password": new_pass
                },
                timeout=5
            )
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "Password changed successfully!")
                self.current_pass_entry.delete(0, tk.END)
                self.new_pass_entry.delete(0, tk.END)
                self.confirm_pass_entry.delete(0, tk.END)
            else:
                messagebox.showerror("Error", response.json().get('error', 'Failed to change password'))
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def save_settings(self):
        """Save system settings"""
        wifi_range = self.wifi_range.get()
        threshold = self.attendance_threshold.get()
        
        if not wifi_range.isdigit() or not threshold.isdigit():
            messagebox.showwarning("Error", "Please enter valid numbers")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/update_settings",
                json={
                    "wifi_range": int(wifi_range),
                    "attendance_threshold": int(threshold)
                },
                timeout=5
            )
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "Settings saved successfully!")
            else:
                messagebox.showerror("Error", "Failed to save settings")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def start_attendance_session(self):
        """Start a new attendance session"""
        try:
            response = requests.post(
                f"{SERVER_URL}/start_session",
                json={"teacher": self.username_entry.get()},
                timeout=5
            )
            
            if response.status_code == 200:
                current_time = datetime.now(pytz.timezone(TIMEZONE)).strftime('%H:%M:%S')
                self.attendance_status.config(
                    text=f"Current Session: Active (Started at {current_time})",
                    foreground="green"
                )
                messagebox.showinfo("Success", "Attendance session started!")
            else:
                messagebox.showerror("Error", "Failed to start session")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def end_attendance_session(self):
        """End the current attendance session"""
        try:
            response = requests.post(
                f"{SERVER_URL}/end_session",
                timeout=5
            )
            
            if response.status_code == 200:
                self.attendance_status.config(
                    text="Current Session: No active session",
                    foreground="black"
                )
                messagebox.showinfo("Success", "Attendance session ended!")
            else:
                messagebox.showerror("Error", "Failed to end session")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def mark_attendance_status(self, status, student_id=None):
        """Manually mark a student's attendance status"""
        if not student_id:
            selected = self.attendance_tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select a student first")
                return
            student = self.attendance_tree.item(selected[0])['values'][0]
        else:
            student = student_id
        
        try:
            response = requests.post(
                f"{SERVER_URL}/mark_attendance",
                json={
                    "student": student,
                    "status": status,
                    "manual": True
                },
                timeout=5
            )
            
            if response.status_code == 200:
                self.update_attendance_table(response.json().get('attendance', {}))
                messagebox.showinfo("Success", f"Marked {student} as {status}")
            else:
                messagebox.showerror("Error", "Failed to update attendance")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def view_student_details(self):
        """View detailed information about a student"""
        selected = self.attendance_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a student first")
            return
        
        student = self.attendance_tree.item(selected[0])['values'][0]
        
        try:
            response = requests.get(
                f"{SERVER_URL}/student_details/{student}",
                timeout=5
            )
            
            if response.status_code == 200:
                details = response.json()
                self.show_student_profile_window(details)
            else:
                messagebox.showerror("Error", "Failed to get student details")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")

    def random_ring(self):
        """Randomly select 2 students and highlight them"""
        # Get all student IDs from the attendance tree
        all_students = []
        for child in self.attendance_tree.get_children():
            student = self.attendance_tree.item(child)['values'][0]
            all_students.append(student)
        
        if len(all_students) < 2:
            messagebox.showwarning("Warning", "Need at least 2 students for random ring")
            return
        
        # Select 2 random students
        selected_students = random.sample(all_students, 2)
        
        # Clear previous highlights
        for child in self.attendance_tree.get_children():
            current_tags = list(self.attendance_tree.item(child)['tags'])
            if 'highlight' in current_tags:
                current_tags.remove('highlight')
                self.attendance_tree.item(child, tags=tuple(current_tags))
        
        # Highlight the selected students
        for child in self.attendance_tree.get_children():
            student = self.attendance_tree.item(child)['values'][0]
            if student in selected_students:
                current_tags = list(self.attendance_tree.item(child)['tags'])
                current_tags.append('highlight')
                self.attendance_tree.item(child, tags=tuple(current_tags))
        
        messagebox.showinfo("Random Ring", f"Selected students: {', '.join(selected_students)}")

    def export_data(self):
        """Export attendance data to a file"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Get current attendance data
            response = requests.get(f"{SERVER_URL}/get_attendance", timeout=5)
            
            if response.status_code == 200:
                attendance_data = response.json().get('students', {})
                
                # Write to CSV
                with open(file_path, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Student', 'Status', 'Time In', 'Time Out', 'Duration', 'WiFi Status', 'Device'])
                    
                    for student, data in attendance_data.items():
                        writer.writerow([
                            student,
                            data.get('status', ''),
                            data.get('time_in', ''),
                            data.get('time_out', ''),
                            data.get('duration', ''),
                            data.get('wifi_status', ''),
                            data.get('device', '')
                        ])
                
                messagebox.showinfo("Success", f"Data exported to {file_path}")
            else:
                messagebox.showerror("Error", "Failed to get attendance data")
        except requests.RequestException:
            messagebox.showerror("Error", "Could not connect to server")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

    def show_attendance_menu(self, event):
        """Show right-click menu for attendance tree"""
        item = self.attendance_tree.identify_row(event.y)
        if item:
            self.attendance_tree.selection_set(item)
            self.attendance_menu.post(event.x_root, event.y_root)

    def show_student_menu(self, event):
        """Show right-click menu for student tree"""
        item = self.student_tree.identify_row(event.y)
        if item:
            self.student_tree.selection_set(item)
            self.student_menu.post(event.x_root, event.y_root)

if __name__ == "__main__":
    root = tk.Tk()
    app = TeacherDashboard(root)
    root.mainloop()
