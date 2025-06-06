import requests
import json
from datetime import datetime, timedelta
import time
import getpass
import pytz

# Configuration
SERVER_URL = "http://localhost:5000"  # Change to your server URL
TIMEZONE = 'Asia/Kolkata'

class TeacherClient:
    def __init__(self):
        self.username = None
        self.session_token = None
        self.current_menu = None
    
    def login(self):
        """Handle teacher login"""
        print("\n" + "="*50)
        print("TEACHER LOGIN".center(50))
        print("="*50)
        
        while not self.username:
            username = input("\nUsername: ").strip()
            password = getpass.getpass("Password: ").strip()
            
            try:
                response = requests.post(
                    f"{SERVER_URL}/login",
                    json={"username": username, "password": password}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('type') == 'teacher':
                        self.username = username
                        print("\nLogin successful!")
                    else:
                        print("\nError: Only teachers can use this portal")
                else:
                    print(f"\nLogin failed: {response.json().get('error', 'Unknown error')}")
            except requests.exceptions.RequestException:
                print("\nError: Could not connect to server")
    
    def main_menu(self):
        """Display main menu"""
        self.current_menu = "main"
        while self.current_menu == "main":
            print("\n" + "="*50)
            print("MAIN MENU".center(50))
            print("="*50)
            print(f"\nLogged in as: {self.username}")
            
            print("\n1. Attendance Management")
            print("2. Student Management")
            print("3. Timetable Management")
            print("4. Reports")
            print("5. System Settings")
            print("0. Exit")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.attendance_menu()
            elif choice == "2":
                self.student_menu()
            elif choice == "3":
                self.timetable_menu()
            elif choice == "4":
                self.reports_menu()
            elif choice == "5":
                self.settings_menu()
            elif choice == "0":
                self.current_menu = None
                print("\nLogging out...")
            else:
                print("Invalid choice. Please try again.")
    
    def attendance_menu(self):
        """Attendance management menu"""
        self.current_menu = "attendance"
        while self.current_menu == "attendance":
            print("\n" + "="*50)
            print("ATTENDANCE MANAGEMENT".center(50))
            print("="*50)
            
            # Check current session status
            session_status = self.get_attendance_session_status()
            print(f"\nCurrent Session: {'ACTIVE' if session_status else 'INACTIVE'}")
            
            print("\n1. Start Attendance Session")
            print("2. End Attendance Session")
            print("3. View Current Attendance")
            print("4. Mark Student Present/Absent")
            print("5. Random Student Call")
            print("6. Export Attendance Data")
            print("0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.start_attendance_session()
            elif choice == "2":
                self.end_attendance_session()
            elif choice == "3":
                self.view_current_attendance()
            elif choice == "4":
                self.mark_student_attendance()
            elif choice == "5":
                self.random_student_call()
            elif choice == "6":
                self.export_attendance_data()
            elif choice == "0":
                self.current_menu = "main"
            else:
                print("Invalid choice. Please try again.")
    
    def get_attendance_session_status(self):
        """Check if there's an active attendance session"""
        try:
            response = requests.get(f"{SERVER_URL}/get_attendance")
            if response.status_code == 200:
                data = response.json()
                return data.get('active_session', False)
        except requests.exceptions.RequestException:
            return False
        return False
    
    def start_attendance_session(self):
        """Start a new attendance session"""
        try:
            response = requests.post(
                f"{SERVER_URL}/start_attendance",
                json={"teacher": self.username}
            )
            
            if response.status_code == 200:
                print("\nAttendance session started successfully!")
            else:
                print(f"\nFailed to start session: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def end_attendance_session(self):
        """End the current attendance session"""
        try:
            response = requests.post(f"{SERVER_URL}/end_attendance")
            
            if response.status_code == 200:
                print("\nAttendance session ended successfully!")
            else:
                print(f"\nFailed to end session: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def view_current_attendance(self):
        """View current attendance status"""
        try:
            response = requests.get(f"{SERVER_URL}/get_attendance")
            
            if response.status_code == 200:
                data = response.json()
                students = data.get('students', {})
                
                if not students:
                    print("\nNo attendance data available")
                    return
                
                print("\n" + "="*90)
                print("CURRENT ATTENDANCE".center(90))
                print("="*90)
                print("\n{:<20} {:<10} {:<15} {:<15} {:<10} {:<15}".format(
                    "Student", "Status", "Time In", "Time Out", "Duration", "WiFi Status"
                ))
                print("-"*90)
                
                present = 0
                absent = 0
                left = 0
                
                for student_id, info in students.items():
                    status = info.get('status', 'absent').capitalize()
                    time_in = info.get('time_in', '')
                    time_out = info.get('time_out', '')
                    duration = info.get('duration', '')
                    wifi_status = info.get('status', 'unknown').capitalize()
                    
                    print("{:<20} {:<10} {:<15} {:<15} {:<10} {:<15}".format(
                        student_id, status, time_in, time_out, duration, wifi_status
                    ))
                    
                    # Count statuses
                    if status.lower() == 'present':
                        present += 1
                    elif status.lower() == 'absent':
                        absent += 1
                    elif status.lower() == 'left':
                        left += 1
                
                print("\n" + "-"*90)
                print(f"Present: {present} | Absent: {absent} | Left Early: {left} | Total: {present + absent + left}")
                print("="*90)
            else:
                print(f"\nFailed to get attendance: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def mark_student_attendance(self):
        """Manually mark a student's attendance"""
        student_id = input("\nEnter student ID: ").strip()
        if not student_id:
            print("Student ID cannot be empty")
            return
            
        print("\n1. Present")
        print("2. Absent")
        print("3. Left Early")
        choice = input("Select status (1-3): ").strip()
        
        status_map = {"1": "present", "2": "absent", "3": "left"}
        status = status_map.get(choice)
        
        if not status:
            print("Invalid choice")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/update_attendance_status",
                json={
                    "student_id": student_id,
                    "status": status
                }
            )
            
            if response.status_code == 200:
                print(f"\nSuccessfully marked {student_id} as {status}")
            else:
                print(f"\nFailed to mark attendance: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def random_student_call(self):
        """Randomly select students for participation"""
        try:
            response = requests.post(
                f"{SERVER_URL}/update_attendance",
                json={"action": "random_ring"}
            )
            
            if response.status_code == 200:
                data = response.json()
                students = data.get('students', [])
                
                print("\n" + "="*50)
                print("RANDOM STUDENT CALL".center(50))
                print("="*50)
                print("\nSelected students:")
                for student in students:
                    print(f"- {student}")
                print("\n" + "="*50)
            else:
                print(f"\nFailed to call students: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def export_attendance_data(self):
        """Export attendance data to file"""
        try:
            response = requests.get(f"{SERVER_URL}/get_attendance")
            
            if response.status_code == 200:
                data = response.json()
                students = data.get('students', {})
                
                if not students:
                    print("\nNo attendance data to export")
                    return
                
                filename = f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
                with open(filename, 'w') as f:
                    f.write("Student,Status,Time In,Time Out,Duration,WiFi Status\n")
                    for student_id, info in students.items():
                        f.write(f"{student_id},{info.get('status','')},{info.get('time_in','')},")
                        f.write(f"{info.get('time_out','')},{info.get('duration','')},{info.get('status','')}\n")
                
                print(f"\nAttendance data exported to {filename}")
            else:
                print(f"\nFailed to get attendance: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
        except Exception as e:
            print(f"\nError exporting data: {str(e)}")
    
    def student_menu(self):
        """Student management menu"""
        self.current_menu = "student"
        while self.current_menu == "student":
            print("\n" + "="*50)
            print("STUDENT MANAGEMENT".center(50))
            print("="*50)
            
            print("\n1. Register New Student")
            print("2. View Student List")
            print("3. View Student Details")
            print("4. Search Students")
            print("0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.register_student()
            elif choice == "2":
                self.view_student_list()
            elif choice == "3":
                self.view_student_details()
            elif choice == "4":
                self.search_students()
            elif choice == "0":
                self.current_menu = "main"
            else:
                print("Invalid choice. Please try again.")
    
    def register_student(self):
        """Register a new student"""
        print("\n" + "="*50)
        print("REGISTER NEW STUDENT".center(50))
        print("="*50)
        
        student_id = input("\nStudent ID: ").strip()
        name = input("Full Name: ").strip()
        student_class = input("Class/Grade: ").strip()
        password = getpass.getpass("Password: ").strip()
        confirm_pass = getpass.getpass("Confirm Password: ").strip()
        
        if password != confirm_pass:
            print("\nError: Passwords do not match")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/register_student",
                json={
                    "student_id": student_id,
                    "name": name,
                    "class": student_class,
                    "password": password
                }
            )
            
            if response.status_code == 201:
                print(f"\nSuccessfully registered student {name}")
            else:
                print(f"\nRegistration failed: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def view_student_list(self):
        """View list of all students"""
        try:
            response = requests.get(f"{SERVER_URL}/get_students")
            
            if response.status_code == 200:
                students = response.json()
                
                if not students:
                    print("\nNo students registered")
                    return
                
                print("\n" + "="*80)
                print("STUDENT DIRECTORY".center(80))
                print("="*80)
                print("\n{:<15} {:<25} {:<15} {:<15} {:<10}".format(
                    "Student ID", "Name", "Class", "Last Seen", "Status"
                ))
                print("-"*80)
                
                for student in students:
                    print("{:<15} {:<25} {:<15} {:<15} {:<10}".format(
                        student.get('id', ''),
                        student.get('name', ''),
                        student.get('class', ''),
                        student.get('last_seen', 'Never'),
                        "Active" if student.get('active', True) else "Inactive"
                    ))
                
                print("="*80)
            else:
                print(f"\nFailed to get students: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def view_student_details(self):
        """View detailed information about a student"""
        student_id = input("\nEnter student ID: ").strip()
        if not student_id:
            print("Student ID cannot be empty")
            return
            
        try:
            response = requests.get(f"{SERVER_URL}/student_details/{student_id}")
            
            if response.status_code == 200:
                details = response.json()
                
                print("\n" + "="*50)
                print("STUDENT PROFILE".center(50))
                print("="*50)
                print(f"\nName: {details.get('name', '')}")
                print(f"ID: {details.get('id', '')}")
                print(f"Class: {details.get('class', '')}")
                print(f"Email: {details.get('email', 'Not provided')}")
                print(f"Phone: {details.get('phone', 'Not provided')}")
                print(f"Address: {details.get('address', 'Not provided')}")
                
                # Attendance stats
                stats = details.get('attendance_stats', {})
                print("\n" + "-"*50)
                print("ATTENDANCE STATISTICS".center(50))
                print("-"*50)
                print(f"\nTotal Classes: {stats.get('total_classes', 0)}")
                print(f"Present: {stats.get('present', 0)}")
                print(f"Absent: {stats.get('absent', 0)}")
                print(f"Left Early: {stats.get('left', 0)}")
                print(f"Attendance Percentage: {stats.get('attendance_percent', 0):.1f}%")
                print("="*50)
            else:
                print(f"\nFailed to get student details: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def search_students(self):
        """Search for students by name or ID"""
        search_term = input("\nEnter search term (name or ID): ").strip().lower()
        if not search_term:
            print("Search term cannot be empty")
            return
            
        try:
            response = requests.get(f"{SERVER_URL}/get_students")
            
            if response.status_code == 200:
                all_students = response.json()
                matched = []
                
                for student in all_students:
                    if (search_term in student.get('id', '').lower() or 
                        search_term in student.get('name', '').lower()):
                        matched.append(student)
                
                if not matched:
                    print("\nNo matching students found")
                    return
                
                print("\n" + "="*80)
                print("SEARCH RESULTS".center(80))
                print("="*80)
                print("\n{:<15} {:<25} {:<15} {:<15} {:<10}".format(
                    "Student ID", "Name", "Class", "Last Seen", "Status"
                ))
                print("-"*80)
                
                for student in matched:
                    print("{:<15} {:<25} {:<15} {:<15} {:<10}".format(
                        student.get('id', ''),
                        student.get('name', ''),
                        student.get('class', ''),
                        student.get('last_seen', 'Never'),
                        "Active" if student.get('active', True) else "Inactive"
                    ))
                
                print("="*80)
            else:
                print(f"\nFailed to search students: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def timetable_menu(self):
        """Timetable management menu"""
        self.current_menu = "timetable"
        while self.current_menu == "timetable":
            print("\n" + "="*50)
            print("TIMETABLE MANAGEMENT".center(50))
            print("="*50)
            
            print("\n1. View Timetable")
            print("2. Edit Timetable")
            print("3. Print Timetable")
            print("0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.view_timetable()
            elif choice == "2":
                self.edit_timetable()
            elif choice == "3":
                self.print_timetable()
            elif choice == "0":
                self.current_menu = "main"
            else:
                print("Invalid choice. Please try again.")
    
    def view_timetable(self):
        """View the current timetable"""
        try:
            response = requests.get(f"{SERVER_URL}/timetable")
            
            if response.status_code == 200:
                timetable = response.json()
                
                if not timetable:
                    print("\nNo timetable available")
                    return
                
                print("\n" + "="*110)
                print("SCHOOL TIMETABLE".center(110))
                print("="*110)
                
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
                    header += day.ljust(15)
                print("\n" + header)
                print("-"*110)
                
                # Add timetable rows
                for period in periods:
                    row = period.ljust(20)
                    for day in days:
                        subject = timetable.get(day, {}).get(period, "")
                        row += subject.ljust(15)
                    print(row)
                
                print("="*110)
            else:
                print(f"\nFailed to get timetable: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def edit_timetable(self):
        """Edit the timetable"""
        print("\nTimetable editing would be implemented here")
        print("This would involve:")
        print("- Fetching current timetable")
        print("- Displaying editable grid")
        print("- Saving changes to server")
    
    def print_timetable(self):
        """Print the timetable (simulated)"""
        print("\nTimetable printing would be implemented here")
    
    def reports_menu(self):
        """Reports menu"""
        self.current_menu = "reports"
        while self.current_menu == "reports":
            print("\n" + "="*50)
            print("REPORTS".center(50))
            print("="*50)
            
            print("\n1. Daily Attendance Summary")
            print("2. Monthly Attendance Report")
            print("3. Student Attendance History")
            print("4. Class Attendance Statistics")
            print("5. Export Report")
            print("0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.daily_attendance_report()
            elif choice == "2":
                self.monthly_attendance_report()
            elif choice == "3":
                self.student_attendance_history()
            elif choice == "4":
                self.class_attendance_stats()
            elif choice == "5":
                self.export_report()
            elif choice == "0":
                self.current_menu = "main"
            else:
                print("Invalid choice. Please try again.")
    
    def daily_attendance_report(self):
        """Generate daily attendance report"""
        date = input("\nEnter date (YYYY-MM-DD) or leave blank for today: ").strip()
        if not date:
            date = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
            
            # Generate report
            response = requests.get(
                f"{SERVER_URL}/generate_report",
                params={
                    "report_type": "daily_attendance_summary",
                    "from_date": date,
                    "to_date": date
                }
            )
            
            if response.status_code == 200:
                report = response.json()
                self.display_report(report)
            else:
                print(f"\nFailed to generate report: {response.json().get('error', 'Unknown error')}")
        except ValueError:
            print("\nInvalid date format. Please use YYYY-MM-DD")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def monthly_attendance_report(self):
        """Generate monthly attendance report"""
        month = input("\nEnter month and year (MM/YYYY) or leave blank for current month: ").strip()
        if not month:
            month = datetime.now(pytz.timezone(TIMEZONE)).strftime("%m/%Y")
        
        try:
            # Validate month format
            month_date = datetime.strptime(month, "%m/%Y")
            from_date = month_date.replace(day=1).strftime("%Y-%m-%d")
            to_date = (month_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            to_date = to_date.strftime("%Y-%m-%d")
            
            # Generate report
            response = requests.get(
                f"{SERVER_URL}/generate_report",
                params={
                    "report_type": "monthly_attendance_report",
                    "from_date": from_date,
                    "to_date": to_date
                }
            )
            
            if response.status_code == 200:
                report = response.json()
                self.display_report(report)
            else:
                print(f"\nFailed to generate report: {response.json().get('error', 'Unknown error')}")
        except ValueError:
            print("\nInvalid month format. Please use MM/YYYY")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def student_attendance_history(self):
        """Generate student attendance history report"""
        student_id = input("\nEnter student ID: ").strip()
        if not student_id:
            print("Student ID cannot be empty")
            return
            
        from_date = input("Enter start date (YYYY-MM-DD) or leave blank: ").strip()
        to_date = input("Enter end date (YYYY-MM-DD) or leave blank: ").strip()
        
        try:
            # Generate report
            response = requests.get(
                f"{SERVER_URL}/generate_report",
                params={
                    "report_type": "student_attendance_history",
                    "from_date": from_date,
                    "to_date": to_date,
                    "student_id": student_id
                }
            )
            
            if response.status_code == 200:
                report = response.json()
                self.display_report(report)
            else:
                print(f"\nFailed to generate report: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def class_attendance_stats(self):
        """Generate class attendance statistics"""
        class_name = input("\nEnter class name or leave blank for all: ").strip()
        
        from_date = input("Enter start date (YYYY-MM-DD) or leave blank: ").strip()
        to_date = input("Enter end date (YYYY-MM-DD) or leave blank: ").strip()
        
        try:
            # Generate report
            response = requests.get(
                f"{SERVER_URL}/generate_report",
                params={
                    "report_type": "class_attendance_statistics",
                    "from_date": from_date,
                    "to_date": to_date,
                    "class": class_name
                }
            )
            
            if response.status_code == 200:
                report = response.json()
                self.display_report(report)
            else:
                print(f"\nFailed to generate report: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def display_report(self, report):
        """Display a report in console"""
        print("\n" + "="*80)
        print(f"{report.get('report_type', 'REPORT').upper()}".center(80))
        print("="*80)
        
        print(f"\nDate Range: {report.get('date_range', 'All dates')}")
        print(f"Class Filter: {report.get('class_filter', 'All classes')}")
        print(f"Generated At: {report.get('generated_at', '')}")
        
        if 'summary' in report:
            print("\nDaily Summary:")
            for date, stats in report['summary'].items():
                print(f"\n{date}:")
                print(f"Present: {stats.get('present', 0)}")
                print(f"Absent: {stats.get('absent', 0)}")
                print(f"Left Early: {stats.get('left', 0)}")
        
        elif 'monthly' in report:
            print("\nMonthly Summary:")
            for month, stats in report['monthly'].items():
                print(f"\n{month}:")
                print(f"Present: {stats.get('present', 0)}")
                print(f"Absent: {stats.get('absent', 0)}")
                print(f"Left Early: {stats.get('left', 0)}")
        
        elif 'student_history' in report:
            print("\nStudent Attendance History:")
            for student in report['student_history']:
                print(f"\nStudent: {student.get('name', '')} ({student.get('student_id', '')})")
                print(f"Class: {student.get('class', '')}")
                print("\nDate       Status    Time In   Time Out  Duration")
                print("-"*40)
                for record in student.get('records', []):
                    print(f"{record.get('date','')} {record.get('status','').ljust(8)} {record.get('time_in','').ljust(8)} {record.get('time_out','').ljust(8)} {record.get('duration','')}")
        
        elif 'class_stats' in report:
            print("\nClass Attendance Statistics:")
            for class_name, stats in report['class_stats'].items():
                print(f"\nClass: {class_name}")
                print(f"Present: {stats.get('present', 0)} ({stats.get('present_percent', 0)}%)")
                print(f"Absent: {stats.get('absent', 0)} ({stats.get('absent_percent', 0)}%)")
                print(f"Left Early: {stats.get('left', 0)} ({stats.get('left_percent', 0)}%)")
                print(f"Total: {stats.get('total', 0)}")
        
        print("\n" + "="*80)
    
    def export_report(self):
        """Export report to file"""
        report_type = input("\nEnter report type to export: ").strip()
        filename = input("Enter filename to save: ").strip()
        
        if not filename:
            print("Filename cannot be empty")
            return
            
        try:
            response = requests.get(
                f"{SERVER_URL}/generate_report",
                params={
                    "report_type": report_type,
                    "format": "csv"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                csv_data = data.get('csv_data', [])
                
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(csv_data)
                
                print(f"\nReport exported to {filename}")
            else:
                print(f"\nFailed to generate report: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
        except Exception as e:
            print(f"\nError exporting report: {str(e)}")
    
    def settings_menu(self):
        """System settings menu"""
        self.current_menu = "settings"
        while self.current_menu == "settings":
            print("\n" + "="*50)
            print("SYSTEM SETTINGS".center(50))
            print("="*50)
            
            print("\n1. Change Password")
            print("2. Configure WiFi Settings")
            print("3. Set Attendance Threshold")
            print("0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ").strip()
            
            if choice == "1":
                self.change_password()
            elif choice == "2":
                self.configure_wifi()
            elif choice == "3":
                self.set_attendance_threshold()
            elif choice == "0":
                self.current_menu = "main"
            else:
                print("Invalid choice. Please try again.")
    
    def change_password(self):
        """Change teacher's password"""
        current_pass = getpass.getpass("\nCurrent Password: ").strip()
        new_pass = getpass.getpass("New Password: ").strip()
        confirm_pass = getpass.getpass("Confirm New Password: ").strip()
        
        if not all([current_pass, new_pass, confirm_pass]):
            print("\nAll fields are required")
            return
            
        if new_pass != confirm_pass:
            print("\nNew passwords do not match")
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/change_password",
                json={
                    "username": self.username,
                    "current_password": current_pass,
                    "new_password": new_pass
                }
            )
            
            if response.status_code == 200:
                print("\nPassword changed successfully!")
            else:
                print(f"\nFailed to change password: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def configure_wifi(self):
        """Configure WiFi settings"""
        print("\n" + "="*50)
        print("WI-FI CONFIGURATION".center(50))
        print("="*50)
        
        try:
            response = requests.get(f"{SERVER_URL}/get_settings")
            
            if response.status_code == 200:
                settings = response.json()
                print(f"\nCurrent WiFi Range: {settings.get('wifi_range', 50)} meters")
                
                new_range = input("\nEnter new detection range in meters (leave blank to keep current): ").strip()
                if new_range and new_range.isdigit():
                    update_response = requests.post(
                        f"{SERVER_URL}/update_settings",
                        json={"wifi_range": int(new_range)}
                    )
                    
                    if update_response.status_code == 200:
                        print(f"\nWiFi range updated to {new_range} meters")
                    else:
                        print(f"\nFailed to update settings: {update_response.json().get('error', 'Unknown error')}")
                else:
                    print("\nWiFi range remains unchanged")
            else:
                print(f"\nFailed to get settings: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")
    
    def set_attendance_threshold(self):
        """Set attendance threshold"""
        try:
            response = requests.get(f"{SERVER_URL}/get_settings")
            
            if response.status_code == 200:
                settings = response.json()
                print(f"\nCurrent Attendance Threshold: {settings.get('attendance_threshold', 15)} minutes")
                
                threshold = input("\nEnter new threshold in minutes: ").strip()
                if threshold and threshold.isdigit():
                    update_response = requests.post(
                        f"{SERVER_URL}/update_settings",
                        json={"attendance_threshold": int(threshold)}
                    )
                    
                    if update_response.status_code == 200:
                        print(f"\nAttendance threshold set to {threshold} minutes")
                    else:
                        print(f"\nFailed to update settings: {update_response.json().get('error', 'Unknown error')}")
                else:
                    print("\nThreshold remains unchanged")
            else:
                print(f"\nFailed to get settings: {response.json().get('error', 'Unknown error')}")
        except requests.exceptions.RequestException:
            print("\nError: Could not connect to server")

if __name__ == "__main__":
    client = TeacherClient()
    client.login()
    if client.username:
        client.main_menu()
