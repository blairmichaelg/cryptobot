import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
import core.azure_monitor as azure_monitor

class TestAzureMonitor:
    
    def test_import_failure_simulation(self):
        """Test that import failure is handled gracefully by simulating the except block (lines 23-24)."""
        # This test verifies that when azure monitor imports fail, the code handles it gracefully
        # We can't easily test the actual import failure in the same process, but we can verify
        # the fallback behavior by checking that functions still work when _azure_monitor_available is False
        
        # Save original state
        original_available = azure_monitor._azure_monitor_available
        original_tracer = azure_monitor._tracer
        
        try:
            # Simulate the import failure state
            azure_monitor._azure_monitor_available = False
            azure_monitor._tracer = None
            
            # Now test that the initialize function returns False when SDK is not available
            result = azure_monitor.initialize_azure_monitor("test_conn")
            assert result is False
            
            # And tracking functions should handle None tracer gracefully
            azure_monitor.track_claim("test", True, 1.0, "BTC")  # Should not crash
            azure_monitor.track_error("error", "message", "faucet")  # Should not crash
            azure_monitor.track_metric("metric", 1.0)  # Should not crash
            
        finally:
            # Restore original state
            azure_monitor._azure_monitor_available = original_available
            azure_monitor._tracer = original_tracer
    
    def test_initialize_azure_monitor_sdk_missing(self):
        """Test initialization when SDK is not installed (lines 40-42)."""
        with patch("core.azure_monitor._azure_monitor_available", False):
            assert azure_monitor.initialize_azure_monitor("test_conn") is False

    def test_initialize_azure_monitor_no_conn_str(self):
        """Test initialization with missing connection string (lines 46-48)."""
        with patch("core.azure_monitor._azure_monitor_available", True):
            with patch.dict(os.environ, {}, clear=True):
                assert azure_monitor.initialize_azure_monitor(None) is False

    def test_initialize_azure_monitor_success(self):
        """Test successful initialization (lines 50-54)."""
        with patch("core.azure_monitor._azure_monitor_available", True):
            with patch("core.azure_monitor.configure_azure_monitor", create=True) as mock_config:
                with patch("core.azure_monitor.trace", create=True) as mock_trace:
                    mock_tracer = MagicMock()
                    mock_trace.get_tracer.return_value = mock_tracer
                    
                    assert azure_monitor.initialize_azure_monitor("test_conn") is True
                    mock_config.assert_called_once_with(connection_string="test_conn")
                    assert azure_monitor._tracer == mock_tracer

    def test_initialize_azure_monitor_exception(self):
        """Test initialization failure due to exception (lines 55-57)."""
        with patch("core.azure_monitor._azure_monitor_available", True):
            with patch("core.azure_monitor.configure_azure_monitor", side_effect=Exception("Fail"), create=True):
                assert azure_monitor.initialize_azure_monitor("test_conn") is False

    def test_track_methods_no_tracer(self):
        """Test tracking methods when tracer is not initialized (lines 71, 98, 120)."""
        with patch("core.azure_monitor._tracer", None):
            # Should return immediately without error
            azure_monitor.track_claim("f", True)
            azure_monitor.track_error("e", "m")
            azure_monitor.track_metric("n", 1)

    def test_track_claim_success(self):
        """Test successful claim tracking (lines 73-83)."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        with patch("core.azure_monitor._tracer", mock_tracer):
            with patch("core.azure_monitor.Status", create=True), \
                 patch("core.azure_monitor.StatusCode", create=True):
                # 1. Success case
                azure_monitor.track_claim("f1", True, 10, "BTC")
                mock_span.set_attribute.assert_any_call("faucet.name", "f1")
                mock_span.set_attribute.assert_any_call("claim.success", True)
                
                # 2. Failure case (83)
                azure_monitor.track_claim("f1", False)
                mock_span.set_status.assert_called()

    def test_track_error(self):
        """Test error tracking (lines 100-105)."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        with patch("core.azure_monitor._tracer", mock_tracer):
            with patch("core.azure_monitor.Status", create=True), \
                 patch("core.azure_monitor.StatusCode", create=True):
                azure_monitor.track_error("proxy_fail", "timed out", "f1")
                mock_span.set_attribute.assert_any_call("error.type", "proxy_fail")
                mock_span.set_status.assert_called()

    def test_track_metric(self):
        """Test metric tracking (lines 122-128)."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        with patch("core.azure_monitor._tracer", mock_tracer):
            azure_monitor.track_metric("prio", 1.5, {"tag": "val"})
            mock_span.set_attribute.assert_any_call("metric.name", "prio")
            mock_span.set_attribute.assert_any_call("metric.tag", "val")

    def test_track_exception_handling(self):
        """Test exception handling in tracking methods (lines 85, 107, 130)."""
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.side_effect = Exception("Span error")
        
        with patch("core.azure_monitor._tracer", mock_tracer):
            # Should log debug but not crash
            azure_monitor.track_claim("f", True)
            azure_monitor.track_error("e", "m")
            azure_monitor.track_metric("n", 1)
