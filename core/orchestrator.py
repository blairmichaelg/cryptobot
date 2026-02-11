"""Job-scheduler and orchestration engine for Cryptobot Gen 3.0.

This module implements the core scheduling loop that drives all faucet-claim
activity.  It manages a min-heap priority queue of :class:`Job` objects,
orchestrates their execution across browser contexts, and provides:

* Concurrency control (global + per-profile limits).
* Per-domain rate limiting to avoid triggering anti-bot defences.
* Automatic proxy rotation on detection / failure.
* Exponential back-off with jitter per faucet.
* Circuit-breaker logic with error-type awareness.
* Session persistence (``config/session_state.json``) for crash recovery.
* Integration with :class:`HealthMonitor` for service-level health.
* ML-style timer prediction (stated vs. actual claim interval tracking).

Classes:
    ErrorType: Enum classifying errors for intelligent retry/disable decisions.
    Job: Dataclass representing a single scheduled claim task.
    JobScheduler: Main orchestration engine.
"""

import asyncio
import logging
import time
import random
import json
import os
import inspect
import shutil
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, TYPE_CHECKING
from datetime import datetime, timezone, timedelta
from enum import Enum
from core.config import BotSettings, AccountProfile, CONFIG_DIR, LOGS_DIR
from core.health_monitor import HealthMonitor

