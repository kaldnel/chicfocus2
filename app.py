import os
import json
import datetime
import threading
import time
import logging
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Load environment variables from file in development
if os.path.exists('render.env') and not os.environ.get('RENDER'):
    with open('render.env') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chicfocus_secret_key')

# Single SocketIO configuration that works in both environments
# Keep ping interval short to prevent disconnections
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',  # Explicitly set this for Windows
    logger=True,
    engineio_logger=True,
    ping_timeout=120,  # Longer timeout
    ping_interval=10   # More frequent pings to keep connection alive
)

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
                    "sessions": []
                },
                "4keni": {
                    "points": 0, 
                    "sessions": []
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
        
        # Send confirmation of connection first
        emit('server_connected', {"status": "Connected to server"})
        
        # Calculate and add the necessary data
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
        
        # Send the data to the connecting client only
        emit('full_update', data)
    except Exception as e:
        logger.error("Error in connect handler: %s", str(e))
        emit('error', {'message': f'Connection error: {str(e)}'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected: %s", request.sid)
    
    # Let's check if this was an unexpected disconnect
    # In production, you might want to store this info for debugging
    if request.sid in active_timers:
        logger.warning("Client disconnected with active timer: %s", request.sid)
    
    # You could also notify other clients about the disconnect if needed
    # socketio.emit('user_disconnected', {'sid': request.sid})

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
        
    if 'current_user' not in json_data or not json_data['current_user']:
        print("Error: Missing current_user in start_chicken data")
        emit('error', {'message': 'Missing current user data'})
        return
    
    try:
        user = json_data['user']
        current_user = json_data['current_user']
        task_name = json_data['task_name']
        tier = int(json_data['tier'])
        
        # Check that user is only controlling their own side
        if user != current_user:
            print(f"Error: User {current_user} tried to control {user}'s timer")
            emit('error', {'message': f'You can only control your own timer'})
            return
        
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
            emit('error', {'message': 'Daily limit reached (5 chickens per day)'})
            return
        
        # Create a new chicken session
        session = {
            "id": str(time.time()),  # Simple ID based on timestamp
            "user": user,
            "task_name": task_name,
            "tier": tier,
            "timestamp": datetime.datetime.now().isoformat(),
            "completed": False
        }
        
        # Add to user's sessions
        data["users"][user]["sessions"].append(session)
        save_data(data)
        
        # Emit chicken_started event to all clients
        socketio.emit('chicken_started', {
            'user': user,
            'task_name': task_name,
            'tier': tier
        })
        
        # Start timer
        duration = CHICKEN_TYPES[tier]["time"] * 60  # Convert minutes to seconds
        timer_thread = threading.Thread(target=timer_worker, args=(user, duration))
        timer_thread.daemon = True
        timer_thread.start()
        
    except Exception as e:
        print(f"Error in start_chicken: {str(e)}")
        emit('error', {'message': f'Error starting chicken: {str(e)}'})

@socketio.on('pause_timer')
def handle_pause_timer(json_data):
    user = json_data.get('user')
    current_user = json_data.get('current_user')
    
    # Check that user is only controlling their own side
    if user != current_user:
        print(f"Error: User {current_user} tried to control {user}'s timer")
        emit('error', {'message': f'You can only control your own timer'})
        return
        
    if user in active_timers:
        socketio.emit('timer_paused', {'user': user})

@socketio.on('resume_timer')
def handle_resume_timer(json_data):
    user = json_data.get('user')
    current_user = json_data.get('current_user')
    is_break = json_data.get('is_break', False)
    
    # Check that user is only controlling their own side
    if user != current_user:
        print(f"Error: User {current_user} tried to control {user}'s timer")
        emit('error', {'message': f'You can only control your own timer'})
        return
        
    if user in active_timers:
        socketio.emit('timer_resumed', {'user': user, 'is_break': is_break})

@socketio.on('reset_timer')
def handle_reset_timer(json_data):
    user = json_data.get('user')
    current_user = json_data.get('current_user')
    
    # Check that user is only controlling their own side
    if user != current_user:
        print(f"Error: User {current_user} tried to control {user}'s timer")
        emit('error', {'message': f'You can only control your own timer'})
        return
        
    if user in active_timers:
        active_timers[user]['stop'] = True
        socketio.emit('timer_reset', {'user': user})

@socketio.on('timer_complete')
def handle_timer_complete(json_data):
    user = json_data.get('user')
    is_break = json_data.get('is_break', False)
    
    try:
        if is_break:
            # Break complete, redirect to main timer reset
            socketio.emit('timer_reset', {'user': user})
            return
        
        data = load_data()
        
        # Find the active session for this user
        active_session = None
        for session in data["users"][user]["sessions"]:
            if not session.get("completed", False):
                active_session = session
                break
                
        if active_session:
            # Mark the session as completed
            active_session["completed"] = True
            active_session["completion_time"] = datetime.datetime.now().isoformat()
            save_data(data)
            
            # Start a break timer (5 minutes)
            break_duration = 5 * 60  # 5 minutes in seconds
            socketio.emit('break_started', {'user': user})
            
            timer_thread = threading.Thread(target=timer_worker, args=(user, break_duration, True))
            timer_thread.daemon = True
            timer_thread.start()
            
            # Calculate updated data
            for u in USERS:
                points = calculate_points(u, data)
                data["users"][u]["current_points"] = points
                
                # Get today's sessions
                sessions_today = len([s for s in data["users"][u]["sessions"] 
                                   if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
                data["users"][u]["sessions_today"] = sessions_today
            
            # Calculate days remaining
            cycle_start = datetime.datetime.fromisoformat(data["cycle_start"])
            days_remaining = 7 - (datetime.datetime.now() - cycle_start).days
            data["days_remaining"] = max(0, days_remaining)
            
            # Send a full update to the client
            socketio.emit('full_update', data)
            
            # Emit session_complete event
            socketio.emit('session_complete', {'user': user})
    except Exception as e:
        print(f"Error in timer_complete: {str(e)}")
        emit('error', {'message': f'Error completing timer: {str(e)}'})

@socketio.on('end_cycle')
def handle_end_cycle():
    data = load_data()
    end_cycle(data)

def end_cycle(data):
    """End the current 7-day cycle and determine a winner"""
    # Calculate points for each user
    luu_points = calculate_points('luu', data)
    keni_points = calculate_points('4keni', data)
    
    # Determine winner
    if luu_points > keni_points:
        winner = 'luu'
    elif keni_points > luu_points:
        winner = '4keni'
    else:
        winner = 'Tie'
        
    # Update data
    data["winner"] = winner
    data["cycle_start"] = datetime.datetime.now().isoformat()
    
    # Reset points
    for user in USERS:
        data["users"][user]["points"] = 0
    
    save_data(data)
    
    # Emit cycle_complete event
    socketio.emit('cycle_complete', {'winner': winner})
    
    # Calculate updated data
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
    
    # Send a full update to the client
    socketio.emit('full_update', data)

if __name__ == '__main__':
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Get port from environment variable (for Render.com) or use default
    port = int(os.environ.get('PORT', 5000))
    
    # In development, run with socketio.run
    # In production (Render), gunicorn will handle this
    if os.environ.get('RENDER', False):
        # Let gunicorn handle the app
        pass
    else:
        # Development mode
        socketio.run(app, host='0.0.0.0', port=port) 