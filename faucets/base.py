"""Base faucet bot and claim result definitions for Cryptobot Gen 3.0.

This module defines the abstract :class:`FaucetBot` superclass that all site-
specific bots inherit from, and the :class:`ClaimResult` dataclass returned by
every claim attempt.

:class:`FaucetBot` provides:
    * Humanised browser interaction helpers (``human_type``, ``human_like_click``,
      ``idle_mouse``, ``random_delay``).
    * Configurable behaviour profiles (``fast`` / ``balanced`` / ``cautious``).
    * CAPTCHA solver integration (Turnstile, hCaptcha, reCAPTCHA, image).
    * Cloudflare challenge detection and bypass.
    * Credential resolution from settings or per-instance overrides.
    * Automatic error-type classification for the scheduler.
"""

import asyncio
import json
import logging
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from playwright.async_api import Locator, Page

from browser.stealth_hub import HumanProfile, StealthHub
from core.analytics import get_tracker
from core.config import BotSettings
from core.extractor import DataExtractor
from core.orchestrator import ErrorType
from solvers.captcha import CaptchaSolver

logger = logging.getLogger(__name__)


@dataclass
class ClaimResult:
    """Outcome of a single faucet claim attempt.

    Attributes:
        success: Whether the claim was successful.
        status: Human-readable status / error description.
        next_claim_minutes: Suggested delay (minutes) before the next attempt.
        amount: Claimed amount as a string (in the faucet's native unit).
        balance: Current account balance as a string.
        error_type: Optional :class:`ErrorType` for scheduler retry decisions.
    """

    success: bool
    status: str
    next_claim_minutes: float = 0
    amount: str = "0"
    balance: str = "0"
    error_type: Optional['ErrorType'] = None

    def validate(self, faucet_name: str = "Unknown") -> 'ClaimResult':
        """
        Validate and sanitize ClaimResult fields.

        Ensures amount and balance are valid strings that can be parsed as numbers.
        Logs warnings for suspicious values.

        Args:
            faucet_name: Name of faucet for logging context

        Returns:
            Self (for chaining)
        """
        # Validate amount
        if self.amount is None:
            logger.warning(f"[{faucet_name}] ClaimResult has None amount, setting to '0'")
            self.amount = "0"
        elif not isinstance(self.amount, str):
            # Try to convert to string
            try:
                self.amount = str(self.amount)
            except Exception as e:
                logger.warning(f"[{faucet_name}] Failed to convert amount to string: {e}")
                self.amount = "0"

        # Validate balance
        if self.balance is None:
            logger.warning(f"[{faucet_name}] ClaimResult has None balance, setting to '0'")
            self.balance = "0"
        elif not isinstance(self.balance, str):
            # Try to convert to string
            try:
                self.balance = str(self.balance)
            except Exception as e:
                logger.warning(f"[{faucet_name}] Failed to convert balance to string: {e}")
                self.balance = "0"

        # Log warning if successful but no amount
        if self.success and (not self.amount or self.amount == "0"):
            logger.warning(
                f"[{faucet_name}] ⚠️ Successful ClaimResult has 0 amount - "
                f"possible extraction failure. Status: {self.status}"
            )

        return self


