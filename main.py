import pygame
import socket
import threading
import time
import json
import requests
from flask import Flask, request, jsonify
from collections import defaultdict

# Server Configuration
app = Flask(__name__)
SERVER_URL = "https://deadball.onrender.com"
PING_INTERVAL = 5
game_rooms = defaultdict(dict)
connected_players = {}

@app.route('/ping', methods=['POST'])
def ping():
    player_id = request.json.get('player_id')
    if player_id in connected_players:
        connected_players[player_id]['last_seen'] = time.time()
        return jsonify({"status": "ok"})
    return jsonify({"error": "Invalid player ID"}), 400

@app.route('/register', methods=['POST'])
def register():
    name = request.json.get('name', 'Player')
    player_id = str(hash(name + str(time.time())))
    connected_players[player_id] = {
        'name': name,
        'last_seen': time.time(),
        'room_id': None
    }
    return jsonify({"player_id": player_id})

@app.route('/create', methods=['POST'])
def create_room():
    player_id = request.json.get('player_id')
    if player_id not in connected_players:
        return jsonify({"error": "Invalid player ID"}), 400
    
    room_id = str(hash(player_id + str(time.time())))
    game_rooms[room_id] = {
        'players': [player_id],
        'host': player_id,
        'state': None,
        'last_active': time.time()
    }
    connected_players[player_id]['room_id'] = room_id
    return jsonify({"room_id": room_id})

@app.route('/join', methods=['POST'])
def join_room():
    player_id = request.json.get('player_id')
    room_id = request.json.get('room_id')
    
    if (player_id not in connected_players or 
        room_id not in game_rooms or 
        len(game_rooms[room_id]['players']) >= 2):
        return jsonify({"error": "Cannot join room"}), 400
    
    game_rooms[room_id]['players'].append(player_id)
    connected_players[player_id]['room_id'] = room_id
    game_rooms[room_id]['last_active'] = time.time()
    
    host_name = connected_players[game_rooms[room_id]['host']]['name']
    return jsonify({"host_name": host_name})

@app.route('/update', methods=['POST'])
def update_state():
    player_id = request.json.get('player_id')
    room_id = request.json.get('room_id')
    game_state = request.json.get('state')
    
    if (player_id in connected_players and 
        room_id in game_rooms and 
        player_id in game_rooms[room_id]['players']):
        game_rooms[room_id]['state'] = game_state
        game_rooms[room_id]['last_active'] = time.time()
        return jsonify({"status": "updated"})
    return jsonify({"error": "Invalid update"}), 400

@app.route('/state', methods=['POST'])
def get_state():
    player_id = request.json.get('player_id')
    room_id = request.json.get('room_id')
    
    if (player_id in connected_players and 
        room_id in game_rooms and 
        player_id in game_rooms[room_id]['players']):
        return jsonify({"state": game_rooms[room_id]['state']})
    return jsonify({"error": "Invalid request"}), 400

def run_server():
    app.run(host='0.0.0.0', port=5000)

