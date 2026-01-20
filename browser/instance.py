from playwright.async_api import Browser, BrowserContext, Page
from camoufox.async_api import AsyncCamoufox
from .blocker import ResourceBlocker
from .secure_storage import SecureCookieStorage
from .stealth_scripts import get_full_stealth_script
from core.config import AccountProfile, BotSettings, CONFIG_DIR
import logging
import random
import os
import json
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages the lifecycle of a stealthy Camoufox browser instance.
    Handles context creation, page management, and cleanup.
    """
    def __init__(self, headless: bool = True, proxy: Optional[str] = None, block_images: bool = True, block_media: bool = True, use_encrypted_cookies: bool = True, timeout: int = 60000):
        """
        Initialize the BrowserManager.

        Args:
            headless: Whether to run the browser in headless mode. Defaults to True.
            proxy: Optional proxy server address (e.g., "http://user:pass@host:port").
            block_images: Whether to block image loading.
            block_media: Whether to block media (video/audio).
            use_encrypted_cookies: Whether to use encrypted cookie storage. Defaults to True.
            timeout: Default timeout in milliseconds.
        """
        self.headless = headless
        self.proxy = proxy
        self.block_images = block_images
        self.block_media = block_media
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.playwright = None
        
        # Cookie storage - encrypted by default
        self.use_encrypted_cookies = use_encrypted_cookies
        if use_encrypted_cookies:
            self._secure_storage = SecureCookieStorage()
        else:
            self._secure_storage = None

    async def launch(self):
        """Launches a highly stealthy Camoufox instance."""
        logger.info(f"Launching Camoufox (Headless: {self.headless})...")
        
        # Construct arguments
        # We launch the browser WITHOUT a global proxy to allow per-context proxies
        kwargs = {
            "headless": self.headless,
            "geoip": True,
            "humanize": True,
            "block_images": self.block_images,
            "fonts": ["Arial", "Courier New", "Georgia", "Times New Roman", "Verdana"] # Fix for Camoufox TypeError
        }

        # We keep the camoufox instance wrapper
        self.camoufox = AsyncCamoufox(**kwargs)
        
        # Start the context
        self.browser = await self.camoufox.__aenter__()
        return self

    async def create_context(self, proxy: Optional[str] = None, user_agent: Optional[str] = None, profile_name: Optional[str] = None) -> BrowserContext:
        """
        Creates a new isolated browser context with specific proxy and user agent.
        Includes enhanced anti-detection measures and sticky session support.
        """
        if not self.browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        # Sticky Session Logic: Register proxy with solver if provided
        if proxy and self._secure_storage:
             # This allows the solver to use the same proxy as the browser
             logger.debug(f"Creating sticky context for {profile_name} with proxy {proxy}")

        # Randomized screen resolutions for natural fingerprints
        dims = random.choice([
            (1920, 1080), (1366, 768), (1440, 900), (1536, 864)
        ])

        context_args = {
            "user_agent": user_agent or random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ]),
            "viewport": {"width": dims[0], "height": dims[1]},
            "device_scale_factor": random.choice([1.0, 1.25, 1.5]),
            "permissions": ["geolocation", "notifications"],
            "locale": random.choice(["en-US", "en-GB"]),
            "timezone_id": random.choice(["America/New_York", "Europe/London", "UTC"]),
        }
        
        # Sticky Session Logic: Resolve and Persist Proxy
        if profile_name:
            # Load existing binding
            saved_proxy = await self.load_proxy_binding(profile_name)
            
            if saved_proxy:
                if proxy and proxy != saved_proxy:
                    logger.warning(f"⚠️ Proxy mismatch for {profile_name}. Requested: {proxy}, Stuck to: {saved_proxy}")
                    logger.info(f"🔄 Updating sticky proxy for {profile_name} to {proxy}")
                    await self.save_proxy_binding(profile_name, proxy)
                elif not proxy:
                     logger.info(f"🔗 Using sticky proxy {saved_proxy} for {profile_name}")
                     proxy = saved_proxy
            elif proxy:
                # No existing binding, create one
                logger.info(f"📌 Binding {profile_name} to proxy {proxy}")
                await self.save_proxy_binding(profile_name, proxy)

        if proxy:
            # Parse proxy string if it's a URL
            if "://" in proxy:
                from urllib.parse import urlparse
                p = urlparse(proxy)
                context_args["proxy"] = {
                    "server": f"{p.scheme}://{p.hostname}:{p.port}",
                    "username": p.username,
                    "password": p.password
                }
            else:
                context_args["proxy"] = {"server": proxy}

        logger.info(f"Creating isolated stealth context (Profile: {profile_name or 'Anonymous'}, Proxy: {proxy or 'None'}, Resolution: {dims[0]}x{dims[1]})")
        context = await self.browser.new_context(**context_args)
        
        # Set global timeout for this context
        context.set_default_timeout(self.timeout)
        
        # Comprehensive Anti-Fingerprinting Suite
        # Includes: WebRTC leak prevention, Canvas/WebGL/Audio evasion, Navigator spoofing
        await context.add_init_script(get_full_stealth_script())

        # Apply Resource Blocker
        blocker = ResourceBlocker(block_images=True, block_media=True)
        await context.route("**/*", blocker.handle_route)
        context.resource_blocker = blocker
        
        # Load cookies if profile name provided
        if profile_name:
            await self.load_cookies(context, profile_name)
        
        return context

    async def save_cookies(self, context: BrowserContext, profile_name: str):
        """
        Save browser cookies to disk for faster subsequent logins.
        Uses encrypted storage by default.
        
        Args:
            context: The browser context to save cookies from
            profile_name: Unique identifier for this profile (e.g., faucet_username)
        """
        try:
            cookies = await context.cookies()
            
            # Use encrypted storage if available
            if self._secure_storage:
                await self._secure_storage.save_cookies(cookies, profile_name)
            else:
                # Fallback to unencrypted (backward compatibility)
                cookies_dir = CONFIG_DIR / "cookies"
                cookies_dir.mkdir(exist_ok=True)
                cookies_file = cookies_dir / f"{profile_name}.json"
                with open(cookies_file, "w") as f:
                    json.dump(cookies, f)
                logger.debug(f"💾 Saved {len(cookies)} cookies for {profile_name} (unencrypted)")
        except Exception as e:
            logger.warning(f"Failed to save cookies for {profile_name}: {e}")

    async def load_cookies(self, context: BrowserContext, profile_name: str) -> bool:
        """
        Load previously saved cookies into a browser context.
        Tries encrypted storage first, falls back to unencrypted.
        
        Args:
            context: The browser context to load cookies into
            profile_name: Unique identifier for this profile
            
        Returns:
            True if cookies were loaded successfully, False otherwise
        """
        cookies = None
        
        try:
            # Try encrypted storage first
            if self._secure_storage:
                cookies = await self._secure_storage.load_cookies(profile_name)
            
            # Fallback to unencrypted if no encrypted cookies found
            if not cookies:
                cookies_file = CONFIG_DIR / "cookies" / f"{profile_name}.json"
                if os.path.exists(cookies_file):
                    with open(cookies_file, "r") as f:
                        cookies = json.load(f)
                    logger.debug(f"Loaded unencrypted cookies for {profile_name}")
            
            if cookies:
                await context.add_cookies(cookies)
                logger.info(f"🍪 Loaded {len(cookies)} cookies for {profile_name}")
                return True
            
            logger.debug(f"No saved cookies for {profile_name}")
            return False
            
        except Exception as e:
            logger.warning(f"Failed to load cookies for {profile_name}: {e}")
            return False

    async def save_proxy_binding(self, profile_name: str, proxy: str):
        """Save the proxy binding for a profile to ensuring sticky sessions."""
        try:
            bindings_file = CONFIG_DIR / "proxy_bindings.json"
            data = {}
            if os.path.exists(bindings_file):
                with open(bindings_file, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            data[profile_name] = proxy
            
            with open(bindings_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save proxy binding for {profile_name}: {e}")

    async def load_proxy_binding(self, profile_name: str) -> Optional[str]:
        """Load the sticky proxy for a profile."""
        try:
            bindings_file = CONFIG_DIR / "proxy_bindings.json"
            if os.path.exists(bindings_file):
                with open(bindings_file, "r") as f:
                    try:
                        data = json.load(f)
                        return data.get(profile_name)
                    except json.JSONDecodeError:
                        pass
            return None
        except Exception as e:
            logger.error(f"Failed to load proxy binding for {profile_name}: {e}")
            return None

    async def new_page(self, context: BrowserContext = None) -> Page:
        """Creates and returns a new page. If context is provided, uses it. Otherwise uses default context."""
        if not self.browser:
            await self.launch()

        if context:
            page = await context.new_page()
        else:
            # Global context page
            page = await self.browser.new_page()
            blocker = ResourceBlocker(block_images=True, block_media=True)
            await page.route("**/*", blocker.handle_route)
            page.resource_blocker = blocker
            
        return page

    async def restart(self):
        """Restarts the browser instance to clear memory and hung processes."""
        logger.info("🔄 Restarting browser instance...")
        await self.close()
        await asyncio.sleep(2)
        await self.launch()
        logger.info("✅ Browser instance restarted.")

    async def check_health(self) -> bool:
        """Checks if the browser instance is still responsive."""
        if not self.browser:
            return False
        try:
            # Try to create a dummy context and check its version
            # This is a lightweight check to ensure the connection is alive
            context = await self.browser.new_context()
            await context.close()
            return True
        except Exception as e:
            logger.warning(f"Browser health check failed: {e}")
            return False

    async def close(self):
        """Cleanup resources."""
        if self.browser:
            try:
                await self.camoufox.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error during browser exit: {e}")
            self.browser = None
            logger.info("Browser closed.")

async def create_stealth_browser(headless: bool = True, proxy: Optional[str] = None):
    """
    Factory helper.
    """
    # Simply return the context manager for 'async with' usage
    return AsyncCamoufox(
        headless=headless,
        geoip=True,
        humanize=True,
        block_images=True,
        proxy={"server": proxy} if proxy else None
    )
