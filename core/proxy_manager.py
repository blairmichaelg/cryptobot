"""Residential proxy pool manager for Cryptobot Gen 3.0.

Manages proxy sourcing (2Captcha, Webshare, Zyte, Azure VMs, DigitalOcean
droplets), sticky session assignment, health monitoring, latency tracking,
reputation scoring, and cooldown / burn policies.

Key class:
    ProxyManager: Singleton-like manager instantiated once by ``main.py``.

Proxy lifecycle::

    load -> validate -> assign (sticky 1:1 per account) -> monitor latency
    -> cooldown on detection -> burn (12 h) on repeated failures -> dead-list
"""

import asyncio
import json
import logging
import os
import random
import string
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

from core.config import AccountProfile, BotSettings, CONFIG_DIR
from core.utils import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)


@dataclass
class Proxy:
    """Represents a single proxy endpoint.

    Attributes:
        ip: Proxy hostname or IP address.
        port: Proxy port number.
        username: Authentication username (may be empty).
        password: Authentication password (may be empty).
        protocol: URL scheme -- ``http`` or ``https``.
    """

    ip: str
    port: int
    username: str
    password: str
    protocol: str = "http"

    def to_string(self) -> str:
        """Format the proxy as a URL string for Playwright.

        Returns:
            ``protocol://user:pass@ip:port`` (with credentials)
            or ``protocol://ip:port`` (without).
        """
        if self.username:
            # Include colon even if password is empty to
            # support providers that expect user: (e.g. Zyte)
            return (
                f"{self.protocol}://{self.username}:"
                f"{self.password}@{self.ip}:{self.port}"
            )
        return f"{self.protocol}://{self.ip}:{self.port}"

    def to_2captcha_string(self) -> str:
        """Format the proxy for the 2Captcha API (no scheme).

        Returns:
            ``user:pass@ip:port`` or ``ip:port``.
        """
        if self.username and self.password:
            return (
                f"{self.username}:{self.password}"
                f"@{self.ip}:{self.port}"
            )
        return f"{self.ip}:{self.port}"


