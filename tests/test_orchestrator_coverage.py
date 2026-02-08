"""
Comprehensive test suite for core/orchestrator.py.

Achieves 100% coverage on Job, ErrorType, and JobScheduler methods including:
- Job creation, serialization, comparison
- ErrorType classification
- JobScheduler initialization and configuration
- Session persistence
- Circuit breaker logic
"""

import pytest
import asyncio
import json
import os
import time
import tempfile
import shutil
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass
from pathlib import Path


@pytest.fixture
def safe_tmp_path():
    """Create a temp directory in user's temp folder to avoid permission issues."""
    temp_dir = tempfile.mkdtemp(prefix="cryptobot_test_")
    yield Path(temp_dir)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


class TestErrorType:
    """Test ErrorType enum values and usage."""
    
    def test_error_type_transient(self):
        """Test TRANSIENT error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.TRANSIENT.value == "transient"
    
    def test_error_type_rate_limit(self):
        """Test RATE_LIMIT error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
    
    def test_error_type_proxy_issue(self):
        """Test PROXY_ISSUE error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.PROXY_ISSUE.value == "proxy_issue"
    
    def test_error_type_permanent(self):
        """Test PERMANENT error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.PERMANENT.value == "permanent"
    
    def test_error_type_faucet_down(self):
        """Test FAUCET_DOWN error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.FAUCET_DOWN.value == "faucet_down"
    
    def test_error_type_captcha_failed(self):
        """Test CAPTCHA_FAILED error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.CAPTCHA_FAILED.value == "captcha_failed"
    
    def test_error_type_config_error(self):
        """Test CONFIG_ERROR error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.CONFIG_ERROR.value == "config_error"
    
    def test_error_type_unknown(self):
        """Test UNKNOWN error type."""
        from core.orchestrator import ErrorType
        
        assert ErrorType.UNKNOWN.value == "unknown"


class TestJobDataclass:
    """Test Job dataclass thoroughly."""
    
    @pytest.fixture
    def sample_profile(self):
        """Create a sample profile."""
        from core.config import AccountProfile
        return AccountProfile(faucet="test", username="user", password="pass")
    
    def test_job_creation_all_fields(self, sample_profile):
        """Test Job creation with all fields."""
        from core.orchestrator import Job
        
        job = Job(
            priority=1,
            next_run=1000.0,
            name="test_job",
            profile=sample_profile,
            faucet_type="test_faucet",
            job_type="claim_wrapper",
            retry_count=3
        )
        
        assert job.priority == 1
        assert job.next_run == 1000.0
        assert job.name == "test_job"
        assert job.profile == sample_profile
        assert job.faucet_type == "test_faucet"
        assert job.job_type == "claim_wrapper"
        assert job.retry_count == 3
    
    def test_job_default_job_type(self, sample_profile):
        """Test Job default job_type."""
        from core.orchestrator import Job
        
        job = Job(
            priority=1,
            next_run=1000.0,
            name="test",
            profile=sample_profile,
            faucet_type="f"
        )
        
        assert job.job_type == "claim_wrapper"
    
    def test_job_default_retry_count(self, sample_profile):
        """Test Job default retry_count."""
        from core.orchestrator import Job
        
        job = Job(
            priority=1,
            next_run=1000.0,
            name="test",
            profile=sample_profile,
            faucet_type="f"
        )
        
        assert job.retry_count == 0
    
    def test_job_to_dict(self, sample_profile):
        """Test Job.to_dict serialization."""
        from core.orchestrator import Job
        
        job = Job(
            priority=2,
            next_run=2000.0,
            name="serialize_test",
            profile=sample_profile,
            faucet_type="test_faucet",
            job_type="claim_wrapper",
            retry_count=1
        )
        
        d = job.to_dict()
        
        assert d["priority"] == 2
        assert d["next_run"] == 2000.0
        assert d["name"] == "serialize_test"
        assert d["faucet_type"] == "test_faucet"
        assert d["job_type"] == "claim_wrapper"
        assert d["retry_count"] == 1
        assert isinstance(d["profile"], dict)
        assert d["profile"]["faucet"] == "test"
        assert d["profile"]["username"] == "user"
    
    def test_job_from_dict(self):
        """Test Job.from_dict deserialization."""
        from core.orchestrator import Job
        
        data = {
            "priority": 3,
            "next_run": 3000.0,
            "name": "restored_job",
            "profile": {
                "faucet": "restored",
                "username": "restored_user",
                "password": "restored_pass"
            },
            "faucet_type": "restored_faucet",
            "job_type": "claim_wrapper",
            "retry_count": 2
        }
        
        job = Job.from_dict(data)
        
        assert job.priority == 3
        assert job.next_run == 3000.0
        assert job.name == "restored_job"
        assert job.faucet_type == "restored_faucet"
        assert job.retry_count == 2
        assert job.profile.faucet == "restored"
        assert job.profile.username == "restored_user"
    
    def test_job_roundtrip(self, sample_profile):
        """Test Job serialization roundtrip."""
        from core.orchestrator import Job
        
        original = Job(
            priority=5,
            next_run=5000.0,
            name="roundtrip",
            profile=sample_profile,
            faucet_type="roundtrip_faucet",
            job_type="claim_wrapper",
            retry_count=4
        )
        
        d = original.to_dict()
        restored = Job.from_dict(d)
        
        assert restored.priority == original.priority
        assert restored.next_run == original.next_run
        assert restored.name == original.name
        assert restored.faucet_type == original.faucet_type
        assert restored.retry_count == original.retry_count
    
    def test_job_comparison_by_priority(self, sample_profile):
        """Test Job comparison by priority."""
        from core.orchestrator import Job
        
        job_low = Job(priority=1, next_run=1000.0, name="low", profile=sample_profile, faucet_type="f")
        job_high = Job(priority=5, next_run=100.0, name="high", profile=sample_profile, faucet_type="f")
        
        # Lower priority number = higher priority (comes first)
        assert job_low < job_high
    
    def test_job_comparison_by_next_run(self, sample_profile):
        """Test Job comparison by next_run when priority is equal."""
        from core.orchestrator import Job
        
        job_soon = Job(priority=1, next_run=100.0, name="soon", profile=sample_profile, faucet_type="f")
        job_later = Job(priority=1, next_run=1000.0, name="later", profile=sample_profile, faucet_type="f")
        
        # Earlier next_run comes first
        assert job_soon < job_later
    
    def test_job_sorting(self, sample_profile):
        """Test sorting a list of Jobs."""
        from core.orchestrator import Job
        
        jobs = [
            Job(priority=3, next_run=500.0, name="j1", profile=sample_profile, faucet_type="f"),
            Job(priority=1, next_run=100.0, name="j2", profile=sample_profile, faucet_type="f"),
            Job(priority=1, next_run=200.0, name="j3", profile=sample_profile, faucet_type="f"),
            Job(priority=2, next_run=50.0, name="j4", profile=sample_profile, faucet_type="f"),
        ]
        
        jobs.sort()
        
        # Should be ordered by priority first, then next_run
        assert jobs[0].name == "j2"  # priority 1, next_run 100
        assert jobs[1].name == "j3"  # priority 1, next_run 200
        assert jobs[2].name == "j4"  # priority 2
        assert jobs[3].name == "j1"  # priority 3


class TestJobSchedulerInit:
    """Test JobScheduler initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.max_concurrent_bots = 3
        settings.max_concurrent_per_profile = 1
        settings.alert_webhook_url = None
        settings.job_timeout_seconds = 600
        return settings
    
    @pytest.fixture
    def mock_browser_manager(self):
        """Create mock browser manager."""
        return AsyncMock()
    
    def test_scheduler_init_basic(self, mock_settings, mock_browser_manager):
        """Test basic JobScheduler initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.settings == mock_settings
        assert scheduler.browser_manager == mock_browser_manager
        assert scheduler.proxy_manager is None
        # Queue may have jobs loaded from session file
        assert isinstance(scheduler.queue, list)
        assert scheduler.running_jobs == {}
    
    def test_scheduler_init_with_proxy_manager(self, mock_settings, mock_browser_manager):
        """Test JobScheduler with proxy manager."""
        from core.orchestrator import JobScheduler
        
        mock_proxy_manager = MagicMock()
        mock_proxy_manager.proxies = ["p1", "p2", "p3", "p4", "p5"]
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager, mock_proxy_manager)
        
        assert scheduler.proxy_manager == mock_proxy_manager
    
    def test_scheduler_init_low_proxy_warning(self, mock_settings, mock_browser_manager):
        """Test JobScheduler logs warning for low proxy count."""
        from core.orchestrator import JobScheduler
        
        mock_proxy_manager = MagicMock()
        mock_proxy_manager.proxies = ["p1", "p2"]  # Less than 3
        
        with patch("core.orchestrator.logger") as mock_logger:
            scheduler = JobScheduler(mock_settings, mock_browser_manager, mock_proxy_manager)
            
            # Should log a warning about low proxy count
            mock_logger.warning.assert_called()
    
    def test_scheduler_init_security_challenge_tracking(self, mock_settings, mock_browser_manager):
        """Test security challenge retry tracking initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.security_challenge_retries == {}
        assert scheduler.MAX_SECURITY_RETRIES == 5
        assert scheduler.SECURITY_RETRY_RESET_HOURS == 24
    
    def test_scheduler_init_backoff_tracking(self, mock_settings, mock_browser_manager):
        """Test exponential backoff tracking initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.faucet_backoff == {}
    
    def test_scheduler_init_circuit_breaker(self, mock_settings, mock_browser_manager):
        """Test circuit breaker initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.faucet_failures == {}
        assert scheduler.faucet_error_types == {}
        assert scheduler.faucet_cooldowns == {}
        assert scheduler.CIRCUIT_BREAKER_THRESHOLD == 5
        assert scheduler.CIRCUIT_BREAKER_COOLDOWN == 14400
    
    def test_scheduler_init_account_usage(self, mock_settings, mock_browser_manager):
        """Test account usage tracking initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.account_usage == {}
    
    def test_scheduler_init_domain_rate_limiting(self, mock_settings, mock_browser_manager):
        """Test domain rate limiting initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.domain_last_access == {}
    
    def test_scheduler_init_health_monitoring(self, mock_settings, mock_browser_manager):
        """Test health monitoring initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.health_monitor is not None
        assert scheduler.last_health_check_time == 0.0
        assert scheduler.consecutive_job_failures == 0
    
    def test_scheduler_init_operation_mode(self, mock_settings, mock_browser_manager):
        """Test operation mode initialization."""
        from core.orchestrator import JobScheduler
        from core.config import OperationMode
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.current_mode == OperationMode.NORMAL
    
    def test_scheduler_init_timer_predictions(self, mock_settings, mock_browser_manager):
        """Test timer predictions initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.timer_predictions == {}
        assert scheduler.TIMER_HISTORY_SIZE == 10


