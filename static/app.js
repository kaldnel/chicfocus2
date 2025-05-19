// Initialize socket with error handling
const socket = io({
    reconnection: true,
    reconnectionAttempts: Infinity,  // Always try to reconnect
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 60000,  // Longer timeout
    transports: ['websocket', 'polling'],
    forceNew: false,
    pingInterval: 5000,  // Match server settings
    pingTimeout: 180000  // Match server settings
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
    
    // If we were disconnected and reconnected, try to get the latest data
    if (currentUser) {
        console.log('Reconnected, requesting data refresh...');
        // Optional: Request a full data refresh from the server
        // socket.emit('request_refresh', { user: currentUser });
    }
});

socket.on('disconnect', (reason) => {
    console.error('Socket disconnected:', reason);
    document.body.classList.remove('socket-connected');
    
    // Don't alert on normal disconnections or page unload
    if (reason !== 'io client disconnect' && reason !== 'transport close') {
        // Show a non-intrusive message instead of an alert
        const statusEl = document.createElement('div');
        statusEl.className = 'disconnection-notice';
        statusEl.textContent = 'Connection lost. Attempting to reconnect...';
        document.body.appendChild(statusEl);
        
        // Remove the message after 5 seconds or when reconnected
        setTimeout(() => {
            if (document.body.contains(statusEl)) {
                document.body.removeChild(statusEl);
            }
        }, 5000);
    }
});

socket.on('reconnect', (attemptNumber) => {
    console.log(`Reconnected after ${attemptNumber} attempts`);
    document.body.classList.add('socket-connected');
    
    // Remove any disconnection notices
    const notices = document.querySelectorAll('.disconnection-notice');
    notices.forEach(notice => document.body.removeChild(notice));
    
    // If user was logged in, try to restore their session
    if (currentUser) {
        console.log('Trying to restore session after reconnection');
    }
});

socket.on('reconnect_attempt', (attemptNumber) => {
    console.log(`Reconnection attempt ${attemptNumber}`);
});

