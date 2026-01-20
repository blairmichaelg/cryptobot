"""
Tests for Profitability Monitor Script
"""

import pytest
import json
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from datetime import datetime

# Import the module to test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.profitability_monitor import (
    get_2captcha_balance,
    calculate_earnings,
    estimate_costs,
    calculate_roi,
    check_profitability,
    generate_alert,
    ROI_THRESHOLD
)
from core.analytics import EarningsTracker


class TestTwoCaptchaAPI:
    """Test 2Captcha API integration."""
    
    @pytest.mark.asyncio
    async def test_get_balance_success(self):
        """Test successful balance retrieval."""
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"status": 1, "request": "5.25"})
        
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            balance = await get_2captcha_balance("test_api_key")
            assert balance == 5.25
    
    @pytest.mark.asyncio
    async def test_get_balance_failure(self):
        """Test balance retrieval failure."""
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST"})
        
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            balance = await get_2captcha_balance("invalid_key")
            assert balance is None
    
    @pytest.mark.asyncio
    async def test_get_balance_exception(self):
        """Test balance retrieval with network error."""
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
        mock_session.__aexit__ = AsyncMock()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            balance = await get_2captcha_balance("test_key")
            assert balance is None


class TestEarningsCalculation:
    """Test earnings calculation."""
    
    def test_calculate_earnings_with_data(self, tmp_path):
        """Test earnings calculation with claim data."""
        storage_file = tmp_path / "test_analytics.json"
        tracker = EarningsTracker(storage_file=str(storage_file))
        
        # Add some claims (use non-test faucet names to avoid filtering)
        tracker.record_claim("firefaucet", True, 100.0, "BTC")
        tracker.record_claim("cointiply", True, 50.0, "LTC")
        tracker.record_claim("dutchy", False, 0.0, "DOGE")
        
        earnings = calculate_earnings(tracker, hours=24)
        
        assert "BTC" in earnings
        assert "LTC" in earnings
        assert earnings["BTC"] == 100.0
        assert earnings["LTC"] == 50.0
    
    def test_calculate_earnings_empty(self, tmp_path):
        """Test earnings calculation with no claims."""
        storage_file = tmp_path / "test_analytics.json"
        tracker = EarningsTracker(storage_file=str(storage_file))
        
        earnings = calculate_earnings(tracker, hours=24)
        
        assert earnings == {}


class TestCostEstimation:
    """Test cost estimation logic."""
    
    def test_estimate_costs_with_balance(self, tmp_path):
        """Test cost estimation with actual balance data."""
        storage_file = tmp_path / "test_analytics.json"
        tracker = EarningsTracker(storage_file=str(storage_file))
        
        # Add some claims (use non-test faucet names)
        tracker.record_claim("firefaucet", True, 100.0, "BTC")
        tracker.record_claim("cointiply", True, 50.0, "LTC")
        
        costs = estimate_costs(tracker, initial_balance=10.0, current_balance=9.5, hours=24)
        
        assert costs["captcha_cost"] == 0.5  # 10.0 - 9.5
        assert costs["proxy_cost"] == 0.002  # 2 claims * 0.001
        assert costs["total_cost"] == 0.502
    
    def test_estimate_costs_without_balance(self, tmp_path):
        """Test cost estimation without balance data."""
        storage_file = tmp_path / "test_analytics.json"
        tracker = EarningsTracker(storage_file=str(storage_file))
        
        # Add some claims (use non-test faucet names)
        tracker.record_claim("firefaucet", True, 100.0, "BTC")
        tracker.record_claim("cointiply", True, 50.0, "LTC")
        tracker.record_claim("dutchy", False, 0.0, "DOGE")
        
        costs = estimate_costs(tracker, initial_balance=None, current_balance=None, hours=24)
        
        assert costs["captcha_cost"] == pytest.approx(0.009)  # 3 claims * 0.003
        assert costs["proxy_cost"] == pytest.approx(0.003)   # 3 claims * 0.001
        assert costs["total_cost"] == pytest.approx(0.012)
    
    def test_estimate_costs_negative_balance_change(self, tmp_path):
        """Test cost estimation when balance increases (shouldn't happen)."""
        storage_file = tmp_path / "test_analytics.json"
        tracker = EarningsTracker(storage_file=str(storage_file))
        
        tracker.record_claim("firefaucet", True, 100.0, "BTC")
        
        # Balance increased (e.g., manual top-up)
        costs = estimate_costs(tracker, initial_balance=5.0, current_balance=10.0, hours=24)
        
        # Should default to 0 for captcha cost (max(0, 5.0 - 10.0))
        assert costs["captcha_cost"] == 0.0
        assert costs["proxy_cost"] == 0.001


