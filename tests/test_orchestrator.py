import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from core.orchestrator import Job, JobScheduler
from core.config import BotSettings, AccountProfile


class TestJob:
    """Test suite for Job dataclass."""
    
    def test_job_creation(self):
        """Test Job dataclass can be created with all fields."""
        profile = AccountProfile(faucet="test", username="user1", password="pass1")
        
        job = Job(
            priority=1,
            next_run=time.time() + 100,
            name="test_job",
            profile=profile,
            faucet_type="faucet",
            job_type="claim_wrapper",
            retry_count=0
        )
        
        assert job.priority == 1
        assert job.name == "test_job"
        assert job.profile == profile
        assert job.faucet_type == "faucet"
        assert job.job_type == "claim_wrapper"
        assert job.retry_count == 0
    
    def test_job_ordering_by_priority(self):
        """Test that jobs are ordered by priority first."""
        profile = AccountProfile(faucet="test", username="user1", password="pass1")
        
        job1 = Job(priority=2, next_run=100.0, name="job1", profile=profile, faucet_type="f", job_type="c")
        job2 = Job(priority=1, next_run=200.0, name="job2", profile=profile, faucet_type="f", job_type="c")
        job3 = Job(priority=3, next_run=50.0, name="job3", profile=profile, faucet_type="f", job_type="c")
        
        jobs = [job1, job2, job3]
        jobs.sort()
        
        assert jobs[0].name == "job2"  # priority 1
        assert jobs[1].name == "job1"  # priority 2
        assert jobs[2].name == "job3"  # priority 3
    
    def test_job_ordering_by_next_run_when_priority_equal(self):
        """Test that jobs with same priority are ordered by next_run."""
        profile = AccountProfile(faucet="test", username="user1", password="pass1")
        
        job1 = Job(priority=1, next_run=200.0, name="job1", profile=profile, faucet_type="f")
        job2 = Job(priority=1, next_run=100.0, name="job2", profile=profile, faucet_type="f")
        job3 = Job(priority=1, next_run=150.0, name="job3", profile=profile, faucet_type="f")
        
        jobs = [job1, job2, job3]
        jobs.sort()
        
        assert jobs[0].name == "job2"  # next_run 100
        assert jobs[1].name == "job3"  # next_run 150
        assert jobs[2].name == "job1"  # next_run 200
    
    def test_job_default_retry_count(self):
        """Test that retry_count defaults to 0."""
        profile = AccountProfile(faucet="test", username="user1", password="pass1")
        
        job = Job(
            priority=1,
            next_run=100.0,
            name="test",
            profile=profile,
            faucet_type="f"
        )
        
        assert job.retry_count == 0


