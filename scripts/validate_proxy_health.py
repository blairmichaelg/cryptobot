#!/usr/bin/env python3
"""
Proxy Health Validation Script

Tests all configured proxies and generates a comprehensive health report.
Validates proxy connectivity, measures latency, and updates proxy_health.json.
"""

import asyncio
import aiohttp
import json
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import statistics

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG_DIR

# Configuration
HEALTH_FILE = CONFIG_DIR / "proxy_health.json"
PROXIES_FILE = CONFIG_DIR / "proxies.txt"
TEST_URLS = [
    "http://ipinfo.io/ip",
    "https://www.google.com",
    "https://api.ipify.org?format=json"
]
TIMEOUT_SECONDS = 15
MAX_CONCURRENT = 10
DEAD_THRESHOLD_MS = 5000


class ProxyHealthValidator:
    def __init__(self):
        self.results: Dict[str, Dict] = {}
        self.proxies: List[str] = []
        
    def load_proxies(self) -> int:
        """Load proxies from config file."""
        if not PROXIES_FILE.exists():
            print(f"❌ Proxy file not found: {PROXIES_FILE}")
            return 0
            
        with open(PROXIES_FILE, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
        self.proxies = lines
        print(f"📋 Loaded {len(self.proxies)} proxies from {PROXIES_FILE}")
        return len(self.proxies)
        
    def _proxy_key(self, proxy_url: str) -> str:
        """Extract key from proxy URL for tracking."""
        try:
            parsed = urlparse(proxy_url)
            if parsed.username and parsed.password:
                return f"{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
            return f"{parsed.hostname}:{parsed.port}"
        except Exception:
            return proxy_url
            
    def _mask_proxy(self, proxy_url: str) -> str:
        """Mask sensitive credentials in proxy URL."""
        try:
            parsed = urlparse(proxy_url)
            if parsed.username:
                masked_user = parsed.username[:8] + "..." if len(parsed.username) > 8 else parsed.username
                return f"{parsed.scheme}://{masked_user}@{parsed.hostname}:{parsed.port}"
            return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        except Exception:
            return proxy_url[:30] + "..."
            
    async def test_proxy(self, proxy_url: str, test_url: str) -> Tuple[bool, float, Optional[str]]:
        """
        Test a single proxy against a test URL.
        
        Returns:
            (success, latency_ms, error_message)
        """
        start_time = time.time()
        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy_url) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    if resp.status == 200:
                        # Try to read response to ensure it's valid
                        _ = await resp.text()
                        return (True, latency_ms, None)
                    else:
                        return (False, latency_ms, f"HTTP {resp.status}")
        except asyncio.TimeoutError:
            latency_ms = TIMEOUT_SECONDS * 1000
            return (False, latency_ms, "Timeout")
        except aiohttp.ClientProxyConnectionError as e:
            latency_ms = (time.time() - start_time) * 1000
            return (False, latency_ms, f"Proxy connection error: {str(e)[:50]}")
        except aiohttp.ClientError as e:
            latency_ms = (time.time() - start_time) * 1000
            return (False, latency_ms, f"Client error: {str(e)[:50]}")
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return (False, latency_ms, f"Error: {str(e)[:50]}")
            
    async def validate_proxy(self, proxy_url: str) -> Dict:
        """
        Validate a proxy against all test URLs.
        
        Returns:
            Dict with health metrics
        """
        proxy_key = self._proxy_key(proxy_url)
        masked_proxy = self._mask_proxy(proxy_url)
        
        print(f"\n🔍 Testing: {masked_proxy}")
        
        results = []
        latencies = []
        errors = []
        
        # Test against each URL
        for test_url in TEST_URLS:
            success, latency, error = await self.test_proxy(proxy_url, test_url)
            results.append(success)
            
            if success:
                latencies.append(latency)
                print(f"  ✅ {test_url}: {latency:.0f}ms")
            else:
                print(f"  ❌ {test_url}: {error}")
                errors.append(error)
                
        # Calculate metrics
        success_count = sum(results)
        success_rate = success_count / len(TEST_URLS)
        
        avg_latency = statistics.mean(latencies) if latencies else None
        min_latency = min(latencies) if latencies else None
        max_latency = max(latencies) if latencies else None
        
        is_healthy = success_rate >= 0.66  # At least 2/3 tests pass
        is_dead = success_rate == 0
        
        status = "🟢 HEALTHY" if is_healthy else ("🔴 DEAD" if is_dead else "🟡 DEGRADED")
        
        summary = {
            "proxy_key": proxy_key,
            "masked_url": masked_proxy,
            "success_count": success_count,
            "total_tests": len(TEST_URLS),
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "is_healthy": is_healthy,
            "is_dead": is_dead,
            "errors": errors,
            "timestamp": time.time()
        }
        
        print(f"  {status} - Success: {success_count}/{len(TEST_URLS)}", end="")
        if avg_latency:
            print(f" - Avg Latency: {avg_latency:.0f}ms")
        else:
            print()
            
        return summary
        
    async def validate_all(self):
        """Validate all proxies with concurrency control."""
        if not self.proxies:
            print("❌ No proxies to validate")
            return
            
        print(f"\n🚀 Starting validation of {len(self.proxies)} proxies...")
        print(f"📊 Testing against {len(TEST_URLS)} endpoints")
        print(f"⏱️  Timeout: {TIMEOUT_SECONDS}s per test")
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def validate_with_semaphore(proxy_url: str):
            async with semaphore:
                return await self.validate_proxy(proxy_url)
                
        results = await asyncio.gather(*[validate_with_semaphore(p) for p in self.proxies])
        
        # Store results
        for result in results:
            self.results[result["proxy_key"]] = result
            
    def generate_report(self) -> str:
        """Generate a comprehensive health report."""
        if not self.results:
            return "No results to report"
            
        healthy = [r for r in self.results.values() if r["is_healthy"]]
        degraded = [r for r in self.results.values() if not r["is_healthy"] and not r["is_dead"]]
        dead = [r for r in self.results.values() if r["is_dead"]]
        
        all_latencies = [r["avg_latency_ms"] for r in self.results.values() if r["avg_latency_ms"]]
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    PROXY HEALTH VALIDATION REPORT                     ║
╚══════════════════════════════════════════════════════════════════════╝

