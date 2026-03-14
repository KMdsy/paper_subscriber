#!/usr/bin/env python3
"""
Sync script to commit and push changes to GitHub.
"""
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error: {res.stderr}")
        return res.stdout.strip()
    except Exception as e:
        print(f"Exception running {cmd}: {e}")
        return None

def main():
    print("Checking for changes...")
    status = run_cmd("git status --porcelain")
    if not status:
        print("No changes to sync.")
        return

    print("Adding changes...")
    run_cmd("git add .")
    
    commit_msg = f"chore: daily update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    print(f"Committing with message: {commit_msg}")
    run_cmd(f'git commit -m "{commit_msg}"')
    
    print("Pushing to origin...")
    run_cmd("git push origin main")
    print("Sync complete.")

if __name__ == "__main__":
    main()