class TestJobScheduler:
    """Test suite for JobScheduler."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return BotSettings(
            max_concurrent_bots=2,
            max_concurrent_per_profile=1,
            user_agents=["Mozilla/5.0 Test Agent"]
        )
    
    @pytest.fixture
    def mock_browser_manager(self):
        """Create mock browser manager."""
        manager = AsyncMock()
        manager.create_context = AsyncMock()
        manager.new_page = AsyncMock()
        return manager
    
    @pytest.fixture
    def scheduler(self, settings, mock_browser_manager):
        """Create JobScheduler instance with mocked persistence."""
        with patch.object(JobScheduler, '_restore_session'), \
             patch.object(JobScheduler, '_persist_session'):
            return JobScheduler(settings, mock_browser_manager)
    
    @pytest.fixture
    def sample_profile(self):
        """Create sample account profile."""
        return AccountProfile(faucet="test", username="user1", password="pass1")
    
    def test_scheduler_initialization(self, scheduler):
        """Test JobScheduler initializes correctly."""
        assert scheduler.queue == []
        assert scheduler.running_jobs == {}
        assert scheduler.profile_concurrency == {}
        assert not scheduler._stop_event.is_set()
    
    def test_add_job(self, scheduler, sample_profile):
        """Test add_job adds and sorts jobs."""
        
        job1 = Job(priority=2, next_run=100.0, name="job1", profile=sample_profile, faucet_type="f")
        job2 = Job(priority=1, next_run=200.0, name="job2", profile=sample_profile, faucet_type="f")
        
        scheduler.add_job(job1)
        assert len(scheduler.queue) == 1
        assert scheduler.queue[0].name == "job1"
        
        scheduler.add_job(job2)
        assert len(scheduler.queue) == 2
        # Should be sorted by priority
        assert scheduler.queue[0].name == "job2"  # priority 1
        assert scheduler.queue[1].name == "job1"  # priority 2
    
    @pytest.mark.asyncio
    async def test_run_job_wrapper_success(self, scheduler, sample_profile, mock_browser_manager):
        """Test _run_job_wrapper executes job successfully."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser_manager.create_context.return_value = mock_context
        mock_browser_manager.new_page.return_value = mock_page
        
        mock_result = MagicMock()
        mock_result.next_claim_minutes = 60
        mock_method = AsyncMock(return_value=mock_result)
        
        job = Job(
            priority=1,
            next_run=time.time(),
            name="test_job",
            profile=sample_profile,
            faucet_type="test_faucet",
            job_type="test_method"
        )
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.test_method = mock_method
            
            await scheduler._run_job_wrapper(job)
            
            mock_get_class.assert_called_with("test_faucet")
            mock_browser_manager.create_context.assert_called_once()
            mock_method.assert_called_once_with(mock_page)
            
            assert len(scheduler.queue) == 1
            assert scheduler.queue[0].retry_count == 0
    
    @pytest.mark.asyncio
    async def test_run_job_wrapper_error_retry(self, scheduler, sample_profile, mock_browser_manager):
        """Test _run_job_wrapper handles errors and retries."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser_manager.create_context.return_value = mock_context
        mock_browser_manager.new_page.return_value = mock_page
        
        mock_method = AsyncMock(side_effect=Exception("Test error"))
        
        job = Job(
            priority=1,
            next_run=time.time(),
            name="test_job",
            profile=sample_profile,
            faucet_type="test_faucet",
            job_type="test_method",
            retry_count=0
        )
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.test_method = mock_method
            
            await scheduler._run_job_wrapper(job)
            
            mock_context.close.assert_called_once()
            
            assert len(scheduler.queue) == 1
            assert scheduler.queue[0].retry_count == 1
            assert scheduler.queue[0].next_run > time.time()
    
    @pytest.mark.asyncio
    async def test_run_job_wrapper_exponential_backoff(self, scheduler, sample_profile, mock_browser_manager):
        """Test retry uses exponential backoff."""
        mock_browser_manager.create_context.return_value = AsyncMock()
        mock_browser_manager.new_page.return_value = AsyncMock()
        
        mock_method = AsyncMock(side_effect=Exception("Test error"))
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.test_method = mock_method

            for retry_count in [0, 1, 2, 3]:
                scheduler.queue.clear()
                job = Job(
                    priority=1,
                    next_run=time.time(),
                    name="test_job",
                    profile=sample_profile,
                    faucet_type="test_faucet",
                    job_type="test_method",
                    retry_count=retry_count
                )
                
                start_time = time.time()
                await scheduler._run_job_wrapper(job)
                
                expected_delay = min(300 * (2 ** (retry_count + 1)), 3600)
                actual_delay = scheduler.queue[0].next_run - start_time
                
                # Loose assertion because processing time adds up
                assert abs(actual_delay - expected_delay) < 1.0

    @pytest.mark.asyncio
    async def test_scheduler_loop_processes_ready_jobs(self, scheduler, sample_profile, mock_browser_manager):
        """Test scheduler_loop processes jobs when ready."""
        mock_browser_manager.create_context.return_value = AsyncMock()
        mock_browser_manager.new_page.return_value = AsyncMock()
        
        mock_result = MagicMock(next_claim_minutes=60)
        mock_method = AsyncMock(return_value=mock_result)
        
        job = Job(
            priority=1,
            next_run=time.time() - 10,
            name="ready_job",
            profile=sample_profile,
            faucet_type="test_faucet",
            job_type="test_method"
        )
        scheduler.add_job(job)
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.test_method = mock_method
            
            loop_task = asyncio.create_task(scheduler.scheduler_loop())
            await asyncio.sleep(0.5)
            scheduler.stop()
            
            try:
                await asyncio.wait_for(loop_task, timeout=2.0)
            except asyncio.TimeoutError:
                pass
            
            # Use 'test_method' since we mocked instance.test_method
            mock_method.assert_called_once()
    
    def test_stop(self, scheduler):
        """Test stop() sets the stop event."""
        assert not scheduler._stop_event.is_set()
        scheduler.stop()
        assert scheduler._stop_event.is_set()
    
    @pytest.mark.asyncio
    async def test_scheduler_loop_stops_when_event_set(self, scheduler):
        """Test scheduler_loop exits when stop event is set."""
        loop_task = asyncio.create_task(scheduler.scheduler_loop())
        await asyncio.sleep(0.1)
        scheduler.stop()
        try:
            await asyncio.wait_for(loop_task, timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("Scheduler loop did not stop within timeout")
        assert scheduler._stop_event.is_set()


class TestWithdrawalScheduling:
    """Test suite for automated withdrawal scheduling."""
    
    @pytest.fixture
    def settings_with_accounts(self):
        """Create settings with account profiles."""
        return BotSettings(
            max_concurrent_bots=2,
            max_concurrent_per_profile=1,
            user_agents=["Mozilla/5.0 Test Agent"],
            prefer_off_peak_withdrawals=True,
            withdrawal_retry_intervals=[3600, 21600, 86400],
            withdrawal_max_retries=3,
            accounts=[
                AccountProfile(faucet="firefaucet", username="test_user1", password="pass1", enabled=True),
                AccountProfile(faucet="cointiply", username="test_user2", password="pass2", enabled=True),
                AccountProfile(faucet="unknown_faucet", username="test_user3", password="pass3", enabled=True),
            ]
        )
    
    @pytest.fixture
    def mock_browser_manager(self):
        """Create mock browser manager."""
        manager = AsyncMock()
        manager.create_context = AsyncMock()
        manager.new_page = AsyncMock()
        manager.save_cookies = AsyncMock()
        manager.check_page_status = AsyncMock(return_value={"blocked": False, "network_error": False})
        return manager
    
    @pytest.fixture
    def scheduler_with_accounts(self, settings_with_accounts, mock_browser_manager):
        """Create JobScheduler instance with accounts."""
        with patch.object(JobScheduler, '_restore_session'), \
             patch.object(JobScheduler, '_persist_session'):
            return JobScheduler(settings_with_accounts, mock_browser_manager)
    
    @pytest.mark.asyncio
    async def test_schedule_withdrawal_jobs_creates_jobs(self, scheduler_with_accounts):
        """Test that schedule_withdrawal_jobs creates withdrawal jobs for supported faucets."""
        with patch('core.analytics.get_tracker') as mock_tracker:
            # Mock analytics
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.get_hourly_rate.return_value = {
                'firefaucet': 150,  # High earner
                'cointiply': 60,    # Medium earner
            }
            mock_tracker_instance.get_faucet_stats.return_value = {}  # For priority calc
            mock_tracker.return_value = mock_tracker_instance
            
            # Schedule withdrawal jobs
            await scheduler_with_accounts.schedule_withdrawal_jobs()
            
            # Check that jobs were created (at least 1 for supported faucets)
            withdrawal_jobs = [j for j in scheduler_with_accounts.queue if "withdraw" in j.job_type.lower()]
            assert len(withdrawal_jobs) >= 1
            
            # Check job properties (priority may be adjusted by dynamic priority system)
            for job in withdrawal_jobs:
                assert job.priority >= 10  # Low priority (10 or higher = lower priority)
                assert job.job_type == "withdraw_wrapper"
                assert job.next_run > time.time()  # Scheduled in future
    
    @pytest.mark.asyncio
    async def test_schedule_withdrawal_jobs_respects_off_peak(self, scheduler_with_accounts):
        """Test that withdrawal jobs are scheduled during off-peak hours."""
        with patch('core.analytics.get_tracker') as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.get_hourly_rate.return_value = {'firefaucet': 100}
            mock_tracker.return_value = mock_tracker_instance
            
            await scheduler_with_accounts.schedule_withdrawal_jobs()
            
            withdrawal_jobs = [j for j in scheduler_with_accounts.queue if "withdraw" in j.job_type.lower()]
            
            for job in withdrawal_jobs:
                # Check that the scheduled time is in off-peak hours
                from datetime import datetime, timezone
                scheduled_time = datetime.fromtimestamp(job.next_run, tz=timezone.utc)
                # Should be in off_peak_hours
                assert scheduled_time.hour in scheduler_with_accounts.settings.off_peak_hours
    
    @pytest.mark.asyncio
    async def test_schedule_withdrawal_jobs_skips_unsupported_faucets(self, scheduler_with_accounts):
        """Test that withdrawal jobs are not created for faucets without withdraw()."""
        with patch('core.analytics.get_tracker') as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.get_hourly_rate.return_value = {}
            mock_tracker.return_value = mock_tracker_instance
            
            await scheduler_with_accounts.schedule_withdrawal_jobs()
            
            # Check that unknown_faucet doesn't have a withdrawal job
            withdrawal_jobs = [j for j in scheduler_with_accounts.queue if "unknown" in j.faucet_type.lower()]
            assert len(withdrawal_jobs) == 0
    
    @pytest.mark.asyncio
    async def test_execute_consolidated_withdrawal_below_threshold(self, scheduler_with_accounts, mock_browser_manager):
        """Test that withdrawal is skipped when balance is below threshold."""
        profile = AccountProfile(faucet="firefaucet", username="test_user", password="pass")
        
        with patch('core.analytics.get_tracker') as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.get_faucet_stats.return_value = {
                'firefaucet': {'earnings': 100}  # Below threshold
            }
            mock_tracker.return_value = mock_tracker_instance
            
            result = await scheduler_with_accounts.execute_consolidated_withdrawal("firefaucet", profile)
            
            assert result.success == True
            assert "Below Threshold" in result.status
            assert result.next_claim_minutes == 1440
    
    @pytest.mark.asyncio
    async def test_execute_consolidated_withdrawal_off_peak_check(self, scheduler_with_accounts, mock_browser_manager):
        """Test that withdrawal is deferred when not in off-peak hours."""
        profile = AccountProfile(faucet="firefaucet", username="test_user", password="pass")
        
        with patch('core.analytics.get_tracker') as mock_tracker, \
             patch.object(scheduler_with_accounts, 'is_off_peak_time', return_value=False):
            
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.get_faucet_stats.return_value = {
                'firefaucet': {'earnings': 100000}  # Above threshold
            }
            mock_tracker.return_value = mock_tracker_instance
            
            result = await scheduler_with_accounts.execute_consolidated_withdrawal("firefaucet", profile)
            
            assert result.success == True
            assert "Off-Peak" in result.status
            assert result.next_claim_minutes == 60
    
    @pytest.mark.asyncio
    async def test_withdrawal_retry_logic_on_failure(self, scheduler_with_accounts, mock_browser_manager, settings_with_accounts):
        """Test that withdrawal jobs retry with exponential backoff on failure."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser_manager.create_context.return_value = mock_context
        mock_browser_manager.new_page.return_value = mock_page
        
        # Mock failed withdrawal
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.status = "Withdrawal Failed"
        mock_result.next_claim_minutes = 60
        mock_method = AsyncMock(return_value=mock_result)
        
        profile = AccountProfile(faucet="firefaucet", username="test_user", password="pass")
        job = Job(
            priority=10,
            next_run=time.time(),
            name="FireFaucet Withdraw",
            profile=profile,
            faucet_type="firefaucet",
            job_type="withdraw_wrapper",
            retry_count=0
        )
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.withdraw_wrapper = mock_method
            
            await scheduler_with_accounts._run_job_wrapper(job)
            
            # Should be rescheduled with retry
            assert len(scheduler_with_accounts.queue) == 1
            rescheduled_job = scheduler_with_accounts.queue[0]
            assert rescheduled_job.retry_count == 1
            
            # Check retry interval (should be first interval: 1 hour = 3600 seconds)
            expected_delay = settings_with_accounts.withdrawal_retry_intervals[0]
            actual_delay = rescheduled_job.next_run - time.time()
            assert abs(actual_delay - expected_delay) < 2.0  # Allow 2s tolerance
    
    @pytest.mark.asyncio
    async def test_withdrawal_max_retries_reached(self, scheduler_with_accounts, mock_browser_manager):
        """Test that withdrawal jobs stop retrying after max attempts."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser_manager.create_context.return_value = mock_context
        mock_browser_manager.new_page.return_value = mock_page
        
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.status = "Withdrawal Failed"
        mock_result.next_claim_minutes = 60
        mock_method = AsyncMock(return_value=mock_result)
        
        profile = AccountProfile(faucet="firefaucet", username="test_user", password="pass")
        job = Job(
            priority=10,
            next_run=time.time(),
            name="FireFaucet Withdraw",
            profile=profile,
            faucet_type="firefaucet",
            job_type="withdraw_wrapper",
            retry_count=3  # Already at max retries
        )
        
        with patch("core.registry.get_faucet_class") as mock_get_class, \
             patch("core.withdrawal_analytics.get_analytics") as mock_analytics:
            
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.withdraw_wrapper = mock_method
            
            mock_analytics_instance = MagicMock()
            mock_analytics.return_value = mock_analytics_instance
            
            await scheduler_with_accounts._run_job_wrapper(job)
            
            # Should NOT be rescheduled
            assert len(scheduler_with_accounts.queue) == 0
            
            # Should log failed withdrawal to analytics
            mock_analytics_instance.record_withdrawal.assert_called_once()
            call_args = mock_analytics_instance.record_withdrawal.call_args
            assert call_args[1]['status'] == 'failed'
    
    @pytest.mark.asyncio
    async def test_withdrawal_exception_retry_logic(self, scheduler_with_accounts, mock_browser_manager):
        """Test that withdrawal exceptions trigger retry logic."""
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser_manager.create_context.return_value = mock_context
        mock_browser_manager.new_page.return_value = mock_page
        
        mock_method = AsyncMock(side_effect=Exception("Test withdrawal error"))
        
        profile = AccountProfile(faucet="firefaucet", username="test_user", password="pass")
        job = Job(
            priority=10,
            next_run=time.time(),
            name="FireFaucet Withdraw",
            profile=profile,
            faucet_type="firefaucet",
            job_type="withdraw_wrapper",
            retry_count=0
        )
        
        with patch("core.registry.get_faucet_class") as mock_get_class:
            mock_bot_cls = MagicMock()
            mock_bot_instance = MagicMock()
            mock_get_class.return_value = mock_bot_cls
            mock_bot_cls.return_value = mock_bot_instance
            mock_bot_instance.withdraw_wrapper = mock_method
            
            await scheduler_with_accounts._run_job_wrapper(job)
            
            # Should be rescheduled with retry
            assert len(scheduler_with_accounts.queue) == 1
            rescheduled_job = scheduler_with_accounts.queue[0]
            assert rescheduled_job.retry_count == 1
            
            # Check retry interval
            expected_delay = scheduler_with_accounts.settings.withdrawal_retry_intervals[0]
            actual_delay = rescheduled_job.next_run - time.time()
            assert abs(actual_delay - expected_delay) < 2.0
    
    def test_is_off_peak_time_implementation_exists(self, scheduler_with_accounts):
        """Test that is_off_peak_time method exists and returns a boolean."""
        result = scheduler_with_accounts.is_off_peak_time()
        assert isinstance(result, bool)

