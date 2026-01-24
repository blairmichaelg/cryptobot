from playwright.async_api import BrowserContext, Page
from browserforge.fingerprints import Screen
from camoufox.async_api import AsyncCamoufox
from .blocker import ResourceBlocker
from .secure_storage import SecureCookieStorage
from .stealth_hub import StealthHub
from core.config import CONFIG_DIR
import logging
import random
import time
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
        self.browser: Optional[Any] = None
        self.context = None
        self.playwright = None
        self.camoufox: Optional[AsyncCamoufox] = None
        
        # Cookie storage - encrypted by default
        # NOTE: Requires that load_dotenv() has been called BEFORE this __init__
        # Otherwise os.environ.get('CRYPTOBOT_COOKIE_KEY') will be None
        self.use_encrypted_cookies = use_encrypted_cookies
        if use_encrypted_cookies:
            self._secure_storage = SecureCookieStorage()
        else:
            self._secure_storage = None
        self.seed_cookie_jar = True

    def _safe_json_write(self, filepath: str, data: dict, max_backups: int = 3):
        """Atomic JSON write with corruption protection and backups."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            if os.path.exists(filepath):
                backup_base = filepath + ".backup"
                for i in range(max_backups - 1, 0, -1):
                    old = f"{backup_base}.{i}"
                    new = f"{backup_base}.{i+1}"
                    if os.path.exists(old):
                        os.replace(old, new)
                os.replace(filepath, f"{backup_base}.1")

            temp_file = filepath + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            with open(temp_file, "r", encoding="utf-8") as f:
                json.load(f)
            os.replace(temp_file, filepath)
        except Exception as e:
            logger.error("Failed to safely write %s: %s", filepath, e)

    def _safe_json_read(self, filepath: str, max_backups: int = 3) -> Optional[dict]:
        """Read JSON with fallback to backups if corrupted."""
        candidates = [filepath] + [f"{filepath}.backup.{i}" for i in range(1, max_backups + 1)]
        for candidate in candidates:
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return None

    def _normalize_proxy_key(self, proxy: str) -> str:
        if not proxy:
            return ""
        return proxy.split("://", 1)[1] if "://" in proxy else proxy

    def _is_proxy_blacklisted(self, proxy: str) -> bool:
        """Check if a proxy is dead or in cooldown based on proxy_health.json."""
        try:
            health_file = CONFIG_DIR / "proxy_health.json"
            data = self._safe_json_read(str(health_file))
            if not data:
                return False

            key = self._normalize_proxy_key(proxy)
            if not key:
                return False

            dead = set(data.get("dead_proxies", []))
            if key in dead:
                return True

            cooldowns = data.get("proxy_cooldowns", {})
            cooldown_until = cooldowns.get(key)
            if cooldown_until and cooldown_until > time.time():
                return True

        except Exception as e:
            logger.debug("Failed to read proxy health data: %s", e)

        return False

    async def launch(self):
        """Launches a highly stealthy Camoufox instance."""
        logger.info("Launching Camoufox (Headless: %s)...", self.headless)
        
        # Construct arguments
        # We launch the browser WITHOUT a global proxy to allow per-context proxies
        # For headless Linux servers, we need to specify realistic screen constraints
        # because auto-detection defaults to 1024x768 which has limited fingerprints
        kwargs = {
            "headless": self.headless,
            "geoip": True,  # Auto-detect location
            "humanize": True,  # Add human-like timing
            "block_images": self.block_images,
        }

        # Avoid browserforge header generation failures with low-resolution
        # headless defaults (e.g., 1024x768) by constraining to a common size.
        if self.headless:
            kwargs["screen"] = Screen(max_width=1920, max_height=1080)

        # We keep the camoufox instance wrapper
        self.camoufox = AsyncCamoufox(**kwargs)
        
        # Start the context
        self.browser = await self.camoufox.__aenter__()
        return self

    async def create_context(self, proxy: Optional[str] = None, user_agent: Optional[str] = None, profile_name: Optional[str] = None, locale_override: Optional[str] = None, timezone_override: Optional[str] = None) -> BrowserContext:
        """
        Creates a new isolated browser context with specific proxy and user agent.
        Includes enhanced anti-detection measures and sticky session support.
        """
        if not self.browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        # Sticky Session Logic: Register proxy with solver if provided
        if proxy and self._secure_storage:
            # This allows the solver to use the same proxy as the browser
            logger.debug("Creating sticky context for %s with proxy %s", profile_name, proxy)

        # Randomized screen resolutions for natural fingerprints using StealthHub
        stealth_data = StealthHub.get_random_dimensions()
        dims = (stealth_data["width"], stealth_data["height"])

        # Load or generate persistent fingerprint settings for this profile
        locale = None
        timezone_id = None
        languages = None
        platform_name = None
        viewport_width = None
        viewport_height = None
        device_scale_factor = None
        audio_seed = None
        if profile_name:
            fingerprint = await self.load_profile_fingerprint(profile_name)
            if fingerprint:
                locale = fingerprint.get("locale")
                timezone_id = fingerprint.get("timezone_id")
                languages = fingerprint.get("languages")
                platform_name = fingerprint.get("platform")
                viewport_width = fingerprint.get("viewport_width")
                viewport_height = fingerprint.get("viewport_height")
                device_scale_factor = fingerprint.get("device_scale_factor")
                audio_seed = fingerprint.get("audio_seed")
                logger.debug("🔒 Using persistent fingerprint for %s: %s, %s", profile_name, locale, timezone_id)
        
        # Generate new fingerprint if not found
        canvas_seed = None
        gpu_index = None
        if locale_override:
            locale = locale_override
        if timezone_override:
            timezone_id = timezone_override

        if not locale or not timezone_id:
            locale = random.choice(["en-US", "en-GB", "en-CA", "en-AU"])
            timezone_id = random.choice(["America/New_York", "America/Los_Angeles", "America/Chicago", "Europe/London", "Europe/Paris", "Asia/Tokyo", "Australia/Sydney"])

            if not languages:
                languages = [locale, locale.split("-")[0]]
            if not platform_name:
                platform_name = random.choice(["Win32", "MacIntel", "Linux x86_64"])
            if viewport_width is None or viewport_height is None:
                viewport_width, viewport_height = dims
            if device_scale_factor is None:
                device_scale_factor = random.choice([1.0, 1.25, 1.5])

            # Save for future use (canvas_seed and gpu_index will be auto-generated)
            if profile_name:
                await self.save_profile_fingerprint(
                    profile_name,
                    locale,
                    timezone_id,
                    canvas_seed=canvas_seed,
                    gpu_index=gpu_index,
                    audio_seed=audio_seed,
                    languages=languages,
                    platform=platform_name,
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    device_scale_factor=device_scale_factor
                )
                logger.info("📌 Generated and saved fingerprint for %s: %s, %s", profile_name, locale, timezone_id)
        else:
            # Load canvas and WebGL params from existing fingerprint
            fingerprint_data = fingerprint or {}
            raw_canvas_seed = fingerprint_data.get("canvas_seed")
            raw_gpu_index = fingerprint_data.get("gpu_index")
            canvas_seed = int(raw_canvas_seed) if raw_canvas_seed is not None else None
            gpu_index = int(raw_gpu_index) if raw_gpu_index is not None else None
            raw_audio_seed = fingerprint_data.get("audio_seed")
            audio_seed = int(raw_audio_seed) if raw_audio_seed is not None else None

        if profile_name and (locale_override or timezone_override):
            await self.save_profile_fingerprint(
                profile_name,
                locale,
                timezone_id,
                canvas_seed=canvas_seed,
                gpu_index=gpu_index,
                audio_seed=audio_seed,
                languages=languages,
                platform=platform_name,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                device_scale_factor=device_scale_factor
            )

        if profile_name and any(v is None for v in [audio_seed, languages, platform_name, viewport_width, viewport_height, device_scale_factor]):
            await self.save_profile_fingerprint(
                profile_name,
                locale,
                timezone_id,
                canvas_seed=canvas_seed,
                gpu_index=gpu_index,
                audio_seed=audio_seed,
                languages=languages,
                platform=platform_name,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                device_scale_factor=device_scale_factor
            )

        context_args = {
            "user_agent": user_agent or StealthHub.get_human_ua(self.user_agents),
            "viewport": {"width": viewport_width or dims[0], "height": viewport_height or dims[1]},
            "device_scale_factor": device_scale_factor if device_scale_factor is not None else random.choice([1.0, 1.25, 1.5]),
            "permissions": ["geolocation", "notifications"],
            "locale": locale,
            "timezone_id": timezone_id,
        }
        
        # Sticky Session Logic: Resolve and Persist Proxy
        if profile_name:
            # Load existing binding
            saved_proxy = await self.load_proxy_binding(profile_name)
            
            if saved_proxy:
                if self._is_proxy_blacklisted(saved_proxy):
                    logger.warning("⚠️ Sticky proxy for %s is dead/cooldown. Clearing binding: %s", profile_name, saved_proxy)
                    await self.remove_proxy_binding(profile_name)
                    saved_proxy = None
                
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

        logger.info("Creating isolated stealth context (Profile: %s, Proxy: %s, Resolution: %sx%s)", profile_name or "Anonymous", proxy or "None", dims[0], dims[1])
        context = await self.browser.new_context(**context_args)
        
        # Set global timeout for this context
        context.set_default_timeout(self.timeout)
        
        # Comprehensive Anti-Fingerprinting Suite using StealthHub with per-profile fingerprints
        # Generate deterministic parameters if not loaded from existing fingerprint
        if canvas_seed is None and profile_name:
            canvas_seed = hash(profile_name) % 1000000
        if gpu_index is None and profile_name:
            gpu_index = hash(profile_name + "_gpu") % 13
        if audio_seed is None and profile_name:
            audio_seed = hash(profile_name + "_audio") % 1000000
        
        # Use defaults for anonymous profiles
        if canvas_seed is None:
            canvas_seed = 12345
        if gpu_index is None:
            gpu_index = 0
        if audio_seed is None:
            audio_seed = 98765
        
        if not languages:
            languages = [locale or "en-US", (locale or "en-US").split("-")[0]]
        if not platform_name:
            platform_name = "Win32"
        await context.add_init_script(
            StealthHub.get_stealth_script(
                canvas_seed=canvas_seed,
                gpu_index=gpu_index,
                audio_seed=audio_seed,
                languages=languages,
                platform=platform_name
            )
        )
        logger.debug("🎨 Injected fingerprint: canvas_seed=%s, gpu_index=%s", canvas_seed, gpu_index)

        # Apply Resource Blocker using instance settings
        blocker = ResourceBlocker(block_images=self.block_images, block_media=self.block_media)
        await context.route("**/*", blocker.handle_route)
        context.resource_blocker = blocker  # type: ignore[attr-defined]
        
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

            if self.seed_cookie_jar:
                await self._seed_cookie_jar(context, profile_name)
                return True
            
            logger.debug(f"No saved cookies for {profile_name}")
            return False
            
        except Exception as e:
            logger.warning(f"Failed to load cookies for {profile_name}: {e}")
            return False

    def _load_cookie_profile(self) -> dict:
        profile_file = CONFIG_DIR / "cookie_profiles.json"
        if os.path.exists(profile_file):
            data = self._safe_json_read(str(profile_file))
            return data or {}
        return {}

    def _save_cookie_profile(self, data: dict) -> None:
        profile_file = CONFIG_DIR / "cookie_profiles.json"
        self._safe_json_write(str(profile_file), data)

    async def _seed_cookie_jar(self, context: BrowserContext, profile_name: str) -> None:
        """Seed a minimal cookie jar to avoid a brand new profile signature."""
        profiles = self._load_cookie_profile()
        entry = profiles.get(profile_name, {})

        if "created_at" not in entry:
            back_days = random.randint(7, 30)
            entry["created_at"] = time.time() - (back_days * 86400)

        base_domains = [
            "google.com",
            "bing.com",
            "wikipedia.org",
            "reddit.com",
            "news.ycombinator.com"
        ]

        cookie_count = entry.get("cookie_count")
        if not cookie_count:
            cookie_count = random.randint(8, 20)
            entry["cookie_count"] = cookie_count

        profiles[profile_name] = entry
        self._save_cookie_profile(profiles)

        now = time.time()
        created_at = entry["created_at"]
        age_days = max(1, int((now - created_at) / 86400))

        cookies = []
        for i in range(cookie_count):
            domain = random.choice(base_domains)
            max_age_days = random.randint(30, 90)
            expires = int(created_at + (max_age_days * 86400))
            if expires < now:
                expires = int(now + (max_age_days * 86400))
            cookies.append({
                "name": f"pref_{i}",
                "value": f"{random.randint(1000, 9999)}",
                "domain": domain,
                "path": "/",
                "expires": expires,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax"
            })

        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"🍪 Seeded {len(cookies)} cookies for {profile_name} (age ~{age_days}d)")

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

            self._safe_json_write(str(bindings_file), data)
        except Exception as e:
            logger.error(f"Failed to save proxy binding for {profile_name}: {e}")

    async def remove_proxy_binding(self, profile_name: str):
        """Remove a sticky proxy binding for a profile."""
        try:
            bindings_file = CONFIG_DIR / "proxy_bindings.json"
            if not os.path.exists(bindings_file):
                return
            data = self._safe_json_read(str(bindings_file)) or {}
            if profile_name in data:
                data.pop(profile_name, None)
                self._safe_json_write(str(bindings_file), data)
        except Exception as e:
            logger.error(f"Failed to remove proxy binding for {profile_name}: {e}")

    async def load_proxy_binding(self, profile_name: str) -> Optional[str]:
        """Load the sticky proxy for a profile."""
        try:
            bindings_file = CONFIG_DIR / "proxy_bindings.json"
            if os.path.exists(bindings_file):
                data = self._safe_json_read(str(bindings_file))
                if data:
                    return data.get(profile_name)
            return None
        except Exception as e:
            logger.error(f"Failed to load proxy binding for {profile_name}: {e}")
            return None

    async def save_profile_fingerprint(
        self,
        profile_name: str,
        locale: str,
        timezone_id: str,
        canvas_seed: Optional[int] = None,
        gpu_index: Optional[int] = None,
        audio_seed: Optional[int] = None,
        languages: Optional[List[str]] = None,
        platform: Optional[str] = None,
        viewport_width: Optional[int] = None,
        viewport_height: Optional[int] = None,
        device_scale_factor: Optional[float] = None
    ):
        """Save the fingerprint settings for a profile including canvas, WebGL, and audio parameters."""
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

            if audio_seed is None:
                audio_seed = hash(profile_name + "_audio") % 1000000

            if languages is None:
                languages = [locale, locale.split("-")[0]]

            if platform is None:
                platform = "Win32"
            
            data[profile_name] = {
                "locale": locale,
                "timezone_id": timezone_id,
                "canvas_seed": canvas_seed,
                "gpu_index": gpu_index,
                "audio_seed": audio_seed,
                "languages": languages,
                "platform": platform,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
                "device_scale_factor": device_scale_factor
            }

            self._safe_json_write(str(fingerprint_file), data)
            
            logger.debug(f"💾 Saved fingerprint for {profile_name}: canvas_seed={canvas_seed}, gpu_index={gpu_index}")
        except Exception as e:
            logger.error(f"Failed to save fingerprint for {profile_name}: {e}")

    async def load_profile_fingerprint(self, profile_name: str) -> Optional[Dict[str, str]]:
        """Load the fingerprint settings for a profile."""
        try:
            fingerprint_file = CONFIG_DIR / "profile_fingerprints.json"
            if os.path.exists(fingerprint_file):
                data = self._safe_json_read(str(fingerprint_file))
                if data:
                    return data.get(profile_name)
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
