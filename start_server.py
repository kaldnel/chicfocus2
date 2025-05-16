import os
import shutil
import webbrowser
import time
import subprocess

def start_server():
    print("Starting ChicFocus server...")
    
    # Check if data directory exists
    if not os.path.exists('data'):
        os.makedirs('data', exist_ok=True)
        print("Created data directory")
    
    # Clear any browser cache hints
    print("Remember to clear your browser cache (Ctrl+Shift+Del)")
    
    # Start the server process
    print("Starting server process...")
    time.sleep(1)
    
    # Open the browser
    print("Opening browser...")
    webbrowser.open('http://localhost:5000')
    
    # Start the actual server
    subprocess.call(["python", "app.py"])

if __name__ == "__main__":
    start_server() 