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
