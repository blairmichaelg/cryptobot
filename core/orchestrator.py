import asyncio
import logging
import time
import random
import json
import os
import inspect
import shutil
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Callable, Any, Union, TYPE_CHECKING
from datetime import datetime, timezone, timedelta
from enum import Enum
from core.config import BotSettings, AccountProfile, CONFIG_DIR, LOGS_DIR
from playwright.async_api import Page, BrowserContext

if TYPE_CHECKING:
    from faucets.base import ClaimResult

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """Classification of error types for intelligent recovery."""
    TRANSIENT = "transient"  # Network timeout, temporary unavailable
    RATE_LIMIT = "rate_limit"  # 429, cloudflare challenge
    PROXY_ISSUE = "proxy_issue"  # Proxy detection, IP blocked
    PERMANENT = "permanent"  # Auth failed, account banned
    FAUCET_DOWN = "faucet_down"  # 500/503 server errors
    CAPTCHA_FAILED = "captcha_failed"  # Captcha solve timeout
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
    priority: int
    next_run: float
    name: str = field(compare=False)
    profile: AccountProfile = field(compare=False)
    faucet_type: str = field(compare=False)
    job_type: str = field(compare=False, default="claim_wrapper")
    retry_count: int = field(default=0, compare=False)

    def to_dict(self):
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
    def from_dict(cls, data):
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
        
        # Startup Checks
        if self.proxy_manager:
             if len(self.proxy_manager.proxies) < 3:
                 logger.warning(f"⚠️ LOW PROXY COUNT: Only {len(self.proxy_manager.proxies)} proxies detected. Recommended: 3+ for stealth.")
        
        self.profile_concurrency: Dict[str, int] = {}  # Key: profile.username
        self._stop_event = asyncio.Event()
        
        # Proxy rotation tracking
        self.proxy_failures: Dict[str, Dict[str, Any]] = {}  # Key: proxy URL
        self.proxy_index: Dict[str, int] = {}  # Key: profile.username
        
        # Circuit Breaker Tracking with Error Type Awareness
        self.faucet_failures: Dict[str, int] = {} # Key: faucet_type
        self.faucet_error_types: Dict[str, List[ErrorType]] = {} # Track recent error types per faucet
        self.faucet_cooldowns: Dict[str, float] = {} # Key: faucet_type, Value: timestamp
        self.CIRCUIT_BREAKER_THRESHOLD = 5
        self.CIRCUIT_BREAKER_COOLDOWN = 14400 # 4 hours
        self.RETRYABLE_COOLDOWN = 600  # 10 minutes for temporary failures
        
        # Failure classification (legacy - replaced by ErrorType enum)
        self.PERMANENT_FAILURES = ["auth_failed", "account_banned", "account_disabled", "invalid_credentials"]
        self.RETRYABLE_FAILURES = ["proxy_blocked", "proxy_detection", "cloudflare", "rate_limit", "timeout", "connection_error"]
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
        
        # Try to restore session on init
        self._restore_session()

    def _restore_session(self):
        """Restore job queue from disk if available."""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                
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
                logger.info(f"Attempting recovery from backup")
                try:
                    shutil.copy2(filepath + ".backup.1", filepath)
                except Exception as restore_err:
                    logger.error(f"Backup restoration failed: {restore_err}")

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

    def _write_heartbeat(self):
        """Write heartbeat file for external monitoring."""
        try:
            with open(self.heartbeat_file, "w") as f:
                f.write(f"{time.time()}\n{len(self.queue)} jobs\n{len(self.running_jobs)} running")
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
            profitability = tracker.get_faucet_profitability(hours=24)

            if faucet_type in stats:
                success_rate = stats[faucet_type].get('success_rate', 50) / 100
                earnings_per_hour = hourly.get(faucet_type, 0)

                # Normalize earnings (assume 100 satoshi/hour is baseline)
                earnings_factor = min(1 + (earnings_per_hour / 100), 2.0)

                roi = profitability.get(faucet_type, {}).get("roi", 0.0)
                roi_factor = max(0.3, min(1.0 + roi, 2.0))

                # Combine factors: success rate, earnings, ROI
                priority = (success_rate * 0.5) + (earnings_factor * 0.3) + (roi_factor * 0.2)
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
            
            if faucet_type not in stats:
                return False, ""
            
            faucet_stats = stats[faucet_type]
            
            # Check minimum samples
            if faucet_stats['total'] < self.settings.faucet_auto_suspend_min_samples:
                return False, ""
            
            # Check success rate
            success_rate = faucet_stats['success_rate']
            if success_rate < self.settings.faucet_min_success_rate:
                return True, f"Low success rate: {success_rate:.1f}% (threshold: {self.settings.faucet_min_success_rate}%)"
            
            # Check ROI using tracked costs (require at least one success/earning)
            success_count = faucet_stats.get("success", 0)
            earnings = faucet_stats.get("earnings", 0.0)
            if success_count > 0 and earnings > 0:
                profitability = get_tracker().get_faucet_profitability(hours=24)
                faucet_profit = profitability.get(faucet_type, {})
                roi = faucet_profit.get("roi")

                if roi is not None and roi < self.settings.faucet_roi_threshold:
                    return True, f"Negative ROI: {roi:.2f} (threshold: {self.settings.faucet_roi_threshold})"
            
            return False, ""
            
        except Exception as e:
            logger.debug(f"Auto-suspend check failed for {faucet_type}: {e}")
            return False, ""

    async def schedule_withdrawal_jobs(self):
        """
        Automatically schedule withdrawal jobs for all faucets with withdraw() support.
        
        Timing strategy:
        - Initial check: 24-72h depending on earnings rate
        - Repeat: Every 24-72h depending on earnings rate
        - Priority: Low (don't interfere with claiming)
        - Timing: Prefer off-peak hours (0-5 UTC, 22-23 UTC, weekends)
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
            logger.info(f"Scheduled withdrawal job for {profile.faucet} ({profile.username}) at {datetime.fromtimestamp(next_withdrawal_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        
        logger.info(f"Withdrawal job scheduling complete: {scheduled_count} jobs scheduled")

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
            current_proxy = self.get_next_proxy(profile)
            
            # Create context
            ua = random.choice(self.settings.user_agents) if self.settings.user_agents else None
            locale_hint, timezone_hint = await self._get_proxy_locale_timezone(current_proxy)
            context = await self.browser_manager.create_context(
                proxy=current_proxy,
                user_agent=ua,
                profile_name=profile.username,
                locale_override=locale_hint,
                timezone_override=timezone_hint
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
            bot.set_behavior_profile(profile_name=profile.username, profile_hint=getattr(profile, "behavior_profile", None))
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
                    await self.browser_manager.save_cookies(context, profile.username)
                    await context.close()
                except Exception as cleanup_error:
                    logger.warning(f"Context cleanup failed: {cleanup_error}")

    def add_job(self, job: Job):
        """
        Add a job to the priority queue with deduplication.
        
        Prevents duplicate pending jobs for the same profile + faucet + job_type.
        """
        username = job.profile.username
        job_key = f"{username}:{job.job_type}:{job.faucet_type}"
        
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

    
    def get_next_proxy(self, profile: AccountProfile) -> Optional[str]:
        """
        Get the next proxy for a profile based on rotation strategy.
        Delegates to ProxyManager if available for advanced rotation.
        """
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

    def record_proxy_failure(self, proxy: str, detected: bool = False):
        """Record a proxy failure, delegating to ProxyManager if available."""
        if self.proxy_manager:
            self.proxy_manager.record_failure(proxy, detected=detected)
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
        TRANSIENT errors don't trip the breaker.
        """
        if error_type == ErrorType.TRANSIENT:
            return False
        
        if error_type == ErrorType.PERMANENT:
            return True
        
        # For PROXY_ISSUE, only trip if we see it repeatedly
        if error_type == ErrorType.PROXY_ISSUE:
            recent_errors = self.faucet_error_types.get(faucet_type, [])
            proxy_error_count = sum(1 for e in recent_errors if e == ErrorType.PROXY_ISSUE)
            return proxy_error_count >= 3
        
        return True  # Default: count toward breaker
    
    def _get_recovery_delay(self, error_type: ErrorType, retry_count: int, current_proxy: Optional[str]) -> tuple[float, str]:
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
                self.record_proxy_failure(current_proxy, detected=True)
                return 1800, "Rotate proxy, requeue +30min"
            else:
                return 1800, "No proxy available, requeue +30min"
        
        elif error_type == ErrorType.PERMANENT:
            # Don't requeue - will be handled by caller
            return float('inf'), "Permanent failure - account disabled"
        
        elif error_type == ErrorType.FAUCET_DOWN:
            return 14400, "Faucet down - skip 4 hours"
        
        elif error_type == ErrorType.CAPTCHA_FAILED:
            return 900, "Captcha failed - requeue +15min"
        
        else:  # UNKNOWN
            return 600, "Unknown error - requeue +10min"

    async def _run_job_wrapper(self, job: Job):
        """Wraps job execution with context management and error handling."""
        context = None
        username = job.profile.username
        current_proxy = None
        try:
            self.profile_concurrency[username] = self.profile_concurrency.get(username, 0) + 1
            
            # Get proxy using rotation logic
            current_proxy = self.get_next_proxy(job.profile)
            
            # Create isolated context for the job
            ua = random.choice(self.settings.user_agents) if self.settings.user_agents else None
            # Sticky Session: Pass profile_name
            locale_hint, timezone_hint = await self._get_proxy_locale_timezone(current_proxy)
            context = await self.browser_manager.create_context(
                proxy=current_proxy,
                user_agent=ua,
                profile_name=username,
                locale_override=locale_hint,
                timezone_override=timezone_hint
            )
            page = await self.browser_manager.new_page(context=context)
            
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
            
            method = getattr(bot, job.job_type)
            result = await method(page)
            
            # Post-execution status check
            status_info = await self.browser_manager.check_page_status(page)
            if status_info["blocked"]:
                 logger.error(f"❌ SITE BLOCK DETECTED for {job.name} ({username}). Status: {status_info['status']}")
                 self.record_proxy_failure(current_proxy, detected=True)
            elif status_info["network_error"]:
                 logger.warning(f"⚠️ NETWORK ERROR DETECTED for {job.name} ({username}).")
                 self.record_proxy_failure(current_proxy, detected=False)

            duration = time.time() - start_time
            logger.info(f"[DONE] Finished {job.name} for {username} in {duration:.1f}s")

            # Check if result indicates proxy detection
            if hasattr(result, 'status') and "Proxy Detected" in result.status:
                logger.error(f"❌ Proxy detected for {job.name} ({username}). Rotating proxy...")
                if current_proxy:
                    self.record_proxy_failure(current_proxy, detected=True)
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
                else:
                    # Classify the error type
                    error_type = ErrorType.UNKNOWN
                    if hasattr(result, 'error_type') and isinstance(result.error_type, ErrorType):
                        error_type = result.error_type
                    else:
                        # Fallback classification based on status message
                        status_lower = result.status.lower()
                        if any(perm in status_lower for perm in ["banned", "suspended", "invalid credentials", "auth failed"]):
                            error_type = ErrorType.PERMANENT
                        elif any(rate in status_lower for rate in ["too many requests", "slow down", "rate limit"]):
                            error_type = ErrorType.RATE_LIMIT
                        elif any(proxy in status_lower for proxy in ["proxy", "vpn detected", "unusual activity"]):
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
                        if job.retry_count >= self.settings.withdrawal_max_retries:
                            logger.error(f"❌ Withdrawal failed {job.retry_count} times for {job.name}. Max retries reached. Skipping.")
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
                                    notes=f"Max retries ({self.settings.withdrawal_max_retries}) exceeded: {result.status}"
                                )
                            except Exception:
                                pass
                            return
                        else:
                            # Use configured retry intervals
                            retry_interval = self.settings.withdrawal_retry_intervals[min(job.retry_count, len(self.settings.withdrawal_retry_intervals) - 1)]
                            job.next_run = time.time() + retry_interval
                            job.retry_count += 1
                            logger.warning(f"⚠️ Withdrawal failed for {job.name}. Retry {job.retry_count}/{self.settings.withdrawal_max_retries} in {retry_interval/3600:.1f}h")
                            self.add_job(job)
                            return
                    else:
                        # Handle PERMANENT errors - disable account
                        if error_type == ErrorType.PERMANENT:
                            logger.error(f"❌ PERMANENT FAILURE: {job.name} - {result.status}")
                            logger.error(f"🚫 Disabling account: {job.profile.username} for {job.faucet_type}")
                            # Don't requeue permanent failures
                            return
                        
                        # Get recovery delay and action
                        delay, action = self._get_recovery_delay(error_type, job.retry_count, current_proxy)
                        logger.info(f"📋 Recovery action: {action}")
                        
                        # Handle FAUCET_DOWN - skip entire faucet
                        if error_type == ErrorType.FAUCET_DOWN:
                            logger.warning(f"⚠️ Faucet appears down: {job.faucet_type}. Skipping for 4 hours.")
                            self.faucet_cooldowns[job.faucet_type] = time.time() + delay
                            job.next_run = time.time() + delay
                            self.add_job(job)
                            return
                        
                        # Check if circuit breaker should trip
                        if self._should_trip_circuit_breaker(job.faucet_type, error_type):
                            self.faucet_failures[job.faucet_type] = self.faucet_failures.get(job.faucet_type, 0) + 1
                            if self.faucet_failures[job.faucet_type] >= self.CIRCUIT_BREAKER_THRESHOLD:
                                logger.error(f"🔌 CIRCUIT BREAKER TRIPPED: {job.faucet_type} failed {self.CIRCUIT_BREAKER_THRESHOLD} times (error: {error_type.value})")
                                self.faucet_cooldowns[job.faucet_type] = time.time() + self.CIRCUIT_BREAKER_COOLDOWN
                        else:
                            logger.debug(f"⚡ Transient error - not counting toward circuit breaker")
                        
                wait_time = result.next_claim_minutes * 60
                # Add jitter for non-withdrawal jobs
                if "withdraw" not in job.job_type.lower():
                    wait_time += random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
                job.next_run = time.time() + wait_time
                if result.success:
                    job.retry_count = 0
                self.add_job(job)
            
        except Exception as e:
            logger.error(f"❌ Error in job {job.name} for {username}: {e}")
            # Retry logic
            self.consecutive_job_failures += 1
            if self.consecutive_job_failures >= MAX_CONSECUTIVE_JOB_FAILURES:
                logger.warning(f"⚠️ {self.consecutive_job_failures} consecutive job failures. Triggering browser restart.")
                await self.browser_manager.restart()
                self.consecutive_job_failures = 0

            # Withdrawal-specific exception handling
            if "withdraw" in job.job_type.lower():
                if job.retry_count >= self.settings.withdrawal_max_retries:
                    logger.error(f"❌ Withdrawal exception for {job.name} after {job.retry_count} retries. Max retries reached.")
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
                    retry_interval = self.settings.withdrawal_retry_intervals[min(job.retry_count, len(self.settings.withdrawal_retry_intervals) - 1)]
                    job.next_run = time.time() + retry_interval
                    job.retry_count += 1
                    logger.warning(f"⚠️ Withdrawal exception for {job.name}. Retry {job.retry_count}/{self.settings.withdrawal_max_retries} in {retry_interval/3600:.1f}h")
                    self.add_job(job)
            else:
                # Standard exponential backoff for non-withdrawal jobs
                job.retry_count += 1
                retry_delay = min(PROXY_COOLDOWN_SECONDS * (2 ** job.retry_count), MAX_RETRY_BACKOFF_SECONDS)
                job.next_run = time.time() + retry_delay
                self.add_job(job)
            
        finally:
            try:
                if context:
                    # Save cookies before closing if it was a successful or partially successful run
                    if "withdraw" not in job.job_type: # Skip cookie save for withdrawal-only roles if needed
                         await self.browser_manager.save_cookies(context, username)
                    await context.close()
            except Exception as cleanup_error:
                logger.warning(f"Context cleanup failed for {job.name}: {cleanup_error}")
            self.profile_concurrency[username] -= 1
            job_key = f"{username}:{job.name}"
            if job_key in self.running_jobs:
                del self.running_jobs[job_key]

    async def scheduler_loop(self):
        """
        Main event loop for the scheduler.
        
        Runs continuously until stopped. In each iteration:
        1. Performs maintenance (heartbeats, session persistence, health checks).
        2. Checks for jobs ready to run (next_run <= now).
        3. Enforces concurrency limits (global and per-profile).
        4. Enforces domain rate limiting.
        5. Spawns tasks for eligible jobs.
        6. Sleeps dynamically until the next job is ready or timeout occurs.
        """
        logger.info("Job Scheduler loop started.")
        
        # Initialize withdrawal jobs on first run
        withdrawal_jobs_scheduled = False
        
        while not self._stop_event.is_set():
            now = time.time()
            
            # Schedule withdrawal jobs once at startup
            if not withdrawal_jobs_scheduled:
                try:
                    await self.schedule_withdrawal_jobs()
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
                logger.info("Performing browser health check...")
                if not await self.browser_manager.check_health():
                    logger.warning("Browser health check failed. Restarting...")
                    await self.browser_manager.restart()
                self.last_health_check_time = now
            
            # 1. Check for ready jobs
            ready_jobs = [j for j in self.queue if j.next_run <= now]
            ready_jobs.sort()  # Sorted by priority then time
            
            # 2. Try to launch jobs
            for job in ready_jobs:
                username = job.profile.username
                active_global = len(self.running_jobs)
                active_profile = self.profile_concurrency.get(username, 0)
                
                # Check constraints
                if active_global >= self.settings.max_concurrent_bots:
                    break  # Global limit reached
                
                # Use a default if max_concurrent_per_profile is not yet in config
                max_per_profile = getattr(self.settings, 'max_concurrent_per_profile', 1)
                if active_profile >= max_per_profile:
                    continue  # Profile limit reached, try next job
                
                # Check domain rate limiting
                domain_delay = self.get_domain_delay(job.faucet_type)
                if domain_delay > 0:
                    logger.debug(f"⏳ Rate limit: {job.name} must wait {domain_delay:.1f}s for {job.faucet_type}")
                    job.next_run = now + domain_delay
                    continue  # Skip for now, will be picked up next iteration
                
                # Check Circuit Breaker
                if job.faucet_type in self.faucet_cooldowns:
                     cooldown_end = self.faucet_cooldowns[job.faucet_type]
                     if now < cooldown_end:
                         logger.debug(f"🔌 Circuit Breaker Active: Skipping {job.faucet_type} until {time.ctime(cooldown_end)}")
                         job.next_run = now + 600 # Check back in 10 mins
                         continue
                     else:
                         # Cooldown expired, reset
                         del self.faucet_cooldowns[job.faucet_type]
                         self.faucet_failures[job.faucet_type] = 0
                         logger.info(f"🟢 Circuit Breaker Reset: Resuming {job.faucet_type}")

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
                    crypto = "unknown" # FaucetBot subclasses should probably specify this
                    recommendation = analytics.recommend_withdrawal_strategy(
                        cur_balance, crypto, job.faucet_type
                    )
                    
                    if recommendation["action"] == "wait":
                        logger.info(f"⏳ Withdrawal Deferred for {job.name}: {recommendation['reason']}")
                        job.next_run = time.time() + 3600 # Check again in 1 hour
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

    def stop(self):
        """Stop the scheduler and persist final state."""
        self._persist_session()
        self._stop_event.set()

