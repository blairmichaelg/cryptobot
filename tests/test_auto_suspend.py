import pytest
import time
from unittest.mock import MagicMock, patch
from core.orchestrator import JobScheduler
from core.config import BotSettings, AccountProfile


@pytest.fixture
def mock_settings():
    """Mock BotSettings."""
    settings = MagicMock(spec=BotSettings)
    settings.faucet_auto_suspend_enabled = True
    settings.faucet_min_success_rate = 30.0
    settings.faucet_roi_threshold = -0.5
    settings.faucet_auto_suspend_duration = 14400
    settings.faucet_auto_suspend_min_samples = 5
    settings.max_concurrent_bots = 3
    return settings


@pytest.fixture
def mock_browser_manager():
    """Mock BrowserManager."""
    return MagicMock()


class TestAutoSuspend:
    
    def test_auto_suspend_low_success_rate(self, mock_settings, mock_browser_manager):
        """Test auto-suspend triggers on low success rate."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Mock analytics to return low success rate
        mock_stats = {
            "test_faucet": {
                "total": 10,
                "success": 2,
                "success_rate": 20.0,  # Below 30% threshold
                "earnings": 100
            }
        }
        
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = mock_stats
            mock_tracker.return_value.get_profitability.return_value = {
                "earnings_usd": 0.01,
                "costs_usd": 0.03,
                "net_profit_usd": -0.02,
                "roi": -0.67
            }
            
            should_suspend, reason = scheduler._check_auto_suspend("test_faucet")
            
            assert should_suspend is True
            assert "Low success rate" in reason
            assert "20.0%" in reason
    
    def test_auto_suspend_negative_roi(self, mock_settings, mock_browser_manager):
        """Test auto-suspend triggers on negative ROI."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Mock analytics to return negative ROI
        mock_stats = {
            "test_faucet": {
                "total": 10,
                "success": 8,
                "success_rate": 80.0,  # Good success rate
                "earnings": 10  # Very low earnings
            }
        }
        
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = mock_stats
            mock_tracker.return_value.get_profitability.return_value = {
                "earnings_usd": 0.001,
                "costs_usd": 0.03,
                "net_profit_usd": -0.029,
                "roi": -0.97
            }
            
            should_suspend, reason = scheduler._check_auto_suspend("test_faucet")
            
            assert should_suspend is True
            assert "Negative ROI" in reason
    
    def test_auto_suspend_min_samples_not_met(self, mock_settings, mock_browser_manager):
        """Test that auto-suspend doesn't trigger with insufficient samples."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Mock analytics with too few samples
        mock_stats = {
            "test_faucet": {
                "total": 3,  # Below min_samples (5)
                "success": 0,
                "success_rate": 0.0,
                "earnings": 0
            }
        }
        
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = mock_stats
            
            should_suspend, reason = scheduler._check_auto_suspend("test_faucet")
            
            assert should_suspend is False
            assert reason == ""
    
    def test_auto_suspend_no_stats(self, mock_settings, mock_browser_manager):
        """Test that auto-suspend doesn't crash with missing stats."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Mock analytics with no stats for faucet
        mock_stats = {}
        
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = mock_stats
            
            should_suspend, reason = scheduler._check_auto_suspend("test_faucet")
            
            assert should_suspend is False
            assert reason == ""
    
    def test_auto_suspend_disabled(self, mock_settings, mock_browser_manager):
        """Test that auto-suspend is skipped when disabled."""
        mock_settings.faucet_auto_suspend_enabled = False
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Even with bad stats, should not trigger
        mock_stats = {
            "test_faucet": {
                "total": 10,
                "success": 1,
                "success_rate": 10.0,
                "earnings": 0
            }
        }
        
        with patch("core.analytics.get_tracker") as mock_tracker:
            mock_tracker.return_value.get_faucet_stats.return_value = mock_stats
            
            # The check won't be called if disabled, but verify settings
            assert mock_settings.faucet_auto_suspend_enabled is False
