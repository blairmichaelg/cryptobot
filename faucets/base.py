import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional, Union, TYPE_CHECKING, Dict, Tuple
from playwright.async_api import Page, Locator
from solvers.captcha import CaptchaSolver
from core.config import BotSettings
from browser.stealth_hub import HumanProfile

from core.extractor import DataExtractor
from core.analytics import get_tracker

if TYPE_CHECKING:
    from core.orchestrator import ErrorType

logger = logging.getLogger(__name__)

@dataclass
class ClaimResult:
    success: bool
    status: str
    next_claim_minutes: float = 0
    amount: str = "0"
    balance: str = "0"
    error_type: Optional['ErrorType'] = None  # Add error type classification
    
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
    """Base class for Faucet Bots."""

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
    
    def __init__(self, settings: BotSettings, page: Page, action_lock: asyncio.Lock = None):
        """
        Initialize the FaucetBot.

        Args:
            settings: Configuration settings for the bot.
            page: The Playwright Page instance to control.
            action_lock: An asyncio.Lock to prevent simultaneous actions across multiple bot instances.
        """
        self.settings = settings
        self.page = page
        self.action_lock = action_lock
        # Initialize solver
        provider = getattr(settings, "captcha_provider", "2captcha").lower()
        key = getattr(settings, "capsolver_api_key", None) if provider == "capsolver" else getattr(settings, "twocaptcha_api_key", None)
        self.solver = CaptchaSolver(
            api_key=key,
            provider=provider,
            daily_budget=getattr(settings, "captcha_daily_budget", 5.0),
            adaptive_routing=getattr(settings, "captcha_provider_routing", "fixed") == "adaptive",
            routing_min_samples=getattr(settings, "captcha_provider_routing_min_samples", 20)
        )
        self.solver.set_headless(getattr(settings, "headless", True))
        fallback_provider = getattr(settings, "captcha_fallback_provider", None)
        fallback_key = getattr(settings, "captcha_fallback_api_key", None)
        
        # Auto-select fallback API key if provider is set but key is not
        if fallback_provider and not fallback_key:
            if fallback_provider.lower() == "capsolver":
                fallback_key = getattr(settings, "capsolver_api_key", None)
            elif fallback_provider.lower() == "2captcha":
                fallback_key = getattr(settings, "twocaptcha_api_key", None)
        
        if fallback_provider and fallback_key:
            self.solver.set_fallback_provider(fallback_provider, fallback_key)
            
        self._faucet_name = "Generic"
        self.faucet_name = "Generic"
        self.base_url = ""
        self.base_url = ""
        self.settings_account_override = None # Allow manual injection of credentials
        self.behavior_profile_name = self.DEFAULT_BEHAVIOR_PROFILE
        self.behavior_profile = self.BEHAVIOR_PROFILES[self.DEFAULT_BEHAVIOR_PROFILE]
        self._behavior_rng = random.Random()
        
        # Human timing profile for advanced stealth
        self.human_profile = None  # Will be loaded from fingerprint or set on first use
        self.last_error_type = None

    def set_behavior_profile(self, profile_name: Optional[str] = None, profile_hint: Optional[str] = None):
        """
        Set a timing profile for humanization based on profile name or explicit hint.
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
        self.behavior_profile = self.BEHAVIOR_PROFILES.get(profile_key, self.BEHAVIOR_PROFILES[self.DEFAULT_BEHAVIOR_PROFILE])
        seed_basis = profile_name or profile_key or self.DEFAULT_BEHAVIOR_PROFILE
        self._behavior_rng = random.Random(hash(seed_basis))

    def _resolve_delay_range(self, min_s: Optional[float], max_s: Optional[float]) -> Tuple[float, float]:
        if min_s is None or max_s is None:
            min_s, max_s = self.behavior_profile.get("delay_range", (2.0, 5.0))
        return float(min_s), float(max_s)

    def _resolve_typing_range(self, delay_min: Optional[int], delay_max: Optional[int]) -> Tuple[int, int]:
        if delay_min is None or delay_max is None:
            delay_min, delay_max = self.behavior_profile.get("typing_ms", (60, 160))
        return int(delay_min), int(delay_max)

    def _resolve_idle_duration(self, duration: Optional[float]) -> float:
        if duration is None:
            min_s, max_s = self.behavior_profile.get("idle_seconds", (1.5, 3.5))
            return self._behavior_rng.uniform(min_s, max_s)
        return float(duration)

    def _resolve_reading_duration(self, duration: Optional[float]) -> float:
        if duration is None:
            min_s, max_s = self.behavior_profile.get("reading_seconds", (2.0, 5.0))
            return self._behavior_rng.uniform(min_s, max_s)
        return float(duration)

    def _resolve_focus_blur_delay(self) -> float:
        min_s, max_s = self.behavior_profile.get("focus_blur_seconds", (0.6, 2.6))
        return self._behavior_rng.uniform(min_s, max_s)

    async def think_pause(self, reason: str = ""):
        """Small pause to simulate user thinking before critical actions."""
        delay = self._behavior_rng.uniform(0.2, 0.6)
        if reason in {"pre_login", "pre_claim"}:
            delay += self._behavior_rng.uniform(0.6, 1.4)
        await asyncio.sleep(delay)

    @property
    def faucet_name(self) -> str:
        return self._faucet_name

    @faucet_name.setter
    def faucet_name(self, value: str) -> None:
        self._faucet_name = value
        if self.solver:
            self.solver.set_faucet_name(value)

    def set_proxy(self, proxy_string: str):
        """Pass the proxy string to the underlying solver."""
        if self.solver:
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
        from core.orchestrator import ErrorType
        
        # Use forced type or auto-classify
        if force_error_type:
            error_type = force_error_type
        else:
            # Auto-classify based on status message and other signals
            status_lower = status.lower()
            if any(config in status_lower for config in ["hcaptcha", "recaptcha", "turnstile", "captcha config", "solver config", "api key"]):
                error_type = ErrorType.CONFIG_ERROR
            elif any(perm in status_lower for perm in ["banned", "suspended", "invalid credentials", "auth failed"]):
                error_type = ErrorType.PERMANENT
            elif exception or page_content or status_code:
                error_type = self.classify_error(exception, page_content, status_code)
            else:
                error_type = ErrorType.UNKNOWN
        
        logger.debug(f"[{self.faucet_name}] Creating error result: {status} (type: {error_type.value})")
        
        return ClaimResult(
            success=False,
            status=status,
            next_claim_minutes=next_claim_minutes,
            error_type=error_type
        )

    def classify_error(self, exception: Optional[Exception] = None, page_content: Optional[str] = None, status_code: Optional[int] = None) -> 'ErrorType':
        """
        Classify error type based on exception, page content, and HTTP status.
        
        Args:
            exception: The exception that was raised (if any)
            page_content: The page HTML/text content (if available)
            status_code: HTTP status code (if available)
        
        Returns:
            ErrorType enum value for intelligent recovery
        """
        from core.orchestrator import ErrorType
        
        # Check status codes first
        if status_code:
            if status_code in [500, 502, 503, 504]:
                logger.debug(f"[{self.faucet_name}] Classified as FAUCET_DOWN (status {status_code})")
                return ErrorType.FAUCET_DOWN
            elif status_code == 429:
                logger.debug(f"[{self.faucet_name}] Classified as RATE_LIMIT (status 429)")
                return ErrorType.RATE_LIMIT
            elif status_code == 403:
                logger.debug(f"[{self.faucet_name}] Classified as PROXY_ISSUE (status 403)")
                return ErrorType.PROXY_ISSUE
        
        # Check exception type and message
        if exception:
            error_msg = str(exception).lower()
            
            # Browser context closed errors - treat as transient (browser can be restarted)
            if any(term in error_msg for term in [
                "target.*closed", "context.*closed", "browser.*closed",
                "connection.*closed", "session.*closed"
            ]):
                logger.debug(f"[{self.faucet_name}] Classified as TRANSIENT (closed context/browser)")
                return ErrorType.TRANSIENT
            
            # Captcha failures - check before timeout since captcha timeouts are specific
            if "captcha" in error_msg and any(term in error_msg for term in ["failed", "timeout", "error"]):
                logger.debug(f"[{self.faucet_name}] Classified as CAPTCHA_FAILED")
                return ErrorType.CAPTCHA_FAILED
            
            # Timeout/connection errors
            if any(term in error_msg for term in ["timeout", "timed out", "connection reset", "connection refused"]):
                logger.debug(f"[{self.faucet_name}] Classified as TRANSIENT (timeout/connection)")
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
        if email is None or not email or '@' not in email:
            return email
        
        local_part, domain = email.rsplit('@', 1)
        if '+' in local_part:
            base_local = local_part.split('+')[0]
            return f"{base_local}@{domain}"
        
        return email

    def get_credentials(self, faucet_name: str):
        """
        Centralized credential retrieval with override support.
        
        Args:
            faucet_name: The name of the faucet to get credentials for.
        
        Returns:
            Credentials dict or None if not found.
        """
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
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
        wallet_dict = getattr(self.settings, "wallet_addresses", {}) if hasattr(self.settings, "wallet_addresses") else {}

        if prefer_wallet and wallet_dict:
            dict_entry = wallet_dict.get(coin)
            if dict_entry:
                if isinstance(dict_entry, dict):
                    for key in ("address", "wallet", "addr"):
                        if dict_entry.get(key):
                            logger.debug(f"[{self.faucet_name}] Using preferred wallet_addresses dict ({key}) for {coin}")
                            return str(dict_entry.get(key))
                else:
                    logger.debug(f"[{self.faucet_name}] Using preferred wallet_addresses dict for {coin}")
                    return str(dict_entry)
        
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
        if hasattr(self.settings, 'wallet_addresses'):
            dict_entry = self.settings.wallet_addresses.get(coin)
            if dict_entry:
                # Support formats: "address", "wallet", "addr"
                if isinstance(dict_entry, dict):
                    for key in ("address", "wallet", "addr"):
                        if dict_entry.get(key):
                            logger.debug(f"[{self.faucet_name}] Using wallet_addresses dict ({key}) for {coin}")
                            return str(dict_entry.get(key))
                else:
                    logger.debug(f"[{self.faucet_name}] Using wallet_addresses dict for {coin}")
                    return str(dict_entry)
        
        logger.warning(f"[{self.faucet_name}] No withdrawal address configured for {coin}")
        return None


    async def random_delay(self, min_s: Optional[float] = None, max_s: Optional[float] = None):
        """
        Wait for a random amount of time to mimic human behavior.
        Uses human timing profile if available, otherwise falls back to parameters.

        Args:
            min_s: Minimum wait time in seconds (optional).
            max_s: Maximum wait time in seconds (optional).
        """
        # Use human profile timing if available and no explicit override
        if self.human_profile and min_s is None and max_s is None:
            delay = HumanProfile.get_action_delay(self.human_profile, "click")
            
            # Check if user should idle (simulates distraction)
            should_pause, pause_duration = HumanProfile.should_idle(self.human_profile)
            if should_pause:
                logger.debug(f"[{self.faucet_name}] Human profile '{self.human_profile}' idle pause: {pause_duration:.1f}s")
                await asyncio.sleep(pause_duration)
                return
        else:
            # Fallback to legacy behavior profile system
            min_s, max_s = self._resolve_delay_range(min_s, max_s)
            delay = self._behavior_rng.uniform(min_s, max_s)
        
        await asyncio.sleep(delay)

    async def thinking_pause(self):
        """
        Realistic \"thinking\" pause before important actions.
        Uses human profile if available.
        """
        if self.human_profile:
            delay = HumanProfile.get_thinking_pause(self.human_profile)
            logger.debug(f"[{self.faucet_name}] Thinking pause ({self.human_profile}): {delay:.2f}s")
        else:
            # Fallback to reasonable default
            delay = random.uniform(1.0, 3.0)
        
        await asyncio.sleep(delay)

    def load_human_profile(self, profile_name: str) -> str:
        """
        Load or assign human timing profile for this account.
        Profile is persisted in profile_fingerprints.json for consistency.
        
        Args:
            profile_name: Account/profile identifier
            
        Returns:
            Selected profile type (fast/normal/cautious/distracted)
        """
        from pathlib import Path
        import json
        
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
            logger.info(f"[{self.faucet_name}] Loaded existing human profile '{self.human_profile}' for {profile_name}")
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
                logger.info(f"[{self.faucet_name}] Assigned new human profile '{self.human_profile}' for {profile_name}")
            except Exception as e:
                logger.error(f"Failed to save human profile: {e}")
        
        return self.human_profile

    async def human_like_click(self, locator: Locator):
        """
        Simulate a human-like click with Bézier-curve style movement,
        randomized delays, scrolling, and offset clicks.
        Includes profile-based pre-click pause for realism.
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

            # Target point within the button (randomized)
            target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
            target_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)

            # Move mouse in 'human' way (multiple small steps)
            # This is a simplified version of Bézier pathing
            await self.page.mouse.move(target_x, target_y, steps=random.randint(5, 12))
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # Action synchronizer
            if self.action_lock:
                async with self.action_lock:
                    await self.page.mouse.click(target_x, target_y, delay=random.randint(80, 200))
            else:
                await self.page.mouse.click(target_x, target_y, delay=random.randint(80, 200))

    async def remove_overlays(self):
        """
        Removes transparent or semi-transparent divs that often layer 
        over buttons to trigger pop-unders.
        """
        await self.page.evaluate("""() => {
            const overlays = Array.from(document.querySelectorAll('div, ins, iframe')).filter(el => {
                const style = window.getComputedStyle(el);
                return (style.position === 'absolute' || style.position === 'fixed') && 
                       (style.zIndex > 100 || style.width === '100vw' || style.height === '100vh') &&
                       (parseFloat(style.opacity) < 0.1 || style.backgroundColor === 'transparent');
            });
            overlays.forEach(el => el.remove());
        }""")

    async def human_type(self, selector: Union[str, Locator], text: str, delay_min: Optional[int] = None, delay_max: Optional[int] = None):
        """
        Type text into a field with human-like delays between keystrokes.
        Uses human profile timing if available.
        
        Args:
            selector: CSS selector or Playwright Locator
            text: Text to type
            delay_min: Minimum delay in ms (optional)
            delay_max: Maximum delay in ms (optional)
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        
        await self.human_like_click(locator)
        
        # Clear existing text if any (optional, context dependent)
        await locator.fill("") 
        
        # Use human profile for typing speed if available
        if self.human_profile and delay_min is None and delay_max is None:
            # Get per-character delay from profile
            char_delay_s = HumanProfile.get_action_delay(self.human_profile, "type")
            delay_ms = max(20, min(300, int(char_delay_s * 1000)))
            await locator.type(text, delay=delay_ms)
        else:
            # Fallback to legacy behavior profile system
            delay_min, delay_max = self._resolve_typing_range(delay_min, delay_max)
            delay_ms = self._behavior_rng.randint(delay_min, delay_max)
            await locator.type(text, delay=delay_ms)

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
            if "Target.*closed" not in str(e) and "Connection.*closed" not in str(e):
                logger.debug(f"[{self.faucet_name}] Page health check failed: {e}")
            return False
    
    async def safe_page_operation(self, operation_name: str, operation_func, *args, **kwargs):
        """
        Safely execute a page operation with health checks.
        Returns None if page is closed or operation fails.
        
        Args:
            operation_name: Name of the operation for logging
            operation_func: Async function to execute
            *args, **kwargs: Arguments to pass to operation_func
            
        Returns:
            Result of operation_func or None if failed
        """
        try:
            # Check page health before operation
            if not await self.check_page_health():
                logger.warning(f"[{self.faucet_name}] Cannot execute {operation_name}: page is not alive")
                return None
            
            # Execute the operation
            return await operation_func(*args, **kwargs)
        except Exception as e:
            if "Target.*closed" in str(e) or "Connection.*closed" in str(e):
                logger.debug(f"[{self.faucet_name}] {operation_name} failed: page/context closed")
            else:
                logger.warning(f"[{self.faucet_name}] {operation_name} failed: {e}")
            return None
    
    async def safe_click(self, selector: Union[str, Locator], **kwargs) -> bool:
        """
        Safely click an element with health checks.
        Returns False if operation fails.
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        result = await self.safe_page_operation(
            f"click({selector})",
            locator.click,
            **kwargs
        )
        return result is not None
    
    async def safe_fill(self, selector: Union[str, Locator], text: str, **kwargs) -> bool:
        """
        Safely fill an input field with health checks.
        Returns False if operation fails.
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
        """
        Safely navigate to a URL with health checks.
        Returns False if operation fails.
        """
        result = await self.safe_page_operation(
            f"goto({url})",
            self.page.goto,
            url,
            **kwargs
        )
        return result is not None

    async def idle_mouse(self, duration: Optional[float] = None):
        """
        Move mouse randomly to simulate user reading/thinking.
        Uses human profile for timing if available.
        
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
        while time.time() - start < duration:
            # Get current viewport size
            vp = self.page.viewport_size
            if not vp: return
            
            w, h = vp['width'], vp['height']
            
            # Random destination
            x = random.randint(0, w)
            y = random.randint(0, h)
            
            # Move in short burst
            await self.page.mouse.move(x, y, steps=self._behavior_rng.randint(5, 20))
            await asyncio.sleep(self._behavior_rng.uniform(0.1, 0.5))

    async def simulate_reading(self, duration: Optional[float] = None):
        """
        Simulate a user reading content with natural scrolling behavior.
        Uses human profile for timing if available.
        
        Combines idle mouse movement with randomized scrolling to mimic
        real user interaction patterns while consuming content.
        
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
        while time.time() - start < duration:
            # Small random scrolls (mostly down, sometimes up)
            direction = self._behavior_rng.choice([1, 1, 1, -1])  # 75% down, 25% up
            delta = self._behavior_rng.randint(30, 100) * direction
            await self.page.mouse.wheel(0, delta)
            
            # Natural pause between scrolls
            await asyncio.sleep(self._behavior_rng.uniform(0.4, 1.2))
            
            # Occasional small mouse movement
            if self._behavior_rng.random() < 0.3:
                vp = self.page.viewport_size
                if vp:
                    x = self._behavior_rng.randint(int(vp['width'] * 0.2), int(vp['width'] * 0.8))
                    y = self._behavior_rng.randint(int(vp['height'] * 0.3), int(vp['height'] * 0.7))
                    await self.page.mouse.move(x, y, steps=self._behavior_rng.randint(3, 8))

    async def random_focus_blur(self):
        """
        Simulate tab switching/focus events to appear more human.
        
        Dispatches blur/focus events with realistic timing to mimic
        a user switching between tabs or windows.
        """
        delay = self._resolve_focus_blur_delay()
        delay_ms = int(delay * 1000)
        await self.page.evaluate(
            """() => {
            // Dispatch blur event (user switched away)
            document.dispatchEvent(new Event('blur'));
            window.dispatchEvent(new FocusEvent('blur'));

            // Schedule focus event after random delay (user came back)
            const delay = %d;  // profile-based delay
            setTimeout(() => {
                document.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new FocusEvent('focus'));
            }, delay);
        }"""
            % delay_ms
        )

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
        
        while (time.time() - start_time) < max_wait_seconds:
            checks += 1
            
            try:
                # Check for page crash/unresponsiveness
                if not await self.detect_page_crash():
                    logger.warning(f"[{self.faucet_name}] Page unresponsive during CF check. Refreshing...")
                    await self.page.reload()
                    await asyncio.sleep(5)
                    continue

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
                        logger.info(f"[{self.faucet_name}] ⏳ Cloudflare/Turnstile challenge detected, waiting...")
                    
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
    
    async def safe_navigate(self, url: str, wait_until: str = "domcontentloaded", timeout: int = None, retry_on_proxy_error: bool = True) -> bool:
        """
        Navigate to URL with automatic proxy error handling and retry logic.
        
        Handles common navigation failures including:
        - NS_ERROR_PROXY_CONNECTION_REFUSED (bad proxy)
        - Timeout errors
        - Network errors
        
        Args:
            url: Target URL to navigate to
            wait_until: Playwright wait strategy (domcontentloaded, networkidle, load, commit)
            timeout: Navigation timeout in ms (uses settings.timeout if None)
            retry_on_proxy_error: If True, retries without proxy on proxy failures
            
        Returns:
            True if navigation succeeded, False otherwise
        """
        if timeout is None:
            timeout = getattr(self.settings, "timeout", 60000)  # Use configured timeout
        
        max_attempts = 2  # Reduced from 3 - fail faster
        for attempt in range(1, max_attempts + 1):
            try:
                # Use shorter timeout on retry attempts
                attempt_timeout = timeout if attempt == 1 else min(timeout // 2, 30000)
                logger.debug(f"[{self.faucet_name}] Navigating to {url} (attempt {attempt}/{max_attempts}, timeout={attempt_timeout}ms)")
                await self.page.goto(url, wait_until=wait_until, timeout=attempt_timeout)
                logger.debug(f"[{self.faucet_name}] Navigation succeeded")
                return True
                
            except Exception as e:
                error_str = str(e)
                
                # Check for proxy-related errors
                is_proxy_error = any(proxy_error in error_str for proxy_error in [
                    "NS_ERROR_PROXY_CONNECTION_REFUSED",
                    "PROXY_CONNECTION_FAILED",
                    "ERR_PROXY_CONNECTION_FAILED",
                    "ECONNREFUSED",
                    "proxy"
                ]) or ("Timeout" in error_str and attempt == 1)  # First attempt timeout likely proxy issue
                
                if is_proxy_error:
                    logger.warning(f"[{self.faucet_name}] Proxy/connection error on attempt {attempt}: {error_str[:150]}")
                    
                    # On last attempt with proxy errors, try to get fresh context without proxy as fallback
                    if attempt == max_attempts:
                        logger.warning(f"[{self.faucet_name}] All proxy attempts failed, proxy may be blocking this site")
                        return False
                    
                    # Immediate retry with exponentially longer wait
                    wait_time = min(attempt * 2, 5)  # 2s, 4s max 5s
                    await asyncio.sleep(wait_time)
                    continue
                
                # Check for timeout errors
                elif "Timeout" in error_str or "timeout" in error_str:
                    logger.warning(f"[{self.faucet_name}] Timeout on attempt {attempt}: {error_str[:150]}")
                    
                    if attempt < max_attempts:
                        # Try with more lenient wait strategy on retry
                        if wait_until == "domcontentloaded":
                            wait_until = "commit"
                            logger.info(f"[{self.faucet_name}] Switching to 'commit' wait strategy")
                        await asyncio.sleep(1)  # Shorter wait
                        continue
                    else:
                        logger.error(f"[{self.faucet_name}] Navigation failed after {max_attempts} timeout attempts")
                        return False
                
                # Other errors - don't retry
                else:
                    logger.error(f"[{self.faucet_name}] Navigation error: {error_str[:150]}")
                    return False
        
        # If we get here, all attempts failed (shouldn't reach this)
        return False

    async def close_popups(self):
        """
        Generic handler for common crypto-site popups, cookie consents, 
        and notification requests that block view or interaction.
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
        """
        Perform the login process for the faucet.

        Returns:
            True if login was successful, False otherwise.
        """
        raise NotImplementedError

    async def claim(self) -> Union[bool, ClaimResult]:
        """
        Execute the claim process.

        Returns:
            True/False or ClaimResult object.
        """
        raise NotImplementedError
        
    async def get_timer(self, selector: str, fallback_selectors: list = None) -> float:
        """
        Extract timer value from a selector and convert to minutes.
        With automatic fallback to DOM auto-detection if selector fails.
        """
        # Structured logging: timer_check start
        logger.debug(f"[LIFECYCLE] timer_check_start | faucet={self.faucet_name} | selector={selector} | timestamp={time.time():.0f}")
        
        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                logger.debug(f"[{self.faucet_name}] Timer extracted from {selector}: {text}")
                minutes = DataExtractor.parse_timer_to_minutes(text)
                # Structured logging: timer_check success
                logger.info(f"[LIFECYCLE] timer_check | faucet={self.faucet_name} | timer_minutes={minutes} | timer_raw={text} | success=true | timestamp={time.time():.0f}")
                return minutes
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Timer extraction failed for {selector}: {e}")
        
        # Try fallback selectors
        if fallback_selectors:
            for fb_sel in fallback_selectors:
                try:
                    el = self.page.locator(fb_sel)
                    if await el.count() > 0 and await el.is_visible():
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
        logger.warning(f"[LIFECYCLE] timer_check | faucet={self.faucet_name} | success=false | timestamp={time.time():.0f}")
        logger.warning(f"[{self.faucet_name}] Could not extract timer from {selector} or fallbacks")
        return 0.0

    async def get_balance(self, selector: str, fallback_selectors: list = None) -> str:
        """
        Extract balance from a selector.
        With automatic fallback to DOM auto-detection if selector fails.
        """
        # Structured logging: balance_check start
        logger.debug(f"[LIFECYCLE] balance_check_start | faucet={self.faucet_name} | selector={selector} | timestamp={time.time():.0f}")
        
        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                logger.debug(f"[{self.faucet_name}] Balance extracted from {selector}: {text}")
                balance = DataExtractor.extract_balance(text)
                # Structured logging: balance_check success
                logger.info(f"[LIFECYCLE] balance_check | faucet={self.faucet_name} | balance={balance} | success=true | timestamp={time.time():.0f}")
                return balance
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Balance extraction failed for {selector}: {e}")
        
        # Try fallback selectors
        if fallback_selectors:
            for fb_sel in fallback_selectors:
                try:
                    el = self.page.locator(fb_sel)
                    if await el.count() > 0 and await el.is_visible():
                        text = await el.first.text_content()
                        logger.info(f"[{self.faucet_name}] Balance extracted from fallback {fb_sel}: {text}")
                        return DataExtractor.extract_balance(text)
                except Exception:
                    continue
        
        # Auto-detect from DOM
        try:
            auto_sel = await DataExtractor.find_balance_selector_in_dom(self.page)
            if auto_sel:
                el = self.page.locator(auto_sel)
                text = await el.first.text_content()
                logger.warning(f"[{self.faucet_name}] Balance auto-detected from DOM: {auto_sel} = {text}")
                return DataExtractor.extract_balance(text)
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Auto-detection failed: {e}")
        
        # Structured logging: balance_check failed
        logger.warning(f"[LIFECYCLE] balance_check | faucet={self.faucet_name} | success=false | timestamp={time.time():.0f}")
        logger.warning(f"[{self.faucet_name}] Could not extract balance from {selector} or fallbacks")
        return "0"
        
    async def is_logged_in(self) -> bool:
        """
        Check if the session is still active. 
        Subclasses should override this with specific checks.
        """
        return False

    async def check_failure_states(self) -> Optional[str]:
        """
        Check for common failure states like IP ban, proxy detection, or maintenance.
        Returns a string describing the state if failure detected, else None.
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
        if any(indicator in title for indicator in ["just a moment", "cloudflare", "ddos protection", "attention required"]):
            logger.info(f"[{self.faucet_name}] Cloudflare challenge detected in title: {title}")
            return "Site Maintenance / Blocked"
        
        # Check for ACTIVE Cloudflare challenge elements (not just mentions in scripts)
        try:
            cf_challenge_element = await self.page.locator("#cf-challenge-running, .cf-browser-verification, #challenge-running").count()
            if cf_challenge_element > 0:
                logger.info(f"[{self.faucet_name}] Cloudflare challenge element detected")
                return "Site Maintenance / Blocked"
        except:
            pass
        
        # Only treat as CF block if challenge indicators are in visible text, not scripts
        try:
            visible_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            for indicator in cf_challenge_indicators:
                if indicator in visible_text:
                    logger.info(f"[{self.faucet_name}] Cloudflare challenge pattern in visible text: '{indicator}'")
                    return "Site Maintenance / Blocked"
        except:
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
        """
        Ensure we are logged in, with failure state checking.
        Automatically loads human timing profile if not already loaded.
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
        logger.info(f"[LIFECYCLE] login_start | faucet={self.faucet_name} | account={account} | timestamp={time.time():.0f}")

        # Attempt to clear Cloudflare/turnstile before failure checks
        try:
            await self.handle_cloudflare(max_wait_seconds=30)
        except Exception:
            pass
        
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
            try:
                from core.orchestrator import ErrorType
                failure_lower = failure.lower()
                if "proxy" in failure_lower or "blocked" in failure_lower:
                    error_type = ErrorType.PROXY_ISSUE
                elif "maintenance" in failure_lower or "cloudflare" in failure_lower:
                    error_type = ErrorType.RATE_LIMIT
                elif "banned" in failure_lower or "suspended" in failure_lower:
                    error_type = ErrorType.PERMANENT
            except Exception:
                error_type = None

            self.last_error_type = error_type
            logger.error(f"[{self.faucet_name}] Failure state detected: {failure}")
            return False
            
        if await self.is_logged_in():
            # Structured logging: login_success (already logged in)
            logger.info(f"[LIFECYCLE] login_success | faucet={self.faucet_name} | account={account} | already_logged_in=true | timestamp={time.time():.0f}")
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
                logger.warning(f"[LIFECYCLE] login_failed | faucet={self.faucet_name} | account={account} | error_type={self.last_error_type.value if self.last_error_type else 'unknown'} | timestamp={time.time():.0f}")
        else:
            # Structured logging: login_success
            logger.info(f"[LIFECYCLE] login_success | faucet={self.faucet_name} | account={account} | timestamp={time.time():.0f}")

        return logged_in

    async def view_ptc_ads(self):
        """
        Generic PTC Ad viewing logic.
        1. Finds ad links (selector provided by subclass)
        2. Clicks and handles new tab
        3. Waits for timer (time provided by subclass or element)
        4. Solves captcha if needed
        """
        logger.warning(f"[{self.faucet_name}] PTC logic not fully implemented in subclass.")
        await asyncio.sleep(1)

    def get_earning_tasks(self):
        """
        Returns a list of async methods (tasks) to execute for earnings.
        """
        tasks = []
        # Claim is usually the primary task
        tasks.append({"func": self.claim, "name": "Faucet Claim"})
        
        # Add PTC if available
        # Note: We now define view_ptc_ads in base, so we check if subclass overrides or configured
        if hasattr(self, "ptc_ads_selector") or self.faucet_name in ["CoinPayU", "AdBTC"]:
            tasks.append({"func": self.view_ptc_ads, "name": "PTC Ads"})
        
        return tasks
             
    async def withdraw(self) -> ClaimResult:
        """
        Generic withdrawal logic. Subclasses should override this with site-specific
        navigation and button clicking.
        """
        logger.warning(f"[{self.faucet_name}] Withdrawal not implemented for this faucet.")
        return ClaimResult(success=False, status="Not Implemented", next_claim_minutes=1440)

    def get_jobs(self):
        """
        Returns a list of Job objects for the scheduler.
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
        
        # 3. PTC job if available
        if hasattr(self, "view_ptc_ads"):
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
        """Wrapper for withdrawal with threshold checking and analytics tracking."""
        from core.withdrawal_analytics import get_analytics
        
        self.page = page
        
        # 1. Ensure logged in
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        
        # 2. Check balance against threshold
        current_balance = await self.get_balance(getattr(self, 'balance_selector', '.balance'))
        balance_before = 0.0
        try:
            balance_before = float(current_balance.replace(',', ''))
            threshold = getattr(self.settings, f"{self.faucet_name.lower()}_min_withdraw", 1000)
            if balance_before < threshold:
                logger.info(f"[{self.faucet_name}] Balance {balance_before} below threshold {threshold}. Skipping.")
                return ClaimResult(success=True, status="Below Threshold", next_claim_minutes=1440)
        except (ValueError, AttributeError) as e:
            logger.debug(f"[{self.faucet_name}] Balance parsing failed: {e}. Proceeding with withdrawal.")
            # Continue if parsing fails
        
        # 3. Execute withdrawal
        result = await self.withdraw()
        
        # 4. Track withdrawal in analytics (if successful)
        if result.success:
            try:
                # Get balance after withdrawal
                balance_after_str = result.balance if result.balance != "0" else await self.get_balance(getattr(self, 'balance_selector', '.balance'))
                balance_after = 0.0
                try:
                    balance_after = float(balance_after_str.replace(',', ''))
                except (ValueError, AttributeError):
                    balance_after = 0.0
                
                # Calculate withdrawn amount
                amount_withdrawn = float(result.amount.replace(',', '')) if result.amount != "0" else (balance_before - balance_after)
                
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
    
    def _get_cryptocurrency_for_faucet(self) -> str:
        """
        Determine the cryptocurrency for this faucet.
        Subclasses can override this method.
        """
        # Try to infer from faucet name
        name_lower = self.faucet_name.lower()
        if "btc" in name_lower or "bitcoin" in name_lower:
            return "BTC"
        elif "ltc" in name_lower or "lite" in name_lower:
            return "LTC"
        elif "doge" in name_lower:
            return "DOGE"
        elif "trx" in name_lower or "tron" in name_lower:
            return "TRX"
        elif "eth" in name_lower:
            return "ETH"
        elif "bnb" in name_lower or "bin" in name_lower:
            return "BNB"
        elif "sol" in name_lower:
            return "SOL"
        elif "ton" in name_lower:
            return "TON"
        elif "matic" in name_lower or "polygon" in name_lower:
            return "MATIC"
        elif "dash" in name_lower:
            return "DASH"
        elif "bch" in name_lower:
            return "BCH"
        elif "usdt" in name_lower or "usd" in name_lower:
            return "USDT"
        else:
            return "UNKNOWN"
             
    async def claim_wrapper(self, page: Page) -> ClaimResult:
        self.page = page
        page_content = None
        status_code = None
        
        # Get account and proxy info for logging
        creds = self.get_credentials(self.faucet_name)
        account = creds.get('username', 'unknown') if creds else 'unknown'
        proxy = getattr(self.page.context, '_proxy', {}).get('server', 'none') if hasattr(self.page, 'context') else 'none'
        
        # Structured logging: claim_submit_start
        logger.info(f"[LIFECYCLE] claim_submit_start | faucet={self.faucet_name} | account={account} | proxy={proxy} | timestamp={time.time():.0f}")
        
        try:
            await self.think_pause("pre_login")
            # Ensure logged in with new wrapper
            if not await self.login_wrapper():
                # Try to get page content for error classification
                try:
                    page_content = await page.content()
                    # Try to infer status from page state
                except Exception:
                    pass
                
                # Classify login failure
                error_type = self.last_error_type or self.classify_error(None, page_content, status_code)
                # Structured logging: claim_submit_failed (login)
                logger.warning(f"[LIFECYCLE] claim_submit_failed | faucet={self.faucet_name} | account={account} | reason=login_failed | error_type={error_type.value if error_type else 'unknown'} | timestamp={time.time():.0f}")
                return ClaimResult(
                    success=False, 
                    status="Login/Access Failed", 
                    next_claim_minutes=30,
                    error_type=error_type
                ).validate(self.faucet_name)
            
            await self.think_pause("pre_claim")
            # Structured logging: claim_submit (executing)
            logger.info(f"[LIFECYCLE] claim_submit | faucet={self.faucet_name} | account={account} | timestamp={time.time():.0f}")
            result = await self.claim()
            
            # Handle cases where claim() might return a boolean (legacy)
            if isinstance(result, bool):
                result = ClaimResult(success=result, status="Claimed" if result else "Failed")
            
            # Validate ClaimResult before proceeding
            result.validate(self.faucet_name)
            
            # Structured logging: claim_verify
            logger.info(f"[LIFECYCLE] claim_verify | faucet={self.faucet_name} | account={account} | success={result.success} | status={result.status[:50]} | timestamp={time.time():.0f}")
            
            # If claim failed, try to classify the error
            if not result.success and not hasattr(result, 'error_type'):
                try:
                    page_content = await page.content()
                except Exception:
                    page_content = None
                
                result.error_type = self.classify_error(None, page_content, status_code)
                logger.info(f"[{self.faucet_name}] Claim failed - classified as {result.error_type.value}")
                
            # Record analytics for the claim
            await self._record_analytics(result)
            
            # Structured logging: result_record
            logger.info(f"[LIFECYCLE] result_record | faucet={self.faucet_name} | account={account} | success={result.success} | amount={result.amount} | balance={result.balance} | next_claim_min={result.next_claim_minutes} | error_type={result.error_type.value if hasattr(result, 'error_type') and result.error_type else 'none'} | timestamp={time.time():.0f}")
                
            return result
            
        except Exception as e:
            # Classify exception-based errors
            try:
                page_content = await page.content()
            except Exception:
                page_content = None
            
            error_type = self.classify_error(e, page_content, status_code)
            logger.error(f"[{self.faucet_name}] Exception in claim_wrapper: {e} (classified as {error_type.value})")
            
            # Structured logging: result_record (exception)
            logger.error(f"[LIFECYCLE] result_record | faucet={self.faucet_name} | account={account} | success=false | exception={str(e)[:100]} | error_type={error_type.value} | timestamp={time.time():.0f}")
            
            return ClaimResult(
                success=False,
                status=f"Exception: {str(e)[:100]}",
                next_claim_minutes=15,
                error_type=error_type
            )

    async def ptc_wrapper(self, page: Page) -> ClaimResult:
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        
        await self.view_ptc_ads()
        return ClaimResult(success=True, status="PTC Done", next_claim_minutes=self.settings.exploration_frequency_minutes)

    async def _record_analytics(self, result: ClaimResult):
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
        for symbol in ["BTC", "LTC", "DOGE", "BCH", "TRX", "ETH", "BNB", "SOL", "TON", "DASH", "USDT", "MATIC", "POLYGON"]:
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
        """
        Main execution flow. 
        Returns the ClaimResult from the primary 'claim' task (or a default failure one)
        to determine the next schedule time.
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
                        logger.info(f"[{self.faucet_name}] {name} Result: {res.status} (Wait: {res.next_claim_minutes}m)")
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