if TYPE_CHECKING:
    from faucets.base import ClaimResult
    from core.config import OperationMode

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of error types for intelligent recovery.

    Error Categories:
    - TRANSIENT: Network timeouts, temporary connection issues (retryable, short delay)
    - RATE_LIMIT: Rate limiting, Cloudflare challenges, security checks, maintenance (retryable, medium delay)
    - PROXY_ISSUE: Proxy/VPN detection, IP blocks (retryable with proxy rotation)
    - CAPTCHA_FAILED: CAPTCHA solve failures or timeouts (retryable, medium delay)
    - CONFIG_ERROR: Configuration problems like invalid API keys (retryable after fix)
    - FAUCET_DOWN: Server errors 500/503 (retryable, long delay)
    - PERMANENT: Account banned, invalid credentials, auth failures (NOT retryable)
    - UNKNOWN: Unclassified errors (retryable with caution)

    Note: Security challenges (Cloudflare, DDoS protection) are classified as RATE_LIMIT,
    not PERMANENT, to allow retry with backoff before permanent disable.
    """
    TRANSIENT = "transient"  # Network timeout, temporary unavailable
    RATE_LIMIT = "rate_limit"  # 429, cloudflare challenge, security checks, maintenance
    PROXY_ISSUE = "proxy_issue"  # Proxy detection, IP blocked
    PERMANENT = "permanent"  # Auth failed, account banned (only true permanent failures)
    FAUCET_DOWN = "faucet_down"  # 500/503 server errors
    CAPTCHA_FAILED = "captcha_failed"  # Captcha solve timeout
    CONFIG_ERROR = "config_error"  # Configuration issue (hCaptcha, solver settings)
    UNKNOWN = "unknown"


# Constants for magic numbers (Code Quality: extracted from hardcoded values)
MAX_PROXY_FAILURES = 3
PROXY_COOLDOWN_SECONDS = 300
BURNED_PROXY_COOLDOWN = 43200  # 12 hours
JITTER_MIN_SECONDS = 30
JITTER_MAX_SECONDS = 120
CLOUDFLARE_MAX_RETRIES = 15
PROXY_RETRY_DELAY_SECONDS = 60
MAX_RETRY_BACKOFF_SECONDS = 3600

# Rate limiting constants
MIN_DOMAIN_GAP_SECONDS = 45  # Minimum seconds between requests to same domain
HEARTBEAT_INTERVAL_SECONDS = 60  # Write heartbeat every minute
SESSION_PERSIST_INTERVAL = 300  # Save queue every 5 minutes
BROWSER_HEALTH_CHECK_INTERVAL = 600  # Check browser every 10 minutes
MAX_CONSECUTIVE_JOB_FAILURES = 5  # Restart browser if 5 jobs fail in a row


@dataclass(order=True)
class Job:
    """A single scheduled faucet-claim task.

    Jobs are ordered by ``(priority, next_run)`` for the min-heap.  Lower
    ``priority`` values execute first; ties are broken by ``next_run``
    (earliest first).

    Attributes:
        priority: Numeric priority (lower = higher urgency).
        next_run: Unix timestamp when this job becomes eligible.
        name: Human-readable job label (e.g. ``"firefaucet_claim"``).
        profile: :class:`AccountProfile` with credentials and proxy info.
        faucet_type: Registry key used to resolve the bot class.
        job_type: Execution wrapper name (default ``"claim_wrapper"``).
        retry_count: Number of consecutive retries so far.
    """

    priority: int
    next_run: float
    name: str = field(compare=False)
    profile: AccountProfile = field(compare=False)
    faucet_type: str = field(compare=False)
    job_type: str = field(compare=False, default="claim_wrapper")
    retry_count: int = field(default=0, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the job to a JSON-safe dictionary."""
        return {
            "priority": self.priority,
            "next_run": self.next_run,
            "name": self.name,
            "profile": self.profile.model_dump(),
            "faucet_type": self.faucet_type,
            "job_type": self.job_type,
            "retry_count": self.retry_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Deserialise a job from a dictionary (e.g. session_state.json)."""
        data['profile'] = AccountProfile(**data['profile'])
        return cls(**data)


class JobScheduler:
    """
    Central orchestration engine for the bot farm.

    Manages a priority queue of Jobs, orchestrating their execution across available
    browser contexts. Handles concurrency limits, rate limiting per domain,
    proxy rotation, and robust error recovery.
    """

    def __init__(self, settings: BotSettings, browser_manager: Any, proxy_manager: Optional[Any] = None):
        """
        Initialize the scheduler.

        Args:
            settings: Global configuration object.
            browser_manager: Manager for Playwright/Camoufox instances.
            proxy_manager: Optional manager for rotating residential proxies.
        """
        self.settings = settings
        self.browser_manager = browser_manager
        self.proxy_manager = proxy_manager
        self.queue: List[Job] = []
        self.running_jobs: Dict[str, asyncio.Task] = {}  # Key: profile.username + job.name

        # Security challenge retry tracking (prevents permanent disable on first challenge)
        # Format: {"faucet_type:username": {"security_retries": count, "last_retry_time": timestamp}}
        self.security_challenge_retries: Dict[str, Dict[str, Any]] = {}
        self.max_security_retries = 5  # Allow up to 5 security challenge retries before permanent disable
        self.security_retry_reset_hours = 24  # Reset retry counter after 24 hours of no challenges

        # Auto-withdrawal management
        self.auto_withdrawal = None  # Will be initialized if wallet daemon is available
        self.withdrawal_check_scheduled = False

        # Exponential backoff tracking per faucet
        self.faucet_backoff: Dict[str, Dict[str, Any]] = {}  # faucet_type -> {consecutive_failures, next_allowed_time}

        # Health monitoring
        self.health_monitor = HealthMonitor(
            browser_manager=self.browser_manager,
            proxy_manager=self.proxy_manager,
            alert_webhook_url=self.settings.alert_webhook_url
        )
        self.last_health_check_time = 0.0

        # Startup Checks
        if self.proxy_manager:
            if len(self.proxy_manager.proxies) < 3:
                logger.warning(
                    f"⚠️ LOW PROXY COUNT: Only {len(self.proxy_manager.proxies)} "
                    f"proxies detected. Recommended: 3+ for stealth."
                )

        self.profile_concurrency: Dict[str, int] = {}  # Key: profile.username
        self._stop_event = asyncio.Event()

        # ML-based timer prediction tracking
        self.timer_predictions: Dict[str, List[Dict[str, float]]] = {}  # faucet_type -> list of {stated: X, actual: Y}
        self.TIMER_HISTORY_SIZE = 10  # Keep last 10 claim timers per faucet

        # Proxy rotation tracking
        self.proxy_failures: Dict[str, Dict[str, Any]] = {}  # Key: proxy URL
        self.proxy_index: Dict[str, int] = {}  # Key: profile.username

        # Circuit Breaker Tracking with Error Type Awareness
        self.faucet_failures: Dict[str, int] = {}  # Key: faucet_type
        self.faucet_error_types: Dict[str, List[ErrorType]] = {}  # Track recent error types per faucet
        self.faucet_cooldowns: Dict[str, float] = {}  # Key: faucet_type, Value: timestamp
        self.CIRCUIT_BREAKER_THRESHOLD = 5
        self.CIRCUIT_BREAKER_COOLDOWN = 14400  # 4 hours
        self.RETRYABLE_COOLDOWN = 600  # 10 minutes for temporary failures

        # Account usage tracking for multi-account support
        self.account_usage: Dict[str, Dict[str, Any]] = {}  # Key: username, Value: {faucet, last_active, status}

        # Failure classification (legacy - replaced by ErrorType enum)
        self.PERMANENT_FAILURES = ["auth_failed", "account_banned", "account_disabled", "invalid_credentials"]
        self.RETRYABLE_FAILURES = ["proxy_blocked", "proxy_detection",
                                   "cloudflare", "rate_limit", "timeout", "connection_error"]
        # Domain rate limiting - prevents hitting same faucet too fast
        self.domain_last_access: Dict[str, float] = {}  # Key: domain, Value: last access time

        # Session persistence - survive restarts
        self.session_file = str(CONFIG_DIR / "session_state.json")
        self.last_persist_time = 0

        # Health monitoring - heartbeat file
        self.heartbeat_file = "/tmp/cryptobot_heartbeat" if os.name != "nt" else str(LOGS_DIR / "heartbeat.txt")
        self.last_heartbeat_time = 0
        self.last_health_check_time = 0
        self.consecutive_job_failures = 0
        self.performance_alert_score = 0

        # Operation mode tracking for graceful degradation
        from core.config import OperationMode
        self.current_mode: OperationMode = OperationMode.NORMAL
        self.last_mode_check_time = 0
        self.MODE_CHECK_INTERVAL = 600  # Check every 10 minutes

        # Try to restore session on init
        self._restore_session()

    def _restore_session(self):
        """Restore job queue from disk if available."""
        try:
            if os.path.exists(self.session_file):
                data = self._safe_json_read(self.session_file)
                if not data:
                    logger.warning("Session state unreadable; skipping restore")
                    return

                self.domain_last_access = data.get("domain_last_access", {})

                # Restore Jobs
                raw_jobs = data.get("queue", [])
                restored_count = 0
                for rj in raw_jobs:
                    try:
                        job = Job.from_dict(rj)
                        if job.next_run < time.time() - 3600:
                            job.next_run = time.time()
                        self.add_job(job)
                        restored_count += 1
                    except Exception as je:
                        logger.warning(f"Failed to restore job: {je}")

                logger.info(f"Restored session: {restored_count} jobs, {len(self.domain_last_access)} domains")
        except Exception as e:
            logger.warning(f"Could not restore session: {e}")

    def has_only_test_jobs(self) -> bool:
        """Return True if the queue contains only legacy test jobs."""
        return bool(self.queue) and all(j.faucet_type.lower() == "test" for j in self.queue)

    def purge_jobs(self, predicate: Callable[["Job"], bool]) -> int:
        """Remove queued jobs matching a predicate. Returns count removed."""
        removed = 0
        remaining: List[Job] = []
        removed_types = set()
        for job in self.queue:
            if predicate(job):
                removed += 1
                removed_types.add(job.faucet_type)
            else:
                remaining.append(job)
        self.queue = remaining

        # Clean stale domain access entries for removed faucet types
        if removed_types:
            active_types = {j.faucet_type for j in self.queue}
            for f_type in list(self.domain_last_access.keys()):
                if f_type in removed_types and f_type not in active_types:
                    self.domain_last_access.pop(f_type, None)

        return removed

    def _safe_json_write(self, filepath: str, data: dict, max_backups: int = 3):
        """Atomic JSON write with corruption protection and backups.

        Args:
            filepath: Target file path
            data: Dictionary to serialize
            max_backups: Number of backup copies to maintain
        """
        try:
            # Create parent directory if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Backup existing file if it exists
            if os.path.exists(filepath):
                backup_base = filepath + ".backup"
                # Rotate backups
                for i in range(max_backups - 1, 0, -1):
                    old = f"{backup_base}.{i}"
                    new = f"{backup_base}.{i+1}"
                    if os.path.exists(old):
                        shutil.move(old, new)
                # Create backup 1
                shutil.copy2(filepath, f"{backup_base}.1")

            # Write to temp file first (atomic)
            temp_file = filepath + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Validate JSON is readable
            with open(temp_file, "r") as f:
                json.load(f)

            # Atomic replace
            shutil.move(temp_file, filepath)
            logger.debug(f"Safely persisted {filepath}")

        except Exception as e:
            logger.error(f"Failed to safely write {filepath}: {e}")
            # Try to restore from backup
            if os.path.exists(filepath + ".backup.1"):
                logger.info("Attempting recovery from backup")
                try:
                    shutil.copy2(filepath + ".backup.1", filepath)
                except Exception as restore_err:
                    logger.error(f"Backup restoration failed: {restore_err}")

    def _safe_json_read(self, filepath: str, max_backups: int = 3) -> Optional[dict]:
        """Read JSON with fallback to backups if corrupted."""
        candidates = [filepath] + [f"{filepath}.backup.{i}" for i in range(1, max_backups + 1)]
        for candidate in candidates:
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, "r") as f:
                    return json.load(f)
            except Exception:
                continue
        return None

    def _persist_session(self):
        """Save session state to disk with corruption protection."""
        try:
            queue_data = [j.to_dict() for j in self.queue]
            data = {
                "domain_last_access": self.domain_last_access,
                "queue": queue_data,
                "timestamp": time.time()
            }
            self._safe_json_write(self.session_file, data)
        except Exception as e:
            logger.warning(f"Could not persist session: {e}")

    def persist_session(self):
        """Public wrapper for persisting session state."""
        self._persist_session()

    def reset_security_retries(self, faucet_type: Optional[str] = None, username: Optional[str] = None):
        """
        Manually reset security challenge retry counters to re-enable accounts.

        This allows recovering from temporary security challenges (Cloudflare, maintenance)
        that may have exceeded the retry limit.

        Args:
            faucet_type: Reset counters for specific faucet (e.g., "fire_faucet"). If None, resets all.
            username: Reset counters for specific username. If None, resets all.

        Examples:
            scheduler.reset_security_retries()  # Reset all
            scheduler.reset_security_retries("fire_faucet")  # Reset all FireFaucet accounts
            scheduler.reset_security_retries("fire_faucet", "user@example.com")  # Reset specific account
        """
        if not self.security_challenge_retries:
            logger.info("No security retry counters to reset")
            return

        reset_count = 0
        keys_to_reset = []

        for retry_key in self.security_challenge_retries.keys():
            # retry_key format: "faucet_type:username"
            key_faucet, key_username = retry_key.split(":", 1)

            # Check if this key matches the filter
            if faucet_type and key_faucet != faucet_type:
                continue
            if username and key_username != username:
                continue

            keys_to_reset.append(retry_key)

        for retry_key in keys_to_reset:
            old_count = self.security_challenge_retries[retry_key].get("security_retries", 0)
            self.security_challenge_retries[retry_key] = {
                "security_retries": 0,
                "last_retry_time": time.time()
            }
            reset_count += 1
            logger.info(f"✅ Reset security retry counter for {retry_key} (was {old_count}/{self.max_security_retries})")

        if reset_count > 0:
            logger.info(f"🔄 Reset {reset_count} security retry counter(s). Accounts can now retry.")
        else:
            logger.info(f"No matching accounts found for reset (faucet: {faucet_type}, username: {username})")

    def get_security_retry_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get current status of all security challenge retry counters.

        Returns:
            Dictionary mapping "faucet:username" to retry state including count and last retry time.
        """
        status = {}
        current_time = time.time()

        for retry_key, retry_state in self.security_challenge_retries.items():
            count = retry_state.get("security_retries", 0)
            last_time = retry_state.get("last_retry_time", 0)
            hours_since = (current_time - last_time) / 3600 if last_time > 0 else 0

            status[retry_key] = {
                "retries": count,
                "max_retries": self.max_security_retries,
                "status": "DISABLED" if count >= self.max_security_retries else "ACTIVE",
                "hours_since_last_retry": round(hours_since, 2),
                "will_reset_in_hours": max(0, self.security_retry_reset_hours - hours_since) if count > 0 else 0
            }

        return status

    def _write_heartbeat(self):
        """Write heartbeat file for external monitoring."""
        try:
            active_accounts = [f"{acc['faucet']}:{username}" for username,
                               acc in self.account_usage.items() if acc.get('status') == 'active']
            with open(self.heartbeat_file, "w") as f:
                f.write(f"{time.time()}\n")
                f.write(f"{len(self.queue)} jobs\n")
                f.write(f"{len(self.running_jobs)} running\n")
                f.write(f"Accounts: {', '.join(active_accounts) if active_accounts else 'None'}\n")
        except Exception as e:
            logger.debug(f"Heartbeat write failed: {e}")

    def get_domain_delay(self, faucet_type: str) -> float:
        """Get required delay before accessing this faucet domain."""
        last_access = self.domain_last_access.get(faucet_type, 0)
        elapsed = time.time() - last_access
        if elapsed < MIN_DOMAIN_GAP_SECONDS:
            return MIN_DOMAIN_GAP_SECONDS - elapsed
        return 0

    def record_domain_access(self, faucet_type: str):
        """Record that we just accessed this faucet domain."""
        self.domain_last_access[faucet_type] = time.time()

    def calculate_retry_delay(self, faucet_type: str, error_type: ErrorType) -> float:
        """Calculate retry delay with exponential backoff + jitter.

        Formula: min(base * (2 ** failures) + random(0, base * 0.3), max_delay)

        Base delays by ErrorType:
        - TRANSIENT: 60s base
        - RATE_LIMIT: 600s base
        - PROXY_ISSUE: 300s base  
        - CAPTCHA_FAILED: 900s base
        - FAUCET_DOWN: 3600s base
        - UNKNOWN: 300s base

        Returns:
            Delay in seconds with jitter applied
        """
        # Base delays by error type
        base_delays = {
            ErrorType.TRANSIENT: 60,
            ErrorType.RATE_LIMIT: 600,
            ErrorType.PROXY_ISSUE: 300,
            ErrorType.CAPTCHA_FAILED: 900,
            ErrorType.FAUCET_DOWN: 3600,
            ErrorType.CONFIG_ERROR: 1800,  # 30 minutes - retryable config issue
            ErrorType.UNKNOWN: 300,
            ErrorType.PERMANENT: float('inf')  # Don't retry permanent failures
        }

        base_delay = base_delays.get(error_type, 300)

        if base_delay == float('inf'):
            return base_delay

        # Get failure count for this faucet
        backoff_state = self.faucet_backoff.get(faucet_type, {})
        consecutive_failures = backoff_state.get('consecutive_failures', 0)

        # Exponential backoff: base * (2 ** failures)
        exponential_delay = base_delay * (2 ** min(consecutive_failures, 5))  # Cap at 5 doublings

        # Apply jitter (±30% of base delay) to prevent thundering herd
        jitter = random.uniform(0, base_delay * 0.3)

        # Total delay with max cap
        max_delay = 7200  # 2 hours max
        total_delay = min(exponential_delay + jitter, max_delay)

        logger.debug(f"Calculated retry delay for {faucet_type} ({error_type.value}): "
                     f"{total_delay:.0f}s (failures: {consecutive_failures}, base: {base_delay}s)")

        return total_delay

    async def _get_proxy_locale_timezone(self, proxy: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Resolve locale/timezone hints based on proxy geolocation."""
        if not proxy or not self.proxy_manager:
            return None, None

        try:
            geo = await self.proxy_manager.get_geolocation_for_proxy(proxy)
            if not geo:
                return None, None
            timezone_id, locale = geo
            return locale, timezone_id
        except Exception as e:
            logger.debug(f"Proxy geolocation lookup failed for {proxy}: {e}")
            return None, None

    def estimate_claim_cost(self, faucet_type: str) -> float:
        """Estimate total cost to claim this faucet.

        Based on historical data:
        - Average captchas per claim (1-3)
        - Captcha types (turnstile=0.003, hcaptcha=0.003, image=0.001)
        - Success/retry rate

        Args:
            faucet_type: The faucet type to estimate

        Returns:
            Estimated USD cost for this claim
        """
        try:
            from core.analytics import get_tracker
            tracker = get_tracker()

            # Get historical captcha usage for this faucet
            faucet_stats = tracker.get_faucet_stats(hours=168)  # Last week
            faucet_data = faucet_stats.get(faucet_type.lower(), {})

            # Default captcha cost estimates per faucet type (based on known patterns)
            faucet_captcha_estimates = {
                "firefaucet": {"count": 1, "type": "turnstile", "cost": 0.003},
                "freebitcoin": {"count": 2, "type": "hcaptcha", "cost": 0.006},
                "cointiply": {"count": 1, "type": "hcaptcha", "cost": 0.003},
                "coinpayu": {"count": 1, "type": "image", "cost": 0.001},
                "dutchycorp": {"count": 1, "type": "turnstile", "cost": 0.003},
                "faucetcrypto": {"count": 1, "type": "turnstile", "cost": 0.003},
                "autofaucet": {"count": 1, "type": "turnstile", "cost": 0.003},
            }

            # Check for pick.io faucets (all use same pattern)
            if "pick" in faucet_type.lower():
                faucet_captcha_estimates[faucet_type.lower()] = {"count": 1, "type": "turnstile", "cost": 0.003}

            # Use historical data if available, otherwise use defaults
            if faucet_data and "total_claims" in faucet_data and faucet_data["total_claims"] > 5:
                # Estimate based on success rate (more retries = more captchas)
                success_rate = faucet_data.get("success_rate", 50) / 100.0
                retry_multiplier = 1.0 / max(success_rate, 0.3)  # At least 30% success assumed

                # Get base cost estimate
                base_estimate = faucet_captcha_estimates.get(faucet_type.lower(), {"count": 1, "cost": 0.003})
                estimated_cost = base_estimate["cost"] * retry_multiplier
            else:
                # Use default estimate
                estimate = faucet_captcha_estimates.get(faucet_type.lower(), {"count": 1, "cost": 0.003})
                estimated_cost = estimate["cost"]

            logger.debug(f"Estimated claim cost for {faucet_type}: ${estimated_cost:.4f}")
            return estimated_cost

        except Exception as e:
            logger.debug(f"Could not estimate claim cost for {faucet_type}: {e}")
            # Default to moderate estimate
            return 0.003

    def is_off_peak_time(self) -> bool:
        """
        Check if current time is optimal for withdrawals (lower network fees).

        Based on research, network fees are typically lowest during:
        - Late night / early morning UTC (22:00 - 05:00)
        - Weekends (especially Sunday)

        Returns:
            True if current time is off-peak for withdrawals
        """
        now = datetime.now(timezone.utc)

        # Check hour (late night / early morning UTC)
        off_peak_hours = [0, 1, 2, 3, 4, 5, 22, 23]
        if now.hour in off_peak_hours:
            return True

        # Also consider weekends as off-peak
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return True

        return False

    def get_faucet_priority(self, faucet_type: str) -> float:
        """
        Calculate dynamic priority based on historical profitability.

        Higher scores = higher priority. Uses success rate and earnings
        to rank faucets. Used for intelligent job scheduling.

        Args:
            faucet_type: The faucet identifier (e.g., 'firefaucet', 'coinpayu')

        Returns:
            Priority multiplier (0.1 to 2.0). Higher = more profitable.
        """
        from core.analytics import get_tracker

        try:
            tracker = get_tracker()
            stats = tracker.get_faucet_stats(24)
            hourly = tracker.get_hourly_rate(hours=24)
            stats_key = self._match_faucet_key(stats, faucet_type)
            hourly_key = self._match_faucet_key(hourly, faucet_type)

            if stats_key:
                success_rate = stats[stats_key].get('success_rate', 50) / 100
                earnings_per_hour = hourly.get(hourly_key, 0) if hourly_key else 0
                profitability = tracker.get_faucet_profitability(stats_key, days=1)

                # Normalize earnings (assume 100 satoshi/hour is baseline)
                earnings_factor = min(1 + (earnings_per_hour / 100), 2.0)

                roi_pct = profitability.get("roi_percentage", 0.0)
                roi = roi_pct / 100.0
                roi_factor = max(0.3, min(1.0 + roi, 2.0))

                # Combine factors: success rate, earnings, ROI
                priority = (success_rate * 0.5) + (earnings_factor * 0.3) + (roi_factor * 0.2)

                # Time-of-day ROI optimization
                if getattr(self.settings, "time_of_day_roi_enabled", False):
                    hourly_roi = tracker.get_hourly_roi(stats_key, days=7)
                    hour_key = datetime.now(timezone.utc).hour
                    roi_by_hour = hourly_roi.get(stats_key, {})
                    roi_pct = roi_by_hour.get(hour_key)
                    if roi_pct is not None:
                        weight = max(0.0, min(getattr(self.settings, "time_of_day_roi_weight", 0.15), 0.5))
                        hour_multiplier = 1.0 + (roi_pct / 100.0) * weight
                        priority *= max(0.3, min(hour_multiplier, 2.0))
                return max(0.1, min(priority, 2.0))
        except Exception as e:
            logger.debug(f"Priority calculation failed for {faucet_type}: {e}")

        return 0.5  # Default mid-priority

    def _check_auto_suspend(self, faucet_type: str) -> tuple[bool, str]:
        """
        Check if a faucet should be auto-suspended based on ROI and success rate.

        Args:
            faucet_type: The faucet identifier

        Returns:
            Tuple of (should_suspend: bool, reason: str)
        """
        from core.analytics import get_tracker

        try:
            # Get faucet stats
            stats = get_tracker().get_faucet_stats(24)
            stats_key = self._match_faucet_key(stats, faucet_type)

            if not stats_key:
                return False, ""

            faucet_stats = stats[stats_key]

            # Check minimum samples
            if faucet_stats['total'] < self.settings.faucet_auto_suspend_min_samples:
                return False, ""

            # Check success rate
            success_rate = faucet_stats['success_rate']
            if success_rate < self.settings.faucet_min_success_rate:
                return (
                    True,
                    f"Low success rate: {success_rate:.1f}% "
                    f"(threshold: {self.settings.faucet_min_success_rate}%)"
                )

            # Check ROI using tracked costs (require at least one success/earning)
            success_count = faucet_stats.get("success", 0)
            earnings = faucet_stats.get("earnings", 0.0)
            if success_count > 0 and earnings > 0:
                faucet_profit = get_tracker().get_faucet_profitability(stats_key, days=1)
                roi_pct = faucet_profit.get("roi_percentage")
                roi = (roi_pct / 100.0) if roi_pct is not None else None

                if roi is not None and roi < self.settings.faucet_roi_threshold:
                    return True, f"Negative ROI: {roi:.2f} (threshold: {self.settings.faucet_roi_threshold})"

            return False, ""

        except Exception as e:
            logger.debug(f"Auto-suspend check failed for {faucet_type}: {e}")
            return False, ""

    def predict_next_claim_time(self, faucet_type: str, stated_timer: float) -> float:
        """Learn actual timer patterns and predict optimal claim time.

        Machine learning approach:
        1. Track last N claim times vs stated timers
        2. Calculate average drift (stated vs actual)
        3. Apply learned offset to future claims
        4. Allows claiming at earliest possible moment

        Typical patterns:
        - Some faucets report 60min but allow claim at 58min (-3.3% drift)
        - Others enforce strict timers or add buffer (+1-2%)
        - Learning curve stabilizes after 5-10 claims

        Args:
            faucet_type: The faucet identifier
            stated_timer: Timer reported by faucet (in minutes)

        Returns:
            Predicted optimal claim time (in minutes)
        """
        # Initialize history if not exists
        if faucet_type not in self.timer_predictions:
            self.timer_predictions[faucet_type] = []

        history = self.timer_predictions[faucet_type]

        # Need at least 3 data points for prediction
        if len(history) < 3:
            logger.debug(f"[{faucet_type}] Insufficient timer history ({len(history)} points), using stated timer")
            return stated_timer

        # Calculate average drift from recent history
        recent_history = history[-self.TIMER_HISTORY_SIZE:]
        drifts = [(entry['actual'] - entry['stated']) / entry['stated']
                  for entry in recent_history if entry['stated'] > 0]

        if not drifts:
            return stated_timer

        # Calculate statistics
        avg_drift = sum(drifts) / len(drifts)

        # Calculate standard deviation for confidence
        if len(drifts) >= 5:
            mean = avg_drift
            variance = sum((d - mean) ** 2 for d in drifts) / len(drifts)
            std_dev = variance ** 0.5

            # Use conservative estimate (mean - 0.5 * std_dev) to avoid early claims
            conservative_drift = avg_drift - (0.5 * std_dev)
        else:
            # Not enough data for std dev, use mean
            conservative_drift = avg_drift

        # Apply learned drift to prediction
        predicted_time = stated_timer * (1 + conservative_drift)

        # Safety bounds: don't predict more than ±10% from stated
        min_time = stated_timer * 0.90
        max_time = stated_timer * 1.10
        predicted_time = max(min_time, min(predicted_time, max_time))

        # Log prediction
        drift_pct = conservative_drift * 100
        logger.info(f"[{faucet_type}] Timer prediction: {predicted_time:.1f}min "
                    f"(stated: {stated_timer:.1f}min, learned drift: {drift_pct:+.1f}%, "
                    f"confidence: {len(drifts)} samples)")

        return predicted_time

    def record_timer_observation(self, faucet_type: str, stated_timer: float, actual_timer: float):
        """Record timer observation for ML learning.

        Args:
            faucet_type: The faucet identifier
            stated_timer: What the faucet claimed the timer was (minutes)
            actual_timer: How long we actually had to wait (minutes)
        """
        if faucet_type not in self.timer_predictions:
            self.timer_predictions[faucet_type] = []

        observation = {
            'stated': stated_timer,
            'actual': actual_timer,
            'timestamp': time.time()
        }

        self.timer_predictions[faucet_type].append(observation)

        # Keep only recent history
        if len(self.timer_predictions[faucet_type]) > self.TIMER_HISTORY_SIZE:
            self.timer_predictions[faucet_type] = (
                self.timer_predictions[faucet_type][-self.TIMER_HISTORY_SIZE:]
            )

        logger.debug(
            f"[{faucet_type}] Recorded timer observation: "
            f"stated={stated_timer:.1f}min, actual={actual_timer:.1f}min"
        )

    @staticmethod
    def _normalize_faucet_key(name: str) -> str:
        return str(name or "").lower().replace("_", "").replace(" ", "")

    def _match_faucet_key(self, data: Dict[str, Any], faucet_type: str) -> Optional[str]:
        """Find a stats key matching the faucet_type using normalized comparison."""
        if faucet_type in data:
            return faucet_type
        target = self._normalize_faucet_key(faucet_type)
        for key in data.keys():
            if self._normalize_faucet_key(key) == target:
                return key
        return None

    async def schedule_withdrawal_jobs(self) -> int:
        """Schedule withdrawal jobs for all faucets with a ``withdraw()`` override.

        Timing strategy:

        * Initial check offset: 24-72 h based on historical earnings rate.
        * Repeat cadence: every 24-72 h.
        * Priority: low (never pre-empts claiming).
        * Preferred windows: off-peak hours (0-5 UTC, 22-23 UTC, weekends).

        Returns:
            Number of withdrawal jobs scheduled.
        """
        from core.registry import FAUCET_REGISTRY, get_faucet_class
        from core.analytics import get_tracker

        logger.info("Scheduling withdrawal jobs for supported faucets...")

        # Get all enabled accounts
        enabled_profiles = [acc for acc in self.settings.accounts if acc.enabled]

        if not enabled_profiles:
            logger.warning("No enabled account profiles found. Skipping withdrawal job scheduling.")
            return

        scheduled_count = 0

        for profile in enabled_profiles:
            # Get the faucet class for this profile
            faucet_type = profile.faucet.lower().replace("_", "").replace(" ", "")

            # Try to find matching faucet in registry
            faucet_class = None
            for registry_key in FAUCET_REGISTRY.keys():
                if registry_key.replace("_", "") in faucet_type or faucet_type in registry_key.replace("_", ""):
                    faucet_class = get_faucet_class(registry_key)
                    faucet_type = registry_key
                    break

            if not faucet_class:
                logger.debug(f"No faucet class found for profile: {profile.username} ({profile.faucet})")
                continue

            # Check if the faucet has withdraw() method implemented
            has_withdraw = False
            try:
                # Check if withdraw method exists and is not the base implementation
                if hasattr(faucet_class, 'withdraw'):
                    method = getattr(faucet_class, 'withdraw')
                    # Check if it's not the base implementation (which just returns "Not Implemented")
                    source = inspect.getsource(method)
                    if "Not Implemented" not in source and "NotImplementedError" not in source:
                        has_withdraw = True
            except Exception as e:
                logger.debug(f"Could not inspect withdraw method for {faucet_type}: {e}")

            if not has_withdraw:
                logger.debug(f"Skipping withdrawal job for {faucet_type} - withdraw() not implemented")
                continue

            # Calculate next withdrawal time based on analytics
            next_withdrawal_time = time.time()

            # Get earnings rate from analytics to determine scheduling frequency
            try:
                tracker = get_tracker()
                hourly_rate = tracker.get_hourly_rate(hours=168)  # 1 week
                faucet_hourly = hourly_rate.get(faucet_type, 0)

                # If high earning rate, check more frequently
                if faucet_hourly > 100:  # High earner (>100 sat/hour)
                    check_interval = 86400  # 24 hours
                elif faucet_hourly > 50:  # Medium earner
                    check_interval = 129600  # 36 hours
                else:  # Low earner
                    check_interval = 259200  # 72 hours
            except Exception as e:
                logger.debug(f"Could not get earnings rate for {faucet_type}: {e}")
                check_interval = 86400  # Default to 24 hours

            # Add initial delay (24 hours) for first withdrawal check
            next_withdrawal_time += check_interval

            # Adjust to off-peak hours if enabled
            if self.settings.prefer_off_peak_withdrawals:
                target_time = datetime.fromtimestamp(next_withdrawal_time, tz=timezone.utc)

                # If not in off-peak hours, adjust to next off-peak window
                if target_time.hour not in self.settings.off_peak_hours:
                    # Find next off-peak hour
                    hours_to_add = 0
                    while (target_time.hour + hours_to_add) % 24 not in self.settings.off_peak_hours:
                        hours_to_add += 1
                    target_time += timedelta(hours=hours_to_add)
                    next_withdrawal_time = target_time.timestamp()

            # Create withdrawal job with low priority
            withdrawal_job = Job(
                priority=10,  # Low priority (higher number = lower priority)
                next_run=next_withdrawal_time,
                name=f"{profile.faucet} Withdraw",
                profile=profile,
                faucet_type=faucet_type,
                job_type="withdraw_wrapper",
                retry_count=0
            )

            self.add_job(withdrawal_job)
            scheduled_count += 1
            logger.info(
                f"Scheduled withdrawal job for {profile.faucet} ({profile.username}) "
                f"at {datetime.fromtimestamp(next_withdrawal_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )

        logger.info(f"Withdrawal job scheduling complete: {scheduled_count} jobs scheduled")
        return scheduled_count

    async def schedule_auto_withdrawal_check(self) -> None:
        """Schedule a recurring automated-withdrawal check job.

        Runs every 4 hours during off-peak windows.  Requires wallet
        RPC configuration (``wallet_rpc_urls``, ``electrum_rpc_user``,
        ``electrum_rpc_pass``).  If any prerequisite is missing or
        connectivity fails, the method logs a warning and returns.
        """
        logger.info("📅 Scheduling automated withdrawal check job...")

        # Initialize auto-withdrawal if we have wallet daemon configured
        try:
            from core.wallet_manager import WalletDaemon
            from core.auto_withdrawal import get_auto_withdrawal_instance
            from core.analytics import get_tracker

            # Check if wallet RPC is configured and credentials provided
            if not self.settings.wallet_rpc_urls:
                logger.info("⏭️  No wallet RPC configured - skipping auto-withdrawal")
                return
            if not (self.settings.electrum_rpc_user and self.settings.electrum_rpc_pass):
                logger.info("⏭️  No RPC credentials present - skipping auto-withdrawal")
                return

            # Create wallet daemon instance
            wallet = WalletDaemon(
                rpc_urls=self.settings.wallet_rpc_urls,
                rpc_user=self.settings.electrum_rpc_user or "",
                rpc_pass=self.settings.electrum_rpc_pass or ""
            )

            # Verify connectivity to at least one wallet daemon
            try:
                ok = await wallet.check_connection("BTC")
            except Exception:
                ok = False
            if not ok:
                logger.info("⏭️  Wallet daemon unreachable - skipping auto-withdrawal")
                return

            # Get analytics tracker
            tracker = get_tracker()

            # Initialize auto-withdrawal manager
            self.auto_withdrawal = get_auto_withdrawal_instance(wallet, self.settings, tracker)

            logger.info("✅ Auto-withdrawal manager initialized")

            # Schedule first check in 4 hours (or sooner if off-peak)
            next_check_time = time.time() + (4 * 3600)

            # Adjust to next off-peak window if enabled
            if self.settings.prefer_off_peak_withdrawals:
                target_time = datetime.fromtimestamp(next_check_time, tz=timezone.utc)

                # If not in off-peak hours, adjust to next off-peak window
                if target_time.hour not in self.settings.off_peak_hours:
                    hours_to_add = 0
                    while (target_time.hour + hours_to_add) % 24 not in self.settings.off_peak_hours:
                        hours_to_add += 1
                    target_time += timedelta(hours=hours_to_add)
                    next_check_time = target_time.timestamp()

            # Create a dummy profile for the withdrawal check job
            withdrawal_profile = AccountProfile(
                faucet="system",
                username="auto_withdrawal",
                password="",
                enabled=True
            )

            # Create withdrawal check job
            withdrawal_job = Job(
                priority=8,  # Medium-low priority
                next_run=next_check_time,
                name="Automated Withdrawal Check",
                profile=withdrawal_profile,
                faucet_type="system",
                job_type="auto_withdrawal_check"
            )

            self.add_job(withdrawal_job)
            self.withdrawal_check_scheduled = True

            logger.info(
                f"✅ Automated withdrawal check scheduled for "
                f"{datetime.fromtimestamp(next_check_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )

        except Exception as e:
            logger.warning(f"Failed to schedule auto-withdrawal check: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    async def execute_auto_withdrawal_check(self, _job: Job) -> 'ClaimResult':
        """Run the automated-withdrawal cycle and reschedule.

        Delegates to :meth:`AutoWithdrawalManager.check_and_execute_withdrawals`,
        logs a summary, and returns a :class:`ClaimResult` whose
        ``next_claim_minutes`` is 240 (4 h).

        Args:
            _job: The scheduler :class:`Job` triggering this check.

        Returns:
            :class:`ClaimResult` with outcome and next-run offset.
        """
        from faucets.base import ClaimResult

        logger.info("💰 Executing automated withdrawal check...")

        try:
            if not self.auto_withdrawal:
                logger.warning("Auto-withdrawal manager not initialized")
                return ClaimResult(
                    success=False,
                    status="Not initialized",
                    next_claim_minutes=240  # Try again in 4 hours
                )

            # Execute withdrawal check
            summary = await self.auto_withdrawal.check_and_execute_withdrawals()

            # Log summary
            logger.info("📊 Withdrawal check complete:")
            logger.info("  - Balances checked: %s", summary['balances_checked'])
            logger.info(
                "  - Withdrawals executed: %s", summary['withdrawals_executed']
            )
            logger.info(
                "  - Withdrawals deferred: %s", summary['withdrawals_deferred']
            )

            if summary['transactions']:
                logger.info("  - Transactions:")
                for tx in summary['transactions']:
                    logger.info(f"    • {tx['currency']}: {tx['amount']} → {tx['tx_id'][:16]}...")

            # Schedule next check in 4 hours
            next_minutes = 240

            return ClaimResult(
                success=True,
                status=(
                    f"Checked {summary['balances_checked']} currencies, "
                    f"executed {summary['withdrawals_executed']} withdrawals"
                ),
                next_claim_minutes=next_minutes
            )

        except Exception as e:
            logger.error(f"Auto-withdrawal check failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())

            return ClaimResult(
                success=False,
                status=f"Error: {str(e)}",
                next_claim_minutes=240  # Try again in 4 hours
            )

    def detect_operation_mode(self) -> "OperationMode":
        """Auto-detect the current operation mode from system health.

        Checks, in order:

        1. ``config/.maintenance`` sentinel file → ``MAINTENANCE``.
        2. Healthy proxy count below threshold → ``LOW_PROXY``.
        3. Daily CAPTCHA spend exceeding budget → ``LOW_BUDGET``.
        4. Recent failure rate > 60 % → ``SLOW_MODE``.
        5. Otherwise → ``NORMAL``.

        Returns:
            The :class:`OperationMode` matching current conditions.
        """
        from core.config import OperationMode

        # Check for manual maintenance mode first
        maintenance_flag = CONFIG_DIR / ".maintenance"
        if maintenance_flag.exists():
            return OperationMode.MAINTENANCE

        # Check proxy health
        healthy_proxies = 0
        if self.proxy_manager:
            try:
                healthy_proxies = len([
                    p for p in self.proxy_manager.proxies
                    if not self.proxy_manager.get_proxy_stats(p).get("is_dead")
                ])
            except Exception:
                healthy_proxies = len(self.proxy_manager.proxies)

            logger.info(
                f"🔍 Mode check: healthy_proxies={healthy_proxies}, "
                f"threshold={self.settings.low_proxy_threshold}, "
                f"comparison={healthy_proxies < self.settings.low_proxy_threshold}"
            )
            if healthy_proxies < self.settings.low_proxy_threshold:
                logger.warning(
                    f"Entering LOW_PROXY mode: {healthy_proxies} < "
                    f"{self.settings.low_proxy_threshold}"
                )
                return OperationMode.LOW_PROXY
            else:
                logger.info(f"✓ Proxy check passed: {healthy_proxies} >= {self.settings.low_proxy_threshold}")

        # Check captcha budget (estimate from recent usage)
        try:
            from core.analytics import get_tracker
            tracker = get_tracker()

            # Get today's captcha costs
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_costs = tracker.get_captcha_costs_since(today_start)

            remaining_budget = self.settings.captcha_daily_budget - today_costs
            if remaining_budget < 1.0:
                return OperationMode.LOW_BUDGET
        except Exception as e:
            logger.debug(f"Could not check captcha budget: {e}")

        # Check overall failure rate (last hour)
        try:
            from core.analytics import get_tracker
            tracker = get_tracker()

            hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_stats = tracker.get_stats_since(hour_ago)

            if recent_stats["total_claims"] > 10:
                failure_rate = (recent_stats["failures"] / recent_stats["total_claims"]) * 100
                if failure_rate > 60:  # >60% failure rate
                    return OperationMode.SLOW_MODE
        except Exception as e:
            logger.debug(f"Could not check failure rate: {e}")

        return OperationMode.NORMAL

    def apply_mode_restrictions(self, mode: "OperationMode") -> float:
        """Modify scheduler behaviour for the given operation mode.

        Side-effects may include:

        * Reducing ``max_concurrent_bots`` (``LOW_PROXY``).
        * Purging high-cost jobs (``LOW_BUDGET``).
        * Increasing delay multiplier (``SLOW_MODE``).
        * Freezing the queue (``MAINTENANCE``).

        Args:
            mode: The :class:`OperationMode` to apply.

        Returns:
            A delay multiplier (``>= 1.0``) to scale all scheduling
            sleeps by.
        """
        from core.config import OperationMode

        delay_multiplier = 1.0

        if mode == OperationMode.LOW_PROXY:
            # Reduce concurrency to preserve proxies
            old_concurrent = self.settings.max_concurrent_bots
            self.settings.max_concurrent_bots = min(2, old_concurrent)
            logger.warning(
                f"⚠️ LOW_PROXY mode: Reduced concurrency to {self.settings.max_concurrent_bots} "
                f"(healthy proxies: {len(self.proxy_manager.proxies) if self.proxy_manager else 0})"
            )

        elif mode == OperationMode.LOW_BUDGET:
            # Skip captcha-heavy faucets, prioritize image-only captchas
            logger.warning("⚠️ LOW_BUDGET mode: Prioritizing low-cost faucets, skipping hCaptcha/reCaptcha v3")
            # Filter queue to remove high-cost faucet types
            high_cost_faucets = ["freebitcoin"]  # Known expensive faucets
            removed = self.purge_jobs(lambda j: j.faucet_type in high_cost_faucets)
            if removed > 0:
                logger.info(f"  Removed {removed} high-cost jobs from queue")

        elif mode == OperationMode.SLOW_MODE:
            # Increase all delays by 3x to reduce failure rate
            delay_multiplier = 3.0
            logger.warning(
                f"⚠️ SLOW_MODE: Increasing delays {delay_multiplier}x due to high failure rate"
            )

        elif mode == OperationMode.MAINTENANCE:
            # Don't add new jobs, finish existing queue
            logger.warning(
                f"🔧 MAINTENANCE mode: Finishing {len(self.queue)} existing jobs, no new jobs added"
            )

        elif mode == OperationMode.NORMAL:
            # Restore normal settings if coming from degraded mode
            if self.current_mode != OperationMode.NORMAL:
                # Reset any temporary restrictions
                self.settings.max_concurrent_bots = 3  # Default value
                logger.info("✅ NORMAL mode: All restrictions lifted, resuming normal operation")

        return delay_multiplier

    def check_and_update_mode(self) -> float:
        """Periodically re-evaluate the operation mode.

        Called from the main scheduler loop.  Skips re-evaluation if
        fewer than :data:`MODE_CHECK_INTERVAL` seconds have elapsed
        since the last check.

        Returns:
            Delay multiplier (``1.0`` when no change, ``> 1.0`` when
            degraded mode is active).
        """
        now = time.time()
        if now - self.last_mode_check_time < self.MODE_CHECK_INTERVAL:
            return 1.0

        self.last_mode_check_time = now

        # Detect new mode
        new_mode = self.detect_operation_mode()

        # Log mode changes
        if new_mode != self.current_mode:
            logger.info(
                f"🔄 Operation mode change: {self.current_mode.value} → {new_mode.value}"
            )
            self.current_mode = new_mode
            delay_multiplier = self.apply_mode_restrictions(new_mode)
            return delay_multiplier

        return 1.0

    async def execute_consolidated_withdrawal(self, faucet_name: str, profile: AccountProfile) -> "ClaimResult":
        """
        Execute withdrawal for a specific faucet with timing optimization.

        Steps:
        1. Load faucet bot instance
        2. Check if balance meets threshold
        3. Check timing optimization (off-peak hours)
        4. Execute withdraw() method via wrapper
        5. Log results to WithdrawalAnalytics

        Args:
            faucet_name: The faucet identifier
            profile: Account profile for this faucet

        Returns:
            ClaimResult with withdrawal outcome
        """
        from core.registry import get_faucet_class
        from core.withdrawal_analytics import get_analytics
        from core.analytics import get_tracker
        from faucets.base import ClaimResult

        logger.info(f"Executing consolidated withdrawal for {faucet_name} ({profile.username})...")

        # 1. Load faucet bot instance
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            logger.error(f"Unknown faucet type: {faucet_name}")
            return ClaimResult(success=False, status="Unknown Faucet", next_claim_minutes=1440)

        # Create a temporary page context for withdrawal
        context = None
        try:
            # Get proxy for this profile
            current_proxy = self.get_next_proxy(profile, faucet_type=faucet_name)

            # Create context
            ua = random.choice(self.settings.user_agents) if self.settings.user_agents else None
            locale_hint, timezone_hint = await self._get_proxy_locale_timezone(current_proxy)
            context = await self.browser_manager.create_context(
                proxy=current_proxy,
                user_agent=ua,
                profile_name=profile.username,
                locale_override=locale_hint,
                timezone_override=timezone_hint,
                allow_sticky_proxy=not self._should_bypass_proxy(faucet_name),
                block_images_override=False if self._should_disable_image_block(faucet_name) else None
            )
            page = await self.browser_manager.new_page(context=context)

            # Instantiate bot
            bot = faucet_class(self.settings, page)
            override = {
                "username": profile.username,
                "password": profile.password,
            }
            if "pick" in faucet_name.lower():
                override["email"] = profile.username
            bot.settings_account_override = override
            bot.set_behavior_profile(profile_name=profile.username,
                                     profile_hint=getattr(profile, "behavior_profile", None))
            if current_proxy:
                bot.set_proxy(current_proxy)

            # 2. Check if balance meets threshold
            # This is handled by withdraw_wrapper, but we can also check here
            tracker = get_tracker()
            faucet_stats = tracker.get_faucet_stats(24)
            current_balance = 0.0

            if faucet_name.lower() in faucet_stats:
                current_balance = faucet_stats[faucet_name.lower()].get("earnings", 0.0)

            # Get threshold from settings
            threshold_key = f"{faucet_name.lower().replace('_', '')}_min_withdraw"
            min_threshold = getattr(self.settings, threshold_key, 1000)

            if current_balance < min_threshold:
                logger.info(f"Balance {current_balance} below threshold {min_threshold}. Deferring withdrawal.")
                return ClaimResult(success=True, status="Below Threshold", next_claim_minutes=1440)

            # 3. Check timing optimization (off-peak hours when network usage is typically lower)
            if self.settings.prefer_off_peak_withdrawals:
                if not self.is_off_peak_time():
                    logger.info(f"Not off-peak time. Deferring withdrawal for {faucet_name}")
                    return ClaimResult(success=True, status="Waiting for Off-Peak", next_claim_minutes=60)

            # 4. Execute withdrawal
            result = await bot.withdraw_wrapper(page)

            # 5. Analytics are logged by withdraw_wrapper
            logger.info(f"Withdrawal completed for {faucet_name}: {result.status}")

            return result

        except Exception as e:
            logger.error(f"Error executing withdrawal for {faucet_name}: {e}")

            # Log failed withdrawal to analytics
            try:
                analytics = get_analytics()
                analytics.record_withdrawal(
                    faucet=faucet_name,
                    cryptocurrency="BTC",  # Default, may not be accurate
                    amount=0.0,
                    network_fee=0.0,
                    platform_fee=0.0,
                    withdrawal_method="unknown",
                    status="failed",
                    notes=str(e)
                )
            except Exception:
                pass

            return ClaimResult(success=False, status=f"Error: {str(e)}", next_claim_minutes=360)
        finally:
            if context:
                try:
                    # Use safe context closure
                    await self.browser_manager.safe_close_context(context, profile_name=profile.username)
                except Exception as cleanup_error:
                    logger.debug(f"Final cleanup exception for {faucet_name}: {cleanup_error}")

    def add_job(self, job: Job) -> None:
        """Enqueue a job with deduplication.

        Prevents adding a job whose ``(profile.username, job_type,
        faucet_type, name)`` tuple already exists in the pending queue
        or the running-jobs set.

        Dynamic priority is applied via :meth:`get_faucet_priority`.

        Args:
            job: The :class:`Job` to add.
        """
        username = job.profile.username
        # 1. Check if an identical job is already in the queue
        for pending_job in self.queue:
            if (pending_job.profile.username == username and
                pending_job.job_type == job.job_type and
                pending_job.faucet_type == job.faucet_type and
                    pending_job.name == job.name):
                logger.debug(f"⏭️ Skipping duplicate job add: {job.name} for {username}")
                return

        # 2. Check if an identical job is currently running
        for running_key in self.running_jobs:
            # running_key is username + job.name, but we want more granular check
            # If job.name matches, it's likely the same job_type/faucet_type
            if running_key.startswith(f"{username}:") and job.name in running_key:
                logger.debug(f"⏭️ Skipping job add (already running): {job.name} for {username}")
                return

        # Apply dynamic priority based on recent performance
        try:
            priority_multiplier = self.get_faucet_priority(job.faucet_type)
            if priority_multiplier:
                adjusted_priority = int(round(job.priority / max(priority_multiplier, 0.1)))
                job.priority = max(1, adjusted_priority)
        except Exception as e:
            logger.debug(f"Dynamic priority adjustment failed for {job.faucet_type}: {e}")

        self.queue.append(job)
        self.queue.sort()  # Simple sort for now, could use heapq if queue grows large
        logger.debug(f"Added job: {job.name} for {username} (Prio: {job.priority}, Time: {job.next_run})")

    def _should_bypass_proxy(self, faucet_type: Optional[str]) -> bool:
        if not faucet_type:
            return False

        def _normalize(name: str) -> str:
            return str(name).lower().replace("_", "").replace(" ", "")

        faucet_key = _normalize(faucet_type)
        bypass_raw = getattr(self.settings, "proxy_bypass_faucets", None) or []
        if isinstance(bypass_raw, str):
            raw = bypass_raw.strip()
            if not raw or raw.lower() in {"[]", "none", "null"}:
                bypass_raw = []
            else:
                try:
                    import json
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        bypass_raw = parsed
                    else:
                        bypass_raw = [raw]
                except Exception:
                    # Fallback: comma/semicolon/space-delimited list
                    bypass_raw = [item for item in (token.strip()
                                                    for token in raw.replace(";", ",").split(",")) if item]

        # Don't apply a default if bypass_raw is explicitly set to empty list
        # This allows users to enable proxies for all faucets including FreeBitcoin

        bypass = {_normalize(name) for name in bypass_raw}
        return any(faucet_key == b or faucet_key in b or b in faucet_key for b in bypass)

    def _should_disable_image_block(self, faucet_type: Optional[str]) -> bool:
        if not faucet_type:
            return False

        def _normalize(name: str) -> str:
            return str(name).lower().replace("_", "").replace(" ", "")

        faucet_key = _normalize(faucet_type)
        bypass_raw = getattr(self.settings, "image_bypass_faucets", None) or []
        if isinstance(bypass_raw, str):
            raw = bypass_raw.strip()
            if not raw or raw.lower() in {"[]", "none", "null"}:
                bypass_raw = []
            else:
                try:
                    import json
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        bypass_raw = parsed
                    else:
                        bypass_raw = [raw]
                except Exception:
                    bypass_raw = [item for item in (token.strip()
                                                    for token in raw.replace(";", ",").split(",")) if item]

        # Don't apply a default - allow explicit empty list to disable all bypasses

        bypass = {_normalize(name) for name in bypass_raw}
        return any(faucet_key == b or faucet_key in b or b in faucet_key for b in bypass)

    def get_next_proxy(self, profile: AccountProfile, faucet_type: Optional[str] = None) -> Optional[str]:
        """Select the next proxy for a profile.

        Delegates to :class:`ProxyManager` when available, otherwise
        rotates through ``profile.proxy_pool`` using round-robin or
        random strategy.

        Args:
            profile: The account whose proxy pool to draw from.
            faucet_type: Faucet identifier; used to check bypass rules.

        Returns:
            ``user:pass@host:port`` proxy string, or ``None`` for
            direct connection.
        """
        if self._should_bypass_proxy(faucet_type):
            try:
                profile.proxy = None
            except Exception:
                pass
            return None
        if self.proxy_manager:
            return self.proxy_manager.rotate_proxy(profile)

        if not profile.proxy_pool or len(profile.proxy_pool) == 0:
            return profile.proxy

        # Filter out failed proxies
        healthy_pool = [
            p for p in profile.proxy_pool
            if self.proxy_failures.get(p, {}).get('failures', 0) < MAX_PROXY_FAILURES
            and not self.proxy_failures.get(p, {}).get('burned', False)
        ]

        if not healthy_pool:
            return profile.proxy

        # Determine strategy
        strategy = getattr(profile, 'proxy_rotation_strategy', 'round_robin')

        if strategy == "random":
            return random.choice(healthy_pool)

        # Default: Round Robin
        username = profile.username
        if username not in self.proxy_index:
            self.proxy_index[username] = 0

        current_index = self.proxy_index[username]
        proxy = healthy_pool[current_index % len(healthy_pool)]

        # Advance index
        self.proxy_index[username] = (current_index + 1) % len(healthy_pool)

        return proxy

    def record_proxy_failure(self, proxy: str, detected: bool = False, status_code: int = 0) -> None:
        """Record a proxy failure or detection event.

        When *detected* is ``True`` the proxy is burned (blacklisted
        for 12 h).

        Args:
            proxy: The ``user:pass@host:port`` proxy string.
            detected: ``True`` if the target site flagged this proxy.
            status_code: HTTP status code that triggered the failure.
        """
        if self.proxy_manager:
            self.proxy_manager.record_failure(proxy, detected=detected, status_code=status_code)
            return

        if proxy not in self.proxy_failures:
            self.proxy_failures[proxy] = {'failures': 0, 'last_failure_time': 0, 'burned': False}

        self.proxy_failures[proxy]['failures'] += 1
        self.proxy_failures[proxy]['last_failure_time'] = time.time()

        if detected:
            self.proxy_failures[proxy]['burned'] = True
            logger.error(f"❌ PROXY BURNED (Detected by site): {proxy}. Blacklisted for 12 hours.")
        else:
            logger.warning(f"⚠️ Proxy connection failure: {proxy}. Failures: {self.proxy_failures[proxy]['failures']}")

    def _track_error_type(self, faucet_type: str, error_type: ErrorType):
        """Track error types for circuit breaker intelligence."""
        if faucet_type not in self.faucet_error_types:
            self.faucet_error_types[faucet_type] = []

        # Keep last 10 errors
        self.faucet_error_types[faucet_type].append(error_type)
        if len(self.faucet_error_types[faucet_type]) > 10:
            self.faucet_error_types[faucet_type].pop(0)

    def _should_trip_circuit_breaker(self, faucet_type: str, error_type: ErrorType) -> bool:
        """Determine if circuit breaker should trip based on error type.

        Only count PERMANENT and repeated PROXY_ISSUE errors toward circuit breaker.
        TRANSIENT and CONFIG_ERROR errors don't trip the breaker.
        """
        if error_type in (ErrorType.TRANSIENT, ErrorType.CONFIG_ERROR):
            return False

        if error_type == ErrorType.PERMANENT:
            return True

        # For PROXY_ISSUE, only trip if we see it repeatedly
        if error_type == ErrorType.PROXY_ISSUE:
            recent_errors = self.faucet_error_types.get(faucet_type, [])
            proxy_error_count = sum(1 for e in recent_errors if e == ErrorType.PROXY_ISSUE)
            return proxy_error_count >= 3

        return True  # Default: count toward breaker

    def _get_recovery_delay(
        self,
        error_type: ErrorType,
        retry_count: int,
        current_proxy: Optional[str]
    ) -> tuple[float, str]:
        """Calculate recovery delay based on error type and retry count.

        Returns:
            Tuple of (delay_seconds, recovery_action_description)
        """
        if error_type == ErrorType.TRANSIENT:
            if retry_count == 0:
                return 0, "Retry immediately"
            else:
                return 300, "Requeue +5min after transient error"

        elif error_type == ErrorType.RATE_LIMIT:
            # Exponential backoff: 10min, 30min, 2hr
            delays = [600, 1800, 7200]
            delay = delays[min(retry_count, len(delays) - 1)]
            return delay, f"Rate limit backoff: {delay/60:.0f}min"

        elif error_type == ErrorType.PROXY_ISSUE:
            if current_proxy:
                self.record_proxy_failure(current_proxy, detected=True, status_code=403)
                return 1800, "Rotate proxy, requeue +30min"
            else:
                return 1800, "No proxy available, requeue +30min"

        elif error_type == ErrorType.PERMANENT:
            # Don't requeue - will be handled by caller
            return float('inf'), "Permanent failure - account disabled"

        elif error_type == ErrorType.CONFIG_ERROR:
            return 1800, "Config error (hCaptcha/solver) - requeue +30min"

        elif error_type == ErrorType.FAUCET_DOWN:
            return 14400, "Faucet down - skip 4 hours"

        elif error_type == ErrorType.CAPTCHA_FAILED:
            return 900, "Captcha failed - requeue +15min"

        else:  # UNKNOWN
            return 600, "Unknown error - requeue +10min"

    def get_recovery_delay(
        self,
        error_type: ErrorType,
        retry_count: int,
        current_proxy: Optional[str]
    ) -> tuple[float, str]:
        """Calculate recovery delay after a job failure.

        Wraps the private :meth:`_get_recovery_delay` helper.

        Args:
            error_type: Classified error category.
            retry_count: How many retries have occurred so far.
            current_proxy: The proxy string in use (may be ``None``).

        Returns:
            ``(delay_minutes, reason)`` tuple describing the wait and
            a human-readable justification.
        """
        return self._get_recovery_delay(error_type, retry_count, current_proxy)

    async def _run_job_wrapper(self, job: Job):
        """Wraps job execution with context management and error handling."""
        context = None
        username = job.profile.username
        current_proxy = None
        start_time = time.time()
        try:
            self.profile_concurrency[username] = self.profile_concurrency.get(username, 0) + 1

            # Track account usage for monitoring
            self.account_usage[username] = {
                "faucet": job.faucet_type,
                "last_active": time.time(),
                "status": "active",
                "proxy": current_proxy
            }

            # Get proxy using rotation logic
            current_proxy = self.get_next_proxy(job.profile, faucet_type=job.faucet_type)

            # Create isolated context for the job with retry on failure
            ua = random.choice(self.settings.user_agents) if self.settings.user_agents else None
            # Sticky Session: Pass profile_name
            locale_hint, timezone_hint = await self._get_proxy_locale_timezone(current_proxy)

            context_creation_attempts = 0
            max_context_attempts = 3
            while context_creation_attempts < max_context_attempts:
                try:
                    context = await self.browser_manager.create_context(
                        proxy=current_proxy,
                        user_agent=ua,
                        profile_name=username,
                        locale_override=locale_hint,
                        timezone_override=timezone_hint,
                        allow_sticky_proxy=not self._should_bypass_proxy(job.faucet_type),
                        block_images_override=False if self._should_disable_image_block(job.faucet_type) else None
                    )
                    page = await self.browser_manager.new_page(context=context)
                    break  # Success - exit retry loop
                except Exception as ctx_error:
                    context_creation_attempts += 1
                    if context_creation_attempts >= max_context_attempts:
                        logger.error(f"Failed to create context after {max_context_attempts} attempts: {ctx_error}")
                        raise
                    logger.warning(
                        f"Context creation failed "
                        f"(attempt {context_creation_attempts}/{max_context_attempts}): "
                        f"{ctx_error}"
                    )
                    # Check if browser is still healthy
                    browser_healthy = await self.browser_manager.check_health()
                    if not browser_healthy:
                        logger.warning("Browser appears unhealthy - restarting before retry")
                        await self.browser_manager.restart()
                    await asyncio.sleep(2 * context_creation_attempts)  # Exponential backoff

            # Check for legacy/test jobs BEFORE attempting to instantiate
            if job.faucet_type.lower() == "test":
                logger.debug(f"⏭️ Skipping legacy/test faucet job: {job.name}")
                return  # Silently complete without rescheduling

            # Instantiate Bot dynamically
            from core.registry import get_faucet_class
            bot_class = get_faucet_class(job.faucet_type)
            if not bot_class:
                raise ValueError(f"Unknown faucet type: {job.faucet_type}")

            bot = bot_class(self.settings, page)
            override = {
                "username": job.profile.username,
                "password": job.profile.password,
            }
            if "pick" in job.faucet_type.lower():
                override["email"] = job.profile.username
            bot.settings_account_override = override
            bot.set_behavior_profile(profile_name=username, profile_hint=getattr(job.profile, "behavior_profile", None))
            # Ensure bot knows about proxy
            if current_proxy:
                bot.set_proxy(current_proxy)

            # Execute the job function
            logger.info(f"🚀 Executing {job.name} ({job.job_type}) for {username}... (Proxy: {current_proxy or 'None'})")
            start_time = time.time()
            job_timeout = max(60, int(getattr(self.settings, "job_timeout_seconds", 600)))

            # Handle special job types
            if job.job_type == "auto_withdrawal_check":
                # Auto-withdrawal check doesn't need a page/bot
                result = await asyncio.wait_for(self.execute_auto_withdrawal_check(job), timeout=job_timeout)
            else:
                # Regular faucet bot method
                method = getattr(bot, job.job_type)
                result = await asyncio.wait_for(method(page), timeout=job_timeout)
            
            # Check if bot signaled that we should retry without proxy
            if (
                hasattr(bot, 'should_retry_without_proxy') 
                and bot.should_retry_without_proxy
                and getattr(self.settings, "enable_direct_fallback", True)
                and current_proxy is not None
            ):
                logger.warning(
                    f"🔄 [DIRECT FALLBACK] Proxy failed for {job.name}. "
                    f"Retrying with direct connection..."
                )
                
                # Close current context
                try:
                    await self.browser_manager.safe_close_context(context, profile_name=username)
                except Exception as cleanup_error:
                    logger.debug(f"Context cleanup error: {cleanup_error}")
                
                # Create new context WITHOUT proxy
                try:
                    context = await self.browser_manager.create_context(
                        proxy=None,  # Force direct connection
                        user_agent=ua,
                        profile_name=username,
                        locale_override=locale_hint,
                        timezone_override=timezone_hint,
                        allow_sticky_proxy=False,  # Disable sticky proxy
                        block_images_override=False if self._should_disable_image_block(job.faucet_type) else None
                    )
                    page = await self.browser_manager.new_page(context=context)
                    
                    # Create new bot instance with direct connection
                    bot = bot_class(self.settings, page)
                    bot.settings_account_override = override
                    bot.set_behavior_profile(profile_name=username, profile_hint=getattr(job.profile, "behavior_profile", None))
                    bot.current_proxy = None  # Explicitly set no proxy
                    
                    # Retry the job
                    logger.info(f"🚀 [RETRY] Executing {job.name} with DIRECT connection...")
                    method = getattr(bot, job.job_type)
                    result = await asyncio.wait_for(method(page), timeout=job_timeout)
                    
                    # Log success or failure of direct connection attempt
                    if hasattr(result, 'success') and result.success:
                        logger.info(
                            f"✅ [DIRECT FALLBACK SUCCESS] {job.name} completed via direct connection!"
                        )
                    else:
                        logger.warning(
                            f"⚠️ [DIRECT FALLBACK FAILED] {job.name} also failed without proxy: {result.status if hasattr(result, 'status') else 'Unknown'}"
                        )
                        
                except Exception as direct_error:
                    logger.error(
                        f"❌ [DIRECT FALLBACK ERROR] Direct connection retry failed: {direct_error}"
                    )
                    # Continue with original result processing

            # Post-execution status check - only if page is still alive
            page_alive = await self.browser_manager.check_page_alive(page)
            if page_alive:
                status_info = await self.browser_manager.check_page_status(page)
                if status_info["blocked"]:
                    logger.error(f"❌ SITE BLOCK DETECTED for {job.name} ({username}). Status: {status_info['status']}")
                    if current_proxy:
                        self.record_proxy_failure(current_proxy, detected=True,
                                                  status_code=status_info.get("status", 0))
                        if self.proxy_manager and getattr(self.settings, "proxy_reputation_enabled", True):
                            self.proxy_manager.record_soft_signal(current_proxy, signal_type="blocked")
                elif status_info["network_error"]:
                    logger.warning(f"⚠️ NETWORK ERROR DETECTED for {job.name} ({username}).")
                    if current_proxy:
                        self.record_proxy_failure(current_proxy, detected=False,
                                                  status_code=status_info.get("status", 0))
                        if self.proxy_manager and getattr(self.settings, "proxy_reputation_enabled", True):
                            self.proxy_manager.record_soft_signal(current_proxy, signal_type="network_error")
            else:
                logger.debug(f"Page already closed for {job.name} - skipping status check")

            duration = time.time() - start_time
            logger.info(f"[DONE] Finished {job.name} for {username} in {duration:.1f}s")

            # Check if result indicates proxy detection
            if hasattr(result, 'status') and "Proxy Detected" in result.status:
                logger.error(f"❌ Proxy detected for {job.name} ({username}). Rotating proxy...")
                if current_proxy:
                    self.record_proxy_failure(current_proxy, detected=True, status_code=403)
                # Reschedule with exponential backoff for proxy issues
                job.next_run = time.time() + PROXY_RETRY_DELAY_SECONDS * (2 ** min(job.retry_count, 4))
                job.retry_count += 1  # Track consecutive proxy failures
                self.add_job(job)
                return

            # Reschedule based on result
            if hasattr(result, 'next_claim_minutes'):
                if result.success:
                    # Reset Circuit Breaker on success
                    self.faucet_failures[job.faucet_type] = 0
                    job.retry_count = 0  # Reset retry count on success
                    # Clear error type tracking on success
                    if job.faucet_type in self.faucet_error_types:
                        self.faucet_error_types[job.faucet_type] = []
                    # Reset backoff state on success
                    if job.faucet_type in self.faucet_backoff:
                        self.faucet_backoff[job.faucet_type] = {'consecutive_failures': 0, 'next_allowed_time': 0}
                    # Record success for health monitoring
                    self.health_monitor.record_faucet_attempt(job.faucet_type, success=True)

                    # Log CAPTCHA cost details for profitability tracking
                    if hasattr(bot, 'solver') and bot.solver:
                        solver_stats = bot.solver.provider_stats.get(
                            bot.solver.provider, {}
                        )
                        if solver_stats.get('cost', 0) > 0:
                            logger.info(
                                f"💰 CAPTCHA Cost for {job.faucet_type}: "
                                f"${solver_stats['cost']:.4f} | "
                                f"Earned: {result.amount} | Balance: {result.balance}"
                            )
                else:
                    # Record failure for health monitoring
                    self.health_monitor.record_faucet_attempt(job.faucet_type, success=False)

                    # Classify the error type
                    error_type = ErrorType.UNKNOWN
                    if hasattr(result, 'error_type') and isinstance(result.error_type, ErrorType):
                        error_type = result.error_type
                    else:
                        # Fallback classification based on status message
                        status_lower = result.status.lower()
                        # Check for configuration errors first (more specific than permanent)
                        if any(
                            config in status_lower
                            for config in [
                                "hcaptcha", "recaptcha", "turnstile",
                                "captcha config", "solver config", "api key"
                            ]
                        ):
                            error_type = ErrorType.CONFIG_ERROR
                        # Security/Cloudflare challenges should be retryable, not permanent
                        elif any(
                            security in status_lower
                            for security in [
                                "cloudflare", "security check", "maintenance",
                                "ddos protection", "blocked", "challenge"
                            ]
                        ):
                            error_type = ErrorType.RATE_LIMIT
                        elif any(
                            perm in status_lower
                            for perm in ["banned", "suspended", "invalid credentials", "auth failed"]
                        ):
                            error_type = ErrorType.PERMANENT
                        elif any(
                            rate in status_lower
                            for rate in ["too many requests", "slow down", "rate limit"]
                        ):
                            error_type = ErrorType.RATE_LIMIT
                        elif any(
                            proxy in status_lower
                            for proxy in ["proxy", "vpn detected", "unusual activity"]
                        ):
                            error_type = ErrorType.PROXY_ISSUE
                        elif "captcha" in status_lower and "failed" in status_lower:
                            error_type = ErrorType.CAPTCHA_FAILED
                        elif "timeout" in status_lower or "connection" in status_lower:
                            error_type = ErrorType.TRANSIENT

                    # Track error type for circuit breaker intelligence
                    self._track_error_type(job.faucet_type, error_type)

                    logger.info(f"🔍 Error classified as: {error_type.value} for {job.name}")

                    # Handle withdrawal job failures differently
                    if "withdraw" in job.job_type.lower():
                        # Withdrawal-specific retry logic with exponential backoff
                        if (
                            job.retry_count
                            >= self.settings.withdrawal_max_retries
                        ):
                            logger.error(
                                f"❌ Withdrawal failed {job.retry_count} times for {job.name}. "
                                f"Max retries reached. Skipping."
                            )
                            # Don't reschedule - mark as permanently failed
                            # Log to analytics
                            try:
                                from core.withdrawal_analytics import get_analytics
                                analytics = get_analytics()
                                analytics.record_withdrawal(
                                    faucet=job.faucet_type,
                                    cryptocurrency="BTC",
                                    amount=0.0,
                                    network_fee=0.0,
                                    platform_fee=0.0,
                                    withdrawal_method="unknown",
                                    status="failed",
                                    notes=(
                                        f"Max retries ({self.settings.withdrawal_max_retries}) "
                                        f"exceeded: {result.status}"
                                    )
                                )
                            except Exception:
                                pass
                            return
                        else:
                            # Use configured retry intervals
                            retry_interval = self.settings.withdrawal_retry_intervals[
                                min(
                                    job.retry_count,
                                    len(self.settings.withdrawal_retry_intervals) - 1
                                )
                            ]
                            job.next_run = time.time() + retry_interval
                            job.retry_count += 1
                            logger.warning(
                                f"⚠️ Withdrawal failed for {job.name}. "
                                f"Retry {job.retry_count}/{self.settings.withdrawal_max_retries} "
                                f"in {retry_interval/3600:.1f}h"
                            )
                            self.add_job(job)
                            return
                    else:
                        # Handle PERMANENT errors - disable account (retry security challenges)
                        if error_type == ErrorType.PERMANENT:
                            # Check if misclassified security challenge
                            status_lower = result.status.lower()
                            is_security_challenge = any(
                                security in status_lower
                                for security in [
                                    "cloudflare", "security check", "maintenance",
                                    "ddos protection", "blocked", "challenge"
                                ]
                            )

                            if is_security_challenge:
                                # Treat as RATE_LIMIT instead
                                logger.warning(
                                    f"⚠️ Reclassifying security challenge as "
                                    f"RATE_LIMIT instead of PERMANENT for {job.name}"
                                )
                                error_type = ErrorType.RATE_LIMIT
                            else:
                                # True permanent failure (banned, invalid credentials, etc.)
                                logger.error(
                                    f"❌ PERMANENT FAILURE: {job.name} - {result.status}"
                                )
                                logger.error(f"🚫 Disabling account: {job.profile.username} for {job.faucet_type}")
                                # Don't requeue permanent failures
                                return

                        # Track security challenge retries (for RATE_LIMIT errors that might be challenges)
                        if error_type == ErrorType.RATE_LIMIT:
                            retry_key = f"{job.faucet_type}:{job.profile.username}"
                            current_time = time.time()

                            if retry_key not in self.security_challenge_retries:
                                self.security_challenge_retries[retry_key] = {
                                    "security_retries": 0,
                                    "last_retry_time": current_time
                                }

                            retry_state = self.security_challenge_retries[retry_key]

                            # Reset counter if last retry was more than 24 hours ago
                            if (
                                current_time - retry_state["last_retry_time"]
                                > (self.security_retry_reset_hours * 3600)
                            ):
                                logger.info(
                                    f"🔄 Resetting security retry counter for {retry_key} "
                                    f"(last retry was "
                                    f"{(current_time - retry_state['last_retry_time'])/3600:.1f}h ago)"
                                )
                                retry_state["security_retries"] = 0

                            retry_state["security_retries"] += 1
                            retry_state["last_retry_time"] = current_time

                            # Check if we've exceeded max security retries
                            if (
                                retry_state["security_retries"]
                                >= self.max_security_retries
                            ):
                                logger.error(
                                    f"❌ Security challenge retry limit exceeded "
                                    f"({self.max_security_retries}) for {job.name}"
                                )
                                logger.error(
                                    f"🚫 Temporarily disabling account: "
                                    f"{job.profile.username} for {job.faucet_type}"
                                )
                                logger.info(
                                    f"💡 TIP: Retry counter will reset after "
                                    f"{self.security_retry_reset_hours}h of no challenges"
                                )
                                logger.info(f"💡 To manually re-enable, restart the bot or use reset_security_retries()")
                                # Don't requeue if retry limit exceeded
                                return
                            else:
                                logger.info(
                                    f"⚠️ Security challenge retry "
                                    f"{retry_state['security_retries']}/{self.max_security_retries} "
                                    f"for {job.name}"
                                )

                        # Update backoff state - increment consecutive failures
                        if job.faucet_type not in self.faucet_backoff:
                            self.faucet_backoff[job.faucet_type] = {'consecutive_failures': 0, 'next_allowed_time': 0}
                        self.faucet_backoff[job.faucet_type]['consecutive_failures'] += 1

                        # Calculate intelligent retry delay with exponential backoff + jitter
                        retry_delay = self.calculate_retry_delay(
                            job.faucet_type, error_type
                        )

                        if retry_delay == float('inf'):
                            logger.error(
                                f"❌ Permanent error - not rescheduling {job.name}"
                            )
                            return

                        # Update next allowed time for this faucet
                        next_allowed = time.time() + retry_delay
                        self.faucet_backoff[job.faucet_type]['next_allowed_time'] = next_allowed

                        logger.info(
                            f"📅 Rescheduling {job.name} in {retry_delay:.0f}s with backoff "
                            f"(failures: {self.faucet_backoff[job.faucet_type]['consecutive_failures']})"
                        )

                        # Handle FAUCET_DOWN - skip entire faucet
                        if error_type == ErrorType.FAUCET_DOWN:
                            logger.warning(
                                f"⚠️ Faucet appears down: {job.faucet_type}. "
                                f"Skipping for {retry_delay/3600:.1f}h."
                            )
                            self.faucet_cooldowns[job.faucet_type] = next_allowed

                        # Check if circuit breaker should trip
                        if self._should_trip_circuit_breaker(job.faucet_type, error_type):
                            self.faucet_failures[job.faucet_type] = (
                                self.faucet_failures.get(job.faucet_type, 0) + 1
                            )
                            if self.faucet_failures[job.faucet_type] >= self.CIRCUIT_BREAKER_THRESHOLD:
                                logger.error(
                                    f"🔌 CIRCUIT BREAKER TRIPPED: {job.faucet_type} "
                                    f"failed {self.CIRCUIT_BREAKER_THRESHOLD} times "
                                    f"(error: {error_type.value})"
                                )
                                self.faucet_cooldowns[job.faucet_type] = (
                                    time.time() + self.CIRCUIT_BREAKER_COOLDOWN
                                )
                        else:
                            logger.debug(
                                "⚡ Transient error - not counting toward circuit breaker"
                            )

                        # Set next run time with backoff delay
                        job.next_run = next_allowed

                # For successful claims, use normal timing with small jitter
                if result.success:
                    wait_time = result.next_claim_minutes * 60
                    # Add jitter for non-withdrawal jobs
                    if "withdraw" not in job.job_type.lower():
                        wait_time += random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
                    job.next_run = time.time() + wait_time
                    job.retry_count = 0
                    job.retry_count = 0
                self.add_job(job)

        except asyncio.TimeoutError:
            logger.error(
                f"⏱️ Job timeout for {job.name} ({username}) "
                f"after {getattr(self.settings, 'job_timeout_seconds', 600)}s"
            )
            from faucets.base import ClaimResult
            result = ClaimResult(success=False, status="Timeout", next_claim_minutes=15, error_type=ErrorType.TRANSIENT)
            try:
                self.health_monitor.record_faucet_attempt(
                    job.faucet_type, success=False
                )
            except Exception:
                pass
            job.retry_count += 1
            job.next_run = time.time() + PROXY_COOLDOWN_SECONDS
            self.add_job(job)
        except Exception as e:
            logger.error(f"❌ Error in job {job.name} for {username}: {e}")
            # Retry logic
            self.consecutive_job_failures += 1
            if self.consecutive_job_failures >= MAX_CONSECUTIVE_JOB_FAILURES:
                logger.warning(
                    f"⚠️ {self.consecutive_job_failures} consecutive job failures. Triggering browser restart.")
                await self.browser_manager.restart()
                self.consecutive_job_failures = 0

            # Withdrawal-specific exception handling
            if "withdraw" in job.job_type.lower():
                if job.retry_count >= self.settings.withdrawal_max_retries:
                    logger.error(
                        f"❌ Withdrawal exception for {job.name} after {job.retry_count} retries. Max retries reached.")
                    # Log failed withdrawal
                    try:
                        from core.withdrawal_analytics import get_analytics
                        analytics = get_analytics()
                        analytics.record_withdrawal(
                            faucet=job.faucet_type,
                            cryptocurrency="BTC",
                            amount=0.0,
                            network_fee=0.0,
                            platform_fee=0.0,
                            withdrawal_method="unknown",
                            status="failed",
                            notes=f"Exception after {job.retry_count} retries: {str(e)}"
                        )
                    except Exception:
                        pass
                    return  # Don't reschedule
                else:
                    # Use configured retry intervals for withdrawals
                    retry_interval = self.settings.withdrawal_retry_intervals[
                        min(
                            job.retry_count,
                            len(self.settings.withdrawal_retry_intervals) - 1
                        )
                    ]
                    job.next_run = time.time() + retry_interval
                    job.retry_count += 1
                    logger.warning(
                        f"⚠️ Withdrawal exception for {job.name}. "
                        f"Retry {job.retry_count}/{self.settings.withdrawal_max_retries} "
                        f"in {retry_interval/3600:.1f}h"
                    )
                    self.add_job(job)
            else:
                # Standard exponential backoff for non-withdrawal jobs
                job.retry_count += 1
                retry_delay = min(PROXY_COOLDOWN_SECONDS * (2 ** job.retry_count), MAX_RETRY_BACKOFF_SECONDS)
                job.next_run = time.time() + retry_delay
                self.add_job(job)

        finally:
            # Record runtime costs (time/proxy) per faucet
            try:
                duration = max(0.0, time.time() - start_time)
                from core.analytics import get_tracker
                tracker = get_tracker()
                tracker.record_runtime_cost(
                    faucet=job.faucet_type,
                    duration_seconds=duration,
                    time_cost_per_hour=getattr(self.settings, "time_cost_per_hour_usd", 0.0),
                    proxy_cost_per_hour=getattr(self.settings, "proxy_cost_per_hour_usd", 0.0),
                    proxy_used=bool(current_proxy)
                )
            except Exception as cost_error:
                logger.debug(f"Runtime cost tracking failed: {cost_error}")
            try:
                if context:
                    # Use safe context closure with automatic health checks and cookie saving
                    await self.browser_manager.safe_close_context(
                        context,
                        profile_name=username if "withdraw" not in job.job_type else None
                    )
            except Exception as cleanup_error:
                # Additional safety net - shouldn't normally reach here with safe_close_context
                logger.debug(f"Final cleanup exception for {job.name}: {cleanup_error}")
            self.profile_concurrency[username] -= 1
            job_key = f"{username}:{job.name}"
            if job_key in self.running_jobs:
                del self.running_jobs[job_key]

    async def scheduler_loop(self) -> None:
        """Main event loop for the scheduler.

        Runs continuously until :meth:`stop` is called.  Each iteration:

        1. Perform maintenance (heartbeat, session persistence, health
           checks, mode evaluation).
        2. Find jobs whose ``next_run <= now``.
        3. Enforce global and per-profile concurrency limits.
        4. Enforce domain rate-limiting.
        5. Spawn ``asyncio.Task`` instances for eligible jobs.
        6. Sleep dynamically until the next job is ready or a timeout.
        """
        logger.info("Job Scheduler loop started.")

        # Initialize withdrawal jobs on first run
        withdrawal_jobs_scheduled = False

        while not self._stop_event.is_set():
            now = time.time()

            # Apply operation mode restrictions periodically
            mode_delay = self.check_and_update_mode()

            # Determine degraded mode based on proxy availability and failure rate
            degraded_mode = None
            delay_multiplier = 1.0
            effective_max_concurrent_bots = self.settings.max_concurrent_bots

            if self.proxy_manager:
                proxy_count = len(self.proxy_manager.proxies)
                if proxy_count == 0:
                    degraded_mode = "maintenance"
                elif proxy_count < self.settings.low_proxy_threshold:
                    degraded_mode = "low_proxy"
                    effective_max_concurrent_bots = min(effective_max_concurrent_bots,
                                                        self.settings.low_proxy_max_concurrent_bots)

            if self.consecutive_job_failures >= self.settings.degraded_failure_threshold:
                delay_multiplier = self.settings.degraded_slow_delay_multiplier
                effective_max_concurrent_bots = max(1, int(effective_max_concurrent_bots / 2))
                degraded_mode = f"{degraded_mode}+slow" if degraded_mode else "slow"

            if mode_delay > delay_multiplier:
                delay_multiplier = mode_delay

            if self.performance_alert_score >= self.settings.performance_alert_slow_threshold:
                delay_multiplier = max(delay_multiplier, self.settings.degraded_slow_delay_multiplier)
                effective_max_concurrent_bots = max(1, int(effective_max_concurrent_bots / 2))
                degraded_mode = f"{degraded_mode}+perf" if degraded_mode else "perf"

            # Schedule withdrawal jobs once at startup
            if not withdrawal_jobs_scheduled:
                try:
                    await self.schedule_withdrawal_jobs()
                    # Also schedule automated withdrawal check
                    if not self.withdrawal_check_scheduled:
                        await self.schedule_auto_withdrawal_check()
                    withdrawal_jobs_scheduled = True
                except Exception as e:
                    logger.warning(f"Failed to schedule withdrawal jobs: {e}")
                    withdrawal_jobs_scheduled = True  # Don't retry every loop

            # Maintenance tasks (heartbeat and session persistence)
            if now - self.last_heartbeat_time >= HEARTBEAT_INTERVAL_SECONDS:
                self._write_heartbeat()
                self.last_heartbeat_time = now

            if now - self.last_persist_time >= SESSION_PERSIST_INTERVAL:
                self._persist_session()
                self.last_persist_time = now

                # Check for performance alerts every persist interval (5 mins)
                # This ensures we don't spam logs but stay updated on drops
                from core.analytics import get_tracker
                alerts = get_tracker().check_performance_alerts(hours=2)
                self.performance_alert_score = len(alerts)
                for alert in alerts:
                    logger.warning(f"🔔 ALERT: {alert}")

                # Fix #27: Log profitability summary every 5 minutes
                profit = get_tracker().get_profitability(hours=24)
                logger.info(
                    f"💰 PROFITABILITY: Earnings ${profit['earnings_usd']:.4f} | "
                    f"Costs ${profit['costs_usd']:.4f} | "
                    f"Net ${profit['net_profit_usd']:.4f} | ROI {profit['roi']:.2f}x"
                )

            if now - self.last_health_check_time >= BROWSER_HEALTH_CHECK_INTERVAL:
                logger.info("🏥 Performing comprehensive health check...")

                # Run full health check (browser, proxy, faucet, system)
                try:
                    health_results = await self.health_monitor.run_full_health_check()

                    # Auto-restart browser if needed
                    if self.health_monitor.should_restart_browser():
                        logger.critical("🔄 Browser health critical - triggering automatic restart")
                        await self.browser_manager.restart()
                        # Reset failure count after restart
                        self.health_monitor.browser_context_failures = 0

                    # Auto-response: replenish proxies if unhealthy
                    proxy_health = health_results.get("proxy", {})
                    if self.proxy_manager and not proxy_health.get("healthy", True):
                        await self.proxy_manager.auto_provision_proxies(
                            min_threshold=self.settings.low_proxy_threshold,
                            provision_count=5
                        )

                    # Auto-response: degrade mode on system health issues
                    system_health = health_results.get("system", {})
                    if not system_health.get("healthy", True):
                        from core.config import OperationMode
                        self.current_mode = OperationMode.SLOW_MODE
                        self.apply_mode_restrictions(self.current_mode)

                    # Log summary
                    logger.info(
                        f"Health check complete - Overall: "
                        f"{'✅ HEALTHY' if health_results['overall_healthy'] else '⚠️ DEGRADED'}"
                    )

                except Exception as e:
                    logger.error(f"Health check failed: {e}")

                self.last_health_check_time = now

            # 1. Check for ready jobs
            ready_jobs = [j for j in self.queue if j.next_run <= now]
            ready_jobs.sort()  # Sorted by priority then time

            # 2. Try to launch jobs
            for job in ready_jobs:
                username = job.profile.username
                active_global = len(self.running_jobs)
                active_profile = self.profile_concurrency.get(username, 0)

                if degraded_mode == "maintenance":
                    logger.warning("🛑 Maintenance Mode: No proxies available. Pausing new jobs.")
                    break

                # Check constraints
                if active_global >= effective_max_concurrent_bots:
                    break  # Global limit reached

                # Use a default if max_concurrent_per_profile is not yet in config
                max_per_profile = getattr(self.settings, 'max_concurrent_per_profile', 1)
                if active_profile >= max_per_profile:
                    continue  # Profile limit reached, try next job

                # Check domain rate limiting
                domain_delay = self.get_domain_delay(job.faucet_type)
                if delay_multiplier > 1.0:
                    domain_delay *= delay_multiplier
                if domain_delay > 0:
                    logger.debug(f"⏳ Rate limit: {job.name} must wait {domain_delay:.1f}s for {job.faucet_type}")
                    job.next_run = now + domain_delay
                    continue  # Skip for now, will be picked up next iteration

                # Check Circuit Breaker
                if job.faucet_type in self.faucet_cooldowns:
                    cooldown_end = self.faucet_cooldowns[job.faucet_type]
                    if now < cooldown_end:
                        logger.debug(
                            f"🔌 Circuit Breaker Active: Skipping {job.faucet_type} until {time.ctime(cooldown_end)}")
                        job.next_run = now + 600  # Check back in 10 mins
                        continue
                    else:
                        # Cooldown expired, reset
                        del self.faucet_cooldowns[job.faucet_type]
                        self.faucet_failures[job.faucet_type] = 0
                        logger.info(f"🟢 Circuit Breaker Reset: Resuming {job.faucet_type}")

                # Budget-Aware Job Selection (Skip jobs we can't afford)
                if "withdraw" not in job.job_type.lower():  # Only check for claim jobs
                    try:
                        # Get captcha solver budget status
                        from solvers.captcha import CaptchaSolver
                        api_key = self.settings.twocaptcha_api_key or self.settings.capsolver_api_key
                        if not api_key:
                            logger.warning("Captcha API key missing; skipping budget check.")
                            budget_stats = {"remaining": float("inf")}
                        else:
                            temp_solver = CaptchaSolver(
                                api_key=api_key,
                                provider=self.settings.captcha_provider,
                                daily_budget=self.settings.captcha_daily_budget
                            )
                            budget_stats = temp_solver.get_budget_stats()
                        estimated_cost = self.estimate_claim_cost(job.faucet_type)

                        if budget_stats["remaining"] < estimated_cost:
                            logger.warning(
                                f"💰 Budget insufficient for {job.name}: "
                                f"Need ${estimated_cost:.4f}, have ${budget_stats['remaining']:.4f}. "
                                f"Deferring claim."
                            )
                            # Defer to next budget reset (tomorrow)
                            import time as time_module
                            tomorrow = time_module.strftime("%Y-%m-%d", time_module.localtime(now + 86400))
                            tomorrow_midnight = time_module.mktime(time_module.strptime(tomorrow, "%Y-%m-%d"))
                            job.next_run = tomorrow_midnight + 300  # 5 min after midnight
                            continue

                        # Check if this is a high-value claim but budget is very low
                        if budget_stats["remaining"] < 0.50 and estimated_cost > 0.002:
                            # Calculate profitability to determine if manual solve is worth it
                            try:
                                from core.analytics import get_tracker
                                tracker = get_tracker()
                                faucet_stats = tracker.get_faucet_stats(hours=168)
                                avg_earnings = faucet_stats.get(job.faucet_type.lower(), {}).get("avg_earnings_usd", 0)

                                if avg_earnings > estimated_cost * 2:  # At least 2x ROI
                                    logger.warning(
                                        f"⚠️ Budget low but {job.name} is profitable (${avg_earnings:.4f} avg). "
                                        f"Consider manual CAPTCHA solve if available."
                                    )
                                    # Continue with job, it might prompt for manual solve
                                else:
                                    logger.info(
                                        f"⏭️ Skipping low-value claim {job.name} "
                                        f"(avg ${avg_earnings:.4f}, cost ${estimated_cost:.4f})"
                                    )
                                    job.next_run = now + 3600  # Try again in 1 hour
                                    continue
                            except Exception as e:
                                logger.debug(f"Profitability check failed: {e}")
                    except Exception as e:
                        logger.debug(f"Budget check failed for {job.name}: {e}")
                        # If budget check fails, allow job to proceed (fail-safe)

                # Auto-Suspend based on ROI and success rate
                if self.settings.faucet_auto_suspend_enabled:
                    should_suspend, reason = self._check_auto_suspend(job.faucet_type)
                    if should_suspend:
                        logger.warning(f"⏸️ AUTO-SUSPEND: {job.faucet_type} - {reason}")
                        self.faucet_cooldowns[job.faucet_type] = now + self.settings.faucet_auto_suspend_duration
                        job.next_run = now + 600  # Check back in 10 mins
                        continue

                # Advanced Withdrawal Scheduling (New Gen 3.0 Logic)
                if "withdraw" in job.job_type.lower() or "withdraw" in job.name.lower():
                    from core.withdrawal_analytics import get_analytics
                    from core.analytics import get_tracker

                    analytics = get_analytics()
                    tracker = get_tracker()

                    # Try to get current balance from tracker
                    cur_balance = 0.0
                    faucet_stats = tracker.get_faucet_stats(24)
                    if job.faucet_type.lower() in faucet_stats:
                        cur_balance = faucet_stats[job.faucet_type.lower()].get("earnings", 0.0)

                    # Get recommendation
                    crypto = "unknown"  # FaucetBot subclasses should probably specify this
                    recommendation = analytics.recommend_withdrawal_strategy(
                        cur_balance, crypto, job.faucet_type
                    )

                    if recommendation["action"] == "wait":
                        logger.info(f"⏳ Withdrawal Deferred for {job.name}: {recommendation['reason']}")
                        job.next_run = time.time() + 3600  # Check again in 1 hour
                        continue

                    # We can also check historical performance to skip low-yield faucets
                    f_stats = analytics.get_faucet_performance(hours=168).get(job.faucet_type, {})
                    if f_stats and f_stats.get("success_rate", 100) < 20:
                        logger.warning(f"⚠️ Skipping low-performance faucet withdrawal: {job.faucet_type}")
                        job.next_run = now + 86400  # Try again tomorrow
                        continue

                # Record that we're accessing this domain
                self.record_domain_access(job.faucet_type)

                # Launch Job
                self.queue.remove(job)
                job_key = f"{username}:{job.name}"
                task = asyncio.create_task(self._run_job_wrapper(job))
                self.running_jobs[job_key] = task

            # 3. Dynamic sleep
            if not self.queue and not self.running_jobs:
                sleep_time = 60
            elif not self.queue:
                sleep_time = 5
            else:
                next_run = min(j.next_run for j in self.queue)
                sleep_time = max(0.1, min(next_run - now, 10.0))

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_time)
                break  # Stop event set during sleep
            except asyncio.TimeoutError:
                pass  # Sleep completed

    def stop(self) -> None:
        """Stop the scheduler, persist session state, and signal the loop."""
        self._persist_session()
        self._stop_event.set()

    async def cleanup(self) -> None:
        """Release resources held by the scheduler.

        Closes the :class:`WalletDaemon` aiohttp session (if the
        auto-withdrawal subsystem was initialised).
        """
        try:
            # Close wallet daemon session if initialized
            if hasattr(self, 'auto_withdrawal') and self.auto_withdrawal:
                if hasattr(self.auto_withdrawal, 'wallet'):
                    await self.auto_withdrawal.wallet.close()
                    logger.info("✅ WalletDaemon session closed")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