# Game Client
class CosmicGoalBattle:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Cosmic Goal Battle")
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_mode = "menu"  # menu, single, multi
        self.player_id = ""
        self.room_id = ""
        self.is_host = False
        self.opponent_name = "Opponent"
        self.last_ping = 0
        self.last_state_update = 0
        self.keys = {
            'p1_up': pygame.K_UP,
            'p1_down': pygame.K_DOWN,
            'p1_left': pygame.K_LEFT,
            'p1_right': pygame.K_RIGHT,
            'p1_shoot': pygame.K_RETURN,
            'p2_up': pygame.K_w,
            'p2_down': pygame.K_s,
            'p2_left': pygame.K_a,
            'p2_right': pygame.K_d,
            'p2_shoot': pygame.K_SPACE
        }
        
        # Game objects
        self.ball = {
            'x': 400, 'y': 300, 'radius': 15,
            'vx': 0, 'vy': 0, 'color': (128, 0, 128)
        }
        self.players = {
            'p1': {'x': 200, 'y': 300, 'radius': 20, 'color': (255, 0, 0),
                  'score': 0, 'health': 100, 'freeze': 0},
            'p2': {'x': 600, 'y': 300, 'radius': 20, 'color': (0, 0, 255),
                  'score': 0, 'health': 100, 'freeze': 0}
        }
        
        # Start server thread
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        # Start network thread
        self.network_thread = threading.Thread(target=self.network_loop, daemon=True)
        self.network_thread.start()
        
        self.main_loop()

    def network_loop(self):
        while self.running:
            current_time = time.time()
            
            # Send ping to maintain connection
            if current_time - self.last_ping > PING_INTERVAL:
                self.send_ping()
                self.last_ping = current_time
            
            # Get game state updates in multiplayer
            if self.game_mode == "multi":
                self.get_game_state()
            
            time.sleep(0.1)

    def send_ping(self):
        try:
            requests.post(f"{SERVER_URL}/ping", json={'player_id': self.player_id}, timeout=2)
        except:
            pass

    def register_player(self, name):
        try:
            response = requests.post(
                f"{SERVER_URL}/register",
                json={'name': name},
                timeout=3
            )
            if response.status_code == 200:
                self.player_id = response.json().get('player_id')
                return True
        except:
            pass
        return False

    def create_room(self):
        try:
            response = requests.post(
                f"{SERVER_URL}/create",
                json={'player_id': self.player_id},
                timeout=3
            )
            if response.status_code == 200:
                self.room_id = response.json().get('room_id')
                self.is_host = True
                return True
        except:
            pass
        return False

    def join_room(self, room_code):
        try:
            response = requests.post(
                f"{SERVER_URL}/join",
                json={
                    'player_id': self.player_id,
                    'room_id': room_code
                },
                timeout=3
            )
            if response.status_code == 200:
                self.room_id = room_code
                self.is_host = False
                self.opponent_name = response.json().get('host_name', 'Opponent')
                return True
        except:
            pass
        return False

    def update_game_state(self):
        if not self.is_host or self.game_mode != "multi":
            return
            
        try:
            state = {
                'ball': {
                    'x': self.ball['x'],
                    'y': self.ball['y'],
                    'vx': self.ball['vx'],
                    'vy': self.ball['vy']
                },
                'scores': {
                    'p1': self.players['p1']['score'],
                    'p2': self.players['p2']['score']
                },
                'health': {
                    'p1': self.players['p1']['health'],
                    'p2': self.players['p2']['health']
                },
                'freeze': {
                    'p1': self.players['p1']['freeze'],
                    'p2': self.players['p2']['freeze']
                }
            }
            
            requests.post(
                f"{SERVER_URL}/update",
                json={
                    'player_id': self.player_id,
                    'room_id': self.room_id,
                    'state': state
                },
                timeout=2
            )
        except:
            pass

    def get_game_state(self):
        if self.is_host or self.game_mode != "multi":
            return
            
        try:
            response = requests.post(
                f"{SERVER_URL}/state",
                json={
                    'player_id': self.player_id,
                    'room_id': self.room_id
                },
                timeout=2
            )
            
            if response.status_code == 200:
                state = response.json().get('state')
                if state:
                    self.ball['x'] = state['ball']['x']
                    self.ball['y'] = state['ball']['y']
                    self.ball['vx'] = state['ball']['vx']
                    self.ball['vy'] = state['ball']['vy']
                    
                    self.players['p1']['score'] = state['scores']['p1']
                    self.players['p2']['score'] = state['scores']['p2']
                    
                    self.players['p1']['health'] = state['health']['p1']
                    self.players['p2']['health'] = state['health']['p2']
                    
                    self.players['p1']['freeze'] = state['freeze']['p1']
                    self.players['p2']['freeze'] = state['freeze']['p2']
        except:
            pass

    def handle_input(self):
        keys = pygame.key.get_pressed()
        
        # Player 1 controls
        if self.players['p1']['freeze'] <= 0:
            if keys[self.keys['p1_up']]:
                self.players['p1']['y'] -= 5
            if keys[self.keys['p1_down']]:
                self.players['p1']['y'] += 5
            if keys[self.keys['p1_left']]:
                self.players['p1']['x'] -= 5
            if keys[self.keys['p1_right']]:
                self.players['p1']['x'] += 5
        
        # Player 2 controls (AI in single player)
        if self.game_mode == "single":
            # Simple AI for single player
            if self.ball['x'] > 400 and abs(self.ball['y'] - self.players['p2']['y']) > 30:
                if self.ball['y'] < self.players['p2']['y']:
                    self.players['p2']['y'] -= 3
                else:
                    self.players['p2']['y'] += 3
        elif self.players['p2']['freeze'] <= 0:
            if keys[self.keys['p2_up']]:
                self.players['p2']['y'] -= 5
            if keys[self.keys['p2_down']]:
                self.players['p2']['y'] += 5
            if keys[self.keys['p2_left']]:
                self.players['p2']['x'] -= 5
            if keys[self.keys['p2_right']]:
                self.players['p2']['x'] += 5
        
        # Keep players on screen
        for player in self.players.values():
            player['x'] = max(player['radius'], min(800 - player['radius'], player['x']))
            player['y'] = max(player['radius'], min(600 - player['radius'], player['y']))

    def update_physics(self):
        # Ball movement
        self.ball['x'] += self.ball['vx']
        self.ball['y'] += self.ball['vy']
        
        # Ball friction
        self.ball['vx'] *= 0.98
        self.ball['vy'] *= 0.98
        
        # Ball boundary collision
        if self.ball['x'] < self.ball['radius'] or self.ball['x'] > 800 - self.ball['radius']:
            self.ball['vx'] *= -0.8
        if self.ball['y'] < self.ball['radius'] or self.ball['y'] > 600 - self.ball['radius']:
            self.ball['vy'] *= -0.8
            
        # Keep ball on screen
        self.ball['x'] = max(self.ball['radius'], min(800 - self.ball['radius'], self.ball['x']))
        self.ball['y'] = max(self.ball['radius'], min(600 - self.ball['radius'], self.ball['y']))
        
        # Player-ball collision
        for player in self.players.values():
            if player['freeze'] > 0:
                player['freeze'] -= 1
                continue
                
            dx = player['x'] - self.ball['x']
            dy = player['y'] - self.ball['y']
            distance = (dx**2 + dy**2)**0.5
            
            if distance < player['radius'] + self.ball['radius']:
                # Calculate collision response
                angle = pygame.math.Vector2(dx, dy).angle_to((1, 0))
                power = min(10, distance / 5)
                
                self.ball['vx'] = pygame.math.Vector2(1, 0).rotate(-angle).x * power
                self.ball['vy'] = pygame.math.Vector2(1, 0).rotate(-angle).y * power
        
        # Goal detection
        if self.ball['x'] < 30 and 250 < self.ball['y'] < 350:
            self.players['p2']['score'] += 1
            self.reset_ball()
            
        if self.ball['x'] > 770 and 250 < self.ball['y'] < 350:
            self.players['p1']['score'] += 1
            self.reset_ball()

    def reset_ball(self):
        self.ball['x'] = 400
        self.ball['y'] = 300
        self.ball['vx'] = 0
        self.ball['vy'] = 0

    def draw(self):
        self.screen.fill((0, 0, 0))
        
        # Draw goals
        pygame.draw.rect(self.screen, (255, 0, 0), (0, 250, 30, 100), 2)
        pygame.draw.rect(self.screen, (0, 0, 255), (770, 250, 30, 100), 2)
        
        # Draw ball
        pygame.draw.circle(self.screen, self.ball['color'], 
                          (int(self.ball['x']), int(self.ball['y'])), 
                          self.ball['radius'])
        
        # Draw players
        for player in self.players.values():
            color = player['color']
            if player['freeze'] > 0:
                color = (color[0]//2, color[1]//2, color[2]//2)
            
            pygame.draw.circle(self.screen, color, 
                              (int(player['x']), int(player['y'])), 
                              player['radius'])
        
        # Draw scores
        font = pygame.font.SysFont(None, 36)
        p1_score = font.render(f"RED: {self.players['p1']['score']}", True, (255, 255, 255))
        p2_score = font.render(f"BLUE: {self.players['p2']['score']}", True, (255, 255, 255))
        self.screen.blit(p1_score, (50, 50))
        self.screen.blit(p2_score, (650, 50))
        
        # Draw menu if needed
        if self.game_mode == "menu":
            s = pygame.Surface((800, 600), pygame.SRCALPHA)
            s.fill((0, 0, 0, 200))
            self.screen.blit(s, (0, 0))
            
            title = pygame.font.SysFont(None, 72).render("COSMIC GOAL BATTLE", True, (255, 255, 255))
            self.screen.blit(title, (400 - title.get_width()//2, 150))
            
        pygame.display.flip()

    def show_menu(self):
        self.game_mode = "menu"
        menu_active = True
        name = ""
        room_code = ""
        
        while menu_active and self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    menu_active = False
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_1:  # Single player
                        self.game_mode = "single"
                        menu_active = False
                    
                    elif event.key == pygame.K_2:  # Multiplayer
                        if self.register_player(name if name else "Player"):
                            self.game_mode = "multi"
                            menu_active = False
                    
                    elif event.key == pygame.K_c:  # Create room
                        if self.register_player(name if name else "Player"):
                            if self.create_room():
                                self.game_mode = "multi"
                                menu_active = False
                    
                    elif event.key == pygame.K_j:  # Join room
                        if self.register_player(name if name else "Player"):
                            if room_code and self.join_room(room_code):
                                self.game_mode = "multi"
                                menu_active = False
                    
                    elif event.key == pygame.K_BACKSPACE:
                        if name:
                            name = name[:-1]
                    
                    else:
                        name += event.unicode
            
            self.draw()
            self.clock.tick(60)

    def main_loop(self):
        self.show_menu()
        
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
            
            self.handle_input()
            self.update_physics()
            
            if self.game_mode == "multi":
                current_time = time.time()
                if current_time - self.last_state_update > 0.1:  # 10fps state updates
                    self.update_game_state()
                    self.last_state_update = current_time
            
            self.draw()
            self.clock.tick(60)

if __name__ == "__main__":
    game = CosmicGoalBattle()
