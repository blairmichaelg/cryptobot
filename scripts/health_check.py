#!/usr/bin/env python3
"""
Cryptobot Health Check Utility
Professional tool for monitoring the bot's health and system resources.
"""

import os
import sys
import time
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# Relative path hack to reach core.config if run from scripts/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from core.config import LOG_DIR, CONFIG_DIR, PROJECT_ROOT
except ImportError:
    # Fallback for direct execution without proper PYTHONPATH
    PROJECT_ROOT = Path(__file__).parent.parent.absolute()
    LOG_DIR = PROJECT_ROOT / "logs"
    CONFIG_DIR = PROJECT_ROOT / "config"

def format_size(size_bytes):
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def check_service():
    if os.name == 'nt':
        return "N/A (Windows)"
    
    try:
        result = subprocess.run(['systemctl', 'is-active', 'cryptobot.service'], 
                              capture_output=True, text=True)
        status = result.stdout.strip()
        if status == 'active':
            return "[OK] Active"
        return f"[FAIL] {status}"
    except:
        return "[?] Unknown (Check if systemd is available)"

def check_heartbeat():
    heartbeat_file = LOG_DIR / "heartbeat.txt"
    if not heartbeat_file.exists():
        return "[FAIL] Missing"
    
    mtime = heartbeat_file.stat().st_mtime
    elapsed = time.time() - mtime
    
    if elapsed < 300: # 5 minutes
        return f"[OK] Healthy ({int(elapsed)}s ago)"
    return f"[WARN] Stale ({int(elapsed/60)}m ago)"

def check_errors():
    log_file = LOG_DIR / "faucet_bot.log"
    if not log_file.exists():
        return "None Found"
    
    try:
        # Check last 100 lines for errors
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-100:]
            errors = [l for l in last_lines if "[ERROR]" in l or "[CRITICAL]" in l]
            if not errors:
                return "[OK] No errors in last 100 lines"
            return f"[WARN] {len(errors)} errors found in last 100 lines"
    except:
        return "[?] Error reading logs"

def main():
    print("\n" + "="*60)
    print(f"Cryptobot Health Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    print(f"\n[System Status]")
    print(f"Service Status:   {check_service()}")
    print(f"Heartbeat:        {check_heartbeat()}")
    
    print(f"\n[Environment]")
    print(f"Project Root:     {PROJECT_ROOT}")
    print(f"Config Dir:       {CONFIG_DIR}")
    print(f"Logs Dir:         {LOG_DIR}")
    
    print(f"\n[Storage]")
    total, used, free = shutil.disk_usage("/")
    print(f"Disk Usage:       {format_size(used)} / {format_size(total)} ({int(used/total*100)}%)")
    
    print(f"\n[Logs Analysis]")
    print(f"Log Status:       {check_errors()}")
    
    print("\n" + "="*60)
    print("Use 'tail -f logs/faucet_bot.log' for real-time monitoring.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
