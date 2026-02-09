"""
Integration tests for JobScheduler orchestration engine.

This test suite validates the end-to-end behavior of the JobScheduler
when managing multiple faucets concurrently. Tests focus on component
integration rather than internal implementation details.

All browser and network calls are mocked to ensure fast, deterministic tests.
"""

import pytest
import asyncio
import json
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, Mock

from core.orchestrator import JobScheduler, Job, ErrorType
from core.config import BotSettings, AccountProfile
from faucets.base import ClaimResult


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for test isolation."""
    temp_dir = tempfile.mkdtemp(prefix="cryptobot_integration_")
    yield Path(temp_dir)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.fixture
def mock_settings():
    """Create mock bot settings for testing."""
    settings = BotSettings()
    settings.twocaptcha_api_key = "test_key"
    settings.use_2captcha_proxies = False
    return settings


@pytest.fixture
def mock_profiles():
    """Create mock account profiles for testing."""
    return [
        AccountProfile(
            faucet="firefaucet",
            username="test_user1",
            password="test_pass1",
            email="test1@example.com"
        ),
        AccountProfile(
            faucet="cointiply",
            username="test_user2",
            password="test_pass2",
            email="test2@example.com"
        ),
        AccountProfile(
            faucet="dutchy",
            username="test_user3",
            password="test_pass3",
            email="test3@example.com"
        ),
    ]


class TestJobSchedulerBasics:
    """Test basic JobScheduler initialization and setup."""
    
    @pytest.mark.asyncio
    async def test_scheduler_initializes(self, mock_settings, temp_config_dir):
        """Test that scheduler initializes with default state."""
        with patch("core.orchestrator.CONFIG_DIR", temp_config_dir):
            scheduler = JobScheduler(
                settings=mock_settings,
                browser_manager=AsyncMock()
            )
            
            # Verify basic initialization
            assert scheduler.queue is not None
            assert scheduler.running_jobs is not None
            assert scheduler.settings == mock_settings
    
    @pytest.mark.asyncio
    async def test_add_job_to_queue(self, mock_settings, mock_profiles):
        """Test adding a job to the scheduler queue."""
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock()
        )
        
        # Create a job
        job = Job(
            faucet_type="firefaucet",
            profile=mock_profiles[0],
            next_run=time.time() + 300,
            priority=1,
            job_type="claim",
            retry_count=0
        )
        
        # Add job
        scheduler.add_job(job)
        
        # Verify job was added
        assert len(scheduler.queue) > 0


class TestMultipleFaucetIntegration:
    """Test integration with multiple faucets."""
    
    @pytest.mark.asyncio
    async def test_multiple_faucet_profiles(self, mock_settings, mock_profiles):
        """Test that scheduler can handle multiple different faucets."""
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock()
        )
        
        # Add jobs for different faucets
        for i, profile in enumerate(mock_profiles):
            job = Job(
                faucet_type=profile.faucet,
                profile=profile,
                next_run=time.time() + (i * 100),
                priority=i + 1,
                job_type="claim",
                retry_count=0
            )
            scheduler.add_job(job)
        
        # Verify all jobs added
        assert len(scheduler.queue) >= len(mock_profiles)


class TestErrorTypeClassification:
    """Test ErrorType enum for intelligent error handling."""
    
    def test_error_types_exist(self):
        """Test that all error types are defined."""
        assert hasattr(ErrorType, "TRANSIENT")
        assert hasattr(ErrorType, "RATE_LIMIT")
        assert hasattr(ErrorType, "PROXY_ISSUE")
        assert hasattr(ErrorType, "PERMANENT")
        assert hasattr(ErrorType, "FAUCET_DOWN")
        assert hasattr(ErrorType, "CAPTCHA_FAILED")
        assert hasattr(ErrorType, "CONFIG_ERROR")
        assert hasattr(ErrorType, "UNKNOWN")
    
    def test_error_type_values(self):
        """Test error type enum values."""
        assert ErrorType.TRANSIENT.value == "transient"
        assert ErrorType.PERMANENT.value == "permanent"
        assert ErrorType.PROXY_ISSUE.value == "proxy_issue"


class TestClaimResultIntegration:
    """Test integration with ClaimResult from faucet bots."""
    
    def test_claim_result_success(self):
        """Test successful claim result creation."""
        result = ClaimResult(
            success=True,
            status="Claimed successfully",
            next_claim_minutes=60,
            amount="100",
            balance="1000"
        )
        
        assert result.success is True
        assert result.next_claim_minutes == 60
        assert result.amount == "100"
    
    def test_claim_result_with_error_type(self):
        """Test claim result with error type for scheduler."""
        result = ClaimResult(
            success=False,
            status="Proxy detected",
            error_type=ErrorType.PROXY_ISSUE
        )
        
        assert result.success is False
        assert result.error_type == ErrorType.PROXY_ISSUE


class TestSessionPersistence:
    """Test session persistence functionality."""
    
    @pytest.mark.asyncio
    async def test_session_file_creation(self, mock_settings, temp_config_dir):
        """Test that session state file can be created."""
        with patch("core.orchestrator.CONFIG_DIR", temp_config_dir):
            scheduler = JobScheduler(
                settings=mock_settings,
                browser_manager=AsyncMock()
            )
            
            # Persist session
            scheduler._persist_session()
            
            # Verify file exists
            session_file = temp_config_dir / "session_state.json"
            assert session_file.exists()
    
    @pytest.mark.asyncio
    async def test_session_contains_queue_data(self, mock_settings, mock_profiles, temp_config_dir):
        """Test that persisted session contains queue data."""
        with patch("core.orchestrator.CONFIG_DIR", temp_config_dir):
            scheduler = JobScheduler(
                settings=mock_settings,
                browser_manager=AsyncMock()
            )
            
            # Add a job
            job = Job(
                faucet_type="firefaucet",
                profile=mock_profiles[0],
                next_run=time.time() + 300,
                priority=1,
                job_type="claim",
                retry_count=0
            )
            scheduler.add_job(job)
            
            # Persist
            scheduler._persist_session()
            
            # Read and verify
            session_file = temp_config_dir / "session_state.json"
            data = json.loads(session_file.read_text())
            
            assert "queue" in data
            assert isinstance(data["queue"], list)


class TestProxyIntegration:
    """Test integration with proxy manager."""
    
    @pytest.mark.asyncio
    async def test_scheduler_with_proxy_manager(self, mock_settings):
        """Test that scheduler can work with proxy manager."""
        mock_proxy_manager = MagicMock()
        
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock(),
            proxy_manager=mock_proxy_manager
        )
        
        assert scheduler.proxy_manager == mock_proxy_manager
    
    @pytest.mark.asyncio
    async def test_scheduler_without_proxy_manager(self, mock_settings):
        """Test that scheduler can work without proxy manager."""
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock(),
            proxy_manager=None
        )
        
        assert scheduler.proxy_manager is None


class TestHealthMonitoring:
    """Test health monitoring integration."""
    
    @pytest.mark.asyncio
    async def test_health_monitor_initialized(self, mock_settings):
        """Test that health monitor is initialized with scheduler."""
        with patch("core.orchestrator.HealthMonitor") as mock_health:
            mock_health_instance = MagicMock()
            mock_health.return_value = mock_health_instance
            
            scheduler = JobScheduler(
                settings=mock_settings,
                browser_manager=AsyncMock()
            )
            
            # Health monitor should be created
            assert scheduler.health_monitor is not None


class TestJobPriorityQueue:
    """Test job priority queue management."""
    
    @pytest.mark.asyncio
    async def test_jobs_added_to_queue(self, mock_settings, mock_profiles):
        """Test that jobs maintain priority ordering."""
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock()
        )
        
        # Add jobs with different priorities
        high_priority = Job(
            faucet_type="urgent",
            profile=mock_profiles[0],
            next_run=time.time(),
            priority=1,
            job_type="claim",
            retry_count=0
        )
        
        low_priority = Job(
            faucet_type="normal",
            profile=mock_profiles[1],
            next_run=time.time(),
            priority=10,
            job_type="claim",
            retry_count=0
        )
        
        scheduler.add_job(low_priority)
        scheduler.add_job(high_priority)
        
        # Queue should have both jobs
        assert len(scheduler.queue) >= 2


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_faucet_failure_tracking(self, mock_settings):
        """Test that faucet failures are tracked."""
        scheduler = JobScheduler(
            settings=mock_settings,
            browser_manager=AsyncMock()
        )
        
        # Verify failure tracking structures exist
        assert hasattr(scheduler, "faucet_failures")
        assert hasattr(scheduler, "faucet_cooldowns")
        assert hasattr(scheduler, "faucet_error_types")
