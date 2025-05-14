from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import json
import datetime
import threading
import time
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chicfocus_secret_key')
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
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
                "luu": {"points": 0, "sessions": []},
                "4keni": {"points": 0, "sessions": []}
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
        emit('chicken_started', {
            'user': user,
            'task_name': task_name,
            'tier': tier,
            'duration': duration
        }, broadcast=True)
        
    except Exception as e:
        print(f"Error in start_chicken: {str(e)}")
        emit('error', {'message': f'Server error: {str(e)}'})

@socketio.on('pause_timer')
def handle_pause_timer(json_data):
    user = json_data['user']
    if user in active_timers:
        active_timers[user]['stop'] = True
        emit('timer_paused', {'user': user}, broadcast=True)

@socketio.on('resume_timer')
def handle_resume_timer(json_data):
    user = json_data['user']
    if user in active_timers and 'remaining' in active_timers[user]:
        duration = active_timers[user]['remaining']
        is_break = json_data.get('is_break', False)
        threading.Thread(target=timer_worker, args=(user, duration, is_break), daemon=True).start()
        emit('timer_resumed', {'user': user}, broadcast=True)

@socketio.on('reset_timer')
def handle_reset_timer(json_data):
    user = json_data['user']
    if user in active_timers:
        active_timers[user]['stop'] = True
        if 'current_session' in active_timers[user]:
            del active_timers[user]['current_session']
    
    emit('timer_reset', {'user': user}, broadcast=True)

@socketio.on('timer_complete')
def handle_timer_complete(json_data):
    user = json_data['user']
    is_break = json_data.get('is_break', False)
    
    if not is_break:
        # Complete chicken, start break
        data = load_data()
        session = active_timers[user]['current_session']
        session['completed'] = True
        
        data["users"][user]["sessions"].append(session)
        save_data(data)
        
        # Start 5-minute break
        threading.Thread(target=timer_worker, args=(user, 300, True), daemon=True).start()
        
        emit('break_started', {'user': user}, broadcast=True)
        emit_full_update(data)
    else:
        # Break complete, session fully done
        emit('session_complete', {'user': user}, broadcast=True)

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
    }, broadcast=True)
    
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
    
    socketio.emit('full_update', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, 
                host='0.0.0.0', 
                port=port,
                debug=False,
                use_reloader=False) 