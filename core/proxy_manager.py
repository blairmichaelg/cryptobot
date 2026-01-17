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
    """

    # Validation constants
    VALIDATION_TIMEOUT_SECONDS = 10
    VALIDATION_TEST_URL = "https://httpbin.org/ip"

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.api_key = settings.twocaptcha_api_key
        self.proxies: List[Proxy] = []
        self.validated_proxies: List[Proxy] = []  # Only proxies that passed validation
        self.assignments: Dict[str, Proxy] = {}  # Map username -> Proxy

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
                    "connection_count": min(count, 2000)  # API max is 2000
                }
                
                async with session.get(gen_url, params=params) as resp:
                    data = await resp.json()
                    
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
