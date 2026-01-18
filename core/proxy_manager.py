import logging
import asyncio
import aiohttp
import random
from typing import List, Dict, Optional
from dataclasses import dataclass
from core.config import AccountProfile, BotSettings

logger = logging.getLogger(__name__)

@dataclass
class Proxy:
    ip: str
    port: int
    username: str
    password: str
    protocol: str = "http"

    def to_string(self) -> str:
        """Returns the proxy string format expected by Playwright: http://user:pass@ip:port or http://ip:port"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{self.protocol}://{self.ip}:{self.port}"

    def to_2captcha_string(self) -> str:
        """Returns the proxy string format expected by 2Captcha: user:pass@ip:port or ip:port"""
        if self.username and self.password:
            return f"{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{self.ip}:{self.port}"

class ProxyManager:
    """
    Manages fetching proxies from 2Captcha and assigning them to accounts
    using a 'Sticky Session' strategy (1 Account = 1 Proxy).
    
    Also provides proxy health monitoring with latency tracking.
    """

    # Validation constants
    VALIDATION_TIMEOUT_SECONDS = 10
    VALIDATION_TEST_URL = "https://httpbin.org/ip"
    LATENCY_HISTORY_MAX = 10  # Keep last 10 latency measurements per proxy
    DEAD_PROXY_THRESHOLD_MS = 5000  # Consider proxy dead if avg latency > 5s
    DEAD_PROXY_FAILURE_COUNT = 3  # Remove after 3 consecutive failures

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.api_key = settings.twocaptcha_api_key
        self.proxies: List[Proxy] = []
        self.validated_proxies: List[Proxy] = []  # Only proxies that passed validation
        self.assignments: Dict[str, Proxy] = {}  # Map username -> Proxy
        
        # Latency tracking: proxy_key -> list of latency measurements (ms)
        self.proxy_latency: Dict[str, List[float]] = {}
        # Failure tracking for dead proxy removal
        self.proxy_failures: Dict[str, int] = {}
        # Dead proxies that have been removed
        self.dead_proxies: List[str] = []

    def _proxy_key(self, proxy: Proxy) -> str:
        """Generate a unique key for a proxy."""
        return f"{proxy.ip}:{proxy.port}"

    async def measure_proxy_latency(self, proxy: Proxy) -> Optional[float]:
        """
        Measure the latency of a proxy in milliseconds.
        
        Args:
            proxy: The proxy to measure
            
        Returns:
            Latency in milliseconds, or None if failed
        """
        import time
        proxy_url = proxy.to_string()
        proxy_key = self._proxy_key(proxy)
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.VALIDATION_TIMEOUT_SECONDS)
            start_time = time.time()
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    self.VALIDATION_TEST_URL,
                    proxy=proxy_url
                ) as resp:
                    if resp.status == 200:
                        latency_ms = (time.time() - start_time) * 1000
                        
                        # Record latency
                        if proxy_key not in self.proxy_latency:
                            self.proxy_latency[proxy_key] = []
                        self.proxy_latency[proxy_key].append(latency_ms)
                        
                        # Keep only last N measurements
                        if len(self.proxy_latency[proxy_key]) > self.LATENCY_HISTORY_MAX:
                            self.proxy_latency[proxy_key] = self.proxy_latency[proxy_key][-self.LATENCY_HISTORY_MAX:]
                        
                        # Reset failure count on success
                        self.proxy_failures[proxy_key] = 0
                        
                        logger.debug(f"📊 Proxy {proxy_key} latency: {latency_ms:.0f}ms")
                        return latency_ms
                    else:
                        self._record_failure(proxy_key)
                        return None
                        
        except asyncio.TimeoutError:
            self._record_failure(proxy_key)
            logger.warning(f"⏱️ Proxy {proxy_key} timed out during latency check")
            return None
        except Exception as e:
            self._record_failure(proxy_key)
            logger.warning(f"❌ Proxy {proxy_key} latency check failed: {e}")
            return None

    def _record_failure(self, proxy_key: str):
        """Record a proxy failure and mark as dead if threshold exceeded."""
        self.proxy_failures[proxy_key] = self.proxy_failures.get(proxy_key, 0) + 1
        if self.proxy_failures[proxy_key] >= self.DEAD_PROXY_FAILURE_COUNT:
            if proxy_key not in self.dead_proxies:
                self.dead_proxies.append(proxy_key)
                logger.error(f"☠️ Proxy {proxy_key} marked as DEAD after {self.DEAD_PROXY_FAILURE_COUNT} failures")

    def get_proxy_stats(self, proxy: Proxy) -> Dict:
        """
        Get statistics for a specific proxy.
        
        Returns:
            Dict with avg_latency, min_latency, max_latency, measurement_count, is_dead
        """
        proxy_key = self._proxy_key(proxy)
        latencies = self.proxy_latency.get(proxy_key, [])
        
        if not latencies:
            return {
                "avg_latency": None,
                "min_latency": None,
                "max_latency": None,
                "measurement_count": 0,
                "is_dead": proxy_key in self.dead_proxies
            }
        
        return {
            "avg_latency": sum(latencies) / len(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "measurement_count": len(latencies),
            "is_dead": proxy_key in self.dead_proxies
        }

    async def health_check_all_proxies(self) -> Dict[str, any]:
        """
        Perform health check on all assigned proxies, measuring latency.
        
        Returns:
            Summary of health check results
        """
        if not self.proxies:
            return {"total": 0, "healthy": 0, "dead": 0}
        
        logger.info(f"🏥 Running health check on {len(self.proxies)} proxies...")
        
        semaphore = asyncio.Semaphore(10)
        
        async def check_with_semaphore(proxy: Proxy):
            async with semaphore:
                return await self.measure_proxy_latency(proxy)
        
        results = await asyncio.gather(*[check_with_semaphore(p) for p in self.proxies])
        
        healthy = sum(1 for r in results if r is not None)
        dead = len(self.dead_proxies)
        
        summary = {
            "total": len(self.proxies),
            "healthy": healthy,
            "dead": dead,
            "avg_latency_ms": sum(r for r in results if r) / max(healthy, 1)
        }
        
        logger.info(f"🏥 Health check complete: {healthy}/{len(self.proxies)} healthy, {dead} dead")
        return summary

    def remove_dead_proxies(self) -> int:
        """
        Remove dead proxies from the active pool.
        
        Returns:
            Number of proxies removed
        """
        before_count = len(self.proxies)
        self.proxies = [p for p in self.proxies if self._proxy_key(p) not in self.dead_proxies]
        self.validated_proxies = [p for p in self.validated_proxies if self._proxy_key(p) not in self.dead_proxies]
        
        removed = before_count - len(self.proxies)
        if removed > 0:
            logger.info(f"🗑️ Removed {removed} dead proxies from pool")
        return removed

    async def validate_proxy(self, proxy: Proxy) -> bool:
        """
        Test proxy connectivity before use.
        
        Args:
            proxy: The proxy to validate
            
        Returns:
            True if proxy is working, False otherwise
        """
        proxy_url = proxy.to_string()
        try:
            timeout = aiohttp.ClientTimeout(total=self.VALIDATION_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    self.VALIDATION_TEST_URL,
                    proxy=proxy_url
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.debug(f"✅ Proxy {proxy.ip}:{proxy.port} validated (origin: {data.get('origin', 'unknown')})")
                        return True
                    else:
                        logger.warning(f"⚠️ Proxy {proxy.ip}:{proxy.port} returned status {resp.status}")
                        return False
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Proxy {proxy.ip}:{proxy.port} timed out during validation")
            return False
        except Exception as e:
            logger.warning(f"❌ Proxy {proxy.ip}:{proxy.port} validation failed: {e}")
            return False

    async def validate_all_proxies(self) -> int:
        """
        Validate all fetched proxies concurrently.
        
        Returns:
            Number of valid proxies
        """
        if not self.proxies:
            return 0
            
        logger.info(f"🔍 Validating {len(self.proxies)} proxies...")
        
        # Validate concurrently (max 10 at a time to avoid overwhelming)
        semaphore = asyncio.Semaphore(10)
        
        async def validate_with_semaphore(proxy: Proxy) -> Optional[Proxy]:
            async with semaphore:
                if await self.validate_proxy(proxy):
                    return proxy
                return None
        
        results = await asyncio.gather(*[validate_with_semaphore(p) for p in self.proxies])
        self.validated_proxies = [p for p in results if p is not None]
        
        valid_count = len(self.validated_proxies)
        logger.info(f"✅ {valid_count}/{len(self.proxies)} proxies passed validation")
        return valid_count

    async def fetch_proxies(self, count: int = 100) -> bool:
        """
        Generates proxies from 2Captcha's Proxy API.
        
        This uses the `generate_white_list_connections` endpoint which requires:
        1. Your API key
        2. Your server's public IP to be whitelisted
        3. Desired number of connections (1-2000)
        
        Returns True if proxies were successfully generated.
        """
        if not self.api_key:
            logger.error("❌ Cannot generate proxies: No 2Captcha API key provided.")
            return False

        logger.info(f"🔄 Generating {count} proxies from 2Captcha...")
        
        async with aiohttp.ClientSession() as session:
            try:
                # Step 1: Get our public IP
                async with session.get("https://api.ipify.org?format=json") as resp:
                    ip_data = await resp.json()
                    public_ip = ip_data.get("ip")
                    logger.info(f"📍 Detected Public IP: {public_ip}")
                
                # Step 2: Verify API key balance first
                async with session.get(f"https://2captcha.com/res.php?key={self.api_key}&action=getbalance&json=1") as resp:
                    data = await resp.json()
                    if data.get('status') != 1:
                        logger.error(f"❌ 2Captcha API Check Failed: {data}")
                        return False
                    logger.info(f"✅ 2Captcha Balance: ${data.get('request')}")
                
                # Step 3: Generate proxies using the whitelist API
                # Note: The IP must already be whitelisted in your 2Captcha dashboard for this to work
                gen_url = "https://api.2captcha.com/proxy/generate_white_list_connections"
                params = {
                    "key": self.api_key,
                    "ip": public_ip,
                    "protocol": "http",
                    "connection_count": min(count, 2000),  # API max is 2000
                    "json": 1
                }
                
                async with session.get(gen_url, params=params) as resp:
                    text = await resp.text()
                    try:
                        data = await resp.json()
                    except Exception:
                        logger.error(f"❌ Failed to parse 2Captcha Proxy API response as JSON. Raw response: {text}")
                        # Fallback parsing for text format if needed
                        if "OK|" in text or (":" in text and "\n" in text):
                             logger.info("ℹ️ Attempting to parse text-format proxy response")
                             # OK|ip:port\nip:port... or just ip:port\nip:port
                             clean_text = text.replace("OK|", "")
                             proxy_list = [p.strip() for p in clean_text.split("\n") if p.strip()]
                             data = {"status": 1, "request": proxy_list}
                        else:
                            return False
                    
                    if data.get("status") != 1:
                        error_msg = data.get("request", "Unknown error")
                        if "NOT_IN_WHITE_LIST" in str(error_msg).upper() or "WHITELIST" in str(error_msg).upper():
                            logger.error(f"❌ Your IP {public_ip} is not whitelisted in 2Captcha.")
                            logger.error("👉 Go to https://2captcha.com/proxy and add this IP to your whitelist.")
                        else:
                            logger.error(f"❌ Proxy generation failed: {error_msg}")
                        return False
                    
                    # Parse the proxy list from response
                    proxy_list = data.get("request", [])
                    if isinstance(proxy_list, str):
                        # Sometimes returned as newline-separated string
                        proxy_list = [p.strip() for p in proxy_list.split("\n") if p.strip()]
                    
                    if not proxy_list:
                        logger.warning("⚠️ No proxies returned from API.")
                        return False
                    
                    # Parse ip:port format into Proxy objects (whitelist = no auth needed)
                    for proxy_str in proxy_list:
                        if ":" in proxy_str:
                            parts = proxy_str.split(":")
                            self.proxies.append(Proxy(
                                ip=parts[0],
                                port=int(parts[1]),
                                username="",  # Whitelist proxies don't need auth
                                password="",
                                protocol="http"
                            ))
                    
                    logger.info(f"✅ Generated {len(self.proxies)} proxies from 2Captcha!")
                    return True
                    
            except Exception as e:
                logger.error(f"❌ Error generating proxies: {e}")
                return False

    def assign_proxies(self, profiles: List[AccountProfile]):
        """
        Assigns proxies to profiles 1:1.
        If we have proxies, we overwrite the profile.proxy field.
        """
        if not self.proxies:
            logger.warning("⚠️ No 2Captcha proxies loaded. Creating fallback assignments from config.")
            return

        logger.info(f"🔄 Assigning {len(self.proxies)} proxies to {len(profiles)} profiles (Sticky Strategy)...")
        
        for i, profile in enumerate(profiles):
            # Round-robin assignment
            proxy = self.proxies[i % len(self.proxies)]
            
            # Store assignment
            self.assignments[profile.username] = proxy
            
            # INJECT into profile
            profile.proxy = proxy.to_string()
            profile.residential_proxy = True # Assume 2Captcha proxies are residential
            
            logger.info(f"   📌 Profile '{profile.username}' -> Proxy {proxy.ip}:{proxy.port}")

    def get_proxy_for_solver(self, username: str) -> Optional[str]:
        """
        Returns the proxy string (user:pass@ip:port) for the captcha solver.
        """
        if username in self.assignments:
            return self.assignments[username].to_2captcha_string()
        return None