class ProxyManager:
    """Manage proxy fetching, assignment, health, and rotation.

    Supports multiple proxy providers (2Captcha, Webshare, Zyte,
    Azure VMs, DigitalOcean droplets) unified behind a single
    interface.  Proxies are assigned in a *sticky session* model
    (one account = one proxy) and tracked for latency, failure
    count, and reputation score.

    Health data is persisted to ``config/proxy_health.json`` so
    that cooldowns and reputation survive restarts.
    """

    # Validation defaults (can be overridden via settings)
    VALIDATION_TIMEOUT_SECONDS = 15
    VALIDATION_TEST_URL = "https://www.google.com"
    LATENCY_HISTORY_MAX = 5
    DEAD_PROXY_THRESHOLD_MS = 5000
    DEAD_PROXY_FAILURE_COUNT = 3
    HOST_DETECTION_THRESHOLD = 3

    # Persistence constants
    HEALTH_FILE_VERSION = 1
    HEALTH_DATA_MAX_AGE = 86400 * 7  # 7 days

    def __init__(self, settings: BotSettings) -> None:
        """Initialise the proxy manager.

        Args:
            settings: Bot-wide configuration object.
        """
        self.settings = settings
        self.api_key = settings.twocaptcha_api_key
        self.proxy_provider = (
            (settings.proxy_provider or "2captcha").lower()
        )
        self.VALIDATION_TIMEOUT_SECONDS = getattr(
            settings,
            "proxy_validation_timeout_seconds",
            self.VALIDATION_TIMEOUT_SECONDS,
        )
        self.VALIDATION_TEST_URL = getattr(
            settings,
            "proxy_validation_url",
            self.VALIDATION_TEST_URL,
        )
        self.zyte_api_key = getattr(
            settings, "zyte_api_key", None,
        )
        self.zyte_proxy_host = (
            getattr(settings, "zyte_proxy_host", "api.zyte.com")
            or "api.zyte.com"
        )
        self.zyte_proxy_port = int(
            getattr(settings, "zyte_proxy_port", 8011) or 8011
        )
        self.zyte_proxy_protocol = (
            getattr(settings, "zyte_proxy_protocol", "http")
            or "http"
        )
        self.zyte_pool_size = int(
            getattr(settings, "zyte_pool_size", 20) or 20
        )
        self.proxies: List[Proxy] = []
        # Master list to preserve proxies during cooldown
        self.all_proxies: List[Proxy] = []
        self.validated_proxies: List[Proxy] = []
        self.assignments: Dict[str, Proxy] = {}
        # Prevent race condition in async assignment
        self._assignment_lock = asyncio.Lock()

        # Latency tracking: proxy_key -> latency measurements (ms)
        self.proxy_latency: Dict[str, List[float]] = {}
        # Failure tracking for dead proxy removal
        self.proxy_failures: Dict[str, int] = {}
        # Dead proxies that have been removed
        self.dead_proxies: List[str] = []
        # Host-level detection tracking (host:port -> count)
        self.proxy_host_failures: Dict[str, int] = {}
        # Cooldown tracking: proxy_key -> reuse timestamp
        self.proxy_cooldowns: Dict[str, float] = {}
        # Reputation scoring
        self.proxy_reputation: Dict[str, float] = {}
        self.proxy_soft_signals: Dict[str, Dict[str, int]] = {}
        # Cooldown durations (seconds)
        self.DETECTION_COOLDOWN = 3600      # 1 hour
        self.FAILURE_COOLDOWN = 300         # 5 minutes

        # Health persistence file
        self.health_file = str(CONFIG_DIR / "proxy_health.json")

        # Auto-load on init
        self.load_proxies_from_file()
        self._load_health_data()

        # Bootstrap Zyte proxies if configured and none loaded
        if not self.proxies and self.proxy_provider == "zyte":
            self._build_zyte_proxies(quantity=self.zyte_pool_size)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_zyte_proxies(self, quantity: int = 10) -> int:
        """Create in-memory Zyte proxy entries.

        No disk write to avoid key leakage.

        Args:
            quantity: Number of proxy entries to create.

        Returns:
            Number of proxies created.
        """
        if not self.zyte_api_key:
            logger.error(
                "[ZYTE] API key missing; cannot build pool."
            )
            return 0

        count = max(1, quantity)
        proxies = [
            Proxy(
                ip=self.zyte_proxy_host,
                port=self.zyte_proxy_port,
                username=self.zyte_api_key,
                password="",
                protocol=self.zyte_proxy_protocol,
            )
            for _ in range(count)
        ]

        self.all_proxies = list(proxies)
        self.proxies = list(proxies)
        self._prune_health_data_for_active_proxies(self.proxies)
        logger.info(
            "[ZYTE] Loaded %s proxy endpoint(s) (%s://%s:%s).",
            len(proxies),
            self.zyte_proxy_protocol,
            self.zyte_proxy_host,
            self.zyte_proxy_port,
        )
        return len(proxies)

    def _proxy_key(self, proxy: Proxy) -> str:
        """Generate a unique dict key for a proxy.

        Returns:
            Credentials + host:port without scheme prefix.
        """
        s = proxy.to_string()
        return s.split("://", 1)[1] if "://" in s else s

    def _mask_proxy_key(self, proxy_key: str) -> str:
        """Redact API keys / credentials for safe logging.

        Args:
            proxy_key: Raw proxy key string.

        Returns:
            Masked version with secrets replaced by ``***``.
        """
        try:
            if self.proxy_provider == "zyte" and self.zyte_api_key:
                if self.zyte_api_key in proxy_key:
                    return proxy_key.replace(
                        self.zyte_api_key, "***",
                    )
            if self.proxy_provider == "2captcha" and self.api_key:
                if self.api_key in proxy_key:
                    return proxy_key.replace(
                        self.api_key, "***",
                    )
        except Exception:
            return proxy_key
        return proxy_key

    def _proxy_host_port_from_str(
        self, proxy_str: str,
    ) -> str:
        """Extract ``host:port`` from a proxy URL string.

        Args:
            proxy_str: Proxy URL or bare ``host:port``.

        Returns:
            ``host:port`` string, or empty string on failure.
        """
        if not proxy_str:
            return ""
        try:
            candidate = (
                proxy_str
                if "://" in proxy_str
                else f"http://{proxy_str}"
            )
            parsed = urlparse(candidate)
            if parsed.hostname and parsed.port:
                return f"{parsed.hostname}:{parsed.port}"
        except Exception:
            return ""
        return ""

    def _proxy_host_port(self, proxy: Proxy) -> str:
        """Return ``host:port`` for the given *Proxy* object.

        Args:
            proxy: Proxy instance.

        Returns:
            ``host:port`` string, or empty string on error.
        """
        try:
            return f"{proxy.ip}:{proxy.port}"
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Health data persistence
    # ------------------------------------------------------------------

    def _load_health_data(self) -> None:
        """Load persisted proxy health data from disk.

        Includes versioning and stale-data filtering.
        """
        try:
            if not os.path.exists(self.health_file):
                logger.debug(
                    "No proxy health file found at %s",
                    self.health_file,
                )
                return

            data = safe_json_read(self.health_file)
            if not data:
                return

            # Version check
            version = data.get("version", 0)
            if version != self.HEALTH_FILE_VERSION:
                logger.warning(
                    "Proxy health file version mismatch "
                    "(expected %s, got %s). Ignoring.",
                    self.HEALTH_FILE_VERSION,
                    version,
                )
                return

            # Age check - ignore stale data
            saved_time = data.get("timestamp", 0)
            age = time.time() - saved_time
            if age > self.HEALTH_DATA_MAX_AGE:
                logger.info(
                    "Proxy health data is stale "
                    "(%.1f days old). Ignoring.",
                    age / 86400,
                )
                return

            # Load health data
            self.proxy_latency = data.get(
                "proxy_latency", {},
            )
            self.proxy_failures = data.get(
                "proxy_failures", {},
            )
            self.dead_proxies = data.get("dead_proxies", [])
            self.proxy_cooldowns = data.get(
                "proxy_cooldowns", {},
            )
            self.proxy_reputation = data.get(
                "proxy_reputation", {},
            )
            self.proxy_soft_signals = data.get(
                "proxy_soft_signals", {},
            )
            self.proxy_host_failures = data.get(
                "proxy_host_failures", {},
            )

            # Clean up expired cooldowns
            now = time.time()
            self.proxy_cooldowns = {
                k: v
                for k, v in self.proxy_cooldowns.items()
                if v > now
            }

            logger.info(
                "Loaded proxy health data: %d tracked, "
                "%d dead, %d in cooldown",
                len(self.proxy_latency),
                len(self.dead_proxies),
                len(self.proxy_cooldowns),
            )

        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse proxy health file: %s. "
                "Starting fresh.",
                e,
            )
        except Exception as e:
            logger.warning(
                "Failed to load proxy health data: %s", e,
            )

    def _prune_health_data_for_active_proxies(
        self, active_proxies: List[Proxy],
    ) -> None:
        """Remove stale health entries for absent proxies.

        Args:
            active_proxies: Currently active proxy list.
        """
        if not active_proxies:
            return

        active_keys = {
            self._proxy_key(p) for p in active_proxies
        }
        if not active_keys:
            return

        def _filter_dict(
            data: Dict[str, Any],
        ) -> Dict[str, Any]:
            """Keep only entries whose key is active."""
            return {
                k: v for k, v in data.items()
                if k in active_keys
            }

        before_cooldowns = len(self.proxy_cooldowns)
        self.proxy_latency = _filter_dict(self.proxy_latency)
        self.proxy_failures = _filter_dict(self.proxy_failures)
        self.proxy_reputation = _filter_dict(
            self.proxy_reputation,
        )
        self.proxy_soft_signals = _filter_dict(
            self.proxy_soft_signals,
        )
        self.proxy_cooldowns = _filter_dict(
            self.proxy_cooldowns,
        )
        self.dead_proxies = [
            k for k in self.dead_proxies if k in active_keys
        ]

        # If everything is in cooldown, release the earliest
        if (
            active_keys
            and len(self.proxy_cooldowns) >= len(active_keys)
        ):
            oldest_key = min(
                self.proxy_cooldowns.items(),
                key=lambda x: x[1],
            )[0]
            self.proxy_cooldowns.pop(oldest_key, None)
            if oldest_key in self.proxy_failures:
                self.proxy_failures[oldest_key] = 0
            logger.warning(
                "All proxies were in cooldown; "
                "releasing one to avoid empty pool."
            )

        if before_cooldowns != len(self.proxy_cooldowns):
            self._save_health_data()

    def _save_health_data(self) -> None:
        """Persist proxy health data to disk with versioning."""
        try:
            data = {
                "version": self.HEALTH_FILE_VERSION,
                "timestamp": time.time(),
                "proxy_latency": self.proxy_latency,
                "proxy_failures": self.proxy_failures,
                "dead_proxies": self.dead_proxies,
                "proxy_cooldowns": self.proxy_cooldowns,
                "proxy_reputation": self.proxy_reputation,
                "proxy_soft_signals": self.proxy_soft_signals,
                "proxy_host_failures": self.proxy_host_failures,
            }

            safe_json_write(self.health_file, data)

            logger.debug(
                "Saved proxy health data to %s",
                self.health_file,
            )

        except Exception as e:
            logger.warning(
                "Failed to save proxy health data: %s", e,
            )

    # ------------------------------------------------------------------
    # Geolocation
    # ------------------------------------------------------------------

    async def get_proxy_geolocation(
        self, proxy: Proxy,
    ) -> Optional[Tuple[str, str]]:
        """Get geolocation (timezone, locale) for a proxy IP.

        Uses ip-api.com free tier (45 req/min limit).

        Args:
            proxy: Proxy object to geolocate.

        Returns:
            Tuple of (timezone_id, locale) or ``None``
            if lookup fails.  Example:
            ``("America/New_York", "en-US")``.
        """
        try:
            api_url = (
                f"http://ip-api.com/json/{proxy.ip}"
                "?fields=timezone,countryCode"
            )

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url, timeout=timeout,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        timezone_id = data.get("timezone")
                        country_code = data.get(
                            "countryCode", "US",
                        )

                        locale_map = {
                            "US": "en-US",
                            "GB": "en-GB",
                            "CA": "en-CA",
                            "AU": "en-AU",
                            "DE": "de-DE",
                            "FR": "fr-FR",
                            "ES": "es-ES",
                            "IT": "it-IT",
                            "JP": "ja-JP",
                            "CN": "zh-CN",
                            "IN": "en-IN",
                            "BR": "pt-BR",
                            "RU": "ru-RU",
                            "NL": "nl-NL",
                        }

                        locale = locale_map.get(
                            country_code, "en-US",
                        )

                        if timezone_id:
                            logger.debug(
                                "Proxy %s geolocated to "
                                "%s, %s",
                                proxy.ip,
                                timezone_id,
                                locale,
                            )
                            return timezone_id, locale

        except Exception as e:
            logger.warning(
                "Failed to geolocate proxy %s: %s",
                proxy.ip, e,
            )

        return None

    async def get_geolocation_for_proxy(
        self, proxy_string: Optional[str],
    ) -> Optional[Tuple[str, str]]:
        """Resolve geolocation for a proxy string.

        Accepts full proxy URL or ``user:pass@ip:port``
        formats.

        Args:
            proxy_string: Proxy URL or address string.

        Returns:
            Tuple of (timezone_id, locale) or ``None``.
        """
        if not proxy_string:
            return None

        try:
            candidate = proxy_string
            if "://" not in candidate:
                candidate = f"http://{candidate}"
            parsed = urlparse(candidate)
            host = parsed.hostname
            port = parsed.port or 0
            if not host:
                return None
            proxy = Proxy(
                ip=host,
                port=port,
                username=parsed.username or "",
                password=parsed.password or "",
                protocol=parsed.scheme or "http",
            )
            return await self.get_proxy_geolocation(proxy)
        except Exception as e:
            logger.warning(
                "Failed to resolve proxy geolocation "
                "for %s: %s",
                proxy_string, e,
            )
            return None

    # ------------------------------------------------------------------
    # Reputation & soft signals
    # ------------------------------------------------------------------

    def record_soft_signal(
        self,
        proxy_str: str,
        signal_type: str = "unknown",
    ) -> None:
        """Record a soft signal that degrades proxy reputation.

        Args:
            proxy_str: Proxy URL or key string.
            signal_type: Kind of signal (e.g. ``blocked``).
        """
        proxy_key = proxy_str
        if "://" in proxy_key:
            proxy_key = proxy_key.split("://", 1)[1]

        if proxy_key not in self.proxy_soft_signals:
            self.proxy_soft_signals[proxy_key] = {}
        signals = self.proxy_soft_signals[proxy_key]
        signals[signal_type] = signals.get(signal_type, 0) + 1

        # Apply immediate reputation penalty
        current = self.proxy_reputation.get(proxy_key, 100.0)
        penalty = (
            5.0
            if signal_type in {"blocked", "captcha_spike"}
            else 2.5
        )
        self.proxy_reputation[proxy_key] = max(
            0.0, current - penalty,
        )
        self._save_health_data()

    def get_proxy_reputation(self, proxy_str: str) -> float:
        """Compute or return cached reputation score.

        Args:
            proxy_str: Proxy URL or key string.

        Returns:
            Score between 0.0 and 100.0.
        """
        proxy_key = proxy_str
        if "://" in proxy_key:
            proxy_key = proxy_key.split("://", 1)[1]

        base = self.proxy_reputation.get(proxy_key, 100.0)
        # Latency penalty
        latencies = self.proxy_latency.get(proxy_key, [])
        if latencies:
            avg = sum(latencies) / len(latencies)
            base -= min(avg / 100.0, 20.0)
        # Failure penalty
        failures = self.proxy_failures.get(proxy_key, 0)
        base -= min(failures * 5.0, 30.0)
        # Soft signal penalty
        signals = self.proxy_soft_signals.get(proxy_key, {})
        signal_penalty = sum(signals.values()) * 1.5
        base -= min(signal_penalty, 30.0)

        score = max(0.0, min(base, 100.0))
        self.proxy_reputation[proxy_key] = score
        return score

    # ------------------------------------------------------------------
    # Latency & health monitoring
    # ------------------------------------------------------------------

    async def measure_proxy_latency(
        self, proxy: Proxy,
    ) -> Optional[float]:
        """Measure the latency of a proxy in milliseconds.

        Args:
            proxy: The proxy to measure.

        Returns:
            Latency in milliseconds, or ``None`` if failed.
        """
        proxy_url = proxy.to_string()
        proxy_key = self._proxy_key(proxy)

        try:
            timeout = aiohttp.ClientTimeout(
                total=self.VALIDATION_TIMEOUT_SECONDS,
            )
            start_time = time.time()

            async with aiohttp.ClientSession(
                timeout=timeout,
            ) as session:
                async with session.get(
                    self.VALIDATION_TEST_URL,
                    proxy=proxy_url,
                ) as resp:
                    if resp.status == 200:
                        latency_ms = (
                            (time.time() - start_time) * 1000
                        )

                        # Record latency
                        if proxy_key not in self.proxy_latency:
                            self.proxy_latency[proxy_key] = []
                        self.proxy_latency[proxy_key].append(
                            latency_ms,
                        )

                        # Keep only last N measurements
                        hist = self.proxy_latency[proxy_key]
                        if len(hist) > self.LATENCY_HISTORY_MAX:
                            self.proxy_latency[proxy_key] = (
                                hist[-self.LATENCY_HISTORY_MAX:]
                            )

                        # Reset failure count on success
                        self.proxy_failures[proxy_key] = 0

                        # Save health data after update
                        self._save_health_data()

                        masked = self._mask_proxy_key(
                            proxy_key,
                        )
                        logger.debug(
                            "[LATENCY] Proxy %s: %.0fms",
                            masked, latency_ms,
                        )
                        return latency_ms
                    self.record_failure(proxy_url)
                    return None

        except asyncio.TimeoutError:
            self.record_failure(proxy_url)
            logger.warning(
                "[TIMEOUT] Proxy %s timed out "
                "during latency check",
                self._mask_proxy_key(proxy_key),
            )
            return None
        except Exception as e:
            self.record_failure(proxy_url)
            logger.warning(
                "[ERROR] Proxy %s latency check failed: %s",
                self._mask_proxy_key(proxy_key), e,
            )
            return None

    def record_failure(
        self,
        proxy_str: str,
        detected: bool = False,
        status_code: int = 0,
    ) -> None:
        """Record a proxy failure with conservative cooldowns.

        Handles session-based proxies by only cooling down the
        specific session, unless a true IP block is confirmed.

        Args:
            proxy_str: Proxy URL or key string.
            detected: Whether the proxy was detected/blocked.
            status_code: HTTP status code (0 for connection
                errors).
        """
        proxy_key = proxy_str
        if "://" in proxy_key:
            proxy_key = proxy_key.split("://", 1)[1]
        host_port = self._proxy_host_port_from_str(proxy_str)

        self.proxy_failures[proxy_key] = (
            self.proxy_failures.get(proxy_key, 0) + 1
        )

        # Reputation penalty for hard failures
        rep = self.proxy_reputation.get(proxy_key, 100.0)
        rep_penalty = (
            15.0 if detected or status_code == 403 else 5.0
        )
        self.proxy_reputation[proxy_key] = max(
            0.0, rep - rep_penalty,
        )

        now = time.time()
        if detected or status_code == 403:
            # 403 or detection: 1 hour cooldown for session
            self.proxy_cooldowns[proxy_key] = (
                now + self.DETECTION_COOLDOWN
            )
            masked = self._mask_proxy_key(proxy_key)
            logger.error(
                "[COOLDOWN] Proxy session %s "
                "detected/403. Cooling down for 1h.",
                masked,
            )

            if host_port:
                self.proxy_host_failures[host_port] = (
                    self.proxy_host_failures.get(
                        host_port, 0,
                    ) + 1
                )
                host_fails = self.proxy_host_failures[
                    host_port
                ]
                if host_fails >= self.HOST_DETECTION_THRESHOLD:
                    self.proxy_cooldowns[host_port] = (
                        now + self.DETECTION_COOLDOWN
                    )
                    logger.warning(
                        "[COOLDOWN] Proxy host %s flagged "
                        "after %d detections.",
                        host_port, host_fails,
                    )

        elif (
            self.proxy_failures[proxy_key]
            >= self.DEAD_PROXY_FAILURE_COUNT
        ):
            # Consistent connection failure: 5 min cooldown
            self.proxy_cooldowns[proxy_key] = (
                now + self.FAILURE_COOLDOWN
            )
            if proxy_key not in self.dead_proxies:
                self.dead_proxies.append(proxy_key)
            fail_count = self.proxy_failures[proxy_key]
            masked = self._mask_proxy_key(proxy_key)
            logger.warning(
                "[COOLDOWN] Proxy session %s failed "
                "%d times. Cooling down for 5m.",
                masked, fail_count,
            )

        # Persist health data after failure
        self._save_health_data()

        # Trigger cleanup
        self.remove_dead_proxies()

        # Check pool health - fetch only if critically low
        active_count = len(self.proxies)
        if (
            active_count < 3
            and self.settings.use_2captcha_proxies
        ):
            logger.warning(
                "Proxy pool critically low (%d). "
                "Triggering replenishment...",
                active_count,
            )
            asyncio.create_task(
                self.fetch_proxies_from_api(20),
            )

    def get_proxy_stats(
        self, proxy: Proxy,
    ) -> Dict[str, Any]:
        """Get statistics for a specific proxy.

        Args:
            proxy: Proxy to query.

        Returns:
            Dict with ``avg_latency``, ``min_latency``,
            ``max_latency``, ``measurement_count``,
            ``is_dead``, and ``reputation_score``.
        """
        proxy_key = self._proxy_key(proxy)
        latencies = self.proxy_latency.get(proxy_key, [])
        is_dead = proxy_key in self.dead_proxies
        rep = self.get_proxy_reputation(proxy_key)

        if not latencies:
            return {
                "avg_latency": None,
                "min_latency": None,
                "max_latency": None,
                "measurement_count": 0,
                "is_dead": is_dead,
                "reputation_score": rep,
            }

        return {
            "avg_latency": sum(latencies) / len(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "measurement_count": len(latencies),
            "is_dead": is_dead,
            "reputation_score": rep,
        }

    async def health_check_all_proxies(
        self,
    ) -> Dict[str, Any]:
        """Run health check on all assigned proxies.

        Returns:
            Summary dict with ``total``, ``healthy``,
            ``dead``, and ``avg_latency_ms``.
        """
        if not self.proxies:
            return {"total": 0, "healthy": 0, "dead": 0}

        logger.info(
            "[HEALTH] Running health check on %d proxies...",
            len(self.proxies),
        )

        semaphore = asyncio.Semaphore(10)

        async def check_with_semaphore(
            proxy: Proxy,
        ) -> Optional[float]:
            """Measure latency under semaphore limit."""
            async with semaphore:
                return await self.measure_proxy_latency(proxy)

        results = await asyncio.gather(
            *[check_with_semaphore(p) for p in self.proxies],
        )

        healthy = sum(1 for r in results if r is not None)
        dead = len(self.dead_proxies)

        valid = [r for r in results if r is not None]
        avg_latency = (
            sum(valid) / len(valid) if valid else 0
        )

        summary: Dict[str, Any] = {
            "total": len(self.proxies),
            "healthy": healthy,
            "dead": dead,
            "avg_latency_ms": avg_latency,
        }

        logger.info(
            "[HEALTH] Check complete: %d/%d healthy, "
            "%d dead",
            healthy, len(self.proxies), dead,
        )
        return summary

    # ------------------------------------------------------------------
    # Dead proxy removal & pool maintenance
    # ------------------------------------------------------------------

    def remove_dead_proxies(self) -> int:
        """Remove dead / slow proxies from the active pool.

        Refreshes ``self.proxies`` based on ``self.all_proxies``
        minus cooldowns.

        Returns:
            Number of proxies removed.
        """
        before_count = len(self.proxies)
        now = time.time()

        # 1. Clean up expired cooldowns
        expired = [
            k for k, t in self.proxy_cooldowns.items()
            if t < now
        ]
        for k in expired:
            del self.proxy_cooldowns[k]
            if k in self.proxy_failures:
                self.proxy_failures[k] = 0
            logger.debug(
                "[RESTORE] Proxy %s finished cooldown.",
                self._mask_proxy_key(k),
            )

        # 2. Filter active proxies (exclude cooling-down)
        current_cooldowns = set(self.proxy_cooldowns.keys())
        dead_set = set(self.dead_proxies)

        active_proxies: List[Proxy] = []
        rep_enabled = getattr(
            self.settings, "proxy_reputation_enabled", True,
        )
        min_rep = getattr(
            self.settings, "proxy_reputation_min_score", 20.0,
        )
        for p in self.all_proxies:
            key = self._proxy_key(p)
            host_port = self._proxy_host_port(p)
            if key in current_cooldowns:
                continue
            if host_port and host_port in current_cooldowns:
                continue
            if key in dead_set:
                continue
            if host_port and host_port in dead_set:
                continue
            if rep_enabled:
                score = self.get_proxy_reputation(
                    p.to_string(),
                )
                if score < min_rep:
                    self.proxy_cooldowns[key] = (
                        now + self.FAILURE_COOLDOWN
                    )
                    continue
            active_proxies.append(p)

        # 3. Filter out slow proxies (latency check)
        final_proxies: List[Proxy] = []
        slow_proxies_keys: List[str] = []

        for p in active_proxies:
            key = self._proxy_key(p)
            latencies = self.proxy_latency.get(key, [])
            avg = (
                sum(latencies) / len(latencies)
                if latencies else 0
            )
            if (
                len(latencies) >= 3
                and avg > self.DEAD_PROXY_THRESHOLD_MS
            ):
                slow_proxies_keys.append(key)
                self.proxy_cooldowns[key] = (
                    now + self.FAILURE_COOLDOWN
                )
            else:
                final_proxies.append(p)

        if slow_proxies_keys:
            masked = [
                self._mask_proxy_key(k)
                for k in slow_proxies_keys[:3]
            ]
            logger.warning(
                "Removing %d slow proxies: %s...",
                len(slow_proxies_keys), masked,
            )

        # If empty, salvage best proxy to avoid hard stall
        if not final_proxies and self.all_proxies:
            candidates = list(self.all_proxies)

            def candidate_score(
                proxy: Proxy,
            ) -> Tuple[float, float]:
                """Score for salvage sorting (lower=better)."""
                key = self._proxy_key(proxy)
                cooldown_until = self.proxy_cooldowns.get(
                    key, 0,
                )
                rep = (
                    self.get_proxy_reputation(
                        proxy.to_string(),
                    )
                    if rep_enabled
                    else 100.0
                )
                return (cooldown_until, -rep)

            candidates.sort(key=candidate_score)
            best = candidates[0]
            best_key = self._proxy_key(best)
            if best_key in self.proxy_cooldowns:
                logger.warning(
                    "All proxies are in cooldown. "
                    "Temporarily reusing %s to avoid "
                    "zero-proxy stall.",
                    self._mask_proxy_key(best_key),
                )
                self.proxy_cooldowns.pop(best_key, None)
            final_proxies = [best]

        # Update the active list
        self.proxies = final_proxies
        slow_set = set(slow_proxies_keys)
        self.validated_proxies = [
            p for p in self.validated_proxies
            if (
                self._proxy_key(p) not in current_cooldowns
                and self._proxy_key(p) not in slow_set
            )
        ]

        removed = before_count - len(self.proxies)
        if removed > 0:
            logger.info(
                "[CLEANUP] Removed %d proxies (Dead/Slow). "
                "Active: %d / Total: %d",
                removed,
                len(self.proxies),
                len(self.all_proxies),
            )

        # If we removed everything, salvage at least one
        if not self.proxies and self.all_proxies:
            logger.warning(
                "All proxies in cooldown or slow!",
            )
            if self.proxy_cooldowns:
                oldest_key = min(
                    self.proxy_cooldowns.items(),
                    key=lambda x: x[1],
                )[0]
                self.proxy_cooldowns.pop(oldest_key, None)
                if oldest_key in self.proxy_failures:
                    self.proxy_failures[oldest_key] = 0
                restored = [
                    p for p in self.all_proxies
                    if self._proxy_key(p) == oldest_key
                ]
                if restored:
                    self.proxies = restored
                    logger.info(
                        "[RESTORE] Re-enabled one proxy "
                        "to avoid empty pool: %s",
                        self._mask_proxy_key(oldest_key),
                    )
                    self._save_health_data()

        return removed

    # ------------------------------------------------------------------
    # Proxy validation
    # ------------------------------------------------------------------

    async def validate_proxy(self, proxy: Proxy) -> bool:
        """Test proxy connectivity before use.

        Args:
            proxy: The proxy to validate.

        Returns:
            ``True`` if proxy is working, ``False`` otherwise.
        """
        proxy_url = proxy.to_string()
        try:
            timeout = aiohttp.ClientTimeout(
                total=self.VALIDATION_TIMEOUT_SECONDS,
            )
            async with aiohttp.ClientSession(
                timeout=timeout,
            ) as session:
                async with session.get(
                    self.VALIDATION_TEST_URL,
                    proxy=proxy_url,
                ) as resp:
                    if resp.status == 200:
                        logger.debug(
                            "[OK] Proxy %s:%s validated "
                            "(status 200)",
                            proxy.ip, proxy.port,
                        )
                        return True
                    logger.warning(
                        "[WARN] Proxy %s:%s returned "
                        "status %s",
                        proxy.ip, proxy.port, resp.status,
                    )
                    return False
        except asyncio.TimeoutError:
            masked = self._mask_proxy_key(
                self._proxy_key(proxy),
            )
            logger.warning(
                "[TIMEOUT] Proxy %s timed out "
                "during validation",
                masked,
            )
            return False
        except Exception as e:
            masked = self._mask_proxy_key(
                self._proxy_key(proxy),
            )
            logger.warning(
                "[ERROR] Proxy %s validation failed: %s",
                masked, e,
            )
            return False

    async def validate_all_proxies(self) -> int:
        """Validate all fetched proxies concurrently.

        Returns:
            Number of valid proxies.
        """
        if not self.proxies:
            return 0

        logger.info(
            "[VALIDATE] Validating %d proxies...",
            len(self.proxies),
        )

        semaphore = asyncio.Semaphore(10)

        async def validate_with_semaphore(
            proxy: Proxy,
        ) -> Optional[Proxy]:
            """Validate a single proxy under semaphore."""
            async with semaphore:
                if await self.validate_proxy(proxy):
                    return proxy
                return None

        results = await asyncio.gather(
            *[validate_with_semaphore(p) for p in self.proxies],
        )
        self.validated_proxies = [
            p for p in results if p is not None
        ]

        valid_count = len(self.validated_proxies)
        logger.info(
            "[OK] %d/%d proxies passed validation",
            valid_count, len(self.proxies),
        )
        return valid_count

    # ------------------------------------------------------------------
    # Proxy file I/O & parsing
    # ------------------------------------------------------------------

    def load_proxies_from_file(self) -> int:
        """Load proxies from the configured proxy file(s).

        Supports 2Captcha residential proxies, Azure VM proxies,
        and DigitalOcean Droplet proxies.  Can load from multiple
        sources if enabled.

        Expected formats per line::

            http://user:pass@host:port
            http://host:port
            user:pass@host:port

        Returns:
            Total number of proxies loaded.
        """
        use_do = getattr(
            self.settings, "use_digitalocean_proxies", False,
        )
        use_azure = getattr(
            self.settings, "use_azure_proxies", False,
        )

        proxy_files: List[Tuple[str, str]] = []

        if use_do:
            proxy_files.append((
                "DIGITALOCEAN",
                self.settings.digitalocean_proxies_file,
            ))
        if use_azure:
            proxy_files.append((
                "AZURE",
                self.settings.azure_proxies_file,
            ))
        if not proxy_files:  # Fallback to 2Captcha
            proxy_files.append((
                "2CAPTCHA",
                self.settings.residential_proxies_file,
            ))

        new_proxies: List[Proxy] = []
        total_count = 0

        for source_name, file_path in proxy_files:
            if not os.path.exists(file_path):
                logger.warning(
                    "[%s] Proxy file not found: %s",
                    source_name, file_path,
                )
                continue

            logger.info(
                "[%s] Loading proxies from %s...",
                source_name, file_path,
            )

            try:
                with open(file_path, "r") as f:
                    lines = f.readlines()

                source_count = 0
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    proxy = self._parse_proxy_string(line)
                    if proxy:
                        new_proxies.append(proxy)
                        source_count += 1

                if source_count > 0:
                    logger.info(
                        "[%s] Loaded %d proxies",
                        source_name, source_count,
                    )
                    total_count += source_count

            except Exception as e:
                logger.error(
                    "[%s] Error loading proxies: %s",
                    source_name, e,
                )

        if total_count == 0:
            logger.warning(
                "[WARN] No proxies loaded from any source",
            )
            return 0

        self.all_proxies = new_proxies
        self.proxies = list(new_proxies)
        self._prune_health_data_for_active_proxies(new_proxies)
        logger.info(
            "[OK] Total proxies loaded: %d", total_count,
        )
        return total_count

    def _parse_proxy_string(
        self, proxy_str: str,
    ) -> Optional[Proxy]:
        """Parse a proxy string into a Proxy object.

        Args:
            proxy_str: Raw proxy string in any supported
                format.

        Returns:
            Parsed ``Proxy`` or ``None`` on failure.
        """
        try:
            if "://" in proxy_str:
                protocol, rest = proxy_str.split("://", 1)
            else:
                protocol = "http"
                rest = proxy_str

            username = ""
            password = ""
            if "@" in rest:
                auth, endpoint = rest.split("@", 1)
                if ":" in auth:
                    username, password = auth.split(":", 1)
            else:
                endpoint = rest

            if ":" not in endpoint:
                logger.warning(
                    "Invalid proxy format (no port): %s",
                    proxy_str,
                )
                return None

            ip, port = endpoint.split(":", 1)

            return Proxy(
                ip=ip,
                port=int(port),
                username=username,
                password=password,
                protocol=protocol,
            )
        except Exception as e:
            logger.error(
                "Failed to parse proxy string '%s': %s",
                proxy_str, e,
            )
            return None

    # ------------------------------------------------------------------
    # Session rotation
    # ------------------------------------------------------------------

    def rotate_session_id(self, base_username: str) -> str:
        """Generate a fresh 2Captcha session ID.

        Args:
            base_username: The base username without session
                parameters.

        Returns:
            New username with session parameter appended:
            ``user-session-ID``.
        """
        pure_username = base_username
        if "-session-" in base_username:
            pure_username = base_username.split(
                "-session-",
            )[0]

        session_id = "".join(
            random.choices(
                string.ascii_lowercase + string.digits, k=8,
            ),
        )
        return f"{pure_username}-session-{session_id}"

    # ------------------------------------------------------------------
    # Proxy fetching / provisioning
    # ------------------------------------------------------------------

    async def generate_whitelist_proxies(
        self,
        country: str = "all",
        count: int = 20,
    ) -> bool:
        """Whitelist VM IP with 2Captcha and generate proxies.

        Args:
            country: Country filter (default ``all``).
            count: Number of connections to request.

        Returns:
            ``True`` if whitelisting succeeded.
        """
        if not self.api_key:
            logger.error("2Captcha API key missing.")
            return False

        current_ip = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api64.ipify.org?format=json",
                ) as resp:
                    if resp.status == 200:
                        current_ip = (
                            (await resp.json()).get("ip")
                        )
        except Exception as e:
            logger.warning(
                "Could not detect current IP: %s", e,
            )

        params_to_try = [
            {
                "key": self.api_key,
                "country": country,
                "protocol": "http",
                "connection_count": count,
                "ip": current_ip,
            },
            {
                "key": self.api_key,
                "country": country,
                "protocol": "http",
                "connection_count": count,
                "ip_address": current_ip,
            },
            {
                "key": self.api_key,
                "country": country,
                "protocol": "http",
                "connection_count": count,
                "ips": current_ip,
            },
        ]

        url = (
            "https://api.2captcha.com"
            "/proxy/generate_white_list_connections"
        )
        async with aiohttp.ClientSession() as session:
            for params in params_to_try:
                has_ip = (
                    params.get("ip")
                    or params.get("ip_address")
                    or params.get("ips")
                )
                if not has_ip:
                    continue

                logger.info(
                    "[WHITELIST] Attempting whitelist "
                    "with params: %s",
                    params,
                )
                try:
                    async with session.get(
                        url, params=params,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("status") == "OK":
                                proxy_list = data.get(
                                    "data", [],
                                )
                                logger.info(
                                    "[OK] Whitelisted and "
                                    "received %d proxies.",
                                    len(proxy_list),
                                )

                                new_proxies: List[Proxy] = []
                                for p_str in proxy_list:
                                    proxy = (
                                        self
                                        ._parse_proxy_string(
                                            f"http://{p_str}",
                                        )
                                    )
                                    if proxy:
                                        new_proxies.append(
                                            proxy,
                                        )

                                if new_proxies:
                                    self.all_proxies = (
                                        new_proxies
                                    )
                                    self.proxies = list(
                                        new_proxies,
                                    )
                                    res_file = (
                                        self.settings
                                        .residential_proxies_file
                                    )
                                    abs_path = (
                                        os.path.abspath(
                                            res_file,
                                        )
                                    )
                                    with open(
                                        abs_path, "w",
                                    ) as f:
                                        f.write(
                                            "# whitelisted"
                                            "-proxies\n",
                                        )
                                        f.write("\n".join(
                                            p.to_string()
                                            for p
                                            in new_proxies
                                        ))
                                    return True
                        logger.warning(
                            "[WHITELIST] Param set "
                            "failed: %s",
                            params,
                        )
                except Exception as e:
                    logger.error(
                        "[ERROR] Whitelist request "
                        "failed: %s",
                        e,
                    )

        return False

    async def fetch_proxy_config_from_2captcha(
        self,
    ) -> Optional[Proxy]:
        """Fetch residential proxy config from 2Captcha API.

        Retrieves the proxy gateway details (host, port,
        credentials) from the user's 2Captcha account.

        Returns:
            ``Proxy`` object if successful, ``None`` otherwise.
        """
        if not self.api_key:
            logger.error("2Captcha API key missing.")
            return None

        endpoints = [
            (
                "https://2captcha.com/res.php",
                {
                    "key": self.api_key,
                    "action": "getproxies",
                    "json": 1,
                },
            ),
            (
                "https://api.2captcha.com/proxy/info",
                {"key": self.api_key},
            ),
        ]

        logger.info(
            "[2CAPTCHA] Fetching residential proxy "
            "configuration from API...",
        )

        async with aiohttp.ClientSession() as session:
            for ep_url, params in endpoints:
                try:
                    timeout = aiohttp.ClientTimeout(total=15)
                    async with session.get(
                        ep_url,
                        params=params,
                        timeout=timeout,
                    ) as resp:
                        if resp.status == 200:
                            try:
                                data = await resp.json()
                                logger.debug(
                                    "[2CAPTCHA] Response "
                                    "from %s: %s",
                                    ep_url, data,
                                )

                                if not isinstance(data, dict):
                                    continue
                                status = data.get("status")
                                if status not in (1, "OK"):
                                    continue

                                proxy_data = (
                                    data.get("request")
                                    or data.get("data")
                                    or data.get("proxies")
                                )
                                if not proxy_data:
                                    continue

                                if (
                                    isinstance(
                                        proxy_data, list,
                                    )
                                    and proxy_data
                                ):
                                    proxy_str = proxy_data[0]
                                else:
                                    proxy_str = proxy_data

                                if isinstance(proxy_str, str):
                                    proxy_url = (
                                        f"http://{proxy_str}"
                                        if not proxy_str
                                        .startswith("http")
                                        else proxy_str
                                    )
                                    proxy = (
                                        self
                                        ._parse_proxy_string(
                                            proxy_url,
                                        )
                                    )
                                    if proxy:
                                        logger.info(
                                            "[2CAPTCHA] "
                                            "Fetched proxy "
                                            "config: "
                                            "%s:%s",
                                            proxy.ip,
                                            proxy.port,
                                        )
                                        return proxy
                            except (
                                json.JSONDecodeError,
                                ValueError,
                            ):
                                body = await resp.text()
                                logger.debug(
                                    "[2CAPTCHA] Non-JSON "
                                    "response from %s: %s",
                                    ep_url, body,
                                )
                                continue
                        else:
                            logger.debug(
                                "[2CAPTCHA] Endpoint %s "
                                "returned status %s",
                                ep_url, resp.status,
                            )
                except Exception as e:
                    logger.debug(
                        "[2CAPTCHA] Error fetching "
                        "from %s: %s",
                        ep_url, e,
                    )
                    continue

        logger.warning(
            "[2CAPTCHA] Could not fetch proxy configuration "
            "from API. You may need to:",
        )
        logger.warning(
            "  1. Purchase residential proxy traffic at "
            "https://2captcha.com/proxy/residential-proxies",
        )
        logger.warning(
            "  2. Manually add your proxy credentials "
            "to config/proxies.txt",
        )
        logger.warning(
            "  Format: username:password"
            "@proxy.2captcha.com:port",
        )
        return None

    async def fetch_proxies_from_api(
        self, quantity: int = 10,
    ) -> int:
        """Generate residential proxies via session rotation.

        Since 2Captcha (and similar providers) use a single
        gateway with session-based rotation, we generate unique
        sessions from the base configured proxy.

        If no base proxy exists, attempts to fetch configuration
        from 2Captcha API first.

        Args:
            quantity: Number of proxies to generate.

        Returns:
            Number of proxies generated.
        """
        if self.proxy_provider == "zyte":
            return self._build_zyte_proxies(quantity)

        if self.proxy_provider != "2captcha":
            return await self.fetch_proxies_from_provider(
                quantity,
            )

        if not self.api_key:
            logger.error("2Captcha API key missing.")
            return 0

        # Try to load from file first if empty
        if not self.proxies:
            self.load_proxies_from_file()

        # If still no proxies, try to fetch from API
        if not self.proxies:
            logger.info(
                "[2CAPTCHA] No base proxy found in file. "
                "Attempting to fetch from API...",
            )
            base_proxy = (
                await self.fetch_proxy_config_from_2captcha()
            )
            if base_proxy:
                self.proxies = [base_proxy]
                self.all_proxies = [base_proxy]
            else:
                logger.error(
                    "Cannot generate proxies: no base proxy "
                    "in proxies.txt and API fetch failed.",
                )
                return 0

        # Use the first proxy as a template
        template_proxy = self.proxies[0]

        if (
            not template_proxy.username
            or not template_proxy.password
        ):
            logger.error(
                "Cannot generate proxies: base proxy "
                "is missing authentication details.",
            )
            return 0

        logger.info(
            "Generating %d unique proxies using "
            "template from %s:%s...",
            quantity,
            template_proxy.ip,
            template_proxy.port,
        )

        # Extract base username (remove existing session)
        base_username = template_proxy.username
        if "-session-" in base_username:
            base_username = base_username.split(
                "-session-",
            )[0]

        new_proxies: List[Proxy] = []
        lines_to_write: List[str] = []
        lines_to_write.append(
            "# Auto-generated from 2Captcha Residential "
            "Proxy with Session Rotation",
        )
        lines_to_write.append(
            "# Base proxy configuration:",
        )
        lines_to_write.append(template_proxy.to_string())
        new_proxies.append(template_proxy)

        lines_to_write.append("# Session-rotated proxies:")
        for _ in range(quantity):
            new_username = self.rotate_session_id(
                base_username,
            )
            proxy_str = (
                f"http://{new_username}:"
                f"{template_proxy.password}"
                f"@{template_proxy.ip}:"
                f"{template_proxy.port}"
            )

            lines_to_write.append(proxy_str)

            new_proxy = self._parse_proxy_string(proxy_str)
            if new_proxy:
                new_proxies.append(new_proxy)

        if len(new_proxies) > 1:
            file_path = self.settings.residential_proxies_file
            try:
                abs_path = os.path.abspath(file_path)
                with open(abs_path, "w") as f:
                    f.write("\n".join(lines_to_write))

                self.all_proxies = new_proxies
                self.proxies = list(new_proxies)
                self._prune_health_data_for_active_proxies(
                    new_proxies,
                )
                logger.info(
                    "Generated and saved %d unique "
                    "residential proxies to %s",
                    len(new_proxies), abs_path,
                )
                return len(new_proxies)
            except Exception as e:
                logger.error(
                    "Failed to save generated proxies: %s", e,
                )
                return 0

        return 0

    async def fetch_proxies_from_provider(
        self, quantity: int = 20,
    ) -> int:
        """Fetch proxies from non-2Captcha providers.

        Currently supports Webshare proxy list API.

        Args:
            quantity: Number of proxies to request.

        Returns:
            Number of proxies added.
        """
        if self.proxy_provider != "webshare":
            logger.warning(
                "Proxy provider '%s' not supported "
                "for auto-provisioning.",
                self.proxy_provider,
            )
            return 0

        if not self.settings.webshare_api_key:
            logger.warning(
                "Webshare API key missing; "
                "cannot auto-provision proxies.",
            )
            return 0

        page_size = max(
            1,
            min(
                quantity,
                self.settings.webshare_page_size,
                100,
            ),
        )
        url = (
            "https://proxy.webshare.io/api/v2/proxy/list/"
            f"?page=1&page_size={page_size}"
        )
        headers = {
            "Authorization": (
                f"Token {self.settings.webshare_api_key}"
            ),
        }

        data = None
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Webshare proxy list returned "
                            "status %s",
                            resp.status,
                        )
                        return 0

                    data = await resp.json()
        except Exception as e:
            logger.warning(
                "Failed to fetch Webshare proxies: %s", e,
            )
            return 0

        results = (
            data.get("results", [])
            if isinstance(data, dict)
            else []
        )
        if not results:
            logger.warning(
                "Webshare proxy list returned no proxies.",
            )
            return 0

        new_proxies: List[Proxy] = []
        lines_to_write = [
            "# Auto-generated from Webshare API",
        ]
        for entry in results:
            host = entry.get("proxy_address")
            port = entry.get("port")
            username = entry.get("username") or ""
            password = entry.get("password") or ""
            if not host or not port:
                continue
            proxy = Proxy(
                ip=host,
                port=int(port),
                username=username,
                password=password,
            )
            new_proxies.append(proxy)
            lines_to_write.append(proxy.to_string())

        if not new_proxies:
            logger.warning(
                "Webshare proxy list did not yield "
                "valid proxies.",
            )
            return 0

        file_path = self.settings.residential_proxies_file
        try:
            abs_path = os.path.abspath(file_path)
            with open(abs_path, "w") as f:
                f.write("\n".join(lines_to_write))
            self.all_proxies = list(new_proxies)
            self.proxies = list(new_proxies)
            logger.info(
                "Loaded %s proxies from Webshare into %s",
                len(new_proxies), abs_path,
            )
            return len(new_proxies)
        except Exception as e:
            logger.error(
                "Failed to save Webshare proxies: %s", e,
            )
            return 0

    async def fetch_proxies(self, count: int = 100) -> bool:
        """Wrapper for ``fetch_proxies_from_api``.

        Maintains backward compatibility.

        Args:
            count: Number of proxies to fetch.

        Returns:
            ``True`` if any proxies were fetched.
        """
        c = await self.fetch_proxies_from_api(count)
        return c > 0

    async def fetch_2captcha_proxies(
        self,
        count: int = 100,
        validate: bool = True,
        max_latency_ms: float = 3000,
    ) -> int:
        """Fetch and populate residential proxies from 2Captcha.

        This method:
        1. Fetches proxy config from 2Captcha API (if needed).
        2. Generates session-rotated proxies.
        3. Validates each proxy before adding to pool.
        4. Filters proxies by latency.
        5. Saves to ``config/proxies.txt``.

        Args:
            count: Number of proxies to generate.
            validate: Whether to validate before adding.
            max_latency_ms: Maximum acceptable latency in ms.

        Returns:
            Number of valid proxies added to pool.

        Example::

            pm = ProxyManager(settings)
            n = await pm.fetch_2captcha_proxies(count=50)
            print(f"Added {n} proxies to pool")
        """
        if self.proxy_provider != "2captcha":
            logger.warning(
                "fetch_2captcha_proxies() only works "
                "with proxy_provider='2captcha'",
            )
            return 0

        if not self.api_key:
            logger.error(
                "Cannot fetch 2Captcha proxies: "
                "TWOCAPTCHA_API_KEY not set",
            )
            return 0

        logger.info(
            "[2CAPTCHA] Fetching %d residential proxies...",
            count,
        )

        # Step 1: Fetch proxy config if we lack a base proxy
        if not self.proxies:
            logger.info(
                "[2CAPTCHA] No base proxy found. "
                "Attempting to fetch from API...",
            )
            base_proxy = (
                await self.fetch_proxy_config_from_2captcha()
            )

            if base_proxy:
                self.proxies = [base_proxy]
                self.all_proxies = [base_proxy]
                logger.info(
                    "[2CAPTCHA] Got base proxy: %s:%s",
                    base_proxy.ip, base_proxy.port,
                )
            else:
                loaded = self.load_proxies_from_file()
                if loaded == 0:
                    logger.error(
                        "[2CAPTCHA] Failed to fetch proxy "
                        "config from API and no proxies "
                        "in file.",
                    )
                    logger.error(
                        "Please ensure you have:",
                    )
                    logger.error(
                        "  1. Purchased residential proxy "
                        "traffic at "
                        "https://2captcha.com/proxy/"
                        "residential-proxies",
                    )
                    logger.error(
                        "  2. Or manually add your proxy "
                        "to config/proxies.txt",
                    )
                    logger.error(
                        "     Format: username:password"
                        "@proxy-gateway.2captcha.com:port",
                    )
                    return 0

        # Step 2: Generate session-rotated proxies
        logger.info(
            "[2CAPTCHA] Generating %d session-rotated "
            "proxies...",
            count,
        )
        generated = await self.fetch_proxies_from_api(
            quantity=count,
        )

        if generated == 0:
            logger.error(
                "[2CAPTCHA] Failed to generate proxies",
            )
            return 0

        logger.info(
            "[2CAPTCHA] Generated %d proxies", generated,
        )

        # Step 3: Validate proxies if requested
        valid_count = generated
        if validate:
            logger.info(
                "[2CAPTCHA] Validating proxies "
                "(this may take a moment)...",
            )
            valid_count = await self.validate_all_proxies()
            logger.info(
                "[2CAPTCHA] Validation complete: "
                "%d/%d proxies are healthy",
                valid_count, generated,
            )

        # Step 4: Filter by latency
        if max_latency_ms > 0 and self.validated_proxies:
            fast_proxies: List[Proxy] = []
            for proxy in self.validated_proxies:
                proxy_key = self._proxy_key(proxy)
                latencies = self.proxy_latency.get(
                    proxy_key, [],
                )
                if latencies:
                    avg = sum(latencies) / len(latencies)
                    if avg <= max_latency_ms:
                        fast_proxies.append(proxy)

            if fast_proxies:
                logger.info(
                    "[2CAPTCHA] Filtered to %d proxies "
                    "with <%sms latency",
                    len(fast_proxies), max_latency_ms,
                )
                valid_count = len(fast_proxies)
            else:
                logger.warning(
                    "[2CAPTCHA] No proxies met latency "
                    "requirement (<%sms)",
                    max_latency_ms,
                )

        # Step 5: Report statistics
        health_stats = await self.health_check_all_proxies()
        logger.info("[2CAPTCHA] === Proxy Pool Summary ===")
        logger.info(
            "[2CAPTCHA]   Total proxies: %d",
            health_stats.get("total", 0),
        )
        logger.info(
            "[2CAPTCHA]   Healthy: %d",
            health_stats.get("healthy", 0),
        )
        logger.info(
            "[2CAPTCHA]   Dead: %d",
            health_stats.get("dead", 0),
        )
        avg_latency = health_stats.get("avg_latency_ms") or 0
        logger.info(
            "[2CAPTCHA]   Avg latency: %.0fms", avg_latency,
        )
        res_file = self.settings.residential_proxies_file
        logger.info(
            "[2CAPTCHA]   File: %s",
            os.path.abspath(res_file),
        )
        logger.info("[2CAPTCHA] ===========================")

        return valid_count

    # ------------------------------------------------------------------
    # Proxy assignment
    # ------------------------------------------------------------------

    def assign_proxies(
        self, profiles: List[AccountProfile],
    ) -> None:
        """Assign proxies to profiles 1:1 (sticky strategy).

        Overwrites each ``profile.proxy`` field.  Filters out
        dead and cooldown proxies during assignment.

        Args:
            profiles: Account profiles to assign proxies to.
        """
        if not self.proxies:
            logger.warning(
                "No proxies loaded for provider '%s'. "
                "Creating fallback assignments from config.",
                self.proxy_provider,
            )
            return

        # Filter out dead / cooldown proxies
        now = time.time()
        healthy_proxies: List[Proxy] = []
        for p in self.proxies:
            proxy_key = self._proxy_key(p)
            host_port = self._proxy_host_port(p)

            # Skip dead
            if proxy_key in self.dead_proxies:
                logger.debug(
                    "Skipping dead proxy: %s",
                    self._mask_proxy_key(proxy_key),
                )
                continue
            if host_port and host_port in self.dead_proxies:
                logger.debug(
                    "Skipping dead proxy: %s",
                    self._mask_proxy_key(proxy_key),
                )
                continue

            # Skip cooldown
            cd = self.proxy_cooldowns.get(proxy_key, 0)
            if cd > now:
                logger.debug(
                    "Skipping proxy in cooldown: %s",
                    self._mask_proxy_key(proxy_key),
                )
                continue
            if host_port:
                host_cd = self.proxy_cooldowns.get(
                    host_port, 0,
                )
                if host_cd > now:
                    logger.debug(
                        "Skipping proxy (host cooldown): %s",
                        self._mask_proxy_key(proxy_key),
                    )
                    continue

            healthy_proxies.append(p)

        if not healthy_proxies:
            logger.error(
                "ALL PROXIES ARE DEAD OR IN COOLDOWN! "
                "Cannot assign proxies to profiles.",
            )
            logger.error(
                "   Dead: %d, In cooldown: %d",
                len(self.dead_proxies),
                len(self.proxy_cooldowns),
            )
            return

        session_proxies = [
            p for p in healthy_proxies
            if "-session-" in (p.username or "")
        ]
        assignable = (
            session_proxies if session_proxies
            else list(healthy_proxies)
        )

        logger.info(
            "Assigning %d healthy proxies to %d profiles "
            "(Sticky Strategy, provider=%s)...",
            len(assignable),
            len(profiles),
            self.proxy_provider,
        )
        skipped = len(self.proxies) - len(healthy_proxies)
        logger.info(
            "   Filtered out %d dead/cooldown proxies",
            skipped,
        )

        def _normalize(name: str) -> str:
            """Normalise faucet name for comparison."""
            return (
                str(name).lower()
                .replace("_", "")
                .replace(" ", "")
            )

        bypass_raw = getattr(
            self.settings, "proxy_bypass_faucets", None,
        ) or []
        bypass = {_normalize(name) for name in bypass_raw}

        for i, profile in enumerate(profiles):
            faucet_key = _normalize(
                getattr(profile, "faucet", ""),
            )
            # Exact or long-prefix match only (avoid short
            # substrings bypassing, e.g. 'coin' or 'free').
            if faucet_key and any(
                faucet_key == b
                or faucet_key.startswith(b)
                for b in bypass
            ):
                logger.info(
                    "   Profile '%s' bypasses proxies "
                    "for faucet '%s'",
                    profile.username, profile.faucet,
                )
                profile.proxy = None
                profile.residential_proxy = False
                continue

            # Round-robin assignment
            proxy = assignable[i % len(assignable)]

            self.assignments[profile.username] = proxy

            profile.proxy = proxy.to_string()
            profile.residential_proxy = True
            masked = self._mask_proxy_key(
                self._proxy_key(proxy),
            )
            logger.info(
                "   Profile '%s' -> Proxy %s",
                profile.username, masked,
            )

    def get_proxy_for_solver(
        self, username: str,
    ) -> Optional[str]:
        """Return the proxy string for the captcha solver.

        Only meaningful for 2Captcha provider; Zyte/webshare
        proxies should not be leaked to the solver.

        Args:
            username: Account username to look up.

        Returns:
            ``user:pass@ip:port`` string, or ``None``.
        """
        if self.proxy_provider != "2captcha":
            return None
        if username in self.assignments:
            return self.assignments[username].to_2captcha_string()
        return None

    # ------------------------------------------------------------------
    # Proxy rotation
    # ------------------------------------------------------------------

    def rotate_proxy(
        self, profile: AccountProfile,
    ) -> Optional[str]:
        """Rotate the proxy for a profile.

        If the current proxy is dead or in cooldown, finds a new
        healthy one.

        Args:
            profile: Account profile to rotate proxy for.

        Returns:
            The new proxy string, or ``None`` if no healthy
            proxies are left.
        """
        current_proxy_str = profile.proxy
        current_key = current_proxy_str or ""
        if "://" in current_key:
            current_key = current_key.split("://", 1)[1]
        current_host = self._proxy_host_port_from_str(
            current_proxy_str or "",
        )

        rep_enabled = getattr(
            self.settings, "proxy_reputation_enabled", True,
        )
        min_score = getattr(
            self.settings, "proxy_reputation_min_score", 20.0,
        )

        current_score = None
        if current_key and rep_enabled:
            current_score = self.get_proxy_reputation(
                current_key,
            )

        now = time.time()
        cooldown_until = self.proxy_cooldowns.get(current_key)
        cooldown_active = bool(
            cooldown_until and cooldown_until > now,
        )
        host_cd = (
            self.proxy_cooldowns.get(current_host)
            if current_host
            else None
        )
        host_cooldown_active = bool(
            host_cd and host_cd > now,
        )

        needs_rotation = (
            not current_key
            or current_key in self.dead_proxies
            or (
                current_host
                and current_host in self.dead_proxies
            )
            or cooldown_active
            or host_cooldown_active
            or profile.proxy_rotation_strategy == "random"
            or (
                current_score is not None
                and current_score < min_score
            )
        )

        if not needs_rotation:
            return current_proxy_str

        if not self.proxies:
            logger.error(
                "No proxies available to rotate for %s",
                profile.username,
            )
            profile.proxy = None
            return None

        # Filter out dead and cooldown proxies
        healthy: List[Proxy] = []
        for p in self.proxies:
            proxy_key = self._proxy_key(p)
            proxy_host = self._proxy_host_port(p)

            if proxy_key in self.dead_proxies:
                continue
            if proxy_host and proxy_host in self.dead_proxies:
                continue
            if self.proxy_cooldowns.get(proxy_key, 0) > now:
                continue
            if (
                proxy_host
                and self.proxy_cooldowns.get(
                    proxy_host, 0,
                ) > now
            ):
                continue

            healthy.append(p)

        # Apply reputation filter if enabled
        if healthy and rep_enabled:
            before_filter = len(healthy)
            healthy = [
                p for p in healthy
                if self.get_proxy_reputation(
                    p.to_string(),
                ) >= min_score
            ]
            filtered_out = before_filter - len(healthy)
            if filtered_out:
                logger.debug(
                    "Filtered out %d low-reputation "
                    "proxies (min score: %s)",
                    filtered_out, min_score,
                )

        if not healthy:
            logger.error(
                "NO HEALTHY PROXIES for %s",
                profile.username,
            )
            logger.error(
                "   Total proxies: %d", len(self.proxies),
            )
            logger.error(
                "   Dead proxies: %d",
                len(self.dead_proxies),
            )
            in_cd = len([
                k for k, v in self.proxy_cooldowns.items()
                if v > now
            ])
            logger.error(
                "   In cooldown: %d", in_cd,
            )

            # Salvage: proxy with shortest cooldown
            cooldown_proxies = [
                (p, self.proxy_cooldowns.get(
                    self._proxy_key(p), 0,
                ))
                for p in self.proxies
                if self._proxy_key(p) in self.proxy_cooldowns
            ]
            if cooldown_proxies:
                best = min(
                    cooldown_proxies, key=lambda x: x[1],
                )
                if best[1] > now:
                    wait_time = int(best[1] - now)
                    logger.warning(
                        "   Best available proxy has "
                        "%ds cooldown remaining",
                        wait_time,
                    )

            profile.proxy = None
            return None

        # Choose new proxy based on rotation strategy
        strategy = profile.proxy_rotation_strategy
        if strategy == "health_based" and rep_enabled:
            new_proxy = max(
                healthy,
                key=lambda p: self.get_proxy_reputation(
                    p.to_string(),
                ),
            )
        else:
            new_proxy = random.choice(healthy)
        profile.proxy = new_proxy.to_string()
        self.assignments[profile.username] = new_proxy
        masked = self._mask_proxy_key(
            self._proxy_key(new_proxy),
        )
        logger.info(
            "[ROTATE] %s rotated to %s",
            profile.username, masked,
        )
        return profile.proxy

    # ------------------------------------------------------------------
    # Auto-provisioning & refresh
    # ------------------------------------------------------------------

    async def auto_provision_proxies(
        self,
        min_threshold: int = 10,
        provision_count: int = 5,
    ) -> int:
        """Auto-buy proxies when pool drops below threshold.

        Integrates with WebShare API to automatically purchase
        proxies when healthy proxy count falls below minimum.

        Args:
            min_threshold: Trigger when healthy < this number.
            provision_count: How many proxies to fetch.

        Returns:
            Number of proxies added.
        """
        healthy_count = len([
            p for p in self.proxies
            if self._proxy_key(p) not in self.dead_proxies
        ])

        if healthy_count >= min_threshold:
            logger.debug(
                "Proxy count healthy: %d/%d",
                healthy_count, min_threshold,
            )
            return 0

        logger.warning(
            "LOW PROXY COUNT: %d/%d. "
            "Auto-provisioning %d proxies...",
            healthy_count,
            min_threshold,
            provision_count,
        )

        try:
            if self.proxy_provider in (
                "2captcha", "webshare", "zyte",
            ):
                added = await self.fetch_proxies_from_api(
                    provision_count,
                )
                if added > 0:
                    logger.info(
                        "Auto-provisioned %d new proxies "
                        "via API",
                        added,
                    )
                    return added
            else:
                logger.warning(
                    "Auto-provisioning not supported "
                    "for provider: %s",
                    self.proxy_provider,
                )
                return 0

        except Exception as e:
            logger.error(
                "Auto-provisioning failed: %s", e,
            )

        return 0

    async def auto_remove_dead_proxies(
        self, failure_threshold: int = 3,
    ) -> int:
        """Remove proxies after consecutive failures.

        Args:
            failure_threshold: Remove after this many
                consecutive failures.

        Returns:
            Number of proxies removed.
        """
        original_count = len(self.proxies)
        self.proxies = [
            p for p in self.proxies
            if self._proxy_key(p) not in self.dead_proxies
        ]
        removed = original_count - len(self.proxies)

        # Also check failure counts
        for proxy in list(self.proxies):
            proxy_key = self._proxy_key(proxy)
            failures = self.proxy_failures.get(proxy_key, 0)
            if failures >= failure_threshold:
                masked = self._mask_proxy_key(proxy_key)
                logger.info(
                    "Removing proxy with %d failures: %s",
                    failures, masked,
                )
                self.proxies.remove(proxy)
                self.dead_proxies.append(proxy_key)
                removed += 1

        if removed > 0:
            logger.info(
                "Removed %d dead/failing proxies from pool",
                removed,
            )
            self._save_health_data()

        return removed

    async def auto_refresh_proxies(
        self,
        min_healthy_count: int = 50,
        target_count: int = 100,
        max_latency_ms: float = 3000,
        refresh_interval_hours: int = 24,
    ) -> bool:
        """Automatically refresh the proxy pool when needed.

        This method:
        1. Checks current healthy proxy count.
        2. If below *min_healthy_count*, fetches new proxies.
        3. Validates and filters by latency.
        4. Can be called periodically (e.g. daily).

        Args:
            min_healthy_count: Minimum healthy proxies before
                refresh.
            target_count: Target total proxy count.
            max_latency_ms: Maximum acceptable latency (ms).
            refresh_interval_hours: Logging only (hours).

        Returns:
            ``True`` if refresh succeeded or was not needed.

        Example::

            pm = ProxyManager(settings)
            success = await pm.auto_refresh_proxies()
        """
        if self.proxy_provider != "2captcha":
            logger.debug(
                "auto_refresh_proxies() skipped: "
                "provider is %s, not 2captcha",
                self.proxy_provider,
            )
            return True

        # Check current health
        health_stats = await self.health_check_all_proxies()
        healthy_count = health_stats.get("healthy", 0)
        total_count = health_stats.get("total", 0)

        logger.info(
            "[AUTO-REFRESH] Current pool: "
            "%d healthy / %d total",
            healthy_count, total_count,
        )

        if healthy_count >= min_healthy_count:
            logger.info(
                "[AUTO-REFRESH] Proxy pool is healthy "
                "(%d >= %d). No refresh needed.",
                healthy_count, min_healthy_count,
            )
            return True

        logger.warning(
            "[AUTO-REFRESH] Low proxy count (%d < %d). "
            "Refreshing pool...",
            healthy_count, min_healthy_count,
        )

        needed = target_count - healthy_count
        fetch_count = max(needed, 20)

        try:
            valid_count = await self.fetch_2captcha_proxies(
                count=fetch_count,
                validate=True,
                max_latency_ms=max_latency_ms,
            )

            if valid_count > 0:
                new_health = (
                    await self.health_check_all_proxies()
                )
                new_healthy = new_health.get("healthy", 0)

                logger.info(
                    "[AUTO-REFRESH] Refresh complete: "
                    "%d healthy proxies (was %d)",
                    new_healthy, healthy_count,
                )

                self._save_health_data()
                return True

            logger.error(
                "[AUTO-REFRESH] Failed to fetch new proxies",
            )
            return False

        except Exception as e:
            logger.error(
                "[AUTO-REFRESH] Error during refresh: %s", e,
            )
            return False

    def get_refresh_schedule_info(self) -> Dict[str, Any]:
        """Get information about the auto-refresh schedule.

        Returns:
            Dictionary with schedule configuration.
        """
        return {
            "enabled": self.proxy_provider == "2captcha",
            "provider": self.proxy_provider,
            "recommended_interval_hours": 24,
            "recommended_cron": "0 2 * * *",
            "health_file": self.health_file,
        }
