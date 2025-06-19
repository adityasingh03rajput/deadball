# -*- coding: utf-8 -*-
#
# letsbunk.py
# A Comprehensive, All-in-One Attendance Management System Client
#
# Version: 1.1.0 (Corrected for PyQt6 compatibility)
# This version resolves the AttributeError related to obsolete High DPI scaling
# attributes in PyQt6, ensuring the application runs correctly.
#
import sys
import os
import time
import json
import platform
import subprocess
import threading
import requests
import re
from datetime import datetime

# --- Core Application Framework ---
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QThread, QUrl, Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel

# =============================================================================
# CONFIGURATION
# =============================================================================
SERVER_URL = "https://deadball-ko18.onrender.com"
# Interval in seconds for fetching status updates from the server.
UPDATE_INTERVAL = 3
# Interval in seconds for the student client to check its WiFi status.
WIFI_CHECK_INTERVAL = 5

# =============================================================================
# FRONTEND ASSETS (HTML, CSS, JS)
# =============================================================================

# This JS file is a prerequisite for QWebChannel to function.
QWEBCHANNEL_JS = """
var QWebChannel = function(transport, initCallback)
{
    if (typeof transport === "undefined") {
        console.error("The QWebChannel transport object is undefined!");
        return;
    }
    var channel = this;
    this.transport = transport;
    this.send = function(data)
    {
        if (typeof(data) !== "string") {
            data = JSON.stringify(data);
        }
        channel.transport.send(data);
    };
    this.receive = function(data)
    {
        if (typeof data !== 'object') {
            data = JSON.parse(data);
        }
        switch (data.type) {
        case 1: // signal
            channel.handleSignal(data);
            break;
        case 2: // response
            channel.handleResponse(data);
            break;
        case 3: // property update
            channel.handlePropertyUpdate(data);
            break;
        default:
            console.error("invalid message received:", data);
            break;
        }
    };
    this.transport.onmessage = this.receive;
    this.execCallbacks = {};
    this.execId = 0;
    this.objects = {};
    this.handleSignal = function(message) {
        var object = channel.objects[message.object];
        if (object) {
            object.signalEmitted(message.signal, message.args);
        } else {
            console.warn("received signal for unknown object", message.object);
        }
    };
    this.handleResponse = function(message) {
        var callback = channel.execCallbacks[message.id];
        if (callback) {
            callback(message.data);
            delete channel.execCallbacks[message.id];
        } else {
            console.warn("received response for unknown exec id", message.id);
        }
    };
    this.handlePropertyUpdate = function(message) {
        for (var i in message.data) {
            var data = message.data[i];
            var object = channel.objects[data.object];
            if (object) {
                object.propertyUpdate(data.signals, data.properties);
            } else {
                console.warn("received property update for unknown object", data.object);
            }
        }
    }
    this.debug = function(message) {
        this.send({type: 0, data: message});
    };
    channel.exec = function(data, callback) {
        if (!callback) {
            data.id = -1;
            channel.send(data);
            return;
        }
        var id = ++channel.execId;
        data.id = id;
        channel.execCallbacks[id] = callback;
        channel.send(data);
    };
    var Signal = function(name, object) {
        this.name = name;
        this.object = object;
        this.callbacks = [];
        this.connect = function(callback) {
            if (typeof(callback) !== "function") {
                console.error("connect failed, callback is not a function. name:" + name);
                return;
            }
            this.callbacks.push(callback);
        };
        this.disconnect = function(callback) {
            for (var i = 0; i < this.callbacks.length; i++) {
                if (this.callbacks[i] === callback) {
                    this.callbacks.splice(i, 1);
                    return;
                }
            }
            console.error("disconnect failed, callback not found. name:" + name);
        };
        this.emit = function() {
            var args = Array.prototype.slice.call(arguments);
            for (var i = 0; i < this.callbacks.length; i++) {
                this.callbacks[i].apply(this, args);
            }
        };
    };
    var PublishedObject = function(name, data, channel) {
        this.name = name;
        this.methods = {};
        this.properties = {};
        this.signals = {};
        for (var i in data.methods) {
            var method = data.methods[i];
            this.methods[method] = (function(method) {
                return function() {
                    var args = Array.prototype.slice.call(arguments);
                    var callback;
                    if (args.length > 0 && typeof(args[args.length - 1]) === "function") {
                        callback = args.pop();
                    }
                    channel.exec({
                        type: 0,
                        object: name,
                        method: method,
                        args: args
                    }, callback);
                }
            }(method));
        }
        for (var i in data.signals) {
            var signal = data.signals[i];
            this.signals[signal] = new Signal(signal, this);
        }
        this.signalEmitted = function(signalName, args) {
            var signal = this.signals[signalName];
            if (signal) {
                signal.emit.apply(signal, args);
            }
        };
    };
    this.transport.onmessage = this.receive;
    this.exec({type: 6}, function(data) {
        for (var objectName in data) {
            var object = new PublishedObject(objectName, data[objectName], channel);
            channel.objects[objectName] = object;
        }
        if (initCallback) {
            initCallback(channel);
        }
    });
};
"""

