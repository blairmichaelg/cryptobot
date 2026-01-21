"""
Additional tests for core.analytics that achieve 100% coverage.
Focus on get_trending_analysis and generate_automated_report functions.
"""
import pytest
import json
import os
import time
from unittest.mock import patch, mock_open
from core.analytics import EarningsTracker, get_tracker, ANALYTICS_FILE


@pytest.fixture
def temp_analytics_file(tmp_path):
    p = tmp_path / "test_analytics.json"
    with patch("core.analytics.ANALYTICS_FILE", str(p)):
        yield p


class TestAnalyticsCoverage:
    
    def test_get_trending_analysis(self, temp_analytics_file):
        """Test get_trending_analysis method (lines 217-255)."""
        tracker = EarningsTracker()
        now = time.time()
        
        # Create claims over multiple days with varying amounts
        for day in range(7):
            timestamp = now - (day * 24 * 3600) - 1800  # Each day, 30 min ago within the day
            # Faucet 1: increasing earnings (from past to present)
            tracker.claims.append({
                "timestamp": timestamp,
                "faucet": "faucet1",
                "success": True,
                "amount": 100 + ((6-day) * 10)  # Past to present: 100, 110, 120, ..., 160
            })
            # Faucet 2: stable earnings
            tracker.claims.append({
                "timestamp": timestamp,
                "faucet": "faucet2",
                "success": True,
                "amount": 50
            })
        
        # Test with 7 periods
        trends = tracker.get_trending_analysis(periods=7)
        
        # Verify structure
        assert "faucet1" in trends
        assert "faucet2" in trends
        
        # Verify each faucet has the right data
        assert "daily_earnings" in trends["faucet1"]
        assert "daily_claims" in trends["faucet1"]
        assert "daily_success" in trends["faucet1"]
        assert "growth_rate" in trends["faucet1"]
        assert "avg_daily_earnings" in trends["faucet1"]
        
        # Verify lengths
        assert len(trends["faucet1"]["daily_earnings"]) == 7
        assert len(trends["faucet1"]["daily_claims"]) == 7
        assert len(trends["faucet1"]["daily_success"]) == 7
        
        # Verify average calculations
        assert trends["faucet1"]["avg_daily_earnings"] > 0
        assert trends["faucet2"]["avg_daily_earnings"] > 0
        
        # Test edge case: 1 period
        trends_1 = tracker.get_trending_analysis(periods=1)
        assert len(trends_1["faucet1"]["daily_earnings"]) == 1
        
        # Test with no yesterday data (lines 246-250)
        tracker_new = EarningsTracker()
        tracker_new.claims = [{
            "timestamp": now - 1800,
            "faucet": "new_faucet",
            "success": True,
            "amount": 100
        }]
        trends_new = tracker_new.get_trending_analysis(periods=3)
        # When yesterday=0 but today>0, growth_rate should be 100
        assert "new_faucet" in trends_new
        assert trends_new["new_faucet"]["growth_rate"] == 100
        
        # Test edge case: both today and yesterday are 0 (line 250)
        tracker_zero = EarningsTracker()
        tracker_zero.claims = [{
            "timestamp": now - (5 * 24 * 3600),  # 5 days ago
            "faucet": "old_faucet",
            "success": True,
            "amount": 100
        }]
        trends_zero = tracker_zero.get_trending_analysis(periods=2)
        # Both periods 0 and 1 should be 0, so growth_rate = 0
        if "old_faucet" in trends_zero:
            assert trends_zero["old_faucet"]["growth_rate"] == 0
    
    def test_generate_automated_report(self, temp_analytics_file):
        """Test generate_automated_report method (lines 267-349)."""
        tracker = EarningsTracker()
        now = time.time()
        
        # Make sure session_start is set so claims fall within the session
        tracker.session_start = now - 10000  # Start session 10000 seconds ago
        
        # Add diverse claims to test all report sections
        claims_data = [
            # High performer
            {"timestamp": now - 1800, "faucet": "top_faucet", "success": True, "amount": 1000, "currency": "BTC"},
            {"timestamp": now - 3600, "faucet": "top_faucet", "success": True, "amount": 900, "currency": "BTC"},
            {"timestamp": now - 5400, "faucet": "top_faucet", "success": True, "amount": 800, "currency": "BTC"},
            # Medium performer
            {"timestamp": now - 1800, "faucet": "mid_faucet", "success": True, "amount": 500, "currency": "LTC"},
            {"timestamp": now - 3600, "faucet": "mid_faucet", "success": True, "amount": 400, "currency": "LTC"},
            # Low success rate performer (for "needs attention" section)
            {"timestamp": now - 1800, "faucet": "bad_faucet", "success": False, "amount": 0, "currency": "DOGE"},
            {"timestamp": now - 3600, "faucet": "bad_faucet", "success": False, "amount": 0, "currency": "DOGE"},
            {"timestamp": now - 5400, "faucet": "bad_faucet", "success": True, "amount": 10, "currency": "DOGE"},
            {"timestamp": now - 7200, "faucet": "bad_faucet", "success": False, "amount": 0, "currency": "DOGE"},
        ]
        
        for claim in claims_data:
            tracker.claims.append(claim)
        
        # Test with save_to_file=False (to avoid file I/O during test)
        report = tracker.generate_automated_report(save_to_file=False)
        
        # Verify report structure and content
        assert "CRYPTOBOT DAILY REPORT" in report
        assert "SESSION OVERVIEW" in report
        assert "EARNINGS BY CURRENCY" in report
        assert "TOP PERFORMING FAUCETS" in report
        assert "NEEDS ATTENTION" in report
        assert "Report generated:" in report
        
        # Verify session stats are included
        assert "Runtime:" in report
        assert "Claims Attempted:" in report
        assert "Success Rate:" in report
        
        # Verify currencies are listed
        assert "BTC:" in report or "BTC" in report
        assert "LTC:" in report or "LTC" in report
        assert "DOGE:" in report or "DOGE" in report
        
        # Verify faucets are mentioned
        assert "top_faucet" in report
        assert "mid_faucet" in report
        assert "bad_faucet" in report
        
        # Verify emojis/symbols are present
        assert "📈" in report or "📉" in report or "➡️" in report
        
        # Test with save_to_file=True (lines 336-347)
        with patch("os.makedirs") as mock_makedirs, \
             patch("builtins.open", create=True) as mock_open:
            report_saved = tracker.generate_automated_report(save_to_file=True)
            assert mock_makedirs.called
            assert mock_open.called
        
        # Test exception handling during file save (line 347)
        with patch("os.makedirs", side_effect=Exception("Permission denied")):
            report_error = tracker.generate_automated_report(save_to_file=True)
            # Should still return the report even if save fails
            assert "CRYPTOBOT DAILY REPORT" in report_error
    
    def test_generate_automated_report_no_low_performers(self, temp_analytics_file):
        """Test report when all faucets perform well (lines 321-325)."""
        tracker = EarningsTracker()
        now = time.time()
        
        # All successful claims
        for i in range(5):
            tracker.claims.append({
                "timestamp": now - (i * 1000),
                "faucet": "good_faucet",
                "success": True,
                "amount": 100,
                "currency": "BTC"
            })
        
        report = tracker.generate_automated_report(save_to_file=False)
        
        # Should show "all faucets performing well" message
        assert "all faucets performing well" in report or "None" in report
    
    def test_generate_automated_report_empty_tracker(self, temp_analytics_file):
        """Test report with no claims."""
        tracker = EarningsTracker()
        
        report = tracker.generate_automated_report(save_to_file=False)
        
        # Should handle empty data gracefully
        assert "CRYPTOBOT DAILY REPORT" in report
        assert isinstance(report, str)
        assert len(report) > 0
    
    def test_get_trending_analysis_initialization_edge_case(self, temp_analytics_file):
        """Test trending analysis when faucets don't exist in trends dict (line 230)."""
        tracker = EarningsTracker()
        now = time.time()
        
        # Single claim on day 0 (today)
        tracker.claims.append({
            "timestamp": now - 1800,
            "faucet": "new_faucet",
            "success": True,
            "amount": 100
        })
        
        # This should initialize the faucet in trends (line 230-236)
        trends = tracker.get_trending_analysis(periods=3)
        
        # Verify initialization
        assert "new_faucet" in trends
        # Period 0 = today (has claim), period 1 = yesterday (none), period 2 = day before (none)
        assert trends["new_faucet"]["daily_earnings"] == [100, 0, 0]
        assert trends["new_faucet"]["daily_claims"] == [1, 0, 0]
        assert trends["new_faucet"]["daily_success"] == [1, 0, 0]
    
    def test_load_exception_handling(self, temp_analytics_file):
        """Test _load exception handling (lines 57-59)."""
        # Create a corrupted analytics file
        with open(temp_analytics_file, "w") as f:
            f.write("not valid json {{{")
        
        # Should handle the exception gracefully
        tracker = EarningsTracker()
        assert tracker.claims == []
    
    def test_get_daily_summary(self, temp_analytics_file):
        """Test get_daily_summary method (lines 183-205)."""
        tracker = EarningsTracker()
        tracker.session_start = time.time() - 3600
        
        # Add some claims
        tracker.claims.append({
            "timestamp": time.time() - 1800,
            "faucet": "test_faucet",
            "success": True,
            "amount": 100,
            "currency": "BTC"
        })
        
        summary = tracker.get_daily_summary()
        
        # Verify all sections are present
        assert "EARNINGS SUMMARY" in summary
        assert "Session Duration:" in summary
        assert "Total Claims:" in summary
        assert "Success Rate:" in summary
        assert "Earnings by Currency:" in summary
        assert "BTC:" in summary
        assert "Per-Faucet Performance:" in summary
        assert "test_faucet:" in summary
    
    def test_get_tracker_singleton(self, temp_analytics_file):
        """Test get_tracker singleton pattern (lines 358-360)."""
        # Reset the global tracker
        import core.analytics
        core.analytics._tracker = None
        
        # First call should create a new instance
        tracker1 = get_tracker()
        assert tracker1 is not None
        
        # Second call should return the same instance
        tracker2 = get_tracker()
        assert tracker1 is tracker2
        
        # Reset for other tests
        core.analytics._tracker = None
    
    def test_record_claim(self, temp_analytics_file):
        """Test record_claim method (lines 85-98)."""
        tracker = EarningsTracker()
        
        # Record a claim (with allow_test=True to bypass test faucet filter)
        tracker.record_claim("test_faucet", True, 100.5, "BTC", 1000.0, allow_test=True)
        
        # Verify claim was recorded
        assert len(tracker.claims) == 1
        assert tracker.claims[0]["faucet"] == "test_faucet"
        assert tracker.claims[0]["success"] == True
        assert tracker.claims[0]["amount"] == 100.5
        assert tracker.claims[0]["currency"] == "BTC"
        assert tracker.claims[0]["balance_after"] == 1000.0
        assert "timestamp" in tracker.claims[0]
        
        # Verify file was saved (because record_claim calls _save)
        assert os.path.exists(temp_analytics_file)
    
    def test_save_exception_handling(self, temp_analytics_file):
        """Test _save exception handling (lines 70-71)."""
        tracker = EarningsTracker()
        
        # Mock open to fail during save
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            # Should log warning but not crash
            tracker._save()
        
        # Tracker should still be functional
        assert tracker.claims is not None
