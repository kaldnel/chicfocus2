// Initialize socket with error handling
const socket = io({
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    timeout: 30000,
    transports: ['websocket', 'polling']
});

// State variables
let currentUser = null;
let partnerUser = null;
let activeTimers = {
    'luu': { isRunning: false, isPaused: false, isBreak: false },
    '4keni': { isRunning: false, isPaused: false, isBreak: false }
};

// Connection handling
socket.on('connect', () => {
    console.log('Socket connected! ID:', socket.id);
    document.body.classList.add('socket-connected');
});

socket.on('disconnect', (reason) => {
    console.error('Socket disconnected:', reason);
    document.body.classList.remove('socket-connected');
    alert('Disconnected from server: ' + reason + '. Please refresh the page.');
});

socket.on('connect_error', (error) => {
    console.error('Socket connection error:', error);
    document.body.classList.remove('socket-connected');
    alert('Connection error: ' + error.message + '. Please refresh the page.');
});

socket.on('server_connected', (data) => {
    console.log('Server confirmation received:', data);
});

socket.on('error', (error) => {
    console.error('Socket error:', error);
    alert(error.message || 'An error occurred');
});

// User management
function selectUser(user) {
    currentUser = user;
    partnerUser = user === 'luu' ? '4keni' : 'luu';
    
    // Hide modal, show app
    document.getElementById('user-modal').classList.add('hidden');
    document.getElementById('main-app').classList.remove('hidden');
    
    // Both sides are visible, but highlight current user's content
    if (user === 'luu') {
        document.getElementById('luu-side').classList.add('current-user-side');
        document.getElementById('keni-side').classList.remove('current-user-side');
    } else {
        document.getElementById('luu-side').classList.remove('current-user-side');
        document.getElementById('keni-side').classList.add('current-user-side');
    }
    
    // Set user indicators
    document.getElementById('luu-user-indicator').textContent = user === 'luu' ? 'luu (you)' : 'luu';
    document.getElementById('keni-user-indicator').textContent = user === '4keni' ? '4keni (you)' : '4keni';
}

function logout() {
    document.getElementById('user-modal').classList.remove('hidden');
    document.getElementById('main-app').classList.add('hidden');
    currentUser = null;
    partnerUser = null;
}

// Chicken management
function startChicken(user) {
    if (!socket.connected) {
        console.error('Socket not connected!');
        alert('Not connected to server. Please refresh the page and try again.');
        return;
    }
    
    if (user !== currentUser) {
        alert("You can only start chickens for your own user!");
        return;
    }
    
    const taskInputId = user === 'luu' ? 'luu-task-name' : 'keni-task-name';
    const tierSelector = user === 'luu' ? 'input[name="luu-tier"]:checked' : 'input[name="keni-tier"]:checked';
    
    const taskName = document.getElementById(taskInputId).value.trim();
    const tierInput = document.querySelector(tierSelector);
    
    if (!tierInput) {
        alert('Please select a chicken tier.');
        return;
    }
    
    const tier = tierInput.value;
    
    if (!taskName) {
        alert('Please enter a task name!');
        return;
    }
    
    // Emit the start_chicken event
    socket.emit('start_chicken', {
        user: user,
        task_name: taskName,
        tier: tier,
        current_user: currentUser
    });
    
    console.log(`Starting chicken for ${user} - Task: ${taskName}, Tier: ${tier}`);
}

// Timer functions
function pauseTimer(user) {
    if (user !== currentUser) {
        alert("You can only control your own timer!");
        return;
    }
    
    if (activeTimers[user].isPaused) {
        socket.emit('resume_timer', {
            user: user, 
            is_break: activeTimers[user].isBreak,
            current_user: currentUser
        });
    } else {
        socket.emit('pause_timer', {
            user: user,
            current_user: currentUser
        });
    }
}

function resetTimer(user) {
    if (user !== currentUser) {
        alert("You can only control your own timer!");
        return;
    }
    
    socket.emit('reset_timer', {
        user: user,
        current_user: currentUser
    });
}

function endCycle() {
    if (confirm('Are you sure you want to end the current cycle?')) {
        socket.emit('end_cycle');
    }
}

// Activity log updating
function updateActivityLog(data) {
    const allSessions = [];
    
    for (const [user, userData] of Object.entries(data.users)) {
        for (const session of userData.sessions) {
            allSessions.push({...session, user});
        }
    }
    
    allSessions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    const logHtml = allSessions.slice(0, 10).map(session => {
        const date = new Date(session.timestamp);
        const timeStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'});
        
        const userClass = session.user === 'luu' ? 'luu' : '\\34keni'; // Using the escaped format for CSS
        
        return `<div class="log-entry tier-${session.tier} ${userClass}">
            <span class="log-user">${session.user}</span>
            <span class="log-task">${session.task_name}</span>
            <span class="log-tier">Tier ${session.tier}</span>
            <span class="log-time">${timeStr}</span>
        </div>`;
    }).join('');
    
    document.getElementById('shared-log').innerHTML = logHtml || '<div class="empty-log">No activities yet</div>';
}

// Socket event handlers
socket.on('chicken_started', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === currentUser) {
        // Update UI for current user
        document.getElementById(`${userKey}-timer-status`).textContent = `Working on: ${data.task_name} (Tier ${data.tier})`;
        document.getElementById(`${userKey}-start-btn`).disabled = true;
        document.getElementById(`${userKey}-pause-btn`).disabled = false;
        document.getElementById(`${userKey}-reset-btn`).disabled = false;
        document.getElementById(`${userKey}-task-name`).value = '';
        
        // Set timer state
        activeTimers[user].isRunning = true;
        activeTimers[user].isPaused = false;
        activeTimers[user].isBreak = false;
    } else {
        // Update partner UI
        const partnerTimerId = user === 'luu' ? 'luu-status' : 'keni-status';
        document.getElementById(partnerTimerId).textContent = `${data.task_name} (Tier ${data.tier})`;
    }
});