# The entire HTML/CSS/JS file for the application's user interface.
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Let's Bunk</title>
    <style>
        :root {
            --bg-dark: #121212;
            --bg-panel: #1E1E1E;
            --bg-element: #2D2D2D;
            --primary: #5D9CEC;
            --primary-light: #7EB0F1;
            --primary-dark: #4A8BD9;
            --text-primary: #E0E0E0;
            --text-secondary: #A0A0A0;
            --accent: #48C774;
            --border: #333333;
            --button-hover: #48C774;
            --error: #ff6b6b;
        }
        
        body {
            font-family: 'Poppins', sans-serif;
            background-color: var(--bg-dark);
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: var(--text-primary);
        }
        
        .container {
            text-align: center;
            width: 80%;
            max-width: 800px;
            margin-top: -60px;
        }
        
        h1 {
            color: var(--primary);
            margin-bottom: 70px;
            font-size: 3.2rem;
            letter-spacing: 1.5px;
            font-weight: 700;
        }
        
        .options-container {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            gap: 30px;
        }
        
        .option-box {
            background-color: var(--bg-panel);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            padding: 30px;
            width: 250px;
            transition: all 0.3s ease;
            cursor: pointer;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 180px;
            border: 1px solid var(--border);
        }
        
        .option-box:hover {
            transform: translateY(-8px);
            box-shadow: 0 12px 20px rgba(0, 0, 0, 0.3);
            border-color: var(--primary);
        }
        
        .option-box h2 {
            margin: 0;
            font-size: 2.2rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: 0.5px;
        }
        
        .new-page {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: var(--bg-dark);
            z-index: 900;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            color: var(--text-primary);
            overflow-y: auto;
            padding: 20px;
            box-sizing: border-box;
        }
                
        .portal-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
        }
        
        .portal-title {
            color: var(--primary);
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5rem;
        }
        
        .auth-tabs-container {
            width: 480px;
            margin-bottom: 30px;
        }
        
        .auth-tabs {
            display: flex;
            border-bottom: 1px solid var(--border);
            gap: 10px;
        }
        
        .auth-tab {
            flex: 1;
            text-align: center;
            padding: 15px;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.3s ease;
            font-size: 1.1rem;
            border-radius: 8px 8px 0 0;
            background-color: var(--bg-element);
            margin-bottom: -1px;
        }
        
        .auth-tab.active {
            color: var(--primary);
            border-bottom: 3px solid var(--primary);
            font-weight: 600;
            background-color: var(--bg-panel);
        }
        
        .auth-container {
            background-color: var(--bg-panel);
            border-radius: 15px;
            padding: 40px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            margin-top: 10px;
            width: 480px;
            box-sizing: border-box;
        }
        
        .auth-form {
            display: none;
            flex-direction: column;
            justify-content: center;
        }
        
        .auth-form.active { display: flex; }
        
        .form-group {
            margin-bottom: 20px;
            width: 100%;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px 15px;
            background-color: var(--bg-element);
            border: 1px solid var(--border);
            border-radius: 5px;
            color: var(--text-primary);
            font-size: 1rem;
            transition: all 0.3s ease;
            box-sizing: border-box;
        }
        
        .auth-button {
            width: 100%;
            padding: 12px;
            background-color: var(--primary);
            color: #ffffff;
            border: none;
            border-radius: 5px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 10px;
        }
        
        .back-button, .logout-btn {
            padding: 12px 30px;
            background-color: var(--bg-panel);
            color: #ffffff;
            border: 1px solid var(--border);
            border-radius: 5px;
            font-size: 1.2rem;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .back-button { margin-top: 40px; }
        .logout-btn { position: absolute; top: 30px; right: 30px; font-size: 1rem; padding: 10px 20px;}

        .back-button:hover, .logout-btn:hover { background-color: var(--primary); }
        
        .message-box {
            text-align: center;
            margin-top: 15px;
            font-size: 0.9rem;
            min-height: 20px;
        }

        .success-message { color: var(--accent); }
        .error-message { color: var(--error); }

        .dashboard-header { text-align: center; margin-bottom: 50px; }
        .dashboard-header h1 { color: var(--primary); font-size: 2.8rem; margin-bottom: 10px; }
        .dashboard-header p { color: var(--text-secondary); font-size: 1.2rem; }
        
        .dashboard-options {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            width: 80%;
            max-width: 900px;
        }
        
        .dashboard-option {
            background-color: var(--bg-panel);
            border-radius: 50%;
            width: 180px;
            height: 180px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid var(--border);
        }
        
        .dashboard-option:hover {
            transform: scale(1.05);
            border-color: var(--primary);
        }
        
        .dashboard-option i { font-size: 3rem; margin-bottom: 15px; color: var(--primary); }
        .dashboard-option span { font-size: 1.2rem; font-weight: 500; text-align: center; }
        
        /* Common Page Styles */
        .page-container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            color: var(--text-primary);
        }

        .page-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }

        .page-title { color: var(--primary); font-size: 2.5rem; margin: 0; }
        
        .page-action-btn {
            padding: 10px 20px;
            background-color: var(--bg-panel);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 5px;
            cursor: pointer;
            font-size: 1rem;
        }

        .page-action-btn:hover { background-color: var(--primary); }
        
        /* Attendance Page */
        .session-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            margin-bottom: 30px;
            background-color: var(--bg-panel);
            padding: 15px;
            border-radius: 10px;
        }
        
        .session-btn, .random-ring-btn, .refresh-btn {
            padding: 12px 25px;
            font-size: 1.1rem;
            border-radius: 8px;
            cursor: pointer;
            border: none;
            color: white;
        }

        .start-session { background-color: var(--accent); }
        .end-session { background-color: var(--error); }
        .random-ring-btn { background-color: var(--primary-dark); }
        .refresh-btn { background-color: #6c757d; }
        .session-status { font-size: 1.1rem; color: var(--text-secondary); }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background-color: var(--bg-panel);
            border-radius: 10px;
            overflow: hidden;
        }

        .data-table th {
            background-color: var(--bg-element);
            color: var(--primary);
            padding: 15px;
            text-align: left;
        }
        .data-table td { padding: 12px 15px; border-bottom: 1px solid var(--border); }
        .data-table tr:last-child td { border-bottom: none; }
        .data-table tr.highlight-ring {
            background-color: rgba(255, 165, 0, 0.2);
            animation: glow 1.5s infinite alternate;
        }

        @keyframes glow {
            from { box-shadow: 0 0 5px rgba(255, 165, 0, 0.2); }
            to { box-shadow: 0 0 20px rgba(255, 165, 0, 0.6); }
        }

        .status-Attended { color: var(--accent); font-weight: bold; }
        .status-Absent { color: var(--error); font-weight: bold; }
        .status-Pending, .status-running { color: #f0ad4e; font-weight: bold; }
        .status-On.Bunk, .status-paused { color: #0275d8; font-weight: bold; }
        .status-completed { color: var(--accent); font-weight: bold; }
        .status-stopped { color: var(--error); font-weight: bold; }
        
        .timer { font-family: 'Courier New', monospace; font-weight: bold; }

        /* Student Dashboard */
        #student-dashboard { text-align: center; }
        #attendance-timer-display { font-size: 4rem; font-family: 'Courier New', monospace; margin: 20px 0; color: var(--accent); }
        #wifi-status-display { font-size: 1.2rem; margin-bottom: 20px; }
        .wifi-authorized { color: var(--accent); }
        .wifi-unauthorized { color: var(--error); }
        #mark-attendance-btn { padding: 15px 30px; font-size: 1.2rem; border-radius: 10px; }
        #mark-attendance-btn:disabled { background-color: #6c757d; cursor: not-allowed; }
        
        /* Settings Page */
        #bssid-list > div {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: var(--bg-element);
            padding: 8px 12px;
            border-radius: 5px;
            margin-bottom: 8px;
        }
        .remove-bssid-btn { color:var(--error); background:none; border:none; cursor:pointer; font-size: 1.2rem; }

    </style>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.1.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <h1>Attendance System</h1>
        <div class="options-container">
            <div class="option-box" id="teacher-box" onclick="selectOption('teacher')"><h2>Teacher</h2></div>
            <div class="option-box" id="student-box" onclick="selectOption('student')"><h2>Student</h2></div>
        </div>
    </div>
    
    <!-- Login/Signup Pages -->
    <div class="new-page" id="teacher-page">
        <div class="portal-container">
            <h2 class="portal-title">Teacher Portal</h2>
            <div class="auth-tabs-container">
                <div class="auth-tabs">
                    <div class="auth-tab active" data-form="teacher-login-form">Login</div>
                    <div class="auth-tab" data-form="teacher-signup-form">Sign Up</div>
                </div>
            </div>
            <div class="auth-container">
                <form id="teacher-login-form" class="auth-form active">
                    <div class="form-group"><label for="teacher-login-id">Teacher ID</label><input type="text" id="teacher-login-id" required></div>
                    <div class="form-group"><label for="teacher-login-password">Password</label><input type="password" id="teacher-login-password" required></div>
                    <button type="submit" class="auth-button">Login</button>
                    <div class="message-box" id="teacher-login-message"></div>
                </form>
                <form id="teacher-signup-form" class="auth-form">
                    <div class="form-group"><label for="teacher-signup-id">Teacher ID</label><input type="text" id="teacher-signup-id" required></div>
                    <div class="form-group"><label for="teacher-signup-name">Full Name</label><input type="text" id="teacher-signup-name" required></div>
                    <div class="form-group"><label for="teacher-signup-password">Password</label><input type="password" id="teacher-signup-password" required></div>
                    <button type="submit" class="auth-button">Create Account</button>
                    <div class="message-box" id="teacher-signup-message"></div>
                </form>
            </div>
        </div>
        <button class="back-button" onclick="goBack()">Back to Home</button>
    </div>
    
    <div class="new-page" id="student-page">
        <div class="portal-container">
            <h2 class="portal-title">Student Portal</h2>
            <div class="auth-container" style="margin-top:20px;">
                <form id="student-login-form" class="auth-form active">
                     <div class="form-group"><label for="student-login-id">Student ID</label><input type="text" id="student-login-id" required></div>
                    <div class="form-group"><label for="student-login-password">Password</label><input type="password" id="student-login-password" required></div>
                    <button type="submit" class="auth-button">Login</button>
                    <div class="message-box" id="student-login-message"></div>
                </form>
            </div>
        </div>
        <button class="back-button" onclick="goBack()">Back to Home</button>
    </div>
    
    <!-- Teacher Dashboard -->
    <div class="new-page" id="teacher-dashboard">
        <button class="logout-btn" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
        <div class="dashboard-header">
            <h1>Teacher Dashboard</h1>
            <p>Welcome back, <span id="teacher-name-display"></span>!</p>
        </div>
        <div class="dashboard-options">
            <div class="dashboard-option" onclick="openPage('attendance-dashboard-page')"><i class="fas fa-clipboard-check"></i><span>Attendance</span></div>
            <div class="dashboard-option" onclick="openPage('student-mgmt-page')"><i class="fas fa-users"></i><span>Students</span></div>
            <div class="dashboard-option" onclick="openPage('settings-page')"><i class="fas fa-cog"></i><span>Settings</span></div>
        </div>
    </div>

    <!-- Student Dashboard -->
    <div class="new-page" id="student-dashboard">
        <button class="logout-btn" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
        <div class="dashboard-header">
            <h1>Student Dashboard</h1>
            <p>Welcome, <span id="student-name-display"></span>!</p>
        </div>
        <div id="student-session-status">Loading session status...</div>
        <div id="attendance-timer-display">--:--</div>
        <div id="wifi-status-display">Checking WiFi...</div>
        <button id="mark-attendance-btn" class="auth-button" disabled>Mark My Attendance</button>
        <div class="message-box" id="student-attendance-message"></div>
    </div>
    
    <!-- Teacher Pages -->
    <div class="new-page" id="attendance-dashboard-page">
        <div class="page-container">
            <div class="page-header">
                <h1 class="page-title">Attendance Management</h1>
                <button class="page-action-btn" onclick="openPage('teacher-dashboard')"><i class="fas fa-arrow-left"></i> Back</button>
            </div>
            <div class="session-controls">
                <button class="session-btn start-session" onclick="startSession()">Start Session</button>
                <button class="session-btn end-session" onclick="endSession()">End Session</button>
                <span id="session-status-display" class="session-status">No active session.</span>
                <button class="random-ring-btn" onclick="randomRing()"><i class="fas fa-bell"></i> Random Ring</button>
                <button class="refresh-btn" onclick="manualRefresh()"><i class="fas fa-sync"></i> Refresh</button>
            </div>
            <table class="data-table">
                <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Timer</th><th>Join Time</th><th>Leave Time</th></tr></thead>
                <tbody id="students-list-body"></tbody>
            </table>
        </div>
    </div>

    <div class="new-page" id="student-mgmt-page">
        <div class="page-container">
             <div class="page-header">
                <h1 class="page-title">Student Management</h1>
                <button class="page-action-btn" onclick="openPage('teacher-dashboard')"><i class="fas fa-arrow-left"></i> Back</button>
            </div>
            <div class="auth-container" style="width: auto; max-width: 600px; margin: 20px auto;">
                <h3 style="text-align:center;">Register New Student</h3>
                <form id="student-register-form">
                     <div class="form-group"><label for="reg-student-id">Student ID</label><input type="text" id="reg-student-id" required></div>
                     <div class="form-group"><label for="reg-student-name">Full Name</label><input type="text" id="reg-student-name" required></div>
                     <button type="submit" class="auth-button">Register Student</button>
                     <div class="message-box" id="student-register-message"></div>
                </form>
            </div>
        </div>
    </div>

    <div class="new-page" id="settings-page">
        <div class="page-container">
            <div class="page-header">
                <h1 class="page-title">Settings</h1>
                <button class="page-action-btn" onclick="openPage('teacher-dashboard')"><i class="fas fa-arrow-left"></i> Back</button>
            </div>
            <div class="auth-container" style="width: auto; max-width: 600px; margin: 20px auto;">
                 <h3 style="text-align:center;">Authorized WiFi BSSIDs</h3>
                 <div id="bssid-list" style="margin-bottom: 20px;"></div>
                 <form id="add-bssid-form" style="display:flex; gap: 10px;">
                    <input type="text" id="new-bssid" placeholder="Enter new BSSID (e.g., aa:bb:cc:dd:ee:ff)" style="flex-grow: 1;" class="form-group input" required>
                    <button type="submit" class="auth-button" style="width:auto; margin-top:0;">Add</button>
                 </form>
                 <div class="message-box" id="bssid-message"></div>
            </div>
        </div>
    </div>

    <script>
        var bridge; 

        document.addEventListener("DOMContentLoaded", function() {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                bridge = channel.objects.bridge;

                bridge.loginResult.connect(handleLoginResult);
                bridge.signupResult.connect(handleSignupResult);
                bridge.statusUpdate.connect(handleStatusUpdate);
                bridge.randomRingAlert.connect(handleRandomRingAlert);
                bridge.bssidUpdate.connect(updateBssidList);
                bridge.studentRegisterResult.connect(handleStudentRegisterResult);
                bridge.studentWifiStatus.connect(handleStudentWifiStatus);
                bridge.studentTimerUpdate.connect(handleStudentTimerUpdate);
            });
        });

        // --- Global Navigation ---
        function goBack() {
            document.querySelectorAll('.new-page').forEach(page => page.style.display = 'none');
            document.querySelector('.container').style.display = 'block';
            if (bridge) bridge.logout();
        }
        function selectOption(option) {
            document.querySelector('.container').style.display = 'none';
            document.getElementById(`${option}-page`).style.display = 'flex';
        }
        function openPage(pageId) {
            document.querySelectorAll('.new-page').forEach(page => page.style.display = 'none');
            document.getElementById(pageId).style.display = 'flex';
            if (pageId === 'attendance-dashboard-page' || pageId === 'settings-page') {
                manualRefresh();
            }
        }
        function logout() {
            goBack();
        }

        // --- Auth Tabs ---
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const parent = tab.closest('.auth-tabs-container');
                parent.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                const formId = tab.dataset.form;
                const container = parent.nextElementSibling;
                container.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
                container.querySelector(`#${formId}`).classList.add('active');
            });
        });

        // --- Form Submissions ---
        document.getElementById('teacher-login-form').addEventListener('submit', e => { e.preventDefault(); bridge.login('teacher', document.getElementById('teacher-login-id').value, document.getElementById('teacher-login-password').value); });
        document.getElementById('teacher-signup-form').addEventListener('submit', e => { e.preventDefault(); bridge.signup('teacher', document.getElementById('teacher-signup-id').value, document.getElementById('teacher-signup-name').value, document.getElementById('teacher-signup-password').value); });
        document.getElementById('student-login-form').addEventListener('submit', e => { e.preventDefault(); bridge.login('student', document.getElementById('student-login-id').value, document.getElementById('student-login-password').value); });
        document.getElementById('student-register-form').addEventListener('submit', e => { e.preventDefault(); bridge.registerStudent(document.getElementById('reg-student-id').value, document.getElementById('reg-student-name').value); });
        document.getElementById('add-bssid-form').addEventListener('submit', e => { e.preventDefault(); bridge.addBssid(document.getElementById('new-bssid').value); document.getElementById('new-bssid').value = ''; });
        document.getElementById('mark-attendance-btn').addEventListener('click', () => bridge.startStudentAttendance());

        // --- Bridge Handlers (JS functions called by Python) ---
        function handleLoginResult(userType, success, message, name) {
            const msgBox = document.getElementById(`${userType}-login-message`);
            msgBox.textContent = message;
            msgBox.className = success ? "message-box success-message" : "message-box error-message";
            if (success) {
                setTimeout(() => {
                    openPage(`${userType}-dashboard`);
                    document.getElementById(`${userType}-name-display`).textContent = name;
                }, 1000);
            }
        }

        function handleSignupResult(userType, success, message) {
            const msgBox = document.getElementById(`${userType}-signup-message`);
            msgBox.textContent = message;
            msgBox.className = success ? "message-box success-message" : "message-box error-message";
        }
        
        function handleStudentRegisterResult(success, message) {
            const msgBox = document.getElementById('student-register-message');
            msgBox.textContent = message;
            msgBox.className = success ? "message-box success-message" : "message-box error-message";
            if (success) document.getElementById('student-register-form').reset();
        }
        
        function handleStatusUpdate(status) {
            const session = status.current_session;
            const students = status.students || {};
            const tbody = document.getElementById('students-list-body');
            
            // Update session status display
            const sessionDisplay = document.getElementById('session-status-display');
            if (session && session.name) {
                sessionDisplay.textContent = `Session "${session.name}" started at ${session.start_time}`;
                sessionDisplay.style.color = 'var(--accent)';
            } else {
                sessionDisplay.textContent = 'No active session.';
                sessionDisplay.style.color = 'var(--text-secondary)';
            }
            
            // Update students table
            tbody.innerHTML = '';
            for (const sid in students) {
                const student = students[sid];
                const timer = student.timer || {};
                const remaining = timer.remaining || 0;
                const minutes = Math.floor(remaining / 60);
                const seconds = Math.floor(remaining % 60);
                const timerStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
                
                const row = document.createElement('tr');
                row.id = `student-row-${sid}`;
                let statusClass = (student.attendance_status || 'Absent').replace(' ', '.');
                if (timer.status) statusClass = timer.status; // Prefer timer status for class name
                
                row.innerHTML = `
                    <td>${sid}</td>
                    <td>${student.name}</td>
                    <td class="status-${statusClass}">${student.attendance_status || 'Absent'}</td>
                    <td class="timer">${timerStr}</td>
                    <td>${student.join_time || 'N/A'}</td>
                    <td>${student.leave_time || 'N/A'}</td>
                `;
                tbody.appendChild(row);
            }
        }

        function handleRandomRingAlert(studentIds) {
            document.querySelectorAll('.highlight-ring').forEach(el => el.classList.remove('highlight-ring'));
            studentIds.forEach(sid => {
                const row = document.getElementById(`student-row-${sid}`);
                if (row) row.classList.add('highlight-ring');
            });
        }
        
        function updateBssidList(bssids, message, success) {
            const listDiv = document.getElementById('bssid-list');
            listDiv.innerHTML = bssids.map(bssid => `
                <div>
                    <span>${bssid}</span>
                    <button class="remove-bssid-btn" onclick="removeBssid('${bssid}')">×</button>
                </div>
            `).join('');
            const msgBox = document.getElementById('bssid-message');
            msgBox.textContent = message || '';
            msgBox.className = success ? "message-box success-message" : "message-box error-message";
        }
        
        function handleStudentWifiStatus(isAuthorized, bssid) {
            const display = document.getElementById('wifi-status-display');
            if (bssid) {
                display.textContent = `Connected to ${bssid}. Status: ${isAuthorized ? 'Authorized' : 'Unauthorized'}`;
                display.className = isAuthorized ? 'wifi-authorized' : 'wifi-unauthorized';
            } else {
                display.textContent = 'Not connected to WiFi.';
                display.className = 'wifi-unauthorized';
            }
        }
        
        function handleStudentTimerUpdate(data) {
            const remainingSeconds = data.remaining || 0;
            const status = data.status || "stopped";
            const sessionActive = data.sessionActive;

            const display = document.getElementById('attendance-timer-display');
            const button = document.getElementById('mark-attendance-btn');
            const message = document.getElementById('student-attendance-message');
            
            const minutes = Math.floor(remainingSeconds / 60);
            const seconds = Math.floor(remainingSeconds % 60);
            display.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

            document.getElementById('student-session-status').textContent = sessionActive ? "Attendance session is active." : "No active session.";
            document.getElementById('student-session-status').style.color = sessionActive ? "var(--accent)" : "var(--text-secondary)";

            button.disabled = !sessionActive || status === 'running' || status === 'completed';
            
            if (status === 'running') message.textContent = 'Attendance timer is running...';
            else if (status === 'completed') message.textContent = 'Attendance marked successfully!';
            else if (status === 'paused') message.textContent = 'Timer paused. Please reconnect to authorized WiFi.';
            else message.textContent = '';
        }

        // --- Functions called by JS UI events ---
        function startSession() { bridge.startSession(); }
        function endSession() { bridge.endSession(); }
        function randomRing() { bridge.randomRing(); }
        function manualRefresh() { bridge.manualRefresh(); }
        function removeBssid(bssid) { bridge.removeBssid(bssid); }

    </script>
