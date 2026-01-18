import pytest
import json
import os
import time
from unittest.mock import patch, MagicMock
from core.analytics import EarningsTracker, ClaimRecord, get_tracker, ANALYTICS_FILE

@pytest.fixture
def temp_analytics_file(tmp_path):
    p = tmp_path / "test_analytics.json"
    with patch("core.analytics.ANALYTICS_FILE", str(p)):
        yield p

class TestAnalytics:
    
    def test_tracker_init_and_load(self, temp_analytics_file):
        """Test tracker initialization and loading from file (lines 39-55)."""
        # 1. No file
        tracker = EarningsTracker()
        assert tracker.claims == []
        
        # 2. Existing file
        data = {"claims": [{"timestamp": time.time(), "faucet": "test", "success": True}]}
        with open(temp_analytics_file, "w") as f:
            json.dump(data, f)
            
        tracker = EarningsTracker()
        assert len(tracker.claims) == 1
        assert tracker.claims[0]["faucet"] == "test"
        
        # 3. Corrupt file (52-54)
        with open(temp_analytics_file, "w") as f:
            f.write("invalid json")
            
        tracker = EarningsTracker()
        assert tracker.claims == []

    def test_record_claim_and_save(self, temp_analytics_file):
        """Test recording claims and periodic saving (lines 68-94)."""
        tracker = EarningsTracker()
        
        # Record 9 claims (no save yet)
        for i in range(9):
            tracker.record_claim(f"f{i}", True, 1.0, "BTC")
        
        assert len(tracker.claims) == 9
        assert not os.path.exists(temp_analytics_file)
        
        # 10th claim triggers save (92-93)
        tracker.record_claim("f9", True, 1.0, "BTC")
        assert os.path.exists(temp_analytics_file)
        
        with open(temp_analytics_file, "r") as f:
            data = json.load(f)
            assert len(data["claims"]) == 10

    def test_get_session_stats(self):
        """Test session statistics calculation (lines 95-117)."""
        tracker = EarningsTracker()
        tracker.session_start = time.time() - 3600 # 1h ago
        
        # Pre-session claim
        tracker.claims.append({"timestamp": time.time() - 7200, "faucet": "old", "success": True, "amount": 10, "currency": "BTC"})
        # Session claims
        tracker.claims.append({"timestamp": time.time() - 1800, "faucet": "new1", "success": True, "amount": 5, "currency": "BTC"})
        tracker.claims.append({"timestamp": time.time() - 600, "faucet": "new2", "success": False, "amount": 0, "currency": "BTC"})
        
        stats = tracker.get_session_stats()
        assert stats["total_claims"] == 2
        assert stats["successful_claims"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["earnings_by_currency"]["BTC"] == 5

    def test_get_faucet_stats(self):
        """Test per-faucet statistics (lines 119-146)."""
        tracker = EarningsTracker()
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 3600, "faucet": "f1", "success": True, "amount": 100},
            {"timestamp": now - 3600, "faucet": "f1", "success": False, "amount": 0},
            {"timestamp": now - 7200, "faucet": "f2", "success": True, "amount": 50},
        ]
        
        stats = tracker.get_faucet_stats(hours=4) # Should include all
        assert stats["f1"]["total"] == 2
        assert stats["f1"]["success"] == 1
        assert stats["f1"]["success_rate"] == 50.0
        assert stats["f1"]["earnings"] == 100
        
        assert stats["f2"]["total"] == 1
        
        # Test cutoff
        stats_short = tracker.get_faucet_stats(hours=1)
        assert "f2" not in stats_short

    def test_get_hourly_rate(self):
        """Test hourly rate calculation (lines 148-174)."""
        tracker = EarningsTracker()
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 1800, "faucet": "f1", "success": True, "amount": 100},
            {"timestamp": now - 3600, "faucet": "f2", "success": True, "amount": 50},
        ]
        
        rates = tracker.get_hourly_rate(hours=24) # 100 / 24 = 4.16, 50 / 24 = 2.08
        assert rates["f1"] == 100 / 24
        assert rates["f2"] == 50 / 24
        
        # Specific faucet
        rate_f1 = tracker.get_hourly_rate(faucet="f1", hours=1)
        assert list(rate_f1.keys()) == ["f1"]
        assert rate_f1["f1"] == 100 / 1

    def test_get_daily_summary(self):
        """Test human-readable summary (lines 176-200)."""
        tracker = EarningsTracker()
        tracker.record_claim("test_faucet", True, 0.0001, "BTC")
        summary = tracker.get_daily_summary()
        assert "test_faucet" in summary
        assert "BTC" in summary

    def test_tracker_singleton(self):
        """Test global tracker singleton (lines 206-211)."""
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

    def test_save_error(self, temp_analytics_file):
        """Test save error handling (lines 65-66)."""
        tracker = EarningsTracker()
        # Mock open to fail
        with patch("builtins.open", side_effect=PermissionError("Denied")):
            tracker._save() # Should log warning instead of crashing