socket.on('timer_update', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    // Update timer display for both sides
    if (user === 'luu') {
        document.getElementById('luu-timer-display').textContent = data.time;
        document.getElementById('luu-timer').textContent = data.time;
    } else {
        document.getElementById('keni-timer-display').textContent = data.time;
        document.getElementById('keni-timer').textContent = data.time;
    }
});

socket.on('timer_paused', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === currentUser) {
        document.getElementById(`${userKey}-pause-btn`).textContent = 'Resume';
        activeTimers[user].isPaused = true;
    }
});

socket.on('timer_resumed', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === currentUser) {
        document.getElementById(`${userKey}-pause-btn`).textContent = 'Pause';
        activeTimers[user].isPaused = false;
    }
});

socket.on('timer_reset', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === 'luu') {
        document.getElementById('luu-timer-display').textContent = '00:00';
        document.getElementById('luu-timer').textContent = '00:00';
        document.getElementById('luu-timer-status').textContent = 'Ready to start';
        document.getElementById('luu-status').textContent = 'Idle';
        
        if (user === currentUser) {
            document.getElementById('luu-start-btn').disabled = false;
            document.getElementById('luu-pause-btn').disabled = true;
            document.getElementById('luu-reset-btn').disabled = true;
            document.getElementById('luu-pause-btn').textContent = 'Pause';
            
            activeTimers[user].isRunning = false;
            activeTimers[user].isPaused = false;
            activeTimers[user].isBreak = false;
        }
    } else {
        document.getElementById('keni-timer-display').textContent = '00:00';
        document.getElementById('keni-timer').textContent = '00:00';
        document.getElementById('keni-timer-status').textContent = 'Ready to start';
        document.getElementById('keni-status').textContent = 'Idle';
        
        if (user === currentUser) {
            document.getElementById('keni-start-btn').disabled = false;
            document.getElementById('keni-pause-btn').disabled = true;
            document.getElementById('keni-reset-btn').disabled = true;
            document.getElementById('keni-pause-btn').textContent = 'Pause';
            
            activeTimers[user].isRunning = false;
            activeTimers[user].isPaused = false;
            activeTimers[user].isBreak = false;
        }
    }
});

socket.on('break_started', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === currentUser) {
        document.getElementById(`${userKey}-timer-status`).textContent = 'Break time! 🐥';
        activeTimers[user].isBreak = true;
    } else {
        const statusId = user === 'luu' ? 'luu-status' : 'keni-status';
        document.getElementById(statusId).textContent = 'On break 🐥';
    }
});

socket.on('session_complete', (data) => {
    const user = data.user;
    const userKey = user === '4keni' ? 'keni' : 'luu';
    
    if (user === 'luu') {
        document.getElementById('luu-timer-display').textContent = '00:00';
        document.getElementById('luu-timer').textContent = '00:00';
        document.getElementById('luu-timer-status').textContent = 'Session completed! 🎉';
        document.getElementById('luu-status').textContent = 'Completed session 🎉';
        
        if (user === currentUser) {
            document.getElementById('luu-start-btn').disabled = false;
            document.getElementById('luu-pause-btn').disabled = true;
            document.getElementById('luu-reset-btn').disabled = true;
            document.getElementById('luu-pause-btn').textContent = 'Pause';
            
            activeTimers[user].isRunning = false;
            activeTimers[user].isPaused = false;
            activeTimers[user].isBreak = false;
            
            alert('Great job! Your chicken is done. 🐥');
        }
    } else {
        document.getElementById('keni-timer-display').textContent = '00:00';
        document.getElementById('keni-timer').textContent = '00:00';
        document.getElementById('keni-timer-status').textContent = 'Session completed! 🎉';
        document.getElementById('keni-status').textContent = 'Completed session 🎉';
        
        if (user === currentUser) {
            document.getElementById('keni-start-btn').disabled = false;
            document.getElementById('keni-pause-btn').disabled = true;
            document.getElementById('keni-reset-btn').disabled = true;
            document.getElementById('keni-pause-btn').textContent = 'Pause';
            
            activeTimers[user].isRunning = false;
            activeTimers[user].isPaused = false;
            activeTimers[user].isBreak = false;
            
            alert('Great job! Your chicken is done. 🐥');
        }
    }
});

socket.on('full_update', (data) => {
    if (!currentUser) return;
    
    // Update points and sessions
    document.getElementById('luu-points').textContent = data.users.luu.current_points;
    document.getElementById('luu-sessions').textContent = data.users.luu.sessions_today;
    document.getElementById('keni-points').textContent = data.users['4keni'].current_points;
    document.getElementById('keni-sessions').textContent = data.users['4keni'].sessions_today;
    
    // Update cycle info
    document.getElementById('days-remaining').textContent = data.days_remaining;
    
    // Update activity log
    updateActivityLog(data);
});

socket.on('cycle_complete', (data) => {
    let message;
    if (data.winner === 'Tie') {
        message = `It's a tie! Both users have the same points.\nYou'll need to decide together who chooses the next date!`;
    } else {
        message = `🎉 ${data.winner} wins!\n\n${data.winner} gets to choose who picks the next date activity.`;
    }
    alert(message);
}); 