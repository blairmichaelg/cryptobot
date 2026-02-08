"""Stealth browser instance management for Cryptobot Gen 3.0.

Provides :class:`BrowserManager` which wraps ``Camoufox`` (a hardened
Firefox fork) via Playwright.  Features include:

* Headless or visible operation with realistic screen constraints.
* Per-account browser contexts with isolated cookies and proxy
  bindings.
* Encrypted cookie persistence via :class:`SecureCookieStorage`.
* Resource blocking (ads, trackers, fingerprinting services).
* WebRTC leak prevention and advanced Firefox pref hardening.
* Fingerprint persistence (canvas seed, GPU, audio, hardware
  concurrency) stored in ``config/profile_fingerprints.json``.
* Atomic JSON read/write with backup rotation for all state files.

NOTE: When deploying to Azure VM, ensure this file is fully
synchronised.  The ``Dict`` and ``List`` imports from ``typing`` are
CRITICAL for the Python version running the service on the VM.
Missing these causes ``NameError`` crashes.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any

from playwright.async_api import BrowserContext, Page
from browserforge.fingerprints import Screen
from camoufox.async_api import AsyncCamoufox
from .blocker import ResourceBlocker
from .secure_storage import SecureCookieStorage
from .stealth_hub import StealthHub
from core.config import CONFIG_DIR
from urllib.parse import urlparse
import logging
import random
import time
import os
import json
import asyncio

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages the lifecycle of a stealth Camoufox browser instance.

    Responsibilities:
        * Launching / closing the Camoufox browser process.
        * Creating isolated ``BrowserContext`` instances per faucet
          account, each with its own proxy, user-agent, and
          fingerprint seed.
        * Loading and saving encrypted cookies for session
          persistence.
        * Attaching the :class:`ResourceBlocker` to intercept
          requests.
        * Exposing ``get_page`` / ``close_context`` helpers for the
          scheduler.

    The manager should be instantiated *once* at startup and re-used
    across all jobs.  Thread safety is provided by asyncio (all public
    methods are coroutines).
    """

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        block_images: bool = True,
        block_media: bool = True,
        use_encrypted_cookies: bool = True,
        timeout: int = 60000,
        user_agents: Optional[List[str]] = None,
    ) -> None:
        """Initialise the BrowserManager.

        Args:
            headless: Whether to run the browser in headless mode.
                Defaults to ``True``.
            proxy: Optional proxy server address
                (e.g. ``http://user:pass@host:port``).
            block_images: Whether to block image loading.
            block_media: Whether to block media (video/audio).
            use_encrypted_cookies: Whether to use encrypted cookie
                storage.  Defaults to ``True``.
            timeout: Default timeout in milliseconds.
            user_agents: Optional list of User-Agent strings to
                rotate through.
        """
        self.headless = headless
        self.proxy = proxy
        self.block_images = block_images
        self.block_media = block_media
        self.timeout = timeout
        self.user_agents = user_agents or []
        self.browser: Optional[Any] = None
        self.context: Optional[BrowserContext] = None
        self.playwright: Optional[Any] = None
        self.camoufox: Optional[AsyncCamoufox] = None

        # Track closed contexts to prevent double-close errors
        self._closed_contexts: set = set()

        # Cookie storage - encrypted by default
        # NOTE: Requires that load_dotenv() has been called BEFORE
        # this __init__.  Otherwise os.environ.get(
        #     'CRYPTOBOT_COOKIE_KEY'
        # ) will be None.
        self.use_encrypted_cookies = use_encrypted_cookies
        if use_encrypted_cookies:
            self._secure_storage: Optional[
                SecureCookieStorage
            ] = SecureCookieStorage()
        else:
            self._secure_storage = None
        self.seed_cookie_jar = True

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def _safe_json_write(
        self,
        filepath: str,
        data: dict,
        max_backups: int = 3,
    ) -> None:
        """Atomically write JSON with corruption protection.

        Writes to a temporary file, validates the output, then
        atomically replaces the target.  Up to *max_backups*
        previous versions are rotated
        (``filepath.backup.1`` ... ``filepath.backup.N``).

        Args:
            filepath: Destination file path.
            data: JSON-serialisable dictionary.
            max_backups: Number of backup generations to keep.
        """
        try:
            os.makedirs(
                os.path.dirname(filepath), exist_ok=True,
            )

            if os.path.exists(filepath):
                backup_base = filepath + ".backup"
                for i in range(max_backups - 1, 0, -1):
                    old = f"{backup_base}.{i}"
                    new = f"{backup_base}.{i + 1}"
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
            logger.error(
                "Failed to safely write %s: %s", filepath, e,
            )

    def _safe_json_read(
        self,
        filepath: str,
        max_backups: int = 3,
    ) -> Optional[dict]:
        """Read JSON with automatic fallback to backup files.

        Tries the primary file first, then
        ``filepath.backup.1`` through ``filepath.backup.N``.
        Returns ``None`` if all candidates are missing or
        corrupted.

        Args:
            filepath: Primary file path.
            max_backups: Number of backup generations to attempt.

        Returns:
            Parsed dictionary, or ``None``.
        """
        candidates = [filepath] + [
            f"{filepath}.backup.{i}"
            for i in range(1, max_backups + 1)
        ]
        for candidate in candidates:
            if not os.path.exists(candidate):
                continue
            try:
                with open(
                    candidate, "r", encoding="utf-8",
                ) as f:
                    return json.load(f)
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Proxy helpers
    # ------------------------------------------------------------------

    def _normalize_proxy_key(self, proxy: str) -> str:
        """Strip the scheme prefix from a proxy URL for dict keys.

        Args:
            proxy: Full proxy URL string.

        Returns:
            Proxy string without the ``scheme://`` prefix.
        """
        if not proxy:
            return ""
        if "://" in proxy:
            return proxy.split("://", 1)[1]
        return proxy

    def _proxy_host_port(self, proxy: str) -> str:
        """Extract ``host:port`` from a proxy URL.

        Used for host-level grouping.

        Args:
            proxy: Full proxy URL string.

        Returns:
            ``host:port`` string, or empty string on failure.
        """
        if not proxy:
            return ""
        try:
            candidate = (
                proxy if "://" in proxy
                else f"http://{proxy}"
            )
            parsed = urlparse(candidate)
            if parsed.hostname and parsed.port:
                return f"{parsed.hostname}:{parsed.port}"
        except Exception:
            return ""
        return ""

    def _is_proxy_blacklisted(self, proxy: str) -> bool:
        """Check if a proxy is dead or in cooldown.

        Reads ``proxy_health.json`` to determine proxy state.

        Args:
            proxy: Full proxy URL string.

        Returns:
            ``True`` if the proxy should not be used.
        """
        try:
            health_file = CONFIG_DIR / "proxy_health.json"
            data = self._safe_json_read(str(health_file))
            if not data:
                return False

            key = self._normalize_proxy_key(proxy)
            if not key:
                return False

            host_port = self._proxy_host_port(proxy)

            dead = set(data.get("dead_proxies", []))
            if key in dead or (
                host_port and host_port in dead
            ):
                return True

            cooldowns = data.get("proxy_cooldowns", {})
            cooldown_until = cooldowns.get(key) or (
                cooldowns.get(host_port) if host_port else None
            )
            if cooldown_until and cooldown_until > time.time():
                return True

        except Exception as e:
            logger.debug(
                "Failed to read proxy health data: %s", e,
            )

        return False

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def launch(self) -> "BrowserManager":
        """Launch a hardened Camoufox browser instance.

        Configures Firefox preferences for stealth (WebRTC leak
        prevention, telemetry disabling, DNS prefetch blocking, etc.)
        and initialises the browser process.  Should be called once
        at startup.

        Returns:
            ``self`` for fluent chaining.

        Raises:
            Exception: If the browser fails to start.
        """
        logger.info(
            "Launching Camoufox (Headless: %s)...",
            self.headless,
        )

        # We launch WITHOUT a global proxy to allow per-context
        # proxies.  For headless Linux servers, we specify realistic
        # screen constraints because auto-detection defaults to
        # 1024x768 which has limited fingerprints.
        kwargs: Dict[str, Any] = {
            "headless": self.headless,
            "geoip": True,
            "humanize": True,
            "block_images": self.block_images,
        }

        # Avoid browserforge header generation failures with
        # low-resolution headless defaults (e.g. 1024x768).
        if self.headless:
            kwargs["screen"] = Screen(
                max_width=1920, max_height=1080,
            )

        # Hardened Firefox preferences for stealth
        firefox_prefs: Dict[str, Any] = {
            # Disable telemetry and crash reporting
            "toolkit.telemetry.enabled": False,
            "datareporting.policy.dataSubmissionEnabled": False,
            "browser.crashReports.unsubmittedCheck"
            ".autoSubmit2": False,
            # Disable health reporting
            "datareporting.healthreport"
            ".uploadEnabled": False,
            # Disable first-run annoyances
            "browser.shell.checkDefaultBrowser": False,
            "browser.startup.homepage_override"
            ".mstone": "ignore",
            # Reduce unique identifiers
            "privacy.resistFingerprinting"
            ".letterboxing": False,
            # Disable Push notifications (reduce fp surface)
            "dom.push.enabled": False,
            # Keep SW enabled - disabling is suspicious
            "dom.serviceWorkers.enabled": True,
            # WebRTC hardening
            "media.peerconnection.ice"
            ".default_address_only": True,
            "media.peerconnection.ice"
            ".no_host": True,
            "media.peerconnection.ice"
            ".proxy_only": True,
            "media.peerconnection.ice"
            ".relay_only": True,
            "media.peerconnection.turn.disable": True,
            # Disable battery API
            "dom.battery.enabled": False,
            # Enable DRM for compatibility
            "media.eme.enabled": True,
            # Disable Pocket and Mozilla services
            "extensions.pocket.enabled": False,
            "browser.newtabpage.activity-stream"
            ".feeds.section.topstories": False,
            # Avoid DNS prefetch leaking real IP
            "network.dns.disablePrefetch": True,
            "network.prefetch-next": False,
            "network.dns.disablePrefetchFromHTTPS": True,
            # Proper referrer policy (blocking is suspicious)
            "network.http.referer.XOriginPolicy": 0,
            # Canvas fingerprinting protection
            "privacy.resistFingerprinting": False,
            "canvas.poisondata": False,
            # Font fingerprinting protection
            "browser.display.use_document_fonts": 1,
            "layout.css.font-visibility.level": 1,
            # WebGL debug extension info leak
            "webgl.enable-debug-renderer-info": True,
            # Proxy connection settings
            "network.proxy.socks_remote_dns": True,
            "network.trr.mode": (
                3 if self.proxy else 0
            ),
            # Prevent speculative connections
            "network.http.speculative-parallel-limit": 0,
            "browser.urlbar"
            ".speculativeConnect.enabled": False,
            # Notifications API (blocking is suspicious)
            "dom.webnotifications.enabled": True,
            "permissions.default"
            ".desktop-notification": 0,
            # Let our JS spoof handle concurrency
            "dom.maxHardwareConcurrency": 0,
            # Required for some sites
            "dom.event.clipboardevents.enabled": True,
            # Connection pooling
            "network.http"
            ".max-persistent-connections-per-server": 6,
            "network.http"
            ".max-persistent-connections-per-proxy": 8,
            # Telemetry beacons (blocking is detectable)
            "beacon.enabled": True,
            "dom.enable_performance": True,
            # SharedWorker (blocking is suspicious)
            "dom.workers.sharedWorkers.enabled": True,
        }
        kwargs["firefox_user_prefs"] = firefox_prefs

        # Keep the camoufox instance wrapper
        try:
            self.camoufox = AsyncCamoufox(**kwargs)
            self.browser = await self.camoufox.__aenter__()
            return self
        except Exception as e:
            try:
                from maxminddb.errors import InvalidDatabaseError
            except Exception:
                InvalidDatabaseError = None

            is_geoip_error = (
                (
                    InvalidDatabaseError
                    and isinstance(e, InvalidDatabaseError)
                )
                or "GeoLite2-City.mmdb" in str(e)
            )
            if is_geoip_error:
                logger.warning(
                    "GeoIP database invalid or missing."
                    " Retrying launch with geoip disabled.",
                )
                kwargs["geoip"] = False
                self.camoufox = AsyncCamoufox(**kwargs)
                self.browser = (
                    await self.camoufox.__aenter__()
                )
                return self
            raise

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def create_context(
        self,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        profile_name: Optional[str] = None,
        locale_override: Optional[str] = None,
        timezone_override: Optional[str] = None,
        allow_sticky_proxy: bool = True,
        block_images_override: Optional[bool] = None,
        block_media_override: Optional[bool] = None,
    ) -> BrowserContext:
        """Create an isolated browser context with per-profile stealth.

        Each context gets its own proxy, fingerprint
        (canvas/WebGL/audio seeds), locale/timezone,
        resource-blocker, and stealth-script injection.  Cookies
        from previous sessions are loaded automatically.

        Args:
            proxy: ``user:pass@host:port`` proxy string
                (or ``None``).
            user_agent: Custom User-Agent (or ``None`` for random).
            profile_name: Profile identifier for sticky sessions /
                cookies.
            locale_override: Force a specific locale
                (e.g. ``en-US``).
            timezone_override: Force a specific IANA timezone.
            allow_sticky_proxy: Load a previously-bound proxy for
                this profile.
            block_images_override: Override global image-blocking.
            block_media_override: Override global media-blocking.

        Returns:
            A configured Playwright ``BrowserContext``.

        Raises:
            RuntimeError: If the browser has not been launched yet.
        """
        if not self.browser:
            raise RuntimeError(
                "Browser not launched. Call launch() first."
            )

        # Sticky Session Logic: Register proxy with solver
        if proxy and self._secure_storage:
            logger.debug(
                "Creating sticky context for %s with proxy %s",
                profile_name, proxy,
            )

        # Randomised screen resolutions using StealthHub
        stealth_data = StealthHub.get_random_dimensions()
        dims = (
            stealth_data["width"], stealth_data["height"],
        )

        # Load or generate persistent fingerprint settings
        locale = None
        timezone_id = None
        languages = None
        platform_name = None
        viewport_width = None
        viewport_height = None
        device_scale_factor = None
        audio_seed = None
        if profile_name:
            fingerprint = (
                await self.load_profile_fingerprint(
                    profile_name,
                )
            )
            if fingerprint:
                locale = fingerprint.get("locale")
                timezone_id = fingerprint.get("timezone_id")
                languages = fingerprint.get("languages")
                platform_name = fingerprint.get("platform")
                viewport_width = fingerprint.get(
                    "viewport_width",
                )
                viewport_height = fingerprint.get(
                    "viewport_height",
                )
                device_scale_factor = fingerprint.get(
                    "device_scale_factor",
                )
                audio_seed = fingerprint.get("audio_seed")
                logger.debug(
                    "Using persistent fingerprint for"
                    " %s: %s, %s",
                    profile_name, locale, timezone_id,
                )

        # Generate new fingerprint if not found
        canvas_seed = None
        gpu_index = None
        if locale_override:
            locale = locale_override
        if timezone_override:
            timezone_id = timezone_override

        if not locale or not timezone_id:
            locale = random.choice([
                "en-US", "en-GB", "en-CA", "en-AU",
            ])
            # Use geo-consistent timezone
            timezone_id = (
                StealthHub.get_consistent_locale_timezone(
                    locale,
                )
            )

            if not languages:
                languages = [
                    locale, locale.split("-")[0],
                ]
            if not platform_name:
                platform_name = random.choice([
                    "Win32", "MacIntel", "Linux x86_64",
                ])
            if (
                viewport_width is None
                or viewport_height is None
            ):
                viewport_width, viewport_height = dims
            if device_scale_factor is None:
                device_scale_factor = random.choice(
                    [1.0, 1.25, 1.5],
                )

            # Save for future use
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
                    device_scale_factor=device_scale_factor,
                )
                logger.info(
                    "Generated and saved fingerprint for"
                    " %s: %s, %s",
                    profile_name, locale, timezone_id,
                )
        else:
            # Load canvas/WebGL params from existing fingerprint
            fingerprint_data = fingerprint or {}
            raw_canvas_seed = fingerprint_data.get(
                "canvas_seed",
            )
            raw_gpu_index = fingerprint_data.get("gpu_index")
            canvas_seed = (
                int(raw_canvas_seed)
                if raw_canvas_seed is not None
                else None
            )
            gpu_index = (
                int(raw_gpu_index)
                if raw_gpu_index is not None
                else None
            )
            raw_audio_seed = fingerprint_data.get(
                "audio_seed",
            )
            audio_seed = (
                int(raw_audio_seed)
                if raw_audio_seed is not None
                else None
            )

        if profile_name and (
            locale_override or timezone_override
        ):
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
                device_scale_factor=device_scale_factor,
            )

        if profile_name and any(
            v is None for v in [
                audio_seed, languages, platform_name,
                viewport_width, viewport_height,
                device_scale_factor,
            ]
        ):
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
                device_scale_factor=device_scale_factor,
            )

        context_args: Dict[str, Any] = {
            "user_agent": (
                user_agent
                or StealthHub.get_human_ua(self.user_agents)
            ),
            "viewport": {
                "width": viewport_width or dims[0],
                "height": viewport_height or dims[1],
            },
            "device_scale_factor": (
                device_scale_factor
                if device_scale_factor is not None
                else random.choice([1.0, 1.25, 1.5])
            ),
            "permissions": ["geolocation", "notifications"],
            "locale": locale,
            "timezone_id": timezone_id,
            "bypass_csp": True,
            "ignore_https_errors": True,
        }

        # Sticky Session Logic: Resolve and Persist Proxy
        if profile_name and allow_sticky_proxy:
            # Load existing binding
            saved_proxy = await self.load_proxy_binding(
                profile_name,
            )

            if proxy and self._is_proxy_blacklisted(proxy):
                logger.warning(
                    "Requested proxy for %s is dead/cooldown."
                    " Ignoring: %s",
                    profile_name, proxy,
                )
                proxy = None
                await self.remove_proxy_binding(profile_name)

            if saved_proxy:
                if self._is_proxy_blacklisted(saved_proxy):
                    logger.warning(
                        "Sticky proxy for %s is"
                        " dead/cooldown."
                        " Clearing binding: %s",
                        profile_name, saved_proxy,
                    )
                    await self.remove_proxy_binding(
                        profile_name,
                    )
                    saved_proxy = None

            if saved_proxy:
                # Sticky: Use saved unless rotation
                if proxy and proxy != saved_proxy:
                    logger.info(
                        "Rotation detected for %s."
                        " Updating sticky binding:"
                        " %s -> %s",
                        profile_name, saved_proxy, proxy,
                    )
                    await self.save_proxy_binding(
                        profile_name, proxy,
                    )
                else:
                    if not proxy:
                        logger.debug(
                            "Using sticky proxy for"
                            " %s: %s",
                            profile_name, saved_proxy,
                        )
                    proxy = saved_proxy
            elif proxy:
                # No existing binding, create one
                logger.info(
                    "Binding %s to proxy %s",
                    profile_name, proxy,
                )
                await self.save_proxy_binding(
                    profile_name, proxy,
                )
        elif profile_name and not allow_sticky_proxy:
            # Clear binding when bypassing proxies
            await self.remove_proxy_binding(profile_name)
            if proxy:
                logger.debug(
                    "Sticky proxy disabled for %s;"
                    " using explicit proxy %s",
                    profile_name, proxy,
                )
            else:
                logger.debug(
                    "Sticky proxy disabled for %s;"
                    " no proxy will be used",
                    profile_name,
                )
                proxy = None

        if proxy:
            # Parse proxy string if it's a URL
            if "://" in proxy:
                p = urlparse(proxy)
                context_args["proxy"] = {
                    "server": (
                        f"{p.scheme}://"
                        f"{p.hostname}:{p.port}"
                    ),
                    "username": p.username,
                    "password": p.password,
                }
            else:
                context_args["proxy"] = {"server": proxy}

        # Realistic HTTP headers
        accept_language_map = {
            "en-US": "en-US,en;q=0.9",
            "en-GB": "en-GB,en;q=0.9",
            "en-CA": "en-CA,en;q=0.9,en-US;q=0.8",
            "en-AU": "en-AU,en;q=0.9,en-US;q=0.8",
            "de-DE": "de-DE,de;q=0.9,en;q=0.8",
            "fr-FR": "fr-FR,fr;q=0.9,en;q=0.8",
            "ja-JP": "ja-JP,ja;q=0.9,en;q=0.8",
            "ko-KR": "ko-KR,ko;q=0.9,en;q=0.8",
            "zh-CN": "zh-CN,zh;q=0.9,en;q=0.8",
            "pt-BR": "pt-BR,pt;q=0.9,en;q=0.8",
            "es-ES": "es-ES,es;q=0.9,en;q=0.8",
        }
        ua = context_args.get("user_agent", "")

        # Ensure platform_name is consistent with UA
        if ua and not platform_name:
            platform_name = (
                StealthHub.get_consistent_platform_for_ua(ua)
            )

        extra_headers: Dict[str, Optional[str]] = {
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": accept_language_map.get(
                locale or "en-US", "en-US,en;q=0.9",
            ),
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            # ~75% have DNT
            "DNT": random.choice(["1", "1", "1", None]),
            "Priority": "u=0, i",
        }

        # Add Sec-CH-UA client hints based on UA string
        if "Chrome/" in ua:
            chrome_ver = (
                ua.split("Chrome/")[-1]
                .split(" ")[0]
                .split(".")[0]
            )
            extra_headers["Sec-CH-UA"] = (
                f'"Chromium";v="{chrome_ver}",'
                f' "Google Chrome";v="{chrome_ver}",'
                f' "Not-A.Brand";v="99"'
            )
            extra_headers["Sec-CH-UA-Mobile"] = "?0"
            plat = platform_name or "Windows"
            extra_headers["Sec-CH-UA-Platform"] = (
                f'"{plat}"'
            )
            extra_headers[
                "Sec-CH-UA-Full-Version-List"
            ] = (
                f'"Chromium";v="{chrome_ver}.0.0.0",'
                f' "Google Chrome";v="{chrome_ver}.0.0.0",'
                f' "Not-A.Brand";v="99.0.0.0"'
            )
        elif "Edg/" in ua:
            edge_ver = (
                ua.split("Edg/")[-1].split(".")[0]
            )
            extra_headers["Sec-CH-UA"] = (
                f'"Chromium";v="{edge_ver}",'
                f' "Microsoft Edge";v="{edge_ver}",'
                f' "Not-A.Brand";v="99"'
            )
            extra_headers["Sec-CH-UA-Mobile"] = "?0"
            extra_headers["Sec-CH-UA-Platform"] = (
                '"Windows"'
            )
            extra_headers[
                "Sec-CH-UA-Full-Version-List"
            ] = (
                f'"Chromium";v="{edge_ver}.0.0.0",'
                f' "Microsoft Edge";v="{edge_ver}.0.0.0",'
                f' "Not-A.Brand";v="99.0.0.0"'
            )

        # Remove None values (e.g. DNT)
        filtered_headers: Dict[str, str] = {
            k: v
            for k, v in extra_headers.items()
            if v is not None
        }
        context_args["extra_http_headers"] = filtered_headers

        logger.info(
            "Creating isolated stealth context"
            " (Profile: %s, Proxy: %s, Resolution: %sx%s)",
            profile_name or "Anonymous",
            proxy or "None",
            dims[0], dims[1],
        )
        context = await self.browser.new_context(
            **context_args,
        )

        # Set global timeout for this context
        context.set_default_timeout(self.timeout)

        # Anti-Fingerprinting Suite v3.0 via StealthHub
        # Deterministic params if not from existing fingerprint
        if canvas_seed is None and profile_name:
            canvas_seed = hash(profile_name) % 1000000
        if gpu_index is None and profile_name:
            gpu_index = (
                hash(profile_name + "_gpu") % 17
            )
        if audio_seed is None and profile_name:
            audio_seed = (
                hash(profile_name + "_audio") % 1000000
            )

        # Defaults for anonymous profiles
        if canvas_seed is None:
            canvas_seed = 12345
        if gpu_index is None:
            gpu_index = 0
        if audio_seed is None:
            audio_seed = 98765

        if not languages:
            languages = [
                locale or "en-US",
                (locale or "en-US").split("-")[0],
            ]
        if not platform_name:
            platform_name = "Win32"

        # Derive hardware_concurrency per profile
        hardware_concurrency = None
        if profile_name:
            hardware_concurrency = (
                4 + (hash(profile_name + "_cores") % 5) * 2
            )  # 4, 6, 8, 10, 12

        await context.add_init_script(
            StealthHub.get_stealth_script(
                canvas_seed=canvas_seed,
                gpu_index=gpu_index,
                audio_seed=audio_seed,
                languages=languages,
                platform=platform_name,
                hardware_concurrency=hardware_concurrency,
            )
        )
        logger.debug(
            "Injected stealth v4.0: canvas_seed=%s,"
            " gpu=%s, cores=%s",
            canvas_seed, gpu_index, hardware_concurrency,
        )

        # Apply Resource Blocker
        block_img = (
            self.block_images
            if block_images_override is None
            else block_images_override
        )
        block_med = (
            self.block_media
            if block_media_override is None
            else block_media_override
        )
        blocker = ResourceBlocker(
            block_images=block_img, block_media=block_med,
        )
        await context.route("**/*", blocker.handle_route)
        # Attach for external access
        context.resource_blocker = blocker  # type: ignore[attr-defined]

        # Load cookies if profile name provided
        if profile_name:
            await self.load_cookies(context, profile_name)

        return context

    # ------------------------------------------------------------------
    # Cookie persistence
    # ------------------------------------------------------------------

    async def save_cookies(
        self,
        context: BrowserContext,
        profile_name: str,
    ) -> None:
        """Persist browser cookies to disk for session reuse.

        Uses :class:`SecureCookieStorage` (Fernet encryption) when
        available; falls back to plain JSON.

        Args:
            context: The browser context whose cookies to save.
            profile_name: Unique key (typically ``faucet_username``).
        """
        try:
            cookies = await context.cookies()

            # Use encrypted storage if available
            if self._secure_storage:
                await self._secure_storage.save_cookies(
                    cookies, profile_name,
                )
            else:
                # Fallback to unencrypted (backward compat)
                cookies_dir = CONFIG_DIR / "cookies"
                cookies_dir.mkdir(exist_ok=True)
                cookies_file = (
                    cookies_dir / f"{profile_name}.json"
                )
                with open(cookies_file, "w") as f:
                    json.dump(cookies, f)
                logger.debug(
                    "Saved %d cookies for %s (unencrypted)",
                    len(cookies), profile_name,
                )
        except Exception as e:
            logger.warning(
                "Failed to save cookies for %s: %s",
                profile_name, e,
            )

    async def load_cookies(
        self,
        context: BrowserContext,
        profile_name: str,
    ) -> bool:
        """Load previously saved cookies into a browser context.

        Tries encrypted storage first, falls back to unencrypted.

        Args:
            context: The browser context to load cookies into.
            profile_name: Unique identifier for this profile.

        Returns:
            ``True`` if cookies were loaded successfully,
            ``False`` otherwise.
        """
        cookies = None

        try:
            # Try encrypted storage first
            if self._secure_storage:
                cookies = (
                    await self._secure_storage.load_cookies(
                        profile_name,
                    )
                )

            # Fallback to unencrypted
            if not cookies:
                cookies_file = (
                    CONFIG_DIR
                    / "cookies"
                    / f"{profile_name}.json"
                )
                if os.path.exists(cookies_file):
                    with open(cookies_file, "r") as f:
                        cookies = json.load(f)
                    logger.debug(
                        "Loaded unencrypted cookies for %s",
                        profile_name,
                    )

            if cookies:
                await context.add_cookies(cookies)
                logger.info(
                    "Loaded %d cookies for %s",
                    len(cookies), profile_name,
                )
                return True

            if self.seed_cookie_jar:
                await self._seed_cookie_jar(
                    context, profile_name,
                )
                return True

            logger.debug(
                "No saved cookies for %s", profile_name,
            )
            return False

        except Exception as e:
            logger.warning(
                "Failed to load cookies for %s: %s",
                profile_name, e,
            )
            return False

    def _load_cookie_profile(self) -> dict:
        """Load cookie profile metadata from disk.

        Returns:
            Dict of profile metadata, or empty dict.
        """
        profile_file = CONFIG_DIR / "cookie_profiles.json"
        if os.path.exists(profile_file):
            data = self._safe_json_read(str(profile_file))
            return data or {}
        return {}

    def _save_cookie_profile(self, data: dict) -> None:
        """Save cookie profile metadata to disk.

        Args:
            data: Profile metadata dictionary.
        """
        profile_file = CONFIG_DIR / "cookie_profiles.json"
        self._safe_json_write(str(profile_file), data)

    async def _seed_cookie_jar(
        self,
        context: BrowserContext,
        profile_name: str,
    ) -> None:
        """Seed a minimal cookie jar to avoid a new-profile signature.

        Uses realistic domain/cookie patterns that mimic organic
        browsing:

        - Popular sites with realistic cookie names
        - Consent cookies (GDPR compliance signals)
        - Age-appropriate creation timestamps

        Args:
            context: Browser context to seed.
            profile_name: Profile identifier.
        """
        profiles = self._load_cookie_profile()
        entry = profiles.get(profile_name, {})

        if "created_at" not in entry:
            back_days = random.randint(14, 90)
            entry["created_at"] = (
                time.time() - (back_days * 86400)
            )

        # Realistic browsing history domains
        base_domains = [
            "google.com",
            "youtube.com",
            "wikipedia.org",
            "reddit.com",
            "amazon.com",
            "twitter.com",
            "github.com",
            "stackoverflow.com",
            "linkedin.com",
            "medium.com",
        ]

        # Realistic cookie name templates
        cookie_templates = [
            {
                "name": "_ga",
                "value_fn": lambda: (
                    f"GA1.2."
                    f"{random.randint(100000000, 999999999)}"
                    f".{int(time.time()) - random.randint(86400, 7776000)}"
                ),
            },
            {
                "name": "_gid",
                "value_fn": lambda: (
                    f"GA1.2."
                    f"{random.randint(100000000, 999999999)}"
                    f".{int(time.time()) - random.randint(0, 86400)}"
                ),
            },
            {
                "name": "NID",
                "value_fn": lambda: (
                    f"{random.randint(100, 999)}="
                    f"{random.randbytes(32).hex()[:40]}"
                ),
            },
            {
                "name": "CONSENT",
                "value_fn": lambda: (
                    f"YES+cb."
                    f"{int(time.time()) - random.randint(0, 31536000):010d}"
                    f"-04-p0.en+FX+"
                    f"{random.randint(100, 999)}"
                ),
            },
            {
                "name": "PREF",
                "value_fn": lambda: (
                    f"tz={random.choice(['America.New_York', 'America.Los_Angeles', 'Europe.London'])}"
                    f"&f6=40000000&f7=100"
                ),
            },
            {
                "name": "cookie_consent",
                "value_fn": lambda: random.choice([
                    "accepted", "true", "1",
                ]),
            },
            {
                "name": "_fbp",
                "value_fn": lambda: (
                    f"fb.1."
                    f"{int(time.time() * 1000) - random.randint(0, 86400000)}"
                    f".{random.randint(100000000, 999999999)}"
                ),
            },
            {
                "name": "theme",
                "value_fn": lambda: random.choice([
                    "light", "dark", "auto",
                ]),
            },
            {
                "name": "lang",
                "value_fn": lambda: random.choice([
                    "en", "en-US", "en-GB",
                ]),
            },
            {
                "name": "session_id",
                "value_fn": lambda: random.randbytes(16).hex(),
            },
        ]

        cookie_count = entry.get("cookie_count")
        if not cookie_count:
            cookie_count = random.randint(12, 30)
            entry["cookie_count"] = cookie_count

        profiles[profile_name] = entry
        self._save_cookie_profile(profiles)

        now = time.time()
        created_at = entry["created_at"]
        age_days = max(1, int((now - created_at) / 86400))

        cookies: List[Dict[str, Any]] = []
        used_combos: set = set()

        for _ in range(cookie_count):
            domain = random.choice(base_domains)
            template = random.choice(cookie_templates)
            combo_key = f"{domain}:{template['name']}"

            # Avoid duplicate domain+name combos
            if combo_key in used_combos:
                continue
            used_combos.add(combo_key)

            max_age_days = random.randint(30, 365)
            expires = int(
                created_at + (max_age_days * 86400),
            )
            if expires < now:
                expires = int(
                    now + random.randint(30, 180) * 86400,
                )

            cookies.append({
                "name": template["name"],
                "value": template["value_fn"](),
                "domain": f".{domain}",
                "path": "/",
                "expires": expires,
                "httpOnly": random.random() < 0.3,
                "secure": True,
                "sameSite": random.choice([
                    "Lax", "None", "Lax",
                ]),
            })

        if cookies:
            await context.add_cookies(cookies)
            logger.info(
                "Seeded %d realistic cookies for %s"
                " (age ~%dd)",
                len(cookies), profile_name, age_days,
            )

    # ------------------------------------------------------------------
    # Proxy bindings
    # ------------------------------------------------------------------

    async def save_proxy_binding(
        self, profile_name: str, proxy: str,
    ) -> None:
        """Save the proxy binding for a profile (sticky sessions).

        Args:
            profile_name: Profile identifier.
            proxy: Proxy URL to bind.
        """
        try:
            bindings_file = (
                CONFIG_DIR / "proxy_bindings.json"
            )
            data = (
                self._safe_json_read(str(bindings_file))
                or {}
            )
            data[profile_name] = proxy
            self._safe_json_write(str(bindings_file), data)
        except Exception as e:
            logger.error(
                "Failed to save proxy binding for %s: %s",
                profile_name, e,
            )

    async def remove_proxy_binding(
        self, profile_name: str,
    ) -> None:
        """Remove a sticky proxy binding for a profile.

        Args:
            profile_name: Profile identifier.
        """
        try:
            bindings_file = (
                CONFIG_DIR / "proxy_bindings.json"
            )
            if not os.path.exists(bindings_file):
                return
            data = (
                self._safe_json_read(str(bindings_file))
                or {}
            )
            if profile_name in data:
                data.pop(profile_name, None)
                self._safe_json_write(
                    str(bindings_file), data,
                )
        except Exception as e:
            logger.error(
                "Failed to remove proxy binding for %s: %s",
                profile_name, e,
            )

    async def load_proxy_binding(
        self, profile_name: str,
    ) -> Optional[str]:
        """Load the sticky proxy for a profile.

        Args:
            profile_name: Profile identifier.

        Returns:
            Proxy URL string, or ``None``.
        """
        try:
            bindings_file = (
                CONFIG_DIR / "proxy_bindings.json"
            )
            if os.path.exists(bindings_file):
                data = self._safe_json_read(
                    str(bindings_file),
                )
                if data:
                    return data.get(profile_name)
            return None
        except Exception as e:
            logger.error(
                "Failed to load proxy binding for %s: %s",
                profile_name, e,
            )
            return None

    # ------------------------------------------------------------------
    # Fingerprint persistence
    # ------------------------------------------------------------------

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
        device_scale_factor: Optional[float] = None,
    ) -> None:
        """Persist deterministic fingerprint parameters.

        Values default to hashes of *profile_name* when ``None``,
        ensuring the same profile always gets the same
        canvas/WebGL/audio fingerprint across sessions.

        Args:
            profile_name: Unique profile key.
            locale: BCP-47 locale (e.g. ``en-US``).
            timezone_id: IANA timezone
                (e.g. ``America/New_York``).
            canvas_seed: Seed for canvas noise generation.
            gpu_index: Index into GPU config array (0--16).
            audio_seed: Seed for audio fingerprint noise.
            languages: Navigator language list.
            platform: ``navigator.platform`` value.
            viewport_width: Viewport width in pixels.
            viewport_height: Viewport height in pixels.
            device_scale_factor: Device pixel ratio.
        """
        try:
            fingerprint_file = (
                CONFIG_DIR / "profile_fingerprints.json"
            )
            data = (
                self._safe_json_read(str(fingerprint_file))
                or {}
            )

            # Generate deterministic params from profile name
            if canvas_seed is None:
                canvas_seed = hash(profile_name) % 1000000

            if gpu_index is None:
                gpu_index = (
                    hash(profile_name + "_gpu") % 17
                )

            if audio_seed is None:
                audio_seed = (
                    hash(profile_name + "_audio") % 1000000
                )

            if languages is None:
                languages = [
                    locale, locale.split("-")[0],
                ]

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
                "device_scale_factor": device_scale_factor,
            }

            self._safe_json_write(
                str(fingerprint_file), data,
            )

            logger.debug(
                "Saved fingerprint for %s:"
                " canvas_seed=%s, gpu_index=%s",
                profile_name, canvas_seed, gpu_index,
            )
        except Exception as e:
            logger.error(
                "Failed to save fingerprint for %s: %s",
                profile_name, e,
            )

    async def load_profile_fingerprint(
        self, profile_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Load persisted fingerprint parameters for a profile.

        Args:
            profile_name: Unique profile key.

        Returns:
            Dict of fingerprint settings, or ``None`` if not found.
        """
        try:
            fingerprint_file = (
                CONFIG_DIR / "profile_fingerprints.json"
            )
            if os.path.exists(fingerprint_file):
                data = self._safe_json_read(
                    str(fingerprint_file),
                )
                if data:
                    return data.get(profile_name)
            return None
        except Exception as e:
            logger.error(
                "Failed to load fingerprint for %s: %s",
                profile_name, e,
            )
            return None

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    async def new_page(
        self, context: Optional[BrowserContext] = None,
    ) -> Page:
        """Create a new page in *context* (or the default context).

        When using the default context, a
        :class:`ResourceBlocker` is automatically attached.

        Args:
            context: Specific context to use
                (``None`` for default).

        Returns:
            A new Playwright ``Page``.

        Raises:
            RuntimeError: If the context is closed or unresponsive.
        """
        if not self.browser:
            await self.launch()

        if context:
            # Verify context is still alive
            if not await self.check_context_alive(context):
                raise RuntimeError(
                    "Cannot create page: context is closed"
                    " or unresponsive"
                )
            page = await context.new_page()
        else:
            # Global context page
            page = await self.browser.new_page()
            blocker = ResourceBlocker(
                block_images=True, block_media=True,
            )
            await page.route("**/*", blocker.handle_route)
            page.resource_blocker = blocker  # type: ignore[attr-defined]

        return page

    async def safe_new_page(
        self, context: BrowserContext,
    ) -> Optional[Page]:
        """Create a new page with a context-health pre-check.

        Args:
            context: The context to create the page in.

        Returns:
            A new ``Page``, or ``None`` if the context is closed.
        """
        try:
            if not await self.check_context_alive(context):
                logger.warning(
                    "Cannot create page: context is not alive",
                )
                return None
            return await context.new_page()
        except Exception as e:
            err_str = str(e).lower()
            if "closed" in err_str and (
                "target" in err_str
                or "connection" in err_str
            ):
                logger.debug(
                    "Context closed during page creation:"
                    " %s", e,
                )
            else:
                logger.warning(
                    "Failed to create page: %s", e,
                )
            return None

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def restart(self) -> None:
        """Restart the browser to clear memory and hung processes."""
        logger.info("Restarting browser instance...")
        await self.close()
        await asyncio.sleep(2)
        await self.launch()
        logger.info("Browser instance restarted.")

    async def check_health(self) -> bool:
        """Verify the browser process is still responsive.

        Creates and immediately closes a throwaway context as a
        lightweight liveness probe.

        Returns:
            ``True`` if the browser responded, ``False`` otherwise.
        """
        if not self.browser:
            return False
        try:
            context = await self.browser.new_context()
            await context.close()
            return True
        except Exception as e:
            logger.warning(
                "Browser health check failed: %s", e,
            )
            return False

    async def check_context_alive(
        self, context: BrowserContext,
    ) -> bool:
        """Check if a context is still alive and usable.

        Creates and immediately closes a test page.  The context is
        added to the ``_closed_contexts`` set on failure.

        Args:
            context: The context to probe.

        Returns:
            ``True`` if the context is responsive.
        """
        try:
            if not context:
                return False

            # Check if in our closed set
            context_id = id(context)
            if context_id in self._closed_contexts:
                logger.debug(
                    "Context %s is in closed set",
                    context_id,
                )
                return False

            # Lightweight operation that fails if closed
            test_page = await asyncio.wait_for(
                context.new_page(), timeout=5.0,
            )
            await test_page.close()
            return True
        except asyncio.TimeoutError:
            logger.debug(
                "Context health check timed out"
                " - context likely frozen",
            )
            if context:
                self._closed_contexts.add(id(context))
            return False
        except Exception as e:
            err_str = str(e).lower()
            if not (
                "closed" in err_str
                and (
                    "target" in err_str
                    or "connection" in err_str
                )
            ):
                logger.debug(
                    "Context health check failed: %s", e,
                )
            if context:
                self._closed_contexts.add(id(context))
            return False

    async def check_page_alive(
        self, page: Page,
    ) -> bool:
        """Check if a page is still alive and responsive.

        Evaluates ``1 + 1`` with a 3-second timeout.

        Args:
            page: The page to probe.

        Returns:
            ``True`` if the page responded.
        """
        try:
            if not page:
                return False
            if page.is_closed():
                return False
            # Add timeout to prevent hanging on frozen pages
            await asyncio.wait_for(
                page.evaluate("1 + 1"), timeout=3.0,
            )
            return True
        except asyncio.TimeoutError:
            logger.debug(
                "Page health check timed out"
                " - page likely frozen",
            )
            return False
        except Exception as e:
            err_str = str(e).lower()
            if not (
                "closed" in err_str
                and (
                    "target" in err_str
                    or "connection" in err_str
                )
            ):
                logger.debug(
                    "Page health check failed: %s", e,
                )
            return False

    async def safe_close_context(
        self,
        context: BrowserContext,
        profile_name: Optional[str] = None,
    ) -> bool:
        """Safely close a browser context with health checks.

        Saves cookies before closing and tracks closed contexts to
        prevent double-close errors.

        Args:
            context: The context to close.
            profile_name: Optional profile name for cookie saving.

        Returns:
            ``True`` if successfully closed, ``False`` if already
            closed or error.
        """
        if not context:
            return False

        context_id = id(context)

        # Check if already closed
        if context_id in self._closed_contexts:
            logger.debug(
                "Context %s already marked as closed",
                context_id,
            )
            return False

        try:
            # Check if context is still alive
            is_alive = await self.check_context_alive(context)

            if is_alive and profile_name:
                # Try to save cookies before closing
                try:
                    await asyncio.wait_for(
                        self.save_cookies(
                            context, profile_name,
                        ),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Cookie save timed out for %s",
                        profile_name,
                    )
                except Exception as e:
                    logger.debug(
                        "Cookie save failed for %s: %s",
                        profile_name, e,
                    )

            if is_alive:
                # Close the context with timeout
                await asyncio.wait_for(
                    context.close(), timeout=5.0,
                )
                logger.debug(
                    "Successfully closed context %s",
                    context_id,
                )
            else:
                logger.debug(
                    "Context %s was already closed"
                    " - skipping close()",
                    context_id,
                )

            # Mark as closed
            self._closed_contexts.add(context_id)
            return True

        except asyncio.TimeoutError:
            logger.warning(
                "Context close timed out for %s",
                context_id,
            )
            self._closed_contexts.add(context_id)
            return False
        except Exception as e:
            err_str = str(e).lower()
            if "closed" in err_str and (
                "target" in err_str
                or "connection" in err_str
            ):
                logger.debug(
                    "Context close on already-closed"
                    " context: %s", e,
                )
            else:
                logger.warning(
                    "Context close failed: %s", e,
                )
            self._closed_contexts.add(context_id)
            return False

    async def check_page_status(
        self, page: Page,
    ) -> Dict[str, Any]:
        """Probe the page for HTTP-level blocks or network errors.

        Issues a lightweight ``HEAD`` fetch against the current URL
        from within the page context.

        Args:
            page: The page to check.

        Returns:
            Dict with keys ``blocked`` (bool),
            ``network_error`` (bool), and ``status``
            (int HTTP code, ``0`` for network error,
            ``-1`` for unknown).
        """
        try:
            # First verify page is still alive
            if not await self.check_page_alive(page):
                logger.warning(
                    "Page is closed - cannot check status",
                )
                return {
                    "blocked": False,
                    "network_error": True,
                    "status": -1,
                }

            head_js = (
                "async () => {"
                " try {"
                " return (await fetch("
                "window.location.href,"
                " {method: 'HEAD'})).status;"
                " } catch(e) { return 0; }"
                " }"
            )
            status = await page.evaluate(head_js)

            if status in (403, 401):
                return {
                    "blocked": True,
                    "network_error": False,
                    "status": status,
                }
            if status == 0:
                return {
                    "blocked": False,
                    "network_error": True,
                    "status": 0,
                }

            return {
                "blocked": False,
                "network_error": False,
                "status": status,
            }
        except Exception as e:
            logger.debug("Status check failed: %s", e)
            return {
                "blocked": False,
                "network_error": False,
                "status": -1,
            }

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Shut down the browser and clear all tracking state."""
        if self.browser:
            try:
                await self.camoufox.__aexit__(
                    None, None, None,
                )
            except Exception as e:
                logger.debug(
                    "Error during browser exit: %s", e,
                )
            self.browser = None
            # Clear closed contexts tracking
            self._closed_contexts.clear()
            logger.info("Browser closed.")


# ------------------------------------------------------------------
# Factory helper
# ------------------------------------------------------------------

async def create_stealth_browser(
    headless: bool = True,
    proxy: Optional[str] = None,
) -> AsyncCamoufox:
    """Create a standalone stealth browser context manager.

    This is a lightweight factory for one-off usage with
    ``async with``.  For full lifecycle management, use
    :class:`BrowserManager` instead.

    Args:
        headless: Whether to run in headless mode.
        proxy: Optional proxy server address.

    Returns:
        An ``AsyncCamoufox`` context manager.
    """
    return AsyncCamoufox(
        headless=headless,
        geoip=True,
        humanize=True,
        block_images=True,
        proxy={"server": proxy} if proxy else None,
    )