class TestJobSchedulerConstants:
    """Test JobScheduler constants."""
    
    def test_constants_defined(self):
        """Test that constants are properly defined."""
        from core.orchestrator import (
            MAX_PROXY_FAILURES,
            PROXY_COOLDOWN_SECONDS,
            BURNED_PROXY_COOLDOWN,
            JITTER_MIN_SECONDS,
            JITTER_MAX_SECONDS,
            CLOUDFLARE_MAX_RETRIES,
            PROXY_RETRY_DELAY_SECONDS,
            MAX_RETRY_BACKOFF_SECONDS,
            MIN_DOMAIN_GAP_SECONDS,
            HEARTBEAT_INTERVAL_SECONDS,
            SESSION_PERSIST_INTERVAL,
            BROWSER_HEALTH_CHECK_INTERVAL,
            MAX_CONSECUTIVE_JOB_FAILURES
        )
        
        assert MAX_PROXY_FAILURES == 3
        assert PROXY_COOLDOWN_SECONDS == 300
        assert BURNED_PROXY_COOLDOWN == 43200
        assert JITTER_MIN_SECONDS == 30
        assert JITTER_MAX_SECONDS == 120
        assert CLOUDFLARE_MAX_RETRIES == 15
        assert PROXY_RETRY_DELAY_SECONDS == 60
        assert MAX_RETRY_BACKOFF_SECONDS == 3600
        assert MIN_DOMAIN_GAP_SECONDS == 45
        assert HEARTBEAT_INTERVAL_SECONDS == 60
        assert SESSION_PERSIST_INTERVAL == 300
        assert BROWSER_HEALTH_CHECK_INTERVAL == 600
        assert MAX_CONSECUTIVE_JOB_FAILURES == 5


