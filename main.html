<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Cosmic Goal Battle</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            margin: 0;
            overflow: hidden;
            font-family: 'Arial', sans-serif;
            background: radial-gradient(ellipse at bottom, #1B2735 0%, #090A0F 100%);
            color: white;
            height: 100vh;
            touch-action: manipulation;
        }

        /* Entry Screen Styles */
        #entry-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            background: radial-gradient(ellipse at bottom, #1B2735 0%, #090A0F 100%);
        }

        .title-container {
            text-align: center;
            margin-bottom: 30px;
            animation: float 3s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-20px); }
        }

        h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            text-shadow: 0 0 10px #4fc3f7, 0 0 20px #4fc3f7;
            background: linear-gradient(to right, #4fc3f7, #e91e63);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }

        .subtitle {
            font-size: 1.2rem;
            opacity: 0.8;
        }

        .input-container {
            width: 80%;
            max-width: 400px;
            margin-bottom: 20px;
        }

        input {
            width: 100%;
            padding: 15px;
            border-radius: 25px;
            border: 2px solid #4fc3f7;
            background: rgba(0, 0, 0, 0.5);
            color: white;
            font-size: 1rem;
            text-align: center;
            outline: none;
            transition: all 0.3s;
        }

        input:focus {
            border-color: #e91e63;
            box-shadow: 0 0 10px #e91e63;
        }

        .btn {
            padding: 15px 30px;
            border-radius: 25px;
            background: linear-gradient(45deg, #4fc3f7, #e91e63);
            color: white;
            border: none;
            font-size: 1rem;
            cursor: pointer;
            margin: 10px;
            transition: all 0.3s;
            text-transform: uppercase;
            font-weight: bold;
            letter-spacing: 1px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
        }

        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
        }

        .btn:active {
            transform: translateY(1px);
        }

        .btn-group {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
        }

        .mode-select {
            margin-top: 20px;
            text-align: center;
        }

        .mode-btn {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.3);
            margin: 5px;
        }

        .mode-btn.active {
            background: linear-gradient(45deg, #4fc3f7, #e91e63);
        }

        /* Connection Screen Styles */
        #connection-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: none;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 999;
            background: radial-gradient(ellipse at bottom, #1B2735 0%, #090A0F 100%);
        }

        .connection-container {
            background: rgba(0, 0, 0, 0.7);
            padding: 30px;
            border-radius: 15px;
            max-width: 500px;
            width: 90%;
            text-align: center;
            border: 1px solid #4fc3f7;
            box-shadow: 0 0 20px rgba(79, 195, 247, 0.5);
        }

        .qr-container {
            margin: 20px 0;
            padding: 10px;
            background: white;
            border-radius: 10px;
            display: inline-block;
        }

        .connection-status {
            margin: 20px 0;
            padding: 10px;
            border-radius: 5px;
        }

        .connected {
            background: rgba(76, 175, 80, 0.3);
            border: 1px solid #4CAF50;
        }

        .disconnected {
            background: rgba(244, 67, 54, 0.3);
            border: 1px solid #F44336;
        }

        /* Game Canvas Styles */
        canvas {
            display: block;
        }

        .scoreboard {
            position: absolute;
            top: 10px;
            width: 100%;
            display: flex;
            justify-content: space-around;
            color: white;
            font-family: 'Arial Black', sans-serif;
            font-size: 24px;
            text-shadow: 0 0 10px #fff;
            z-index: 100;
        }

        .controls {
            position: absolute;
            bottom: 10px;
            width: 100%;
            display: flex;
            justify-content: space-around;
            color: white;
            font-family: Arial, sans-serif;
            font-size: 14px;
            text-align: center;
            z-index: 100;
        }

        .goal {
            position: absolute;
            width: 40px;
            height: 150px;
            border: 3px dashed rgba(255, 255, 255, 0.7);
            z-index: 10;
        }

        #redGoal {
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            border-right: none;
        }

        #blueGoal {
            right: 0;
            top: 50%;
            transform: translateY(-50%);
            border-left: none;
        }

        .freeze-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            display: none;
        }

        #redFreeze {
            background: rgba(255, 0, 0, 0.3);
        }

        #blueFreeze {
            background: rgba(0, 0, 255, 0.3);
        }

        /* Mobile Controls */
        .mobile-controls {
            display: none;
            position: fixed;
            width: 100%;
            height: 150px;
            bottom: 0;
            left: 0;
            z-index: 200;
            pointer-events: none;
        }

        .joystick-container {
            position: absolute;
            left: 30px;
            bottom: 30px;
            width: 100px;
            height: 100px;
            pointer-events: auto;
        }

        .joystick {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.5);
        }

        .joystick-knob {
            position: absolute;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.7);
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }

        .shoot-btn {
            position: absolute;
            right: 30px;
            bottom: 30px;
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: rgba(255, 0, 0, 0.3);
            border: 2px solid rgba(255, 255, 255, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
            font-weight: bold;
            pointer-events: auto;
            user-select: none;
        }

        .aim-toggle {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-size: 12px;
            pointer-events: auto;
            display: none;
        }

        /* Stars background for entry screen */
        .stars {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: -1;
        }

        .star {
            position: absolute;
            background-color: white;
            border-radius: 50%;
            animation: twinkle var(--duration) infinite ease-in-out;
        }

        @keyframes twinkle {
            0%, 100% { opacity: 0.2; }
            50% { opacity: 1; }
        }

        /* Responsive adjustments */
        @media (max-width: 768px) {
            h1 {
                font-size: 2rem;
            }

            .subtitle {
                font-size: 1rem;
            }

            .btn {
                padding: 12px 25px;
                font-size: 0.9rem;
            }

            .mobile-controls {
                display: block;
            }

            .aim-toggle {
                display: block;
            }

            .controls {
                display: none;
            }
        }
    </style>
</head>
<body>
    <!-- Entry Screen -->
    <div id="entry-screen">
        <div class="stars" id="stars"></div>
        <div class="title-container">
            <h1>COSMIC GOAL BATTLE</h1>
            <div class="subtitle">Intergalactic Spaceship Soccer</div>
        </div>
        
        <div class="input-container">
            <input type="text" id="player-name" placeholder="Enter your spaceship name" maxlength="12">
        </div>
        
        <div class="btn-group">
            <button class="btn" id="single-player-btn">Solo Mission</button>
            <button class="btn" id="multiplayer-btn">Dual Combat</button>
        </div>
        
        <div class="mode-select">
            <div style="margin-bottom: 10px;">Select Control Mode:</div>
            <div class="btn-group">
                <button class="btn mode-btn active" data-mode="keyboard">Keyboard</button>
                <button class="btn mode-btn" data-mode="mobile">Mobile</button>
            </div>
        </div>
    </div>

    <!-- Connection Screen -->
    <div id="connection-screen">
        <div class="connection-container">
            <h2>Multiplayer Connection</h2>
            <p id="connection-role">Waiting for connection...</p>
            
            <div class="qr-container" id="qr-code"></div>
            
            <div class="connection-status disconnected" id="connection-status">
                Disconnected
            </div>
            
            <div id="connection-info" style="margin: 15px 0; font-family: monospace; word-break: break-all;"></div>
            
            <button class="btn" id="cancel-connection-btn">Cancel</button>
        </div>
    </div>

    <!-- Game Canvas -->
    <canvas id="spaceCanvas"></canvas>
    
    <div class="scoreboard">
        <div id="redScore">RED: 0</div>
        <div id="blueScore">BLUE: 0</div>
    </div>
    
    <div class="controls">
        <div>RED: Arrows to move, 1(Aim Player)/2(Aim Ball)<br>ENTER to shoot</div>
        <div>BLUE: WASD to move, 0(Aim Player)/9(Aim Ball)<br>SPACE to shoot</div>
    </div>
    
    <div id="redGoal" class="goal"></div>
    <div id="blueGoal" class="goal"></div>
    
    <div id="redFreeze" class="freeze-overlay"></div>
    <div id="blueFreeze" class="freeze-overlay"></div>

    <!-- Mobile Controls -->
    <div class="mobile-controls">
        <div class="aim-toggle" id="aim-toggle">AIM: BALL</div>
        <div class="joystick-container">
            <div class="joystick">
                <div class="joystick-knob" id="joystick-knob"></div>
            </div>
        </div>
        <div class="shoot-btn" id="shoot-btn">FIRE</div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/peerjs@1.3.1/dist/peerjs.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/qrcode@1.4.4/build/qrcode.min.js"></script>
    <script>
        // Constants
        const PLAYER_SPEED = 5;
        const FRICTION = 0.93;
        const AUTO_AIM_SPEED = 0.05;
        const FREEZE_DURATION = 180; // 3 seconds at 60fps
        const GOAL_WIDTH = 40;
        const GOAL_HEIGHT = 150;

        // Game state
        let gameMode = 'single'; // 'single' or 'multi'
        let controlMode = 'keyboard'; // 'keyboard' or 'mobile'
        let playerName = 'Player';
        let peer = null;
        let conn = null;
        let isHost = false;
        let peerId = '';
        let connected = false;

        // DOM elements
        const entryScreen = document.getElementById('entry-screen');
        const connectionScreen = document.getElementById('connection-screen');
        const playerNameInput = document.getElementById('player-name');
        const singlePlayerBtn = document.getElementById('single-player-btn');
        const multiplayerBtn = document.getElementById('multiplayer-btn');
        const cancelConnectionBtn = document.getElementById('cancel-connection-btn');
        const connectionRole = document.getElementById('connection-role');
        const connectionStatus = document.getElementById('connection-status');
        const connectionInfo = document.getElementById('connection-info');
        const qrCodeContainer = document.getElementById('qr-code');
        const aimToggle = document.getElementById('aim-toggle');
        const shootBtn = document.getElementById('shoot-btn');
        const joystickKnob = document.getElementById('joystick-knob');

        // Mobile controls variables
        let joystickActive = false;
        let joystickAngle = 0;
        let joystickDistance = 0;
        let joystickStartX = 0;
        let joystickStartY = 0;
        let joystickKnobX = 0;
        let joystickKnobY = 0;
        let isShooting = false;

        // Create stars for background
        function createStars() {
            const starsContainer = document.getElementById('stars');
            const starsCount = Math.floor(window.innerWidth * window.innerHeight / 1000);
            
            for (let i = 0; i < starsCount; i++) {
                const star = document.createElement('div');
                star.className = 'star';
                
                // Random position
                const x = Math.random() * 100;
                const y = Math.random() * 100;
                
                // Random size (0.5px to 2px)
                const size = Math.random() * 1.5 + 0.5;
                
                // Random animation duration (2s to 5s)
                const duration = Math.random() * 3 + 2;
                
                star.style.left = `${x}%`;
                star.style.top = `${y}%`;
                star.style.width = `${size}px`;
                star.style.height = `${size}px`;
                star.style.setProperty('--duration', `${duration}s`);
                
                starsContainer.appendChild(star);
            }
        }

        // Set up event listeners
        function setupEventListeners() {
            // Mode selection buttons
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    controlMode = this.dataset.mode;
                });
            });

            // Single player button
            singlePlayerBtn.addEventListener('click', function() {
                playerName = playerNameInput.value.trim() || 'Player';
                gameMode = 'single';
                startGame();
            });

            // Multiplayer button
            multiplayerBtn.addEventListener('click', function() {
                playerName = playerNameInput.value.trim() || 'Player';
                gameMode = 'multi';
                setupMultiplayer();
            });

            // Cancel connection button
            cancelConnectionBtn.addEventListener('click', function() {
                if (conn) conn.close();
                if (peer) peer.destroy();
                connectionScreen.style.display = 'none';
                entryScreen.style.display = 'flex';
            });

            // Mobile controls
            if (isMobile()) {
                setupMobileControls();
            }

            // Handle window resize
            window.addEventListener('resize', handleResize);
        }

        // Check if mobile device
        function isMobile() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        }

        // Set up mobile controls
        function setupMobileControls() {
            const joystickContainer = document.querySelector('.joystick-container');
            
            // Touch start
            joystickContainer.addEventListener('touchstart', handleJoystickStart);
            document.addEventListener('touchstart', handleDocumentTouchStart);
            
            // Touch move
            document.addEventListener('touchmove', handleJoystickMove);
            
            // Touch end
            document.addEventListener('touchend', handleJoystickEnd);
            
            // Shoot button
            shootBtn.addEventListener('touchstart', function(e) {
                e.preventDefault();
                isShooting = true;
                this.style.transform = 'scale(0.9)';
                this.style.background = 'rgba(255, 0, 0, 0.5)';
            });
            
            shootBtn.addEventListener('touchend', function(e) {
                e.preventDefault();
                isShooting = false;
                this.style.transform = 'scale(1)';
                this.style.background = 'rgba(255, 0, 0, 0.3)';
            });
            
            // Aim toggle
            aimToggle.addEventListener('click', function() {
                if (this.textContent === 'AIM: BALL') {
                    this.textContent = 'AIM: PLAYER';
                } else {
                    this.textContent = 'AIM: BALL';
                }
            });
        }

        function handleJoystickStart(e) {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = e.currentTarget.getBoundingClientRect();
            
            joystickStartX = rect.left + rect.width / 2;
            joystickStartY = rect.top + rect.height / 2;
            joystickActive = true;
            
            handleJoystickMove(e);
        }

        function handleDocumentTouchStart(e) {
            if (!joystickActive) {
                const touch = e.touches[0];
                const joystickRect = document.querySelector('.joystick-container').getBoundingClientRect();
                
                // Check if touch is within joystick area
                if (touch.clientX >= joystickRect.left && touch.clientX <= joystickRect.right &&
                    touch.clientY >= joystickRect.top && touch.clientY <= joystickRect.bottom) {
                    handleJoystickStart(e);
                }
            }
        }

        function handleJoystickMove(e) {
            if (!joystickActive) return;
            e.preventDefault();
            
            const touch = e.touches[0];
            const dx = touch.clientX - joystickStartX;
            const dy = touch.clientY - joystickStartY;
            const distance = Math.sqrt(dx * dx + dy * dy);
            const maxDistance = 50;
            
            joystickAngle = Math.atan2(dy, dx);
            joystickDistance = Math.min(distance, maxDistance);
            
            // Update joystick knob position
            joystickKnobX = Math.cos(joystickAngle) * joystickDistance;
            joystickKnobY = Math.sin(joystickAngle) * joystickDistance;
            
            joystickKnob.style.transform = `translate(calc(-50% + ${joystickKnobX}px), calc(-50% + ${joystickKnobY}px)`;
        }

        function handleJoystickEnd(e) {
            if (!joystickActive) return;
            e.preventDefault();
            
            joystickActive = false;
            joystickDistance = 0;
            joystickKnob.style.transform = 'translate(-50%, -50%)';
        }

        // Set up multiplayer connection
        function setupMultiplayer() {
            entryScreen.style.display = 'none';
            connectionScreen.style.display = 'flex';
            
            // Create PeerJS connection
            peer = new Peer();
            
            peer.on('open', function(id) {
                peerId = id;
                connectionInfo.textContent = `Your ID: ${id}`;
                
                // Show QR code for easy connection
                QRCode.toCanvas(qrCodeContainer, id, { width: 200 }, function(error) {
                    if (error) console.error(error);
                });
                
                // Ask user if they want to host or join
                connectionRole.innerHTML = `
                    <p>Share your ID with a friend to connect</p>
                    <div class="btn-group" style="margin-top: 15px;">
                        <button class="btn" id="host-btn">Host Game</button>
                        <button class="btn" id="join-btn">Join Game</button>
                    </div>
                    <input type="text" id="peer-id-input" placeholder="Enter friend's ID" style="margin-top: 15px;">
                `;
                
                document.getElementById('host-btn').addEventListener('click', function() {
                    isHost = true;
                    connectionRole.innerHTML = '<p>Waiting for player to join...</p>';
                    waitForConnection();
                });
                
                document.getElementById('join-btn').addEventListener('click', function() {
                    isHost = false;
                    const peerIdInput = document.getElementById('peer-id-input').value.trim();
                    if (peerIdInput) {
                        connectToPeer(peerIdInput);
                    } else {
                        alert('Please enter your friend\'s ID');
                    }
                });
            });
            
            peer.on('error', function(err) {
                console.error('PeerJS error:', err);
                connectionStatus.textContent = 'Connection Error';
                connectionStatus.className = 'connection-status disconnected';
            });
        }

        function waitForConnection() {
            peer.on('connection', function(connection) {
                conn = connection;
                setupConnection();
            });
        }

        function connectToPeer(peerId) {
            conn = peer.connect(peerId);
            setupConnection();
        }

        function setupConnection() {
            conn.on('open', function() {
                connected = true;
                connectionStatus.textContent = 'Connected!';
                connectionStatus.className = 'connection-status connected';
                
                // Send player name
                conn.send({ type: 'name', name: playerName });
                
                // Start the game after a short delay
                setTimeout(startGame, 1000);
            });
            
            conn.on('data', function(data) {
                handleMessage(data);
            });
            
            conn.on('close', function() {
                connected = false;
                connectionStatus.textContent = 'Disconnected';
                connectionStatus.className = 'connection-status disconnected';
                alert('Connection lost');
                location.reload();
            });
            
            conn.on('error', function(err) {
                console.error('Connection error:', err);
                connectionStatus.textContent = 'Connection Error';
                connectionStatus.className = 'connection-status disconnected';
            });
        }

        function handleMessage(data) {
            switch(data.type) {
                case 'name':
                    // Store opponent's name
                    opponentName = data.name;
                    break;
                case 'input':
                    // Handle opponent's input
                    handleRemoteInput(data);
                    break;
                case 'state':
                    // Sync game state
                    syncGameState(data);
                    break;
            }
        }

        function sendMessage(message) {
            if (conn && conn.open) {
                conn.send(message);
            }
        }

        // Start the game
        function startGame() {
            entryScreen.style.display = 'none';
            connectionScreen.style.display = 'none';
            
            // Initialize canvas and game
            initGame();
        }

        // Handle window resize
        function handleResize() {
            if (canvas) {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
                
                if (centralBall) {
                    centralBall.reset();
                }
                
                if (player1) {
                    player1.respawn();
                }
                
                if (player2) {
                    player2.respawn();
                }
            }
        }

        // Initialize the game
        function initGame() {
            // Canvas setup
            const canvas = document.getElementById('spaceCanvas');
            const ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;

            // Player class
            class Player {
                constructor(x, y, color, keys) {
                    this.x = x;
                    this.y = y;
                    this.radius = 20;
                    this.color = color;
                    this.velocity = [0, 0];
                    this.health = 100;
                    this.maxHealth = 100;
                    this.bullets = [];
                    this.score = 0;
                    this.frozen = 0;
                    this.keys = keys;
                    this.autoAimTarget = null;
                    this.previousHealth = this.health;
                    this.angle = Math.random() * Math.PI * 2;
                    this.isShooting = false;
                    this.shootCooldown = 0;
                    this.freezeTime = 0;
                    this.invulnerable = 0;
                    this.isLocal = false;
                }

                update(target, ball) {
                    // Handle freeze state
                    if (this.freezeTime > 0) {
                        this.freezeTime--;
                        if (this.freezeTime === 0) {
                            this.health = this.maxHealth;
                            this.invulnerable = 60; // 1 second invulnerability
                            document.getElementById(`${this.color.toLowerCase()}Freeze`).style.display = 'none';
                            this.respawn();
                        }
                        return;
                    }
                    
                    // Handle invulnerability
                    if (this.invulnerable > 0) {
                        this.invulnerable--;
                    }

                    // Apply friction
                    this.velocity[0] *= FRICTION;
                    this.velocity[1] *= FRICTION;

                    // Update position
                    this.x += this.velocity[0];
                    this.y += this.velocity[1];

                    // Keep player within bounds
                    this.x = Math.max(this.radius, Math.min(canvas.width - this.radius, this.x));
                    this.y = Math.max(this.radius, Math.min(canvas.height - this.radius, this.y));

                    // Auto-aim logic
                    if (this.autoAimTarget) {
                        let targetX, targetY;
                        
                        if (this.autoAimTarget === 'player') {
                            // Aim at the other player
                            targetX = target.x;
                            targetY = target.y;
                        } else if (this.autoAimTarget === 'ball') {
                            // Aim at the central ball
                            targetX = ball.x;
                            targetY = ball.y;
                        }
                        
                        const desiredAngle = Math.atan2(targetY - this.y, targetX - this.x);
                        let angleDiff = desiredAngle - this.angle;
                        
                        // Normalize angle difference
                        while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
                        while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
                        
                        // Smoothly adjust angle
                        this.angle += angleDiff * AUTO_AIM_SPEED;
                    }

                    // Handle shooting cooldown
                    if (this.shootCooldown > 0) {
                        this.shootCooldown--;
                    } else if (this.isShooting) {
                        this.shoot();
                        this.shootCooldown = 15;
                    }
                }

                draw(ctx) {
                    // Draw spaceship (circle with direction indicator)
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                    ctx.fillStyle = this.invulnerable > 0 && Math.floor(Date.now() / 100) % 2 === 0 ? 'white' : this.color;
                    ctx.fill();
                    
                    // Draw direction indicator
                    ctx.beginPath();
                    ctx.moveTo(this.x, this.y);
                    ctx.lineTo(
                        this.x + Math.cos(this.angle) * this.radius * 1.5,
                        this.y + Math.sin(this.angle) * this.radius * 1.5
                    );
                    ctx.lineWidth = 3;
                    ctx.strokeStyle = 'white';
                    ctx.stroke();

                    // Draw health bar if not invulnerable
                    if (this.invulnerable === 0) {
                        const healthBarWidth = this.radius * 2;
                        const healthPercentage = this.health / this.maxHealth;
                        
                        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
                        ctx.fillRect(this.x - this.radius, this.y - this.radius - 15, healthBarWidth, 5);
                        
                        ctx.fillStyle = healthPercentage > 0.6 ? '#00ff00' : 
                                        healthPercentage > 0.3 ? '#ffff00' : '#ff0000';
                        ctx.fillRect(this.x - this.radius, this.y - this.radius - 15, healthBarWidth * healthPercentage, 5);
                    }
                }

                shoot() {
                    const bulletSpeed = 10;
                    const bullet = {
                        x: this.x + Math.cos(this.angle) * this.radius,
                        y: this.y + Math.sin(this.angle) * this.radius,
                        vx: Math.cos(this.angle) * bulletSpeed,
                        vy: Math.sin(this.angle) * bulletSpeed,
                        radius: 5,
                        color: this.color,
                        owner: this,
                        distance: 0 // Track distance traveled
                    };
                    this.bullets.push(bullet);
                }

                updateBullets() {
                    for (let i = this.bullets.length - 1; i >= 0; i--) {
                        const bullet = this.bullets[i];
                        bullet.x += bullet.vx;
                        bullet.y += bullet.vy;
                        bullet.distance += Math.sqrt(bullet.vx**2 + bullet.vy**2);

                        // Remove bullets that are out of bounds
                        if (bullet.x < 0 || bullet.x > canvas.width || 
                            bullet.y < 0 || bullet.y > canvas.height) {
                            this.bullets.splice(i, 1);
                        }
                    }
                }

                drawBullets(ctx) {
                    ctx.save();
                    this.bullets.forEach(bullet => {
                        ctx.beginPath();
                        ctx.arc(bullet.x, bullet.y, bullet.radius, 0, Math.PI * 2);
                        ctx.fillStyle = bullet.color;
                        ctx.fill();
                    });
                    ctx.restore();
                }

                freeze() {
                    this.freezeTime = FREEZE_DURATION;
                    this.velocity = [0, 0];
                    document.getElementById(`${this.color.toLowerCase()}Freeze`).style.display = 'block';
                }

                respawn() {
                    this.x = this.color === 'Red' ? canvas.width * 0.25 : canvas.width * 0.75;
                    this.y = canvas.height / 2;
                    this.velocity = [0, 0];
                }
            }

            // Central ball
            const centralBall = {
                x: canvas.width / 2,
                y: canvas.height / 2,
                radius: 25,
                color: 'purple',
                velocity: [0, 0],
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
                    
                    const gradient = ctx.createRadialGradient(
                        this.x - this.radius/3, 
                        this.y - this.radius/3, 
                        0,
                        this.x, 
                        this.y, 
                        this.radius
                    );
                    gradient.addColorStop(0, 'white');
                    gradient.addColorStop(0.7, this.color);
                    gradient.addColorStop(1, '#4B0082');
                    
                    ctx.fillStyle = gradient;
                    ctx.fill();
                    
                    // Add some decoration
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.radius * 0.7, 0, Math.PI * 2);
                    ctx.strokeStyle = 'white';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                },
                update() {
                    // Apply friction
                    this.velocity[0] *= 0.98;
                    this.velocity[1] *= 0.98;
                    
                    // Update position
                    this.x += this.velocity[0];
                    this.y += this.velocity[1];
                    
                    // Keep ball within bounds
                    const margin = 50;
                    if (this.x < margin) {
                        this.x = margin;
                        this.velocity[0] *= -0.8;
                    }
                    if (this.x > canvas.width - margin) {
                        this.x = canvas.width - margin;
                        this.velocity[0] *= -0.8;
                    }
                    if (this.y < margin) {
                        this.y = margin;
                        this.velocity[1] *= -0.8;
                    }
                    if (this.y > canvas.height - margin) {
                        this.y = canvas.height - margin;
                        this.velocity[1] *= -0.8;
                    }
                    
                    // Check for goals
                    this.checkGoals();
                },
                checkGoals() {
                    // Check red goal (left side)
                    if (this.x - this.radius < GOAL_WIDTH && 
                        this.y > (canvas.height - GOAL_HEIGHT)/2 && 
                        this.y < (canvas.height + GOAL_HEIGHT)/2) {
                        player2.score++;
                        updateScoreboard();
                        this.reset();
                    }
                    
                    // Check blue goal (right side)
                    if (this.x + this.radius > canvas.width - GOAL_WIDTH && 
                        this.y > (canvas.height - GOAL_HEIGHT)/2 && 
                        this.y < (canvas.height + GOAL_HEIGHT)/2) {
                        player1.score++;
                        updateScoreboard();
                        this.reset();
                    }
                },
                reset() {
                    this.x = canvas.width / 2;
                    this.y = canvas.height / 2;
                    this.velocity = [0, 0];
                }
            };

            // Star class for background
            class Star {
                constructor() {
                    this.x = Math.random() * canvas.width;
                    this.y = Math.random() * canvas.height;
                    this.size = Math.random() * 1.5;
                    this.blinkSpeed = Math.random() * 0.05;
                    this.opacity = Math.random();
                    this.opacityDirection = Math.random() > 0.5 ? 1 : -1;
                }
                
                update() {
                    this.opacity += this.blinkSpeed * this.opacityDirection;
                    if (this.opacity > 1 || this.opacity < 0.2) {
                        this.opacityDirection *= -1;
                    }
                }
                
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(255, 255, 255, ${this.opacity})`;
                    ctx.fill();
                }
            }

            // Shooting star class for background
            class ShootingStar {
                constructor() {
                    this.reset();
                }
                
                reset() {
                    this.x = Math.random() * canvas.width;
                    this.y = 0;
                    this.speed = Math.random() * 10 + 5;
                    this.size = Math.random() * 2 + 1;
                    this.angle = Math.random() * Math.PI / 4 + Math.PI / 8;
                    this.length = Math.random() * 50 + 50;
                    this.active = true;
                }
                
                update() {
                    this.x += Math.cos(this.angle) * this.speed;
                    this.y += Math.sin(this.angle) * this.speed;
                    
                    if (this.x > canvas.width || this.y > canvas.height) {
                        this.active = false;
                    }
                }
                
                draw() {
                    ctx.beginPath();
                    ctx.moveTo(this.x, this.y);
                    ctx.lineTo(
                        this.x - Math.cos(this.angle) * this.length,
                        this.y - Math.sin(this.angle) * this.length
                    );
                    ctx.lineWidth = this.size;
                    ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
                    ctx.stroke();
                }
            }

            // Create players
            const player1 = new Player(
                canvas.width * 0.25,
                canvas.height / 2,
                'Red',
                {up: 'ArrowUp', down: 'ArrowDown', left: 'ArrowLeft', right: 'ArrowRight', shoot: 'Enter'}
            );

            const player2 = new Player(
                canvas.width * 0.75,
                canvas.height / 2,
                'Blue',
                {up: 'w', down: 's', left: 'a', right: 'd', shoot: ' '}
            );

            // Set local player based on game mode
            if (gameMode === 'single') {
                player1.isLocal = true;
                player2.isLocal = false;
            } else if (gameMode === 'multi') {
                player1.isLocal = isHost;
                player2.isLocal = !isHost;
            }

            // Create stars
            const stars = [];
            const starCount = Math.floor(canvas.width * canvas.height / 1000);
            for (let i = 0; i < starCount; i++) {
                stars.push(new Star());
            }

            // Create shooting stars
            const shootingStars = [];
            for (let i = 0; i < 3; i++) {
                shootingStars.push(new ShootingStar());
            }

            // Handle keyboard input
            const keysPressed = {};

            window.addEventListener('keydown', (e) => {
                keysPressed[e.key] = true;
                
                // Player 1 shooting (Enter)
                if (e.key === player1.keys.shoot) {
                    player1.isShooting = true;
                }
                
                // Player 2 shooting (Space)
                if (e.key === player2.keys.shoot) {
                    player2.isShooting = true;
                }
                
                // Player 1 auto-aim modes
                if (e.key === '1') player1.autoAimTarget = 'player';
                if (e.key === '2') player1.autoAimTarget = 'ball';
                
                // Player 2 auto-aim modes
                if (e.key === '0') player2.autoAimTarget = 'player';
                if (e.key === '9') player2.autoAimTarget = 'ball';
            });

            window.addEventListener('keyup', (e) => {
                keysPressed[e.key] = false;
                
                // Player 1 shooting
                if (e.key === player1.keys.shoot) {
                    player1.isShooting = false;
                }
                
                // Player 2 shooting
                if (e.key === player2.keys.shoot) {
                    player2.isShooting = false;
                }
            });

            function updatePlayerMovement() {
                if (controlMode === 'keyboard') {
                    // Player 1 movement (Arrow keys)
                    if (keysPressed[player1.keys.up]) player1.velocity[1] = -PLAYER_SPEED;
                    if (keysPressed[player1.keys.down]) player1.velocity[1] = PLAYER_SPEED;
                    if (keysPressed[player1.keys.left]) player1.velocity[0] = -PLAYER_SPEED;
                    if (keysPressed[player1.keys.right]) player1.velocity[0] = PLAYER_SPEED;

                    // Player 2 movement (WASD)
                    if (keysPressed[player2.keys.up]) player2.velocity[1] = -PLAYER_SPEED;
                    if (keysPressed[player2.keys.down]) player2.velocity[1] = PLAYER_SPEED;
                    if (keysPressed[player2.keys.left]) player2.velocity[0] = -PLAYER_SPEED;
                    if (keysPressed[player2.keys.right]) player2.velocity[0] = PLAYER_SPEED;
                } else if (controlMode === 'mobile') {
                    // Mobile controls for local player
                    const localPlayer = player1.isLocal ? player1 : player2;
                    
                    if (joystickActive) {
                        localPlayer.velocity[0] = Math.cos(joystickAngle) * PLAYER_SPEED * (joystickDistance / 50);
                        localPlayer.velocity[1] = Math.sin(joystickAngle) * PLAYER_SPEED * (joystickDistance / 50);
                    }
                    
                    // Auto-aim based on toggle
                    if (aimToggle.textContent === 'AIM: BALL') {
                        localPlayer.autoAimTarget = 'ball';
                    } else {
                        localPlayer.autoAimTarget = 'player';
                    }
                    
                    // Shooting
                    localPlayer.isShooting = isShooting;
                }
            }

            function checkBulletCollisions() {
                // Check bullet-to-bullet collisions
                for (let i = player1.bullets.length - 1; i >= 0; i--) {
                    for (let j = player2.bullets.length - 1; j >= 0; j--) {
                        const b1 = player1.bullets[i];
                        const b2 = player2.bullets[j];
                        
                        const dx = b1.x - b2.x;
                        const dy = b1.y - b2.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        
                        if (distance < b1.radius + b2.radius) {
                            // Destroy the bullet that's traveled farther
                            if (b1.distance > b2.distance) {
                                player1.bullets.splice(i, 1);
                            } else {
                                player2.bullets.splice(j, 1);
                            }
                            break; // Only one collision per bullet
                        }
                    }
                }
            }

            function checkCollisions() {
                // Check bullet collisions
                checkBulletCollisions();
                checkPlayerBulletCollisions(player1, player2);
                checkPlayerBulletCollisions(player2, player1);
                
                // Check player-to-player collision
                checkPlayerCollision(player1, player2);
                
                // Check collisions with central ball
                checkBallCollision(player1);
                checkBallCollision(player2);
            }

            function checkPlayerCollision(p1, p2) {
                if (p1.freezeTime > 0 || p2.freezeTime > 0) return;
                
                const dx = p1.x - p2.x;
                const dy = p1.y - p2.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const minDistance = p1.radius + p2.radius;
                
                if (distance < minDistance) {
                    const angle = Math.atan2(dy, dx);
                    const overlap = minDistance - distance;
                    
                    const moveX = Math.cos(angle) * overlap * 0.5;
                    const moveY = Math.sin(angle) * overlap * 0.5;
                    
                    p1.x += moveX;
                    p1.y += moveY;
                    p2.x -= moveX;
                    p2.y -= moveY;
                    
                    const speed1 = Math.sqrt(p1.velocity[0] ** 2 + p1.velocity[1] ** 2);
                    const speed2 = Math.sqrt(p2.velocity[0] ** 2 + p2.velocity[1] ** 2);
                    
                    p1.velocity[0] = Math.cos(angle) * speed2 * 0.8;
                    p1.velocity[1] = Math.sin(angle) * speed2 * 0.8;
                    p2.velocity[0] = -Math.cos(angle) * speed1 * 0.8;
                    p2.velocity[1] = -Math.sin(angle) * speed1 * 0.8;
                }
            }

            function checkBallCollision(player) {
                if (player.freezeTime > 0) return;
                
                const dx = player.x - centralBall.x;
                const dy = player.y - centralBall.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const minDistance = player.radius + centralBall.radius;
                
                if (distance < minDistance) {
                    const angle = Math.atan2(dy, dx);
                    
                    player.x = centralBall.x + Math.cos(angle) * minDistance;
                    player.y = centralBall.y + Math.sin(angle) * minDistance;
                    
                    const speed = Math.sqrt(player.velocity[0] ** 2 + player.velocity[1] ** 2);
                    player.velocity[0] = Math.cos(angle) * speed * 1.2;
                    player.velocity[1] = Math.sin(angle) * speed * 1.2;
                    
                    // Push ball
                    centralBall.velocity[0] = -Math.cos(angle) * speed * 0.5;
                    centralBall.velocity[1] = -Math.sin(angle) * speed * 0.5;
                }
            }

            function checkPlayerBulletCollisions(shooter, target) {
                for (let i = shooter.bullets.length - 1; i >= 0; i--) {
                    const bullet = shooter.bullets[i];
                    
                    if (target.freezeTime === 0 && target.invulnerable === 0) {
                        const dx = target.x - bullet.x;
                        const dy = target.y - bullet.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);

                        if (distance < target.radius + bullet.radius) {
                            target.health -= 10;
                            shooter.bullets.splice(i, 1);
                            
                            if (target.health <= 0) {
                                target.freeze();
                                shooter.score++;
                                updateScoreboard();
                            }
                        }
                    }
                    
                    const ballDx = centralBall.x - bullet.x;
                    const ballDy = centralBall.y - bullet.y;
                    const ballDistance = Math.sqrt(ballDx * ballDx + ballDy * ballDy);
                    
                    if (ballDistance < centralBall.radius + bullet.radius) {
                        shooter.bullets.splice(i, 1);
                        centralBall.velocity[0] += bullet.vx * 0.1;
                        centralBall.velocity[1] += bullet.vy * 0.1;
                    }
                }
            }

            function updateScoreboard() {
                document.getElementById('redScore').textContent = `RED: ${player1.score}`;
                document.getElementById('blueScore').textContent = `BLUE: ${player2.score}`;
            }

            // Animation loop
            function animate() {
                // Clear canvas with a semi-transparent black to create trailing effect
                ctx.fillStyle = 'rgba(11, 13, 23, 0.2)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                
                // Update and draw stars
                stars.forEach(star => {
                    star.update();
                    star.draw(ctx);
                });
                
                // Update and draw shooting stars
                shootingStars.forEach((star, index) => {
                    if (star.active) {
                        star.update();
                        star.draw(ctx);
                    } else if (Math.random() > 0.98) {
                        shootingStars[index] = new ShootingStar();
                    }
                });
                
                // Update central ball
                centralBall.update();
                
                // Update player movement
                updatePlayerMovement();
                
                // Update players with their respective targets
                player1.update(player2, centralBall);
                player2.update(player1, centralBall);
                
                // Update bullets
                player1.updateBullets();
                player2.updateBullets();
                
                // Check collisions
                checkCollisions();
                
                // Draw central ball
                centralBall.draw(ctx);
                
                // Draw players and bullets
                player1.draw(ctx);
                player2.draw(ctx);
                player1.drawBullets(ctx);
                player2.drawBullets(ctx);
                
                requestAnimationFrame(animate);
            }

            // Start the animation
            animate();
            updateScoreboard();
        }

        // Initialize the app
        createStars();
        setupEventListeners();
    </script>
</body>
</html>
