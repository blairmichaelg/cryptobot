"""
Tests for health monitoring system
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from core.health_monitor import HealthMonitor, HealthStatus, HealthCheckResult


@pytest.fixture
def mock_health_monitor(tmp_path):
    """Create a health monitor with mocked commands"""
    with patch('core.health_monitor.Path.home', return_value=tmp_path):
        monitor = HealthMonitor(log_file=str(tmp_path / "vm_health.log"), enable_azure=False)
        return monitor


def test_health_monitor_initialization(tmp_path):
    """Test health monitor initialization"""
    log_file = tmp_path / "vm_health.log"
    monitor = HealthMonitor(log_file=str(log_file), enable_azure=False)
    
    assert monitor.log_file == log_file
    assert log_file.parent.exists()
    assert monitor.azure_enabled == False


def test_run_command_success(mock_health_monitor):
    """Test successful command execution"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="active",
            stderr=""
        )
        
        exit_code, stdout, stderr = mock_health_monitor._run_command("test command")
        
        assert exit_code == 0
        assert stdout == "active"
        assert stderr == ""


def test_run_command_failure(mock_health_monitor):
    """Test failed command execution"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message"
        )
        
        exit_code, stdout, stderr = mock_health_monitor._run_command("test command")
        
        assert exit_code == 1
        assert stdout == ""
        assert stderr == "error message"


def test_check_service_status_active(mock_health_monitor):
    """Test service status check when service is active"""
    with patch.object(mock_health_monitor, '_run_command') as mock_cmd:
        # First call for is-active
        # Second call for detailed status
        mock_cmd.side_effect = [
            (0, "active", ""),
            (0, "active (running)", "")
        ]
        
        is_active, is_running, crash_count = mock_health_monitor.check_service_status()
        
        assert is_active == True
        assert is_running == True
        assert crash_count == 0


def test_check_service_status_inactive(mock_health_monitor):
    """Test service status check when service is inactive"""
    with patch.object(mock_health_monitor, '_run_command') as mock_cmd:
        mock_cmd.side_effect = [
            (1, "inactive", ""),
            (3, "inactive (dead)", "")
        ]
        
        is_active, is_running, crash_count = mock_health_monitor.check_service_status()
        
        assert is_active == False
        assert is_running == False


def test_check_disk_usage(mock_health_monitor):
    """Test disk usage check"""
    with patch.object(mock_health_monitor, '_run_command') as mock_cmd:
        mock_cmd.return_value = (0, "75", "")
        
        disk_usage = mock_health_monitor.check_disk_usage()
        
        assert disk_usage == 75


def test_check_memory_usage(mock_health_monitor):
    """Test memory usage check"""
    with patch.object(mock_health_monitor, '_run_command') as mock_cmd:
        mock_cmd.return_value = (0, "65", "")
        
        memory_usage = mock_health_monitor.check_memory_usage()
        
        assert memory_usage == 65


def test_perform_health_check_healthy(mock_health_monitor):
    """Test health check when everything is healthy"""
    with patch.object(mock_health_monitor, 'check_service_status', return_value=(True, True, 0)), \
         patch.object(mock_health_monitor, 'check_disk_usage', return_value=50), \
         patch.object(mock_health_monitor, 'check_memory_usage', return_value=60), \
         patch.object(mock_health_monitor, 'check_heartbeat', return_value=30), \
         patch.object(mock_health_monitor, 'check_service_logs', return_value=[]):
        
        result = mock_health_monitor.perform_health_check()
        
        assert result.status == HealthStatus.HEALTHY
        assert result.service_active == True
        assert result.service_running == True
        assert result.disk_usage_percent == 50
        assert result.memory_usage_percent == 60
        assert result.heartbeat_age_seconds == 30
        assert len(result.alerts) == 0


def test_perform_health_check_service_down(mock_health_monitor):
    """Test health check when service is down"""
    with patch.object(mock_health_monitor, 'check_service_status', return_value=(False, False, 0)), \
         patch.object(mock_health_monitor, 'check_disk_usage', return_value=50), \
         patch.object(mock_health_monitor, 'check_memory_usage', return_value=60), \
         patch.object(mock_health_monitor, 'check_heartbeat', return_value=30), \
         patch.object(mock_health_monitor, 'check_service_logs', return_value=[]):
        
        result = mock_health_monitor.perform_health_check()
        
        assert result.status == HealthStatus.CRITICAL
        assert result.service_active == False
        assert "Service is not active" in result.alerts


def test_perform_health_check_high_disk_usage(mock_health_monitor):
    """Test health check with high disk usage"""
    with patch.object(mock_health_monitor, 'check_service_status', return_value=(True, True, 0)), \
         patch.object(mock_health_monitor, 'check_disk_usage', return_value=95), \
         patch.object(mock_health_monitor, 'check_memory_usage', return_value=60), \
         patch.object(mock_health_monitor, 'check_heartbeat', return_value=30), \
         patch.object(mock_health_monitor, 'check_service_logs', return_value=[]):
        
        result = mock_health_monitor.perform_health_check()
        
        assert result.status == HealthStatus.CRITICAL
        assert result.disk_usage_percent == 95
        assert any("Disk usage critical" in alert for alert in result.alerts)


def test_perform_health_check_crash_loop(mock_health_monitor):
    """Test health check with crash loop detection"""
    with patch.object(mock_health_monitor, 'check_service_status', return_value=(True, True, 10)), \
         patch.object(mock_health_monitor, 'check_disk_usage', return_value=50), \
         patch.object(mock_health_monitor, 'check_memory_usage', return_value=60), \
         patch.object(mock_health_monitor, 'check_heartbeat', return_value=30), \
         patch.object(mock_health_monitor, 'check_service_logs', return_value=[]):
        
        result = mock_health_monitor.perform_health_check()
        
        assert result.status == HealthStatus.WARNING
        assert result.crash_count == 10
        assert any("crash loop" in alert.lower() for alert in result.alerts)


def test_restart_backoff_logic(tmp_path):
    """Test exponential backoff for restarts"""
    from datetime import datetime, timedelta
    
    monitor = HealthMonitor(log_file=str(tmp_path / "vm_health.log"), enable_azure=False)
    
    # Initial state
    assert monitor.restart_count == 0
    assert monitor.backoff_seconds == 10
    
    # Simulate restarts with time passing
    with patch.object(monitor, '_run_command', return_value=(0, "", "")), \
         patch.object(monitor, 'check_service_status', return_value=(True, True, 0)):
        
        # First restart
        monitor.restart_service_with_backoff()
        assert monitor.restart_count == 1
        assert monitor.backoff_seconds == 20
        
        # Move time forward to allow second restart
        monitor.last_restart_time = datetime.now() - timedelta(seconds=30)
        
        # Second restart
        monitor.restart_service_with_backoff()
        assert monitor.restart_count == 2
        assert monitor.backoff_seconds == 40
        
        # Move time forward to allow third restart
        monitor.last_restart_time = datetime.now() - timedelta(seconds=50)
        
        # Third restart
        monitor.restart_service_with_backoff()
        assert monitor.restart_count == 3
        assert monitor.backoff_seconds == 80


def test_reset_backoff(tmp_path):
    """Test backoff reset"""
    monitor = HealthMonitor(log_file=str(tmp_path / "vm_health.log"), enable_azure=False)
    
    # Set some backoff state
    monitor.restart_count = 5
    monitor.backoff_seconds = 160
    
    # Reset
    monitor.reset_backoff()
    
    assert monitor.restart_count == 0
    assert monitor.backoff_seconds == 10


def test_health_check_result_to_dict():
    """Test HealthCheckResult serialization"""
    result = HealthCheckResult(
        timestamp="2026-01-24T12:00:00",
        status=HealthStatus.HEALTHY,
        service_active=True,
        service_running=True,
        crash_count=0,
        disk_usage_percent=50,
        memory_usage_percent=60,
        heartbeat_age_seconds=30,
        alerts=[],
        metrics={'disk_usage': 50}
    )
    
    result_dict = result.to_dict()
    
    assert result_dict['status'] == 'HEALTHY'
    assert result_dict['service_active'] == True
    assert result_dict['disk_usage_percent'] == 50
    assert 'metrics' in result_dict


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
