#!/usr/bin/env python3
"""
Cron-friendly script to refresh the 2Captcha proxy pool.

This script should be called from cron to automatically refresh proxies.

Example crontab entry (daily at 2 AM):
    0 2 * * * /path/to/cryptobot/scripts/refresh_proxies.py

The script will:
1. Check current proxy pool health
2. Refresh if healthy count is below threshold
3. Validate and filter new proxies
4. Exit cleanly with status code
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from core.proxy_manager import ProxyManager


async def refresh_proxies():
    """Refresh proxy pool if needed"""
    try:
        settings = BotSettings()
        
        # Check if auto-refresh is enabled
        if not getattr(settings, 'proxy_auto_refresh_enabled', False):
            print("Auto-refresh is disabled in configuration. Skipping.")
            return 0
        
        # Check if 2Captcha proxies are enabled
        if not getattr(settings, 'use_2captcha_proxies', False):
            print("2Captcha proxies are not enabled. Skipping.")
            return 0
        
        # Initialize ProxyManager
        pm = ProxyManager(settings)
        
        # Get configuration values
        min_healthy = getattr(settings, 'proxy_min_healthy_count', 50)
        target_count = getattr(settings, 'proxy_target_count', 100)
        max_latency = getattr(settings, 'proxy_max_latency_ms', 3000)
        
        print(f"Starting proxy refresh check...")
        print(f"  Min healthy count: {min_healthy}")
        print(f"  Target count: {target_count}")
        print(f"  Max latency: {max_latency}ms")
        
        # Run refresh
        success = await pm.auto_refresh_proxies(
            min_healthy_count=min_healthy,
            target_count=target_count,
            max_latency_ms=max_latency
        )
        
        if success:
            print("✅ Proxy refresh completed successfully")
            return 0
        else:
            print("⚠️  Proxy refresh failed")
            return 1
            
    except Exception as e:
        print(f"❌ Error during proxy refresh: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(refresh_proxies())
    sys.exit(exit_code)
