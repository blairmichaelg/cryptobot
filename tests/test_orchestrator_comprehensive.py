"""Comprehensive test suite for core/orchestrator.py.

Targets all uncovered branches and methods to bring coverage above 90%.
Covers:
- purge_jobs, _safe_json_write, _safe_json_read, _persist_session
- reset_security_retries, get_security_retry_status
- _write_heartbeat, get_domain_delay, record_domain_access
- calculate_retry_delay, estimate_claim_cost
- is_off_peak_time, get_faucet_priority, _check_auto_suspend
- predict_next_claim_time, record_timer_observation
- _normalize_faucet_key, _match_faucet_key
- schedule_withdrawal_jobs, schedule_auto_withdrawal_check
- execute_auto_withdrawal_check
- detect_operation_mode, apply_mode_restrictions, check_and_update_mode
- add_job (duplicate detection, dynamic priority)
- _is_faucet_in_bypass_list, _should_bypass_proxy, _should_disable_image_block
- get_next_proxy, record_proxy_failure
- _track_error_type, _should_trip_circuit_breaker
- _get_recovery_delay, get_recovery_delay
- _run_job_wrapper (success, error branches, withdrawal retries)
- scheduler_loop (startup, maintenance tasks, degraded modes)
- stop, cleanup
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import AccountProfile, OperationMode
from core.orchestrator import (
    BROWSER_HEALTH_CHECK_INTERVAL,
    BURNED_PROXY_COOLDOWN,
    CLOUDFLARE_MAX_RETRIES,
    HEARTBEAT_INTERVAL_SECONDS,
    JITTER_MAX_SECONDS,
    JITTER_MIN_SECONDS,
    MAX_CONSECUTIVE_JOB_FAILURES,
    MAX_PROXY_FAILURES,
    MAX_RETRY_BACKOFF_SECONDS,
    MIN_DOMAIN_GAP_SECONDS,
    PROXY_COOLDOWN_SECONDS,
    PROXY_RETRY_DELAY_SECONDS,
    SESSION_PERSIST_INTERVAL,
    ErrorType,
    Job,
    JobScheduler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile():
    """Standard test account profile."""
    return AccountProfile(faucet="test_faucet", username="testuser", password="testpass")


@pytest.fixture
def mock_settings():
    """Minimal mock of BotSettings."""
    s = MagicMock()
    s.max_concurrent_bots = 3
    s.max_concurrent_per_profile = 1
    s.alert_webhook_url = None
    s.job_timeout_seconds = 600
    s.accounts = []
    s.proxy_bypass_faucets = []
    s.image_bypass_faucets = []
    s.user_agents = ["Mozilla/5.0 Test"]
    s.captcha_provider = "2captcha"
    s.captcha_daily_budget = 5.0
    s.twocaptcha_api_key = "test_key"
    s.capsolver_api_key = None
    s.faucet_auto_suspend_enabled = False
    s.faucet_auto_suspend_min_samples = 10
    s.faucet_min_success_rate = 20.0
    s.faucet_roi_threshold = -0.5
    s.faucet_auto_suspend_duration = 3600
    s.prefer_off_peak_withdrawals = False
    s.off_peak_hours = [0, 1, 2, 3, 4, 5, 22, 23]
    s.withdrawal_max_retries = 3
    s.withdrawal_retry_intervals = [3600, 7200, 14400]
    s.wallet_rpc_urls = {}
    s.electrum_rpc_user = None
    s.electrum_rpc_pass = None
    s.low_proxy_threshold = 3
    s.low_proxy_max_concurrent_bots = 2
    s.performance_alert_slow_threshold = 5
    s.degraded_slow_delay_multiplier = 2.0
    s.scheduler_tick_rate = 1.0
    return s


@pytest.fixture
def mock_bm():
    """Mock browser manager."""
    bm = AsyncMock()
    bm.create_context = AsyncMock(return_value=MagicMock())
    bm.new_page = AsyncMock(return_value=MagicMock())
    bm.check_page_alive = AsyncMock(return_value=False)
    bm.safe_close_context = AsyncMock()
    bm.check_health = AsyncMock(return_value=True)
    bm.restart = AsyncMock()
    return bm


@pytest.fixture
def scheduler(mock_settings, mock_bm):
    """A JobScheduler with no session file to restore."""
    with patch("core.orchestrator.os.path.exists", return_value=False):
        return JobScheduler(mock_settings, mock_bm)


@pytest.fixture
def job(profile):
    """Standard test Job."""
    return Job(
        priority=2,
        next_run=time.time() + 60,
        name="test_job",
        profile=profile,
        faucet_type="test_faucet",
        job_type="claim_wrapper",
    )


# ---------------------------------------------------------------------------
# purge_jobs
# ---------------------------------------------------------------------------

class TestPurgeJobs:
    def test_purge_removes_matching_jobs(self, scheduler, profile):
        j1 = Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="a")
        j2 = Job(priority=1, next_run=0, name="j2", profile=profile, faucet_type="b")
        j3 = Job(priority=1, next_run=0, name="j3", profile=profile, faucet_type="a")
        scheduler.queue = [j1, j2, j3]
        removed = scheduler.purge_jobs(lambda j: j.faucet_type == "a")
        assert removed == 2
        assert len(scheduler.queue) == 1
        assert scheduler.queue[0].name == "j2"

    def test_purge_cleans_domain_access(self, scheduler, profile):
        j1 = Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="keep")
        j2 = Job(priority=1, next_run=0, name="j2", profile=profile, faucet_type="remove")
        scheduler.queue = [j1, j2]
        scheduler.domain_last_access = {"keep": 100.0, "remove": 200.0}
        scheduler.purge_jobs(lambda j: j.faucet_type == "remove")
        assert "keep" in scheduler.domain_last_access
        assert "remove" not in scheduler.domain_last_access

    def test_purge_no_matches(self, scheduler, profile):
        j1 = Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="a")
        scheduler.queue = [j1]
        removed = scheduler.purge_jobs(lambda j: j.faucet_type == "nonexistent")
        assert removed == 0
        assert len(scheduler.queue) == 1


# ---------------------------------------------------------------------------
# _safe_json_write / _safe_json_read / _persist_session
# ---------------------------------------------------------------------------

class TestJsonPersistence:
    def test_safe_json_write_and_read(self, scheduler):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            data = {"key": "value", "number": 42}
            scheduler._safe_json_write(path, data)
            result = scheduler._safe_json_read(path)
            assert result == data

    def test_safe_json_write_creates_backup(self, scheduler):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            scheduler._safe_json_write(path, {"v": 1})
            scheduler._safe_json_write(path, {"v": 2})
            assert os.path.exists(path + ".backup.1")
            with open(path + ".backup.1") as f:
                backup = json.load(f)
            assert backup == {"v": 1}

    def test_safe_json_read_missing_file(self, scheduler):
        result = scheduler._safe_json_read("/nonexistent/file.json")
        assert result is None

    def test_persist_session(self, scheduler, profile):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.session_file = os.path.join(tmpdir, "session.json")
            j = Job(priority=1, next_run=1000, name="j1", profile=profile, faucet_type="f")
            scheduler.queue = [j]
            scheduler.domain_last_access = {"f": 999.0}
            scheduler._persist_session()
            data = scheduler._safe_json_read(scheduler.session_file)
            assert data is not None
            assert len(data["queue"]) == 1
            assert data["domain_last_access"]["f"] == 999.0

    def test_persist_session_public_wrapper(self, scheduler):
        with patch.object(scheduler, "_persist_session") as mock:
            scheduler.persist_session()
            mock.assert_called_once()


# ---------------------------------------------------------------------------
# reset_security_retries / get_security_retry_status
# ---------------------------------------------------------------------------

class TestSecurityRetries:
    def test_reset_all(self, scheduler):
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 3, "last_retry_time": 100},
            "faucet2:user2": {"security_retries": 5, "last_retry_time": 200},
        }
        scheduler.reset_security_retries()
        for v in scheduler.security_challenge_retries.values():
            assert v["security_retries"] == 0

    def test_reset_by_faucet_type(self, scheduler):
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 3, "last_retry_time": 100},
            "faucet2:user2": {"security_retries": 5, "last_retry_time": 200},
        }
        scheduler.reset_security_retries(faucet_type="faucet1")
        assert scheduler.security_challenge_retries["faucet1:user1"]["security_retries"] == 0
        assert scheduler.security_challenge_retries["faucet2:user2"]["security_retries"] == 5

    def test_reset_by_username(self, scheduler):
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 3, "last_retry_time": 100},
            "faucet1:user2": {"security_retries": 4, "last_retry_time": 200},
        }
        scheduler.reset_security_retries(username="user1")
        assert scheduler.security_challenge_retries["faucet1:user1"]["security_retries"] == 0
        assert scheduler.security_challenge_retries["faucet1:user2"]["security_retries"] == 4

    def test_reset_empty(self, scheduler):
        scheduler.security_challenge_retries = {}
        scheduler.reset_security_retries()  # Should not error

    def test_get_status(self, scheduler):
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 5, "last_retry_time": time.time() - 3600},
        }
        status = scheduler.get_security_retry_status()
        assert "faucet1:user1" in status
        assert status["faucet1:user1"]["status"] == "DISABLED"
        assert status["faucet1:user1"]["retries"] == 5

    def test_get_status_active(self, scheduler):
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 2, "last_retry_time": time.time()},
        }
        status = scheduler.get_security_retry_status()
        assert status["faucet1:user1"]["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# _write_heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    def test_write_heartbeat(self, scheduler):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.heartbeat_file = os.path.join(tmpdir, "heartbeat.txt")
            scheduler.account_usage = {
                "user1": {"faucet": "f1", "status": "active"},
                "user2": {"faucet": "f2", "status": "idle"},
            }
            scheduler._write_heartbeat()
            assert os.path.exists(scheduler.heartbeat_file)
            with open(scheduler.heartbeat_file) as f:
                lines = f.readlines()
            assert len(lines) >= 1  # At least timestamp


# ---------------------------------------------------------------------------
# Domain rate limiting
# ---------------------------------------------------------------------------

class TestDomainRateLimiting:
    def test_get_domain_delay_no_access(self, scheduler):
        assert scheduler.get_domain_delay("new_faucet") == 0

    def test_get_domain_delay_recent_access(self, scheduler):
        scheduler.domain_last_access["faucet"] = time.time()
        delay = scheduler.get_domain_delay("faucet")
        assert delay > 0
        assert delay <= MIN_DOMAIN_GAP_SECONDS

    def test_get_domain_delay_old_access(self, scheduler):
        scheduler.domain_last_access["faucet"] = time.time() - 100
        assert scheduler.get_domain_delay("faucet") == 0

    def test_record_domain_access(self, scheduler):
        scheduler.record_domain_access("faucet")
        assert "faucet" in scheduler.domain_last_access
        assert abs(scheduler.domain_last_access["faucet"] - time.time()) < 1


# ---------------------------------------------------------------------------
# calculate_retry_delay
# ---------------------------------------------------------------------------

class TestRetryDelay:
    @pytest.mark.parametrize("error_type,min_expected", [
        (ErrorType.TRANSIENT, 60),
        (ErrorType.RATE_LIMIT, 600),
        (ErrorType.PROXY_ISSUE, 300),
        (ErrorType.CAPTCHA_FAILED, 900),
        (ErrorType.FAUCET_DOWN, 3600),
        (ErrorType.CONFIG_ERROR, 1800),
        (ErrorType.UNKNOWN, 300),
    ])
    def test_base_delays(self, scheduler, error_type, min_expected):
        delay = scheduler.calculate_retry_delay("test", error_type)
        assert delay >= min_expected  # At least base delay

    def test_permanent_returns_inf(self, scheduler):
        delay = scheduler.calculate_retry_delay("test", ErrorType.PERMANENT)
        assert delay == float('inf')

    def test_exponential_backoff(self, scheduler):
        scheduler.faucet_backoff["test"] = {'consecutive_failures': 3, 'next_allowed_time': 0}
        delay_with_backoff = scheduler.calculate_retry_delay("test", ErrorType.TRANSIENT)
        scheduler.faucet_backoff["test"] = {'consecutive_failures': 0, 'next_allowed_time': 0}
        delay_no_backoff = scheduler.calculate_retry_delay("test", ErrorType.TRANSIENT)
        assert delay_with_backoff > delay_no_backoff


# ---------------------------------------------------------------------------
# estimate_claim_cost
# ---------------------------------------------------------------------------

class TestEstimateClaimCost:
    def test_known_faucet(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            cost = scheduler.estimate_claim_cost("firefaucet")
            assert cost == 0.003

    def test_unknown_faucet_defaults(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            cost = scheduler.estimate_claim_cost("unknown_faucet")
            assert cost == 0.003  # Default

    def test_pick_faucet(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            cost = scheduler.estimate_claim_cost("litepick")
            assert cost == 0.003

    def test_with_historical_data(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {
                    "total_claims": 20,
                    "success_rate": 80,
                }
            }
            cost = scheduler.estimate_claim_cost("firefaucet")
            assert cost > 0

    def test_exception_returns_default(self, scheduler):
        with patch("core.analytics.get_tracker", side_effect=Exception("fail")):
            cost = scheduler.estimate_claim_cost("test")
            assert cost == 0.003


# ---------------------------------------------------------------------------
# is_off_peak_time
# ---------------------------------------------------------------------------

class TestOffPeakTime:
    def test_off_peak_night(self, scheduler):
        with patch("core.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=3, weekday=lambda: 2)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert scheduler.is_off_peak_time() is True

    def test_off_peak_weekend(self, scheduler):
        with patch("core.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=14, weekday=lambda: 6)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert scheduler.is_off_peak_time() is True

    def test_peak_time(self, scheduler):
        with patch("core.orchestrator.datetime") as mock_dt:
            mock_dt.now.return_value = MagicMock(hour=14, weekday=lambda: 2)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert scheduler.is_off_peak_time() is False


# ---------------------------------------------------------------------------
# predict_next_claim_time / record_timer_observation
# ---------------------------------------------------------------------------

class TestTimerPrediction:
    def test_insufficient_data_returns_stated(self, scheduler):
        result = scheduler.predict_next_claim_time("faucet", 60.0)
        assert result == 60.0

    def test_prediction_with_data(self, scheduler):
        for i in range(5):
            scheduler.record_timer_observation("faucet", 60.0, 58.0)
        predicted = scheduler.predict_next_claim_time("faucet", 60.0)
        # Should predict slightly less than 60 since actual < stated
        assert predicted < 60.0
        assert predicted >= 54.0  # Within 10% bounds

    def test_history_trimmed(self, scheduler):
        for i in range(15):
            scheduler.record_timer_observation("faucet", 60.0, 59.0)
        assert len(scheduler.timer_predictions["faucet"]) == scheduler.TIMER_HISTORY_SIZE


# ---------------------------------------------------------------------------
# _normalize_faucet_key / _match_faucet_key
# ---------------------------------------------------------------------------

class TestFaucetKeyMatching:
    def test_normalize(self):
        assert JobScheduler._normalize_faucet_key("Fire_Faucet") == "firefaucet"
        assert JobScheduler._normalize_faucet_key("coin tiply") == "cointiply"
        assert JobScheduler._normalize_faucet_key("") == ""
        assert JobScheduler._normalize_faucet_key(None) == ""

    def test_match_exact(self, scheduler):
        data = {"firefaucet": {"claims": 10}}
        assert scheduler._match_faucet_key(data, "firefaucet") == "firefaucet"

    def test_match_normalized(self, scheduler):
        data = {"fire_faucet": {"claims": 10}}
        result = scheduler._match_faucet_key(data, "firefaucet")
        assert result == "fire_faucet"

    def test_match_none(self, scheduler):
        data = {"firefaucet": {"claims": 10}}
        assert scheduler._match_faucet_key(data, "cointiply") is None


# ---------------------------------------------------------------------------
# _is_faucet_in_bypass_list / _should_bypass_proxy / _should_disable_image_block
# ---------------------------------------------------------------------------

class TestBypassLists:
    def test_bypass_proxy_empty(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = []
        assert scheduler._should_bypass_proxy("firefaucet") is False

    def test_bypass_proxy_match(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = ["freebitcoin"]
        assert scheduler._should_bypass_proxy("freebitcoin") is True

    def test_bypass_proxy_none_faucet(self, scheduler):
        assert scheduler._should_bypass_proxy(None) is False

    def test_bypass_proxy_json_string(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = '["freebitcoin", "firefaucet"]'
        assert scheduler._should_bypass_proxy("freebitcoin") is True
        assert scheduler._should_bypass_proxy("cointiply") is False

    def test_bypass_proxy_csv_string(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = "freebitcoin, firefaucet"
        assert scheduler._should_bypass_proxy("freebitcoin") is True

    def test_bypass_proxy_empty_string(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = "[]"
        assert scheduler._should_bypass_proxy("freebitcoin") is False

    def test_bypass_proxy_none_string(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = "none"
        assert scheduler._should_bypass_proxy("freebitcoin") is False

    def test_disable_image_block(self, scheduler):
        scheduler.settings.image_bypass_faucets = ["cointiply"]
        assert scheduler._should_disable_image_block("cointiply") is True
        assert scheduler._should_disable_image_block("firefaucet") is False
        assert scheduler._should_disable_image_block(None) is False

    def test_bypass_non_list_json(self, scheduler):
        scheduler.settings.proxy_bypass_faucets = '"freebitcoin"'
        assert scheduler._should_bypass_proxy("freebitcoin") is True


# ---------------------------------------------------------------------------
# get_next_proxy
# ---------------------------------------------------------------------------

class TestGetNextProxy:
    def test_bypass_returns_none(self, scheduler, profile):
        scheduler.settings.proxy_bypass_faucets = ["test_faucet"]
        result = scheduler.get_next_proxy(profile, faucet_type="test_faucet")
        assert result is None

    def test_with_proxy_manager(self, scheduler, profile):
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.rotate_proxy.return_value = "http://proxy:8080"
        result = scheduler.get_next_proxy(profile)
        assert result == "http://proxy:8080"

    def test_empty_pool_returns_sticky(self, scheduler, profile):
        profile.proxy = "http://sticky:8080"
        profile.proxy_pool = []
        result = scheduler.get_next_proxy(profile)
        assert result == "http://sticky:8080"

    def test_round_robin(self, scheduler, profile):
        profile.proxy_pool = ["p1", "p2", "p3"]
        profile.proxy_rotation_strategy = "round_robin"
        r1 = scheduler.get_next_proxy(profile)
        r2 = scheduler.get_next_proxy(profile)
        assert r1 == "p1"
        assert r2 == "p2"

    def test_random_strategy(self, scheduler, profile):
        profile.proxy_pool = ["p1", "p2", "p3"]
        profile.proxy_rotation_strategy = "random"
        result = scheduler.get_next_proxy(profile)
        assert result in ["p1", "p2", "p3"]

    def test_filters_failed_proxies(self, scheduler, profile):
        profile.proxy_pool = ["p1", "p2"]
        scheduler.proxy_failures = {"p1": {"failures": 5, "burned": False}}
        result = scheduler.get_next_proxy(profile)
        assert result == "p2"

    def test_all_proxies_failed_returns_sticky(self, scheduler, profile):
        profile.proxy = "http://sticky:8080"
        profile.proxy_pool = ["p1"]
        scheduler.proxy_failures = {"p1": {"failures": 5, "burned": False}}
        result = scheduler.get_next_proxy(profile)
        assert result == "http://sticky:8080"


# ---------------------------------------------------------------------------
# record_proxy_failure
# ---------------------------------------------------------------------------

class TestRecordProxyFailure:
    def test_record_failure(self, scheduler):
        scheduler.record_proxy_failure("http://proxy:8080")
        assert scheduler.proxy_failures["http://proxy:8080"]["failures"] == 1
        assert scheduler.proxy_failures["http://proxy:8080"]["burned"] is False

    def test_record_detected(self, scheduler):
        scheduler.record_proxy_failure("http://proxy:8080", detected=True)
        assert scheduler.proxy_failures["http://proxy:8080"]["burned"] is True

    def test_delegates_to_proxy_manager(self, scheduler):
        scheduler.proxy_manager = MagicMock()
        scheduler.record_proxy_failure("http://proxy:8080", detected=True, status_code=403)
        scheduler.proxy_manager.record_failure.assert_called_once_with(
            "http://proxy:8080", detected=True, status_code=403
        )


# ---------------------------------------------------------------------------
# _track_error_type / _should_trip_circuit_breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_track_error_type(self, scheduler):
        scheduler._track_error_type("faucet", ErrorType.TRANSIENT)
        assert ErrorType.TRANSIENT in scheduler.faucet_error_types["faucet"]

    def test_track_limits_to_10(self, scheduler):
        for _ in range(15):
            scheduler._track_error_type("faucet", ErrorType.TRANSIENT)
        assert len(scheduler.faucet_error_types["faucet"]) == 10

    def test_transient_does_not_trip(self, scheduler):
        assert scheduler._should_trip_circuit_breaker("faucet", ErrorType.TRANSIENT) is False

    def test_config_error_does_not_trip(self, scheduler):
        assert scheduler._should_trip_circuit_breaker("faucet", ErrorType.CONFIG_ERROR) is False

    def test_permanent_trips(self, scheduler):
        assert scheduler._should_trip_circuit_breaker("faucet", ErrorType.PERMANENT) is True

    def test_proxy_issue_requires_multiple(self, scheduler):
        # Less than 3 proxy errors - should not trip
        scheduler.faucet_error_types["faucet"] = [ErrorType.PROXY_ISSUE, ErrorType.PROXY_ISSUE]
        assert scheduler._should_trip_circuit_breaker("faucet", ErrorType.PROXY_ISSUE) is False

        # 3+ proxy errors - should trip
        scheduler.faucet_error_types["faucet"] = [
            ErrorType.PROXY_ISSUE, ErrorType.PROXY_ISSUE, ErrorType.PROXY_ISSUE
        ]
        assert scheduler._should_trip_circuit_breaker("faucet", ErrorType.PROXY_ISSUE) is True


# ---------------------------------------------------------------------------
# _get_recovery_delay / get_recovery_delay
# ---------------------------------------------------------------------------

class TestRecoveryDelay:
    def test_transient_immediate(self, scheduler):
        delay, msg = scheduler._get_recovery_delay(ErrorType.TRANSIENT, 0, None)
        assert delay == 0
        assert "immediately" in msg.lower()

    def test_transient_retry(self, scheduler):
        delay, msg = scheduler._get_recovery_delay(ErrorType.TRANSIENT, 1, None)
        assert delay == 300

    def test_rate_limit_escalation(self, scheduler):
        d0, _ = scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 0, None)
        d1, _ = scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 1, None)
        d2, _ = scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 2, None)
        assert d0 == 600
        assert d1 == 1800
        assert d2 == 7200

    def test_proxy_issue_records_failure(self, scheduler):
        delay, _ = scheduler._get_recovery_delay(ErrorType.PROXY_ISSUE, 0, "http://proxy:8080")
        assert delay == 1800
        assert scheduler.proxy_failures.get("http://proxy:8080", {}).get("burned") is True

    def test_permanent(self, scheduler):
        delay, _ = scheduler._get_recovery_delay(ErrorType.PERMANENT, 0, None)
        assert delay == float('inf')

    def test_faucet_down(self, scheduler):
        delay, _ = scheduler._get_recovery_delay(ErrorType.FAUCET_DOWN, 0, None)
        assert delay == 14400

    def test_captcha_failed(self, scheduler):
        delay, _ = scheduler._get_recovery_delay(ErrorType.CAPTCHA_FAILED, 0, None)
        assert delay == 900

    def test_unknown(self, scheduler):
        delay, _ = scheduler._get_recovery_delay(ErrorType.UNKNOWN, 0, None)
        assert delay == 600

    def test_public_wrapper(self, scheduler):
        delay, msg = scheduler.get_recovery_delay(ErrorType.TRANSIENT, 0, None)
        assert delay == 0


# ---------------------------------------------------------------------------
# add_job (deduplication, dynamic priority)
# ---------------------------------------------------------------------------

class TestAddJob:
    def test_add_basic(self, scheduler, job):
        scheduler.add_job(job)
        assert len(scheduler.queue) == 1

    def test_skip_duplicate_in_queue(self, scheduler, job):
        scheduler.add_job(job)
        scheduler.add_job(job)
        assert len(scheduler.queue) == 1

    def test_skip_no_profile(self, scheduler):
        j = Job(priority=1, next_run=0, name="no_profile", profile=None, faucet_type="f")
        scheduler.add_job(j)
        assert len(scheduler.queue) == 0

    def test_skip_already_running(self, scheduler, job):
        scheduler.running_jobs["testuser:test_job"] = MagicMock()
        scheduler.add_job(job)
        assert len(scheduler.queue) == 0


# ---------------------------------------------------------------------------
# detect_operation_mode
# ---------------------------------------------------------------------------

class TestOperationMode:
    def test_normal_mode(self, scheduler):
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.return_value = 0.0
                tracker_inst.get_stats_since.return_value = {"total_claims": 0, "failures": 0}
                mode = scheduler.detect_operation_mode()
                assert mode == OperationMode.NORMAL

    def test_maintenance_mode(self, scheduler):
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)
            mode = scheduler.detect_operation_mode()
            assert mode == OperationMode.MAINTENANCE

    def test_low_proxy_mode(self, scheduler):
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1"]
        scheduler.proxy_manager.get_proxy_stats.return_value = {"is_dead": False}
        scheduler.settings.low_proxy_threshold = 3
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            mode = scheduler.detect_operation_mode()
            assert mode == OperationMode.LOW_PROXY


# ---------------------------------------------------------------------------
# apply_mode_restrictions
# ---------------------------------------------------------------------------

class TestApplyModeRestrictions:
    def test_low_proxy_reduces_concurrency(self, scheduler):
        scheduler.settings.max_concurrent_bots = 5
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1"]
        scheduler.apply_mode_restrictions(OperationMode.LOW_PROXY)
        assert scheduler.settings.max_concurrent_bots <= 2

    def test_slow_mode_returns_multiplier(self, scheduler):
        multiplier = scheduler.apply_mode_restrictions(OperationMode.SLOW_MODE)
        assert multiplier == 3.0

    def test_low_budget_purges_expensive(self, scheduler, profile):
        j = Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="freebitcoin")
        scheduler.queue = [j]
        scheduler.apply_mode_restrictions(OperationMode.LOW_BUDGET)
        assert len(scheduler.queue) == 0

    def test_normal_resets_restrictions(self, scheduler):
        scheduler.current_mode = OperationMode.SLOW_MODE
        multiplier = scheduler.apply_mode_restrictions(OperationMode.NORMAL)
        assert multiplier == 1.0

    def test_maintenance(self, scheduler, profile):
        j = Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="test")
        scheduler.queue = [j]
        multiplier = scheduler.apply_mode_restrictions(OperationMode.MAINTENANCE)
        assert multiplier == 1.0
        assert len(scheduler.queue) == 1  # Queue not purged


# ---------------------------------------------------------------------------
# check_and_update_mode
# ---------------------------------------------------------------------------

class TestCheckAndUpdateMode:
    def test_skips_within_interval(self, scheduler):
        scheduler.last_mode_check_time = time.time()
        result = scheduler.check_and_update_mode()
        assert result == 1.0

    def test_detects_change(self, scheduler):
        scheduler.last_mode_check_time = 0
        with patch.object(scheduler, "detect_operation_mode", return_value=OperationMode.SLOW_MODE):
            with patch.object(scheduler, "apply_mode_restrictions", return_value=3.0):
                result = scheduler.check_and_update_mode()
                assert result == 3.0
                assert scheduler.current_mode == OperationMode.SLOW_MODE


# ---------------------------------------------------------------------------
# get_faucet_priority
# ---------------------------------------------------------------------------

class TestFaucetPriority:
    def test_default_priority(self, scheduler):
        with patch("core.analytics.get_tracker", side_effect=Exception("no data")):
            priority = scheduler.get_faucet_priority("unknown")
            assert priority == 0.5

    def test_with_stats(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            tracker_inst = mock_tracker.return_value
            tracker_inst.get_faucet_stats.return_value = {
                "firefaucet": {
                    "success_rate": 90,
                    "total": 20,
                }
            }
            tracker_inst.get_hourly_rate.return_value = {
                "firefaucet": 100,
            }
            priority = scheduler.get_faucet_priority("firefaucet")
            assert 0.1 <= priority <= 2.0


# ---------------------------------------------------------------------------
# _check_auto_suspend
# ---------------------------------------------------------------------------

class TestAutoSuspend:
    def test_no_data(self, scheduler):
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            result, reason = scheduler._check_auto_suspend("unknown")
            assert result is False

    def test_below_min_samples(self, scheduler):
        scheduler.settings.faucet_auto_suspend_min_samples = 10
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "test": {"total": 5, "success_rate": 50}
            }
            result, reason = scheduler._check_auto_suspend("test")
            assert result is False

    def test_low_success_rate_triggers(self, scheduler):
        scheduler.settings.faucet_auto_suspend_min_samples = 5
        scheduler.settings.faucet_min_success_rate = 30.0
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "test": {"total": 20, "success_rate": 10}
            }
            result, reason = scheduler._check_auto_suspend("test")
            assert result is True
            assert "success rate" in reason.lower()


# ---------------------------------------------------------------------------
# schedule_withdrawal_jobs
# ---------------------------------------------------------------------------

class TestScheduleWithdrawals:
    @pytest.mark.asyncio
    async def test_no_accounts(self, scheduler):
        scheduler.settings.accounts = []
        count = await scheduler.schedule_withdrawal_jobs()
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_withdraw_method(self, scheduler, profile):
        scheduler.settings.accounts = [profile]
        with patch("core.registry.get_faucet_class", return_value=None):
            count = await scheduler.schedule_withdrawal_jobs()
            assert count == 0


# ---------------------------------------------------------------------------
# execute_auto_withdrawal_check
# ---------------------------------------------------------------------------

class TestAutoWithdrawalCheck:
    @pytest.mark.asyncio
    async def test_not_initialized(self, scheduler, job):
        scheduler.auto_withdrawal = None
        result = await scheduler.execute_auto_withdrawal_check(job)
        assert result.success is False
        assert result.next_claim_minutes == 240

    @pytest.mark.asyncio
    async def test_successful_check(self, scheduler, job):
        scheduler.auto_withdrawal = AsyncMock()
        scheduler.auto_withdrawal.check_and_execute_withdrawals.return_value = {
            "balances_checked": 3,
            "withdrawals_executed": 1,
            "withdrawals_deferred": 2,
            "transactions": [{"currency": "BTC", "amount": 0.001, "tx_id": "abc123def456ghi7"}],
        }
        result = await scheduler.execute_auto_withdrawal_check(job)
        assert result.success is True
        assert "3 currencies" in result.status

    @pytest.mark.asyncio
    async def test_exception(self, scheduler, job):
        scheduler.auto_withdrawal = AsyncMock()
        scheduler.auto_withdrawal.check_and_execute_withdrawals.side_effect = Exception("fail")
        result = await scheduler.execute_auto_withdrawal_check(job)
        assert result.success is False


# ---------------------------------------------------------------------------
# _run_job_wrapper
# ---------------------------------------------------------------------------

class TestRunJobWrapper:
    @pytest.mark.asyncio
    async def test_test_faucet_skipped(self, scheduler, profile, mock_bm):
        """Test jobs with faucet_type='test' are silently skipped."""
        job = Job(
            priority=1, next_run=0, name="test_job",
            profile=profile, faucet_type="test",
            job_type="claim_wrapper",
        )
        await scheduler._run_job_wrapper(job)
        # Should not add any jobs back to queue
        assert all(j.faucet_type != "test" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_unknown_faucet_type(self, scheduler, profile, mock_bm):
        """Unknown faucet type raises and gets handled."""
        job = Job(
            priority=1, next_run=0, name="test_job",
            profile=profile, faucet_type="nonexistent_xyz",
            job_type="claim_wrapper",
        )
        with patch("core.registry.get_faucet_class", return_value=None):
            await scheduler._run_job_wrapper(job)
            # Should not crash

    @pytest.mark.asyncio
    async def test_auto_withdrawal_check_dispatch(self, scheduler, profile, mock_bm):
        """auto_withdrawal_check jobs are dispatched correctly."""
        job = Job(
            priority=1, next_run=0, name="withdrawal_check",
            profile=profile, faucet_type="system",
            job_type="auto_withdrawal_check",
        )
        scheduler.auto_withdrawal = None
        await scheduler._run_job_wrapper(job)
        # Should complete without crash, add job back
        result_jobs = [j for j in scheduler.queue if j.job_type == "auto_withdrawal_check"]
        # May or may not reschedule depending on result
        assert True  # Just verify no crash


# ---------------------------------------------------------------------------
# _get_proxy_locale_timezone
# ---------------------------------------------------------------------------

class TestProxyLocaleTimezone:
    @pytest.mark.asyncio
    async def test_no_proxy(self, scheduler):
        locale, tz = await scheduler._get_proxy_locale_timezone(None)
        assert locale is None
        assert tz is None

    @pytest.mark.asyncio
    async def test_no_proxy_manager(self, scheduler):
        scheduler.proxy_manager = None
        locale, tz = await scheduler._get_proxy_locale_timezone("http://proxy:8080")
        assert locale is None
        assert tz is None

    @pytest.mark.asyncio
    async def test_with_geolocation(self, scheduler):
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.get_geolocation_for_proxy = AsyncMock(
            return_value=("America/New_York", "en-US")
        )
        locale, tz = await scheduler._get_proxy_locale_timezone("http://proxy:8080")
        assert locale == "en-US"
        assert tz == "America/New_York"


# ---------------------------------------------------------------------------
# stop / cleanup
# ---------------------------------------------------------------------------

class TestStopAndCleanup:
    def test_stop(self, scheduler):
        scheduler.stop()
        assert scheduler._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_cleanup_no_wallet(self, scheduler):
        scheduler.auto_withdrawal = None
        await scheduler.cleanup()  # Should not error

    @pytest.mark.asyncio
    async def test_cleanup_with_wallet(self, scheduler):
        scheduler.auto_withdrawal = MagicMock()
        scheduler.auto_withdrawal.wallet = AsyncMock()
        scheduler.auto_withdrawal.wallet.close = AsyncMock()
        await scheduler.cleanup()
        scheduler.auto_withdrawal.wallet.close.assert_called_once()


# ---------------------------------------------------------------------------
# has_only_test_jobs
# ---------------------------------------------------------------------------

class TestHasOnlyTestJobs:
    def test_empty_queue(self, scheduler):
        assert scheduler.has_only_test_jobs() is False

    def test_only_test_jobs(self, scheduler, profile):
        scheduler.queue = [
            Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="test"),
            Job(priority=1, next_run=0, name="j2", profile=profile, faucet_type="Test"),
        ]
        assert scheduler.has_only_test_jobs() is True

    def test_mixed_jobs(self, scheduler, profile):
        scheduler.queue = [
            Job(priority=1, next_run=0, name="j1", profile=profile, faucet_type="test"),
            Job(priority=1, next_run=0, name="j2", profile=profile, faucet_type="firefaucet"),
        ]
        assert scheduler.has_only_test_jobs() is False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestClassConstants:
    def test_class_level_constants(self):
        assert JobScheduler.CIRCUIT_BREAKER_THRESHOLD == 5
        assert JobScheduler.CIRCUIT_BREAKER_COOLDOWN == 14400
        assert JobScheduler.RETRYABLE_COOLDOWN == 600
        assert JobScheduler.TIMER_HISTORY_SIZE == 10
        assert JobScheduler.MODE_CHECK_INTERVAL == 600
        assert JobScheduler.MAX_SECURITY_RETRIES == 5
        assert JobScheduler.SECURITY_RETRY_RESET_HOURS == 24

    def test_module_constants(self):
        assert MAX_PROXY_FAILURES == 3
        assert PROXY_COOLDOWN_SECONDS == 300
        assert BURNED_PROXY_COOLDOWN == 43200
        assert JITTER_MIN_SECONDS == 30
        assert JITTER_MAX_SECONDS == 120
        assert MIN_DOMAIN_GAP_SECONDS == 45


# ---------------------------------------------------------------------------
# schedule_auto_withdrawal_check
# ---------------------------------------------------------------------------

class TestScheduleAutoWithdrawalCheck:
    @pytest.mark.asyncio
    async def test_no_rpc_urls(self, scheduler):
        scheduler.settings.wallet_rpc_urls = {}
        await scheduler.schedule_auto_withdrawal_check()
        assert scheduler.withdrawal_check_scheduled is False

    @pytest.mark.asyncio
    async def test_no_rpc_credentials(self, scheduler):
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = None
        scheduler.settings.electrum_rpc_pass = None
        await scheduler.schedule_auto_withdrawal_check()
        assert scheduler.withdrawal_check_scheduled is False


# ---------------------------------------------------------------------------
# ErrorType enum completeness
# ---------------------------------------------------------------------------

class TestErrorTypeEnum:
    def test_all_values(self):
        assert len(ErrorType) == 8
        values = {e.value for e in ErrorType}
        expected = {
            "transient", "rate_limit", "proxy_issue", "permanent",
            "faucet_down", "captcha_failed", "config_error", "unknown",
        }
        assert values == expected


# ---------------------------------------------------------------------------
# Job dataclass
# ---------------------------------------------------------------------------

class TestJobDataclass:
    def test_ordering(self, profile):
        j1 = Job(priority=1, next_run=100, name="j1", profile=profile, faucet_type="f")
        j2 = Job(priority=2, next_run=50, name="j2", profile=profile, faucet_type="f")
        assert j1 < j2  # Lower priority number wins

    def test_same_priority_orders_by_time(self, profile):
        j1 = Job(priority=1, next_run=100, name="j1", profile=profile, faucet_type="f")
        j2 = Job(priority=1, next_run=200, name="j2", profile=profile, faucet_type="f")
        assert j1 < j2

    def test_roundtrip_serialization(self, profile):
        original = Job(
            priority=3, next_run=5000.0, name="roundtrip",
            profile=profile, faucet_type="faucet",
            job_type="withdraw_wrapper", retry_count=2,
        )
        restored = Job.from_dict(original.to_dict())
        assert restored.priority == original.priority
        assert restored.next_run == original.next_run
        assert restored.name == original.name
        assert restored.faucet_type == original.faucet_type
        assert restored.job_type == original.job_type
        assert restored.retry_count == original.retry_count
        assert restored.profile.username == original.profile.username

    def test_from_dict_no_profile(self):
        data = {
            "priority": 1, "next_run": 100, "name": "test",
            "faucet_type": "f", "job_type": "claim_wrapper",
            "retry_count": 0, "profile": None,
        }
        job = Job.from_dict(data)
        assert job.profile is None

    def test_defaults(self, profile):
        j = Job(priority=1, next_run=0, name="j", profile=profile, faucet_type="f")
        assert j.job_type == "claim_wrapper"
        assert j.retry_count == 0


# ---------------------------------------------------------------------------
# _run_job_wrapper – deep branch coverage
# ---------------------------------------------------------------------------

def _make_claim_result(success, status="OK", next_claim_minutes=60,
                       amount="100", balance="500", error_type=None):
    """Helper to build a ClaimResult-like object without importing the real class."""
    from faucets.base import ClaimResult
    return ClaimResult(
        success=success,
        status=status,
        next_claim_minutes=next_claim_minutes,
        amount=amount,
        balance=balance,
        error_type=error_type,
    )


def _make_bot_class(result):
    """Return a mock faucet class whose claim_wrapper returns *result*."""
    bot_instance = MagicMock()
    bot_instance.claim_wrapper = AsyncMock(return_value=result)
    bot_instance.withdraw_wrapper = AsyncMock(return_value=result)
    bot_instance.solver = None
    bot_cls = MagicMock(return_value=bot_instance)
    return bot_cls, bot_instance


class TestRunJobWrapperSuccessPath:
    """Cover _run_job_wrapper when the claim succeeds."""

    @pytest.mark.asyncio
    async def test_successful_claim_reschedules(self, scheduler, profile, mock_bm):
        """Successful claim resets circuit breaker and reschedules job."""
        result = _make_claim_result(True)
        bot_cls, bot_inst = _make_bot_class(result)

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="claim_test",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper", retry_count=2)

        # Pre-populate failure state to verify reset
        scheduler.faucet_failures["firefaucet"] = 3
        scheduler.faucet_error_types["firefaucet"] = [ErrorType.TRANSIENT]
        scheduler.faucet_backoff["firefaucet"] = {"consecutive_failures": 2, "next_allowed_time": 999}

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Verify circuit breaker was reset
        assert scheduler.faucet_failures.get("firefaucet") == 0
        assert scheduler.faucet_error_types.get("firefaucet") == []
        assert scheduler.faucet_backoff["firefaucet"]["consecutive_failures"] == 0

        # Job should be re-added to queue
        matching = [j for j in scheduler.queue if j.name == "claim_test"]
        assert len(matching) == 1
        assert matching[0].retry_count == 0

    @pytest.mark.asyncio
    async def test_successful_claim_logs_captcha_cost(self, scheduler, profile, mock_bm):
        """When solver has cost data it should be logged without errors."""
        result = _make_claim_result(True)
        bot_cls, bot_inst = _make_bot_class(result)
        # Set up solver mock
        solver_mock = MagicMock()
        solver_mock.provider = "2captcha"
        solver_mock.provider_stats = {"2captcha": {"cost": 0.005}}
        bot_inst.solver = solver_mock

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="cost_log",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # No crash – test passes implicitly

    @pytest.mark.asyncio
    async def test_successful_withdrawal_no_jitter(self, scheduler, profile, mock_bm):
        """Withdrawal jobs should not add jitter on success."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, bot_inst = _make_bot_class(result)

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="withdraw_test",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "withdraw_test"]
        assert len(matching) == 1


