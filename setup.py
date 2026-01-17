#!/usr/bin/env python3
"""Quick setup script for crypto faucet bot"""

import os
import sys
import subprocess

def run_command(cmd):
    """Run shell command"""
    try:
        subprocess.run(cmd, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("Crypto Faucet Bot - Setup")
    print("="*60 + "\n")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("ERROR: Python 3.8+ required")
        sys.exit(1)
    
    print("Step 1: Creating virtual environment...")
    if not run_command(f"{sys.executable} -m venv venv"):
        print("Failed to create venv")
        sys.exit(1)
    
    print("Step 2: Upgrading pip...")
    venv_python = os.path.join('venv', 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join('venv', 'bin', 'python')
    if not run_command(f'"{venv_python}" -m pip install --upgrade pip'):
        print("Warning: Failed to upgrade pip. Continuing...")

    print("Step 3: Installing dependencies...")
    if not run_command(f'"{venv_python}" -m pip install -r requirements.txt'):
        print("Failed to install dependencies")
        sys.exit(1)
    
    print("Step 4: Creating config file...")
    default_config = {
        "wallet_addresses": {
            "BTC": "YOUR_BTC_ADDRESS",
            "ETH": "YOUR_ETH_ADDRESS",
            "LTC": "YOUR_LTC_ADDRESS",
            "DOGE": "YOUR_DOGE_ADDRESS",
            "XRP": "YOUR_XRP_ADDRESS",
        },
        "accounts": {},
        "enabled_faucets": ["faucetpay", "fire_faucet", "cointiply"],
        "consolidation_enabled": True,
        "consolidation_threshold": 100000
    }
    with open('faucet_config.json', 'w', encoding='utf-8') as f:
        import json
        json.dump(default_config, f, indent=2)
    
    print("\n" + "="*60)
    print("Setup Complete!")
    print("="*60)
    print("\nNEXT STEPS:")
    print("1. Edit faucet_config.json with your wallet addresses")
    print("2. Run: python crypto_faucet_bot.py")
    print("3. For 24/7: python crypto_faucet_bot.py --continuous")
    print("\n")

if __name__ == '__main__':
    main()
