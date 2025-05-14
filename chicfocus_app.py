import tkinter as tk
from tkinter import ttk, messagebox
import json
import datetime
import threading
import time
import os

class ChicfocusApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chicfocus - Focus Session Tracker")
        self.root.geometry("600x700")
        
        # Data storage
        self.data_file = "chicfocus_data.json"
        self.log_file = "chicfocus_log.txt"
        self.users = ["User 1", "User 2"]
        self.current_user = None
        self.timer_running = False
        self.timer_thread = None
        self.remaining_time = 0
        self.current_session = None
        self.break_active = False
        
        # Chicken types configuration
        self.chicken_types = {
            1: {"label": "Light Chicken", "intensity": "casual", "time": 15, "points": 1},
            2: {"label": "Medium Chicken", "intensity": "normal", "time": 30, "points": 2},
            3: {"label": "Heavy Chicken", "intensity": "deep focus", "time": 45, "points": 3}
        }
        
        # Load or initialize data
        self.load_data()
        
        # Create GUI
        self.create_login_screen()
        
    def load_data(self):
        """Load existing data or create new structure"""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "users": {
                    "User 1": {"points": 0, "sessions": []},
                    "User 2": {"points": 0, "sessions": []}
                },
                "cycle_start": datetime.datetime.now().isoformat(),
                "winner": None
            }
        
        # Check if 7-day cycle has passed
        cycle_start = datetime.datetime.fromisoformat(self.data["cycle_start"])
        if (datetime.datetime.now() - cycle_start).days >= 7:
            self.end_cycle()
    
    def save_data(self):
        """Save data to JSON file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def log_to_file(self, message):
        """Log session to text file"""
        with open(self.log_file, 'a') as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    
    def create_login_screen(self):
        """Create login interface"""
        self.clear_screen()
        
        login_frame = ttk.Frame(self.root)
        login_frame.pack(expand=True, fill='both', padx=20, pady=20)
        
        ttk.Label(login_frame, text="Chicfocus", font=("Arial", 24, "bold")).pack(pady=20)
        ttk.Label(login_frame, text="Select User:", font=("Arial", 14)).pack(pady=10)
        
        for user in self.users:
            btn = ttk.Button(login_frame, text=user, 
                           command=lambda u=user: self.login_user(u))
            btn.pack(pady=5, fill='x', padx=50)
    
    def login_user(self, user):
        """Log in selected user and show main interface"""
        self.current_user = user
        self.create_main_interface()
    
    def create_main_interface(self):
        """Create main application interface"""
        self.clear_screen()
        
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(header_frame, text=f"Welcome, {self.current_user}!", 
                 font=("Arial", 16, "bold")).pack(side='left')
        
        ttk.Button(header_frame, text="Logout", 
                  command=self.create_login_screen).pack(side='right')
        
        # Task input section
        task_frame = ttk.LabelFrame(self.root, text="Start New Chicken")
        task_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(task_frame, text="Task Name:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.task_name_var = tk.StringVar()
        ttk.Entry(task_frame, textvariable=self.task_name_var, width=30).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(task_frame, text="Chicken Tier:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.tier_var = tk.IntVar(value=1)
        tier_frame = ttk.Frame(task_frame)
        tier_frame.grid(row=1, column=1, sticky='w', padx=5, pady=5)
        
        for tier, info in self.chicken_types.items():
            ttk.Radiobutton(tier_frame, text=f"Tier {tier} ({info['time']}min - {info['points']}pts)", 
                           variable=self.tier_var, value=tier).pack(anchor='w')
        
        ttk.Button(task_frame, text="Start Chicken", 
                  command=self.start_chicken).grid(row=2, column=0, columnspan=2, pady=10)
        
        # Timer section
        timer_frame = ttk.LabelFrame(self.root, text="Timer")
        timer_frame.pack(fill='x', padx=10, pady=5)
        
        self.timer_label = ttk.Label(timer_frame, text="00:00", font=("Arial", 32, "bold"))
        self.timer_label.pack(pady=10)
        
        self.status_label = ttk.Label(timer_frame, text="Ready to start", font=("Arial", 12))
        self.status_label.pack()
        
        timer_buttons = ttk.Frame(timer_frame)
        timer_buttons.pack(pady=10)
        
        self.pause_btn = ttk.Button(timer_buttons, text="Pause", command=self.pause_timer, state='disabled')
        self.pause_btn.pack(side='left', padx=5)
        
        self.reset_btn = ttk.Button(timer_buttons, text="Reset", command=self.reset_timer, state='disabled')
        self.reset_btn.pack(side='left', padx=5)
        
        # Scoreboard section
        self.create_scoreboard()
        
        # Log section
        self.create_log_viewer()
        
        # Cycle management
        cycle_frame = ttk.Frame(self.root)
        cycle_frame.pack(fill='x', padx=10, pady=5)
        
        cycle_start = datetime.datetime.fromisoformat(self.data["cycle_start"])
        days_remaining = 7 - (datetime.datetime.now() - cycle_start).days
        ttk.Label(cycle_frame, text=f"Days remaining in cycle: {max(0, days_remaining)}").pack(side='left')
        
        ttk.Button(cycle_frame, text="End Cycle", command=self.end_cycle).pack(side='right')
    
    def create_scoreboard(self):
        """Create scoreboard display"""
        score_frame = ttk.LabelFrame(self.root, text="Current Scoreboard")
        score_frame.pack(fill='x', padx=10, pady=5)
        
        for user in self.users:
            points = self.calculate_points(user)
            sessions_today = len([s for s in self.data["users"][user]["sessions"] 
                                if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
            
            user_frame = ttk.Frame(score_frame)
            user_frame.pack(fill='x', padx=5, pady=2)
            
            ttk.Label(user_frame, text=f"{user}: {points} pts ({sessions_today}/5 chickens today)", 
                     font=("Arial", 12, "bold" if user == self.current_user else "normal")).pack(side='left')
    
    def create_log_viewer(self):
        """Create log viewer with clickable entries"""
        log_frame = ttk.LabelFrame(self.root, text="Chicken Log")
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create treeview for log
        columns = ("User", "Tier", "Task", "Date", "Points")
        self.log_tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.log_tree.heading(col, text=col)
            self.log_tree.column(col, width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scrollbar.set)
        
        self.log_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Load recent sessions
        self.update_log_viewer()
    
    def update_log_viewer(self):
        """Update log viewer with recent sessions"""
        # Clear existing items
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
        
        # Get all sessions from all users, sorted by timestamp
        all_sessions = []
        for user in self.users:
            for session in self.data["users"][user]["sessions"]:
                session["user"] = user
                all_sessions.append(session)
        
        all_sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Add last 50 sessions
        for session in all_sessions[:50]:
            date_str = datetime.datetime.fromisoformat(session["timestamp"]).strftime("%m/%d %H:%M")
            tier_info = self.chicken_types[session["tier"]]
            points = self.calculate_session_points(session["user"], session)
            
            self.log_tree.insert('', 'end', values=(
                session["user"],
                f"Tier {session['tier']}",
                session["task_name"][:20] + "..." if len(session["task_name"]) > 20 else session["task_name"],
                date_str,
                f"+{points}"
            ))
    
    def start_chicken(self):
        """Start a new chicken session"""
        task_name = self.task_name_var.get().strip()
        if not task_name:
            messagebox.showerror("Error", "Please enter a task name!")
            return
        
        tier = self.tier_var.get()
        
        # Check daily limit
        sessions_today = len([s for s in self.data["users"][self.current_user]["sessions"] 
                            if datetime.datetime.fromisoformat(s["timestamp"]).date() == datetime.date.today()])
        
        if sessions_today >= 5:
            messagebox.showerror("Daily Limit", "You've reached the maximum of 5 chickens per day!")
            return
        
        # Create session object
        self.current_session = {
            "task_name": task_name,
            "tier": tier,
            "timestamp": datetime.datetime.now().isoformat(),
            "completed": False
        }
        
        # Start timer
        self.remaining_time = self.chicken_types[tier]["time"] * 60  # Convert to seconds
        self.timer_running = True
        self.break_active = False
        
        # Update UI
        self.status_label.config(text=f"Working on: {task_name} (Tier {tier})")
        self.pause_btn.config(state='normal')
        self.reset_btn.config(state='normal')
        
        # Start timer thread
        self.timer_thread = threading.Thread(target=self.run_timer)
        self.timer_thread.daemon = True
        self.timer_thread.start()
        
        # Log start
        self.log_to_file(f"{self.current_user} started Tier {tier} - {task_name}")
    
    def run_timer(self):
        """Run timer in separate thread"""
        while self.timer_running and self.remaining_time > 0:
            minutes, seconds = divmod(self.remaining_time, 60)
            self.root.after(0, lambda: self.timer_label.config(text=f"{minutes:02d}:{seconds:02d}"))
            time.sleep(1)
            self.remaining_time -= 1
        
        if self.remaining_time <= 0 and self.timer_running:
            if not self.break_active:
                # Chicken completed, start break
                self.root.after(0, self.start_break)
            else:
                # Break completed
                self.root.after(0, self.complete_session)
    
    def start_break(self):
        """Start 5-minute break after chicken completion"""
        self.break_active = True
        self.remaining_time = 5 * 60  # 5 minutes
        self.status_label.config(text="Break time! 🐥")
        
        # Save completed chicken
        self.current_session["completed"] = True
        self.data["users"][self.current_user]["sessions"].append(self.current_session.copy())
        self.save_data()
        
        # Continue timer for break
        self.timer_thread = threading.Thread(target=self.run_timer)
        self.timer_thread.daemon = True
        self.timer_thread.start()
        
        # Log completion
        tier = self.current_session["tier"]
        task_name = self.current_session["task_name"]
        self.log_to_file(f"{self.current_user} completed Tier {tier} - {task_name}")
    
    def complete_session(self):
        """Complete the entire session (chicken + break)"""
        self.timer_running = False
        self.break_active = False
        self.current_session = None
        
        # Update UI
        self.timer_label.config(text="00:00")
        self.status_label.config(text="Session completed! 🎉")
        self.pause_btn.config(state='disabled')
        self.reset_btn.config(state='disabled')
        
        # Clear task name
        self.task_name_var.set("")
        
        # Refresh scoreboard and log
        self.create_scoreboard()
        self.update_log_viewer()
        
        messagebox.showinfo("Session Complete", "Great job! Your chicken is done. 🐥")
    
    def pause_timer(self):
        """Pause/resume timer"""
        self.timer_running = not self.timer_running
        
        if self.timer_running:
            self.pause_btn.config(text="Pause")
            self.timer_thread = threading.Thread(target=self.run_timer)
            self.timer_thread.daemon = True
            self.timer_thread.start()
        else:
            self.pause_btn.config(text="Resume")
    
    def reset_timer(self):
        """Reset current timer"""
        self.timer_running = False
        self.break_active = False
        self.current_session = None
        
        # Update UI
        self.timer_label.config(text="00:00")
        self.status_label.config(text="Ready to start")
        self.pause_btn.config(state='disabled', text="Pause")
        self.reset_btn.config(state='disabled')
        
        # Clear task name
        self.task_name_var.set("")
    
    def calculate_points(self, user):
        """Calculate total points for a user with bonuses/penalties"""
        sessions = self.data["users"][user]["sessions"]
        total_points = 0
        
        for i, session in enumerate(sessions):
            if not session.get("completed", False):
                continue
                
            points = self.calculate_session_points(user, session, i)
            total_points += points
        
        return total_points
    
    def calculate_session_points(self, user, session, session_index=None):
        """Calculate points for a single session with bonuses/penalties"""
        if not session.get("completed", False):
            return 0
        
        base_points = self.chicken_types[session["tier"]]["points"]
        sessions = self.data["users"][user]["sessions"]
        
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
        
        return max(0, base_points)  # Ensure points don't go negative
    
    def end_cycle(self):
        """End current 7-day cycle and determine winner"""
        user1_points = self.calculate_points("User 1")
        user2_points = self.calculate_points("User 2")
        
        if user1_points > user2_points:
            winner = "User 1"
        elif user2_points > user1_points:
            winner = "User 2"
        else:
            winner = "Tie"
        
        # Show results
        if winner == "Tie":
            message = f"It's a tie! Both users have {user1_points} points.\nYou'll need to decide together who chooses the next date!"
        else:
            loser = "User 2" if winner == "User 1" else "User 1"
            message = f"🎉 {winner} wins with {max(user1_points, user2_points)} points!\n\n{winner} gets to choose who picks the next date activity."
        
        messagebox.showinfo("Cycle Complete", message)
        
        # Reset cycle
        self.data = {
            "users": {
                "User 1": {"points": 0, "sessions": []},
                "User 2": {"points": 0, "sessions": []}
            },
            "cycle_start": datetime.datetime.now().isoformat(),
            "winner": winner
        }
        self.save_data()
        
        # Log cycle end
        self.log_to_file(f"Cycle ended. Winner: {winner}. User 1: {user1_points}, User 2: {user2_points}")
        
        # Refresh interface
        if hasattr(self, 'current_user') and self.current_user:
            self.create_main_interface()
    
    def clear_screen(self):
        """Clear all widgets from root window"""
        for widget in self.root.winfo_children():
            widget.destroy()
    
    def run(self):
        """Start the application"""
        self.root.mainloop()

if __name__ == "__main__":
    app = ChicfocusApp()
    app.run() 