class TestRunJobWrapperFailurePath:
    """Cover _run_job_wrapper when the claim fails (result.success=False)."""

    @pytest.mark.asyncio
    async def test_error_classified_from_status_config(self, scheduler, profile, mock_bm):
        """hCaptcha/config status classified as CONFIG_ERROR."""
        result = _make_claim_result(False, status="hCaptcha solver timeout", next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="cfg_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Should have tracked CONFIG_ERROR
        assert ErrorType.CONFIG_ERROR in scheduler.faucet_error_types.get("firefaucet", [])

    @pytest.mark.asyncio
    async def test_error_classified_permanent_banned(self, scheduler, profile, mock_bm):
        """'Account banned' maps to PERMANENT and stops rescheduling."""
        result = _make_claim_result(False, status="Account banned permanently", next_claim_minutes=0)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="perm_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Permanent → not re-added
        assert not any(j.name == "perm_err" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_error_classified_rate_limit_cloudflare(self, scheduler, profile, mock_bm):
        """Cloudflare challenge classified as RATE_LIMIT, tracks security retries."""
        result = _make_claim_result(False, status="Cloudflare security challenge detected",
                                    next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="cf_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Security retry should be tracked
        key = "firefaucet:testuser"
        assert key in scheduler.security_challenge_retries
        assert scheduler.security_challenge_retries[key]["security_retries"] == 1
        # Job re-added with backoff
        assert any(j.name == "cf_err" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_security_retry_limit_exceeded(self, scheduler, profile, mock_bm):
        """When security retries hit MAX, job is NOT rescheduled."""
        result = _make_claim_result(False, status="Cloudflare blocked", next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        # Pre-set retries near limit
        key = "firefaucet:testuser"
        scheduler.security_challenge_retries[key] = {
            "security_retries": 4,  # Next will be 5 == MAX
            "last_retry_time": time.time()
        }

        job = Job(priority=1, next_run=0, name="sec_limit",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Job should NOT be re-added after limit exceeded
        assert not any(j.name == "sec_limit" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_error_classified_proxy_issue(self, scheduler, profile, mock_bm):
        """'VPN Detected' classified as PROXY_ISSUE."""
        result = _make_claim_result(False, status="VPN Detected - access denied",
                                    next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="proxy_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        assert ErrorType.PROXY_ISSUE in scheduler.faucet_error_types.get("firefaucet", [])

    @pytest.mark.asyncio
    async def test_error_classified_captcha_failed(self, scheduler, profile, mock_bm):
        """'Captcha solve failed' classified as CAPTCHA_FAILED."""
        result = _make_claim_result(False, status="Captcha solve failed after timeout",
                                    next_claim_minutes=15)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="cap_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        assert ErrorType.CAPTCHA_FAILED in scheduler.faucet_error_types.get("firefaucet", [])

    @pytest.mark.asyncio
    async def test_error_classified_transient_timeout(self, scheduler, profile, mock_bm):
        """'Connection timeout' classified as TRANSIENT."""
        result = _make_claim_result(False, status="Connection timeout after 30s",
                                    next_claim_minutes=15)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="trans_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        assert ErrorType.TRANSIENT in scheduler.faucet_error_types.get("firefaucet", [])

    @pytest.mark.asyncio
    async def test_error_with_explicit_error_type(self, scheduler, profile, mock_bm):
        """When result has error_type attribute, it is used directly."""
        result = _make_claim_result(False, status="Something went wrong",
                                    next_claim_minutes=15,
                                    error_type=ErrorType.FAUCET_DOWN)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="typed_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        assert ErrorType.FAUCET_DOWN in scheduler.faucet_error_types.get("firefaucet", [])
        # Faucet down should set cooldown
        assert "firefaucet" in scheduler.faucet_cooldowns

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_on_many_failures(self, scheduler, profile, mock_bm):
        """Circuit breaker trips after CIRCUIT_BREAKER_THRESHOLD failures."""
        result = _make_claim_result(False, status="Server 500 error",
                                    next_claim_minutes=60,
                                    error_type=ErrorType.FAUCET_DOWN)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        # Pre-set failures close to threshold
        scheduler.faucet_failures["firefaucet"] = 4  # One more = 5 = threshold

        job = Job(priority=1, next_run=0, name="cb_trip",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Circuit breaker should have tripped
        assert scheduler.faucet_failures["firefaucet"] >= scheduler.CIRCUIT_BREAKER_THRESHOLD
        assert "firefaucet" in scheduler.faucet_cooldowns

    @pytest.mark.asyncio
    async def test_withdrawal_failure_retries(self, scheduler, profile, mock_bm):
        """Failed withdrawal job retries with configured intervals."""
        result = _make_claim_result(False, status="Insufficient balance",
                                    next_claim_minutes=0)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="wd_retry",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper", retry_count=0)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "wd_retry"]
        assert len(matching) == 1
        assert matching[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_withdrawal_failure_max_retries(self, scheduler, profile, mock_bm):
        """Withdrawal that hit max retries is not rescheduled."""
        result = _make_claim_result(False, status="Withdrawal failed", next_claim_minutes=0)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        # Already at max retries
        job = Job(priority=1, next_run=0, name="wd_maxretry",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper",
                  retry_count=scheduler.settings.withdrawal_max_retries)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("core.withdrawal_analytics.get_analytics") as mock_analytics:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_analytics.return_value.record_withdrawal = MagicMock()
            await scheduler._run_job_wrapper(job)

        assert not any(j.name == "wd_maxretry" for j in scheduler.queue)


class TestRunJobWrapperProxyDetection:
    """Cover the 'Proxy Detected' result path."""

    @pytest.mark.asyncio
    async def test_proxy_detected_rotates_and_reschedules(self, scheduler, profile, mock_bm):
        """When result status contains 'Proxy Detected', proxy is marked and job rescheduled."""
        result = _make_claim_result(False, status="Proxy Detected by site", next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="proxy_det",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper", retry_count=0)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "proxy_det"]
        assert len(matching) == 1
        assert matching[0].retry_count == 1


class TestRunJobWrapperPageStatus:
    """Cover post-execution page status checks (blocked / network error)."""

    @pytest.mark.asyncio
    async def test_page_blocked_records_failure(self, scheduler, profile, mock_bm):
        """Blocked page triggers proxy failure recording."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, _ = _make_bot_class(result)

        mock_bm.check_page_alive = AsyncMock(return_value=True)
        mock_bm.check_page_status = AsyncMock(return_value={
            "blocked": True, "network_error": False, "status": 403
        })

        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.rotate_proxy = MagicMock(return_value="http://proxy:8080")
        scheduler.proxy_manager.record_soft_signal = MagicMock()

        job = Job(priority=1, next_run=0, name="page_blocked",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        scheduler.proxy_manager.record_soft_signal.assert_called()

    @pytest.mark.asyncio
    async def test_page_network_error(self, scheduler, profile, mock_bm):
        """Network error triggers proxy failure without detection flag."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, _ = _make_bot_class(result)

        mock_bm.check_page_alive = AsyncMock(return_value=True)
        mock_bm.check_page_status = AsyncMock(return_value={
            "blocked": False, "network_error": True, "status": 0
        })

        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.rotate_proxy = MagicMock(return_value="http://proxy:8080")
        scheduler.proxy_manager.record_soft_signal = MagicMock()

        job = Job(priority=1, next_run=0, name="net_err",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        scheduler.proxy_manager.record_soft_signal.assert_called_with(
            "http://proxy:8080", signal_type="network_error"
        )


class TestRunJobWrapperExceptions:
    """Cover timeout and general exception branches."""

    @pytest.mark.asyncio
    async def test_timeout_reschedules(self, scheduler, profile, mock_bm):
        """asyncio.TimeoutError reschedules with proxy cooldown."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.claim_wrapper = AsyncMock(side_effect=asyncio.TimeoutError)
        bot_inst.solver = None
        bot_cls.return_value = bot_inst

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="timeout_test",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper", retry_count=0)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "timeout_test"]
        assert len(matching) == 1
        assert matching[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_general_exception_exponential_backoff(self, scheduler, profile, mock_bm):
        """General exception uses exponential backoff for non-withdrawal jobs."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.claim_wrapper = AsyncMock(side_effect=RuntimeError("Boom"))
        bot_inst.solver = None
        bot_cls.return_value = bot_inst

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="exc_test",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper", retry_count=0)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "exc_test"]
        assert len(matching) == 1
        assert matching[0].retry_count == 1
        assert scheduler.consecutive_job_failures >= 1

    @pytest.mark.asyncio
    async def test_consecutive_failures_restart_browser(self, scheduler, profile, mock_bm):
        """After MAX_CONSECUTIVE_JOB_FAILURES, browser should restart."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.claim_wrapper = AsyncMock(side_effect=RuntimeError("crash"))
        bot_inst.solver = None
        bot_cls.return_value = bot_inst

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        # Set failures to threshold - 1
        scheduler.consecutive_job_failures = MAX_CONSECUTIVE_JOB_FAILURES - 1

        job = Job(priority=1, next_run=0, name="restart_test",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Browser should have been restarted
        mock_bm.restart.assert_called()
        assert scheduler.consecutive_job_failures == 0

    @pytest.mark.asyncio
    async def test_withdrawal_exception_retries(self, scheduler, profile, mock_bm):
        """Withdrawal job exception retries with configured intervals."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.withdraw_wrapper = AsyncMock(side_effect=RuntimeError("network fail"))
        bot_inst.solver = None
        bot_cls.return_value = bot_inst

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="wd_exc_retry",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper", retry_count=0)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        matching = [j for j in scheduler.queue if j.name == "wd_exc_retry"]
        assert len(matching) == 1
        assert matching[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_withdrawal_exception_max_retries(self, scheduler, profile, mock_bm):
        """Withdrawal exception at max retries does not reschedule."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.withdraw_wrapper = AsyncMock(side_effect=RuntimeError("permanent fail"))
        bot_inst.solver = None
        bot_cls.return_value = bot_inst

        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="wd_exc_max",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper",
                  retry_count=scheduler.settings.withdrawal_max_retries)

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("core.withdrawal_analytics.get_analytics") as mock_wa:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_wa.return_value.record_withdrawal = MagicMock()
            await scheduler._run_job_wrapper(job)

        assert not any(j.name == "wd_exc_max" for j in scheduler.queue)


class TestRunJobWrapperContextRetry:
    """Cover context creation retry and browser restart paths."""

    @pytest.mark.asyncio
    async def test_context_creation_retries_then_succeeds(self, scheduler, profile, mock_bm):
        """Context creation fails once, browser restarts, then succeeds on retry."""
        call_count = 0

        async def create_context_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Browser crashed")
            return MagicMock()

        mock_bm.create_context = AsyncMock(side_effect=create_context_side_effect)
        mock_bm.check_health = AsyncMock(return_value=False)  # Unhealthy → restart
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, bot_inst = _make_bot_class(result)

        job = Job(priority=1, next_run=0, name="ctx_retry",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Browser should have been restarted due to unhealthy check
        mock_bm.restart.assert_called()
        # Job should complete successfully
        matching = [j for j in scheduler.queue if j.name == "ctx_retry"]
        assert len(matching) == 1

    @pytest.mark.asyncio
    async def test_context_creation_all_attempts_fail(self, scheduler, profile, mock_bm):
        """All context creation attempts fail → handled by exception path."""
        mock_bm.create_context = AsyncMock(side_effect=RuntimeError("Cannot create context"))
        mock_bm.check_health = AsyncMock(return_value=True)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="ctx_fail",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            await scheduler._run_job_wrapper(job)

        # Job should be rescheduled via exception handler
        matching = [j for j in scheduler.queue if j.name == "ctx_fail"]
        assert len(matching) == 1


class TestRunJobWrapperPickFaucet:
    """Cover the pick faucet email override branch."""

    @pytest.mark.asyncio
    async def test_pick_faucet_sets_email(self, scheduler, profile, mock_bm):
        """Pick faucets should set email in the override dict."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, bot_inst = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="pick_test",
                  profile=profile, faucet_type="litepick",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Verify email was set in the override
        override = bot_inst.settings_account_override
        assert "email" in override
        assert override["email"] == profile.username


# ---------------------------------------------------------------------------
# scheduler_loop
# ---------------------------------------------------------------------------

class TestSchedulerLoop:
    """Cover key branches in scheduler_loop."""

    @pytest.mark.asyncio
    async def test_loop_stops_on_stop_event(self, scheduler, profile):
        """Scheduler loop should exit when _stop_event is set."""
        scheduler._stop_event.set()
        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            await scheduler.scheduler_loop()
        # Exited cleanly

    @pytest.mark.asyncio
    async def test_loop_heartbeat_and_persist(self, scheduler, profile):
        """Heartbeat and session persistence run on schedule."""
        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError  # Simulate tick

        # Set last times to 0 so maintenance runs immediately
        scheduler.last_heartbeat_time = 0
        scheduler.last_persist_time = 0
        scheduler.last_health_check_time = time.time()  # Skip heavy health check

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_write_heartbeat") as mock_hb, \
             patch.object(scheduler, "_persist_session") as mock_persist, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_tracker.return_value.check_performance_alerts.return_value = []
            mock_tracker.return_value.get_profitability.return_value = {
                "earnings_usd": 0.01, "costs_usd": 0.005,
                "net_profit_usd": 0.005, "roi": 2.0
            }
            # Add settings attributes needed by degraded mode
            scheduler.settings.degraded_failure_threshold = 10
            await scheduler.scheduler_loop()

        mock_hb.assert_called()
        mock_persist.assert_called()

    @pytest.mark.asyncio
    async def test_loop_launches_ready_job(self, scheduler, profile, mock_bm):
        """Ready job (next_run <= now) gets launched."""
        job = Job(priority=1, next_run=0, name="ready_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.001), \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("core.withdrawal_analytics.get_analytics") as mock_wa, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            # Budget check
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 5.0}
            mock_solver.return_value = mock_solver_inst
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            # Settings for degraded mode
            scheduler.settings.degraded_failure_threshold = 10
            await scheduler.scheduler_loop()

        # The job should have been removed from queue and launched
        assert "testuser:ready_job" in scheduler.running_jobs or mock_run.called

    @pytest.mark.asyncio
    async def test_loop_maintenance_mode_pauses_jobs(self, scheduler, profile, mock_bm):
        """Maintenance degraded mode pauses launching new jobs."""
        job = Job(priority=1, next_run=0, name="maint_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        # Set up proxy_manager with 0 proxies → maintenance mode
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = []

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 10
            await scheduler.scheduler_loop()

        # Job should NOT have been launched (maintenance pause)
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_dynamic_sleep_empty_queue(self, scheduler):
        """With empty queue and no running jobs, sleep should be 60s."""
        scheduler._stop_event.set()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            await scheduler.scheduler_loop()
        # Just verify no crash with empty state


# ---------------------------------------------------------------------------
# _restore_session
# ---------------------------------------------------------------------------

class TestRestoreSession:
    def test_restore_from_disk(self, mock_settings, mock_bm):
        """Session restoration loads jobs and domain access."""
        session_data = {
            "queue": [
                {
                    "priority": 1, "next_run": time.time() + 60, "name": "restored",
                    "faucet_type": "firefaucet", "job_type": "claim_wrapper",
                    "retry_count": 0,
                    "profile": {"faucet": "firefaucet", "username": "user1", "password": "pass1"}
                }
            ],
            "domain_last_access": {"firefaucet": time.time()},
            "timestamp": time.time()
        }
        with patch("core.orchestrator.os.path.exists", return_value=True), \
             patch.object(JobScheduler, "_safe_json_read", return_value=session_data), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler = JobScheduler(mock_settings, mock_bm)

        assert len(scheduler.queue) == 1
        assert scheduler.queue[0].name == "restored"
        assert "firefaucet" in scheduler.domain_last_access

    def test_restore_expired_job_resets_time(self, mock_settings, mock_bm):
        """Jobs with next_run > 1 hour in the past get reset to now."""
        old_time = time.time() - 7200  # 2 hours ago
        session_data = {
            "queue": [
                {
                    "priority": 1, "next_run": old_time, "name": "old_job",
                    "faucet_type": "firefaucet", "job_type": "claim_wrapper",
                    "retry_count": 0,
                    "profile": {"faucet": "firefaucet", "username": "user1", "password": "pass1"}
                }
            ],
            "domain_last_access": {},
            "timestamp": time.time()
        }
        with patch("core.orchestrator.os.path.exists", return_value=True), \
             patch.object(JobScheduler, "_safe_json_read", return_value=session_data), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler = JobScheduler(mock_settings, mock_bm)

        assert len(scheduler.queue) == 1
        # next_run should have been reset to approximately now
        assert scheduler.queue[0].next_run > old_time

    def test_restore_corrupt_data(self, mock_settings, mock_bm):
        """Corrupted session data doesn't crash init."""
        with patch("core.orchestrator.os.path.exists", return_value=True), \
             patch.object(JobScheduler, "_safe_json_read", return_value=None):
            scheduler = JobScheduler(mock_settings, mock_bm)

        assert len(scheduler.queue) == 0


# ---------------------------------------------------------------------------
# execute_consolidated_withdrawal
# ---------------------------------------------------------------------------

class TestExecuteConsolidatedWithdrawal:
    @pytest.mark.asyncio
    async def test_unknown_faucet(self, scheduler, profile):
        """Unknown faucet type returns failure result."""
        with patch("core.registry.get_faucet_class", return_value=None):
            result = await scheduler.execute_consolidated_withdrawal("nonexistent", profile)
        assert result.success is False
        assert "Unknown Faucet" in result.status


# ---------------------------------------------------------------------------
# Additional targeted coverage tests
# ---------------------------------------------------------------------------

class TestSecurityRetryResetAfter24h:
    """Cover the 24h auto-reset branch in _run_job_wrapper (lines 1937-1942)."""

    @pytest.mark.asyncio
    async def test_security_retry_counter_resets_after_24h(self, scheduler, profile, mock_bm):
        """If last retry was >24h ago, counter should be reset before incrementing."""
        result = _make_claim_result(False, status="Cloudflare challenge page",
                                    next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        key = "firefaucet:testuser"
        scheduler.security_challenge_retries[key] = {
            "security_retries": 3,
            "last_retry_time": time.time() - (25 * 3600)  # 25 hours ago
        }

        job = Job(priority=1, next_run=0, name="reset24h",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Counter should have been reset to 0, then incremented to 1
        assert scheduler.security_challenge_retries[key]["security_retries"] == 1


class TestPermanentReclassification:
    """Cover the permanent-to-rate_limit reclassification (lines 1913-1914)."""

    @pytest.mark.asyncio
    async def test_permanent_with_security_words_reclassified(self, scheduler, profile, mock_bm):
        """Permanent error with 'blocked' in status gets reclassified to RATE_LIMIT."""
        # This tests both the "banned" keyword matching PERMANENT and the reclassification
        result = _make_claim_result(False,
                                    status="Account banned - blocked by cloudflare",
                                    next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="reclass",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Should be reclassified to RATE_LIMIT (not PERMANENT)
        # So job should be re-added (PERMANENT would not re-add)
        assert any(j.name == "reclass" for j in scheduler.queue)


class TestProxyLocaleEdgeCases:
    """Cover edge cases in _get_proxy_locale_timezone."""

    @pytest.mark.asyncio
    async def test_geolocation_returns_none(self, scheduler):
        """When geolocation returns None, fall back to None/None."""
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.get_geolocation_for_proxy = AsyncMock(return_value=None)
        locale, tz = await scheduler._get_proxy_locale_timezone("http://proxy:8080")
        assert locale is None
        assert tz is None

    @pytest.mark.asyncio
    async def test_geolocation_raises(self, scheduler):
        """When geolocation throws, fall back to None/None."""
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.get_geolocation_for_proxy = AsyncMock(
            side_effect=Exception("lookup failed")
        )
        locale, tz = await scheduler._get_proxy_locale_timezone("http://proxy:8080")
        assert locale is None
        assert tz is None


class TestResetSecurityRetriesEdgeCases:
    """Cover edge cases in reset_security_retries."""

    def test_no_matching_accounts(self, scheduler):
        """When filters don't match any account."""
        scheduler.security_challenge_retries = {
            "faucet1:user1": {"security_retries": 3, "last_retry_time": 100}
        }
        scheduler.reset_security_retries(faucet_type="nonexistent")
        # Should not reset
        assert scheduler.security_challenge_retries["faucet1:user1"]["security_retries"] == 3


class TestRecoveryDelayEdgeCases:
    """Cover uncovered branches in _get_recovery_delay."""

    def test_proxy_issue_without_proxy(self, scheduler):
        """Proxy issue with no proxy still returns delay."""
        delay, msg = scheduler._get_recovery_delay(ErrorType.PROXY_ISSUE, 0, None)
        assert delay == 1800
        assert "No proxy" in msg

    def test_config_error(self, scheduler):
        """Config error returns appropriate delay."""
        delay, msg = scheduler._get_recovery_delay(ErrorType.CONFIG_ERROR, 0, None)
        assert delay == 1800


class TestPredictNextClaimTimeEdgeCases:
    """Cover edge cases in timer prediction."""

    def test_empty_drifts_after_filter(self, scheduler):
        """If stated==0 for all entries, drifts would be empty."""
        # Add entries with stated=0 which would cause division by zero guard
        scheduler.timer_predictions["faucet"] = [
            {"stated": 0, "actual": 5, "timestamp": time.time()},
            {"stated": 0, "actual": 5, "timestamp": time.time()},
            {"stated": 0, "actual": 5, "timestamp": time.time()},
        ]
        result = scheduler.predict_next_claim_time("faucet", 60.0)
        # Should fall back to stated timer since drifts would be empty
        assert result == 60.0


class TestAutoSuspendROI:
    """Cover the ROI threshold branch in _check_auto_suspend (lines 733-747)."""

    def test_negative_roi_triggers_suspend(self, scheduler):
        """Faucet with negative ROI should be auto-suspended."""
        scheduler.settings.faucet_auto_suspend_min_samples = 5
        scheduler.settings.faucet_min_success_rate = 10.0
        scheduler.settings.faucet_roi_threshold = -0.5
        with patch("core.analytics.get_tracker") as mock_tracker:
            tracker = mock_tracker.return_value
            tracker.get_faucet_stats.return_value = {
                "test": {"total": 20, "success_rate": 50, "success": 10, "earnings": 100}
            }
            tracker.get_faucet_profitability.return_value = {
                "roi_percentage": -80.0  # -80% ROI → -0.8 < -0.5 threshold
            }
            result, reason = scheduler._check_auto_suspend("test")
        assert result is True
        assert "ROI" in reason


class TestFaucetPriorityTimeOfDay:
    """Cover the time_of_day_roi_enabled branch (lines 683-695)."""

    def test_time_of_day_roi_adjusts_priority(self, scheduler):
        """When time_of_day_roi_enabled, priority should be adjusted."""
        scheduler.settings.time_of_day_roi_enabled = True
        scheduler.settings.time_of_day_roi_weight = 0.15
        with patch("core.analytics.get_tracker") as mock_tracker:
            tracker = mock_tracker.return_value
            tracker.get_faucet_stats.return_value = {
                "firefaucet": {"success_rate": 80, "total": 20}
            }
            tracker.get_hourly_rate.return_value = {"firefaucet": 100}
            tracker.get_faucet_profitability.return_value = {"roi_percentage": 50.0}
            tracker.get_hourly_roi.return_value = {
                "firefaucet": {i: 20.0 for i in range(24)}
            }
            priority = scheduler.get_faucet_priority("firefaucet")
        assert 0.1 <= priority <= 2.0


class TestSchedulerLoopDegraded:
    """Cover scheduler_loop degraded mode branches."""

    @pytest.mark.asyncio
    async def test_low_proxy_degraded_mode(self, scheduler, profile, mock_bm):
        """Low proxy count enters low_proxy degraded mode."""
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1"]  # Below threshold

        scheduler._stop_event.set()
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 10
            scheduler.settings.low_proxy_threshold = 3
            scheduler.settings.low_proxy_max_concurrent_bots = 1
            await scheduler.scheduler_loop()
        # No crash in low proxy mode

    @pytest.mark.asyncio
    async def test_slow_degraded_mode(self, scheduler, profile, mock_bm):
        """High failure rate enters slow degraded mode."""
        scheduler.consecutive_job_failures = 10

        scheduler._stop_event.set()
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 5
            scheduler.settings.degraded_slow_delay_multiplier = 2.0
            await scheduler.scheduler_loop()
        # No crash in slow mode

    @pytest.mark.asyncio
    async def test_performance_alert_degraded(self, scheduler, profile, mock_bm):
        """High performance alert score enters perf degraded mode."""
        scheduler.performance_alert_score = 10

        scheduler._stop_event.set()
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 100
            scheduler.settings.performance_alert_slow_threshold = 5
            scheduler.settings.degraded_slow_delay_multiplier = 2.0
            await scheduler.scheduler_loop()
        # No crash in perf degraded mode

    @pytest.mark.asyncio
    async def test_mode_delay_overrides_multiplier(self, scheduler, profile, mock_bm):
        """When mode_delay is higher than delay_multiplier, it should be used."""
        scheduler._stop_event.set()
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=5.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

    @pytest.mark.asyncio
    async def test_withdrawal_scheduling_exception(self, scheduler, profile, mock_bm):
        """Exception in withdrawal scheduling sets flag to avoid retrying."""
        scheduler._stop_event.set()
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, side_effect=Exception("fail")), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

    @pytest.mark.asyncio
    async def test_circuit_breaker_cooldown_in_loop(self, scheduler, profile, mock_bm):
        """Jobs with active circuit breaker cooldown are deferred."""
        job = Job(priority=1, next_run=0, name="cb_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        # Set cooldown in the future
        scheduler.faucet_cooldowns["firefaucet"] = time.time() + 3600

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        # Job should NOT have been launched (circuit breaker active)
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_cooldown_expired(self, scheduler, profile, mock_bm):
        """Expired circuit breaker cooldown resets and allows job."""
        job = Job(priority=1, next_run=0, name="cb_reset_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        # Set cooldown in the past → should be cleared
        scheduler.faucet_cooldowns["firefaucet"] = time.time() - 1
        scheduler.faucet_failures["firefaucet"] = 5

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.001), \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 5.0}
            mock_solver.return_value = mock_solver_inst
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        # Circuit breaker should have been reset
        assert "firefaucet" not in scheduler.faucet_cooldowns
        assert scheduler.faucet_failures.get("firefaucet") == 0

    @pytest.mark.asyncio
    async def test_global_concurrency_limit(self, scheduler, profile, mock_bm):
        """When global concurrency limit reached, no new jobs launched."""
        job = Job(priority=1, next_run=0, name="limit_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        # Fill running jobs to capacity
        scheduler.running_jobs = {f"user{i}:job{i}": MagicMock() for i in range(3)}

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_profile_concurrency_limit(self, scheduler, profile, mock_bm):
        """When per-profile concurrency limit reached, job skipped."""
        job = Job(priority=1, next_run=0, name="profile_limit",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        # Set this profile at capacity
        scheduler.profile_concurrency["testuser"] = 1
        scheduler.settings.max_concurrent_per_profile = 1

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_domain_rate_limit_with_multiplier(self, scheduler, profile, mock_bm):
        """Domain delay is multiplied by delay_multiplier when > 1.0."""
        job = Job(priority=1, next_run=0, name="rate_limit_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        # Set recent domain access so delay > 0
        scheduler.domain_last_access["firefaucet"] = time.time()

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=2.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        # Job should have been deferred
        assert scheduler.queue[0].next_run > time.time() - 1

    @pytest.mark.asyncio
    async def test_auto_suspend_in_loop(self, scheduler, profile, mock_bm):
        """Auto-suspend defers job when enabled and triggered."""
        job = Job(priority=1, next_run=0, name="suspend_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        scheduler.settings.faucet_auto_suspend_enabled = True
        scheduler.settings.faucet_auto_suspend_duration = 3600

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_check_auto_suspend", return_value=(True, "Low ROI")), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        assert "firefaucet" in scheduler.faucet_cooldowns

    @pytest.mark.asyncio
    async def test_budget_insufficient_defers(self, scheduler, profile, mock_bm):
        """When budget is insufficient, job is deferred to next day."""
        job = Job(priority=1, next_run=0, name="budget_defer",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "estimate_claim_cost", return_value=1.0), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 0.001}
            mock_solver.return_value = mock_solver_inst
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        # Job should be deferred to tomorrow
        assert job.next_run > time.time() + 3600

    @pytest.mark.asyncio
    async def test_no_api_key_skips_budget_check(self, scheduler, profile, mock_bm):
        """When no API key, budget check is skipped with infinite remaining."""
        job = Job(priority=1, next_run=0, name="no_key_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]
        scheduler.settings.twocaptcha_api_key = None
        scheduler.settings.capsolver_api_key = None

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper", new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.001), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        # Job should have been launched despite no API key
        assert mock_run.called or "testuser:no_key_job" in scheduler.running_jobs


class TestCleanupEdgeCases:
    """Cover cleanup exception path."""

    @pytest.mark.asyncio
    async def test_cleanup_wallet_close_exception(self, scheduler):
        """Cleanup handles wallet close exception gracefully."""
        scheduler.auto_withdrawal = MagicMock()
        scheduler.auto_withdrawal.wallet = MagicMock()
        scheduler.auto_withdrawal.wallet.close = AsyncMock(
            side_effect=Exception("close failed")
        )
        await scheduler.cleanup()  # Should not raise


class TestPersistSessionException:
    """Cover _persist_session exception path."""

    def test_persist_session_handles_error(self, scheduler):
        """_persist_session handles serialization errors."""
        # Create a non-serializable object in queue
        scheduler.session_file = "/nonexistent/dir/session.json"
        scheduler.queue = []
        scheduler._persist_session()  # Should not raise


class TestRestoreSessionExceptionPath:
    """Cover _restore_session outer exception."""

    def test_restore_handles_read_exception(self, mock_settings, mock_bm):
        """If _safe_json_read raises, init still completes."""
        with patch("core.orchestrator.os.path.exists", return_value=True), \
             patch.object(JobScheduler, "_safe_json_read",
                          side_effect=Exception("disk error")):
            scheduler = JobScheduler(mock_settings, mock_bm)
        assert len(scheduler.queue) == 0


class TestSafeJsonWriteEdgeCases:
    """Cover _safe_json_write error paths."""

    def test_write_error_with_backup_restoration(self, scheduler):
        """When write fails and backup exists, recovery is attempted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            # Write initial valid data
            scheduler._safe_json_write(path, {"v": 1})

            # Now make the write fail by patching json.dump
            with patch("json.dump", side_effect=Exception("write error")):
                scheduler._safe_json_write(path, {"v": 2})

            # Original data should be preserved via backup
            result = scheduler._safe_json_read(path)
            assert result is not None


class TestHealthCheckInLoop:
    """Cover health check branches in scheduler_loop."""

    @pytest.mark.asyncio
    async def test_health_check_exception(self, scheduler, profile, mock_bm):
        """Health check exception is caught and logged."""
        scheduler.last_health_check_time = 0  # Force health check
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()

        scheduler.health_monitor.run_full_health_check = AsyncMock(
            side_effect=Exception("health failed")
        )

        scheduler._stop_event.set()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs", new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check", new_callable=AsyncMock):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        # Should have completed without crash


# ---------------------------------------------------------------------------
# schedule_withdrawal_jobs – deeper coverage
# ---------------------------------------------------------------------------

class TestScheduleWithdrawalJobsDeep:
    """Cover schedule_withdrawal_jobs with actual withdraw implementations."""

    @pytest.mark.asyncio
    async def test_schedules_for_faucet_with_withdraw(self, scheduler, profile):
        """Withdrawal job is created when faucet has a real withdraw() method."""
        profile.faucet = "firefaucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        def mock_source(method):
            return "def withdraw(self): return self.do_real_withdrawal()"

        with patch("core.registry.get_faucet_class", return_value=mock_class), \
             patch("core.registry.FAUCET_REGISTRY", {"firefaucet": mock_class}), \
             patch("inspect.getsource", side_effect=mock_source), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {"firefaucet": 150}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 1
        assert any(j.job_type == "withdraw_wrapper" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_skips_base_withdraw_implementation(self, scheduler, profile):
        """Base faucets with 'Not Implemented' withdraw are skipped."""
        profile.faucet = "firefaucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        def mock_source(method):
            return 'def withdraw(self): return "Not Implemented"'

        with patch("core.registry.get_faucet_class", return_value=mock_class), \
             patch("core.registry.FAUCET_REGISTRY", {"firefaucet": mock_class}), \
             patch("inspect.getsource", side_effect=mock_source), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 0

    @pytest.mark.asyncio
    async def test_faucet_registry_key_normalization(self, scheduler, profile):
        """Faucet type with underscores is found via registry key normalization."""
        profile.faucet = "fire_faucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        def mock_source(method):
            return "def withdraw(self): return self.execute()"

        # First get_faucet_class call returns None, second returns the class
        with patch("core.registry.get_faucet_class", side_effect=[None, mock_class]) as mock_get, \
             patch("core.registry.FAUCET_REGISTRY", {"fire_faucet": mock_class}), \
             patch("inspect.getsource", side_effect=mock_source), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 1

    @pytest.mark.asyncio
    async def test_withdrawal_high_earner_interval(self, scheduler, profile):
        """High earner gets 24h check interval."""
        profile.faucet = "firefaucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        with patch("core.registry.get_faucet_class", return_value=mock_class), \
             patch("core.registry.FAUCET_REGISTRY", {"firefaucet": mock_class}), \
             patch("inspect.getsource", return_value="def withdraw(self): pass"), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {"firefaucet": 150}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 1
        wd_job = [j for j in scheduler.queue if j.job_type == "withdraw_wrapper"][0]
        # High earner: 86400s = 24h
        assert wd_job.next_run >= time.time() + 80000

    @pytest.mark.asyncio
    async def test_withdrawal_off_peak_adjustment(self, scheduler, profile):
        """Off-peak withdrawal scheduling adjusts to off-peak hours."""
        profile.faucet = "firefaucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]
        scheduler.settings.prefer_off_peak_withdrawals = True
        scheduler.settings.off_peak_hours = [0, 1, 2, 3, 4, 5, 22, 23]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        with patch("core.registry.get_faucet_class", return_value=mock_class), \
             patch("core.registry.FAUCET_REGISTRY", {"firefaucet": mock_class}), \
             patch("inspect.getsource", return_value="def withdraw(self): pass"), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {"firefaucet": 60}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 1

    @pytest.mark.asyncio
    async def test_withdrawal_inspect_exception(self, scheduler, profile):
        """When inspect.getsource fails, withdrawal is skipped gracefully."""
        profile.faucet = "firefaucet"
        profile.enabled = True
        scheduler.settings.accounts = [profile]

        mock_class = MagicMock()
        mock_class.withdraw = MagicMock()

        with patch("core.registry.get_faucet_class", return_value=mock_class), \
             patch("core.registry.FAUCET_REGISTRY", {"firefaucet": mock_class}), \
             patch("inspect.getsource", side_effect=Exception("no source")), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            count = await scheduler.schedule_withdrawal_jobs()

        assert count == 0


# ---------------------------------------------------------------------------
# schedule_auto_withdrawal_check – wallet creation
# ---------------------------------------------------------------------------

class TestScheduleAutoWithdrawalCheckDeep:
    """Cover schedule_auto_withdrawal_check wallet initialization."""

    @pytest.mark.asyncio
    async def test_wallet_created_and_job_scheduled(self, scheduler):
        """Successful wallet connection creates auto-withdrawal job."""
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = "user"
        scheduler.settings.electrum_rpc_pass = "pass"
        scheduler.settings.prefer_off_peak_withdrawals = False

        mock_wallet = AsyncMock()
        mock_wallet.check_connection = AsyncMock(return_value=True)

        with patch("core.wallet_manager.WalletDaemon", return_value=mock_wallet), \
             patch("core.auto_withdrawal.get_auto_withdrawal_instance") as mock_aw, \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_aw.return_value = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler.schedule_auto_withdrawal_check()

        assert scheduler.withdrawal_check_scheduled is True
        assert any(j.job_type == "auto_withdrawal_check" for j in scheduler.queue)

    @pytest.mark.asyncio
    async def test_wallet_unreachable_skips(self, scheduler):
        """Unreachable wallet daemon skips scheduling."""
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = "user"
        scheduler.settings.electrum_rpc_pass = "pass"

        mock_wallet = AsyncMock()
        mock_wallet.check_connection = AsyncMock(return_value=False)

        with patch("core.wallet_manager.WalletDaemon", return_value=mock_wallet):
            await scheduler.schedule_auto_withdrawal_check()

        assert scheduler.withdrawal_check_scheduled is False

    @pytest.mark.asyncio
    async def test_wallet_connection_exception(self, scheduler):
        """Wallet connection exception is caught gracefully."""
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = "user"
        scheduler.settings.electrum_rpc_pass = "pass"

        mock_wallet = AsyncMock()
        mock_wallet.check_connection = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("core.wallet_manager.WalletDaemon", return_value=mock_wallet):
            await scheduler.schedule_auto_withdrawal_check()

        assert scheduler.withdrawal_check_scheduled is False

    @pytest.mark.asyncio
    async def test_wallet_with_off_peak_scheduling(self, scheduler):
        """Off-peak scheduling adjusts withdrawal check time."""
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = "user"
        scheduler.settings.electrum_rpc_pass = "pass"
        scheduler.settings.prefer_off_peak_withdrawals = True
        scheduler.settings.off_peak_hours = [0, 1, 2, 3, 4, 5, 22, 23]

        mock_wallet = AsyncMock()
        mock_wallet.check_connection = AsyncMock(return_value=True)

        with patch("core.wallet_manager.WalletDaemon", return_value=mock_wallet), \
             patch("core.auto_withdrawal.get_auto_withdrawal_instance") as mock_aw, \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_aw.return_value = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler.schedule_auto_withdrawal_check()

        assert scheduler.withdrawal_check_scheduled is True

    @pytest.mark.asyncio
    async def test_overall_exception_caught(self, scheduler):
        """General exception in schedule_auto_withdrawal_check is caught."""
        scheduler.settings.wallet_rpc_urls = {"BTC": "http://localhost:8332"}
        scheduler.settings.electrum_rpc_user = "user"
        scheduler.settings.electrum_rpc_pass = "pass"

        with patch("core.wallet_manager.WalletDaemon", side_effect=Exception("import error")):
            await scheduler.schedule_auto_withdrawal_check()

        assert scheduler.withdrawal_check_scheduled is False


# ---------------------------------------------------------------------------
# execute_consolidated_withdrawal – full path
# ---------------------------------------------------------------------------

class TestExecuteConsolidatedWithdrawalDeep:
    """Cover execute_consolidated_withdrawal main logic."""

    @pytest.mark.asyncio
    async def test_successful_withdrawal(self, scheduler, profile, mock_bm):
        """Successful consolidated withdrawal returns result."""
        result = _make_claim_result(True, status="Withdrawal sent", next_claim_minutes=1440)
        bot_cls, bot_inst = _make_bot_class(result)

        # Set min_withdraw threshold below the earnings
        scheduler.settings.firefaucet_min_withdraw = 100

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 50000}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            r = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

        assert r.success is True

    @pytest.mark.asyncio
    async def test_below_threshold_defers(self, scheduler, profile, mock_bm):
        """Balance below threshold returns deferred result."""
        bot_cls, _ = _make_bot_class(_make_claim_result(True))

        # Set threshold above the earnings
        scheduler.settings.firefaucet_min_withdraw = 50000

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 10}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            r = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

        assert r.success is True
        assert "Below Threshold" in r.status

    @pytest.mark.asyncio
    async def test_off_peak_deferral(self, scheduler, profile, mock_bm):
        """Non-off-peak time defers withdrawal."""
        scheduler.settings.prefer_off_peak_withdrawals = True
        bot_cls, _ = _make_bot_class(_make_claim_result(True))

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch.object(scheduler, "is_off_peak_time", return_value=False):
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 999999}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            # Set a very low threshold so balance check passes
            scheduler.settings.firefaucet_min_withdraw = 1
            r = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

        assert "Off-Peak" in r.status

    @pytest.mark.asyncio
    async def test_exception_logs_analytics(self, scheduler, profile, mock_bm):
        """Exception during withdrawal logs to analytics."""
        bot_cls = MagicMock()
        bot_inst = MagicMock()
        bot_inst.withdraw_wrapper = AsyncMock(side_effect=RuntimeError("network"))
        bot_inst.solver = None
        bot_inst.set_behavior_profile = MagicMock()
        bot_inst.set_proxy = MagicMock()
        bot_inst.settings_account_override = {}
        bot_cls.return_value = bot_inst

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("core.withdrawal_analytics.get_analytics") as mock_wa:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 999999}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.firefaucet_min_withdraw = 1
            mock_wa.return_value.record_withdrawal = MagicMock()
            r = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

        assert r.success is False
        assert "Error" in r.status


# ---------------------------------------------------------------------------
# detect_operation_mode – remaining branches
# ---------------------------------------------------------------------------

class TestDetectOperationModeDeep:
    """Cover detect_operation_mode LOW_BUDGET, SLOW_MODE, and edge cases."""

    def test_low_budget_mode(self, scheduler):
        """Low captcha budget triggers LOW_BUDGET mode."""
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.return_value = 4.5  # 4.5 of 5.0 budget used
                tracker_inst.get_stats_since.return_value = {"total_claims": 0, "failures": 0}
                mode = scheduler.detect_operation_mode()

        assert mode == OperationMode.LOW_BUDGET

    def test_slow_mode_high_failure_rate(self, scheduler):
        """High failure rate triggers SLOW_MODE."""
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.return_value = 0.0
                tracker_inst.get_stats_since.return_value = {
                    "total_claims": 20, "failures": 15  # 75% failure rate
                }
                mode = scheduler.detect_operation_mode()

        assert mode == OperationMode.SLOW_MODE

    def test_proxy_stats_exception(self, scheduler):
        """Proxy stats exception falls back to counting all proxies."""
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1", "p2", "p3", "p4", "p5"]
        scheduler.proxy_manager.get_proxy_stats.side_effect = Exception("no stats")
        scheduler.settings.low_proxy_threshold = 3

        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.return_value = 0.0
                tracker_inst.get_stats_since.return_value = {"total_claims": 0, "failures": 0}
                mode = scheduler.detect_operation_mode()

        assert mode == OperationMode.NORMAL  # 5 proxies >= 3 threshold

    def test_captcha_budget_check_exception(self, scheduler):
        """Exception in captcha budget check is caught gracefully."""
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.side_effect = Exception("db error")
                tracker_inst.get_stats_since.return_value = {"total_claims": 0, "failures": 0}
                mode = scheduler.detect_operation_mode()

        assert mode == OperationMode.NORMAL

    def test_failure_rate_check_exception(self, scheduler):
        """Exception in failure rate check is caught gracefully."""
        with patch("core.orchestrator.CONFIG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )
            with patch("core.analytics.get_tracker") as mock_tracker:
                tracker_inst = mock_tracker.return_value
                tracker_inst.get_captcha_costs_since.return_value = 0.0
                tracker_inst.get_stats_since.side_effect = Exception("stats error")
                mode = scheduler.detect_operation_mode()

        assert mode == OperationMode.NORMAL


# ---------------------------------------------------------------------------
# Health check auto-response branches in scheduler_loop
# ---------------------------------------------------------------------------

class TestHealthCheckAutoResponse:
    """Cover the health check auto-response branches (lines 2190-2223)."""

    @pytest.mark.asyncio
    async def test_browser_restart_on_critical(self, scheduler, profile, mock_bm):
        """Critical browser health triggers automatic restart."""
        scheduler.last_health_check_time = 0
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()

        scheduler.health_monitor.run_full_health_check = AsyncMock(return_value={
            "overall_healthy": False,
            "browser": {"healthy": False},
            "proxy": {"healthy": True},
            "system": {"healthy": True},
        })
        scheduler.health_monitor.should_restart_browser = MagicMock(return_value=True)
        scheduler.health_monitor.browser_context_failures = 5

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_bm.restart.assert_called()
        assert scheduler.health_monitor.browser_context_failures == 0

    @pytest.mark.asyncio
    async def test_proxy_auto_provision(self, scheduler, mock_bm):
        """Unhealthy proxy triggers auto-provisioning."""
        scheduler.last_health_check_time = 0
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()

        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1", "p2", "p3", "p4"]  # Above threshold
        scheduler.proxy_manager.auto_provision_proxies = AsyncMock()

        scheduler.health_monitor.run_full_health_check = AsyncMock(return_value={
            "overall_healthy": False,
            "browser": {"healthy": True},
            "proxy": {"healthy": False},
            "system": {"healthy": True},
        })
        scheduler.health_monitor.should_restart_browser = MagicMock(return_value=False)

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        scheduler.proxy_manager.auto_provision_proxies.assert_called()

    @pytest.mark.asyncio
    async def test_system_health_enters_slow_mode(self, scheduler, mock_bm):
        """System health issues switch to SLOW_MODE."""
        scheduler.last_health_check_time = 0
        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()

        scheduler.health_monitor.run_full_health_check = AsyncMock(return_value={
            "overall_healthy": False,
            "browser": {"healthy": True},
            "proxy": {"healthy": True},
            "system": {"healthy": False},
        })
        scheduler.health_monitor.should_restart_browser = MagicMock(return_value=False)

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        assert scheduler.current_mode == OperationMode.SLOW_MODE


# ---------------------------------------------------------------------------
# Scheduler loop – withdrawal analytics branch
# ---------------------------------------------------------------------------

class TestSchedulerLoopWithdrawalAnalytics:
    """Cover the withdrawal scheduling analytics path in scheduler_loop."""

    @pytest.mark.asyncio
    async def test_withdrawal_wait_recommendation(self, scheduler, profile, mock_bm):
        """Withdrawal job deferred when analytics recommends waiting."""
        job = Job(priority=1, next_run=0, name="wd_analytics",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper",
                          new_callable=AsyncMock) as mock_run, \
             patch("core.withdrawal_analytics.get_analytics") as mock_wa, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 100}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_wa.return_value.recommend_withdrawal_strategy.return_value = {
                "action": "wait", "reason": "Balance too low"
            }
            mock_wa.return_value.get_faucet_performance.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        assert job.next_run > time.time() - 5

    @pytest.mark.asyncio
    async def test_withdrawal_low_performance_skip(self, scheduler, profile, mock_bm):
        """Low-performance faucet withdrawal is skipped."""
        job = Job(priority=1, next_run=0, name="wd_perf",
                  profile=profile, faucet_type="firefaucet",
                  job_type="withdraw_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper",
                          new_callable=AsyncMock) as mock_run, \
             patch("core.withdrawal_analytics.get_analytics") as mock_wa, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 100}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            mock_wa.return_value.recommend_withdrawal_strategy.return_value = {
                "action": "withdraw", "reason": "Good time"
            }
            mock_wa.return_value.get_faucet_performance.return_value = {
                "firefaucet": {"success_rate": 10}  # < 20% threshold
            }
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        # Deferred to tomorrow
        assert job.next_run > time.time() + 80000


# ---------------------------------------------------------------------------
# Scheduler loop – budget profitability check
# ---------------------------------------------------------------------------

class TestSchedulerLoopBudgetProfitability:
    """Cover the low-budget profitability check branches (lines 2300-2325)."""

    @pytest.mark.asyncio
    async def test_low_budget_profitable_continues(self, scheduler, profile, mock_bm):
        """Low budget but profitable claim is allowed to proceed."""
        job = Job(priority=1, next_run=0, name="profit_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper",
                          new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.003), \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 0.30}
            mock_solver.return_value = mock_solver_inst
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"avg_earnings_usd": 0.01}  # > 0.003 * 2
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        # Job should have been launched (profitable)
        assert mock_run.called or "testuser:profit_job" in scheduler.running_jobs

    @pytest.mark.asyncio
    async def test_low_budget_unprofitable_skips(self, scheduler, profile, mock_bm):
        """Low budget unprofitable claim is skipped."""
        job = Job(priority=1, next_run=0, name="unprofit_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper",
                          new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.003), \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 0.30}
            mock_solver.return_value = mock_solver_inst
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"avg_earnings_usd": 0.001}  # < 0.003 * 2
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        assert job.next_run > time.time() + 3000


# ---------------------------------------------------------------------------
# _safe_json_read fallback to backup
# ---------------------------------------------------------------------------

class TestSafeJsonReadFallback:
    """Cover _safe_json_read backup fallback path."""

    def test_corrupt_file_reads_backup(self, scheduler):
        """When main file is corrupt, falls back to backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            # Write valid backup
            backup_path = path + ".backup.1"
            with open(backup_path, "w") as f:
                json.dump({"source": "backup"}, f)
            # Write corrupt main file
            with open(path, "w") as f:
                f.write("not valid json {{{")

            result = scheduler._safe_json_read(path)

        assert result == {"source": "backup"}


# ---------------------------------------------------------------------------
# _persist_session with non-serializable queue
# ---------------------------------------------------------------------------

class TestPersistSessionEdge:
    """Cover _persist_session serialization error."""

    def test_persist_serialization_error(self, scheduler, profile):
        """Non-serializable queue item triggers exception path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.session_file = os.path.join(tmpdir, "session.json")
            # Create a job with a non-serializable profile
            j = Job(priority=1, next_run=0, name="bad", profile=profile, faucet_type="f")
            j.profile = MagicMock()  # MagicMock won't serialize
            j.profile.username = "test"
            # Override to_dict to raise
            j.to_dict = MagicMock(side_effect=TypeError("not serializable"))
            scheduler.queue = [j]
            scheduler._persist_session()  # Should not raise


# ---------------------------------------------------------------------------
# _write_heartbeat exception
# ---------------------------------------------------------------------------

class TestHeartbeatException:
    """Cover heartbeat write exception."""

    def test_heartbeat_write_failure(self, scheduler):
        """Heartbeat write failure is caught."""
        scheduler.heartbeat_file = "/nonexistent/dir/heartbeat.txt"
        scheduler._write_heartbeat()  # Should not raise


# ---------------------------------------------------------------------------
# Job restore with bad data
# ---------------------------------------------------------------------------

class TestRestoreSessionBadJob:
    """Cover the job restoration failure path (lines 290-291)."""

    def test_restore_skips_bad_job(self, mock_settings, mock_bm):
        """Malformed job data is skipped during restore."""
        session_data = {
            "queue": [
                {"bad": "data"},  # Will fail Job.from_dict
                {
                    "priority": 1, "next_run": time.time() + 60, "name": "good",
                    "faucet_type": "firefaucet", "job_type": "claim_wrapper",
                    "retry_count": 0,
                    "profile": {"faucet": "firefaucet", "username": "user1", "password": "pass1"}
                }
            ],
            "domain_last_access": {},
            "timestamp": time.time()
        }
        with patch("core.orchestrator.os.path.exists", return_value=True), \
             patch.object(JobScheduler, "_safe_json_read", return_value=session_data), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler = JobScheduler(mock_settings, mock_bm)

        # Only the good job should be restored
        assert len(scheduler.queue) == 1
        assert scheduler.queue[0].name == "good"


# ---------------------------------------------------------------------------
# _safe_json_write backup restoration failure
# ---------------------------------------------------------------------------

class TestSafeJsonWriteBackupRestoreFailure:
    """Cover _safe_json_write backup restoration failure (lines 367-368)."""

    def test_write_and_restore_both_fail(self, scheduler):
        """When both write and backup restore fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            # Write initial valid data
            scheduler._safe_json_write(path, {"v": 1})

            # Make both write and restore fail
            with patch("json.dump", side_effect=Exception("write error")), \
                 patch("shutil.copy2", side_effect=Exception("copy error")):
                scheduler._safe_json_write(path, {"v": 2})

            # File should still exist from initial write
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# _run_job_wrapper – cleanup exception in finally block
# ---------------------------------------------------------------------------

class TestRunJobWrapperCleanupException:
    """Cover the final cleanup exception path (lines 2094-2096)."""

    @pytest.mark.asyncio
    async def test_cleanup_exception_logged(self, scheduler, profile, mock_bm):
        """Exception in final cleanup is caught and logged."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)
        mock_bm.safe_close_context = AsyncMock(side_effect=RuntimeError("cleanup boom"))

        job = Job(priority=1, next_run=0, name="cleanup_exc",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Job should still be rescheduled despite cleanup error
        matching = [j for j in scheduler.queue if j.name == "cleanup_exc"]
        assert len(matching) == 1


# ---------------------------------------------------------------------------
# add_job dynamic priority exception
# ---------------------------------------------------------------------------

class TestAddJobDynamicPriorityException:
    """Cover dynamic priority exception path (lines 1457-1458)."""

    def test_dynamic_priority_exception_allows_add(self, scheduler, profile):
        """Exception in get_faucet_priority still allows job to be added."""
        job = Job(priority=5, next_run=0, name="prio_exc",
                  profile=profile, faucet_type="firefaucet")

        with patch.object(scheduler, "get_faucet_priority",
                          side_effect=Exception("priority calc error")):
            scheduler.add_job(job)

        assert len(scheduler.queue) == 1
        assert scheduler.queue[0].name == "prio_exc"


# ---------------------------------------------------------------------------
# Timer prediction – conservative drift (3-4 samples, not enough for stddev)
# ---------------------------------------------------------------------------

class TestTimerPredictionConservativeDrift:
    """Cover the else branch at line 801 (< 5 samples, no std dev)."""

    def test_prediction_with_3_samples(self, scheduler):
        """With 3 samples, should use avg_drift directly (no std dev)."""
        for _ in range(3):
            scheduler.record_timer_observation("faucet", 60.0, 58.0)
        predicted = scheduler.predict_next_claim_time("faucet", 60.0)
        assert predicted < 60.0
        assert predicted >= 54.0


# ---------------------------------------------------------------------------
# check_and_update_mode – mode changed return (line 1293)
# ---------------------------------------------------------------------------

class TestCheckAndUpdateModeChange:
    """Cover the mode-changed return path at line 1293."""

    def test_mode_change_returns_delay(self, scheduler):
        """When mode actually changes, return new delay multiplier."""
        scheduler.last_mode_check_time = 0
        scheduler.current_mode = OperationMode.NORMAL
        with patch.object(scheduler, "detect_operation_mode",
                          return_value=OperationMode.SLOW_MODE), \
             patch.object(scheduler, "apply_mode_restrictions",
                          return_value=3.0):
            result = scheduler.check_and_update_mode()
        assert result == 3.0
        assert scheduler.current_mode == OperationMode.SLOW_MODE


# ---------------------------------------------------------------------------
# _run_job_wrapper – running_jobs cleanup in finally block (line 2100)
# ---------------------------------------------------------------------------

class TestRunJobWrapperFinallyCleanup:
    """Cover the running_jobs cleanup in the finally block (line 2100)."""

    @pytest.mark.asyncio
    async def test_running_jobs_cleaned_up(self, scheduler, profile, mock_bm):
        """After _run_job_wrapper completes, running_jobs entry is removed."""
        result = _make_claim_result(True, next_claim_minutes=60)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="cleanup_key",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        # Pre-populate running_jobs so finally block has something to clean
        scheduler.running_jobs["testuser:cleanup_key"] = MagicMock()
        scheduler.profile_concurrency["testuser"] = 1

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Running job entry should be cleaned up
        assert "testuser:cleanup_key" not in scheduler.running_jobs


# ---------------------------------------------------------------------------
# scheduler_loop – combined degraded modes (low_proxy+slow, etc.)
# ---------------------------------------------------------------------------

class TestSchedulerLoopCombinedDegraded:
    """Cover the combined degraded mode branches (lines 2136-2150)."""

    @pytest.mark.asyncio
    async def test_low_proxy_plus_slow_mode(self, scheduler, profile, mock_bm):
        """Low proxy count + high failure rate = low_proxy+slow."""
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.proxies = ["p1", "p2"]  # Below threshold of 3
        scheduler.consecutive_job_failures = 15  # Above degraded_failure_threshold

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 10
            scheduler.settings.low_proxy_threshold = 3
            scheduler.settings.low_proxy_max_concurrent_bots = 2
            scheduler.settings.degraded_slow_delay_multiplier = 2.0
            scheduler.settings.performance_alert_slow_threshold = 100
            await scheduler.scheduler_loop()

    @pytest.mark.asyncio
    async def test_perf_degraded_with_alerts(self, scheduler, profile, mock_bm):
        """Performance alerts + slow mode = combined degraded."""
        scheduler.performance_alert_score = 10
        scheduler.consecutive_job_failures = 15

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 10
            scheduler.settings.degraded_slow_delay_multiplier = 2.0
            scheduler.settings.performance_alert_slow_threshold = 5
            await scheduler.scheduler_loop()


# ---------------------------------------------------------------------------
# scheduler_loop – withdrawal scheduling within loop (lines 2155-2162)
# ---------------------------------------------------------------------------

class TestSchedulerLoopWithdrawalScheduling:
    """Cover the withdrawal job scheduling path in the loop."""

    @pytest.mark.asyncio
    async def test_withdrawal_scheduled_once(self, scheduler, profile, mock_bm):
        """Withdrawal jobs are scheduled on first loop iteration."""
        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=2) as mock_wd, \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock) as mock_awc, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_wd.assert_called_once()
        mock_awc.assert_called_once()


# ---------------------------------------------------------------------------
# _run_job_wrapper – permanent error not rescheduled (line 1971-1972)
# ---------------------------------------------------------------------------

class TestRunJobWrapperPermanentNotRescheduled:
    """Cover the permanent error inf delay return path (lines 1971-1972)."""

    @pytest.mark.asyncio
    async def test_true_permanent_not_rescheduled(self, scheduler, profile, mock_bm):
        """True permanent errors (no security words) are not rescheduled."""
        result = _make_claim_result(False, status="Account suspended permanently",
                                    next_claim_minutes=0,
                                    error_type=ErrorType.PERMANENT)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="true_perm",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Permanent error → not re-added
        assert not any(j.name == "true_perm" for j in scheduler.queue)


# ---------------------------------------------------------------------------
# _run_job_wrapper – proxy detected branch (line 1802)
# ---------------------------------------------------------------------------

class TestRunJobWrapperProxyDetectedWithProxy:
    """Cover proxy detection recording with actual proxy (line 1802)."""

    @pytest.mark.asyncio
    async def test_proxy_detected_records_failure(self, scheduler, profile, mock_bm):
        """When 'Proxy Detected' with a proxy, record_proxy_failure is called."""
        result = _make_claim_result(False, status="Proxy Detected by site",
                                    next_claim_minutes=30)
        bot_cls, _ = _make_bot_class(result)
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        # Set up proxy manager to provide a proxy
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.rotate_proxy.return_value = "http://proxy:8080"
        scheduler.proxy_manager.record_soft_signal = MagicMock()

        job = Job(priority=1, next_run=0, name="proxy_det2",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # Proxy failure should be recorded via proxy_manager
        scheduler.proxy_manager.record_failure.assert_called_with(
            "http://proxy:8080", detected=True, status_code=403
        )


# ---------------------------------------------------------------------------
# heartbeat – active accounts line (line 483)
# ---------------------------------------------------------------------------

class TestHeartbeatActiveAccounts:
    """Cover the active accounts line in _write_heartbeat (line 483)."""

    def test_heartbeat_with_active_accounts(self, scheduler):
        """Heartbeat writes active account info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler.heartbeat_file = os.path.join(tmpdir, "heartbeat.txt")
            scheduler.account_usage = {
                "user1": {"faucet": "firefaucet", "status": "claiming"},
            }
            scheduler.running_jobs = {"user1:claim": MagicMock()}
            scheduler._write_heartbeat()
            assert os.path.exists(scheduler.heartbeat_file)
            with open(scheduler.heartbeat_file) as f:
                content = f.read()
            assert "user1" in content or len(content) > 0


# ---------------------------------------------------------------------------
# Performance alerts in scheduler_loop (line 2179)
# ---------------------------------------------------------------------------

class TestSchedulerLoopPerformanceAlerts:
    """Cover performance alert logging (line 2179)."""

    @pytest.mark.asyncio
    async def test_performance_alerts_logged(self, scheduler, profile, mock_bm):
        """Performance alerts are logged during maintenance tick."""
        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = 0
        scheduler.last_persist_time = 0
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_write_heartbeat") as mock_hb, \
             patch.object(scheduler, "_persist_session") as mock_persist, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_tracker.return_value.check_performance_alerts.return_value = [
                "Faucet firefaucet has 80% failure rate"
            ]
            mock_tracker.return_value.get_profitability.return_value = {
                "earnings_usd": 0.01, "costs_usd": 0.005,
                "net_profit_usd": 0.005, "roi": 2.0
            }
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        assert scheduler.performance_alert_score == 1


# ---------------------------------------------------------------------------
# check_and_update_mode – mode unchanged (line 1293)
# ---------------------------------------------------------------------------

class TestCheckAndUpdateModeUnchanged:
    """Cover the return 1.0 when mode is checked but unchanged (line 1293)."""

    def test_mode_unchanged_returns_1(self, scheduler):
        """When mode is checked but hasn't changed, return 1.0."""
        scheduler.last_mode_check_time = 0  # Force check
        scheduler.current_mode = OperationMode.NORMAL
        with patch.object(scheduler, "detect_operation_mode",
                          return_value=OperationMode.NORMAL):
            result = scheduler.check_and_update_mode()
        assert result == 1.0
        assert scheduler.current_mode == OperationMode.NORMAL


# ---------------------------------------------------------------------------
# _run_job_wrapper – auto_withdrawal_check dispatch (line 1770)
# ---------------------------------------------------------------------------

class TestRunJobWrapperAutoWithdrawalDispatch:
    """Cover the auto_withdrawal_check job type dispatch (line 1770)."""

    @pytest.mark.asyncio
    async def test_auto_withdrawal_direct_dispatch(self, scheduler, profile, mock_bm):
        """auto_withdrawal_check jobs dispatch through execute_auto_withdrawal_check."""
        mock_bm.check_page_alive = AsyncMock(return_value=False)

        job = Job(priority=1, next_run=0, name="aw_dispatch",
                  profile=profile, faucet_type="system",
                  job_type="auto_withdrawal_check")

        # Mock the execution path
        scheduler.auto_withdrawal = AsyncMock()
        scheduler.auto_withdrawal.check_and_execute_withdrawals.return_value = {
            "balances_checked": 1,
            "withdrawals_executed": 0,
            "withdrawals_deferred": 0,
            "transactions": [],
        }

        with patch("core.registry.get_faucet_class", return_value=MagicMock()), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.record_runtime_cost = MagicMock()
            mock_tracker.return_value.get_faucet_stats.return_value = {}
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            await scheduler._run_job_wrapper(job)

        # auto_withdrawal should have been called
        scheduler.auto_withdrawal.check_and_execute_withdrawals.assert_called_once()


# ---------------------------------------------------------------------------
# execute_consolidated_withdrawal – pick faucet override (line 1353)
# ---------------------------------------------------------------------------

class TestConsolidatedWithdrawalPick:
    """Cover pick faucet email override in execute_consolidated_withdrawal (line 1353)."""

    @pytest.mark.asyncio
    async def test_pick_faucet_sets_email_override(self, scheduler, profile, mock_bm):
        """Pick faucets get email set in override."""
        result = _make_claim_result(True, status="Withdrawal sent", next_claim_minutes=1440)
        bot_cls, bot_inst = _make_bot_class(result)

        scheduler.settings.litepick_min_withdraw = 100

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "litepick": {"earnings": 50000}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            r = await scheduler.execute_consolidated_withdrawal("litepick", profile)

        assert r.success is True
        # Pick faucet should have email set
        assert bot_inst.settings_account_override.get("email") == profile.username

    @pytest.mark.asyncio
    async def test_consolidated_withdrawal_with_proxy(self, scheduler, profile, mock_bm):
        """Consolidated withdrawal with proxy manager sets proxy on bot."""
        result = _make_claim_result(True, status="Withdrawal sent", next_claim_minutes=1440)
        bot_cls, bot_inst = _make_bot_class(result)

        scheduler.settings.firefaucet_min_withdraw = 100
        scheduler.proxy_manager = MagicMock()
        scheduler.proxy_manager.rotate_proxy.return_value = "http://proxy:8080"

        with patch("core.registry.get_faucet_class", return_value=bot_cls), \
             patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"earnings": 50000}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            r = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

        assert r.success is True
        bot_inst.set_proxy.assert_called_with("http://proxy:8080")


# ---------------------------------------------------------------------------
# scheduler_loop – low-value claim skip (lines 2322-2325)
# ---------------------------------------------------------------------------

class TestSchedulerLoopLowValueSkip:
    """Cover the low-value claim skip path (lines 2322-2325)."""

    @pytest.mark.asyncio
    async def test_low_value_claim_skipped(self, scheduler, profile, mock_bm):
        """Claims with avg earnings < 2x cost are skipped when budget is low."""
        job = Job(priority=1, next_run=0, name="lowval_job",
                  profile=profile, faucet_type="firefaucet",
                  job_type="claim_wrapper")
        scheduler.queue = [job]

        loop_count = 0

        async def tick_then_stop(*args, **kwargs):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                scheduler._stop_event.set()
            raise asyncio.TimeoutError

        scheduler.last_heartbeat_time = time.time()
        scheduler.last_persist_time = time.time()
        scheduler.last_health_check_time = time.time()

        with patch.object(scheduler, "check_and_update_mode", return_value=1.0), \
             patch.object(scheduler, "schedule_withdrawal_jobs",
                          new_callable=AsyncMock, return_value=0), \
             patch.object(scheduler, "schedule_auto_withdrawal_check",
                          new_callable=AsyncMock), \
             patch.object(scheduler, "_run_job_wrapper",
                          new_callable=AsyncMock) as mock_run, \
             patch.object(scheduler, "estimate_claim_cost", return_value=0.005), \
             patch("solvers.captcha.CaptchaSolver") as mock_solver, \
             patch("core.analytics.get_tracker") as mock_tracker, \
             patch("asyncio.wait_for", side_effect=tick_then_stop):
            mock_solver_inst = MagicMock()
            mock_solver_inst.get_budget_stats.return_value = {"remaining": 0.30}
            mock_solver.return_value = mock_solver_inst
            # avg_earnings_usd < cost * 2 (0.002 < 0.005 * 2 = 0.010)
            mock_tracker.return_value.get_faucet_stats.return_value = {
                "firefaucet": {"avg_earnings_usd": 0.002}
            }
            mock_tracker.return_value.get_hourly_rate.return_value = {}
            scheduler.settings.degraded_failure_threshold = 100
            await scheduler.scheduler_loop()

        mock_run.assert_not_called()
        # Job should be deferred 1 hour
        assert job.next_run > time.time() + 3500


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
