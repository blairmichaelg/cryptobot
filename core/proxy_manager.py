import logging
import asyncio
import aiohttp
import random
import string
import os
import time
from typing import List, Dict, Optional, Any
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
        elif self.username:
            # Fix #35: Keep username even if password is empty (Common for whitelisted sessions)
            return f"{self.protocol}://{self.username}@{self.ip}:{self.port}"
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
    VALIDATION_TIMEOUT_SECONDS = 15
    VALIDATION_TEST_URL = "https://www.google.com"
    LATENCY_HISTORY_MAX = 5  # Keep last 5 latency measurements per proxy
    DEAD_PROXY_THRESHOLD_MS = 5000  # Consider proxy dead if avg latency > 5s
    DEAD_PROXY_FAILURE_COUNT = 3  # Remove after 3 consecutive failures

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.api_key = settings.twocaptcha_api_key
        self.proxies: List[Proxy] = []
        self.all_proxies: List[Proxy] = [] # Fix: Master list to preserve proxies during cooldown
        self.validated_proxies: List[Proxy] = []  # Only proxies that passed validation
        self.assignments: Dict[str, Proxy] = {}  # Map username -> Proxy
        
        # Latency tracking: proxy_key -> list of latency measurements (ms)
        self.proxy_latency: Dict[str, List[float]] = {}
        # Failure tracking for dead proxy removal
        self.proxy_failures: Dict[str, int] = {}
        # Dead proxies that have been removed
        self.dead_proxies: List[str] = []
        # Cooldown tracking: proxy_key -> timestamp when it can be reused
        self.proxy_cooldowns: Dict[str, float] = {}
        # Cooldown durations (seconds)
        self.DETECTION_COOLDOWN = 3600  # 1 hour for 403/Detection
        self.FAILURE_COOLDOWN = 300      # 5 minutes for connection errors

        # Auto-load on init
        self.load_proxies_from_file()

    def _proxy_key(self, proxy: Proxy) -> str:
        """Generate a unique key for a proxy (full string with session)."""
        return proxy.to_string().split("://", 1)[1] if "://" in proxy.to_string() else proxy.to_string()



    async def measure_proxy_latency(self, proxy: Proxy) -> Optional[float]:
        """
        Measure the latency of a proxy in milliseconds.
        
        Args:
            proxy: The proxy to measure
            
        Returns:
            Latency in milliseconds, or None if failed
        """
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
                        
                        logger.debug(f"[LATENCY] Proxy {proxy_key} latency: {latency_ms:.0f}ms")
                        return latency_ms
                    else:
                        self.record_failure(proxy_url)
                        return None
                        
        except asyncio.TimeoutError:
            self.record_failure(proxy_url)
            logger.warning(f"[TIMEOUT] Proxy {proxy_key} timed out during latency check")
            return None
        except Exception as e:
            self.record_failure(proxy_url)
            logger.warning(f"[ERROR] Proxy {proxy_key} latency check failed: {e}")
            return None

    def record_failure(self, proxy_str: str, detected: bool = False):
        """
        Record a proxy failure.
        
        Args:
            proxy_str: The full proxy URL string
            detected: Whether the proxy was specifically detected as a bot by a site
        """
        # Use FULL proxy string as key (including session ID) to track each session independently
        # This prevents burning all sessions when one session is detected
        proxy_key = proxy_str
        
        # Normalize the key: remove protocol prefix but keep everything else (including session)
        if "://" in proxy_key:
            proxy_key = proxy_key.split("://", 1)[1]  # Remove http:// or https://
            
        self.proxy_failures[proxy_key] = self.proxy_failures.get(proxy_key, 0) + 1
        
        if detected:
            # Detection: Put on long cooldown
            self.proxy_cooldowns[proxy_key] = time.time() + self.DETECTION_COOLDOWN
            logger.error(f"[BURNED] Proxy session detected by site. Cooldown for {self.DETECTION_COOLDOWN/60:.0f}m: {proxy_key}")
        else:
        # Check if we need to remove from ALL pool if truly dead
        if self.proxy_failures[proxy_key] >= self.DEAD_PROXY_FAILURE_COUNT * 2:
            if proxy_key not in self.dead_proxies:
                self.dead_proxies.append(proxy_key)
                logger.error(f"[DEAD] Proxy {proxy_key} removed permanently after multiple cooldowns.")

        self.remove_dead_proxies()
        
        if len(self.proxies) < 5 and self.settings.use_2captcha_proxies:
            logger.warning("📉 Proxy pool low (< 5). Triggering background replenishment...")
            asyncio.create_task(self.fetch_proxies_from_api(100))

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

    async def health_check_all_proxies(self) -> Dict[str, Any]:
        """
        Perform health check on all assigned proxies, measuring latency.
        
        Returns:
            Summary of health check results
        """
        if not self.proxies:
            return {"total": 0, "healthy": 0, "dead": 0}
        
        logger.info(f"[HEALTH] Running health check on {len(self.proxies)} proxies...")
        
        semaphore = asyncio.Semaphore(10)
        
        async def check_with_semaphore(proxy: Proxy):
            async with semaphore:
                return await self.measure_proxy_latency(proxy)
        
        results = await asyncio.gather(*[check_with_semaphore(p) for p in self.proxies])
        
        healthy = sum(1 for r in results if r is not None)
        dead = len(self.dead_proxies)
        
        # Calculate average latency of HEALTHY proxies
        valid_latencies = [r for r in results if r is not None]
        avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
        
        summary = {
            "total": len(self.proxies),
            "healthy": healthy,
            "dead": dead,
            "avg_latency_ms": avg_latency
        }
        
        logger.info(f"[HEALTH] Health check complete: {healthy}/{len(self.proxies)} healthy, {dead} dead")
        return summary

    def remove_dead_proxies(self) -> int:
        """
        Remove dead or slow proxies from the active pool.
        
        Returns:
            Number of proxies removed
        """
        before_count = len(self.proxies)
        now = time.time()
        
        # 1. Clean up expired cooldowns
        expired = [k for k, t in self.proxy_cooldowns.items() if t < now]
        for k in expired:
            del self.proxy_cooldowns[k]
            if k in self.proxy_failures:
                self.proxy_failures[k] = 0 # Reset failures after cooldown
            logger.info(f"[RESTORE] Proxy {k} finished cooldown and is now active.")

        # 2. Filter active proxies: must NOT be in cooldown and must NOT be slow from the master list
        current_cooldowns = set(self.proxy_cooldowns.keys())
        
        # Filter proxies based on master list to allow restoration
        self.proxies = [p for p in self.all_proxies if self._proxy_key(p) not in current_cooldowns]
        self.validated_proxies = [p for p in self.validated_proxies if self._proxy_key(p) not in current_cooldowns]
        
        # 3. Filter out slow proxies (avg latency > threshold)
        slow_proxies = []
        for p in self.proxies:
            key = self._proxy_key(p)
            latencies = self.proxy_latency.get(key, [])
            if latencies and (sum(latencies) / len(latencies)) > self.DEAD_PROXY_THRESHOLD_MS:
                slow_proxies.append(key)
                self.proxy_cooldowns[key] = now + self.FAILURE_COOLDOWN # Trigger cooldown for slow ones too
        
        if slow_proxies:
            logger.warning(f"Removing {len(slow_proxies)} SLOW proxies from pool (cooldown): {slow_proxies}")
            self.proxies = [p for p in self.proxies if self._proxy_key(p) not in slow_proxies]
            self.validated_proxies = [p for p in self.validated_proxies if self._proxy_key(p) not in slow_proxies]
            
        removed = before_count - len(self.proxies)
        if removed > 0:
            logger.info(f"[CLEANUP] Removed {removed} total dead/slow proxies from pool. Remaining: {len(self.proxies)}")
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
                        logger.debug(f"[OK] Proxy {proxy.ip}:{proxy.port} validated (origin: {data.get('origin', 'unknown')})")
                        return True
                    else:
                        logger.warning(f"[WARN] Proxy {proxy.ip}:{proxy.port} returned status {resp.status}")
                        return False
        except asyncio.TimeoutError:
            logger.warning(f"[TIMEOUT] Proxy {proxy.ip}:{proxy.port} timed out during validation")
            return False
        except Exception as e:
            logger.warning(f"[ERROR] Proxy {proxy.ip}:{proxy.port} validation failed: {e}")
            return False

    async def validate_all_proxies(self) -> int:
        """
        Validate all fetched proxies concurrently.
        
        Returns:
            Number of valid proxies
        """
        if not self.proxies:
            return 0
            
        logger.info(f"[VALIDATE] Validating {len(self.proxies)} proxies...")
        
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
        logger.info(f"[OK] {valid_count}/{len(self.proxies)} proxies passed validation")
        return valid_count

    def load_proxies_from_file(self) -> int:
        """
        Loads proxies from the configured proxy file (default: proxies.txt).
        Expected format per line:
        - http://user:pass@host:port (Standard)
        - user:pass@host:port (Short)
        """
        import os
        file_path = self.settings.residential_proxies_file
        
        if not os.path.exists(file_path):
            logger.warning(f"[WARN] Proxy file not found: {file_path}. Creating template.")
            try:
                with open(file_path, "w") as f:
                    f.write("# Add your proxies here, one per line\n")
                    f.write("# Format: user:pass@host:port\n")
                    f.write("# Example: user123:pass456@192.168.1.1:8080\n")
            except Exception as e:
                logger.error(f"[ERROR] Could not create proxy template: {e}")
            return 0

        logger.info(f"[LOAD] Loading proxies from {file_path}...")
        count = 0
        new_proxies = []
        
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                proxy = self._parse_proxy_string(line)
                if proxy:
                    new_proxies.append(proxy)
                    count += 1
            
            self.all_proxies = new_proxies
            self.proxies = list(new_proxies)
            logger.info(f"[OK] Loaded {count} proxies from file.")
            return count
            
        except Exception as e:
            logger.error(f"[ERROR] Error loading proxies from file: {e}")
            return 0

    def _parse_proxy_string(self, proxy_str: str) -> Optional[Proxy]:
        """Parses a proxy string into a Proxy object."""
        try:
            # Strip protocol if present for easier parsing
            if "://" in proxy_str:
                protocol, rest = proxy_str.split("://", 1)
            else:
                protocol = "http"
                rest = proxy_str
            
            # Check for auth
            username = ""
            password = ""
            if "@" in rest:
                auth, endpoint = rest.split("@", 1)
                if ":" in auth:
                    username, password = auth.split(":", 1)
            else:
                endpoint = rest
            
            # Parse host:port
            if ":" not in endpoint:
                logger.warning(f"Invalid proxy format (no port): {proxy_str}")
                return None
                
            ip, port = endpoint.split(":", 1)
            
            return Proxy(
                ip=ip,
                port=int(port),
                username=username,
                password=password,
                protocol=protocol
            )
        except Exception as e:
            logger.error(f"Failed to parse proxy string '{proxy_str}': {e}")
            return None

    def rotate_session_id(self, base_username: str) -> str:
        """
        Generates a fresh 2Captcha session ID for a base username.
        
        Args:
            base_username: The base username without session parameters
            
        Returns:
            New username string with session parameter: user-session-ID
        """
        # Remove any existing session params if present
        pure_username = base_username
        if "-session-" in base_username:
            pure_username = base_username.split("-session-")[0]
            
        session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{pure_username}-session-{session_id}"

    async def generate_whitelist_proxies(self, country: str = "all", count: int = 20) -> bool:
        """
        Whitelists the current VM IP with 2Captcha and generates proxies.
        """
        if not self.api_key:
            logger.error("2Captcha API key missing.")
            return False

        current_ip = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api64.ipify.org?format=json") as resp:
                    if resp.status == 200:
                        current_ip = (await resp.json()).get("ip")
        except Exception as e:
            logger.warning(f"Could not detect current IP: {e}")

        # Try multiple parameter names for IP whitelisting as per research
        params_to_try = [
            {"key": self.api_key, "country": country, "protocol": "http", "connection_count": count, "ip": current_ip},
            {"key": self.api_key, "country": country, "protocol": "http", "connection_count": count, "ip_address": current_ip},
            {"key": self.api_key, "country": country, "protocol": "http", "connection_count": count, "ips": current_ip}
        ]

        url = "https://api.2captcha.com/proxy/generate_white_list_connections"
        async with aiohttp.ClientSession() as session:
            for params in params_to_try:
                if not params.get("ip") and not params.get("ip_address") and not params.get("ips"):
                    continue
                    
                logger.info(f"[WHITELIST] Attempting whitelist with params: {params}")
                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("status") == "OK":
                                proxy_list = data.get("data", [])
                                logger.info(f"[OK] Successfully whitelisted and received {len(proxy_list)} proxies.")
                                
                                new_proxies = []
                                for p_str in proxy_list:
                                    proxy = self._parse_proxy_string(f"http://{p_str}")
                                    if proxy:
                                        new_proxies.append(proxy)
                                
                                if new_proxies:
                                    self.all_proxies = new_proxies
                                    self.proxies = list(new_proxies)
                                    abs_path = os.path.abspath(self.settings.residential_proxies_file)
                                    with open(abs_path, "w") as f:
                                        f.write("# whitelisted-proxies\n")
                                        f.write("\n".join([p.to_string() for p in new_proxies]))
                                    return True
                        logger.warning(f"[WHITELIST] Param set failed: {params}")
                except Exception as e:
                    logger.error(f"[ERROR] Whitelist request failed: {e}")
            
        return False

    async def fetch_proxies_from_api(self, quantity: int = 10) -> int:
        """
        Generates residential proxies by rotating session IDs.
        Since 2Captcha (and similar providers) use a single gateway with session-based rotation,
        we generate unique sessions from the base configured proxy.
        """
        # We need a base proxy to work from.
        # Try to load from file first if empty
        if not self.proxies:
            self.load_proxies_from_file()
            
        if not self.proxies:
            logger.error("Cannot generate proxies: No base proxy found in proxies.txt to use as template.")
            return 0

        # Use the first proxy as a template
        template_proxy = self.proxies[0]
        
        if not template_proxy.username or not template_proxy.password:
             logger.error("Cannot generate proxies: Base proxy is missing authentication details.")
             return 0

        logger.info(f"Generating {quantity} unique proxies using template from {template_proxy.ip}:{template_proxy.port}...")
        
        # Extract base username (remove existing session params if present)
        base_username = template_proxy.username
        if "-session-" in base_username:
            base_username = base_username.split("-session-")[0]
            
        new_proxies = []
        lines_to_write = []
        lines_to_write.append("# Auto-generated from Base Proxy with Session Rotation")
        # Keep the base one
        lines_to_write.append(template_proxy.to_string())
        new_proxies.append(template_proxy)
        
        for i in range(quantity):
            # Construct new username using rotate_session_id helper
            new_username = self.rotate_session_id(template_proxy.username)
            
            # Create proxy string
            # Format: http://user:pass@ip:port
            proxy_str = f"http://{new_username}:{template_proxy.password}@{template_proxy.ip}:{template_proxy.port}"
            
            lines_to_write.append(proxy_str)
            
            new_proxy = self._parse_proxy_string(proxy_str)
            if new_proxy:
                new_proxies.append(new_proxy)

        if len(new_proxies) > 1:
            # Update file
            file_path = self.settings.residential_proxies_file
            try:
                # Use absolute path for safety
                abs_path = os.path.abspath(file_path)
                with open(abs_path, "w") as f:
                    f.write("\n".join(lines_to_write))
                
                self.all_proxies = new_proxies
                self.proxies = list(new_proxies)
                logger.info(f"✅ Generated and saved {len(new_proxies)} unique residential proxies to {abs_path}")
                return len(new_proxies)
            except Exception as e:
                logger.error(f"Failed to save generated proxies: {e}")
                return 0
        
        return 0

    async def fetch_proxies(self, count: int = 100) -> bool:
        """
        Wrapper for fetch_proxies_from_api to maintain compatibility.
        """
        c = await self.fetch_proxies_from_api(count)
        return c > 0

    def assign_proxies(self, profiles: List[AccountProfile]):
        """
        Assigns proxies to profiles 1:1.
        If we have proxies, we overwrite the profile.proxy field.
        """
        if not self.proxies:
            logger.warning("No 2Captcha proxies loaded. Creating fallback assignments from config.")
            return

        logger.info(f"Assigning {len(self.proxies)} proxies to {len(profiles)} profiles (Sticky Strategy)...")
        
        for i, profile in enumerate(profiles):
            # Round-robin assignment
            proxy = self.proxies[i % len(self.proxies)]
            
            # Store assignment
            self.assignments[profile.username] = proxy
            
            # INJECT into profile
            profile.proxy = proxy.to_string()
            profile.residential_proxy = True # Assume 2Captcha proxies are residential
            logger.info(f"   Profile '{profile.username}' -> Proxy {proxy.ip}:{proxy.port}")

    def get_proxy_for_solver(self, username: str) -> Optional[str]:
        """
        Returns the proxy string (user:pass@ip:port) for the captcha solver.
        """
        if username in self.assignments:
            return self.assignments[username].to_2captcha_string()
        return None

    def rotate_proxy(self, profile: AccountProfile) -> Optional[str]:
        """
        Rotates the proxy for a profile, ensuring it stays on a healthy one.
        If the current proxy is marked dead, it finds a new one.
        
        Returns:
            The new proxy string, or None if no healthy proxies left
        """
        current_proxy_str = profile.proxy
        # Normalize current key to match _proxy_key format (user:pass@ip:port)
        current_key = current_proxy_str or ""
        if "://" in current_key:
             current_key = current_key.split("://", 1)[1]
                
        # If current is dead or we just want to rotate
        if not current_key or current_key in self.dead_proxies or profile.proxy_rotation_strategy == "random":
            if not self.proxies:
                 # Check if we can fetch more
                 return None
                
            # Filter out dead ones
            healthy = [p for p in self.proxies if self._proxy_key(p) not in self.dead_proxies]
            if not healthy:
                logger.warning(f"No healthy proxies left for {profile.username}. Trying to replenish pool...")
                # We return None but the orchestrator might trigger a retry or replenishment
                return None
                
            # Choose new one
            new_proxy = random.choice(healthy)
            profile.proxy = new_proxy.to_string()
            self.assignments[profile.username] = new_proxy
            logger.info(f"[ROTATE] {profile.username} rotated to {self._proxy_key(new_proxy)}")
            return profile.proxy
        
        return current_proxy_str