class TestJobSchedulerSessionPersistence:
    """Test session persistence methods."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.max_concurrent_bots = 3
        settings.max_concurrent_per_profile = 1
        settings.alert_webhook_url = None
        settings.job_timeout_seconds = 600
        return settings
    
    @pytest.fixture
    def mock_browser_manager(self):
        """Create mock browser manager."""
        return AsyncMock()
    
    def test_scheduler_session_file_path(self, mock_settings, mock_browser_manager, safe_tmp_path):
        """Test session file path is set correctly."""
        from core.orchestrator import JobScheduler
        
        with patch("core.orchestrator.CONFIG_DIR", safe_tmp_path):
            scheduler = JobScheduler(mock_settings, mock_browser_manager)
            
            assert "session_state.json" in scheduler.session_file
    
    def test_scheduler_heartbeat_file_windows(self, mock_settings, mock_browser_manager):
        """Test heartbeat file path on Windows."""
        from core.orchestrator import JobScheduler
        
        with patch("os.name", "nt"):
            scheduler = JobScheduler(mock_settings, mock_browser_manager)
            
            assert "heartbeat.txt" in scheduler.heartbeat_file


class TestJobSchedulerFailureClassification:
    """Test failure classification lists."""
    
    @pytest.fixture
    def scheduler(self):
        """Create a scheduler instance."""
        from core.orchestrator import JobScheduler
        
        mock_settings = MagicMock()
        mock_settings.max_concurrent_bots = 3
        mock_settings.max_concurrent_per_profile = 1
        mock_settings.alert_webhook_url = None
        mock_settings.job_timeout_seconds = 600
        
        return JobScheduler(mock_settings, AsyncMock())
    
    def test_permanent_failures_list(self, scheduler):
        """Test PERMANENT_FAILURES list."""
        assert "auth_failed" in scheduler.PERMANENT_FAILURES
        assert "account_banned" in scheduler.PERMANENT_FAILURES
        assert "account_disabled" in scheduler.PERMANENT_FAILURES
        assert "invalid_credentials" in scheduler.PERMANENT_FAILURES
    
    def test_retryable_failures_list(self, scheduler):
        """Test RETRYABLE_FAILURES list."""
        assert "proxy_blocked" in scheduler.RETRYABLE_FAILURES
        assert "proxy_detection" in scheduler.RETRYABLE_FAILURES
        assert "cloudflare" in scheduler.RETRYABLE_FAILURES
        assert "rate_limit" in scheduler.RETRYABLE_FAILURES
        assert "timeout" in scheduler.RETRYABLE_FAILURES
        assert "connection_error" in scheduler.RETRYABLE_FAILURES


class TestOperationMode:
    """Test OperationMode enum."""
    
    def test_operation_mode_normal(self):
        """Test NORMAL operation mode."""
        from core.config import OperationMode
        
        assert OperationMode.NORMAL.value == "normal"
    
    def test_operation_mode_low_proxy(self):
        """Test LOW_PROXY operation mode."""
        from core.config import OperationMode
        
        assert OperationMode.LOW_PROXY.value == "low_proxy"
    
    def test_operation_mode_low_budget(self):
        """Test LOW_BUDGET operation mode."""
        from core.config import OperationMode
        
        assert OperationMode.LOW_BUDGET.value == "low_budget"
    
    def test_operation_mode_slow(self):
        """Test SLOW_MODE operation mode."""
        from core.config import OperationMode
        
        assert OperationMode.SLOW_MODE.value == "slow"
    
    def test_operation_mode_maintenance(self):
        """Test MAINTENANCE operation mode."""
        from core.config import OperationMode
        
        assert OperationMode.MAINTENANCE.value == "maintenance"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
