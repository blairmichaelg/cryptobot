"""
Test suite for the job-based scheduler.
Tests job queue priority ordering, concurrent execution, rescheduling, retry logic, and concurrency limits.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from core.orchestrator import JobScheduler, Job
from core.config import BotSettings, AccountProfile
from faucets.base import ClaimResult


@pytest.fixture(autouse=True)
def clean_scheduler_session():
    """Ensure tests start with a clean scheduler state."""
    with patch("os.path.exists", return_value=False):
        yield

@pytest.fixture
def mock_settings():
    """Create mock bot settings."""
    settings = BotSettings()
    settings.max_concurrent_bots = 2
    settings.max_concurrent_per_profile = 1
    settings.user_agents = ["Mozilla/5.0 Test Agent"]
    return settings


@pytest.fixture
def mock_browser_manager():
    """Create mock browser manager."""
    manager = AsyncMock()
    manager.create_context = AsyncMock(return_value=AsyncMock())
    manager.new_page = AsyncMock(return_value=AsyncMock())
    manager.check_health = AsyncMock(return_value=True)
    manager.restart = AsyncMock()
    return manager


@pytest.fixture
def test_profile():
    """Create test account profile."""
    return AccountProfile(
        faucet="test_faucet",
        username="test_user",
        password="test_pass",
        enabled=True
    )


@pytest.mark.asyncio
async def test_job_priority_ordering(mock_settings, mock_browser_manager, test_profile):
    """Test that jobs are executed in priority order."""
    from unittest.mock import patch
    
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    # Mock get_faucet_priority to prevent dynamic adjustment
    with patch.object(scheduler, 'get_faucet_priority', return_value=1.0):
        # Add jobs with different priorities
        job1 = Job(priority=2, next_run=time.time(), name="Low Priority", profile=test_profile,
                   faucet_type="test", job_type="claim_wrapper")
        job2 = Job(priority=1, next_run=time.time(), name="High Priority", profile=test_profile,
                   faucet_type="test2", job_type="claim_wrapper")
        job3 = Job(priority=3, next_run=time.time(), name="Lowest Priority", profile=test_profile,
                   faucet_type="test3", job_type="claim_wrapper")
        
        scheduler.add_job(job1)
        scheduler.add_job(job2)
        scheduler.add_job(job3)
        
        # Verify queue is sorted by priority
        assert scheduler.queue[0].priority == 1
        assert scheduler.queue[1].priority == 2
        assert scheduler.queue[2].priority == 3


@pytest.mark.asyncio
async def test_concurrent_job_execution(mock_settings, mock_browser_manager, test_profile):
    """Test that jobs execute concurrently up to the limit."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    # Create multiple jobs
    for i in range(5):
        job = Job(priority=1, next_run=time.time(), name=f"Job {i}", profile=test_profile,
                  faucet_type="test", job_type="claim_wrapper")
        scheduler.add_job(job)
    
    # Start scheduler in background
    scheduler_task = asyncio.create_task(scheduler.scheduler_loop())
    
    # Wait a bit for jobs to start
    await asyncio.sleep(0.2)
    
    # Check that we're respecting concurrency limits
    assert len(scheduler.running_jobs) <= mock_settings.max_concurrent_bots
    
    # Stop scheduler
    scheduler.stop()
    await asyncio.sleep(0.1)
    try:
        scheduler_task.cancel()
        await scheduler_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_job_rescheduling(mock_settings, mock_browser_manager, test_profile):
    """Test that jobs are rescheduled after completion."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    job = Job(priority=1, next_run=time.time(), name="Test Job", profile=test_profile,
              faucet_type="test", job_type="claim_wrapper")
    
    initial_queue_size = len(scheduler.queue)
    scheduler.add_job(job)
    
    # Verify job was added
    assert len(scheduler.queue) == initial_queue_size + 1
    
    # Note: We can't easily test rescheduling without mocking the entire faucet bot
    # This would require mocking the registry and bot instantiation


@pytest.mark.asyncio
async def test_retry_logic(mock_settings, mock_browser_manager, test_profile):
    """Test exponential backoff retry logic."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    job = Job(priority=1, next_run=time.time(), name="Failing Job", profile=test_profile,
              faucet_type="test", job_type="claim_wrapper", retry_count=0)
    
    scheduler.add_job(job)
    
    # Verify job is in queue
    assert len(scheduler.queue) == 1
    
    # Note: Testing actual retry behavior requires integration testing with real bot


@pytest.mark.asyncio
async def test_profile_concurrency_limit(mock_settings, mock_browser_manager, test_profile):
    """Test that profile concurrency limits are respected."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    # Create multiple jobs for the same profile
    for i in range(3):
        job = Job(priority=1, next_run=time.time(), name=f"Job {i}", profile=test_profile,
                  faucet_type="test", job_type="claim_wrapper")
        scheduler.add_job(job)
    
    # Start scheduler
    scheduler_task = asyncio.create_task(scheduler.scheduler_loop())
    
    # Wait longer for scheduler to process jobs
    await asyncio.sleep(0.5)
    
    # Check profile concurrency - should be at most max_concurrent_per_profile
    # Note: Due to timing, this may occasionally be 0 if jobs complete quickly
    concurrent_count = scheduler.profile_concurrency.get(test_profile.username, 0)
    assert concurrent_count <= mock_settings.max_concurrent_per_profile, \
        f"Profile concurrency {concurrent_count} exceeds limit {mock_settings.max_concurrent_per_profile}"
    
    # Cleanup
    scheduler.stop()
    await asyncio.sleep(0.1)
    try:
        scheduler_task.cancel()
        await scheduler_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_global_concurrency_limit(mock_settings, mock_browser_manager):
    """Test that global concurrency limits are respected."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
   # Create jobs for different profiles
    for i in range(5):
        profile = AccountProfile(
            faucet="test",
            username=f"user{i}",
            password="pass",
            enabled=True
        )
        job = Job(priority=1, next_run=time.time(), name=f"Job {i}", profile=profile,
                  faucet_type="test", job_type="claim_wrapper")
        scheduler.add_job(job)
    
    # Start scheduler
    scheduler_task = asyncio.create_task(scheduler.scheduler_loop())
    
    # Wait for jobs to start
    await asyncio.sleep(0.2)
    
    # Check global concurrency
    assert len(scheduler.running_jobs) <= mock_settings.max_concurrent_bots
    
    # Cleanup
    scheduler.stop()
    await asyncio.sleep(0.1)
    try:
        scheduler_task.cancel()
        await scheduler_task
    except asyncio.CancelledError:
        pass
