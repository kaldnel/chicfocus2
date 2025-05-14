from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import json
import datetime
import threading
import time
import os
import logging
import uuid

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chicfocus_secret_key')
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   logger=True,
                   engineio_logger=True,
                   ping_timeout=60,
                   ping_interval=25)

# Data storage
DATA_FILE = 'data/chickens.json'
USERS = ['luu', '4keni']

# Chicken types configuration
CHICKEN_TYPES = {
    1: {"label": "Light Chicken", "intensity": "casual", "time": 15, "points": 1},
    2: {"label": "Medium Chicken", "intensity": "normal", "time": 30, "points": 2},
    3: {"label": "Heavy Chicken", "intensity": "deep focus", "time": 45, "points": 3}
}

# Active timers for each user
active_timers = {}

def load_data():
    """Load existing data or create new structure"""
    logger.debug("Loading data from %s", DATA_FILE)
    os.makedirs('data', exist_ok=True)
    
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    else:
        logger.info("Data file not found, creating new data structure")
        return {
            "users": {
                "luu": {
                    "points": 0, 
                    "sessions": [],
                    "folders": [
                        {
                            "id": "luu_default",
                            "name": "Default",
                            "emoji": "📁",
                            "parent_id": None,
                            "chickens": []
                        }
                    ]
                },
                "4keni": {
                    "points": 0, 
                    "sessions": [],
                    "folders": [
                        {
                            "id": "4keni_default",
                            "name": "Default",
                            "emoji": "📁",
                            "parent_id": None,
                            "chickens": []
                        }
                    ]
                }
            },
            "cycle_start": datetime.datetime.now().isoformat(),
            "winner": None
        }

