#!/usr/bin/env python3
"""
Automated Proxy Health Check Script

Runs periodic proxy health checks and maintains proxy_health.json.
Can be run via cron or systemd timer for continuous monitoring.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.validate_proxy_health import ProxyHealthValidator


async def main():
    """Quick health check - faster than full validation."""
    validator = ProxyHealthValidator()
    
    # Load proxies
    count = validator.load_proxies()
    if count == 0:
        print("❌ No proxies found")
        return 1
        
    print(f"🔍 Running health check on {count} proxies...")
    
    # Validate all (concurrently)
    await validator.validate_all()
    
    # Generate summary only (no full report to reduce noise)
    results = validator.results.values()
    healthy = len([r for r in results if r["is_healthy"]])
    degraded = len([r for r in results if not r["is_healthy"] and not r["is_dead"]])
    dead = len([r for r in results if r["is_dead"]])
    
    print(f"\n✅ Health Check Complete:")
    print(f"   🟢 Healthy: {healthy}/{count} ({healthy/count*100:.1f}%)")
    if degraded > 0:
        print(f"   🟡 Degraded: {degraded}/{count}")
    if dead > 0:
        print(f"   🔴 Dead: {dead}/{count}")
        
    # Update health file
    validator.update_health_file()
    
    # Exit code: 0 if mostly healthy, 1 if >50% dead/degraded
    if (dead + degraded) > count / 2:
        print("\n⚠️  WARNING: More than 50% of proxies are unhealthy!")
        return 1
        
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