</body>
</html>
"""

# =============================================================================
# WORKER THREADS (for non-GUI tasks)
# =============================================================================

class Worker(QObject):
    """Base class for workers that run in a separate thread."""
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._is_running = True

    def stop(self):
        self._is_running = False

class StatusUpdater(Worker):
    """Periodically fetches status from the server for all user types."""
    statusUpdate = pyqtSignal(dict)
    studentTimerUpdate = pyqtSignal(dict)

    def run(self):
        while self._is_running:
            try:
                if self.bridge.user_id:
                    response = requests.get(f"{SERVER_URL}/get_status", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        self.statusUpdate.emit(data)

                        # If user is a student, emit specific timer updates
                        if self.bridge.user_type == 'student':
                            student_data = data.get('students', {}).get(self.bridge.user_id, {})
                            timer_data = student_data.get('timer', {})
                            timer_data['sessionActive'] = data.get('current_session') is not None
                            self.studentTimerUpdate.emit(timer_data)

            except requests.RequestException as e:
                self.error.emit(f"Connection Error: {e}")
            
            time.sleep(UPDATE_INTERVAL)
        self.finished.emit()

class WifiChecker(Worker):
    """Periodically checks the connected WiFi BSSID for the student client."""
    wifiStatus = pyqtSignal(bool, str) # is_authorized, bssid_str

    def __init__(self, bridge):
        super().__init__(bridge)
        self.os_type = platform.system()
        self.bssid_pattern = re.compile(r"([0-9a-f]{2}[:-]){5}([0-9a-f]{2})")

    def _get_bssid(self):
        try:
            if self.os_type == "Windows":
                result = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                for line in result.stdout.splitlines():
                    if "BSSID" in line and ":" in line:
                        bssid = line.split(":", 1)[1].strip().lower()
                        if self.bssid_pattern.match(bssid):
                            return bssid
            elif self.os_type == "Linux":
                result = subprocess.run(["iwgetid", "-ar"], capture_output=True, text=True, check=True)
                bssid = result.stdout.strip().lower()
                if self.bssid_pattern.match(bssid):
                    return bssid
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        return None

    def run(self):
        while self._is_running:
            if self.bridge.user_type == 'student' and self.bridge.user_id:
                current_bssid = self._get_bssid()
                is_authorized = current_bssid in self.bridge.authorized_bssids if current_bssid else False
                
                # If connection or auth status changes, notify the server
                if current_bssid != self.bridge.current_bssid or is_authorized != self.bridge.student_is_authorized:
                    self.bridge.current_bssid = current_bssid
                    self.bridge.student_is_authorized = is_authorized
                    self.bridge.update_student_connection_status(current_bssid)
                
                self.wifiStatus.emit(is_authorized, current_bssid)
            
            time.sleep(WIFI_CHECK_INTERVAL)
        self.finished.emit()

# =============================================================================
# BRIDGE (Python <-> JavaScript Communication Logic)
# =============================================================================

class Bridge(QObject):
    """Handles application logic and communication between Python and JS."""
    # Signals to send data TO JavaScript
    loginResult = pyqtSignal(str, bool, str, str)
    signupResult = pyqtSignal(str, bool, str)
    statusUpdate = pyqtSignal(dict)
    randomRingAlert = pyqtSignal(list)
    bssidUpdate = pyqtSignal(list, str, bool)
    studentRegisterResult = pyqtSignal(bool, str)
    studentWifiStatus = pyqtSignal(bool, str)
    studentTimerUpdate = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_id = None
        self.user_type = None
        self.user_name = None
        self.authorized_bssids = []
        self.student_is_authorized = False
        self.current_bssid = None
        self.status_thread = None
        self.wifi_thread = None

    def start_background_tasks(self):
        self.stop_background_tasks() # Ensure no old threads are running

        self.status_thread = QThread()
        self.status_updater = StatusUpdater(self)
        self.status_updater.moveToThread(self.status_thread)
        self.status_thread.started.connect(self.status_updater.run)
        self.status_updater.statusUpdate.connect(self.on_status_update)
        self.status_updater.studentTimerUpdate.connect(self.studentTimerUpdate.emit)
        self.status_updater.finished.connect(self.status_thread.quit)
        self.status_thread.start()

        self.wifi_thread = QThread()
        self.wifi_checker = WifiChecker(self)
        self.wifi_checker.moveToThread(self.wifi_thread)
        self.wifi_thread.started.connect(self.wifi_checker.run)
        self.wifi_checker.wifiStatus.connect(self.studentWifiStatus.emit)
        self.wifi_checker.finished.connect(self.wifi_thread.quit)
        self.wifi_thread.start()

    def stop_background_tasks(self):
        if hasattr(self, 'status_updater') and self.status_thread.isRunning():
            self.status_updater.stop()
            self.status_thread.wait()
        if hasattr(self, 'wifi_checker') and self.wifi_thread.isRunning():
            self.wifi_checker.stop()
            self.wifi_thread.wait()

    def on_status_update(self, status_data):
        self.authorized_bssids = status_data.get('authorized_bssids', [])
        if self.user_type == 'teacher':
            self.statusUpdate.emit(status_data)

    @pyqtSlot()
    def logout(self):
        self.user_id = None
        self.user_type = None
        self.user_name = None

    @pyqtSlot(str, str, str)
    def login(self, user_type, user_id, password):
        self.logout()
        # NOTE: In a real application, login would be a POST request to a secure endpoint.
        # For this demo, we assume login is successful to proceed.
        self.user_type = user_type
        self.user_id = user_id
        self.user_name = f"{user_type.capitalize()} {user_id}"
        self.loginResult.emit(user_type, True, "Login successful!", self.user_name)
        self.manualRefresh()

    @pyqtSlot(str, str, str, str)
    def signup(self, user_type, user_id, name, password):
        # Placeholder for signup logic.
        self.signupResult.emit(user_type, True, "Signup successful! Please log in.")
    
    @pyqtSlot()
    def manualRefresh(self):
        if not self.user_id: return
        threading.Thread(target=self._fetch_status).start()

    def _fetch_status(self):
        try:
            response = requests.get(f"{SERVER_URL}/get_status", timeout=5)
            if response.status_code == 200:
                self.on_status_update(response.json())
        except Exception as e:
            print(f"Refresh Error: {e}")

    # --- Methods called FROM JavaScript (Teacher UI) ---
    @pyqtSlot()
    def startSession(self):
        self._make_post_request("/start_session", {"session_name": f"Session by {self.user_name}"})

    @pyqtSlot()
    def endSession(self):
        self._make_post_request("/end_session")

    @pyqtSlot()
    def randomRing(self):
        try:
            response = requests.post(f"{SERVER_URL}/random_ring", timeout=5)
            if response.status_code == 200:
                self.randomRingAlert.emit(response.json().get("selected_students", []))
        except Exception as e:
            print(f"Random Ring Error: {e}")

    @pyqtSlot(str, str)
    def registerStudent(self, student_id, name):
        # Placeholder. A real app would have a secure teacher endpoint.
        self.studentRegisterResult.emit(True, f"Student '{name}' registered.")

    @pyqtSlot(str)
    def addBssid(self, new_bssid):
        new_bssid = new_bssid.strip().lower()
        if not self.bssid_pattern.match(new_bssid):
            self.bssidUpdate.emit(self.authorized_bssids, "Invalid BSSID format.", False)
            return
        if new_bssid not in self.authorized_bssids:
            updated_list = self.authorized_bssids + [new_bssid]
            self._set_bssid_list(updated_list, "BSSID added successfully.")

    @pyqtSlot(str)
    def removeBssid(self, bssid_to_remove):
        updated_list = [b for b in self.authorized_bssids if b != bssid_to_remove]
        self._set_bssid_list(updated_list, "BSSID removed.")
        
    def _set_bssid_list(self, bssid_list, success_message):
        try:
            response = requests.post(f"{SERVER_URL}/set_bssid", json={"bssids": bssid_list}, timeout=5)
            if response.status_code == 200:
                self.authorized_bssids = bssid_list
                self.bssidUpdate.emit(self.authorized_bssids, success_message, True)
            else:
                self.bssidUpdate.emit(self.authorized_bssids, "Server error.", False)
        except Exception as e:
            self.bssidUpdate.emit(self.authorized_bssids, f"Connection error: {e}", False)

    # --- Methods called FROM JavaScript (Student UI) ---
    def update_student_connection_status(self, bssid):
        self._make_post_request("/student/connect", {"student_id": self.user_id, "bssid": bssid})

    @pyqtSlot()
    def startStudentAttendance(self):
        self._make_post_request("/student/timer/start", {"student_id": self.user_id})

    # --- Internal Helper ---
    def _make_post_request(self, endpoint, data=None):
        if not self.user_id: return
        threading.Thread(target=self.__execute_post, args=(endpoint, data)).start()
        
    def __execute_post(self, endpoint, data):
        try:
            requests.post(f"{SERVER_URL}{endpoint}", json=data, timeout=5)
            self._fetch_status() # Refresh state after action
        except Exception as e:
            print(f"POST Error to {endpoint}: {e}")

# =============================================================================
# MAIN APPLICATION WINDOW
# =============================================================================

class CustomWebEnginePage(QWebEnginePage):
    """Custom QWebEnginePage to capture and print JavaScript console messages for debugging."""
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        print(f"JS Console > {message} (line: {lineNumber})")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Let's Bunk - Attendance System")
        self.setGeometry(100, 100, 1400, 900)

        self.browser = QWebEngineView()
        self.page = CustomWebEnginePage(self.browser)
        self.browser.setPage(self.page)
        
        self.channel = QWebChannel()
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)
        
        self.browser.setHtml(HTML_CONTENT, QUrl("qrc:///"))
        self.page.loadFinished.connect(self._on_load_finished)
        
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.browser)
        self.setCentralWidget(central_widget)

        self.bridge.start_background_tasks()

    def _on_load_finished(self, ok):
        if ok:
            self.page.runJavaScript(QWEBCHANNEL_JS)

    def closeEvent(self, event):
        self.bridge.stop_background_tasks()
        event.accept()

# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================
if __name__ == '__main__':
    # FIX: The following lines caused the AttributeError.
    # In PyQt6, High DPI scaling is handled automatically and these attributes are obsolete.
    # They have been removed to ensure the application runs correctly.
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
