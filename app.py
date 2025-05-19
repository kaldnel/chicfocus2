import os
import json
import datetime
import threading
import time
import logging
import eventlet
import psutil
import gc
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import random
from collections import deque
import uuid

# Set up logging with rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', maxBytes=1024*1024, backupCount=5)
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load environment variables from file in development
if os.path.exists('render.env') and not os.environ.get('RENDER'):
    with open('render.env') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chicfocus_secret_key')

# Socket.IO configuration with improved settings for 24/7 operation
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    ping_timeout=300,  # Increased timeout
    ping_interval=30,  # Reduced ping frequency
    max_http_buffer_size=1e8,  # Increased buffer size
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1000,
    reconnection_delay_max=5000
)

# Data storage
DATA_FILE = 'data/chickens.json'
BARNS_FILE = 'data/barns.json'
USERS = ['luu', '4keni']

def load_barns():
    """Load the barns data file, or initialize if missing/corrupt."""
    if not os.path.exists(BARNS_FILE):
        # Initialize structure with default barns
        barns = {
            "users": {
                u: {
                    "barns": [
                        {"id": "default", "name": "Main Barn", "description": "Your main focus barn"},
                        {"id": "special", "name": "Special Projects", "description": "For important tasks"}
                    ]
                } for u in USERS
            }
        }
        save_barns(barns)
        return barns
    try:
        with open(BARNS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        # If file is corrupt, reinitialize
        os.rename(BARNS_FILE, BARNS_FILE + '.bak')
        return load_barns()

def save_barns(barns):
    """Save the barns data file."""
    with open(BARNS_FILE, 'w') as f:
        json.dump(barns, f, indent=2, default=str)

def load_data():
    """Load the main data file, or initialize if missing/corrupt."""
    if not os.path.exists(DATA_FILE):
        # Initialize structure
        data = {
            "users": {u: {"points": 0, "sessions": [], "stats": {
                "streak": 0,
                "momentum_multiplier": 1.0,
                "mystery_egg_used_date": None,
                "mystery_egg_effect": None,
                "lifetime_tier3_count": 0,
                "longest_streak": 0,
                "weekly_tier3_count": 0,
                "weekly_chickens": 0,
                "unlocked_skins": ["default"],
                "current_skin": "default",
                "unlocked_themes": ["default"],
                "current_theme": "default",
                "achievements": []
            }} for u in USERS},
            "cycle_start": datetime.datetime.now().isoformat(),
            "winner": None,
            "weekly_chaos_chicken": {
                "offered": False,
                "offered_to": None,
                "offered_date": None,
                "completed": False,
                "completion_date": None,
                "completed_by": None,
                "challenge_type": None,
                "challenge_params": None
            }
        }
        save_data(data)
        return data
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        # If file is corrupt, reinitialize
        os.rename(DATA_FILE, DATA_FILE + '.bak')
        return load_data()

def save_data(data):
    """Save the main data file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

# Livestock types configuration
CHICKEN_TYPES = {
    0: {"label": "Test Animal (5 sec)", "intensity": "quick test", "time": 0.08, "points": 0},  # 5 seconds for testing
    1: {"label": "Chicken", "intensity": "casual", "time": 15, "points": 1},
    2: {"label": "Goat", "intensity": "light", "time": 25, "points": 2},
    3: {"label": "Sheep", "intensity": "moderate", "time": 30, "points": 3},
    4: {"label": "Pig", "intensity": "focused", "time": 45, "points": 4},
    5: {"label": "Cow", "intensity": "deep focus", "time": 60, "points": 5},
    6: {"label": "Horse", "intensity": "intense focus", "time": 90, "points": 6}
}

# Active timers for each user
active_timers = {}

# Track current session per user (in memory)
current_sessions = {user: None for user in USERS}

AVAILABLE_ANIMALS = [
    {"name": "Chicken", "duration": 15, "base_price": [5, 10]},
    {"name": "Goat", "duration": 25, "base_price": [12, 20]},
    {"name": "Sheep", "duration": 30, "base_price": [18, 28]},
    {"name": "Pig", "duration": 45, "base_price": [25, 40]},
    {"name": "Cow", "duration": 60, "base_price": [40, 60]},
    {"name": "Horse", "duration": 90, "base_price": [60, 100]}
]

# --- Market Event System ---
MARKET_EVENTS = deque(maxlen=10)  # Store last 10 events
CURRENT_EVENT = None
EVENT_EFFECTS = {
    'Chicken': [
        {'name': 'Bird Flu Scare', 'emoji': '🐔', 'effect': -0.3, 'desc': 'Chicken prices drop 30%'},
        {'name': 'Egg Boom', 'emoji': '🥚', 'effect': 0.15, 'desc': 'Chicken prices rise 15%'}
    ],
    'Goat': [
        {'name': 'Goat Yoga Trend', 'emoji': '🧘‍♂️', 'effect': 0.2, 'desc': 'Goat prices up 20%'},
        {'name': 'Milk Surplus', 'emoji': '🥛', 'effect': -0.2, 'desc': 'Goat prices drop 20%'}
    ],
    'Sheep': [
        {'name': 'Wool Rush', 'emoji': '🧶', 'effect': 0.25, 'desc': 'Sheep prices up 25%'},
        {'name': 'Shearing Scandal', 'emoji': '✂️', 'effect': -0.2, 'desc': 'Sheep prices drop 20%'}
    ],
    'Pig': [
        {'name': 'Bacon Craze', 'emoji': '🥓', 'effect': 0.2, 'desc': 'Pig demand spikes +20%'},
        {'name': 'Swine Flu', 'emoji': '🤒', 'effect': -0.25, 'desc': 'Pig prices drop 25%'}
    ],
    'Cow': [
        {'name': 'Steak Festival', 'emoji': '🥩', 'effect': 0.18, 'desc': 'Cow prices up 18%'},
        {'name': 'Dairy Dump', 'emoji': '🧀', 'effect': -0.15, 'desc': 'Cow prices drop 15%'}
    ],
    'Horse': [
        {'name': 'Race Day', 'emoji': '🏇', 'effect': 0.22, 'desc': 'Horse prices up 22%'},
        {'name': 'Stable Outbreak', 'emoji': '💀', 'effect': -0.2, 'desc': 'Horse prices drop 20%'}
    ]
}

# Store event-affected points for chart annotation
EVENT_POINTS = deque(maxlen=10)

# --- Market Feed System ---
MARKET_FEED = deque(maxlen=30)  # Last 30 feed items

def add_fake_trade_to_feed():
    users = ['luu', '4keni', 'guest']
    animals = ['Chicken', 'Goat', 'Sheep', 'Pig', 'Cow', 'Horse']
    emojis = {'Chicken': '🐔', 'Goat': '🐐', 'Sheep': '🐑', 'Pig': '🐖', 'Cow': '🐄', 'Horse': '🐎'}
    actions = [
        lambda u, a, p: f"<b>{u}</b> made <span class='neon-profit'>${p}</span> flipping {emojis[a]} <b>{a}</b> 💸",
        lambda u, a, p: f"<b>{u}</b> scored a <span class='neon-profit'>${p}</span> profit on {emojis[a]} <b>{a}</b>!",
        lambda u, a, p: f"{emojis[a]} <b>{a}</b> market is heating up! <b>{u}</b> just cashed in <span class='neon-profit'>${p}</span>!"
    ]
    u = random.choice(users)
    a = random.choice(animals)
    p = random.randint(50, 500)
    msg = random.choice(actions)(u, a, p)
    MARKET_FEED.appendleft({
        'id': str(uuid.uuid4()),
        'type': 'trade',
        'msg': msg,
        'time': datetime.datetime.now().isoformat()
    })

def add_event_to_feed(event):
    msg = f"<span class='neon-event'>{event['emoji']} {event['name']}</span> – {event['desc']}"
    MARKET_FEED.appendleft({
        'id': str(uuid.uuid4()),
        'type': 'event',
        'msg': msg,
        'time': event['time']
    })

# Periodically add fake trades for demo
threading.Thread(target=lambda: [time.sleep(random.randint(20, 40)) or add_fake_trade_to_feed() for _ in iter(int, 1)], daemon=True).start()

# Hook: when a new event is created, add to feed
def market_event_thread():
    global CURRENT_EVENT
    while True:
        # Wait 1-3 minutes between events
        time.sleep(random.randint(60, 180))
        animal = random.choice(list(EVENT_EFFECTS.keys()))
        event = random.choice(EVENT_EFFECTS[animal])
        event_time = datetime.datetime.now().isoformat()
        event_obj = {
            'animal': animal,
            'name': event['name'],
            'emoji': event['emoji'],
            'effect': event['effect'],
            'desc': event['desc'],
            'time': event_time
        }
        MARKET_EVENTS.appendleft(event_obj)
        CURRENT_EVENT = event_obj
        # Store for chart annotation
        EVENT_POINTS.append({'animal': animal, 'effect': event['effect'], 'time': event_time, 'desc': event['desc'], 'emoji': event['emoji']})
        # Add to feed
        add_event_to_feed(event_obj)
        # Event lasts for 1-2 minutes
        time.sleep(random.randint(60, 120))
        CURRENT_EVENT = None

def check_and_create_chaos_chicken(data):
    """Check if a weekly chaos chicken challenge should be created and offer it to a user."""
    # If a challenge is already offered or completed, don't create a new one
    if data["weekly_chaos_chicken"]["offered"] or data["weekly_chaos_chicken"]["completed"]:
        return data
        
    # Randomly select a user to offer the challenge to
    selected_user = random.choice(USERS)
    
    # Define possible challenge types
    challenge_types = [
        {
            "type": "speed_run",
            "params": {"time_limit": 30, "points": 10},
            "description": "Complete a 30-minute focus session in under 25 minutes"
        },
        {
            "type": "streak_master",
            "params": {"required_streak": 3, "points": 15},
            "description": "Complete 3 focus sessions in a row without breaks"
        },
        {
            "type": "tier_challenge",
            "params": {"required_tier": 3, "points": 20},
            "description": "Complete a Tier 3 focus session"
        }
    ]
    
    # Select a random challenge
    challenge = random.choice(challenge_types)
    
    # Update the weekly chaos chicken data
    data["weekly_chaos_chicken"] = {
        "offered": True,
        "offered_to": selected_user,
        "offered_date": datetime.datetime.now().isoformat(),
        "completed": False,
        "completion_date": None,
        "completed_by": None,
        "challenge_type": challenge["type"],
        "challenge_params": challenge["params"],
        "description": challenge["description"]
    }
    
    return data

@app.route('/')
def index():
    data = load_data()
    
    # Check for weekly chaos chicken
    data = check_and_create_chaos_chicken(data)
    save_data(data)
    
    return render_template('index.html', users=USERS, chicken_types=CHICKEN_TYPES)

@app.route('/status')
def status():
    logger.info("Status endpoint called")
    try:
        data = load_data()
        health = get_system_health()
        
        # Check critical components
        status = {
            "status": "ok",
            "users": USERS,
            "chicken_types": CHICKEN_TYPES,
            "system_health": health,
            "active_connections": len(socketio.server.manager.rooms.get('/', {}).get('', set())),
            "active_timers": len(active_timers),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Add warning if memory usage is high
        if health['memory_usage'] > 500:  # 500MB threshold
            status['warnings'] = ['High memory usage detected']
            cleanup_memory()
            
        return jsonify(status)
    except Exception as e:
        logger.error("Error in status: %s", str(e), exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }), 500

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
            data = end_cycle(data)
            save_data(data)
        
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
        
        # Send only to the client that just connected
        emit('full_update', data)
        
        # Cleanup memory after heavy operation
        cleanup_memory()
        
    except Exception as e:
        logger.error("Error in connect handler: %s", str(e), exc_info=True)
        emit('error', {'message': f'Connection error: {str(e)}'})
        # Attempt recovery
        try:
            cleanup_memory()
        except:
            pass

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected: %s", request.sid)
    
    try:
        # Clean up any active timers
        if request.sid in active_timers:
            logger.warning("Client disconnected with active timer: %s", request.sid)
            # Store the timer state for potential recovery
            timer_state = active_timers[request.sid]
            # Clean up the timer
            del active_timers[request.sid]
            
        # Notify other clients about the disconnect
        socketio.emit('user_disconnected', {
            'sid': request.sid,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
        # Cleanup memory
        cleanup_memory()
        
    except Exception as e:
        logger.error("Error in disconnect handler: %s", str(e), exc_info=True)

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
        emit('error', {'message': 'Missing animal type data'})
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
        chicken_name = json_data.get('chicken_name', '')  # New field for chicken name
        barn_id = json_data.get('barn_id', 'default')  # New field for barn ID
        
        # Validate barn_id
        barns = load_barns()
        if barn_id not in [b['id'] for b in barns['users'][user]['barns']]:
            emit('error', {'message': 'Invalid barn selected'})
            return
        
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
            print(f"Error: Invalid animal type '{tier}'")
            emit('error', {'message': f'Invalid animal type: {tier}'})
            return
        
        data = load_data()
        
        # Check daily limit
        sessions_today = len([s for s in data["users"][user]["sessions"] 
                          if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
        
        if sessions_today >= 5:
            emit('error', {'message': 'Daily limit reached (5 sessions per day)'})
            return
        
        # Get animal data from AVAILABLE_ANIMALS
        animal_idx = tier - 1
        animal_data = AVAILABLE_ANIMALS[animal_idx] if 0 <= animal_idx < len(AVAILABLE_ANIMALS) else None
        if not animal_data:
            emit('error', {'message': 'Invalid animal selection.'})
            return

        # Store current session for user
        current_sessions[user] = {
            'animal': animal_data,
            'task_name': task_name,
            'start_time': datetime.datetime.now().isoformat(),
            'chicken_name': chicken_name,
            'barn_id': barn_id
        }

        # Get current time for both timestamp and start_time
        current_time = datetime.datetime.now().isoformat()
        
        # Check if user has tier_upgrade mystery egg effect
        has_tier_upgrade = data["users"][user]["stats"].get("mystery_egg_effect") == "tier_upgrade"
        
        # Create a new session (for focus tracking)
        session = {
            "id": str(time.time()),
            "user": user,
            "task_name": task_name,
            "tier": tier,
            "animal": animal_data,
            "timestamp": current_sessions[user]['start_time'],
            "start_time": current_sessions[user]['start_time'],
            "pauses": [],
            "total_pause_duration": 0,
            "completed": False,
            "chicken_name": chicken_name,
            "barn_id": barn_id
        }
        
        # Apply tier upgrade if active
        if has_tier_upgrade and tier < 6:  # Can't upgrade beyond the highest tier
            # Mark the session with the original tier for reference
            session["original_tier"] = tier
            # Upgrade tier by 1 without changing time
            session["tier"] = tier + 1
            # Clear the effect after it's used
            data["users"][user]["stats"]["mystery_egg_effect"] = None
            
            # Get animal names for message
            original_animal = CHICKEN_TYPES[tier]["label"]
            upgraded_animal = CHICKEN_TYPES[tier + 1]["label"]
            
            # Notify the user
            socketio.emit('effect_used', {
                'user': user,
                'effect_type': 'tier_upgrade',
                'message': f'Tier Upgrade used! Your {original_animal} session is now a {upgraded_animal} with the same time.'
            })
            
            # Update tier for notifications and timer calculations
            tier = tier + 1
        
        # Check for SNIPE MODE (duel) opportunity
        partner = "luu" if user == "4keni" else "4keni"
        partner_recent_sessions = [s for s in data["users"][partner]["sessions"] 
                                if not s.get("completed", False) and s["tier"] == tier]
        
        # If partner has an active session of the same tier, check if it's within 2 minutes
        if partner_recent_sessions:
            partner_session = partner_recent_sessions[0]
            partner_start_time = datetime.datetime.fromisoformat(partner_session["timestamp"])
            current_time_dt = datetime.datetime.now()
            
            # If started within 2 minutes, create a duel
            if (current_time_dt - partner_start_time).total_seconds() < 120:  # 2 minutes = 120 seconds
                animal_type = CHICKEN_TYPES[tier]["label"]
                duel = {
                    "id": f"duel_{int(time.time())}",
                    "user1": partner,
                    "user2": user,
                    "tier": tier,
                    "start_time": current_time_dt.isoformat(),
                    "user1_completed": False,
                    "user2_completed": False,
                    "user1_time": None,
                    "user2_time": None
                }
                data.setdefault("active_duels", []).append(duel)
                
                # Mark sessions as part of a duel
                partner_session["duel_id"] = duel["id"]
                session["duel_id"] = duel["id"]
                
                # Notify both users of the duel
                socketio.emit('duel_started', {
                    'user1': partner,
                    'user2': user,
                    'tier': tier,
                    'animal_type': animal_type
                })
        
        # Add to user's sessions
        data["users"][user]["sessions"].append(session)
        save_data(data)
        
        # Emit chicken_started event to all clients
        socketio.emit('chicken_started', {
            'user': user,
            'task_name': task_name,
            'tier': tier
        })
        
        # Use animal duration for timer
        duration = animal_data["duration"] * 60
        timer_thread = threading.Thread(target=timer_worker, args=(user, duration))
        timer_thread.daemon = True
        timer_thread.start()
        
    except Exception as e:
        print(f"Error in start_chicken: {str(e)}")
        emit('error', {'message': f'Error starting session: {str(e)}'})

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
        # Record pause time for precision mode calculations
        data = load_data()
        
        # Find the active session
        active_session = None
        for session in data["users"][user]["sessions"]:
            if not session.get("completed", False) and not session.get("aborted", False):
                active_session = session
                break
                
        if active_session:
            # Record pause start time
            pause_info = {
                "pause_start": datetime.datetime.now().isoformat(),
                "pause_end": None
            }
            active_session.setdefault("pauses", []).append(pause_info)
            save_data(data)
        
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
        # Record resume time for precision mode calculations
        if not is_break:  # Only track pauses for main timer, not break timer
            data = load_data()
            
            # Find the active session
            active_session = None
            for session in data["users"][user]["sessions"]:
                if not session.get("completed", False) and not session.get("aborted", False):
                    active_session = session
                    break
                    
            if active_session and "pauses" in active_session and active_session["pauses"]:
                # Update the last pause with end time
                last_pause = active_session["pauses"][-1]
                if last_pause["pause_end"] is None:  # Make sure it's still paused
                    last_pause["pause_end"] = datetime.datetime.now().isoformat()
                    
                    # Calculate pause duration
                    pause_start = datetime.datetime.fromisoformat(last_pause["pause_start"])
                    pause_end = datetime.datetime.fromisoformat(last_pause["pause_end"])
                    pause_duration = (pause_end - pause_start).total_seconds()
                    
                    # Update total pause duration
                    active_session["total_pause_duration"] = active_session.get("total_pause_duration", 0) + pause_duration
                    
                    save_data(data)
        
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
        
        # Update user's streak and momentum multiplier
        data = load_data()
        
        # Check if user has combo_extender active
        has_combo_extender = data["users"][user]["stats"].get("mystery_egg_effect") == "combo_extender"
        
        # Reset user's streak only if they don't have combo_extender active
        if not has_combo_extender:
            data["users"][user]["stats"]["streak"] = 0
            data["users"][user]["stats"]["momentum_multiplier"] = 1.0
        else:
            # Clear the effect after it's used
            data["users"][user]["stats"]["mystery_egg_effect"] = None
            socketio.emit('effect_used', {
                'user': user,
                'effect_type': 'combo_extender',
                'message': 'Combo Extender used! Your streak is preserved.'
            })
        
        # Check for any active sessions that need to be marked as incomplete
        for session in data["users"][user]["sessions"]:
            if not session.get("completed", False):
                session["completed"] = False
                session["aborted"] = True
                session["abort_time"] = datetime.datetime.now().isoformat()
                
                # Check if this session was part of a duel
                if "duel_id" in session:
                    for duel in data.get("active_duels", [])[:]:  # Make a copy to allow removal
                        if duel["id"] == session["duel_id"]:
                            # Mark this user as forfeiting the duel
                            partner = duel["user1"] if duel["user2"] == user else duel["user2"]
                            
                            # Emit duel forfeit event
                            socketio.emit('duel_forfeit', {
                                'winner': partner,
                                'loser': user,
                                'tier': duel["tier"]
                            })
                            
                            # Remove the duel
                            data["active_duels"].remove(duel)
                
                break
        
        save_data(data)
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
            
            # Update momentum multiplier
            streak = data["users"][user]["stats"]["streak"] + 1
            data["users"][user]["stats"]["streak"] = streak
            
            # Update longest streak if applicable
            if streak > data["users"][user]["stats"]["longest_streak"]:
                data["users"][user]["stats"]["longest_streak"] = streak
            
            # Set momentum multiplier based on streak
            if streak == 1:
                data["users"][user]["stats"]["momentum_multiplier"] = 1.0
            elif streak == 2:
                data["users"][user]["stats"]["momentum_multiplier"] = 1.2
            elif streak == 3:
                data["users"][user]["stats"]["momentum_multiplier"] = 1.5
            else:  # 4 or more
                data["users"][user]["stats"]["momentum_multiplier"] = 2.0
                
            # Update session counts
            data["users"][user]["stats"]["weekly_chickens"] += 1
            if active_session["tier"] >= 5:  # Cow or Horse (high tier sessions)
                data["users"][user]["stats"]["lifetime_tier3_count"] += 1
                data["users"][user]["stats"]["weekly_tier3_count"] += 1
            
            # Check for Mystery Egg (only once per day, after first session)
            today = datetime.date.today().isoformat()
            mystery_egg_used_date = data["users"][user]["stats"]["mystery_egg_used_date"]
            sessions_today = len([s for s in data["users"][user]["sessions"] 
                               if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today() 
                               and s.get("completed", False)])
            
            # Check if this is the user's first session today and they haven't used the mystery egg yet
            if sessions_today == 1 and (mystery_egg_used_date is None or mystery_egg_used_date != today):
                # Activate mystery egg
                data["users"][user]["stats"]["mystery_egg_used_date"] = today
                
                # Choose a random effect (0-7 for more variety)
                effect_id = random.randint(0, 7)
                
                if effect_id == 0:  # +1 bonus point
                    data["users"][user]["points"] += 1
                    mystery_effect = {
                        "type": "bonus_point",
                        "description": "+1 bonus point added!"
                    }
                elif effect_id == 1:  # Skip next break
                    mystery_effect = {
                        "type": "skip_break",
                        "description": "Next break will be skipped!"
                    }
                elif effect_id == 2:  # Double points on next session
                    mystery_effect = {
                        "type": "double_points",
                        "description": "Double points on your next session!"
                    }
                elif effect_id == 3:  # Mirror mode
                    # Find partner's last completed session
                    partner = "luu" if user == "4keni" else "4keni"
                    partner_sessions = [s for s in data["users"][partner]["sessions"] if s.get("completed", False)]
                    partner_session = partner_sessions[-1] if partner_sessions else None
                    
                    if partner_session:
                        # Get animal type name
                        animal_type = CHICKEN_TYPES[partner_session["tier"]]["label"]
                        mystery_effect = {
                            "type": "mirror_mode",
                            "description": f"Revealed {partner}'s last task: {partner_session['task_name']} ({animal_type})"
                        }
                    else:
                        mystery_effect = {
                            "type": "bonus_point",
                            "description": "+1 bonus point (partner has no tasks yet)"
                        }
                        data["users"][user]["points"] += 1
                elif effect_id == 4:  # Next tier upgrade without penalty
                    mystery_effect = {
                        "type": "tier_upgrade",
                        "description": "Your next session can be upgraded one tier without additional time!"
                    }
                elif effect_id == 5:  # Combo extender
                    mystery_effect = {
                        "type": "combo_extender",
                        "description": "Your momentum multiplier will persist even if you reset your next session!"
                    }
                elif effect_id == 6:  # Dual challenge
                    mystery_effect = {
                        "type": "dual_challenge",
                        "description": "Complete two sessions in a row for a 3-point bonus!"
                    }
                elif effect_id == 7:  # Theme swap
                    partner = "luu" if user == "4keni" else "4keni"
                    mystery_effect = {
                        "type": "theme_swap",
                        "description": f"You can use {partner}'s theme for one day!"
                    }
                    # Add the partner's theme to unlocked themes temporarily
                    partner_theme = f"{partner}_theme"
                    if partner_theme not in data["users"][user]["stats"]["unlocked_themes"]:
                        data["users"][user]["stats"]["unlocked_themes"].append(partner_theme)
                        data["users"][user]["stats"]["temp_theme_unlock_date"] = today
                
                # Store the effect information
                data["users"][user]["stats"]["mystery_egg_effect"] = mystery_effect["type"]
                if mystery_effect["type"] == "double_points":
                    # Mark next session as the target for double points
                    data["users"][user]["stats"]["mystery_egg_target_session"] = None
                
                # Send the mystery egg event
                socketio.emit('mystery_egg_activated', {
                    'user': user,
                    'effect': mystery_effect
                })
            
            # Check for Duel completion if this session was part of a duel
            for duel in data.get("active_duels", [])[:]:  # Make a copy to allow removal
                if duel["user1"] == user or duel["user2"] == user:
                    # This user completed their part of the duel
                    if duel["user1"] == user:
                        duel["user1_completed"] = True
                        duel["user1_time"] = datetime.datetime.now().isoformat()
                    else:
                        duel["user2_completed"] = True
                        duel["user2_time"] = datetime.datetime.now().isoformat()
                    
                    # Check if both have completed or if this is the first to complete
                    if duel.get("user1_completed") and duel.get("user2_completed"):
                        # Duel is over, determine winner by completion time
                        time1 = datetime.datetime.fromisoformat(duel["user1_time"])
                        time2 = datetime.datetime.fromisoformat(duel["user2_time"])
                        
                        winner = duel["user1"] if time1 < time2 else duel["user2"]
                        loser = duel["user2"] if winner == duel["user1"] else duel["user1"]
                        
                        # Mark the session with duel victory
                        if winner == user:
                            active_session["duel_victory"] = True
                        
                        # Get animal type for the duel
                        animal_type = CHICKEN_TYPES[duel["tier"]]["label"]
                        
                        # Emit duel result event
                        socketio.emit('duel_complete', {
                            'winner': winner,
                            'loser': loser,
                            'tier': duel["tier"],
                            'animal_type': animal_type
                        })
                        
                        # Remove the completed duel
                        data["active_duels"].remove(duel)
                    
                    # Only one user has completed so far, just save the state
                    break
            
            # Check for achievements (Focus Flex Moments)
            achievements = []
            
            # Achievement: 5 sessions in a week
            if data["users"][user]["stats"]["weekly_chickens"] == 5 and "weekly_5_chickens" not in data["users"][user]["stats"]["achievements"]:
                achievements.append({
                    "id": "weekly_5_chickens",
                    "title": "WeekWarrior",
                    "description": "Completed 5 sessions in a week"
                })
                data["users"][user]["stats"]["achievements"].append("weekly_5_chickens")
            
            # Achievement: 3 high tier sessions in a row (Cow or Horse)
            if streak >= 3:
                last_three = data["users"][user]["sessions"][-3:]
                if all(s["tier"] >= 5 for s in last_three) and "three_tier3_streak" not in data["users"][user]["stats"]["achievements"]:
                    achievements.append({
                        "id": "three_tier3_streak",
                        "title": "Boss Mode",
                        "description": "Completed 3 high-tier sessions (Cow/Horse) in a row"
                    })
                    data["users"][user]["stats"]["achievements"].append("three_tier3_streak")
            
            # Achievement: Gold unlock (20 lifetime high-tier sessions)
            if data["users"][user]["stats"]["lifetime_tier3_count"] == 20 and "gold_chicken" not in data["users"][user]["stats"]["unlocked_skins"]:
                data["users"][user]["stats"]["unlocked_skins"].append("gold_chicken")
                achievements.append({
                    "id": "gold_chicken_unlock",
                    "title": "Gold Standard",
                    "description": "Unlocked Gold skin"
                })
            
            # Emit achievements if any were earned
            if achievements:
                socketio.emit('achievements_earned', {
                    'user': user,
                    'achievements': achievements
                })
                
                # Send flex notification to the partner
                partner = "luu" if user == "4keni" else "4keni"
                flex_message = f"{user} just earned: {', '.join(a['title'] for a in achievements)}"
                
                socketio.emit('focus_flex', {
                    'user': user,
                    'partner': partner,
                    'message': flex_message
                })
            
            save_data(data)
            
            # Determine if user should skip break (mystery egg effect)
            skip_break = False
            if data["users"][user]["stats"].get("mystery_egg_effect") == "skip_break":
                skip_break = True
                # Clear the effect after it's used
                data["users"][user]["stats"]["mystery_egg_effect"] = None
                save_data(data)
            
            if not skip_break:
                # Start a break timer (5 minutes)
                break_duration = 5 * 60  # 5 minutes in seconds
                socketio.emit('break_started', {'user': user})
                
                timer_thread = threading.Thread(target=timer_worker, args=(user, break_duration, True))
                timer_thread.daemon = True
                timer_thread.start()
            else:
                # Skip break and reset timer directly
                socketio.emit('break_skipped', {'user': user})
                socketio.emit('timer_reset', {'user': user})
            
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
            
            # Send a full update to all clients
            socketio.emit('full_update', data)
            
            # Emit session_complete event
            socketio.emit('session_complete', {'user': user})

            # Add animal to inventory in animals.json with barn and name
            try:
                with open('data/animals.json', 'r') as f:
                    animals_data = json.load(f)
            except Exception:
                animals_data = {u: {"inventory": [], "cash": 0} for u in USERS}
                
            animal_to_add = active_session.get("animal")
            if animal_to_add:
                animals_data.setdefault(user, {"inventory": [], "cash": 0})
                # Add barn and name information to the animal
                animal_to_add.update({
                    "barn_id": active_session.get("barn_id", "default"),
                    "name": active_session.get("chicken_name", ""),
                    "timestamp": datetime.datetime.now().isoformat()
                })
                animals_data[user]["inventory"].append(animal_to_add)
                with open('data/animals.json', 'w') as f:
                    json.dump(animals_data, f, indent=2)
                    
            # Clear current session
            current_sessions[user] = None
    except Exception as e:
        print(f"Error in timer_complete: {str(e)}")
        emit('error', {'message': f'Error completing timer: {str(e)}'})

@socketio.on('end_cycle')
def handle_end_cycle():
    data = load_data()
    data = end_cycle(data)
    save_data(data)
    
    # Emit full data update to all clients
    socketio.emit('full_update', data)
    socketio.emit('cycle_ended', {'winner': data["winner"]})

def end_cycle(data):
    """End the current 7-day cycle and determine winner"""
    # Calculate final points for the cycle
    cycle_results = {}
    for user in USERS:
        points = calculate_points(user, data)
        cycle_results[user] = {
            "points": points,
            "tier3_count": data["users"][user]["stats"]["weekly_tier3_count"],
            "total_chickens": data["users"][user]["stats"]["weekly_chickens"],
            "longest_streak": data["users"][user]["stats"]["longest_streak"],
            "achievements": len(data["users"][user]["stats"]["achievements"])
        }
    
    # Determine winner based on points
    winner = max(cycle_results, key=lambda x: cycle_results[x]["points"])
    
    # In case of a tie, we could use other metrics
    if len(set(cycle_results[user]["points"] for user in USERS)) == 1:  # All same points
        # Try breaking tie by tier3 count
        winner = max(cycle_results, key=lambda x: cycle_results[x]["tier3_count"])
        
        # If still tied, it's officially a tie
        if len(set(cycle_results[user]["tier3_count"] for user in USERS)) == 1:
            winner = "Tie"
    
    # Archive cycle data
    cycle_archive = {
        "start_date": data["cycle_start"],
        "end_date": datetime.datetime.now().isoformat(),
        "results": cycle_results,
        "winner": winner
    }
    
    # Add cycle archive to data
    data.setdefault("cycle_history", []).append(cycle_archive)
    
    # Create achievements based on cycle results
    for user in USERS:
        user_achievements = []
        
        # Achievement: Won a cycle
        if winner == user and "cycle_winner" not in data["users"][user]["stats"]["achievements"]:
            data["users"][user]["stats"]["achievements"].append("cycle_winner")
            user_achievements.append({
                "id": "cycle_winner",
                "title": "Cycle Champion",
                "description": "Won a full 7-day cycle"
            })
        
        # Achievement: Tier 3 Master (completed at least 5 tier 3 chickens in a week)
        if cycle_results[user]["tier3_count"] >= 5 and "tier3_master" not in data["users"][user]["stats"]["achievements"]:
            data["users"][user]["stats"]["achievements"].append("tier3_master")
            user_achievements.append({
                "id": "tier3_master",
                "title": "Tier 3 Master",
                "description": "Completed 5+ Tier 3 chickens in a single cycle"
            })
        
        # Achievement: Perfect Week (completed at least 5 chickens on 5 different days)
        sessions_by_day = {}
        for session in data["users"][user]["sessions"]:
            if session.get("completed", False):
                day = datetime.datetime.fromisoformat(session["timestamp"]).date().isoformat()
                sessions_by_day.setdefault(day, 0)
                sessions_by_day[day] += 1
        
        days_with_5_chickens = sum(1 for count in sessions_by_day.values() if count >= 5)
        
        if days_with_5_chickens >= 5 and "perfect_week" not in data["users"][user]["stats"]["achievements"]:
            data["users"][user]["stats"]["achievements"].append("perfect_week")
            user_achievements.append({
                "id": "perfect_week",
                "title": "Perfect Week",
                "description": "Completed 5+ chickens on 5+ days in a single cycle"
            })
            
            # Unlock special theme for Perfect Week achievement
            special_theme = "perfect_week_theme"
            if special_theme not in data["users"][user]["stats"]["unlocked_themes"]:
                data["users"][user]["stats"]["unlocked_themes"].append(special_theme)
        
        # Emit achievements if any were earned
        if user_achievements:
            socketio.emit('achievements_earned', {
                'user': user,
                'achievements': user_achievements
            })
    
    # Reset for new cycle
    data["cycle_start"] = datetime.datetime.now().isoformat()
    data["winner"] = winner
    
    # Reset weekly stats but keep lifetime stats
    for user in USERS:
        data["users"][user]["stats"]["weekly_tier3_count"] = 0
        data["users"][user]["stats"]["weekly_chickens"] = 0
        data["users"][user]["stats"]["streak"] = 0
        data["users"][user]["stats"]["momentum_multiplier"] = 1.0
    
    # Keep sessions from this week as historical data, but reset active state
    # Optionally, you could archive old sessions to a separate data structure
    
    # Reset active duels
    data["active_duels"] = []
    
    return data

@socketio.on('start_chaos_chicken')
def handle_start_chaos_chicken(json_data):
    user = json_data.get('user')
    current_user = json_data.get('current_user')
    
    # Check that user is only controlling their own side
    if user != current_user:
        print(f"Error: User {current_user} tried to control {user}'s timer")
        emit('error', {'message': f'You can only control your own timer'})
        return
    
    try:
        data = load_data()
        
        # Check if chaos chicken is offered to this user
        if not data["weekly_chaos_chicken"]["offered"] or data["weekly_chaos_chicken"]["offered_to"] != user:
            emit('error', {'message': 'No chaos chicken challenge available for you'})
            return
        
        # Get challenge data
        challenge_type = data["weekly_chaos_chicken"]["challenge_type"]
        challenge_params = data["weekly_chaos_chicken"]["challenge_params"]
        
        # Mark that the user has accepted the challenge
        data["weekly_chaos_chicken"]["accepted"] = True
        data["weekly_chaos_chicken"]["accepted_date"] = datetime.datetime.now().isoformat()
        
        # Save the updated data
        save_data(data)
        
        # Emit an event to let the user know the challenge has begun
        socketio.emit('chaos_chicken_started', {
            'user': user,
            'challenge_type': challenge_type,
            'challenge_params': challenge_params
        })
        
    except Exception as e:
        print(f"Error in start_chaos_chicken: {str(e)}")
        emit('error', {'message': f'Error starting chaos chicken: {str(e)}'})

@socketio.on('complete_chaos_chicken')
def handle_complete_chaos_chicken(json_data):
    user = json_data.get('user')
    current_user = json_data.get('current_user')
    success = json_data.get('success', False)
    
    # Check that user is only controlling their own side
    if user != current_user:
        print(f"Error: User {current_user} tried to control {user}'s timer")
        emit('error', {'message': f'You can only control your own timer'})
        return
    
    try:
        data = load_data()
        
        # Check if chaos chicken is active for this user
        if not data["weekly_chaos_chicken"].get("accepted", False) or data["weekly_chaos_chicken"]["offered_to"] != user:
            emit('error', {'message': 'No active chaos chicken challenge'})
            return
        
        # Mark the challenge as completed
        data["weekly_chaos_chicken"]["completed"] = success
        data["weekly_chaos_chicken"]["completion_date"] = datetime.datetime.now().isoformat()
        data["weekly_chaos_chicken"]["completed_by"] = user
        
        # Award points if successful
        if success:
            # Award 5 bonus points for completing the chaos chicken
            data["users"][user]["points"] += 5
            
            # Create a special achievement
            achievement = {
                "id": f"chaos_chicken_{data['weekly_chaos_chicken']['challenge_type']}",
                "title": "Chaos Conqueror",
                "description": f"Completed the {data['weekly_chaos_chicken']['challenge_type']} chaos chicken challenge!"
            }
            
            # Add to user's achievements if not already there
            if achievement["id"] not in data["users"][user]["stats"]["achievements"]:
                data["users"][user]["stats"]["achievements"].append(achievement["id"])
                
                # Emit achievement notification
                socketio.emit('achievements_earned', {
                    'user': user,
                    'achievements': [achievement]
                })
                
                # Send flex notification to the partner
                partner = "luu" if user == "4keni" else "4keni"
                flex_message = f"{user} just conquered the chaos chicken challenge!"
                
                socketio.emit('focus_flex', {
                    'user': user,
                    'partner': partner,
                    'message': flex_message
                })
        
        # Reset the weekly chaos chicken
        data["weekly_chaos_chicken"]["offered"] = False
        data["weekly_chaos_chicken"]["accepted"] = False
        
        # Save the updated data
        save_data(data)
        
        # Emit a completion event
        socketio.emit('chaos_chicken_completed', {
            'user': user,
            'success': success,
            'points_earned': 5 if success else 0
        })
        
    except Exception as e:
        print(f"Error in complete_chaos_chicken: {str(e)}")
        emit('error', {'message': f'Error completing chaos chicken: {str(e)}'})

@app.route('/api/available_animals')
def api_available_animals():
    return jsonify(get_available_animals())

@app.route('/api/user_animals/<user>')
def api_user_animals(user):
    try:
        with open('data/animals.json', 'r') as f:
            animals_data = json.load(f)
        user_data = animals_data.get(user, {"inventory": [], "cash": 0})
        
        # Load barns data
        barns = load_barns()
        user_barns = barns['users'].get(user, {"barns": []})
        
        # Count animals raised today
        today = datetime.date.today().isoformat()
        today_count = sum(1 for a in user_data.get('inventory', []) if a.get('timestamp', '').startswith(today))
        
        # Get current animal (if any)
        current_animal = None
        if user in current_sessions and current_sessions[user]:
            current_animal = current_sessions[user]['animal']
            if current_animal:
                current_animal.update({
                    'barn_id': current_sessions[user].get('barn_id', 'default'),
                    'name': current_sessions[user].get('chicken_name', '')
                })
        
        # Organize animals by barn
        animals_by_barn = {}
        for barn in user_barns['barns']:
            barn_id = barn['id']
            animals_by_barn[barn_id] = {
                'barn_info': barn,
                'animals': []
            }
        
        # Add animals to their respective barns
        for animal in user_data.get('inventory', []):
            barn_id = animal.get('barn_id', 'default')
            if barn_id not in animals_by_barn:
                # If barn was deleted, put animals in default barn
                barn_id = 'default'
            animals_by_barn[barn_id]['animals'].append(animal)
        
        return jsonify({
            "inventory": user_data.get('inventory', []),
            "cash": user_data.get('cash', 0),
            "today_count": today_count,
            "current_animal": current_animal,
            "barns": animals_by_barn
        })
    except Exception as e:
        return jsonify({
            "inventory": [],
            "cash": 0,
            "today_count": 0,
            "current_animal": None,
            "barns": {},
            "error": str(e)
        })

@app.route('/api/market_events')
def api_market_events():
    return jsonify(list(MARKET_EVENTS))

@app.route('/api/market_feed')
def api_market_feed():
    return jsonify(list(MARKET_FEED))

@app.route('/static/market_graph.png')
def market_graph():
    # Mock price data for each animal
    animals = get_available_animals()
    n_points = 24
    x = np.arange(n_points)
    price_data = {}
    event_marks = {e['animal']: e for e in EVENT_POINTS}
    # Define colors and styles for each animal
    colors = {
        'Chicken': '#FFD700',  # Gold
        'Goat': '#8FBC8F',     # Dark Sea Green
        'Sheep': '#87CEEB',    # Sky Blue
        'Pig': '#FF69B4',      # Hot Pink
        'Cow': '#A0522D',      # Sienna
        'Horse': '#6A5ACD'     # Slate Blue
    }
    emojis = {
        'Chicken': '🐔',
        'Goat': '🐐',
        'Sheep': '🐑',
        'Pig': '🐖',
        'Cow': '🐄',
        'Horse': '🐎'
    }
    # Generate price data with event effects
    for animal in animals:
        low, high = animal['base_price']
        trend = np.linspace(low, high, n_points)
        noise = np.random.normal(0, (high-low)*0.1, n_points)
        seasonal = np.sin(np.linspace(0, 4*np.pi, n_points)) * (high-low)*0.05
        prices = trend + noise + seasonal
        # Apply event effect to last point if event is active
        if animal['name'] in event_marks:
            effect = event_marks[animal['name']]['effect']
            prices[-1] = prices[-2] * (1 + effect)
        prices = np.clip(prices, low, high)
        price_data[animal['name']] = prices
    # Create figure with custom style
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 4), facecolor='#1a1a1a')
    # Plot each animal's price line and place emoji at the end
    for animal in animals:
        name = animal['name']
        y = price_data[name]
        ax.plot(x, y, label=name, color=colors[name], linewidth=2, alpha=0.8)
        # Place emoji at the last point
        ax.text(x[-1]+0.2, y[-1], emojis[name], fontsize=18, ha='left', va='center', fontweight='bold', fontname='Segoe UI Emoji')
        # If event, highlight last point
        if name in event_marks:
            ax.scatter(x[-1], y[-1], s=180, color=colors[name], edgecolor='white', zorder=10)
            ax.text(x[-1], y[-1]+(high-low)*0.08, f"{event_marks[name]['emoji']} {event_marks[name]['desc']}", color=colors[name], fontsize=10, ha='center', va='bottom', fontweight='bold', bbox=dict(facecolor='#222', edgecolor=colors[name], boxstyle='round,pad=0.2', alpha=0.8))
    # Customize the plot
    ax.set_title('Animal Market Prices', color='white', pad=20, fontsize=14)
    ax.set_xlabel('Hour', color='#999', labelpad=10)
    ax.set_ylabel('Price ($)', color='#999', labelpad=10)
    ax.grid(True, linestyle='--', alpha=0.2, color='#666')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#666')
    ax.spines['bottom'].set_color('#666')
    ax.tick_params(colors='#999')
    legend = ax.legend(loc='upper left', 
                      bbox_to_anchor=(0.02, 0.98),
                      frameon=True,
                      facecolor='#222',
                      edgecolor='#333',
                      fontsize=10)
    plt.tight_layout()
    # Save to static/market_graph.png with high DPI
    out_path = os.path.join('static', 'market_graph.png')
    plt.savefig(out_path, 
                dpi=150,
                bbox_inches='tight',
                facecolor='#1a1a1a',
                edgecolor='none',
                transparent=False)
    plt.close()
    # Always serve with no-cache headers for live updates
    response = send_file(out_path, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Start the event thread on app startup
threading.Thread(target=market_event_thread, daemon=True).start()

# System health monitoring
def get_system_health():
    process = psutil.Process()
    memory_info = process.memory_info()
    return {
        'memory_usage': memory_info.rss / 1024 / 1024,  # MB
        'cpu_percent': process.cpu_percent(),
        'thread_count': threading.active_count(),
        'uptime': time.time() - process.create_time()
    }

# Memory management
def cleanup_memory():
    gc.collect()
    plt.close('all')  # Close any open matplotlib figures

# Add new routes for barn management
@app.route('/api/barns/<user>')
def api_user_barns(user):
    try:
        barns = load_barns()
        return jsonify(barns['users'].get(user, {"barns": []}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@socketio.on('create_barn')
def handle_create_barn(json_data):
    user = json_data.get('user')
    barn_name = json_data.get('name')
    description = json_data.get('description', '')
    
    if not user or not barn_name:
        emit('error', {'message': 'Missing required fields'})
        return
        
    try:
        barns = load_barns()
        # Generate unique ID for the barn
        barn_id = f"barn_{int(time.time())}"
        
        # Add new barn
        barns['users'][user]['barns'].append({
            "id": barn_id,
            "name": barn_name,
            "description": description
        })
        
        save_barns(barns)
        
        # Notify all clients about the new barn
        socketio.emit('barn_created', {
            'user': user,
            'barn': {
                "id": barn_id,
                "name": barn_name,
                "description": description
            }
        })
        
    except Exception as e:
        emit('error', {'message': f'Error creating barn: {str(e)}'})

@socketio.on('rename_barn')
def handle_rename_barn(json_data):
    user = json_data.get('user')
    barn_id = json_data.get('barn_id')
    new_name = json_data.get('new_name')
    
    if not all([user, barn_id, new_name]):
        emit('error', {'message': 'Missing required fields'})
        return
        
    try:
        barns = load_barns()
        # Find and update the barn
        for barn in barns['users'][user]['barns']:
            if barn['id'] == barn_id:
                barn['name'] = new_name
                save_barns(barns)
                socketio.emit('barn_renamed', {
                    'user': user,
                    'barn_id': barn_id,
                    'new_name': new_name
                })
                return
                
        emit('error', {'message': 'Barn not found'})
        
    except Exception as e:
        emit('error', {'message': f'Error renaming barn: {str(e)}'})

if __name__ == '__main__':
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    print("Data directory checked/created")
    
    # Get port from environment variable (for Render.com) or use default
    port = int(os.environ.get('PORT', 5000))
    print(f"Using port: {port}")
    
    # Force development mode for local testing
    production_mode = False
    print(f"RENDER env var: {os.environ.get('RENDER')}")
    print(f"Production mode: {production_mode}")
    
    if production_mode:
        # Let gunicorn handle the app
        print("Running in production mode")
    else:
        # Development mode with debug enabled
        print("Starting development server in verbose mode...")
        # Explicitly set logger levels
        logging.getLogger('werkzeug').setLevel(logging.INFO)
        logging.getLogger('engineio').setLevel(logging.DEBUG)
        logging.getLogger('socketio').setLevel(logging.DEBUG)
        
        # Start server with eventlet
        socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True) 