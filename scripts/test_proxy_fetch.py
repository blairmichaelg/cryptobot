#!/bin/bash
# test_proxy_fetch.py
# A simple script to verify 2Captcha proxy fetching

import asyncio
import os
import sys
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import aiohttp

# Load env vars
load_dotenv()

# Add core to path
sys.path.append(os.getcwd())

from core.config import BotSettings
from core.proxy_manager import ProxyManager

IP_INFO_URLS = [
    "https://ipinfo.io/json",
    "https://ipapi.co/json"
]

async def fetch_ip_info(proxy_url: str) -> Optional[Dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url in IP_INFO_URLS:
            try:
                async with session.get(url, proxy=proxy_url) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                continue
    return None

async def test_fetch():
    print("Testing 2Captcha Proxy Fetching...")
    
    settings = BotSettings()
    
    if not settings.twocaptcha_api_key:
        print("❌ Error: TWOCAPTCHA_API_KEY not found in environment.")
        print("Please ensure .env is set up correctly.")
        return

    print(f"API Key found: {settings.twocaptcha_api_key[:4]}***")
    
    manager = ProxyManager(settings)
    
    # Try validation of existing proxies first
    print(f"Current proxies in file: {len(manager.proxies)}")
    
    print("Attempting to fetch newer proxies from API...")
    count = await manager.fetch_proxies_from_api(quantity=10)
    
    if count > 0:
        print(f"✅ Successfully fetched {count} proxies from 2Captcha!")
        print("Validating them now...")
        valid = await manager.validate_all_proxies()
        print(f"✅ Validation Complete. Healthy proxies: {valid}")

        # ISP/ASN checks for validated proxies (no credentials printed)
        if manager.validated_proxies:
            print("\nProxy ISP/ASN snapshot (via ipinfo/ipapi):")
            for proxy in manager.validated_proxies:
                info = await fetch_ip_info(proxy.to_string())
                if not info:
                    print(f"- {proxy.ip}:{proxy.port} -> info unavailable")
                    continue

                ip = info.get("ip") or info.get("query") or "unknown"
                org = info.get("org") or info.get("as") or info.get("orgname") or "unknown"
                city = info.get("city") or "unknown"
                country = info.get("country") or info.get("country_code") or "unknown"
                print(f"- {proxy.ip}:{proxy.port} -> IP: {ip}, Org: {org}, Loc: {city}, {country}")
    else:
        print("⚠️ No proxies fetched. This might mean:")
        print("  1. You haven't purchased any proxies in your 2Captcha dashboard.")
        print("  2. The API key is invalid.")
        print("  3. The API endpoint format has changed.")

if __name__ == "__main__":
    asyncio.run(test_fetch())