def save_data(data):
    """Save data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def calculate_session_points(user, session, sessions, session_index=None):
    """Calculate points for a single session with bonuses/penalties"""
    if not session.get("completed", False):
        return 0
    
    base_points = CHICKEN_TYPES[session["tier"]]["points"]
    
    if session_index is None:
        session_index = sessions.index(session)
    
    # Check for repeat penalty (same task 3 times in a row)
    if session_index >= 2:
        last_three = sessions[session_index-2:session_index+1]
        if all(s["task_name"] == session["task_name"] for s in last_three):
            base_points -= 1
    
    # Check for switch bonus (switch tasks within 3 chickens)
    if session_index >= 2:
        last_three = sessions[session_index-2:session_index+1]
        task_names = [s["task_name"] for s in last_three]
        if len(set(task_names)) > 1:
            base_points += 2
    
    # Check for boss streak (3+ tier 3 chickens in a row)
    if session["tier"] == 3 and session_index >= 2:
        tier_3_streak = 1
        for j in range(session_index-1, -1, -1):
            if sessions[j]["tier"] == 3:
                tier_3_streak += 1
            else:
                break
        
        if tier_3_streak >= 3:
            base_points += 3
    
    return max(0, base_points)

def calculate_points(user, data):
    """Calculate total points for a user with bonuses/penalties"""
    sessions = data["users"][user]["sessions"]
    total_points = 0
    
    for i, session in enumerate(sessions):
        if not session.get("completed", False):
            continue
        points = calculate_session_points(user, session, sessions, i)
        total_points += points
    
    return total_points

def timer_worker(user, duration, is_break=False):
    """Run timer in separate thread"""
    if user in active_timers:
        active_timers[user]['stop'] = True
    
    active_timers[user] = {'stop': False, 'remaining': duration}
    
    while duration > 0 and not active_timers[user]['stop']:
        minutes, seconds = divmod(duration, 60)
        socketio.emit('timer_update', {
            'user': user,
            'time': f"{minutes:02d}:{seconds:02d}",
            'remaining': duration,
            'is_break': is_break
        })
        
        time.sleep(1)
        duration -= 1
        active_timers[user]['remaining'] = duration
    
    if not active_timers[user]['stop']:
        socketio.emit('timer_complete', {
            'user': user,
            'is_break': is_break
        })

@app.route('/')
def index():
    return render_template('index.html', users=USERS, chicken_types=CHICKEN_TYPES)

@app.route('/status')
def status():
    logger.debug("Status endpoint called")
    try:
        data = load_data()
        return jsonify({"status": "ok", "users": USERS, "chicken_types": CHICKEN_TYPES})
    except Exception as e:
        logger.error("Error in status: %s", str(e))
        return jsonify({"status": "error", "message": str(e)})

@app.route('/debug/emit/<event>')
def debug_emit(event):
    logger.debug("Debug emit endpoint called for event: %s", event)
    try:
        socketio.emit(event, {"message": f"Debug event {event}"})
        return jsonify({"status": "ok", "message": f"Emitted {event}"})
    except Exception as e:
        logger.error("Error in debug_emit: %s", str(e))
        return jsonify({"status": "error", "message": str(e)})

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected: %s", request.sid)
    try:
        data = load_data()
        
        # Check if 7-day cycle has passed
        cycle_start = datetime.datetime.fromisoformat(data["cycle_start"])
        if (datetime.datetime.now() - cycle_start).days >= 7:
            end_cycle(data)
        
        emit_full_update(data)
        
        # Send confirmation of connection
        emit('server_connected', {"status": "Connected to server"})
    except Exception as e:
        logger.error("Error in connect handler: %s", str(e))
        emit('error', {'message': f'Connection error: {str(e)}'})

@socketio.on('start_chicken')
def handle_start_chicken(json_data):
    print(f"Received start_chicken event with data: {json_data}")
    
    # Validate input data
    if 'user' not in json_data or not json_data['user']:
        print("Error: Missing user in start_chicken data")
        emit('error', {'message': 'Missing user data'})
        return
        
    if 'task_name' not in json_data or not json_data['task_name']:
        print("Error: Missing task_name in start_chicken data")
        emit('error', {'message': 'Missing task name'})
        return
        
    if 'tier' not in json_data:
        print("Error: Missing tier in start_chicken data")
        emit('error', {'message': 'Missing tier data'})
        return
    
    try:
        user = json_data['user']
        task_name = json_data['task_name']
        tier = int(json_data['tier'])
        
        if user not in USERS:
            print(f"Error: Invalid user '{user}'")
            emit('error', {'message': f'Invalid user: {user}'})
            return
            
        if tier not in CHICKEN_TYPES:
            print(f"Error: Invalid tier '{tier}'")
            emit('error', {'message': f'Invalid tier: {tier}'})
            return
        
        data = load_data()
        
        # Check daily limit
        sessions_today = len([s for s in data["users"][user]["sessions"] 
                          if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
        
        if sessions_today >= 5:
            print(f"Error: Daily limit reached for user '{user}'")
            emit('error', {'message': 'Daily limit of 5 chickens reached!'})
            return
        
        # Create session object
        session = {
            "task_name": task_name,
            "tier": tier,
            "timestamp": datetime.datetime.now().isoformat(),
            "completed": False
        }
        
        # Start timer
        duration = CHICKEN_TYPES[tier]["time"] * 60
        threading.Thread(target=timer_worker, args=(user, duration), daemon=True).start()
        
        # Store session temporarily (will be completed when timer ends)
        if user not in active_timers:
            active_timers[user] = {}
        active_timers[user]['current_session'] = session
        
        print(f"Starting chicken for '{user}': {task_name} (Tier {tier})")
        socketio.emit('chicken_started', {
            'user': user,
            'task_name': task_name,
            'tier': tier,
            'duration': duration
        })
        
    except Exception as e:
        print(f"Error in start_chicken: {str(e)}")
        emit('error', {'message': f'Server error: {str(e)}'})

@socketio.on('pause_timer')
def handle_pause_timer(json_data):
    user = json_data['user']
    if user in active_timers:
        active_timers[user]['stop'] = True
        socketio.emit('timer_paused', {'user': user})

@socketio.on('resume_timer')
def handle_resume_timer(json_data):
    user = json_data['user']
    if user in active_timers and 'remaining' in active_timers[user]:
        duration = active_timers[user]['remaining']
        is_break = json_data.get('is_break', False)
        threading.Thread(target=timer_worker, args=(user, duration, is_break), daemon=True).start()
        socketio.emit('timer_resumed', {'user': user})

@socketio.on('reset_timer')
def handle_reset_timer(json_data):
    user = json_data['user']
    if user in active_timers:
        active_timers[user]['stop'] = True
        if 'current_session' in active_timers[user]:
            del active_timers[user]['current_session']
    
    socketio.emit('timer_reset', {'user': user})

@socketio.on('timer_complete')
def handle_timer_complete(json_data):
    user = json_data['user']
    is_break = json_data.get('is_break', False)
    
    if not is_break:
        # Complete chicken, start break
        data = load_data()
        session = active_timers[user]['current_session']
        session['completed'] = True
        
        # Add session to sessions list
        data["users"][user]["sessions"].append(session)
        
        # Create a chicken object with ID
        chicken_id = f"{user}_chicken_{str(uuid.uuid4())[:8]}"
        new_chicken = {
            "id": chicken_id,
            "task_name": session["task_name"],
            "tier": session["tier"],
            "timestamp": session["timestamp"],
            "completed": True
        }
        
        # Find default folder
        default_folder = None
        for folder in data["users"][user]["folders"]:
            if folder["id"] == f"{user}_default":
                default_folder = folder
                break
                
        if not default_folder:
            # Create default folder if doesn't exist
            default_folder = {
                "id": f"{user}_default",
                "name": "Default",
                "emoji": "📁",
                "parent_id": None,
                "chickens": []
            }
            data["users"][user]["folders"].append(default_folder)
            
        # Add chicken to default folder
        default_folder["chickens"].append(new_chicken)
        save_data(data)
        
        # Start 5-minute break
        threading.Thread(target=timer_worker, args=(user, 300, True), daemon=True).start()
        
        socketio.emit('break_started', {'user': user})
        socketio.emit('chicken_created', {'user': user, 'chicken': new_chicken})
        emit_full_update(data)
    else:
        # Break complete, session fully done
        socketio.emit('session_complete', {'user': user})

@socketio.on('end_cycle')
def handle_end_cycle():
    data = load_data()
    end_cycle(data)

def end_cycle(data):
    """End current 7-day cycle and determine winner"""
    luu_points = calculate_points("luu", data)
    keni_points = calculate_points("4keni", data)
    
    if luu_points > keni_points:
        winner = "luu"
    elif keni_points > luu_points:
        winner = "4keni"
    else:
        winner = "Tie"
    
    # Reset cycle
    data = {
        "users": {
            "luu": {"points": 0, "sessions": []},
            "4keni": {"points": 0, "sessions": []}
        },
        "cycle_start": datetime.datetime.now().isoformat(),
        "winner": winner
    }
    save_data(data)
    
    socketio.emit('cycle_complete', {
        'winner': winner,
        'luu_points': luu_points,
        'keni_points': keni_points
    })
    
    emit_full_update(data)

def emit_full_update(data):
    """Emit complete data update to all clients"""
    # Calculate points for display
    for user in USERS:
        points = calculate_points(user, data)
        data["users"][user]["current_points"] = points
        
        # Get today's sessions
        sessions_today = len([s for s in data["users"][user]["sessions"] 
                            if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
        data["users"][user]["sessions_today"] = sessions_today
    
    # Calculate days remaining
    cycle_start = datetime.datetime.fromisoformat(data["cycle_start"])
    days_remaining = 7 - (datetime.datetime.now() - cycle_start).days
    data["days_remaining"] = max(0, days_remaining)
    
    socketio.emit('full_update', data)

# Add folder management routes and socket events
@socketio.on('create_folder')
def handle_create_folder(json_data):
    logger.info("create_folder request: %s", json_data)
    try:
        user = json_data.get('user')
        folder_name = json_data.get('name', 'New Folder')
        emoji = json_data.get('emoji', '')
        parent_id = json_data.get('parent_id', None)
        
        if not user or user not in USERS:
            emit('error', {'message': 'Invalid user'})
            return
            
        data = load_data()
        
        # Create a new folder ID
        folder_id = f"{user}_{str(uuid.uuid4())[:8]}"
        
        # Create the new folder
        new_folder = {
            "id": folder_id,
            "name": folder_name,
            "emoji": emoji,
            "parent_id": parent_id,
            "chickens": []
        }
        
        # Add to user's folders
        data["users"][user]["folders"].append(new_folder)
        save_data(data)
        
        # Send updated folders to clients
        socketio.emit('folders_updated', {"user": user, "folders": data["users"][user]["folders"]})
        
    except Exception as e:
        logger.error("Error creating folder: %s", str(e))
        emit('error', {'message': f'Error creating folder: {str(e)}'})

@socketio.on('edit_folder')
def handle_edit_folder(json_data):
    logger.info("edit_folder request: %s", json_data)
    try:
        user = json_data.get('user')
        folder_id = json_data.get('folder_id')
        new_name = json_data.get('name')
        new_emoji = json_data.get('emoji')
        new_parent_id = json_data.get('parent_id')
        
        if not user or user not in USERS:
            emit('error', {'message': 'Invalid user'})
            return
            
        if not folder_id:
            emit('error', {'message': 'Folder ID required'})
            return
            
        data = load_data()
        
        # Find and update the folder
        folder_found = False
        for folder in data["users"][user]["folders"]:
            if folder["id"] == folder_id:
                if new_name is not None:
                    folder["name"] = new_name
                if new_emoji is not None:
                    folder["emoji"] = new_emoji
                if new_parent_id is not None:
                    # Check for circular references
                    if new_parent_id == folder_id:
                        emit('error', {'message': 'Cannot set a folder as its own parent'})
                        return
                    
                    # Check if parent exists
                    parent_exists = False
                    for potential_parent in data["users"][user]["folders"]:
                        if potential_parent["id"] == new_parent_id:
                            parent_exists = True
                            break
                    
                    if parent_exists or new_parent_id is None:
                        folder["parent_id"] = new_parent_id
                    else:
                        emit('error', {'message': 'Parent folder does not exist'})
                        return
                
                folder_found = True
                break
        
        if not folder_found:
            emit('error', {'message': 'Folder not found'})
            return
            
        save_data(data)
        
        # Send updated folders to clients
        socketio.emit('folders_updated', {"user": user, "folders": data["users"][user]["folders"]})
        
    except Exception as e:
        logger.error("Error editing folder: %s", str(e))
        emit('error', {'message': f'Error editing folder: {str(e)}'})

@socketio.on('delete_folder')
def handle_delete_folder(json_data):
    logger.info("delete_folder request: %s", json_data)
    try:
        user = json_data.get('user')
        folder_id = json_data.get('folder_id')
        
        if not user or user not in USERS:
            emit('error', {'message': 'Invalid user'})
            return
            
        if not folder_id:
            emit('error', {'message': 'Folder ID required'})
            return
            
        # Don't allow deleting the default folder
        if folder_id in [f"{user}_default"]:
            emit('error', {'message': 'Cannot delete the default folder'})
            return
            
        data = load_data()
        
        # Find the folder index
        folder_index = None
        for i, folder in enumerate(data["users"][user]["folders"]):
            if folder["id"] == folder_id:
                folder_index = i
                break
        
        if folder_index is None:
            emit('error', {'message': 'Folder not found'})
            return
        
        # Get the chickens from this folder before removing it
        chickens_to_move = data["users"][user]["folders"][folder_index]["chickens"]
        
        # Find the default folder
        default_folder = None
        for folder in data["users"][user]["folders"]:
            if folder["id"] == f"{user}_default":
                default_folder = folder
                break
        
        if default_folder is None:
            # Create a default folder if it doesn't exist
            default_folder = {
                "id": f"{user}_default",
                "name": "Default",
                "emoji": "📁",
                "parent_id": None,
                "chickens": []
            }
            data["users"][user]["folders"].append(default_folder)
        
        # Move chickens to default folder
        default_folder["chickens"].extend(chickens_to_move)
        
        # Update any subfolders to point to parent's parent
        parent_id = data["users"][user]["folders"][folder_index]["parent_id"]
        for subfolder in data["users"][user]["folders"]:
            if subfolder["parent_id"] == folder_id:
                subfolder["parent_id"] = parent_id
        
        # Remove the folder
        data["users"][user]["folders"].pop(folder_index)
        save_data(data)
        
        # Send updated folders to clients
        socketio.emit('folders_updated', {"user": user, "folders": data["users"][user]["folders"]})
        
    except Exception as e:
        logger.error("Error deleting folder: %s", str(e))
        emit('error', {'message': f'Error deleting folder: {str(e)}'})

@socketio.on('move_chicken')
def handle_move_chicken(json_data):
    logger.info("move_chicken request: %s", json_data)
    try:
        user = json_data.get('user')
        chicken_id = json_data.get('chicken_id')
        target_folder_id = json_data.get('target_folder_id')
        source_folder_id = json_data.get('source_folder_id')
        
        if not user or user not in USERS:
            emit('error', {'message': 'Invalid user'})
            return
            
        if not chicken_id:
            emit('error', {'message': 'Chicken ID required'})
            return
            
        if not target_folder_id:
            emit('error', {'message': 'Target folder ID required'})
            return
            
        data = load_data()
        
        # Find the source folder
        source_folder = None
        if source_folder_id:
            for folder in data["users"][user]["folders"]:
                if folder["id"] == source_folder_id:
                    source_folder = folder
                    break
        else:
            # If no source folder specified, search all folders
            for folder in data["users"][user]["folders"]:
                for chicken in folder["chickens"]:
                    if chicken["id"] == chicken_id:
                        source_folder = folder
                        break
                if source_folder:
                    break
        
        if not source_folder:
            emit('error', {'message': 'Source folder not found or chicken not found'})
            return
            
        # Find the target folder
        target_folder = None
        for folder in data["users"][user]["folders"]:
            if folder["id"] == target_folder_id:
                target_folder = folder
                break
                
        if not target_folder:
            emit('error', {'message': 'Target folder not found'})
            return
            
        # Find and remove the chicken from source folder
        chicken = None
        for i, chk in enumerate(source_folder["chickens"]):
            if chk["id"] == chicken_id:
                chicken = source_folder["chickens"].pop(i)
                break
                
        if not chicken:
            emit('error', {'message': 'Chicken not found in source folder'})
            return
            
        # Add chicken to target folder
        target_folder["chickens"].append(chicken)
        save_data(data)
        
        # Send updated folders to clients
        socketio.emit('folders_updated', {"user": user, "folders": data["users"][user]["folders"]})
        
    except Exception as e:
        logger.error("Error moving chicken: %s", str(e))
        emit('error', {'message': f'Error moving chicken: {str(e)}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, 
                host='0.0.0.0', 
                port=port,
                debug=False,
                use_reloader=False) 