📊 SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total Proxies:     {len(self.results)}
  🟢 Healthy:        {len(healthy)} ({len(healthy)/len(self.results)*100:.1f}%)
  🟡 Degraded:       {len(degraded)} ({len(degraded)/len(self.results)*100:.1f}%)
  🔴 Dead:           {len(dead)} ({len(dead)/len(self.results)*100:.1f}%)

⚡ LATENCY STATISTICS (Healthy Proxies Only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if all_latencies:
            report += f"""  Average:           {statistics.mean(all_latencies):.0f}ms
  Median:            {statistics.median(all_latencies):.0f}ms
  Min:               {min(all_latencies):.0f}ms
  Max:               {max(all_latencies):.0f}ms
  Std Dev:           {statistics.stdev(all_latencies):.0f}ms
"""
        else:
            report += "  No healthy proxies with latency data\n"
            
        # Top performers
        if healthy:
            report += "\n🏆 TOP 5 FASTEST PROXIES\n"
            report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            sorted_healthy = sorted(healthy, key=lambda x: x["avg_latency_ms"])[:5]
            for i, proxy in enumerate(sorted_healthy, 1):
                report += f"  {i}. {proxy['masked_url']}\n"
                report += f"     ⚡ {proxy['avg_latency_ms']:.0f}ms avg | {proxy['min_latency_ms']:.0f}-{proxy['max_latency_ms']:.0f}ms range\n"
                
        # Dead proxies details
        if dead:
            report += "\n💀 DEAD PROXIES (Action Required)\n"
            report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for proxy in dead:
                report += f"  ❌ {proxy['masked_url']}\n"
                if proxy['errors']:
                    report += f"     Errors: {', '.join(set(proxy['errors']))}\n"
                    
        # Degraded proxies
        if degraded:
            report += "\n⚠️  DEGRADED PROXIES (Intermittent Issues)\n"
            report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for proxy in degraded:
                report += f"  🟡 {proxy['masked_url']}\n"
                report += f"     Success: {proxy['success_count']}/{proxy['total_tests']} tests"
                if proxy['avg_latency_ms']:
                    report += f" | {proxy['avg_latency_ms']:.0f}ms avg\n"
                else:
                    report += "\n"
                if proxy['errors']:
                    report += f"     Errors: {', '.join(set(proxy['errors']))}\n"
                    
        report += "\n" + "═" * 70 + "\n"
        return report
        
    def update_health_file(self):
        """Update proxy_health.json with validation results."""
        # Load existing health file
        existing_data = {}
        if HEALTH_FILE.exists():
            try:
                with open(HEALTH_FILE, 'r') as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"⚠️  Could not load existing health file: {e}")
                
        # Update with new results
        proxy_latency = existing_data.get("proxy_latency", {})
        
        for proxy_key, result in self.results.items():
            if result["avg_latency_ms"] is not None:
                # Append to history (keep last 5)
                if proxy_key not in proxy_latency:
                    proxy_latency[proxy_key] = []
                proxy_latency[proxy_key].append(result["avg_latency_ms"])
                proxy_latency[proxy_key] = proxy_latency[proxy_key][-5:]  # Keep last 5
                
        # Clean up dead proxies from health tracking
        dead_keys = [r["proxy_key"] for r in self.results.values() if r["is_dead"]]
        for dead_key in dead_keys:
            proxy_latency.pop(dead_key, None)
            
        # Build updated health file
        health_data = {
            "version": 1,
            "timestamp": time.time(),
            "proxy_latency": proxy_latency,
            "proxy_failures": {},  # Reset failures after validation
            "dead_proxies": dead_keys,
            "proxy_cooldowns": {},  # Clear cooldowns after validation
            "proxy_reputation": {},
            "proxy_soft_signals": {},
            "proxy_host_failures": {}
        }
        
        # Save
        try:
            with open(HEALTH_FILE, 'w') as f:
                json.dump(health_data, f, indent=2)
            print(f"\n✅ Updated {HEALTH_FILE}")
            print(f"   - {len(proxy_latency)} healthy proxies tracked")
            print(f"   - {len(dead_keys)} dead proxies removed")
        except Exception as e:
            print(f"\n❌ Failed to update health file: {e}")
            
    def save_detailed_report(self):
        """Save detailed validation results to a report file."""
        report_file = CONFIG_DIR / "proxy_validation_report.json"
        
        report_data = {
            "validation_time": time.time(),
            "test_urls": TEST_URLS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "total_proxies": len(self.results),
            "healthy_count": len([r for r in self.results.values() if r["is_healthy"]]),
            "degraded_count": len([r for r in self.results.values() if not r["is_healthy"] and not r["is_dead"]]),
            "dead_count": len([r for r in self.results.values() if r["is_dead"]]),
            "detailed_results": list(self.results.values())
        }
        
        try:
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"📄 Detailed report saved to {report_file}")
        except Exception as e:
            print(f"❌ Failed to save detailed report: {e}")


async def main():
    """Main validation workflow."""
    validator = ProxyHealthValidator()
    
    # Load proxies
    count = validator.load_proxies()
    if count == 0:
        return 1
        
    # Validate all
    await validator.validate_all()
    
    # Generate and print report
    report = validator.generate_report()
    print(report)
    
    # Update health file
    validator.update_health_file()
    
    # Save detailed report
    validator.save_detailed_report()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
