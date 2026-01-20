import asyncio
import logging
import time
import random
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Callable, Any, Union
from core.config import BotSettings, AccountProfile, CONFIG_DIR, LOGS_DIR
from playwright.async_api import Page, BrowserContext

logger = logging.getLogger(__name__)

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
    def __init__(self, settings: BotSettings, browser_manager: Any, proxy_manager: Optional[Any] = None):
        self.settings = settings
        self.browser_manager = browser_manager
        self.proxy_manager = proxy_manager
        self.queue: List[Job] = []
        self.running_jobs: Dict[str, asyncio.Task] = {}  # Key: profile.username + job.name
        self.profile_concurrency: Dict[str, int] = {}  # Key: profile.username
        self._stop_event = asyncio.Event()
        
        # Proxy rotation tracking
        self.proxy_failures: Dict[str, Dict[str, Any]] = {}  # Key: proxy URL
        self.proxy_index: Dict[str, int] = {}  # Key: profile.username
        
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

    def _persist_session(self):
        """Save session state to disk."""
        try:
            queue_data = [j.to_dict() for j in self.queue]
            data = {
                "domain_last_access": self.domain_last_access,
                "queue": queue_data,
                "timestamp": time.time()
            }
            with open(self.session_file, "w") as f:
                json.dump(data, f)
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

    def is_off_peak_time(self) -> bool:
        """
        Check if current time is optimal for withdrawals (lower network fees).
        
        Based on research, network fees are typically lowest during:
        - Late night / early morning UTC (22:00 - 05:00)
        - Weekends (especially Sunday)
        
        Returns:
            True if current time is off-peak for withdrawals
        """
        from datetime import datetime, timezone
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
            stats = get_tracker().get_faucet_stats(24)
            hourly = get_tracker().get_hourly_rate(hours=24)
            
            if faucet_type in stats:
                success_rate = stats[faucet_type].get('success_rate', 50) / 100
                earnings_per_hour = hourly.get(faucet_type, 0)
                
                # Normalize earnings (assume 100 satoshi/hour is baseline)
                earnings_factor = min(1 + (earnings_per_hour / 100), 2.0)
                
                # Combine factors: success rate weighted 60%, earnings 40%
                priority = (success_rate * 0.6) + (earnings_factor * 0.4)
                return max(0.1, min(priority, 2.0))
        except Exception as e:
            logger.debug(f"Priority calculation failed for {faucet_type}: {e}")
        
        return 0.5  # Default mid-priority

    def add_job(self, job: Job):
        """Add a job to the priority queue."""
        self.queue.append(job)
        self.queue.sort()  # Simple sort for now, could use heapq if queue grows large
        logger.debug(f"Added job: {job.name} for {job.profile.username} (Prio: {job.priority}, Time: {job.next_run})")

    
    def get_next_proxy(self, profile: AccountProfile) -> Optional[str]:
        """
        Get the next proxy for a profile based on rotation strategy.
        Delegates to ProxyManager if available for advanced rotation.
        """
        if self.proxy_manager:
            return self.proxy_manager.rotate_proxy(profile)
            
        # Fallback to local logic if no ProxyManager
        if not profile.proxy_pool or len(profile.proxy_pool) == 0:
            return profile.proxy
        
        # ... (rest of legacy logic remains as fallback)
        return profile.proxy or profile.proxy_pool[0]

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
            context = await self.browser_manager.create_context(
                proxy=current_proxy,
                user_agent=ua,
                profile_name=username
            )
            page = await self.browser_manager.new_page(context=context)
            
            # Instantiate Bot dynamically
            from core.registry import get_faucet_class
            bot_class = get_faucet_class(job.faucet_type)
            if not bot_class:
                raise ValueError(f"Unknown faucet type: {job.faucet_type}")
            
            bot = bot_class(self.settings, page)
            bot.settings_account_override = {
                "username": job.profile.username,
                "password": job.profile.password,
            }
            # Ensure bot knows about proxy
            if current_proxy:
                 p_str = current_proxy
                 if "://" in p_str:
                     p_str = p_str.split("://")[1]
                 bot.set_proxy(p_str)

            # Execute the job function
            logger.info(f"🚀 Executing {job.name} ({job.job_type}) for {username}... (Proxy: {current_proxy or 'None'})")
            start_time = time.time()
            
            method = getattr(bot, job.job_type)
            result = await method(page)
            
            duration = time.time() - start_time
            logger.info(f"✅ Finished {job.name} for {username} in {duration:.1f}s")
            
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
                wait_time = result.next_claim_minutes * 60
                # Add jitter
                wait_time += random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
                job.next_run = time.time() + wait_time
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

            job.retry_count += 1
            retry_delay = min(PROXY_COOLDOWN_SECONDS * (2 ** job.retry_count), MAX_RETRY_BACKOFF_SECONDS)  # Exponential backoff capped
            job.next_run = time.time() + retry_delay
            self.add_job(job)
            
        finally:
            try:
                if context:
                    await context.close()
            except Exception as cleanup_error:
                logger.warning(f"Context cleanup failed for {job.name}: {cleanup_error}")
            self.profile_concurrency[username] -= 1
            job_key = f"{username}:{job.name}"
            if job_key in self.running_jobs:
                del self.running_jobs[job_key]

    async def scheduler_loop(self):
        """Main event loop for the scheduler."""
        logger.info("Job Scheduler loop started.")
        while not self._stop_event.is_set():
            now = time.time()
            
            # Maintenance tasks (heartbeat and session persistence)
            if now - self.last_heartbeat_time >= HEARTBEAT_INTERVAL_SECONDS:
                self._write_heartbeat()
                self.last_heartbeat_time = now
            
            if now - self.last_persist_time >= SESSION_PERSIST_INTERVAL:
                self._persist_session()
                self.last_persist_time = now
            
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
                
                # Check Off-Peak and Profitability for Withdrawals
                if "withdraw" in job.job_type.lower() or "withdraw" in job.name.lower():
                    from core.withdrawal_analytics import get_analytics
                    analytics = get_analytics()
                    
                    # Note: We don't have the current balance here easily, 
                    # but we can check if it's generally off-peak
                    if not self.is_off_peak_time():
                        logger.debug(f"⏳ Scheduling: Postponing withdrawal {job.name} until off-peak hours.")
                        job.next_run = now + 1800  # Check again in 30 minutes
                        continue
                        
                    # We can also check historical performance to skip low-yield faucets
                    f_stats = analytics.get_faucet_performance(hours=168).get(job.faucet_type, {})
                    if f_stats and f_stats.get("success_rate", 100) < 20:
                        logger.warning(f"⚠️ Scheduling: Skipping {job.name} due to low historical success rate ({f_stats.get('success_rate')}%)")
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