class FaucetBot:
    """Abstract base class for all faucet bots.

    Subclasses **must** implement:
        * ``async login() -> bool``
        * ``async get_balance() -> str``
        * ``async get_timer() -> float``
        * ``async claim() -> ClaimResult``

    And should define ``faucet_name`` and ``base_url`` in ``__init__``.

    Attributes:
        settings: Global :class:`BotSettings` configuration.
        page: Active Playwright ``Page`` for browser interaction.
        solver: :class:`CaptchaSolver` instance (auto-configured from settings).
        faucet_name: Human-readable faucet identifier (set by subclass).
        base_url: Root URL of the faucet site.
        behavior_profile_name: Current humanisation profile name.
        human_profile: Optional :class:`HumanProfile` for advanced timing.
    """

    BEHAVIOR_PROFILES: Dict[str, Dict[str, Tuple[float, float]]] = {
        "fast": {
            "delay_range": (1.0, 3.0),
            "typing_ms": (40, 110),
            "idle_seconds": (0.6, 1.6),
            "reading_seconds": (1.0, 3.0),
            "focus_blur_seconds": (0.4, 1.6)
        },
        "balanced": {
            "delay_range": (2.0, 5.0),
            "typing_ms": (60, 160),
            "idle_seconds": (1.5, 3.5),
            "reading_seconds": (2.0, 5.0),
            "focus_blur_seconds": (0.6, 2.6)
        },
        "cautious": {
            "delay_range": (3.0, 8.0),
            "typing_ms": (80, 220),
            "idle_seconds": (2.5, 6.0),
            "reading_seconds": (4.0, 9.0),
            "focus_blur_seconds": (1.0, 4.0)
        }
    }
    DEFAULT_BEHAVIOR_PROFILE = "balanced"

    def __init__(
        self,
        settings: BotSettings,
        page: Page,
        action_lock: Optional[asyncio.Lock] = None,
    ) -> None:
        """Initialize the FaucetBot.

        Args:
            settings: Configuration settings for the bot.
            page: The Playwright Page instance to control.
            action_lock: Lock to prevent simultaneous actions
                across multiple bot instances.
        """
        self.settings = settings
        self.page = page
        self.action_lock = action_lock

        self.faucet_name = "Generic"
        self.base_url = ""
        self.settings_account_override = None  # Allow manual injection of credentials
        self.behavior_profile_name = self.DEFAULT_BEHAVIOR_PROFILE
        self.behavior_profile = self.BEHAVIOR_PROFILES[self.DEFAULT_BEHAVIOR_PROFILE]
        self._behavior_rng = random.Random()

        # Human timing profile for advanced stealth
        self.human_profile = None  # Will be loaded from fingerprint or set on first use
        self.last_error_type = None

        self._configure_solver(settings)

    def _configure_solver(self, settings: BotSettings) -> None:
        """Initialize and configure the captcha solver."""
        provider = getattr(settings, "captcha_provider", "2captcha").lower()

        # Get primary key
        if provider == "capsolver":
            key = getattr(settings, "capsolver_api_key", None)
        else:
            key = getattr(settings, "twocaptcha_api_key", None)

        self.solver = CaptchaSolver(
            api_key=key,
            provider=provider,
            daily_budget=getattr(settings, "captcha_daily_budget", 5.0),
            adaptive_routing=getattr(settings, "captcha_provider_routing", "fixed") == "adaptive",
            routing_min_samples=getattr(settings, "captcha_provider_routing_min_samples", 20)
        )
        self.solver.set_headless(getattr(settings, "headless", True))

        # Fallback configuration
        fallback_provider = getattr(settings, "captcha_fallback_provider", None)
        fallback_key = getattr(settings, "captcha_fallback_api_key", None)

        # Infer fallback key if missing
        if fallback_provider and not fallback_key:
            if fallback_provider.lower() == "capsolver":
                fallback_key = getattr(settings, "capsolver_api_key", None)
            elif fallback_provider.lower() == "2captcha":
                fallback_key = getattr(settings, "twocaptcha_api_key", None)

        # Automatic fallback to CapSolver if primary is 2captcha (for hCaptcha support)
        if not fallback_provider and provider == "2captcha":
            capsolver_key = getattr(settings, "capsolver_api_key", None)
            if capsolver_key:
                fallback_provider = "capsolver"
                fallback_key = capsolver_key
                logger.info("Auto-configured CapSolver as fallback captcha provider")

        if fallback_provider and fallback_key:
            self.solver.set_fallback_provider(fallback_provider, fallback_key)

    def set_behavior_profile(
        self,
        profile_name: Optional[str] = None,
        profile_hint: Optional[str] = None,
    ) -> None:
        """Select a humanisation timing profile.

        If *profile_hint* is given and matches a known profile key it is used
        directly.  Otherwise a deterministic pseudo-random choice is made
        based on the hash of *profile_name*, ensuring the same account always
        receives the same profile.

        Args:
            profile_name: Seed for deterministic profile selection (e.g. username).
            profile_hint: Explicit profile key (``fast`` / ``balanced`` / ``cautious``).
        """
        profile_key = None
        if profile_hint and profile_hint in self.BEHAVIOR_PROFILES:
            profile_key = profile_hint
        elif profile_name:
            profile_keys = list(self.BEHAVIOR_PROFILES.keys())
            seeded_rng = random.Random(hash(profile_name))
            profile_key = seeded_rng.choice(profile_keys)
        else:
            profile_key = self.DEFAULT_BEHAVIOR_PROFILE

        self.behavior_profile_name = profile_key
        self.behavior_profile = self.BEHAVIOR_PROFILES.get(
            profile_key, self.BEHAVIOR_PROFILES[self.DEFAULT_BEHAVIOR_PROFILE])
        seed_basis = profile_name or profile_key or self.DEFAULT_BEHAVIOR_PROFILE
        self._behavior_rng = random.Random(hash(seed_basis))

    def _resolve_delay_range(self, min_s: Optional[float], max_s: Optional[float]) -> Tuple[float, float]:
        """Return an explicit or profile-default delay range in seconds."""
        if min_s is None or max_s is None:
            min_s, max_s = self.behavior_profile.get("delay_range", (2.0, 5.0))
        return float(min_s), float(max_s)

    def _resolve_typing_range(self, delay_min: Optional[int], delay_max: Optional[int]) -> Tuple[int, int]:
        """Return an explicit or profile-default per-key typing delay range (ms)."""
        if delay_min is None or delay_max is None:
            delay_min, delay_max = self.behavior_profile.get("typing_ms", (60, 160))
        return int(delay_min), int(delay_max)

    def _resolve_idle_duration(self, duration: Optional[float]) -> float:
        """Return an explicit or profile-default idle pause duration (seconds)."""
        if duration is None:
            min_s, max_s = self.behavior_profile.get("idle_seconds", (1.5, 3.5))
            return self._behavior_rng.uniform(min_s, max_s)
        return float(duration)

    def _resolve_reading_duration(self, duration: Optional[float]) -> float:
        """Return an explicit or profile-default simulated reading duration (seconds)."""
        if duration is None:
            min_s, max_s = self.behavior_profile.get("reading_seconds", (2.0, 5.0))
            return self._behavior_rng.uniform(min_s, max_s)
        return float(duration)

    def _resolve_focus_blur_delay(self) -> float:
        """Return a profile-derived delay for simulated focus / blur events."""
        min_s, max_s = self.behavior_profile.get("focus_blur_seconds", (0.6, 2.6))
        return self._behavior_rng.uniform(min_s, max_s)

    async def think_pause(self, reason: str = "") -> None:
        """Small pause simulating user thinking before critical actions.

        Args:
            reason: Context hint -- ``"pre_login"`` or ``"pre_claim"`` add
                extra delay.
        """
        delay = self._behavior_rng.uniform(0.2, 0.6)
        if reason in {"pre_login", "pre_claim"}:
            delay += self._behavior_rng.uniform(0.6, 1.4)
        await asyncio.sleep(delay)

    @property
    def faucet_name(self) -> str:
        """Return the human-readable faucet name."""
        return self._faucet_name

    @faucet_name.setter
    def faucet_name(self, value: str) -> None:
        """Set the faucet name and propagate it to the solver."""
        self._faucet_name = value
        if hasattr(self, 'solver') and self.solver is not None:
            self.solver.set_faucet_name(value)

    def set_proxy(self, proxy_string: str) -> None:
        """Forward proxy configuration to the underlying CAPTCHA solver.

        Args:
            proxy_string: ``user:pass@host:port`` formatted proxy string.
        """
        self.solver.set_proxy(proxy_string)

    def create_error_result(self, status: str, next_claim_minutes: float = 60,
                            exception: Optional[Exception] = None,
                            page_content: Optional[str] = None,
                            status_code: Optional[int] = None,
                            force_error_type: Optional['ErrorType'] = None) -> ClaimResult:
        """
        Create a ClaimResult for an error with automatic error type classification.

        Args:
            status: Error status message
            next_claim_minutes: Minutes until next retry attempt
            exception: The exception that occurred (if any)
            page_content: HTML content for classification
            status_code: HTTP status code
            force_error_type: Override automatic classification

        Returns:
            ClaimResult with appropriate error_type set
        """

        # Use forced type or auto-classify
        if force_error_type:
            error_type = force_error_type
        else:
            # Auto-classify based on status message and other signals
            status_lower = status.lower()
            if any(
                config in status_lower for config in [
                    "hcaptcha", "recaptcha", "turnstile",
                    "captcha config", "solver config", "api key",
                ]
            ):
                error_type = ErrorType.CONFIG_ERROR
            elif any(
                perm in status_lower for perm in [
                    "banned", "suspended",
                    "invalid credentials", "auth failed",
                ]
            ):
                error_type = ErrorType.PERMANENT
            elif exception or page_content or status_code:
                error_type = self.classify_error(exception, page_content, status_code)
            else:
                error_type = ErrorType.UNKNOWN

        logger.debug(
            f"[{self.faucet_name}] Creating error result:"
            f" {status} (type: {error_type.value})"
        )

        return ClaimResult(
            success=False,
            status=status,
            next_claim_minutes=next_claim_minutes,
            error_type=error_type
        )

    def classify_error(
        self,
        exception: Optional[Exception] = None,
        page_content: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> 'ErrorType':
        """Classify error type based on exception, page content, and HTTP status.

        Args:
            exception: The exception that was raised (if any).
            page_content: The page HTML/text content (if available).
            status_code: HTTP status code (if available).

        Returns:
            ErrorType enum value for intelligent recovery.
        """

        # Check status codes first
        if status_code:
            if status_code in [500, 502, 503, 504]:
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    f" FAUCET_DOWN (status {status_code})"
                )
                return ErrorType.FAUCET_DOWN
            if status_code == 429:
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    " RATE_LIMIT (status 429)"
                )
                return ErrorType.RATE_LIMIT
            if status_code == 403:
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    " PROXY_ISSUE (status 403)"
                )
                return ErrorType.PROXY_ISSUE

        # Check exception type and message
        if exception:
            error_msg = str(exception).lower()

            # Browser context closed errors
            if "closed" in error_msg and any(
                term in error_msg for term in [
                    "target", "context", "browser",
                    "connection", "session",
                ]
            ):
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    " TRANSIENT (closed context/browser)"
                )
                return ErrorType.TRANSIENT

            # Captcha failures
            if "captcha" in error_msg and any(
                term in error_msg
                for term in ["failed", "timeout", "error"]
            ):
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    " CAPTCHA_FAILED"
                )
                return ErrorType.CAPTCHA_FAILED

            # Timeout/connection errors
            if any(
                term in error_msg for term in [
                    "timeout", "timed out",
                    "connection reset", "connection refused",
                ]
            ):
                logger.debug(
                    f"[{self.faucet_name}] Classified as"
                    " TRANSIENT (timeout/connection)"
                )
                return ErrorType.TRANSIENT

        # Check page content for specific error messages
        if page_content:
            content_lower = page_content.lower()

            # Permanent failures - account issues
            if any(term in content_lower for term in [
                "banned", "suspended", "disabled",
                "invalid credentials", "wrong password",
                "account locked", "account closed"
            ]):
                logger.debug(f"[{self.faucet_name}] Classified as PERMANENT (account issue)")
                return ErrorType.PERMANENT

            # Rate limiting
            if any(term in content_lower for term in [
                "too many requests", "slow down", "rate limit",
                "try again later", "please wait"
            ]):
                logger.debug(f"[{self.faucet_name}] Classified as RATE_LIMIT")
                return ErrorType.RATE_LIMIT

            # Proxy detection
            if any(term in content_lower for term in [
                "proxy detected", "vpn detected", "unusual activity",
                "suspicious activity", "automated access", "bot detected"
            ]):
                logger.debug(f"[{self.faucet_name}] Classified as PROXY_ISSUE")
                return ErrorType.PROXY_ISSUE

            # Cloudflare/security challenges
            if any(term in content_lower for term in [
                "cloudflare", "checking your browser", "security check",
                "ddos protection", "ray id"
            ]):
                logger.debug(f"[{self.faucet_name}] Classified as RATE_LIMIT (cloudflare)")
                return ErrorType.RATE_LIMIT

        # Default to UNKNOWN if we can't classify
        logger.debug(f"[{self.faucet_name}] Classified as UNKNOWN (no clear indicators)")
        return ErrorType.UNKNOWN

    @staticmethod
    def strip_email_alias(email: Optional[str]) -> Optional[str]:
        """
        Strip email alias (plus addressing) from email address.

        Converts 'user+alias@example.com' to 'user@example.com'.
        Some faucets (CoinPayU, AdBTC) block email aliases with '+'.

        Args:
            email: The email address that may contain a '+' alias.
                   Can be None or empty string.

        Returns:
            The base email address without the alias.
            Returns the input unchanged if it's None, empty, or doesn't contain '@'.
        """
        if not email or '@' not in email:
            return email

        local_part, domain = email.rsplit('@', 1)
        if '+' in local_part:
            base_local = local_part.split('+')[0]
            return f"{base_local}@{domain}"

        return email

    def get_credentials(self, faucet_name: str) -> Optional[Dict[str, str]]:
        """Retrieve login credentials for a faucet.

        Checks :attr:`settings_account_override` first (set by the
        scheduler when injecting per-profile credentials), then falls
        back to :meth:`BotSettings.get_account`.

        Args:
            faucet_name: Faucet identifier (e.g. ``"firefaucet"``).

        Returns:
            Dict with ``username`` / ``password`` keys, or ``None``.
        """
        if self.settings_account_override:
            return self.settings_account_override
        return self.settings.get_account(faucet_name)

    def get_withdrawal_address(self, coin: str) -> Optional[str]:
        """
        Get the appropriate withdrawal address based on configuration.

        Checks settings.use_faucetpay first, falls back to direct wallet.
        Priority (configurable):
        1) wallet_addresses dict when prefer_wallet_addresses=True (Cake direct)
        2) FaucetPay
        3) Direct wallet fields
        4) wallet_addresses dict fallback

        Args:
            coin: Cryptocurrency symbol (BTC, LTC, DOGE, TRX, ETH, etc.)

        Returns:
            Withdrawal address string, or None if not configured
        """
        coin = coin.upper()

        # Normalize coin name variations
        coin_map = {
            "LITE": "LTC",
            "TRON": "TRX",
            "BINANCE": "BNB",
            "USD": "USDT",
            "MATIC": "POLYGON",
        }
        coin = coin_map.get(coin, coin)

        prefer_wallet = getattr(self.settings, "prefer_wallet_addresses", False)
        wallet_dict = getattr(self.settings, "wallet_addresses", {})

        if prefer_wallet and wallet_dict:
            addr = self._resolve_wallet_dict_entry(wallet_dict, coin, "preferred")
            if addr:
                return addr

        # 1. FaucetPay mode (preferred for micro-earnings)
        if self.settings.use_faucetpay:
            fp_attr = f"faucetpay_{coin.lower()}_address"
            fp_address = getattr(self.settings, fp_attr, None)
            if not fp_address and coin == "POLYGON":
                fp_address = getattr(self.settings, "faucetpay_polygon_address", None)
            if fp_address:
                logger.debug(f"[{self.faucet_name}] Using FaucetPay address for {coin}")
                return fp_address

        # 2. Direct wallet mode
        direct_attr = f"{coin.lower()}_withdrawal_address"
        direct_address = getattr(self.settings, direct_attr, None)
        if direct_address:
            logger.debug(f"[{self.faucet_name}] Using direct wallet address for {coin}")
            return direct_address

        # 3. Fallback to wallet_addresses dict (supports nested dicts)
        if wallet_dict:
            addr = self._resolve_wallet_dict_entry(wallet_dict, coin, "fallback")
            if addr:
                return addr

        logger.warning(f"[{self.faucet_name}] No withdrawal address configured for {coin}")
        return None

    def _resolve_wallet_dict_entry(self, wallet_dict: Dict, coin: str, source: str) -> Optional[str]:
        """Extract an address from a wallet_addresses dict entry.

        Supports both plain string entries and nested dicts with
        ``address``, ``wallet``, or ``addr`` keys.

        Args:
            wallet_dict: The wallet_addresses mapping.
            coin: Cryptocurrency symbol.
            source: Label for debug logging (e.g. ``"preferred"``, ``"fallback"``).

        Returns:
            Address string or ``None``.
        """
        dict_entry = wallet_dict.get(coin)
        if not dict_entry:
            return None
        if isinstance(dict_entry, dict):
            for key in ("address", "wallet", "addr"):
                if dict_entry.get(key):
                    logger.debug(
                        f"[{self.faucet_name}] Using {source}"
                        f" wallet_addresses dict ({key})"
                        f" for {coin}"
                    )
                    return str(dict_entry[key])
            return None
        logger.debug(f"[{self.faucet_name}] Using {source} wallet_addresses dict for {coin}")
        return str(dict_entry)

    async def random_delay(self, min_s: Optional[float] = None, max_s: Optional[float] = None) -> None:
        """Wait a random duration to mimic human inter-action pauses.

        When a :class:`HumanProfile` is active and no explicit bounds are
        supplied, timings are drawn from the profile's ``click`` action
        range.  An idle-pause (simulated distraction) may also occur.

        Args:
            min_s: Override minimum wait in seconds.
            max_s: Override maximum wait in seconds.
        """
        # Use human profile timing if available and no explicit override
        if self.human_profile and min_s is None and max_s is None:
            delay = HumanProfile.get_action_delay(self.human_profile, "click")

            # Check if user should idle (simulates distraction)
            should_pause, pause_duration = HumanProfile.should_idle(self.human_profile)
            if should_pause:
                logger.debug(
                    f"[{self.faucet_name}] Human profile '{self.human_profile}'"
                    f" idle pause: {pause_duration:.1f}s"
                )
                await asyncio.sleep(pause_duration)
                return
        else:
            # Fallback to legacy behavior profile system
            min_s, max_s = self._resolve_delay_range(min_s, max_s)
            delay = self._behavior_rng.uniform(min_s, max_s)

        await asyncio.sleep(delay)

    async def thinking_pause(self) -> None:
        """Insert a "thinking" pause before important actions.

        Draws the delay from the active :class:`HumanProfile` ``thinking``
        range, or falls back to ``uniform(1.0, 3.0)`` seconds.
        """
        if self.human_profile:
            delay = HumanProfile.get_thinking_pause(self.human_profile)
            logger.debug(f"[{self.faucet_name}] Thinking pause ({self.human_profile}): {delay:.2f}s")
        else:
            # Fallback to reasonable default
            delay = random.uniform(1.0, 3.0)

        await asyncio.sleep(delay)

    async def warm_up_page(self) -> None:
        """Simulate organic browsing behaviour after page load.

        Creates a behavioural baseline that makes the session look natural
        before any login/claim interaction:

        * Scroll events (humans always scroll to see the page).
        * Mouse-move events at random viewport positions.
        * Short reading delays.

        Call **after** :meth:`safe_navigate` but **before** interacting
        with login / claim buttons.
        """
        try:
            warmup_script = StealthHub.get_pre_navigation_warmup_script()
            await self.page.evaluate(warmup_script)

            # Additional page-level engagement: move mouse across viewport
            vp = self.page.viewport_size
            if vp:
                # Simulate a few natural mouse positions (reading behavior)
                for _ in range(random.randint(2, 4)):
                    x = random.randint(100, max(200, vp['width'] - 100))
                    y = random.randint(80, max(200, vp['height'] - 100))
                    await self.page.mouse.move(x, y, steps=random.randint(5, 15))
                    await asyncio.sleep(random.uniform(0.3, 1.2))

            # Brief reading pause
            await asyncio.sleep(random.uniform(0.5, 2.0))
            logger.debug(f"[{self.faucet_name}] Page warm-up complete")
        except Exception as e:
            # Non-critical - don't fail the faucet if warmup fails
            logger.debug(f"[{self.faucet_name}] Warm-up skipped: {e}")

    async def simulate_tab_activity(self) -> None:
        """Simulate tab switching / background-foreground transitions.

        Anti-bot systems track visibility state changes. Real users frequently
        switch tabs. This simulates that pattern by briefly blurring and
        re-focusing the page, creating natural visibilitychange events.
        """
        try:
            # Simulate losing focus (user switches to another tab)
            await self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            await asyncio.sleep(random.uniform(1.0, 5.0))

            # Simulate regaining focus (user comes back)
            await self.page.evaluate("""() => {
                window.dispatchEvent(new Event('focus'));
                document.dispatchEvent(new Event('visibilitychange'));
            }""")
            await asyncio.sleep(random.uniform(0.3, 1.0))
            logger.debug(f"[{self.faucet_name}] Tab activity simulated")
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Tab activity simulation skipped: {e}")

    def load_human_profile(self, profile_name: str) -> str:
        """
        Load or assign human timing profile for this account.
        Profile is persisted in profile_fingerprints.json for consistency.

        Args:
            profile_name: Account/profile identifier

        Returns:
            Selected profile type (fast/normal/cautious/distracted)
        """
        config_dir = Path(__file__).parent.parent / "config"
        fingerprint_file = config_dir / "profile_fingerprints.json"

        # Load existing fingerprints
        fingerprints = {}
        if fingerprint_file.exists():
            try:
                with open(fingerprint_file, 'r') as f:
                    fingerprints = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load profile fingerprints: {e}")

        # Check if profile already has human_profile assigned
        if profile_name in fingerprints and "human_profile" in fingerprints[profile_name]:
            self.human_profile = fingerprints[profile_name]["human_profile"]
            logger.info(
                f"[{self.faucet_name}] Loaded existing human"
                f" profile '{self.human_profile}'"
                f" for {profile_name}"
            )
        else:
            # Assign new profile
            self.human_profile = HumanProfile.get_random_profile()

            # Save to fingerprints
            if profile_name not in fingerprints:
                fingerprints[profile_name] = {}
            fingerprints[profile_name]["human_profile"] = self.human_profile

            try:
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(fingerprint_file, 'w') as f:
                    json.dump(fingerprints, f, indent=2)
                logger.info(
                    f"[{self.faucet_name}] Assigned new human profile"
                    f" '{self.human_profile}' for {profile_name}"
                )
            except Exception as e:
                logger.error(f"Failed to save human profile: {e}")

        return self.human_profile

    async def human_like_click(self, locator: Locator) -> None:
        """Click an element with Bezier-curve mouse movement.

        Simulates a realistic human click by:

        * Scrolling the element into view.
        * Pre-click aiming delay (profile-based).
        * Removing transparent overlay divs that capture clicks.
        * Moving the cursor along a cubic Bezier curve with
          acceleration/deceleration.
        * Clicking at a Gaussian-distributed offset within the
          element's bounding box.

        Args:
            locator: Playwright ``Locator`` targeting the element.
        """
        if await locator.is_visible():
            await locator.scroll_into_view_if_needed()

            # Profile-based pre-click pause (thinking/aiming)
            if self.human_profile:
                pre_click_delay = HumanProfile.get_action_delay(self.human_profile, "click") * 0.3
                await asyncio.sleep(pre_click_delay)
            else:
                await asyncio.sleep(random.uniform(0.2, 0.6))

            # Remove blocking overlays
            await self.remove_overlays()

            box = await locator.bounding_box()
            if not box:
                await locator.click(delay=random.randint(100, 250))
                return

            # Target point within the button (Gaussian distribution toward center)
            target_x = box['x'] + box['width'] * max(0.15, min(0.85, random.gauss(0.5, 0.15)))
            target_y = box['y'] + box['height'] * max(0.15, min(0.85, random.gauss(0.5, 0.15)))

            # Get current mouse position estimate (or use a random starting point)
            vp = self.page.viewport_size
            if vp:
                start_x = random.uniform(0, vp['width'])
                start_y = random.uniform(0, vp['height'])
            else:
                start_x = random.uniform(100, 800)
                start_y = random.uniform(100, 500)

            # Cubic Bézier mouse movement for natural trajectory
            await self._bezier_mouse_move(start_x, start_y, target_x, target_y)

            # Tiny pause before click (aim/settle time)
            await asyncio.sleep(random.uniform(0.05, 0.18))

            # Randomized mouse button hold duration (humans don't click instantly)
            click_delay = random.randint(60, 180)

            # Action synchronizer
            if self.action_lock:
                async with self.action_lock:
                    await self.page.mouse.click(target_x, target_y, delay=click_delay)
            else:
                await self.page.mouse.click(target_x, target_y, delay=click_delay)

            # Small post-click drift (hand relaxation)
            if random.random() < 0.4:
                drift_x = target_x + random.uniform(-8, 8)
                drift_y = target_y + random.uniform(-5, 15)
                await self.page.mouse.move(drift_x, drift_y, steps=random.randint(2, 5))

    async def _bezier_mouse_move(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        """Move the mouse along a cubic Bezier curve.

        Simulates natural acceleration (fast start, slow end) using
        Fitts's law approximation. Two random control points offset
        from the straight line create a natural arc.
        """
        # Distance determines number of steps and control point spread
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.sqrt(dx * dx + dy * dy)

        # More steps for longer distances (with natural variation)
        num_steps = max(
            8, min(40, int(distance / 15) + random.randint(-3, 5))
        )

        # Control point 1 (about 1/3 of the way, with arc offset)
        spread = min(distance * 0.4, 150)
        cp1_x = (start_x + dx * random.uniform(0.2, 0.4)
                 + random.uniform(-spread, spread))
        cp1_y = (start_y + dy * random.uniform(0.2, 0.4)
                 + random.uniform(-spread * 0.5, spread * 0.5))

        # Control point 2 (about 2/3 of the way, smaller offset)
        cp2_x = (start_x + dx * random.uniform(0.6, 0.8)
                 + random.uniform(-spread * 0.3, spread * 0.3))
        cp2_y = (start_y + dy * random.uniform(0.6, 0.8)
                 + random.uniform(-spread * 0.3, spread * 0.3))

        # Generate points along the Bezier curve with easing
        for i in range(1, num_steps + 1):
            # Ease-out timing function: fast start, slow approach
            t_linear = i / num_steps
            t = 1 - (1 - t_linear) ** 2.5  # Quadratic ease-out

            # Cubic Bézier formula
            inv_t = 1 - t
            bx = (inv_t**3 * start_x +
                  3 * inv_t**2 * t * cp1_x +
                  3 * inv_t * t**2 * cp2_x +
                  t**3 * end_x)
            by = (inv_t**3 * start_y +
                  3 * inv_t**2 * t * cp1_y +
                  3 * inv_t * t**2 * cp2_y +
                  t**3 * end_y)

            # Add micro-jitter (hand tremor) - reduces near the target
            jitter_scale = max(0.2, 1.0 - t)
            bx += random.gauss(0, 0.5 * jitter_scale)
            by += random.gauss(0, 0.5 * jitter_scale)

            await self.page.mouse.move(bx, by)

            # Variable inter-step delay (slower near target = Fitts's law)
            speed_factor = max(0.3, 1.0 - t * 0.7)
            await asyncio.sleep(random.uniform(0.003, 0.015) * speed_factor)

    async def remove_overlays(self) -> None:
        """Remove transparent/fixed overlay divs that steal clicks.

        Faucet sites often layer invisible ``<div>``/``<ins>``/``<iframe>``
        elements over buttons to trigger pop-unders.  This JS snippet
        removes elements matching ``position:fixed|absolute`` with
        ``zIndex > 100`` and near-zero opacity.
        """
        await self.page.evaluate("""() => {
            const overlays = Array.from(document.querySelectorAll('div, ins, iframe')).filter(el => {
                const style = window.getComputedStyle(el);
                return (style.position === 'absolute' || style.position === 'fixed') &&
                       (parseInt(style.zIndex, 10) > 100 || style.width === '100vw' || style.height === '100vh') &&
                       (parseFloat(style.opacity) < 0.1 || style.backgroundColor === 'transparent');
            });
            overlays.forEach(el => el.remove());
        }""")

    async def human_type(
        self,
        selector: Union[str, Locator],
        text: str,
        delay_min: Optional[int] = None,
        delay_max: Optional[int] = None,
        simulate_typos: bool = False,
    ) -> None:
        """Type text with realistic keystroke dynamics.

        Simulates human typing patterns:

        * Variable inter-key delays (faster for common digraphs).
        * Occasional mid-word pauses.
        * Burst-then-pause rhythm.
        * Optional typo injection with backspace correction.

        Args:
            selector: CSS selector string or Playwright ``Locator``.
            text: The text to type.
            delay_min: Per-key minimum delay in **ms** (overrides profile).
            delay_max: Per-key maximum delay in **ms** (overrides profile).
            simulate_typos: If ``True``, occasionally mis-type and correct.
                Use only for non-credential fields.
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector

        await self.human_like_click(locator)

        # Clear existing text
        await locator.fill("")

        # Determine base typing speed from profile
        if self.human_profile and delay_min is None and delay_max is None:
            char_delay_s = HumanProfile.get_action_delay(self.human_profile, "type")
            base_delay_ms = max(30, min(250, int(char_delay_s * 1000)))
        else:
            delay_min, delay_max = self._resolve_typing_range(delay_min, delay_max)
            base_delay_ms = self._behavior_rng.randint(delay_min, delay_max)

        # Type character by character with realistic dynamics
        # Common letter pairs that are typed faster (muscle memory)
        fast_pairs = {'th', 'he', 'in', 'er', 'an', 'on', 'en', 'at', 'es',
                      'or', 'ti', 'te', 'st', 'io', 'ar', 'le', 'nd', 'ou', 'it', 'se'}

        # Adjacent keyboard keys for realistic typos
        adjacent_keys = {
            'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr', 'f': 'dg',
            'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk', 'k': 'jl', 'l': 'k',
            'm': 'n', 'n': 'bm', 'o': 'ip', 'p': 'o', 'q': 'w', 'r': 'et',
            's': 'ad', 't': 'ry', 'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc',
            'y': 'tu', 'z': 'x'
        }

        for i, char in enumerate(text):
            # Simulate occasional typo (2-4% chance)
            if (simulate_typos and char.isalpha()
                    and random.random() < 0.03
                    and 2 < i < len(text) - 2):
                # Type a wrong adjacent key
                wrong_char = random.choice(adjacent_keys.get(char.lower(), char.lower()))
                if char.isupper():
                    wrong_char = wrong_char.upper()
                await self.page.keyboard.type(wrong_char, delay=0)
                await asyncio.sleep(random.uniform(0.08, 0.2))

                # Brief pause (noticing the mistake)
                await asyncio.sleep(random.uniform(0.15, 0.5))

                # Backspace to correct
                await self.page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))

            # Calculate delay for this keystroke
            delay = base_delay_ms

            # Common digraphs are faster (muscle memory)
            if i > 0 and text[i - 1:i + 1].lower() in fast_pairs:
                delay = int(delay * random.uniform(0.5, 0.75))

            # Capitals and special characters take slightly longer
            if char.isupper() or char in '!@#$%^&*()_+-=[]{}|;:,.<>?/~`':
                delay = int(delay * random.uniform(1.2, 1.6))

            # Numbers typed slightly faster (numpad muscle memory)
            if char.isdigit():
                delay = int(delay * random.uniform(0.8, 1.1))

            # Spaces often have a tiny pause (between words)
            if char == ' ':
                delay = int(delay * random.uniform(1.1, 1.8))

            # Occasional "thinking" micro-pause (2-5% of keystrokes)
            if random.random() < 0.035 and i > 2:
                await asyncio.sleep(random.uniform(0.3, 0.9))

            # Burst typing: consecutive keys sometimes come faster
            if i > 1 and i % random.randint(4, 8) == 0:
                # Short burst at higher speed
                delay = int(delay * random.uniform(0.4, 0.6))

            # Add natural variance (±30%)
            delay = int(delay * random.uniform(0.7, 1.3))
            delay = max(20, delay)

            # Use page.keyboard for reliable character input
            await self.page.keyboard.type(char, delay=0)
            await asyncio.sleep(delay / 1000.0)

    async def check_page_health(self) -> bool:
        """
        Check if the page is still alive and responsive.
        Returns False if page is closed or unresponsive.
        """
        try:
            if not self.page:
                logger.debug(f"[{self.faucet_name}] Page health check: no page object")
                return False

            # Check if page is closed
            if self.page.is_closed():
                logger.debug(f"[{self.faucet_name}] Page health check: page is closed")
                return False

            # Try a lightweight operation to verify page is responsive
            await asyncio.wait_for(self.page.evaluate("1 + 1"), timeout=3.0)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"[{self.faucet_name}] Page health check timed out - page likely frozen")
            return False
        except Exception as e:
            # Don't log closed page errors as warnings
            err_str = str(e).lower()
            if not ("closed" in err_str and ("target" in err_str or "connection" in err_str)):
                logger.debug(f"[{self.faucet_name}] Page health check failed: {e}")
            return False

    async def safe_page_operation(
        self,
        operation_name: str,
        operation_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Safely execute a page operation with health checks.

        Returns ``None`` if page is closed or operation fails.

        Args:
            operation_name: Name of the operation for logging.
            operation_func: Async function to execute.
            *args: Positional arguments for *operation_func*.
            **kwargs: Keyword arguments for *operation_func*.

        Returns:
            Result of *operation_func* or ``None`` if failed.
        """
        try:
            # Check page health before operation
            if not await self.check_page_health():
                logger.warning(f"[{self.faucet_name}] Cannot execute {operation_name}: page is not alive")
                return None

            # Execute the operation
            return await operation_func(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "closed" in err_str and ("target" in err_str or "connection" in err_str):
                logger.debug(f"[{self.faucet_name}] {operation_name} failed: page/context closed")
            else:
                logger.warning(f"[{self.faucet_name}] {operation_name} failed: {e}")
            return None

    async def safe_click(self, selector: Union[str, Locator], **kwargs) -> bool:
        """Click an element with page-health pre-checks.

        Wraps :meth:`safe_page_operation` around ``locator.click()``.

        Args:
            selector: CSS selector string or Playwright ``Locator``.
            **kwargs: Forwarded to ``locator.click()``.

        Returns:
            ``True`` if the click succeeded, ``False`` on any error.
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        result = await self.safe_page_operation(
            f"click({selector})",
            locator.click,
            **kwargs
        )
        return result is not None

    async def safe_fill(self, selector: Union[str, Locator], text: str, **kwargs) -> bool:
        """Fill an input field with page-health pre-checks.

        Args:
            selector: CSS selector string or Playwright ``Locator``.
            text: Value to fill.
            **kwargs: Forwarded to ``locator.fill()``.

        Returns:
            ``True`` if the fill succeeded, ``False`` on any error.
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        result = await self.safe_page_operation(
            f"fill({selector})",
            locator.fill,
            text,
            **kwargs
        )
        return result is not None

    async def safe_goto(self, url: str, **kwargs) -> bool:
        """Navigate to *url* with page-health pre-checks.

        Args:
            url: Target URL.
            **kwargs: Forwarded to ``page.goto()``.

        Returns:
            ``True`` if the navigation succeeded, ``False`` otherwise.
        """
        result = await self.safe_page_operation(
            f"goto({url})",
            self.page.goto,
            url,
            **kwargs
        )
        return result is not None

    async def idle_mouse(self, duration: Optional[float] = None) -> None:
        """
        Move mouse randomly to simulate user reading/thinking
        with natural movement patterns including:
        - Drift towards content areas (not edges)
        - Variable speed (slow drifts + quick repositions)
        - Occasional pauses (hand resting)
        - Small circular/figure-8 micro-movements

        Args:
            duration: Approximate duration in seconds (optional)
        """
        # Use human profile scroll timing if no duration specified
        if duration is None:
            if self.human_profile:
                duration = HumanProfile.get_action_delay(self.human_profile, "scroll") * 2
            else:
                duration = self._resolve_idle_duration(duration)

        start = time.time()
        # Initialize cursor position
        vp = self.page.viewport_size
        if not vp:
            return

        w, h = vp['width'], vp['height']
        # Start in the content area (avoid edges)
        cur_x = random.uniform(w * 0.15, w * 0.85)
        cur_y = random.uniform(h * 0.2, h * 0.7)

        while time.time() - start < duration:
            action = random.random()

            if action < 0.15:
                # 15%: Hand resting - no movement, just pause
                await asyncio.sleep(random.uniform(0.5, 2.0))

            elif action < 0.35:
                # 20%: Small micro-circle (finger fidget)
                radius = random.uniform(3, 12)
                steps = random.randint(6, 12)
                for j in range(steps):
                    angle = 2 * math.pi * j / steps
                    mx = cur_x + radius * math.cos(angle)
                    my = cur_y + radius * math.sin(angle)
                    await self.page.mouse.move(mx, my)
                    await asyncio.sleep(random.uniform(0.02, 0.06))

            elif action < 0.65:
                # 30%: Short drift (reading along a line)
                drift_x = cur_x + random.uniform(-60, 60)
                drift_y = cur_y + random.uniform(-15, 25)  # Bias slightly downward
                # Clamp to content area
                drift_x = max(w * 0.05, min(w * 0.95, drift_x))
                drift_y = max(h * 0.05, min(h * 0.95, drift_y))

                steps = random.randint(4, 10)
                await self.page.mouse.move(drift_x, drift_y, steps=steps)
                cur_x, cur_y = drift_x, drift_y
                await asyncio.sleep(random.uniform(0.15, 0.5))

            else:
                # 35%: Quick reposition (looking at different part of page)
                new_x = random.gauss(w * 0.5, w * 0.2)  # Gaussian toward center
                new_y = random.gauss(h * 0.45, h * 0.2)
                new_x = max(w * 0.05, min(w * 0.95, new_x))
                new_y = max(h * 0.05, min(h * 0.95, new_y))

                await self.page.mouse.move(new_x, new_y, steps=random.randint(6, 15))
                cur_x, cur_y = new_x, new_y
                await asyncio.sleep(random.uniform(0.2, 0.8))

    async def simulate_reading(self, duration: Optional[float] = None) -> None:
        """
        Simulate a user reading content with natural scrolling behavior.

        Models realistic reading patterns:
        - Smooth scroll segments (reading paragraphs)
        - Quick skim scrolls (scanning content)
        - Occasional scroll-back (re-reading)
        - Mouse following text (tracking with cursor)
        - Pauses at interesting content

        Args:
            duration: Approximate duration in seconds to simulate reading (optional)
        """
        # Use human profile read timing if no duration specified
        if duration is None:
            if self.human_profile:
                duration = HumanProfile.get_action_delay(self.human_profile, "read")
            else:
                duration = self._resolve_reading_duration(duration)

        start = time.time()
        vp = self.page.viewport_size
        if not vp:
            await asyncio.sleep(duration)
            return

        total_scrolled = 0

        while time.time() - start < duration:
            action_roll = self._behavior_rng.random()

            if action_roll < 0.50:
                # 50%: Normal reading scroll (small, paragraph-sized)
                scroll_amount = self._behavior_rng.randint(40, 120)
                # Use physics-based momentum scroll
                await self.natural_scroll(distance=scroll_amount, direction=1)
                total_scrolled += scroll_amount

                # Reading pause (longer = more engaged)
                await asyncio.sleep(self._behavior_rng.uniform(0.8, 2.5))

            elif action_roll < 0.65:
                # 15%: Quick skim scroll (scanning content)
                scroll_amount = self._behavior_rng.randint(150, 350)
                await self.natural_scroll(distance=scroll_amount, direction=1)
                total_scrolled += scroll_amount
                await asyncio.sleep(self._behavior_rng.uniform(0.3, 0.8))

            elif action_roll < 0.75:
                # 10%: Scroll back up (re-reading something)
                scroll_back = self._behavior_rng.randint(50, min(200, max(50, total_scrolled // 3)))
                await self.natural_scroll(distance=scroll_back, direction=-1)
                total_scrolled = max(0, total_scrolled - scroll_back)
                await asyncio.sleep(self._behavior_rng.uniform(0.5, 1.5))

            elif action_roll < 0.88:
                # 13%: Mouse tracks text (cursor follows reading position)
                w = vp['width']
                # Simulate reading left-to-right
                line_y = self._behavior_rng.randint(int(vp['height'] * 0.3), int(vp['height'] * 0.6))
                x_start = self._behavior_rng.randint(int(w * 0.1), int(w * 0.3))
                x_end = self._behavior_rng.randint(int(w * 0.5), int(w * 0.8))

                await self.page.mouse.move(x_start, line_y, steps=3)
                steps = self._behavior_rng.randint(6, 15)
                for step in range(steps):
                    progress = step / steps
                    x = x_start + (x_end - x_start) * progress
                    y = line_y + random.gauss(0, 1.5)
                    await self.page.mouse.move(x, y)
                    await asyncio.sleep(self._behavior_rng.uniform(0.04, 0.12))

                await asyncio.sleep(self._behavior_rng.uniform(0.3, 0.8))

            else:
                # 12%: Pause + Perlin drift or idle micro-movement (absorbed in content)
                if self._behavior_rng.random() < 0.5:
                    await self.natural_mouse_drift(duration=self._behavior_rng.uniform(0.5, 1.5))
                else:
                    await self.idle_mouse(duration=self._behavior_rng.uniform(0.5, 1.5))

    async def natural_scroll(self, distance: int = 300, direction: int = 1) -> None:
        """
        Perform a physically realistic scroll with momentum and deceleration.

        Models real trackpad/mouse wheel physics:
        - Initial acceleration phase (finger starts moving)
        - Peak velocity (mid-scroll)
        - Deceleration with friction (finger slows/lifts)
        - Optional micro-bounce at end (trackpad overscroll)

        Args:
            distance: Total scroll distance in pixels
            direction: 1 for down, -1 for up
        """
        if not self.page or distance <= 0:
            return

        try:
            # Physics parameters with human variation
            num_steps = self._behavior_rng.randint(8, 18)

            # Generate velocity curve: ease-in, sustain, ease-out
            # Using a modified sigmoid for natural feel
            velocities = []
            for i in range(num_steps):
                t = i / (num_steps - 1)  # 0.0 to 1.0
                # Bell curve: slow start, fast middle, slow end
                # v(t) = sin(pi * t) ^ 0.7 gives natural scroll feel
                v = math.sin(math.pi * t) ** 0.7
                # Add per-step jitter (finger tremor)
                v *= self._behavior_rng.uniform(0.85, 1.15)
                velocities.append(max(0.05, v))

            # Normalize velocities so total distance matches target
            total_v = sum(velocities)

            for i, v in enumerate(velocities):
                step_distance = int((v / total_v) * distance) * direction
                if step_distance == 0:
                    step_distance = direction  # Minimum 1px

                await self.page.mouse.wheel(0, step_distance)

                # Inter-step delay: shorter at peak velocity, longer at start/end
                t = i / (num_steps - 1) if num_steps > 1 else 0.5
                base_delay = 0.015 + 0.035 * (1.0 - math.sin(math.pi * t) ** 0.5)
                delay = base_delay * self._behavior_rng.uniform(0.8, 1.3)
                await asyncio.sleep(delay)

            # 25% chance of micro-bounce (trackpad overscroll behavior)
            if self._behavior_rng.random() < 0.25:
                bounce = self._behavior_rng.randint(3, 12) * (-direction)
                await asyncio.sleep(self._behavior_rng.uniform(0.03, 0.08))
                await self.page.mouse.wheel(0, bounce)
                await asyncio.sleep(self._behavior_rng.uniform(0.05, 0.12))
                await self.page.mouse.wheel(0, -bounce // 2)  # Settle back

        except Exception:
            # Fallback to simple scroll if physics scroll fails
            try:
                await self.page.mouse.wheel(0, distance * direction)
            except Exception:
                pass

    async def natural_mouse_drift(self, duration: float = 2.0) -> None:
        """
        Generate Perlin-noise-like mouse drift for idle periods.

        More sophisticated than idle_mouse() — this creates smooth,
        continuous drift patterns that closely mimic real hand tremor
        on a mouse/trackpad while the user is reading or thinking.

        Uses layered sinusoidal motion at different frequencies
        to simulate organic hand micro-movements (poor man's Perlin noise).

        Args:
            duration: How long to drift in seconds
        """
        if not self.page:
            return

        try:
            vp = self.page.viewport_size
            if not vp:
                await asyncio.sleep(duration)
                return

            # Start from a random natural position
            cx = self._behavior_rng.randint(int(vp['width'] * 0.2), int(vp['width'] * 0.8))
            cy = self._behavior_rng.randint(int(vp['height'] * 0.25), int(vp['height'] * 0.7))

            start_time = time.time()
            step_interval = self._behavior_rng.uniform(0.04, 0.08)

            # Layered frequencies for natural-looking drift
            # Each layer has: amplitude, frequency_x, frequency_y, phase_x, phase_y
            layers = []
            for _ in range(3):
                layers.append({
                    'amp': self._behavior_rng.uniform(0.5, 3.0),
                    'fx': self._behavior_rng.uniform(0.3, 1.5),
                    'fy': self._behavior_rng.uniform(0.3, 1.5),
                    'px': self._behavior_rng.uniform(0, 2 * math.pi),
                    'py': self._behavior_rng.uniform(0, 2 * math.pi),
                })

            while time.time() - start_time < duration:
                t = time.time() - start_time

                # Sum sinusoidal layers for smooth organic drift
                dx = sum(
                    layer['amp'] * math.sin(layer['fx'] * t + layer['px'])
                    for layer in layers
                )
                dy = sum(
                    layer['amp'] * math.sin(layer['fy'] * t + layer['py'])
                    for layer in layers
                )

                # Add micro-tremor (high frequency, low amplitude)
                dx += random.gauss(0, 0.3)
                dy += random.gauss(0, 0.3)

                x = int(cx + dx)
                y = int(cy + dy)

                # Clamp to viewport
                x = max(5, min(vp['width'] - 5, x))
                y = max(5, min(vp['height'] - 5, y))

                await self.page.mouse.move(x, y)
                await asyncio.sleep(step_interval)

        except Exception:
            await asyncio.sleep(duration)

    async def random_micro_interaction(self) -> None:
        """
        Perform a small random interaction that makes the session appear
        more organic. Called periodically during long waits.

        Possible micro-actions:
        - Hover over a random link
        - Natural momentum scroll
        - Tab focus/blur cycle
        - Mouse idle movement / Perlin drift
        - Text selection/deselection
        """
        action = random.random()

        try:
            if action < 0.20:
                # Hover over a random visible link
                links = self.page.locator("a:visible")
                count = await links.count()
                if count > 0:
                    idx = random.randint(0, min(count - 1, 10))
                    link = links.nth(idx)
                    try:
                        await link.hover(timeout=2000)
                        await asyncio.sleep(random.uniform(0.3, 1.0))
                    except Exception:
                        pass

            elif action < 0.38:
                # Natural momentum scroll (physics-based)
                direction = random.choice([1, 1, -1])
                distance = random.randint(40, 180)
                await self.natural_scroll(distance=distance, direction=direction)

            elif action < 0.52:
                # Tab focus/blur cycle
                await self.random_focus_blur()
                await asyncio.sleep(random.uniform(0.5, 2.0))

            elif action < 0.68:
                # Idle mouse movement (classic)
                await self.idle_mouse(duration=random.uniform(0.5, 1.5))

            elif action < 0.82:
                # Perlin-like mouse drift (organic hand tremor)
                await self.natural_mouse_drift(duration=random.uniform(0.8, 2.0))

            else:
                # Just wait naturally
                await asyncio.sleep(random.uniform(0.5, 2.0))

        except Exception:
            # Micro-interactions should never crash the bot
            pass

    async def random_focus_blur(self) -> None:
        """
        Simulate tab switching/focus events to appear more human.

        Models realistic behavior: user switches to another tab,
        spends variable time there, then returns. Uses page-level
        visibility API events for maximum realism.
        """
        # How long user "looks at another tab"
        if self.human_profile:
            away_time = HumanProfile.get_action_delay(self.human_profile, "read") * random.uniform(0.3, 0.8)
        else:
            away_time = random.uniform(0.8, 4.0)

        away_time_ms = int(away_time * 1000)

        await self.page.evaluate(
            """(awayMs) => {
            // Simulate tab losing focus
            document.dispatchEvent(new Event('visibilitychange'));
            window.dispatchEvent(new FocusEvent('blur'));
            document.dispatchEvent(new Event('blur'));

            // After 'away' period, simulate returning
            setTimeout(() => {
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new FocusEvent('focus'));
                document.dispatchEvent(new Event('focus'));

                // Mouse re-entry (user moves cursor back into window)
                const evt = new MouseEvent('mouseenter', {
                    bubbles: true, clientX: Math.random() * window.innerWidth,
                    clientY: Math.random() * window.innerHeight
                });
                document.dispatchEvent(evt);
            }, awayMs);
        }""",
            away_time_ms
        )

        # Actually wait the away time
        await asyncio.sleep(away_time)

    async def human_wait(self, seconds: float, with_interactions: bool = True) -> None:
        """
        Wait for a specified duration while performing periodic human-like
        micro-interactions to maintain session liveness.

        Use this instead of bare asyncio.sleep() for long waits (>5s)
        to prevent inactivity detection.

        Args:
            seconds: Total time to wait
            with_interactions: Whether to perform micro-interactions during wait
        """
        if not with_interactions or seconds < 3:
            await asyncio.sleep(seconds)
            return

        start = time.time()
        while time.time() - start < seconds:
            remaining = seconds - (time.time() - start)
            if remaining <= 0:
                break

            # Wait a chunk, then do a micro-interaction
            chunk = min(remaining, random.uniform(8, 25))
            await asyncio.sleep(chunk)

            remaining = seconds - (time.time() - start)
            if remaining > 2 and with_interactions:
                try:
                    await self.random_micro_interaction()
                except Exception:
                    pass

    async def handle_cloudflare(self, max_wait_seconds: int = 60) -> bool:
        """
        Detects and waits for Cloudflare challenges including:
        - 'Just a moment' interstitial
        - Turnstile CAPTCHA challenges
        - Waiting room queues
        - DDoS protection pages

        Args:
            max_wait_seconds: Maximum time to wait for challenge resolution

        Returns:
            True if challenge resolved, False if stuck/timed out
        """
        cloudflare_indicators = [
            "just a moment",
            "cloudflare",
            "checking your browser",
            "please wait",
            "ddos protection",
            "security check"
        ]

        cloudflare_selectors = [
            "#cf-challenge-running",
            ".cf-turnstile",
            "[id*='cf-turnstile']",
            "#challenge-running",
            ".challenge-body",
            "#trk_jschal_js"
        ]

        start_time = time.time()
        checks = 0
        consecutive_no_cf = 0  # Track consecutive checks with no CF detected
        turnstile_error_detected = False  # Track if Turnstile is broken

        while (time.time() - start_time) < max_wait_seconds:
            checks += 1

            try:
                # Check for page crash/unresponsiveness
                if not await self.detect_page_crash():
                    logger.warning(
                        f"[{self.faucet_name}] Page unresponsive"
                        " during CF check. Refreshing..."
                    )
                    await self.page.reload()
                    await asyncio.sleep(5)
                    continue

                # Check for broken Turnstile (sitekey misconfiguration)
                # If Turnstile JavaScript threw an error, it won't complete - exit early
                if checks == 2 and not turnstile_error_detected:
                    try:
                        # Check page for signs of broken Turnstile
                        turnstile_broken = await self.page.evaluate('''() => {
                            // Check if Turnstile iframe failed to load properly
                            const iframes = document.querySelectorAll(
                                'iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]'
                            );
                            for (const iframe of iframes) {
                                // Empty iframe or error state
                                if (!iframe.contentDocument && iframe.style.display !== 'none') {
                                    return true;
                                }
                            }
                            // Check for Turnstile error messages in page
                            const pageText = document.body?.innerText || '';
                            if (pageText.includes('TurnstileError') || pageText.includes('Invalid sitekey')) {
                                return true;
                            }
                            return false;
                        }''')
                        if turnstile_broken:
                            turnstile_error_detected = True
                            logger.warning(
                                f"[{self.faucet_name}] ⚠️ Broken Turnstile detected"
                                f" (sitekey error). Site misconfigured.")
                    except Exception:
                        pass  # Evaluation failed, continue normal flow

                # If Turnstile is broken, wait max 10s then proceed (site issue, not ours)
                if turnstile_error_detected and (time.time() - start_time) > 10:
                    logger.info(
                        f"[{self.faucet_name}] Proceeding"
                        " despite broken Turnstile"
                        " (site misconfiguration)"
                    )
                    return True

                # Check page title for Cloudflare indicators
                title = (await self.page.title()).lower()
                title_detected = any(indicator in title for indicator in cloudflare_indicators)

                # Check page content for challenge elements
                element_detected = False
                for selector in cloudflare_selectors:
                    try:
                        locator = self.page.locator(selector)
                        if await locator.is_visible(timeout=500):
                            element_detected = True

                            # INTERACTION: Try to click Turnstile checkbox if visible
                            if "turnstile" in selector:
                                try:
                                    # Find the checkbox iframe or element
                                    # Turnstile usually has a checkbox in an iframe
                                    if await locator.count() > 0:
                                        # Random delay and movement before interaction
                                        await self.idle_mouse(random.uniform(0.5, 1.5))
                                        # Use human_like_click on the locator
                                        await self.human_like_click(locator)
                                        logger.info(f"[{self.faucet_name}] 🖱️ Clicked Turnstile checkbox")
                                except Exception as click_err:
                                    logger.debug(f"Failed to click Turnstile: {click_err}")

                            break
                    except Exception:
                        continue

                # Early exit if no CF detected for multiple consecutive checks
                if not title_detected and not element_detected:
                    consecutive_no_cf += 1
                    if consecutive_no_cf >= 3:  # 3 checks * 2s sleep = 6s of no CF
                        logger.debug(f"[{self.faucet_name}] No Cloudflare detected for 6s, proceeding")
                        return True
                else:
                    consecutive_no_cf = 0  # Reset counter if CF found

                if title_detected or element_detected:
                    if checks == 1:
                        logger.info(
                            f"[{self.faucet_name}]"
                            " Cloudflare/Turnstile challenge"
                            " detected, waiting..."
                        )

                    # Simulate human-like behavior while waiting
                    await asyncio.sleep(random.uniform(2.0, 4.0))

                    # Occasionally move mouse or scroll to appear active
                    if checks % 3 == 0:
                        try:
                            if random.random() < 0.5:
                                await self.idle_mouse(0.8)
                            else:
                                await self.simulate_reading(1.0)
                        except Exception:
                            pass
                else:
                    # Challenge appears resolved
                    if checks > 1:
                        elapsed = time.time() - start_time
                        logger.info(f"[{self.faucet_name}] ✅ Cloudflare challenge resolved in {elapsed:.1f}s")
                    return True

            except Exception as e:
                # Page might have crashed or navigated
                logger.warning(f"[{self.faucet_name}] Cloudflare check error (recoverable): {e}")
                await asyncio.sleep(2)

        logger.error(f"[{self.faucet_name}] ❌ Cloudflare challenge timed out after {max_wait_seconds}s")
        return False

    async def detect_page_crash(self) -> bool:
        """
        Detect if the page has crashed or become unresponsive.

        Returns:
            True if page appears healthy, False if crashed/unresponsive
        """
        try:
            # Try a simple evaluation to check page responsiveness
            await asyncio.wait_for(
                self.page.evaluate("() => document.readyState"),
                timeout=5.0
            )
            return True
        except asyncio.TimeoutError:
            logger.error(f"[{self.faucet_name}] Page appears unresponsive (timeout)")
            return False
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Page crash detected: {e}")
            return False

    async def safe_navigate(
        self,
        url: str,
        wait_until: str = "commit",
        timeout: Optional[int] = None,
        retry_on_proxy_error: bool = True,
    ) -> bool:
        """Navigate to URL with proxy error handling and retry logic.

        Handles common navigation failures including:

        * ``NS_ERROR_PROXY_CONNECTION_REFUSED`` (bad proxy).
        * Timeout errors.
        * Network errors.

        Args:
            url: Target URL to navigate to.
            wait_until: Playwright wait strategy
                (domcontentloaded, networkidle, load, commit).
            timeout: Navigation timeout in ms (uses
                ``settings.timeout`` if ``None``).
            retry_on_proxy_error: If ``True``, retries on proxy
                failures.

        Returns:
            ``True`` if navigation succeeded, ``False`` otherwise.
        """
        if timeout is None:
            timeout = getattr(self.settings, "timeout", 60000)

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                # On retry, halve timeout but keep >= 60s
                attempt_timeout = (
                    timeout if attempt == 1
                    else max(timeout // 2, 60000)
                )
                logger.debug(
                    f"[{self.faucet_name}] Navigating to {url}"
                    f" (attempt {attempt}/{max_attempts},"
                    f" timeout={attempt_timeout}ms)"
                )
                await self.page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=attempt_timeout,
                )
                logger.debug(
                    f"[{self.faucet_name}] Navigation succeeded"
                )
                return True

            except Exception as e:
                error_str = str(e)

                # Check for proxy-related errors
                is_proxy_error = any(
                    proxy_err in error_str for proxy_err in [
                        "NS_ERROR_PROXY_CONNECTION_REFUSED",
                        "PROXY_CONNECTION_FAILED",
                        "ERR_PROXY_CONNECTION_FAILED",
                        "ECONNREFUSED",
                        "proxy",
                    ]
                ) or (
                    "Timeout" in error_str and attempt == 1
                )

                if is_proxy_error:
                    logger.warning(
                        f"[{self.faucet_name}] Proxy/connection"
                        f" error on attempt {attempt}:"
                        f" {error_str[:120]}"
                    )
                    if attempt == max_attempts:
                        logger.warning(
                            f"[{self.faucet_name}] All proxy"
                            " attempts failed, proxy may be"
                            " blocking this site"
                        )
                        return False
                    wait_time = min(attempt * 2, 5)
                    await asyncio.sleep(wait_time)
                    continue

                if "Timeout" in error_str or "timeout" in error_str:
                    logger.warning(
                        f"[{self.faucet_name}] Timeout on"
                        f" attempt {attempt}:"
                        f" {error_str[:120]}"
                    )
                    if attempt < max_attempts:
                        timeout = min(timeout + 30000, 150000)
                        logger.info(
                            f"[{self.faucet_name}] Extending"
                            f" timeout to {timeout}ms for retry"
                        )
                        await asyncio.sleep(1)
                        continue
                    logger.error(
                        f"[{self.faucet_name}] Navigation failed"
                        f" after {max_attempts} timeout attempts"
                    )
                    return False

                # Other errors - don't retry
                logger.error(
                    f"[{self.faucet_name}] Navigation error:"
                    f" {error_str[:120]}"
                )
                return False

        # If we get here, all attempts failed (shouldn't reach this)
        return False

    async def close_popups(self) -> None:
        """Dismiss common crypto-site popups and cookie-consent banners.

        Iterates over a built-in list of CSS selectors for cookie
        consent, notification permission, Bootstrap modals, and
        Google consent dialogs.  Each visible match is clicked with a
        short timeout; failures are silently ignored.
        """
        selectors = [
            ".cc-btn.cc-dismiss",         # Cookie Consent
            ".pushpad_deny_button",       # Notification Permission
            ".close-reveal-modal",        # Reveal Modals
            "div[title='Close']",         # Generic Title-based close
            "#multitab_comm_close",       # Common in Freebitco.in
            ".modal-header .close",       # Bootstrap modals
            "button:has-text('Accept All')",
            "button:has-text('Got it!')",
            ".fc-cta-consent"             # Google Consent
        ]

        if not self.page:
            return

        for sel in selectors:
            try:
                el = self.page.locator(sel)
                if await el.count() > 0 and await el.first.is_visible():
                    logger.debug(f"[{self.faucet_name}] Closing popup: {sel}")
                    await el.first.click(timeout=1000)
                    await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                continue  # Expected for popups that don't exist
            except Exception as e:
                logger.debug(f"[{self.faucet_name}] Popup close failed for {sel}: {e}")
                continue

    async def login(self) -> bool:
        """Authenticate with the faucet site.

        Subclasses **must** override this method with site-specific
        login logic (navigate to login page, fill credentials, solve
        CAPTCHA, verify success).

        Returns:
            ``True`` if login succeeded, ``False`` otherwise.

        Raises:
            NotImplementedError: Always, in the base class.
        """
        raise NotImplementedError

    async def claim(self) -> Union[bool, ClaimResult]:
        """Execute the faucet claim action.

        Subclasses **must** override this with site-specific claim
        logic (navigate to claim page, solve CAPTCHA, click claim
        button, parse result).

        Returns:
            A :class:`ClaimResult` (preferred) or a bare ``bool``.

        Raises:
            NotImplementedError: Always, in the base class.
        """
        raise NotImplementedError

    async def get_timer(self, selector: str, fallback_selectors: Optional[List[str]] = None) -> float:
        """Extract the countdown timer from the page and convert to minutes.

        Tries the primary *selector* first; if invisible or absent, tries
        each entry in *fallback_selectors*; finally falls back to
        :meth:`DataExtractor.find_timer_selector_in_dom` for automatic
        discovery.

        Args:
            selector: Primary CSS selector for the timer element.
            fallback_selectors: Optional list of alternative selectors.

        Returns:
            Remaining wait time in **minutes**, or ``0.0`` if the timer
            could not be found (claim assumed ready).
        """
        # Structured logging: timer_check start
        logger.debug(
            f"[LIFECYCLE] timer_check_start"
            f" | faucet={self.faucet_name}"
            f" | selector={selector}"
            f" | timestamp={time.time():.0f}"
        )

        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                logger.debug(
                    f"[{self.faucet_name}] Timer extracted"
                    f" from {selector}: {text}"
                )
                minutes = DataExtractor.parse_timer_to_minutes(text)
                # Structured logging: timer_check success
                logger.info(
                    f"[LIFECYCLE] timer_check"
                    f" | faucet={self.faucet_name}"
                    f" | timer_minutes={minutes}"
                    f" | timer_raw={text}"
                    f" | success=true"
                    f" | timestamp={time.time():.0f}"
                )
                return minutes
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Timer extraction failed for {selector}: {e}")

        # Try fallback selectors
        if fallback_selectors:
            for fb_sel in fallback_selectors:
                try:
                    el = self.page.locator(fb_sel)
                    if await el.count() > 0 and await el.first.is_visible():
                        text = await el.first.text_content()
                        logger.info(f"[{self.faucet_name}] Timer extracted from fallback {fb_sel}: {text}")
                        return DataExtractor.parse_timer_to_minutes(text)
                except Exception:
                    continue

        # Auto-detect from DOM
        try:
            auto_sel = await DataExtractor.find_timer_selector_in_dom(self.page)
            if auto_sel:
                el = self.page.locator(auto_sel)
                text = await el.first.text_content()
                logger.warning(f"[{self.faucet_name}] Timer auto-detected from DOM: {auto_sel} = {text}")
                return DataExtractor.parse_timer_to_minutes(text)
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Auto-detection failed: {e}")

        # Structured logging: timer_check failed
        logger.warning(
            f"[LIFECYCLE] timer_check"
            f" | faucet={self.faucet_name}"
            f" | success=false"
            f" | timestamp={time.time():.0f}"
        )
        logger.warning(
            f"[{self.faucet_name}] Could not extract timer"
            f" from {selector} or fallbacks"
        )
        return 0.0

    async def get_balance(
        self,
        selector: str,
        fallback_selectors: Optional[List[str]] = None,
    ) -> str:
        """Extract the account balance from the page.

        Tries the primary *selector*; if invisible or absent, tries
        each entry in *fallback_selectors*; finally falls back to
        :meth:`DataExtractor.find_balance_selector_in_dom` for
        automatic discovery.

        Args:
            selector: Primary CSS selector for the balance element.
            fallback_selectors: Optional list of alternative selectors.

        Returns:
            Balance as a string, or ``"0"`` if extraction failed.
        """
        # Structured logging: balance_check start
        logger.debug(
            f"[LIFECYCLE] balance_check_start"
            f" | faucet={self.faucet_name}"
            f" | selector={selector}"
            f" | timestamp={time.time():.0f}"
        )

        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                logger.debug(
                    f"[{self.faucet_name}] Balance extracted"
                    f" from {selector}: {text}"
                )
                balance = DataExtractor.extract_balance(text)
                # Structured logging: balance_check success
                logger.info(
                    f"[LIFECYCLE] balance_check"
                    f" | faucet={self.faucet_name}"
                    f" | balance={balance}"
                    f" | success=true"
                    f" | timestamp={time.time():.0f}"
                )
                return balance
        except Exception as e:
            logger.debug(
                f"[{self.faucet_name}] Balance extraction"
                f" failed for {selector}: {e}"
            )

        # Try fallback selectors
        if fallback_selectors:
            for fb_sel in fallback_selectors:
                try:
                    el = self.page.locator(fb_sel)
                    if await el.count() > 0 and await el.first.is_visible():
                        text = await el.first.text_content()
                        logger.info(
                            f"[{self.faucet_name}] Balance"
                            f" extracted from fallback"
                            f" {fb_sel}: {text}"
                        )
                        return DataExtractor.extract_balance(text)
                except Exception:
                    continue

        # Auto-detect from DOM
        try:
            auto_sel = await DataExtractor.find_balance_selector_in_dom(self.page)
            if auto_sel:
                el = self.page.locator(auto_sel)
                text = await el.first.text_content()
                logger.warning(
                    f"[{self.faucet_name}] Balance"
                    f" auto-detected from DOM:"
                    f" {auto_sel} = {text}"
                )
                return DataExtractor.extract_balance(text)
        except Exception as e:
            logger.debug(
                f"[{self.faucet_name}] Auto-detection"
                f" failed: {e}"
            )

        # Structured logging: balance_check failed
        logger.warning(
            f"[LIFECYCLE] balance_check"
            f" | faucet={self.faucet_name}"
            f" | success=false"
            f" | timestamp={time.time():.0f}"
        )
        logger.warning(
            f"[{self.faucet_name}] Could not extract balance"
            f" from {selector} or fallbacks"
        )
        return "0"

    async def is_logged_in(self) -> bool:
        """
        Check if the session is still active.

        Subclasses should override with site-specific indicators
        (e.g. presence of a logout button, dashboard elements).

        Returns:
            ``True`` if logged in, ``False`` otherwise.
        """
        return False

    async def check_failure_states(self) -> Optional[str]:
        """Detect common failure conditions on the current page.

        Inspects page content, URL, and title for patterns indicating:

        * **Cloudflare challenge** -- interstitial, Turnstile, DDoS page.
        * **Proxy / VPN detection** -- "proxy detected", "vpn detected".
        * **Account ban / suspension**.
        * **Site maintenance**.
        * **HTTP error pages** (403, 404, 500).

        Returns:
            A human-readable failure description string if a problem is
            detected, or ``None`` when the page appears healthy.
        """
        content = (await self.page.content()).lower()
        url = self.page.url.lower()
        title = (await self.page.title()).lower()

        # First check if we're on an actual Cloudflare challenge page (not just site mentioning CF)
        # True Cloudflare challenges have specific indicators
        cf_challenge_indicators = [
            "checking your browser",
            "just a moment",
            "please wait while we verify",
            "verify you are human",
            "enable javascript and cookies to continue",
            "ray id:",  # Cloudflare ray ID on challenge pages
            "cf-browser-verification",
            "cf-challenge-running",
        ]

        # Check title for CF challenge
        if any(indicator in title for indicator in ["just a moment",
               "cloudflare", "ddos protection", "attention required"]):
            logger.info(f"[{self.faucet_name}] Cloudflare challenge detected in title: {title}")
            return "Site Maintenance / Blocked"

        # Check for ACTIVE Cloudflare challenge elements (not just mentions in scripts)
        try:
            cf_challenge_element = await self.page.locator(
                "#cf-challenge-running, .cf-browser-verification, #challenge-running"
            ).count()
            if cf_challenge_element > 0:
                logger.info(f"[{self.faucet_name}] Cloudflare challenge element detected")
                return "Site Maintenance / Blocked"
        except Exception:
            pass

        # Only treat as CF block if challenge indicators are in visible text, not scripts
        try:
            visible_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            for indicator in cf_challenge_indicators:
                if indicator in visible_text:
                    logger.info(
                        f"[{self.faucet_name}] Cloudflare"
                        " challenge pattern in visible"
                        f" text: '{indicator}'"
                    )
                    return "Site Maintenance / Blocked"
        except Exception:
            pass

        # Proxy/VPN Detection Patterns
        proxy_patterns = [
            "proxy detected",
            "vpn detected",
            "suspicious activity",
            "datacenter ip",
            "hosting provider",
            "please disable your proxy",
            "please disable your vpn",
            "access denied",
            "forbidden",
            "your ip has been flagged",
            "unusual traffic"
        ]

        for pattern in proxy_patterns:
            if pattern in content:
                logger.warning(f"[{self.faucet_name}] Proxy detection pattern found: '{pattern}'")
                return "Proxy Detected"

        # Account Ban/Suspension Patterns
        ban_patterns = [
            "account banned",
            "account suspended",
            "account disabled",
            "account locked",
            "permanently banned",
            "violation of terms"
        ]

        for pattern in ban_patterns:
            if pattern in content:
                logger.error(f"[{self.faucet_name}] Account ban pattern found: '{pattern}'")
                return "Account Banned"

        # Site Maintenance Patterns (excluding 'cloudflare' as it's too broad)
        maintenance_patterns = [
            "maintenance",
            "under maintenance",
            "temporarily unavailable",
            "ddos protection by",  # More specific - actual block message
            "security check required",
        ]

        for pattern in maintenance_patterns:
            if pattern in content:
                logger.info(f"[{self.faucet_name}] Maintenance/security pattern found: '{pattern}'")
                return "Site Maintenance / Blocked"

        # Check for error pages in URL
        if any(err in url for err in ["error", "403", "404", "500", "banned"]):
            logger.warning(f"[{self.faucet_name}] Error page detected in URL: {url}")
            return "Error Page"

        return None

    async def login_wrapper(self) -> bool:
        """High-level login orchestrator with anti-detection warmup.

        1. Loads the human timing profile (if not already assigned).
        2. Handles Cloudflare challenges pre-emptively.
        3. Warms up the page (:meth:`warm_up_page`).
        4. Checks for failure states (proxy detection, bans, maintenance).
        5. Verifies existing session via :meth:`is_logged_in`.
        6. Calls :meth:`login` if needed, with a single retry.

        Returns:
            ``True`` if authenticated (existing or new session).
        """
        # Load human profile if not already loaded
        if self.human_profile is None:
            # Get account credentials to derive profile name
            creds = self.get_credentials(self.faucet_name)
            if creds and creds.get('username'):
                profile_name = creds['username']
                self.load_human_profile(profile_name)
            else:
                # Fallback to faucet name as profile identifier
                self.load_human_profile(self.faucet_name)

        # Structured logging: login_start
        creds = self.get_credentials(self.faucet_name)
        account = creds.get('username', 'unknown') if creds else 'unknown'
        logger.info(
            f"[LIFECYCLE] login_start"
            f" | faucet={self.faucet_name}"
            f" | account={account}"
            f" | timestamp={time.time():.0f}"
        )

        # Attempt to clear Cloudflare/turnstile before failure checks
        try:
            await self.handle_cloudflare(max_wait_seconds=30)
        except Exception:
            pass

        # Warm up the page to establish behavioral baseline before any actions
        await self.warm_up_page()

        # Brief organic mouse drift before login interaction (~40%)
        if random.random() < 0.4:
            await self.natural_mouse_drift(duration=random.uniform(0.5, 1.2))

        self.last_error_type = None
        failure = await self.check_failure_states()
        if failure:
            # Retry once after reload in case we hit a transient challenge page
            if failure in {"Proxy Detected", "Site Maintenance / Blocked"}:
                try:
                    await self.page.reload()
                    await self.handle_cloudflare(max_wait_seconds=30)
                except Exception:
                    pass
                failure = await self.check_failure_states()

        if failure:
            error_type = None
            failure_lower = failure.lower()
            if "proxy" in failure_lower or "blocked" in failure_lower:
                error_type = ErrorType.PROXY_ISSUE
            elif "maintenance" in failure_lower or "cloudflare" in failure_lower:
                error_type = ErrorType.RATE_LIMIT
            elif "banned" in failure_lower or "suspended" in failure_lower:
                error_type = ErrorType.PERMANENT

            self.last_error_type = error_type
            logger.error(f"[{self.faucet_name}] Failure state detected: {failure}")
            return False

        if await self.is_logged_in():
            # Structured logging: login_success (already logged in)
            logger.info(
                f"[LIFECYCLE] login_success"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | already_logged_in=true"
                f" | timestamp={time.time():.0f}"
            )
            return True

        logged_in = await self.login()
        if not logged_in:
            # Retry once for transient failures (slow proxies, CF challenges, DOM not ready)
            try:
                await self.page.reload()
                await self.handle_cloudflare(max_wait_seconds=45)
                await self.close_popups()
            except Exception:
                pass

            retry_failure = await self.check_failure_states()
            if not retry_failure:
                try:
                    logged_in = await self.login()
                except Exception:
                    logged_in = False

            if not logged_in:
                try:
                    page_content = await self.page.content()
                except Exception:
                    page_content = None
                try:
                    self.last_error_type = self.classify_error(None, page_content, None)
                except Exception:
                    self.last_error_type = None

                # Structured logging: login_failed
                err_type_val = (
                    self.last_error_type.value
                    if self.last_error_type else 'unknown'
                )
                logger.warning(
                    f"[LIFECYCLE] login_failed"
                    f" | faucet={self.faucet_name}"
                    f" | account={account}"
                    f" | error_type={err_type_val}"
                    f" | timestamp={time.time():.0f}"
                )
        else:
            # Structured logging: login_success
            logger.info(
                f"[LIFECYCLE] login_success"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | timestamp={time.time():.0f}"
            )

        return logged_in

    async def view_ptc_ads(self) -> None:
        """View Paid-to-Click advertisements for bonus earnings.

        Subclasses that support PTC (e.g. CoinPayU, AdBTC) should
        override to implement ad-link discovery, tab management,
        timer waiting, and optional CAPTCHA solving.
        """
        logger.warning(f"[{self.faucet_name}] PTC logic not fully implemented in subclass.")
        await self.human_wait(1)

    def get_earning_tasks(self) -> List[Dict[str, Any]]:
        """Return the ordered list of earning tasks for this faucet.

        Each entry is a dict with:

        * ``func`` -- an async callable to execute.
        * ``name`` -- human-readable task label.

        By default includes ``Faucet Claim`` and, for PTC-capable
        faucets, ``PTC Ads``.

        Returns:
            List of task dicts.
        """
        tasks = []
        # Claim is usually the primary task
        tasks.append({"func": self.claim, "name": "Faucet Claim"})

        # Add PTC if the subclass actually overrides view_ptc_ads
        if type(self).view_ptc_ads is not FaucetBot.view_ptc_ads:
            tasks.append({"func": self.view_ptc_ads, "name": "PTC Ads"})

        return tasks

    async def withdraw(self) -> ClaimResult:
        """Execute a withdrawal from the faucet.

        Subclasses should override with site-specific navigation and
        form submission.  The base implementation returns a
        "Not Implemented" failure result.

        Returns:
            :class:`ClaimResult` indicating success/failure.
        """
        logger.warning(f"[{self.faucet_name}] Withdrawal not implemented for this faucet.")
        return ClaimResult(success=False, status="Not Implemented", next_claim_minutes=1440)

    def get_jobs(self) -> List[Any]:
        """Build :class:`Job` objects for the scheduler.

        Creates three jobs per faucet:

        1. **Claim** (priority 1) -- runs immediately.
        2. **Withdraw** (priority 5) -- runs after 1 hour, then daily.
        3. **PTC** (priority 3) -- runs after 5 min if PTC is available.

        Returns:
            List of :class:`core.orchestrator.Job` instances.
        """
        from core.orchestrator import Job

        jobs = []
        f_type = self.faucet_name.lower().replace(" ", "_")

        # 1. Primary claim job - highest priority
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper"
        ))

        # 2. Withdrawal job - scheduled once per day
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
            job_type="withdraw_wrapper"
        ))

        # 3. PTC job if the subclass actually implements PTC
        if type(self).view_ptc_ads is not FaucetBot.view_ptc_ads:
            jobs.append(Job(
                priority=3,
                next_run=time.time() + 300,
                name=f"{self.faucet_name} PTC",
                profile=None,
                faucet_type=f_type,
                job_type="ptc_wrapper"
            ))

        return jobs

    async def withdraw_wrapper(self, page: Page) -> ClaimResult:
        """Scheduler entry-point for withdrawal jobs.

        Handles the full withdrawal lifecycle:

        1. Ensure authentication via :meth:`login_wrapper`.
        2. Check balance against the configured minimum threshold.
        3. Call :meth:`withdraw` (site-specific).
        4. Record withdrawal analytics.

        Args:
            page: Playwright ``Page`` assigned by the scheduler.

        Returns:
            :class:`ClaimResult` with withdrawal outcome.
        """
        from core.withdrawal_analytics import get_analytics

        self.page = page

        # 1. Ensure logged in
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)

        # 2. Check balance against threshold
        current_balance = await self.get_balance(
            getattr(self, 'balance_selector', '.balance')
        )
        balance_before = 0.0
        try:
            balance_before = float(current_balance.replace(',', ''))
            threshold = getattr(
                self.settings,
                f"{self.faucet_name.lower()}_min_withdraw",
                1000,
            )
            if balance_before < threshold:
                logger.info(
                    f"[{self.faucet_name}] Balance"
                    f" {balance_before} below threshold"
                    f" {threshold}. Skipping."
                )
                return ClaimResult(
                    success=True,
                    status="Below Threshold",
                    next_claim_minutes=1440,
                )
        except (ValueError, AttributeError) as e:
            logger.debug(
                f"[{self.faucet_name}] Balance parsing"
                f" failed: {e}. Proceeding with withdrawal."
            )
            # Continue if parsing fails

        # 3. Execute withdrawal
        result = await self.withdraw()

        # 4. Track withdrawal in analytics (if successful)
        if result.success:
            try:
                # Get balance after withdrawal
                balance_after_str = (
                    result.balance if result.balance != "0"
                    else await self.get_balance(
                        getattr(self, 'balance_selector', '.balance')
                    )
                )
                balance_after = 0.0
                try:
                    balance_after = float(balance_after_str.replace(',', ''))
                except (ValueError, AttributeError):
                    balance_after = 0.0

                # Calculate withdrawn amount
                if result.amount != "0":
                    amount_withdrawn = float(
                        result.amount.replace(',', '')
                    )
                else:
                    amount_withdrawn = balance_before - balance_after

                # Determine cryptocurrency from faucet name or settings
                crypto = self._get_cryptocurrency_for_faucet()

                # Record withdrawal (fees are typically platform-side for faucets)
                analytics = get_analytics()
                analytics.record_withdrawal(
                    faucet=self.faucet_name,
                    cryptocurrency=crypto,
                    amount=amount_withdrawn,
                    network_fee=0.0,  # Most faucets don't charge network fees
                    platform_fee=0.0,  # Can be updated by subclass if known
                    withdrawal_method="faucetpay" if self.settings.use_faucetpay else "direct",
                    status="success",
                    balance_before=balance_before,
                    balance_after=balance_after,
                    notes=result.status
                )
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Failed to record withdrawal analytics: {e}")

        return result

    # Mapping of name substrings to cryptocurrency codes
    _CRYPTO_NAME_MAP: Dict[str, str] = {
        "btc": "BTC", "bitcoin": "BTC",
        "ltc": "LTC", "lite": "LTC",
        "doge": "DOGE",
        "trx": "TRX", "tron": "TRX",
        "eth": "ETH",
        "bnb": "BNB",
        "sol": "SOL",
        "ton": "TON",
        "matic": "MATIC", "polygon": "MATIC",
        "dash": "DASH",
        "bch": "BCH",
        "usdt": "USDT", "usd": "USDT",
    }

    def _get_cryptocurrency_for_faucet(self) -> str:
        """
        Determine the cryptocurrency for this faucet.
        Subclasses can override this method.
        """
        name_lower = self.faucet_name.lower()
        for keyword, symbol in self._CRYPTO_NAME_MAP.items():
            if keyword in name_lower:
                return symbol
        return "UNKNOWN"

    async def claim_wrapper(self, page: Page) -> ClaimResult:
        """Scheduler entry-point for claim jobs.

        Orchestrates the full faucet-claim lifecycle:

        1. Authenticate via :meth:`login_wrapper`.
        2. Warm up the page and inject organic mouse / scroll events.
        3. Call :meth:`claim` (site-specific).
        4. Classify errors and record analytics.

        All steps are wrapped in structured lifecycle logging for
        observability.

        Args:
            page: Playwright ``Page`` assigned by the scheduler.

        Returns:
            :class:`ClaimResult` with claim outcome.
        """
        self.page = page
        page_content = None
        status_code = None

        # Get account and proxy info for logging
        creds = self.get_credentials(self.faucet_name)
        account = (
            creds.get('username', 'unknown') if creds
            else 'unknown'
        )
        ctx = getattr(self.page, 'context', None)
        proxy = getattr(
            ctx, '_proxy', {}
        ).get('server', 'none')

        # Structured logging: claim_submit_start
        logger.info(
            f"[LIFECYCLE] claim_submit_start"
            f" | faucet={self.faucet_name}"
            f" | account={account}"
            f" | proxy={proxy}"
            f" | timestamp={time.time():.0f}"
        )

        try:
            await self.think_pause("pre_login")
            # Ensure logged in with new wrapper
            if not await self.login_wrapper():
                # Try to get page content for error classification
                try:
                    page_content = await page.content()
                except Exception:
                    pass

                # Classify login failure
                error_type = (
                    self.last_error_type
                    or self.classify_error(
                        None, page_content, status_code
                    )
                )
                err_val = (
                    error_type.value if error_type
                    else 'unknown'
                )
                # Structured logging: claim_submit_failed
                logger.warning(
                    f"[LIFECYCLE] claim_submit_failed"
                    f" | faucet={self.faucet_name}"
                    f" | account={account}"
                    f" | reason=login_failed"
                    f" | error_type={err_val}"
                    f" | timestamp={time.time():.0f}"
                )
                return ClaimResult(
                    success=False,
                    status="Login/Access Failed",
                    next_claim_minutes=30,
                    error_type=error_type
                ).validate(self.faucet_name)

            await self.think_pause("pre_claim")

            # Simulate natural tab switching behavior (~40% of the time)
            if random.random() < 0.4:
                await self.simulate_tab_activity()

            # Warm up the page again before claim action (may have navigated)
            await self.warm_up_page()

            # Natural scroll to orient on page before claiming (~60%)
            if random.random() < 0.6:
                await self.natural_scroll(
                    distance=random.randint(80, 250),
                    direction=random.choice([1, 1, -1])
                )
                await asyncio.sleep(random.uniform(0.3, 1.0))

            # Brief organic mouse drift before clicking claim (~30%)
            if random.random() < 0.3:
                await self.natural_mouse_drift(duration=random.uniform(0.5, 1.5))

            # Structured logging: claim_submit (executing)
            logger.info(
                f"[LIFECYCLE] claim_submit"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | timestamp={time.time():.0f}"
            )
            result = await self.claim()

            # Handle cases where claim() might return a boolean (legacy)
            if isinstance(result, bool):
                result = ClaimResult(success=result, status="Claimed" if result else "Failed")

            # Validate ClaimResult before proceeding
            result.validate(self.faucet_name)

            # Structured logging: claim_verify
            logger.info(
                f"[LIFECYCLE] claim_verify"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | success={result.success}"
                f" | status={result.status[:50]}"
                f" | timestamp={time.time():.0f}"
            )

            # If claim failed and no error_type was set, try to classify the error
            if not result.success and result.error_type is None:
                try:
                    page_content = await page.content()
                except Exception:
                    page_content = None

                result.error_type = self.classify_error(
                    None, page_content, status_code
                )
                logger.info(
                    f"[{self.faucet_name}] Claim failed"
                    f" - classified as"
                    f" {result.error_type.value}"
                )

            # Record analytics for the claim
            await self._record_analytics(result)

            # Structured logging: result_record
            err_type_str = (
                result.error_type.value
                if result.error_type else 'none'
            )
            logger.info(
                f"[LIFECYCLE] result_record"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | success={result.success}"
                f" | amount={result.amount}"
                f" | balance={result.balance}"
                f" | next_claim_min={result.next_claim_minutes}"
                f" | error_type={err_type_str}"
                f" | timestamp={time.time():.0f}"
            )

            return result

        except Exception as e:
            # Classify exception-based errors
            try:
                page_content = await page.content()
            except Exception:
                page_content = None

            error_type = self.classify_error(e, page_content, status_code)
            logger.error(
                f"[{self.faucet_name}] Exception in"
                f" claim_wrapper: {e}"
                f" (classified as {error_type.value})"
            )

            # Structured logging: result_record (exception)
            logger.error(
                f"[LIFECYCLE] result_record"
                f" | faucet={self.faucet_name}"
                f" | account={account}"
                f" | success=false"
                f" | exception={str(e)[:100]}"
                f" | error_type={error_type.value}"
                f" | timestamp={time.time():.0f}"
            )

            return ClaimResult(
                success=False,
                status=f"Exception: {str(e)[:100]}",
                next_claim_minutes=15,
                error_type=error_type
            )

    async def ptc_wrapper(self, page: Page) -> ClaimResult:
        """Scheduler entry-point for PTC (Paid-to-Click) ad jobs.

        Authenticates and then delegates to :meth:`view_ptc_ads`.

        Args:
            page: Playwright ``Page`` assigned by the scheduler.

        Returns:
            :class:`ClaimResult` -- always ``success=True`` unless login
            fails.
        """
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)

        await self.view_ptc_ads()
        return ClaimResult(success=True, status="PTC Done",
                           next_claim_minutes=self.settings.exploration_frequency_minutes)

    async def _record_analytics(self, result: ClaimResult) -> None:
        """Helper to record analytics for a result with enhanced validation."""
        try:
            tracker = get_tracker()

            # Extract amount from ClaimResult
            raw_amount = result.amount or ""
            amount_str = DataExtractor.extract_balance(str(raw_amount))

            # Fallback: try extracting from status message if amount is empty
            if (not amount_str or amount_str == "0") and result.status:
                amount_str = DataExtractor.extract_balance(result.status)

            # Convert to float with validation
            amount_val = 0.0
            try:
                amount_val = float(amount_str) if amount_str else 0.0
            except (ValueError, TypeError) as e:
                logger.warning(f"[{self.faucet_name}] Failed to parse amount '{amount_str}': {e}")
                amount_val = 0.0

            # Determine currency
            currency = getattr(self, 'coin', None) or self._get_cryptocurrency_for_faucet()
            if not currency or currency == "UNKNOWN":
                detected = self._detect_currency_from_text(f"{raw_amount} {result.status or ''} {result.balance or ''}")
                if detected:
                    currency = detected

            # Normalize amount to smallest unit (satoshi, wei, etc.)
            amount = self._normalize_claim_amount(amount_val, raw_amount, currency)

            # Extract balance_after from ClaimResult
            raw_balance = result.balance or ""
            balance_str = DataExtractor.extract_balance(str(raw_balance))

            # Convert to float with validation
            balance_after = 0.0
            try:
                balance_after = float(balance_str) if balance_str else 0.0
            except (ValueError, TypeError) as e:
                logger.warning(f"[{self.faucet_name}] Failed to parse balance '{balance_str}': {e}")
                balance_after = 0.0

            # Normalize balance to smallest unit
            balance_after = self._normalize_claim_amount(balance_after, raw_balance, currency)

            # Log extracted values for debugging
            logger.debug(
                f"[{self.faucet_name}] Analytics: "
                f"raw_amount='{raw_amount}' -> {amount} {currency}, "
                f"raw_balance='{raw_balance}' -> {balance_after}"
            )

            # Record to analytics
            tracker.record_claim(
                faucet=self.faucet_name,
                success=result.success,
                amount=amount,
                currency=currency,
                balance_after=balance_after
            )
        except Exception as analytics_err:
            logger.warning(f"[{self.faucet_name}] Analytics tracking failed: {analytics_err}", exc_info=True)

    def _normalize_claim_amount(self, amount: float, raw_amount: str, currency: str) -> float:
        """Normalize claim amount into smallest units for analytics.

        Heuristic: if the raw amount looks like a fractional coin value, convert
        using currency decimals. Otherwise, keep as-is (assumed smallest unit).
        """
        try:
            if amount <= 0:
                return amount

            raw_text = str(raw_amount or "")
            looks_fractional = any(token in raw_text for token in [".", "e", "E"])

            from core.analytics import CryptoPriceFeed
            decimals = CryptoPriceFeed.CURRENCY_DECIMALS.get(currency.upper())

            if decimals is not None and (looks_fractional or amount < 1):
                return amount * (10 ** decimals)
        except Exception:
            pass

        return amount

    @staticmethod
    def _detect_currency_from_text(text: str) -> Optional[str]:
        """Detect currency code from claim/balance text."""
        if not text:
            return None
        upper = text.upper()
        for symbol in ["BTC", "LTC", "DOGE", "BCH", "TRX", "ETH",
                       "BNB", "SOL", "TON", "DASH", "USDT", "MATIC", "POLYGON"]:
            if symbol in upper:
                return "POLYGON" if symbol == "MATIC" else symbol
        name_map = {
            "BITCOIN": "BTC",
            "LITECOIN": "LTC",
            "DOGECOIN": "DOGE",
            "BITCOIN CASH": "BCH",
            "TRON": "TRX",
            "ETHEREUM": "ETH",
            "BINANCE": "BNB",
            "SOLANA": "SOL",
            "TETHER": "USDT",
            "DASH": "DASH",
            "POLYGON": "POLYGON",
        }
        for name, symbol in name_map.items():
            if name in upper:
                return symbol
        if "SAT" in upper or "SATOSHI" in upper:
            return "BTC"
        return None

    async def run(self) -> ClaimResult:
        """Execute the full faucet run (login + all earning tasks).

        This is the legacy entry-point; newer code uses the individual
        ``*_wrapper`` methods called directly by the scheduler.  The
        method still works for standalone testing.

        Returns:
            :class:`ClaimResult` from the primary claim task, or a
            default failure result if everything fails.
        """
        logger.info(f"[{self.faucet_name}] Starting run...")

        # Default result in case everything fails
        final_result = ClaimResult(success=False, status="Run Failed", next_claim_minutes=5)

        try:
            if not await self.login():
                logger.error(f"[{self.faucet_name}] Login Failed")
                res = ClaimResult(success=False, status="Login Failed", next_claim_minutes=30)
                await self._record_analytics(res)
                return res

            await self.close_popups()

            # Note: WebRTC/Canvas stealth is handled at context creation in browser/instance.py
            await self.random_delay()

            # Execute all defined tasks
            tasks = self.get_earning_tasks()

            for task_info in tasks:
                func = task_info["func"]
                name = task_info["name"]

                try:
                    logger.info(f"[{self.faucet_name}] Executing: {name}")
                    res = await func()

                    # If this was the main claim, capture the result for scheduling
                    if isinstance(res, ClaimResult):
                        final_result = res
                        logger.info(
                            f"[{self.faucet_name}] {name} Result: "
                            f"{res.status} (Wait: {res.next_claim_minutes}m)"
                        )
                        # NO ANALYTICS HERE - Handled by wrappers or caller

                    elif res:
                        logger.info(f"[{self.faucet_name}] {name} Successful")
                    else:
                        logger.warning(f"[{self.faucet_name}] {name} Completed with no result/fail")

                    await self.random_delay()

                except Exception as e:
                    error_msg = f"Task '{name}' Error: {e}"
                    logger.error(f"[{self.faucet_name}] {error_msg}")

                    # If the primary claim fails with an exception, update final_result
                    if name == "Faucet Claim":
                        final_result = ClaimResult(success=False, status=error_msg, next_claim_minutes=15)

                    # We continue to the next task even if this one failed!

            return final_result

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Runtime Fatal Error: {e}")
            final_result = ClaimResult(success=False, status=f"Fatal: {e}", next_claim_minutes=10)
            return final_result
        finally:
            await self.solver.close()