class TestROICalculation:
    """Test ROI calculation."""
    
    def test_roi_positive(self):
        """Test ROI calculation with profit."""
        roi = calculate_roi(earnings=10.0, costs=5.0)
        assert roi == 100.0  # (10 - 5) / 5 * 100
    
    def test_roi_negative(self):
        """Test ROI calculation with loss."""
        roi = calculate_roi(earnings=5.0, costs=10.0)
        assert roi == -50.0  # (5 - 10) / 10 * 100
    
    def test_roi_breakeven(self):
        """Test ROI calculation at breakeven."""
        roi = calculate_roi(earnings=5.0, costs=5.0)
        assert roi == 0.0
    
    def test_roi_zero_costs(self):
        """Test ROI calculation with zero costs."""
        roi = calculate_roi(earnings=10.0, costs=0.0)
        assert roi == 100.0  # Edge case: returns 100% when there are earnings but no costs
    
    def test_roi_zero_everything(self):
        """Test ROI calculation with zero earnings and costs."""
        roi = calculate_roi(earnings=0.0, costs=0.0)
        assert roi == 0.0


class TestAlertGeneration:
    """Test alert generation logic."""
    
    def test_alert_below_threshold(self):
        """Test alert generation when ROI is below threshold."""
        result = {
            "roi_percentage": 30.0,  # Below 50% threshold
            "net_profit": -5.0,
            "earnings_usd": 10.0,
            "costs": {
                "total_cost": 15.0,
                "captcha_cost": 10.0,
                "proxy_cost": 5.0
            }
        }
        
        with patch('scripts.profitability_monitor.logger') as mock_logger:
            alert_triggered = generate_alert(result)
            assert alert_triggered is True
            # Verify warning was logged
            assert mock_logger.warning.called
    
    def test_no_alert_above_threshold(self):
        """Test no alert when ROI is above threshold."""
        result = {
            "roi_percentage": 75.0,  # Above 50% threshold
            "net_profit": 15.0,
            "earnings_usd": 35.0,
            "costs": {
                "total_cost": 20.0,
                "captcha_cost": 15.0,
                "proxy_cost": 5.0
            }
        }
        
        with patch('scripts.profitability_monitor.logger') as mock_logger:
            alert_triggered = generate_alert(result)
            assert alert_triggered is False
            # Verify info log was called (not warning)
            assert mock_logger.info.called
    
    def test_alert_at_threshold(self):
        """Test alert generation when ROI is exactly at threshold."""
        result = {
            "roi_percentage": ROI_THRESHOLD,  # Exactly at threshold
            "net_profit": 5.0,
            "earnings_usd": 15.0,
            "costs": {
                "total_cost": 10.0,
                "captcha_cost": 7.0,
                "proxy_cost": 3.0
            }
        }
        
        with patch('scripts.profitability_monitor.logger') as mock_logger:
            alert_triggered = generate_alert(result)
            # At threshold should not trigger (only below)
            assert alert_triggered is False


class TestProfitabilityCheck:
    """Test the main profitability check function."""
    
    @pytest.mark.asyncio
    async def test_check_profitability_with_api_key(self, tmp_path):
        """Test profitability check with 2Captcha API key."""
        storage_file = tmp_path / "test_analytics.json"
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.twocaptcha_api_key = "test_key"
        
        # Mock tracker
        mock_tracker = MagicMock(spec=EarningsTracker)
        mock_tracker.get_session_stats.return_value = {
            "total_claims": 10,
            "earnings_by_currency": {"BTC": 100.0, "LTC": 50.0}
        }
        
        with patch('scripts.profitability_monitor.BotSettings', return_value=mock_settings), \
             patch('scripts.profitability_monitor.EarningsTracker', return_value=mock_tracker), \
             patch('scripts.profitability_monitor.get_2captcha_balance', return_value=9.5), \
             patch('scripts.profitability_monitor.ANALYTICS_FILE', str(storage_file.parent / "analytics.json")), \
             patch('builtins.open', mock_open(read_data='{"initial_balance": 10.0}')):
            
            result = await check_profitability(hours=24)
            
            assert "roi_percentage" in result
            assert "net_profit" in result
            assert "earnings_usd" in result
            assert "costs" in result
            assert result["captcha_balance"] == 9.5
    
    @pytest.mark.asyncio
    async def test_check_profitability_without_api_key(self, tmp_path):
        """Test profitability check without 2Captcha API key."""
        storage_file = tmp_path / "test_analytics.json"
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.twocaptcha_api_key = None
        
        # Mock tracker
        mock_tracker = MagicMock(spec=EarningsTracker)
        mock_tracker.get_session_stats.return_value = {
            "total_claims": 5,
            "earnings_by_currency": {"BTC": 50.0}
        }
        
        with patch('scripts.profitability_monitor.BotSettings', return_value=mock_settings), \
             patch('scripts.profitability_monitor.EarningsTracker', return_value=mock_tracker), \
             patch('scripts.profitability_monitor.ANALYTICS_FILE', str(storage_file.parent / "analytics.json")):
            
            result = await check_profitability(hours=24)
            
            assert "roi_percentage" in result
            assert "net_profit" in result
            assert result["captcha_balance"] is None
