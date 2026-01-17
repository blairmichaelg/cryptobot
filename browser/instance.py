from playwright.async_api import Browser, BrowserContext, Page
from camoufox.async_api import AsyncCamoufox
from .blocker import ResourceBlocker
from .secure_storage import SecureCookieStorage
import logging
import random
import os
import json
from typing import Optional

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages the lifecycle of a stealthy Camoufox browser instance.
    Handles context creation, page management, and cleanup.
    """
    def __init__(self, headless: bool = True, proxy: Optional[str] = None, block_images: bool = True, block_media: bool = True, use_encrypted_cookies: bool = True):
        """
        Initialize the BrowserManager.

        Args:
            headless: Whether to run the browser in headless mode. Defaults to True.
            proxy: Optional proxy server address (e.g., "http://user:pass@host:port").
            block_images: Whether to block image loading.
            block_media: Whether to block media (video/audio).
            use_encrypted_cookies: Whether to use encrypted cookie storage. Defaults to True.
        """
        self.headless = headless
        self.proxy = proxy
        self.block_images = block_images
        self.block_media = block_media
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
        }

        # We keep the camoufox instance wrapper
        self.camoufox = AsyncCamoufox(**kwargs)
        
        # Start the context
        self.browser = await self.camoufox.__aenter__()
        return self

    async def create_context(self, proxy: Optional[str] = None, user_agent: Optional[str] = None) -> BrowserContext:
        """
        Creates a new isolated browser context with specific proxy and user agent.
        Includes enhanced anti-detection measures.
        """
        if not self.browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        # Randomized screen resolutions for natural fingerprints
        dims = random.choice([
            (1920, 1080), (1366, 768), (1440, 900), (1536, 864)
        ])

        context_args = {
            "user_agent": user_agent,
            "viewport": {"width": dims[0], "height": dims[1]},
            "device_scale_factor": random.choice([1.0, 1.25, 1.5]),
            "permissions": ["geolocation", "notifications"],
            "locale": random.choice(["en-US", "en-GB"]),
            "timezone_id": random.choice(["America/New_York", "Europe/London", "UTC"]),
        }
        
        if proxy:
            context_args["proxy"] = {"server": proxy}

        logger.info(f"Creating isolated stealth context (Proxy: {proxy or 'None'}, Resolution: {dims[0]}x{dims[1]})")
        context = await self.browser.new_context(**context_args)
        
        # WebRTC Leak Prevention: Critical for proxy-based stealth
        # We use evaluate_on_new_document to poison the WebRTC API
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            if (window.RTCPeerConnection) {
                const orig = window.RTCPeerConnection;
                window.RTCPeerConnection = function(config) {
                    if (config && config.iceServers) {
                        config.iceServers = []; // Remove TURN/STUN servers to prevent leak
                    }
                    return new orig(config);
                };
            }
        """)

        # Apply Resource Blocker
        blocker = ResourceBlocker(block_images=True, block_media=True)
        await context.route("**/*", blocker.handle_route)
        context.resource_blocker = blocker
        
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
                cookies_dir = os.path.join(os.path.dirname(__file__), "..", "cookies")
                os.makedirs(cookies_dir, exist_ok=True)
                cookies_file = os.path.join(cookies_dir, f"{profile_name}.json")
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
                cookies_file = os.path.join(
                    os.path.dirname(__file__), "..", "cookies", f"{profile_name}.json"
                )
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

    async def close(self):
        """Cleanup resources."""
        if self.browser:
            await self.camoufox.__aexit__(None, None, None)
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
