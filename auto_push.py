import os
import time
import datetime
import subprocess

def run_command(command):
    """Run a command and return its output"""
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode('utf-8'), stderr.decode('utf-8'), process.returncode

def git_status():
    """Check if there are any changes to commit"""
    stdout, stderr, code = run_command("git status --porcelain")
    return len(stdout.strip()) > 0

def commit_and_push():
    """Commit and push changes"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Add all changes
    run_command("git add .")
    
    # Commit with timestamp
    run_command(f'git commit -m "Auto-commit: {timestamp}"')
    
    # Push changes
    stdout, stderr, code = run_command("git push")
    
    if code == 0:
        print(f"✅ Successfully pushed changes at {timestamp}")
    else:
        print(f"❌ Failed to push changes: {stderr}")

def main():
    print("🔄 Auto-push script started. Press Ctrl+C to stop.")
    try:
        while True:
            if git_status():
                print("📝 Changes detected, committing and pushing...")
                commit_and_push()
            else:
                print("👍 No changes detected.")
            
            # Wait for 5 minutes before checking again
            print("⏱️ Waiting 5 minutes before checking again...")
            time.sleep(300)
    except KeyboardInterrupt:
        print("\n🛑 Auto-push script stopped.")

if __name__ == "__main__":
    main() 