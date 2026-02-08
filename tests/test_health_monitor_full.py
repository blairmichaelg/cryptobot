"""
Comprehensive tests for HealthMonitor, HealthStatus, and HealthCheckResult.

Fills coverage gaps not covered by tests/test_health_monitor.py, including:
- HealthStatus enum completeness
- HealthCheckResult edge-case serialization
- _run_command timeout and exception paths
- check_heartbeat fresh/stale/missing/error
- check_disk_usage and check_memory_usage failure paths
- check_service_logs parsing
- perform_health_check combined alert scenarios
- send_webhook_notification / send_azure_metrics / send_email_notification
- restart_service_with_backoff edge cases
- run_check orchestration (alerts, auto-restart, backoff reset)
- run_daemon loop with KeyboardInterrupt / exception
- _load_restart_state / _save_restart_state edge cases
- Async methods: browser health, proxy health, faucet health, system health,
  full health check, send_health_alert (deduplication, webhook)
- record_faucet_attempt and history trimming
- should_restart_browser threshold logic
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from core.health_monitor import HealthMonitor, HealthStatus, HealthCheckResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monitor(tmpdir, **kwargs):
    """Create a HealthMonitor whose files live inside *tmpdir*."""
    defaults = {
        "log_file": str(Path(tmpdir) / "vm_health.log"),
        "enable_azure": False,
    }
    defaults.update(kwargs)
    return HealthMonitor(**defaults)


@pytest.fixture()
def tmpdir():
    """Yield a fresh temporary directory and clean it up afterwards.

    Uses tempfile.mkdtemp instead of tmp_path to avoid Windows
    PermissionError issues with pytest's tmp_path fixture.
    """
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def monitor(tmpdir):
    """Convenience fixture: a HealthMonitor pointing at *tmpdir*."""
    return _make_monitor(tmpdir)


# ===================================================================
# 1. HealthStatus enum
# ===================================================================

class TestHealthStatusEnum:
    def test_healthy_value(self):
        assert HealthStatus.HEALTHY.value == "HEALTHY"

    def test_warning_value(self):
        assert HealthStatus.WARNING.value == "WARNING"

    def test_critical_value(self):
        assert HealthStatus.CRITICAL.value == "CRITICAL"

    def test_unknown_value(self):
        assert HealthStatus.UNKNOWN.value == "UNKNOWN"

    def test_enum_members_count(self):
        assert len(HealthStatus) == 4

    def test_enum_iteration(self):
        names = {s.name for s in HealthStatus}
        assert names == {"HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"}


# ===================================================================
# 2. HealthCheckResult dataclass
# ===================================================================

class TestHealthCheckResult:
    def _make_result(self, **overrides):
        defaults = dict(
            timestamp="2026-02-08T10:00:00",
            status=HealthStatus.HEALTHY,
            service_active=True,
            service_running=True,
            crash_count=0,
            disk_usage_percent=40,
            memory_usage_percent=55,
            heartbeat_age_seconds=10,
            alerts=[],
            metrics={"disk_usage": 40},
        )
        defaults.update(overrides)
        return HealthCheckResult(**defaults)

    def test_to_dict_status_string(self):
        r = self._make_result(status=HealthStatus.WARNING)
        d = r.to_dict()
        assert d["status"] == "WARNING"

    def test_to_dict_critical_status_string(self):
        r = self._make_result(status=HealthStatus.CRITICAL)
        assert r.to_dict()["status"] == "CRITICAL"

    def test_to_dict_unknown_status_string(self):
        r = self._make_result(status=HealthStatus.UNKNOWN)
        assert r.to_dict()["status"] == "UNKNOWN"

    def test_to_dict_preserves_alerts(self):
        r = self._make_result(alerts=["alert1", "alert2"])
        d = r.to_dict()
        assert d["alerts"] == ["alert1", "alert2"]

    def test_to_dict_json_serializable(self):
        r = self._make_result(
            status=HealthStatus.CRITICAL,
            alerts=["disk full"],
            metrics={"disk_usage": 99, "memory_usage": 88},
        )
        serialized = json.dumps(r.to_dict())
        parsed = json.loads(serialized)
        assert parsed["status"] == "CRITICAL"
        assert parsed["disk_usage_percent"] == 99

    def test_to_dict_contains_all_fields(self):
        r = self._make_result()
        d = r.to_dict()
        expected_keys = {
            "timestamp", "status", "service_active", "service_running",
            "crash_count", "disk_usage_percent", "memory_usage_percent",
            "heartbeat_age_seconds", "alerts", "metrics",
        }
        assert expected_keys == set(d.keys())


# ===================================================================
# 3. HealthMonitor.__init__ variants
# ===================================================================

class TestHealthMonitorInit:
    def test_default_log_file_when_none(self, tmpdir):
        """When no log_file is given, the default is logs/vm_health.log."""
        m = HealthMonitor(enable_azure=False)
        assert m.log_file.name == "vm_health.log"

    def test_custom_log_file(self, tmpdir):
        log = str(Path(tmpdir) / "custom.log")
        m = _make_monitor(tmpdir, log_file=log)
        assert str(m.log_file) == log

    def test_webhook_url_from_param(self, tmpdir):
        m = _make_monitor(tmpdir, alert_webhook_url="https://hooks.example.com/x")
        assert m.alert_webhook_url == "https://hooks.example.com/x"

    def test_webhook_url_from_env(self, tmpdir):
        with patch.dict(os.environ, {"CRYPTOBOT_ALERT_WEBHOOK": "https://env.hook"}):
            m = _make_monitor(tmpdir)
            assert m.alert_webhook_url == "https://env.hook"

    def test_browser_and_proxy_managers_stored(self, tmpdir):
        bm = MagicMock(name="browser_mgr")
        pm = MagicMock(name="proxy_mgr")
        m = _make_monitor(tmpdir, browser_manager=bm, proxy_manager=pm)
        assert m.browser_manager is bm
        assert m.proxy_manager is pm

    def test_initial_tracking_state(self, monitor):
        assert monitor.browser_context_failures == 0
        assert monitor.faucet_attempt_history == {}
        assert monitor.last_browser_check == 0.0
        assert monitor.alert_cooldowns == {}


# ===================================================================
# 4. _run_command edge cases
# ===================================================================

class TestRunCommand:
    def test_timeout_returns_minus_one(self, monitor):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            code, out, err = monitor._run_command("sleep 999", timeout=1)
        assert code == -1
        assert err == "Command timed out"

    def test_generic_exception(self, monitor):
        with patch("subprocess.run", side_effect=OSError("no such file")):
            code, out, err = monitor._run_command("bogus")
        assert code == -1
        assert "no such file" in err

    def test_custom_timeout_forwarded(self, monitor):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            monitor._run_command("echo hi", timeout=99)
            _, kwargs = mock_run.call_args
            assert kwargs["timeout"] == 99


# ===================================================================
# 5. check_service_status with restart mentions
# ===================================================================

class TestCheckServiceStatus:
    def test_restart_count_parsed_from_output(self, monitor):
        with patch.object(monitor, "_run_command") as mc:
            mc.side_effect = [
                (0, "active", ""),
                (0, "Active: active (running)\nRestart=restart\nrestart triggered\nrestart", ""),
            ]
            _, _, crash_count = monitor.check_service_status()
        assert crash_count == 3

    def test_active_but_not_running(self, monitor):
        """Service is 'active' but detailed status says 'activating'."""
        with patch.object(monitor, "_run_command") as mc:
            mc.side_effect = [
                (0, "active", ""),
                (0, "activating (auto-restart)", ""),
            ]
            is_active, is_running, _ = monitor.check_service_status()
        assert is_active is True
        assert is_running is False


# ===================================================================
# 6. check_heartbeat
# ===================================================================

class TestCheckHeartbeat:
    def test_fresh_heartbeat(self, tmpdir):
        m = _make_monitor(tmpdir)
        # Create heartbeat file in the default location
        m.heartbeat_file = Path(tmpdir) / "heartbeat.txt"
        m.heartbeat_file.write_text("alive")
        age = m.check_heartbeat()
        assert 0 <= age <= 5

    def test_stale_heartbeat(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.heartbeat_file = Path(tmpdir) / "heartbeat.txt"
        m.heartbeat_file.write_text("alive")
        # Back-date the file's mtime by 600 seconds
        old_time = time.time() - 600
        os.utime(str(m.heartbeat_file), (old_time, old_time))
        age = m.check_heartbeat()
        assert age >= 590

    def test_missing_heartbeat(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.heartbeat_file = Path(tmpdir) / "no_such_heartbeat.txt"
        # Also make sure the fallback /tmp path doesn't interfere
        with patch("core.health_monitor.Path.exists", return_value=False):
            age = m.check_heartbeat()
        assert age == -1

    def test_heartbeat_stat_exception(self, tmpdir):
        m = _make_monitor(tmpdir)
        hb = Path(tmpdir) / "heartbeat.txt"
        hb.write_text("alive")
        m.heartbeat_file = hb
        with patch.object(Path, "stat", side_effect=PermissionError("denied")):
            # All paths raise, so we get -1
            with patch.object(Path, "exists", return_value=True):
                age = m.check_heartbeat()
        assert age == -1


# ===================================================================
# 7. check_disk_usage failure paths
# ===================================================================

class TestCheckDiskUsage:
    def test_command_failure_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(1, "", "err")):
            assert monitor.check_disk_usage() == 0

    def test_empty_stdout_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "", "")):
            assert monitor.check_disk_usage() == 0

    def test_non_integer_stdout_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "abc", "")):
            assert monitor.check_disk_usage() == 0

    def test_success_returns_integer(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "82", "")):
            assert monitor.check_disk_usage() == 82


# ===================================================================
# 8. check_memory_usage failure paths
# ===================================================================

class TestCheckMemoryUsage:
    def test_command_failure_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(1, "", "err")):
            assert monitor.check_memory_usage() == 0

    def test_empty_stdout_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "", "")):
            assert monitor.check_memory_usage() == 0

    def test_non_integer_stdout_returns_zero(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "xyz", "")):
            assert monitor.check_memory_usage() == 0


# ===================================================================
# 9. check_service_logs
# ===================================================================

class TestCheckServiceLogs:
    def test_returns_error_lines(self, monitor):
        log_output = "Jan 01 err1\nJan 02 err2"
        with patch.object(monitor, "_run_command", return_value=(0, log_output, "")):
            errors = monitor.check_service_logs()
        assert len(errors) == 2
        assert errors[0] == "Jan 01 err1"

    def test_no_entries_returns_empty(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "-- No entries --", "")):
            assert monitor.check_service_logs() == []

    def test_command_failure_returns_empty(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(1, "", "failed")):
            assert monitor.check_service_logs() == []

    def test_empty_stdout_returns_empty(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "", "")):
            assert monitor.check_service_logs() == []


# ===================================================================
# 10. perform_health_check combined scenarios
# ===================================================================

class TestPerformHealthCheckScenarios:
    def _patch_all(self, monitor, service=(True, True, 0), disk=50,
                   memory=60, heartbeat=30, logs=None):
        """Return a context manager that stubs every sub-check."""
        if logs is None:
            logs = []
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(monitor, "check_service_status", return_value=service))
        stack.enter_context(patch.object(monitor, "check_disk_usage", return_value=disk))
        stack.enter_context(patch.object(monitor, "check_memory_usage", return_value=memory))
        stack.enter_context(patch.object(monitor, "check_heartbeat", return_value=heartbeat))
        stack.enter_context(patch.object(monitor, "check_service_logs", return_value=logs))
        return stack

    def test_active_but_not_running(self, monitor):
        with self._patch_all(monitor, service=(True, False, 0)):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.CRITICAL
        assert any("not running" in a for a in result.alerts)

    def test_disk_warning_range(self, monitor):
        """Disk between 80-90 => WARNING, not CRITICAL."""
        with self._patch_all(monitor, disk=85):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.WARNING
        assert any("Disk usage high" in a for a in result.alerts)

    def test_high_memory_triggers_warning(self, monitor):
        with self._patch_all(monitor, memory=92):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.WARNING
        assert any("Memory usage high" in a for a in result.alerts)

    def test_stale_heartbeat_triggers_warning(self, monitor):
        with self._patch_all(monitor, heartbeat=600):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.WARNING
        assert any("stale" in a.lower() for a in result.alerts)

    def test_missing_heartbeat_triggers_warning(self, monitor):
        with self._patch_all(monitor, heartbeat=-1):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.WARNING
        assert any("No heartbeat" in a for a in result.alerts)

    def test_service_errors_trigger_warning(self, monitor):
        with self._patch_all(monitor, logs=["err1", "err2"]):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.WARNING
        assert any("recent errors" in a for a in result.alerts)

    def test_critical_takes_precedence_over_warning(self, monitor):
        """service down + high memory => CRITICAL wins."""
        with self._patch_all(monitor, service=(False, False, 0), memory=95):
            result = monitor.perform_health_check()
        assert result.status == HealthStatus.CRITICAL

    def test_metrics_dict_populated(self, monitor):
        with self._patch_all(monitor, disk=55, memory=40, heartbeat=20):
            result = monitor.perform_health_check()
        assert result.metrics["disk_usage"] == 55
        assert result.metrics["memory_usage"] == 40
        assert result.metrics["heartbeat_age"] == 20


# ===================================================================
# 11. send_webhook_notification
# ===================================================================

class TestSendWebhookNotification:
    def test_skipped_when_healthy(self, monitor):
        monitor.alert_webhook_url = "https://hooks.example.com/x"
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.HEALTHY,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=10,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=[], metrics={},
        )
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            monitor.send_webhook_notification(result)
            mock_req.post.assert_not_called()

    def test_sent_for_warning(self, monitor):
        monitor.alert_webhook_url = "https://hooks.example.com/x"
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=85,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=["Disk usage high: 85%"], metrics={},
        )
        mock_resp = MagicMock(status_code=200)
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            monitor.send_webhook_notification(result)
            mock_req.post.assert_called_once()
            payload = mock_req.post.call_args[1]["json"]
            assert "attachments" in payload

    def test_sent_for_critical(self, monitor):
        monitor.alert_webhook_url = "https://hooks.example.com/x"
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.CRITICAL,
            service_active=False, service_running=False,
            crash_count=0, disk_usage_percent=95,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=["Service is not active"], metrics={},
        )
        mock_resp = MagicMock(status_code=200)
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            monitor.send_webhook_notification(result)
            mock_req.post.assert_called_once()
            # Verify color is red for critical
            payload = mock_req.post.call_args[1]["json"]
            assert payload["attachments"][0]["color"] == "#FF0000"

    def test_no_webhook_url_noop(self, monitor):
        monitor.alert_webhook_url = None
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=85,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=["Disk high"], metrics={},
        )
        with patch.dict(os.environ, {}, clear=True), \
             patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            # Ensure ALERT_WEBHOOK_URL is not in env
            os.environ.pop("ALERT_WEBHOOK_URL", None)
            monitor.send_webhook_notification(result)
            mock_req.post.assert_not_called()

    def test_request_exception_handled(self, monitor):
        monitor.alert_webhook_url = "https://hooks.example.com/x"
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.CRITICAL,
            service_active=False, service_running=False,
            crash_count=0, disk_usage_percent=95,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=["Service down"], metrics={},
        )
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            mock_req.post.side_effect = ConnectionError("timeout")
            # Should not raise
            monitor.send_webhook_notification(result)

    def test_webhook_non_200_logged(self, monitor):
        monitor.alert_webhook_url = "https://hooks.example.com/x"
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=85,
            memory_usage_percent=10, heartbeat_age_seconds=5,
            alerts=["Disk high"], metrics={},
        )
        mock_resp = MagicMock(status_code=500)
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            monitor.send_webhook_notification(result)
            # Just verifying it doesn't raise


# ===================================================================
# 12. send_azure_metrics
# ===================================================================

class TestSendAzureMetrics:
    def test_skipped_when_disabled(self, monitor):
        monitor.azure_enabled = False
        result = MagicMock()
        with patch("core.health_monitor.AZURE_MONITOR_AVAILABLE", True):
            monitor.send_azure_metrics(result)
            # Nothing to assert beyond no exception

    def test_sends_metrics_when_enabled(self, monitor):
        monitor.azure_enabled = True
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.HEALTHY,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=50,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=[], metrics={},
        )
        with patch("core.health_monitor.track_metric") as mock_tm, \
             patch("core.health_monitor.track_error"):
            monitor.send_azure_metrics(result)
            assert mock_tm.call_count == 5  # disk, mem, heartbeat, crash, service_active

    def test_sends_errors_for_critical(self, monitor):
        monitor.azure_enabled = True
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.CRITICAL,
            service_active=False, service_running=False,
            crash_count=0, disk_usage_percent=95,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Service down", "Disk full"], metrics={},
        )
        with patch("core.health_monitor.track_metric"), \
             patch("core.health_monitor.track_error") as mock_te:
            monitor.send_azure_metrics(result)
            assert mock_te.call_count == 2

    def test_sends_errors_for_warning(self, monitor):
        monitor.azure_enabled = True
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=10, disk_usage_percent=50,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Crash loop detected"], metrics={},
        )
        with patch("core.health_monitor.track_metric"), \
             patch("core.health_monitor.track_error") as mock_te:
            monitor.send_azure_metrics(result)
            assert mock_te.call_count == 1

    def test_exception_handled(self, monitor):
        monitor.azure_enabled = True
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.HEALTHY,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=50,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=[], metrics={},
        )
        with patch("core.health_monitor.track_metric", side_effect=RuntimeError("boom")):
            # Should not raise
            monitor.send_azure_metrics(result)


# ===================================================================
# 13. send_email_notification
# ===================================================================

class TestSendEmailNotification:
    def test_skipped_when_healthy(self, monitor):
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.HEALTHY,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=50,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=[], metrics={},
        )
        with patch.dict(os.environ, {"ALERT_EMAIL": "a@b.com"}):
            monitor.send_email_notification(result)
            # no exception = pass

    def test_skipped_when_no_email(self, monitor):
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=10, disk_usage_percent=85,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Crash loop"], metrics={},
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ALERT_EMAIL", None)
            monitor.send_email_notification(result)

    def test_skipped_when_smtp_creds_missing(self, monitor):
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.WARNING,
            service_active=True, service_running=True,
            crash_count=10, disk_usage_percent=85,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Crash loop"], metrics={},
        )
        env = {"ALERT_EMAIL": "a@b.com"}
        # Remove SMTP_USER, SMTP_PASSWORD if present
        with patch.dict(os.environ, env, clear=True):
            monitor.send_email_notification(result)

    def test_smtp_send_exception_handled(self, monitor):
        result = HealthCheckResult(
            timestamp="t", status=HealthStatus.CRITICAL,
            service_active=False, service_running=False,
            crash_count=0, disk_usage_percent=95,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Service down"], metrics={},
        )
        env = {
            "ALERT_EMAIL": "a@b.com",
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=True), \
             patch("smtplib.SMTP", side_effect=ConnectionError("smtp down")):
            monitor.send_email_notification(result)


# ===================================================================
# 14. restart_service_with_backoff edge cases
# ===================================================================

class TestRestartServiceWithBackoff:
    def test_skipped_during_backoff_period(self, monitor):
        monitor.last_restart_time = datetime.now()
        monitor.backoff_seconds = 9999
        result = monitor.restart_service_with_backoff()
        assert result is False

    def test_restart_command_fails(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(1, "", "permission denied")):
            result = monitor.restart_service_with_backoff()
        assert result is False

    def test_service_not_running_after_restart(self, monitor):
        with patch.object(monitor, "_run_command", return_value=(0, "", "")), \
             patch.object(monitor, "check_service_status", return_value=(False, False, 0)), \
             patch("time.sleep"):
            result = monitor.restart_service_with_backoff()
        assert result is False

    def test_successful_restart_updates_state(self, tmpdir):
        m = _make_monitor(tmpdir)
        assert m.restart_count == 0
        with patch.object(m, "_run_command", return_value=(0, "", "")), \
             patch.object(m, "check_service_status", return_value=(True, True, 0)), \
             patch("time.sleep"):
            result = m.restart_service_with_backoff()
        assert result is True
        assert m.restart_count == 1
        assert m.backoff_seconds == 20  # 10 * 2

    def test_backoff_capped_at_max(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.backoff_seconds = 200
        m.last_restart_time = datetime.now() - timedelta(seconds=9999)
        with patch.object(m, "_run_command", return_value=(0, "", "")), \
             patch.object(m, "check_service_status", return_value=(True, True, 0)), \
             patch("time.sleep"):
            m.restart_service_with_backoff()
        assert m.backoff_seconds == min(200 * 2, m.MAX_BACKOFF_SECONDS)


# ===================================================================
# 15. run_check orchestration
# ===================================================================

class TestRunCheck:
    def _healthy_result(self):
        return HealthCheckResult(
            timestamp="t", status=HealthStatus.HEALTHY,
            service_active=True, service_running=True,
            crash_count=0, disk_usage_percent=50,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=[], metrics={},
        )

    def _critical_result(self):
        return HealthCheckResult(
            timestamp="t", status=HealthStatus.CRITICAL,
            service_active=False, service_running=False,
            crash_count=0, disk_usage_percent=95,
            memory_usage_percent=60, heartbeat_age_seconds=30,
            alerts=["Service down"], metrics={},
        )

    def test_alerts_dispatched_when_enabled(self, monitor):
        monitor.azure_enabled = True
        result = self._critical_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "send_azure_metrics") as mock_az, \
             patch.object(monitor, "send_webhook_notification") as mock_wh, \
             patch.object(monitor, "send_email_notification") as mock_em:
            monitor.run_check(send_alerts=True, auto_restart=False)
            mock_az.assert_called_once_with(result)
            mock_wh.assert_called_once_with(result)
            mock_em.assert_called_once_with(result)

    def test_alerts_not_dispatched_when_disabled(self, monitor):
        result = self._healthy_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "send_webhook_notification") as mock_wh:
            monitor.run_check(send_alerts=False)
            mock_wh.assert_not_called()

    def test_auto_restart_on_critical(self, monitor):
        result = self._critical_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "restart_service_with_backoff") as mock_restart:
            monitor.run_check(send_alerts=False, auto_restart=True)
            mock_restart.assert_called_once()

    def test_no_auto_restart_when_healthy(self, monitor):
        result = self._healthy_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "restart_service_with_backoff") as mock_restart:
            monitor.run_check(send_alerts=False, auto_restart=True)
            mock_restart.assert_not_called()

    def test_healthy_resets_backoff(self, monitor):
        monitor.restart_count = 3
        result = self._healthy_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "reset_backoff") as mock_reset:
            monitor.run_check()
            mock_reset.assert_called_once()

    def test_healthy_no_reset_when_count_zero(self, monitor):
        monitor.restart_count = 0
        result = self._healthy_result()
        with patch.object(monitor, "perform_health_check", return_value=result), \
             patch.object(monitor, "reset_backoff") as mock_reset:
            monitor.run_check()
            mock_reset.assert_not_called()


# ===================================================================
# 16. run_daemon
# ===================================================================

class TestRunDaemon:
    def test_keyboard_interrupt_stops_loop(self, monitor):
        with patch.object(monitor, "run_check", side_effect=KeyboardInterrupt):
            # Should exit cleanly, not raise
            monitor.run_daemon(check_interval=1)

    def test_exception_propagates(self, monitor):
        with patch.object(monitor, "run_check", side_effect=RuntimeError("fatal")):
            with pytest.raises(RuntimeError, match="fatal"):
                monitor.run_daemon(check_interval=1)

    def test_loop_respects_interval(self, monitor):
        call_count = 0

        def _side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt
            return MagicMock()

        with patch.object(monitor, "run_check", side_effect=_side_effect), \
             patch("time.sleep") as mock_sleep:
            monitor.run_daemon(check_interval=42)
            mock_sleep.assert_called_with(42)


# ===================================================================
# 17. _load_restart_state / _save_restart_state
# ===================================================================

class TestRestartStatePersistence:
    def test_load_from_file(self, tmpdir):
        state_file = Path(tmpdir) / "restart_backoff.json"
        state = {
            "restart_count": 3,
            "last_restart_time": "2026-01-01T12:00:00",
            "backoff_seconds": 80,
        }
        state_file.write_text(json.dumps(state))

        m = _make_monitor(tmpdir)
        m.restart_backoff_file = state_file
        m._load_restart_state()
        assert m.restart_count == 3
        assert m.backoff_seconds == 80
        assert m.last_restart_time is not None

    def test_load_missing_file(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = Path(tmpdir) / "nonexistent.json"
        m._load_restart_state()
        # Defaults remain unchanged
        assert m.restart_count == 0
        assert m.backoff_seconds == m.INITIAL_BACKOFF_SECONDS

    def test_load_corrupt_json(self, tmpdir):
        state_file = Path(tmpdir) / "corrupt.json"
        state_file.write_text("{invalid json!!!")
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = state_file
        m._load_restart_state()
        # Defaults remain, no crash
        assert m.restart_count == 0

    def test_save_creates_file(self, tmpdir):
        state_file = Path(tmpdir) / "state_out.json"
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = state_file
        m.restart_count = 5
        m.backoff_seconds = 160
        m.last_restart_time = datetime(2026, 1, 1, 12, 0, 0)
        m._save_restart_state()

        saved = json.loads(state_file.read_text())
        assert saved["restart_count"] == 5
        assert saved["backoff_seconds"] == 160
        assert "2026" in saved["last_restart_time"]

    def test_save_with_no_last_restart(self, tmpdir):
        state_file = Path(tmpdir) / "state_no_time.json"
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = state_file
        m.last_restart_time = None
        m._save_restart_state()

        saved = json.loads(state_file.read_text())
        assert saved["last_restart_time"] is None

    def test_save_handles_write_error(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = Path(tmpdir) / "no_dir" / "deep" / "file.json"
        # Parent directory doesn't exist, so write will fail -- should not raise
        m._save_restart_state()


# ===================================================================
# 18. Async: check_browser_health
# ===================================================================

class TestCheckBrowserHealth:
    def test_no_browser_manager(self, monitor):
        monitor.browser_manager = None
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert result["healthy"] is True
        assert "No browser manager" in result["message"]

    def test_no_browser_instance(self, monitor):
        bm = MagicMock()
        bm.browser = None
        monitor.browser_manager = bm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert result["healthy"] is False
        assert monitor.browser_context_failures == 1

    def test_browser_missing_browser_attr(self, monitor):
        bm = MagicMock(spec=[])  # no 'browser' attribute
        monitor.browser_manager = bm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert result["healthy"] is False

    def test_healthy_browser_resets_failures(self, monitor):
        monitor.browser_context_failures = 2
        bm = MagicMock()
        bm.browser.contexts = [MagicMock(), MagicMock()]
        monitor.browser_manager = bm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert result["healthy"] is True
        assert result["context_count"] == 2
        assert monitor.browser_context_failures == 0

    def test_browser_contexts_exception(self, monitor):
        bm = MagicMock()
        type(bm.browser).contexts = PropertyMock(side_effect=RuntimeError("crash"))
        monitor.browser_manager = bm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert monitor.browser_context_failures == 1
        # Still healthy when below threshold
        assert result["healthy"] is True

    def test_browser_exceeds_failure_threshold(self, monitor):
        monitor.browser_context_failures = monitor.MAX_BROWSER_CONTEXT_FAILURES - 1
        bm = MagicMock()
        type(bm.browser).contexts = PropertyMock(side_effect=RuntimeError("crash"))
        monitor.browser_manager = bm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_browser_health()
        )
        assert result["healthy"] is False


# ===================================================================
# 19. Async: check_proxy_health
# ===================================================================

class TestCheckProxyHealth:
    def test_no_proxy_manager(self, monitor):
        monitor.proxy_manager = None
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_proxy_health()
        )
        assert result["healthy"] is True

    def test_healthy_proxy_pool(self, monitor):
        pm = MagicMock()
        pm.all_proxies = ["p1", "p2", "p3", "p4", "p5"]
        pm.proxies = ["p1", "p2", "p3", "p4"]
        pm.dead_proxies = ["p5"]
        pm.proxy_cooldowns = {}
        pm.proxy_latency = {"p1": [100, 120], "p2": [90]}
        monitor.proxy_manager = pm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_proxy_health()
        )
        assert result["healthy"] is True
        assert result["healthy_count"] == 4
        assert result["dead"] == 1

    def test_unhealthy_proxy_pool(self, monitor):
        pm = MagicMock()
        pm.all_proxies = ["p1", "p2", "p3"]
        pm.proxies = ["p1"]  # below MIN_HEALTHY_PROXIES
        pm.dead_proxies = ["p2", "p3"]
        pm.proxy_cooldowns = {}
        pm.proxy_latency = {}
        monitor.proxy_manager = pm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_proxy_health()
        )
        assert result["healthy"] is False

    def test_proxy_check_exception(self, monitor):
        pm = MagicMock()
        type(pm).all_proxies = PropertyMock(side_effect=RuntimeError("oops"))
        monitor.proxy_manager = pm
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_proxy_health()
        )
        assert result["healthy"] is False


# ===================================================================
# 20. record_faucet_attempt and check_faucet_health
# ===================================================================

class TestFaucetAttemptTracking:
    def test_record_creates_history(self, monitor):
        monitor.record_faucet_attempt("freebitcoin", True)
        assert "freebitcoin" in monitor.faucet_attempt_history
        assert monitor.faucet_attempt_history["freebitcoin"] == [True]

    def test_record_appends(self, monitor):
        monitor.record_faucet_attempt("fb", True)
        monitor.record_faucet_attempt("fb", False)
        monitor.record_faucet_attempt("fb", True)
        assert monitor.faucet_attempt_history["fb"] == [True, False, True]

    def test_history_trimmed_at_max(self, monitor):
        for i in range(monitor.MAX_FAUCET_HISTORY + 5):
            monitor.record_faucet_attempt("fb", i % 2 == 0)
        assert len(monitor.faucet_attempt_history["fb"]) == monitor.MAX_FAUCET_HISTORY

    def test_faucet_health_empty(self, monitor):
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_faucet_health()
        )
        assert result == {}

    def test_faucet_health_high_success(self, monitor):
        for _ in range(8):
            monitor.record_faucet_attempt("good", True)
        for _ in range(2):
            monitor.record_faucet_attempt("good", False)
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_faucet_health()
        )
        assert result["good"]["healthy"] is True
        assert result["good"]["success_rate"] == 0.8

    def test_faucet_health_low_success(self, monitor):
        for _ in range(1):
            monitor.record_faucet_attempt("bad", True)
        for _ in range(9):
            monitor.record_faucet_attempt("bad", False)
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_faucet_health()
        )
        assert result["bad"]["healthy"] is False
        assert result["bad"]["success_rate"] == 0.1

    def test_faucet_health_few_attempts_healthy(self, monitor):
        """Fewer than 3 attempts => always healthy regardless of rate."""
        monitor.record_faucet_attempt("new", False)
        monitor.record_faucet_attempt("new", False)
        result = asyncio.get_event_loop().run_until_complete(
            monitor.check_faucet_health()
        )
        assert result["new"]["healthy"] is True


# ===================================================================
# 21. Async: check_system_health
# ===================================================================

class TestCheckSystemHealth:
    def test_psutil_not_available(self, monitor):
        with patch("core.health_monitor.PSUTIL_AVAILABLE", False):
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is True
        assert "psutil not available" in result["message"]

    def test_all_metrics_ok(self, monitor):
        mock_mem = MagicMock(percent=50.0)
        mock_disk = MagicMock(free=10 * 1024**3)  # 10 GB
        with patch("core.health_monitor.PSUTIL_AVAILABLE", True), \
             patch("core.health_monitor.psutil") as mock_ps:
            mock_ps.virtual_memory.return_value = mock_mem
            mock_ps.cpu_percent.return_value = 30.0
            mock_ps.disk_usage.return_value = mock_disk
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is True
        assert result["memory_percent"] == 50.0
        assert result["cpu_percent"] == 30.0

    def test_high_memory(self, monitor):
        mock_mem = MagicMock(percent=95.0)
        mock_disk = MagicMock(free=10 * 1024**3)
        with patch("core.health_monitor.PSUTIL_AVAILABLE", True), \
             patch("core.health_monitor.psutil") as mock_ps:
            mock_ps.virtual_memory.return_value = mock_mem
            mock_ps.cpu_percent.return_value = 30.0
            mock_ps.disk_usage.return_value = mock_disk
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is False
        assert "High memory" in result["message"]

    def test_high_cpu(self, monitor):
        mock_mem = MagicMock(percent=50.0)
        mock_disk = MagicMock(free=10 * 1024**3)
        with patch("core.health_monitor.PSUTIL_AVAILABLE", True), \
             patch("core.health_monitor.psutil") as mock_ps:
            mock_ps.virtual_memory.return_value = mock_mem
            mock_ps.cpu_percent.return_value = 98.0
            mock_ps.disk_usage.return_value = mock_disk
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is False
        assert "High CPU" in result["message"]

    def test_low_disk_space(self, monitor):
        mock_mem = MagicMock(percent=50.0)
        mock_disk = MagicMock(free=1 * 1024**3)  # 1 GB < MIN_DISK_GB (2)
        with patch("core.health_monitor.PSUTIL_AVAILABLE", True), \
             patch("core.health_monitor.psutil") as mock_ps:
            mock_ps.virtual_memory.return_value = mock_mem
            mock_ps.cpu_percent.return_value = 30.0
            mock_ps.disk_usage.return_value = mock_disk
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is False
        assert "Low disk" in result["message"]

    def test_exception_handled(self, monitor):
        with patch("core.health_monitor.PSUTIL_AVAILABLE", True), \
             patch("core.health_monitor.psutil") as mock_ps:
            mock_ps.virtual_memory.side_effect = RuntimeError("access denied")
            result = asyncio.get_event_loop().run_until_complete(
                monitor.check_system_health()
            )
        assert result["healthy"] is False


# ===================================================================
# 22. Async: send_health_alert (deduplication, webhook)
# ===================================================================

class TestSendHealthAlert:
    def test_alert_logged(self, monitor):
        asyncio.get_event_loop().run_until_complete(
            monitor.send_health_alert("WARNING", "test msg", "browser")
        )
        assert "browser:WARNING:test msg" in monitor.alert_cooldowns

    def test_duplicate_alert_suppressed(self, monitor):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            monitor.send_health_alert("WARNING", "dup", "browser")
        )
        # Record the cooldown timestamp
        first_ts = monitor.alert_cooldowns["browser:WARNING:dup"]

        # Call again -- should be suppressed (no second webhook call)
        monitor.alert_webhook_url = "https://hook.example.com"
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            loop.run_until_complete(
                monitor.send_health_alert("WARNING", "dup", "browser")
            )
            mock_req.post.assert_not_called()

    def test_alert_sent_after_cooldown(self, monitor):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            monitor.send_health_alert("CRITICAL", "issue", "system")
        )
        # Simulate cooldown expired
        key = "system:CRITICAL:issue"
        monitor.alert_cooldowns[key] = time.time() - monitor.ALERT_COOLDOWN_SECONDS - 1

        monitor.alert_webhook_url = "https://hook.example.com"
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            loop.run_until_complete(
                monitor.send_health_alert("CRITICAL", "issue", "system")
            )
            mock_req.post.assert_called_once()

    def test_webhook_failure_handled(self, monitor):
        monitor.alert_webhook_url = "https://hook.example.com"
        with patch("core.health_monitor.REQUESTS_AVAILABLE", True), \
             patch("core.health_monitor.requests") as mock_req:
            mock_req.post.side_effect = ConnectionError("fail")
            asyncio.get_event_loop().run_until_complete(
                monitor.send_health_alert("INFO", "test", "general")
            )
            # No exception raised


# ===================================================================
# 23. Async: run_full_health_check
# ===================================================================

class TestRunFullHealthCheck:
    def test_all_healthy(self, monitor):
        monitor.browser_manager = None
        monitor.proxy_manager = None
        with patch("core.health_monitor.PSUTIL_AVAILABLE", False):
            result = asyncio.get_event_loop().run_until_complete(
                monitor.run_full_health_check()
            )
        assert result["overall_healthy"] is True

    def test_degraded_proxy(self, monitor):
        monitor.browser_manager = None

        pm = MagicMock()
        pm.all_proxies = ["p1"]
        pm.proxies = []
        pm.dead_proxies = ["p1"]
        pm.proxy_cooldowns = {}
        pm.proxy_latency = {}
        monitor.proxy_manager = pm

        with patch("core.health_monitor.PSUTIL_AVAILABLE", False), \
             patch.object(monitor, "send_health_alert") as mock_alert:
            result = asyncio.get_event_loop().run_until_complete(
                monitor.run_full_health_check()
            )
        assert result["overall_healthy"] is False
        mock_alert.assert_called()

    def test_unhealthy_faucet_sends_warning(self, monitor):
        monitor.browser_manager = None
        monitor.proxy_manager = None
        # Record many failures
        for _ in range(5):
            monitor.record_faucet_attempt("bad_faucet", False)

        with patch("core.health_monitor.PSUTIL_AVAILABLE", False), \
             patch.object(monitor, "send_health_alert") as mock_alert:
            result = asyncio.get_event_loop().run_until_complete(
                monitor.run_full_health_check()
            )
        assert result["overall_healthy"] is False
        # Should have called send_health_alert for the faucet
        faucet_calls = [c for c in mock_alert.call_args_list
                        if "faucet_" in str(c)]
        assert len(faucet_calls) >= 1

    def test_browser_critical_alert(self, monitor):
        monitor.proxy_manager = None
        monitor.browser_context_failures = monitor.MAX_BROWSER_CONTEXT_FAILURES

        bm = MagicMock()
        bm.browser = None
        monitor.browser_manager = bm

        with patch("core.health_monitor.PSUTIL_AVAILABLE", False), \
             patch.object(monitor, "send_health_alert") as mock_alert:
            asyncio.get_event_loop().run_until_complete(
                monitor.run_full_health_check()
            )
        # Check that a CRITICAL browser alert was sent
        critical_calls = [
            c for c in mock_alert.call_args_list
            if c.args[0] == "CRITICAL" and c.args[2] == "browser"
        ]
        assert len(critical_calls) >= 1


# ===================================================================
# 24. should_restart_browser
# ===================================================================

class TestShouldRestartBrowser:
    def test_below_threshold(self, monitor):
        monitor.browser_context_failures = 0
        assert monitor.should_restart_browser() is False

    def test_at_threshold(self, monitor):
        monitor.browser_context_failures = monitor.MAX_BROWSER_CONTEXT_FAILURES
        assert monitor.should_restart_browser() is True

    def test_above_threshold(self, monitor):
        monitor.browser_context_failures = monitor.MAX_BROWSER_CONTEXT_FAILURES + 5
        assert monitor.should_restart_browser() is True


# ===================================================================
# 25. reset_backoff persistence
# ===================================================================

class TestResetBackoff:
    def test_reset_clears_all_fields(self, tmpdir):
        m = _make_monitor(tmpdir)
        m.restart_count = 7
        m.backoff_seconds = 320
        m.last_restart_time = datetime.now()
        m.reset_backoff()
        assert m.restart_count == 0
        assert m.backoff_seconds == m.INITIAL_BACKOFF_SECONDS
        assert m.last_restart_time is None

    def test_reset_saves_state_file(self, tmpdir):
        state_file = Path(tmpdir) / "backoff.json"
        m = _make_monitor(tmpdir)
        m.restart_backoff_file = state_file
        m.restart_count = 3
        m.reset_backoff()

        saved = json.loads(state_file.read_text())
        assert saved["restart_count"] == 0


# ===================================================================
# 26. Class constants
# ===================================================================

class TestClassConstants:
    def test_backoff_constants(self):
        assert HealthMonitor.INITIAL_BACKOFF_SECONDS == 10
        assert HealthMonitor.BACKOFF_MULTIPLIER == 2
        assert HealthMonitor.MAX_BACKOFF_SECONDS == 300

    def test_health_thresholds(self):
        assert HealthMonitor.MIN_HEALTHY_PROXIES == 3
        assert HealthMonitor.MAX_BROWSER_CONTEXT_FAILURES == 3
        assert HealthMonitor.MIN_FAUCET_SUCCESS_RATE == 0.3
        assert HealthMonitor.MAX_MEMORY_PERCENT == 90
        assert HealthMonitor.MAX_CPU_PERCENT == 95
        assert HealthMonitor.MIN_DISK_GB == 2
        assert HealthMonitor.MAX_FAUCET_HISTORY == 10
        assert HealthMonitor.ALERT_COOLDOWN_SECONDS == 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
