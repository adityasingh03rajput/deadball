from flask import Flask, request, jsonify
import time
import threading
from collections import defaultdict
import uuid

app = Flask(__name__)

# Game state storage
game_rooms = {}
connected_players = {}
player_sessions = {}

# Cleanup settings
CLEANUP_INTERVAL = 30
PLAYER_TIMEOUT = 60

@app.route("/ping", methods=["POST"])
def ping():
    data = request.json
    player_id = data.get('player_id')
    
    if player_id in player_sessions:
        player_sessions[player_id]['last_seen'] = time.time()
        return {"status": "ok"}, 200
    return {"error": "Invalid player ID"}, 400

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    name = data.get('name', 'Player')
    
    player_id = str(uuid.uuid4())
    player_sessions[player_id] = {
        'name': name,
        'last_seen': time.time(),
        'room_id': None
    }
    return {"player_id": player_id}, 200

@app.route("/create", methods=["POST"])
def create_room():
    data = request.json
    player_id = data.get('player_id')
    
    if player_id not in player_sessions:
        return {"error": "Invalid player ID"}, 400
    
    room_id = str(uuid.uuid4())
    game_rooms[room_id] = {
        'players': [player_id],
        'host': player_id,
        'state': None,
        'last_active': time.time()
    }
    
    player_sessions[player_id]['room_id'] = room_id
    return {"room_id": room_id}, 200

@app.route("/join", methods=["POST"])
def join_room():
    data = request.json
    player_id = data.get('player_id')
    room_id = data.get('room_id')
    
    if player_id not in player_sessions:
        return {"error": "Invalid player ID"}, 400
    
    if room_id not in game_rooms:
        return {"error": "Invalid room ID"}, 400
    
    if len(game_rooms[room_id]['players']) >= 2:
        return {"error": "Room full"}, 400
    
    game_rooms[room_id]['players'].append(player_id)
    player_sessions[player_id]['room_id'] = room_id
    game_rooms[room_id]['last_active'] = time.time()
    
    host_name = player_sessions[game_rooms[room_id]['host']]['name']
    return {"host_name": host_name}, 200

@app.route("/update", methods=["POST"])
def update_state():
    data = request.json
    player_id = data.get('player_id')
    room_id = data.get('room_id')
    game_state = data.get('state')
    
    if (player_id not in player_sessions or 
        room_id not in game_rooms or 
        player_id not in game_rooms[room_id]['players']):
        return {"error": "Invalid request"}, 400
    
    game_rooms[room_id]['state'] = game_state
    game_rooms[room_id]['last_active'] = time.time()
    return {"status": "updated"}, 200

@app.route("/state", methods=["POST"])
def get_state():
    data = request.json
    player_id = data.get('player_id')
    room_id = data.get('room_id')
    
    if (player_id not in player_sessions or 
        room_id not in game_rooms or 
        player_id not in game_rooms[room_id]['players']):
        return {"error": "Invalid request"}, 400
    
    return {"state": game_rooms[room_id]['state']}, 200

def cleanup():
    while True:
        current_time = time.time()
        
        # Clean up old players
        for pid in list(player_sessions.keys()):
            if current_time - player_sessions[pid]['last_seen'] > PLAYER_TIMEOUT:
                room_id = player_sessions[pid]['room_id']
                if room_id and room_id in game_rooms:
                    game_rooms[room_id]['players'].remove(pid)
                    if not game_rooms[room_id]['players']:
                        del game_rooms[room_id]
                del player_sessions[pid]
        
        # Clean up old rooms
        for rid in list(game_rooms.keys()):
            if current_time - game_rooms[rid]['last_active'] > PLAYER_TIMEOUT * 2:
                del game_rooms[rid]
        
        time.sleep(CLEANUP_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=cleanup, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
