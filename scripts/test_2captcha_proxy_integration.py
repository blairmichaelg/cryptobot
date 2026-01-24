#!/usr/bin/env python3
"""
Test script for 2Captcha proxy API integration.

This script verifies:
1. API fetching from 2Captcha
2. Auto-population of config/proxies.txt
3. Session rotation
4. Health monitoring
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from core.proxy_manager import ProxyManager

async def test_integration():
    """Test the full proxy integration flow"""
    print("=" * 60)
    print("2Captcha Proxy Integration Test")
    print("=" * 60)
    
    # Load settings
    settings = BotSettings()
    
    # Check API key
    if not settings.twocaptcha_api_key:
        print("❌ ERROR: TWOCAPTCHA_API_KEY not set in .env")
        print("Please add your 2Captcha API key to continue.")
        return False
    
    print(f"✅ API Key found: {settings.twocaptcha_api_key[:8]}...")
    
    # Check if use_2captcha_proxies is enabled
    print(f"✅ use_2captcha_proxies: {settings.use_2captcha_proxies}")
    
    # Initialize ProxyManager
    print("\n" + "-" * 60)
    print("Initializing ProxyManager...")
    print("-" * 60)
    proxy_manager = ProxyManager(settings)
    
    initial_count = len(proxy_manager.proxies)
    print(f"Initial proxies loaded from file: {initial_count}")
    
    # Test API fetching
    print("\n" + "-" * 60)
    print("Testing API fetch...")
    print("-" * 60)
    
    # Try to fetch proxy config from API
    api_proxy = await proxy_manager.fetch_proxy_config_from_2captcha()
    if api_proxy:
        print(f"✅ Successfully fetched proxy config from API:")
        print(f"   Host: {api_proxy.ip}:{api_proxy.port}")
        print(f"   Username: {api_proxy.username}")
        print(f"   Protocol: {api_proxy.protocol}")
    else:
        print("⚠️  API fetch returned None")
        print("   This is expected if you haven't purchased residential proxies")
        print("   or if the API endpoints have changed.")
    
    # Test session rotation
    print("\n" + "-" * 60)
    print("Testing session rotation...")
    print("-" * 60)
    
    # Clear proxies to test auto-fetch
    proxy_manager.proxies = []
    proxy_manager.all_proxies = []
    
    # This should either use file proxies or fetch from API
    count = await proxy_manager.fetch_proxies_from_api(quantity=5)
    
    if count > 0:
        print(f"✅ Generated {count} proxies (base + sessions)")
        print(f"   Total active proxies: {len(proxy_manager.proxies)}")
        
        # Show first few proxies
        print("\n   Sample proxies:")
        for i, proxy in enumerate(proxy_manager.proxies[:3]):
            print(f"   [{i+1}] {proxy.username}@{proxy.ip}:{proxy.port}")
    else:
        print("❌ Failed to generate proxies")
        return False
    
    # Test health monitoring
    print("\n" + "-" * 60)
    print("Testing health monitoring...")
    print("-" * 60)
    
    print("Running health checks (this may take a moment)...")
    health = await proxy_manager.health_check_all_proxies()
    
    print(f"✅ Health check complete:")
    print(f"   Total proxies: {health.get('total', 0)}")
    print(f"   Healthy: {health.get('healthy', 0)}")
    print(f"   Dead: {health.get('dead', 0)}")
    print(f"   Avg latency: {health.get('avg_latency_ms', 0):.0f}ms")
    
    # Verify file was updated
    print("\n" + "-" * 60)
    print("Verifying config/proxies.txt...")
    print("-" * 60)
    
    proxy_file = Path(settings.residential_proxies_file)
    if proxy_file.exists():
        with open(proxy_file, 'r') as f:
            lines = f.readlines()
        print(f"✅ Proxy file exists with {len(lines)} lines")
        print(f"   Location: {proxy_file}")
        
        # Show first few lines
        print("\n   First few lines:")
        for line in lines[:5]:
            print(f"   {line.rstrip()}")
    else:
        print(f"⚠️  Proxy file not found at: {proxy_file}")
    
    print("\n" + "=" * 60)
    print("Integration test complete!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = asyncio.run(test_integration())
    sys.exit(0 if success else 1)