socket.on('connect_error', (error) => {
    console.error('Socket connection error:', error);
    document.body.classList.remove('socket-connected');
    
    // Only show an alert if we've tried to reconnect several times
    if (socket.io.reconnectionAttempts > 5) {
        alert(`Connection error: ${error.message}. Please refresh the page.`);
    }
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

// Session management
function startChicken(user) {
    if (!socket.connected) {
        console.error('Socket not connected!');
        alert('Not connected to server. Please refresh the page and try again.');
        return;
    }
    
    if (user !== currentUser) {
        alert("You can only start sessions for your own user!");
        return;
    }
    
    const taskInputId = user === 'luu' ? 'luu-task-name' : 'keni-task-name';
    const tierInputId = user === 'luu' ? 'luu-animal-tier' : 'keni-animal-tier';
    
    const taskName = document.getElementById(taskInputId).value.trim();
    const tierInput = document.getElementById(tierInputId);
    
    if (!tierInput || !tierInput.value) {
        alert('Please select an animal type.');
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
    
    console.log(`Starting session for ${user} - Task: ${taskName}, Type: ${tier}`);
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
        
        // Get animal type name based on tier
        let animalType = "Session";
        const tierValue = parseInt(session.tier);
        if (tierValue === 1) animalType = "Chicken";
        else if (tierValue === 2) animalType = "Goat";
        else if (tierValue === 3) animalType = "Sheep";
        else if (tierValue === 4) animalType = "Pig";
        else if (tierValue === 5) animalType = "Cow";
        else if (tierValue === 6) animalType = "Horse";
        
        return `<div class="log-entry tier-${session.tier} ${userClass}">
            <span class="log-user">${session.user}</span>
            <span class="log-task">${session.task_name}</span>
            <span class="log-tier">${animalType}</span>
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
        // Get the animal type label instead of tier number
        let animalType = "Session";
        const tierValue = parseInt(data.tier);
        if (tierValue === 1) animalType = "Chicken";
        else if (tierValue === 2) animalType = "Goat";
        else if (tierValue === 3) animalType = "Sheep";
        else if (tierValue === 4) animalType = "Pig";
        else if (tierValue === 5) animalType = "Cow";
        else if (tierValue === 6) animalType = "Horse";
        
        // Update UI for current user
        document.getElementById(`${userKey}-timer-status`).textContent = `Working on: ${data.task_name} (${animalType})`;
        document.getElementById(`${userKey}-start-btn`).disabled = true;
        document.getElementById(`${userKey}-pause-btn`).disabled = false;
        document.getElementById(`${userKey}-reset-btn`).disabled = false;
        document.getElementById(`${userKey}-task-name`).value = '';
        
        // Set timer state
        activeTimers[user].isRunning = true;
        activeTimers[user].isPaused = false;
        activeTimers[user].isBreak = false;
    } else {
        // Get the animal type label for partner display
        let animalType = "Session";
        const tierValue = parseInt(data.tier);
        if (tierValue === 1) animalType = "Chicken";
        else if (tierValue === 2) animalType = "Goat";
        else if (tierValue === 3) animalType = "Sheep";
        else if (tierValue === 4) animalType = "Pig";
        else if (tierValue === 5) animalType = "Cow";
        else if (tierValue === 6) animalType = "Horse";
        
        // Update partner UI
        const partnerTimerId = user === 'luu' ? 'luu-status' : 'keni-status';
        document.getElementById(partnerTimerId).textContent = `${data.task_name} (${animalType})`;
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
            
            alert('Great job! Your session is done. 🎉');
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
            
            alert('Great job! Your session is done. 🎉');
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
    
    // Update chaos chicken UI
    updateChaosChickenUI(data);
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

// --- Market Events Frontend Logic ---
let lastEventTime = null;
let eventPopupTimeout = null;

function showMarketEventPopup(event) {
    // Remove any existing popup
    let popup = document.getElementById('market-event-popup');
    if (popup) popup.remove();
    // Create popup
    popup = document.createElement('div');
    popup.id = 'market-event-popup';
    popup.className = 'market-event-popup neon-glow';
    popup.innerHTML = `
        <span class="event-emoji">${event.emoji}</span>
        <span class="event-title">${event.name}</span>
        <span class="event-desc">${event.desc}</span>
    `;
    document.body.appendChild(popup);
    // Animate in
    setTimeout(() => popup.classList.add('show'), 10);
    // Auto-hide after 5s
    clearTimeout(eventPopupTimeout);
    eventPopupTimeout = setTimeout(() => {
        popup.classList.remove('show');
        setTimeout(() => popup.remove(), 500);
    }, 5000);
}

function pollMarketEvents() {
    fetch('/api/market_events')
        .then(res => res.json())
        .then(events => {
            if (events.length > 0) {
                const latest = events[0];
                if (lastEventTime !== latest.time) {
                    lastEventTime = latest.time;
                    showMarketEventPopup(latest);
                    // Refresh chart image
                    const img = document.getElementById('market-graph-img');
                    if (img) img.src = '/static/market_graph.png?v=' + Date.now();
                }
            }
        });
}

// Start polling when market tab is open
let marketEventInterval = null;
function showMarketTab() {
    document.getElementById('main-app').classList.add('hidden');
    document.getElementById('market-tab').style.display = 'block';
    fetch('/api/available_animals')
        .then(res => res.json())
        .then(animals => {
            const pricesContainer = document.getElementById('market-prices');
            pricesContainer.innerHTML = '';
            animals.forEach(animal => {
                const priceItem = document.createElement('div');
                priceItem.className = 'market-price-item';
                priceItem.innerHTML = `
                    <span class="market-price-emoji">${getAnimalEmoji(animal.name)}</span>
                    <div class="market-price-info">
                        <div class="market-price-name">${animal.name}</div>
                        <div class="market-price-value">$${animal.base_price[0]} - $${animal.base_price[1]}</div>
                    </div>
                `;
                pricesContainer.appendChild(priceItem);
            });
            document.getElementById('market-graph-img').src = '/static/market_graph.png?v=' + Date.now();
            const legend = document.querySelector('.market-graph-legend');
            legend.innerHTML = animals.map(animal => 
                `<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">
                    <span>${getAnimalEmoji(animal.name)}</span>
                    <span>${animal.name}</span>
                </div>`
            ).join('');
        });
    // Start polling for events
    if (!marketEventInterval) {
        pollMarketEvents();
        marketEventInterval = setInterval(pollMarketEvents, 5000);
    }
}
function hideMarketTab() {
    document.getElementById('main-app').classList.remove('hidden');
    document.getElementById('market-tab').style.display = 'none';
    // Stop polling
    if (marketEventInterval) {
        clearInterval(marketEventInterval);
        marketEventInterval = null;
    }
}

function getAnimalEmoji(name) {
    const emojiMap = {
        'Chicken': '🐔',
        'Goat': '🐐',
        'Sheep': '🐑',
        'Pig': '🐖',
        'Cow': '🐄',
        'Horse': '🐎'
    };
    return emojiMap[name] || '🐔';
}

// --- Market Feed Frontend Logic ---
let lastFeedIds = [];
function renderMarketFeed(feed) {
    const feedContainer = document.getElementById('market-feed');
    if (!feedContainer) return;
    // Only show the latest 10
    const latest = feed.slice(0, 10);
    // Animate new entries
    let html = '';
    latest.forEach(item => {
        const isNew = !lastFeedIds.includes(item.id);
        html += `<div class="market-feed-item${isNew ? ' feed-new' : ''} feed-type-${item.type}">${item.msg}</div>`;
    });
    feedContainer.innerHTML = html;
    // Animate in
    setTimeout(() => {
        document.querySelectorAll('.market-feed-item.feed-new').forEach(el => {
            el.classList.remove('feed-new');
        });
    }, 100);
    lastFeedIds = latest.map(item => item.id);
}

function pollMarketFeed() {
    fetch('/api/market_feed')
        .then(res => res.json())
        .then(feed => {
            renderMarketFeed(feed);
        });
}

// Patch showMarketTab/hideMarketTab to start/stop feed polling
let marketFeedInterval = null;
const originalShowMarketTab = showMarketTab;
showMarketTab = function() {
    originalShowMarketTab();
    pollMarketFeed();
    if (!marketFeedInterval) {
        marketFeedInterval = setInterval(pollMarketFeed, 4000);
    }
};
const originalHideMarketTab = hideMarketTab;
hideMarketTab = function() {
    originalHideMarketTab();
    if (marketFeedInterval) {
        clearInterval(marketFeedInterval);
        marketFeedInterval = null;
    }
};

// Chaos Chicken Challenge Functions
function startChaosChicken(user) {
    if (!socket.connected) {
        console.error('Socket not connected!');
        alert('Not connected to server. Please refresh the page and try again.');
        return;
    }
    
    if (user !== currentUser) {
        alert("You can only start challenges for your own user!");
        return;
    }
    
    socket.emit('start_chaos_chicken', {
        user: user,
        current_user: currentUser
    });
}

function completeChaosChicken(user, success) {
    if (!socket.connected) {
        console.error('Socket not connected!');
        alert('Not connected to server. Please refresh the page and try again.');
        return;
    }
    
    if (user !== currentUser) {
        alert("You can only complete challenges for your own user!");
        return;
    }
    
    socket.emit('complete_chaos_chicken', {
        user: user,
        current_user: currentUser,
        success: success
    });
}

function updateChaosChickenUI(data) {
    const userKey = data.user === '4keni' ? 'keni' : 'luu';
    const challengeSection = document.getElementById(`${userKey}-chaos-chicken`);
    
    if (data.weekly_chaos_chicken.offered && data.weekly_chaos_chicken.offered_to === data.user) {
        // Show the challenge section
        challengeSection.classList.remove('hidden');
        
        // Update challenge description
        const description = challengeSection.querySelector('.challenge-description');
        description.textContent = data.weekly_chaos_chicken.description;
        
        // Update button state
        const startBtn = challengeSection.querySelector('.start-challenge-btn');
        if (data.weekly_chaos_chicken.accepted) {
            startBtn.disabled = true;
            startBtn.textContent = 'Challenge in Progress';
        } else {
            startBtn.disabled = false;
            startBtn.textContent = 'Accept Challenge';
        }
    } else {
        // Hide the challenge section
        challengeSection.classList.add('hidden');
    }
}

// Add socket event listeners for chaos chicken
socket.on('chaos_chicken_started', (data) => {
    const userKey = data.user === '4keni' ? 'keni' : 'luu';
    const challengeSection = document.getElementById(`${userKey}-chaos-chicken`);
    const startBtn = challengeSection.querySelector('.start-challenge-btn');
    
    startBtn.disabled = true;
    startBtn.textContent = 'Challenge in Progress';
    
    // Show a notification
    showNotification(`${data.user} has started a chaos chicken challenge!`);
});

socket.on('chaos_chicken_completed', (data) => {
    const userKey = data.user === '4keni' ? 'keni' : 'luu';
    const challengeSection = document.getElementById(`${userKey}-chaos-chicken`);
    
    // Hide the challenge section
    challengeSection.classList.add('hidden');
    
    // Show a notification
    if (data.success) {
        showNotification(`${data.user} has completed the chaos chicken challenge and earned ${data.points_earned} points!`);
    } else {
        showNotification(`${data.user} has failed the chaos chicken challenge.`);
    }
}); 