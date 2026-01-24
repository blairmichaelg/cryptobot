from playwright.async_api import Browser, BrowserContext, Page
from camoufox.async_api import AsyncCamoufox
from .blocker import ResourceBlocker
from .secure_storage import SecureCookieStorage
from .stealth_hub import StealthHub
from core.config import AccountProfile, BotSettings, CONFIG_DIR
import logging
import random
import os
import json
from typing import Optional, List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages the lifecycle of a stealthy Camoufox browser instance.
    Handles context creation, page management, and cleanup.
    """
    def __init__(self, headless: bool = True, proxy: Optional[str] = None, block_images: bool = True, block_media: bool = True, use_encrypted_cookies: bool = True, timeout: int = 60000, user_agents: Optional[List[str]] = None):
        """
        Initialize the BrowserManager.

        Args:
            headless: Whether to run the browser in headless mode. Defaults to True.
            proxy: Optional proxy server address (e.g., "http://user:pass@host:port").
            block_images: Whether to block image loading.
            block_media: Whether to block media (video/audio).
            use_encrypted_cookies: Whether to use encrypted cookie storage. Defaults to True.
            timeout: Default timeout in milliseconds.
            user_agents: Optional list of User-Agent strings to rotate through.
        """
        self.headless = headless
        self.proxy = proxy
        self.block_images = block_images
        self.block_media = block_media
        self.timeout = timeout
        self.user_agents = user_agents or []
        self.browser = None
        self.context = None
        self.playwright = None
        
        # Cookie storage - encrypted by default
        # NOTE: Requires that load_dotenv() has been called BEFORE this __init__
        # Otherwise os.environ.get('CRYPTOBOT_COOKIE_KEY') will be None
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
        # For headless Linux servers, we need to specify realistic screen constraints
        # because auto-detection defaults to 1024x768 which has limited fingerprints
        from camoufox.utils import Screen
        
        kwargs = {
            "headless": self.headless,
            "geoip": True,  # Auto-detect location
            "humanize": True,  # Add human-like timing
            "block_images": self.block_images,
            # Provide realistic screen constraints for headless servers
            # Common desktop resolutions have better fingerprint coverage in browserforge
            "screen": Screen(
                min_width=1280,
                max_width=1920,
                min_height=720,
                max_height=1080
            )
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

        # Randomized screen resolutions for natural fingerprints using StealthHub
        stealth_data = StealthHub.get_random_dimensions()
        dims = (stealth_data["width"], stealth_data["height"])

        # Load or generate persistent fingerprint settings for this profile
        locale = None
        timezone_id = None
        if profile_name:
            fingerprint = await self.load_profile_fingerprint(profile_name)
            if fingerprint:
                locale = fingerprint.get("locale")
                timezone_id = fingerprint.get("timezone_id")
                logger.debug(f"🔒 Using persistent fingerprint for {profile_name}: {locale}, {timezone_id}")
        
        # Generate new fingerprint if not found
        canvas_seed = None
        gpu_index = None
        if not locale or not timezone_id:
            locale = random.choice(["en-US", "en-GB", "en-CA", "en-AU"])
            timezone_id = random.choice(["America/New_York", "America/Los_Angeles", "America/Chicago", "Europe/London", "Europe/Paris", "Asia/Tokyo", "Australia/Sydney"])
            
            # Save for future use (canvas_seed and gpu_index will be auto-generated)
            if profile_name:
                await self.save_profile_fingerprint(profile_name, locale, timezone_id)
                logger.info(f"📌 Generated and saved fingerprint for {profile_name}: {locale}, {timezone_id}")
        else:
            # Load canvas and WebGL params from existing fingerprint
            canvas_seed = fingerprint.get("canvas_seed")
            gpu_index = fingerprint.get("gpu_index")

        context_args = {
            "user_agent": user_agent or StealthHub.get_human_ua(self.user_agents),
            "viewport": {"width": dims[0], "height": dims[1]},
            "device_scale_factor": random.choice([1.0, 1.25, 1.5]),
            "permissions": ["geolocation", "notifications"],
            "locale": locale,
            "timezone_id": timezone_id,
        }
        
        # Sticky Session Logic: Resolve and Persist Proxy
        if profile_name:
            # Load existing binding
            saved_proxy = await self.load_proxy_binding(profile_name)
            
            if saved_proxy:
                # Sticky session: Use saved proxy unless a new one is explicitly requested (Rotation)
                if proxy and proxy != saved_proxy:
                    logger.info(f"🔄 Rotation detected for {profile_name}. Updating sticky binding: {saved_proxy} -> {proxy}")
                    await self.save_proxy_binding(profile_name, proxy)
                else:
                    # No specific proxy requested, or same one requested -> Stick to saved
                    if not proxy:
                        logger.debug(f"🔗 Using sticky proxy for {profile_name}: {saved_proxy}")
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
        
        # Comprehensive Anti-Fingerprinting Suite using StealthHub with per-profile fingerprints
        # Generate deterministic parameters if not loaded from existing fingerprint
        if canvas_seed is None and profile_name:
            canvas_seed = hash(profile_name) % 1000000
        if gpu_index is None and profile_name:
            gpu_index = hash(profile_name + "_gpu") % 13
        
        # Use defaults for anonymous profiles
        if canvas_seed is None:
            canvas_seed = 12345
        if gpu_index is None:
            gpu_index = 0
        
        await context.add_init_script(StealthHub.get_stealth_script(canvas_seed=canvas_seed, gpu_index=gpu_index))
        logger.debug(f"🎨 Injected fingerprint: canvas_seed={canvas_seed}, gpu_index={gpu_index}")

        # Apply Resource Blocker using instance settings
        blocker = ResourceBlocker(block_images=self.block_images, block_media=self.block_media)
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

    async def save_profile_fingerprint(self, profile_name: str, locale: str, timezone_id: str, canvas_seed: int = None, gpu_index: int = None):
        """Save the fingerprint settings for a profile including canvas and WebGL parameters."""
        try:
            fingerprint_file = CONFIG_DIR / "profile_fingerprints.json"
            data = {}
            if os.path.exists(fingerprint_file):
                with open(fingerprint_file, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            # Generate deterministic fingerprint parameters based on profile name
            if canvas_seed is None:
                # Use hash of profile name to generate consistent seed
                canvas_seed = hash(profile_name) % 1000000
            
            if gpu_index is None:
                # Use hash to select GPU from 13 available configs (0-12)
                gpu_index = hash(profile_name + "_gpu") % 13
            
            data[profile_name] = {
                "locale": locale,
                "timezone_id": timezone_id,
                "canvas_seed": canvas_seed,
                "gpu_index": gpu_index
            }
            
            with open(fingerprint_file, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"💾 Saved fingerprint for {profile_name}: canvas_seed={canvas_seed}, gpu_index={gpu_index}")
        except Exception as e:
            logger.error(f"Failed to save fingerprint for {profile_name}: {e}")

    async def load_profile_fingerprint(self, profile_name: str) -> Optional[Dict[str, str]]:
        """Load the fingerprint settings for a profile."""
        try:
            fingerprint_file = CONFIG_DIR / "profile_fingerprints.json"
            if os.path.exists(fingerprint_file):
                with open(fingerprint_file, "r") as f:
                    try:
                        data = json.load(f)
                        return data.get(profile_name)
                    except json.JSONDecodeError:
                        pass
            return None
        except Exception as e:
            logger.error(f"Failed to load fingerprint for {profile_name}: {e}")
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

    async def check_page_status(self, page: Page) -> Dict[str, Any]:
        """
        Check the page for common failure status codes or network errors.
        Returns a dict with 'blocked', 'network_error', and 'status'.
        """
        try:
            # We don't need listeners for the primary status, 
            # we can just use the page.url and a lightweight eval
            status = await page.evaluate("async () => { try { return (await fetch(window.location.href, {method: 'HEAD'})).status; } catch(e) { return 0; } }")
            
            # Note: Fetch might be blocked too, so we also check readyState and content
            if status == 403 or status == 401:
                return {"blocked": True, "network_error": False, "status": status}
            if status == 0:
                # Potential network error or fetch blocked
                return {"blocked": False, "network_error": True, "status": 0}
                
            return {"blocked": False, "network_error": False, "status": status}
        except Exception as e:
            logger.debug(f"Status check failed: {e}")
            return {"blocked": False, "network_error": False, "status": -1}

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
