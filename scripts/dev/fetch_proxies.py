#!/usr/bin/env python3
"""
Simple script to manually fetch and populate 2Captcha residential proxies.

Usage:
    python3 fetch_proxies.py [--count 100] [--validate] [--max-latency 3000]

Examples:
    # Fetch 50 proxies with validation
    python3 fetch_proxies.py --count 50 --validate
    
    # Fetch 100 proxies without validation (faster)
    python3 fetch_proxies.py --count 100
    
    # Fetch proxies with custom latency limit
    python3 fetch_proxies.py --count 75 --validate --max-latency 2000
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from core.proxy_manager import ProxyManager


async def main():
    parser = argparse.ArgumentParser(
        description='Fetch residential proxies from 2Captcha API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--count', 
        type=int, 
        default=100,
        help='Number of proxies to fetch (default: 100)'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate proxies before adding to pool (recommended)'
    )
    
    parser.add_argument(
        '--max-latency',
        type=float,
        default=3000,
        help='Maximum acceptable latency in milliseconds (default: 3000)'
    )
    
    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Skip latency filtering (keep all proxies regardless of speed)'
    )
    
    args = parser.parse_args()
    
    # Load settings
    settings = BotSettings()
    
    # Verify prerequisites
    if not settings.twocaptcha_api_key:
        print("❌ ERROR: TWOCAPTCHA_API_KEY not set in .env")
        print("Please add your 2Captcha API key to continue.")
        return 1
    
    if settings.proxy_provider != "2captcha":
        print(f"⚠️  Warning: PROXY_PROVIDER is set to '{settings.proxy_provider}'")
        print("   This script only works with proxy_provider='2captcha'")
        print("   Continuing anyway...")
    
    # Initialize ProxyManager
    print(f"Initializing ProxyManager...")
    pm = ProxyManager(settings)
    
    # Fetch proxies
    print(f"\nFetching {args.count} proxies from 2Captcha...")
    print(f"  Validate: {args.validate}")
    print(f"  Max latency: {args.max_latency}ms")
    print(f"  Filter by latency: {not args.no_filter}")
    print()
    
    try:
        count = await pm.fetch_2captcha_proxies(
            count=args.count,
            validate=args.validate,
            max_latency_ms=0 if args.no_filter else args.max_latency
        )
        
        if count > 0:
            print(f"\n✅ Successfully added {count} proxies to pool")
            print(f"   Proxies saved to: {settings.residential_proxies_file}")
            return 0
        else:
            print(f"\n❌ Failed to add any proxies")
            print("   Check the logs above for details")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
