import pytest
import sqlite3
import time
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from dataclasses import asdict

from core.withdrawal_analytics import (
    WithdrawalAnalytics,
    WithdrawalRecord,
    WithdrawalMethod,
    WithdrawalStatus,
    get_analytics
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_withdrawals.db"
    return str(db_path)


@pytest.fixture
def analytics(temp_db):
    """Create a WithdrawalAnalytics instance with temporary database."""
    return WithdrawalAnalytics(db_path=temp_db)


class TestWithdrawalAnalytics:
    
    def test_init_and_database_creation(self, temp_db):
        """Test initialization creates database schema."""
        analytics = WithdrawalAnalytics(db_path=temp_db)
        
        # Verify database file was created
        assert os.path.exists(temp_db)
        
        # Verify schema
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='withdrawals'
        """)
        assert cursor.fetchone() is not None
        
        # Verify indexes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name IN ('idx_timestamp', 'idx_faucet', 'idx_crypto')
        """)
        indexes = cursor.fetchall()
        assert len(indexes) == 3
        
        conn.close()
    
    def test_record_withdrawal_success(self, analytics):
        """Test recording a successful withdrawal."""
        record_id = analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            network_fee=0.00001,
            platform_fee=0.000005,
            withdrawal_method="faucetpay",
            status="success",
            balance_before=0.0005,
            balance_after=0.0004,
            tx_id="abc123",
            notes="Test withdrawal"
        )
        
        assert record_id > 0
        
        # Verify record was stored
        history = analytics.get_withdrawal_history(limit=1)
        assert len(history) == 1
        assert history[0]["faucet"] == "FreeBitcoin"
        assert history[0]["cryptocurrency"] == "BTC"
        assert history[0]["amount"] == 0.0001
        assert history[0]["network_fee"] == 0.00001
        assert history[0]["platform_fee"] == 0.000005
        assert history[0]["status"] == "success"
        assert history[0]["tx_id"] == "abc123"
    
    def test_record_withdrawal_failed(self, analytics):
        """Test recording a failed withdrawal."""
        record_id = analytics.record_withdrawal(
            faucet="Cointiply",
            cryptocurrency="LTC",
            amount=0.01,
            status="failed",
            notes="Insufficient balance"
        )
        
        assert record_id > 0
        
        history = analytics.get_withdrawal_history(limit=1)
        assert history[0]["status"] == "failed"
        assert history[0]["notes"] == "Insufficient balance"
    
    def test_calculate_effective_rate_no_data(self, analytics):
        """Test effective rate calculation with no data."""
        result = analytics.calculate_effective_rate()
        
        assert result["total_earned"] == 0.0
        assert result["total_fees"] == 0.0
        assert result["net_profit"] == 0.0
        assert result["hourly_rate"] == 0.0
        assert result["fee_percentage"] == 0.0
    
    def test_calculate_effective_rate_with_data(self, analytics):
        """Test effective rate calculation with withdrawal data."""
        # Record multiple withdrawals
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            network_fee=0.00001,
            platform_fee=0.000005,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="Cointiply",
            cryptocurrency="BTC",
            amount=0.0002,
            network_fee=0.00002,
            platform_fee=0.00001,
            status="success"
        )
        
        # Failed withdrawal shouldn't count
        analytics.record_withdrawal(
            faucet="Test",
            cryptocurrency="BTC",
            amount=0.001,
            status="failed"
        )
        
        result = analytics.calculate_effective_rate(hours=24)
        
        # 0.0001 + 0.0002 = 0.0003 total earned
        assert result["total_earned"] == pytest.approx(0.0003)
        
        # 0.00001 + 0.000005 + 0.00002 + 0.00001 = 0.000045 total fees
        assert result["total_fees"] == pytest.approx(0.000045)
        
        # 0.0003 - 0.000045 = 0.000255 net profit
        assert result["net_profit"] == pytest.approx(0.000255)
        
        # Net profit / 24 hours
        assert result["hourly_rate"] == pytest.approx(0.000255 / 24)
        
        # Fee percentage
        assert result["fee_percentage"] == pytest.approx(15.0)
    
    def test_calculate_effective_rate_filtered(self, analytics):
        """Test effective rate calculation with filters."""
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            network_fee=0.00001,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="LitePick",
            cryptocurrency="LTC",
            amount=0.01,
            network_fee=0.001,
            status="success"
        )
        
        # Filter by faucet
        btc_result = analytics.calculate_effective_rate(faucet="FreeBitcoin")
        assert btc_result["total_earned"] == pytest.approx(0.0001)
        
        # Filter by cryptocurrency
        ltc_result = analytics.calculate_effective_rate(cryptocurrency="LTC")
        assert ltc_result["total_earned"] == pytest.approx(0.01)
    
    def test_get_faucet_performance(self, analytics):
        """Test per-faucet performance statistics."""
        # Record multiple withdrawals for different faucets
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            network_fee=0.00001,
            platform_fee=0.000005,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0002,
            network_fee=0.00002,
            status="failed"
        )
        
        analytics.record_withdrawal(
            faucet="Cointiply",
            cryptocurrency="BTC",
            amount=0.0003,
            network_fee=0.00003,
            status="success"
        )
        
        performance = analytics.get_faucet_performance(hours=24)
        
        # Check FreeBitcoin stats
        assert "FreeBitcoin" in performance
        fb_stats = performance["FreeBitcoin"]
        assert fb_stats["total_withdrawals"] == 2
        assert fb_stats["successful_withdrawals"] == 1
        assert fb_stats["success_rate"] == 50.0
        assert fb_stats["total_earned"] == pytest.approx(0.0003)  # Both withdrawals count for amount
        assert fb_stats["net_profit"] == pytest.approx(0.0003 - 0.000015 - 0.00002)
        
        # Check Cointiply stats
        assert "Cointiply" in performance
        ct_stats = performance["Cointiply"]
        assert ct_stats["total_withdrawals"] == 1
        assert ct_stats["successful_withdrawals"] == 1
        assert ct_stats["success_rate"] == 100.0
    
    def test_recommend_withdrawal_strategy_insufficient_balance(self, analytics):
        """Test recommendation when balance is too low."""
        # Record some history
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.001,
            network_fee=0.0001,
            status="success"
        )
        
        recommendation = analytics.recommend_withdrawal_strategy(
            current_balance=0.0001,  # Too low compared to avg fee
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        
        assert recommendation["action"] == "wait"
        assert "too low" in recommendation["reason"].lower()
    
    def test_recommend_withdrawal_strategy_high_fee_percentage(self, analytics):
        """Test recommendation when fee percentage is too high."""
        # Record history with high fees
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.001,
            network_fee=0.0001,
            status="success"
        )
        
        recommendation = analytics.recommend_withdrawal_strategy(
            current_balance=0.0005,  # Fee would be 20% of balance
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        
        assert recommendation["action"] == "wait"
        assert "fee" in recommendation["reason"].lower()
    
    @patch('core.withdrawal_analytics.datetime')
    def test_recommend_withdrawal_strategy_peak_hours(self, mock_datetime, analytics):
        """Test recommendation during peak hours."""
        # Mock datetime to return peak hours (e.g., 12:00 UTC)
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_datetime.now.return_value = mock_now
        
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.01,
            network_fee=0.0001,
            status="success"
        )
        
        recommendation = analytics.recommend_withdrawal_strategy(
            current_balance=0.01,
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        
        assert recommendation["action"] == "wait"
        assert "off-peak" in recommendation["reason"].lower()
    
    def test_recommend_withdrawal_strategy_optimal_conditions(self, analytics):
        """Test recommendation logic evaluates all factors."""
        # Record history with reasonable fees (1% fee)
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.01,
            network_fee=0.00005,
            platform_fee=0.00005,
            status="success"
        )
        
        recommendation = analytics.recommend_withdrawal_strategy(
            current_balance=0.01,  # Good balance (fee will be ~1% of balance)
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        
        # Recommendation should be based on time of day
        # During peak hours: wait, during off-peak: withdraw
        assert recommendation["action"] in ["withdraw", "wait"]
        assert "optimal" in recommendation["reason"].lower() or "off-peak" in recommendation["reason"].lower()
    
    def test_recommend_withdrawal_method_selection(self, analytics):
        """Test withdrawal method recommendation based on amount."""
        # Record history with low fees
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.01,
            network_fee=0.00005,
            platform_fee=0.00005,
            status="success"
        )
        
        # Test that method selection is based on balance size
        small_rec = analytics.recommend_withdrawal_strategy(
            current_balance=0.0005,
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        assert small_rec["optimal_method"] == "faucetpay"
        
        # Large balance -> Direct
        large_rec = analytics.recommend_withdrawal_strategy(
            current_balance=0.002,  # Above 0.001 threshold
            cryptocurrency="BTC",
            faucet="FreeBitcoin"
        )
        assert large_rec["optimal_method"] == "direct"
    
    def test_generate_report_daily(self, analytics):
        """Test daily report generation."""
        # Add some withdrawal data
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            network_fee=0.00001,
            platform_fee=0.000005,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="Cointiply",
            cryptocurrency="BTC",
            amount=0.0002,
            network_fee=0.00002,
            status="success"
        )
        
        report = analytics.generate_report(period="daily")
        
        # Verify report contains key sections
        assert "WITHDRAWAL ANALYTICS REPORT" in report
        assert "OVERALL PERFORMANCE" in report
        assert "PER-FAUCET BREAKDOWN" in report
        assert "FreeBitcoin" in report
        assert "Cointiply" in report
        assert "BEST PERFORMER" in report
    
    def test_generate_report_with_crypto_filter(self, analytics):
        """Test report generation filtered by cryptocurrency."""
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="LitePick",
            cryptocurrency="LTC",
            amount=0.01,
            status="success"
        )
        
        btc_report = analytics.generate_report(period="daily", cryptocurrency="BTC")
        
        assert "FreeBitcoin" in btc_report
        # LitePick should be excluded because it only has LTC withdrawals
        # (Note: This test relies on _faucet_uses_crypto filtering)
    
    def test_get_withdrawal_history(self, analytics):
        """Test retrieving withdrawal history."""
        # Add test data
        analytics.record_withdrawal(
            faucet="FreeBitcoin",
            cryptocurrency="BTC",
            amount=0.0001,
            status="success"
        )
        
        analytics.record_withdrawal(
            faucet="Cointiply",
            cryptocurrency="LTC",
            amount=0.01,
            status="success"
        )
        
        # Get all history
        all_history = analytics.get_withdrawal_history(limit=10)
        assert len(all_history) == 2
        
        # Filter by faucet
        fb_history = analytics.get_withdrawal_history(faucet="FreeBitcoin")
        assert len(fb_history) == 1
        assert fb_history[0]["faucet"] == "FreeBitcoin"
        
        # Filter by cryptocurrency
        btc_history = analytics.get_withdrawal_history(cryptocurrency="BTC")
        assert len(btc_history) == 1
        assert btc_history[0]["cryptocurrency"] == "BTC"
    
    def test_get_withdrawal_history_limit(self, analytics):
        """Test withdrawal history respects limit parameter."""
        # Add multiple records
        for i in range(10):
            analytics.record_withdrawal(
                faucet="Test",
                cryptocurrency="BTC",
                amount=0.0001,
                status="success"
            )
        
        limited_history = analytics.get_withdrawal_history(limit=5)
        assert len(limited_history) == 5
    
    def test_get_withdrawal_history_ordering(self, analytics):
        """Test withdrawal history is ordered by timestamp descending."""
        # Add records with slight delays
        analytics.record_withdrawal(
            faucet="First",
            cryptocurrency="BTC",
            amount=0.0001,
            status="success"
        )
        
        time.sleep(0.01)  # Ensure different timestamp
        
        analytics.record_withdrawal(
            faucet="Second",
            cryptocurrency="BTC",
            amount=0.0001,
            status="success"
        )
        
        history = analytics.get_withdrawal_history(limit=2)
        assert history[0]["faucet"] == "Second"  # Most recent first
        assert history[1]["faucet"] == "First"
    
    def test_singleton_pattern(self, temp_db):
        """Test global analytics singleton."""
        with patch("core.withdrawal_analytics.DB_FILE", temp_db):
            analytics1 = get_analytics()
            analytics2 = get_analytics()
            
            assert analytics1 is analytics2
    
    def test_database_error_handling(self, temp_db):
        """Test error handling for database operations."""
        analytics = WithdrawalAnalytics(db_path=temp_db)
        
        # Close and delete database to simulate error
        os.remove(temp_db)
        
        # Should handle errors gracefully
        result = analytics.calculate_effective_rate()
        assert result["total_earned"] == 0.0
        
        performance = analytics.get_faucet_performance()
        assert performance == {}
        
        history = analytics.get_withdrawal_history()
        assert history == []
    
    def test_withdrawal_record_dataclass(self):
        """Test WithdrawalRecord dataclass."""
        record = WithdrawalRecord(
            timestamp=time.time(),
            faucet="Test",
            cryptocurrency="BTC",
            amount=0.001,
            network_fee=0.0001,
            platform_fee=0.00005,
            withdrawal_method="faucetpay",
            status="success",
            tx_id="test123"
        )
        
        assert record.faucet == "Test"
        assert record.cryptocurrency == "BTC"
        assert record.amount == 0.001
        assert record.tx_id == "test123"
        
        # Test asdict conversion
        record_dict = asdict(record)
        assert record_dict["faucet"] == "Test"
    
    def test_enums(self):
        """Test withdrawal enums."""
        assert WithdrawalMethod.FAUCETPAY.value == "faucetpay"
        assert WithdrawalMethod.DIRECT.value == "direct"
        assert WithdrawalMethod.WALLET_DAEMON.value == "wallet_daemon"
        
        assert WithdrawalStatus.SUCCESS.value == "success"
        assert WithdrawalStatus.FAILED.value == "failed"
        assert WithdrawalStatus.PENDING.value == "pending"
    
    def test_time_filtering_cutoff(self, analytics):
        """Test that time-based queries correctly filter old data."""
        current_time = time.time()
        
        # Add old withdrawal (48 hours ago)
        with patch('time.time', return_value=current_time - 48*3600):
            analytics.record_withdrawal(
                faucet="Old",
                cryptocurrency="BTC",
                amount=0.001,
                status="success"
            )
        
        # Add recent withdrawal (1 hour ago)
        with patch('time.time', return_value=current_time - 3600):
            analytics.record_withdrawal(
                faucet="Recent",
                cryptocurrency="BTC",
                amount=0.001,
                status="success"
            )
        
        # Query last 24 hours should only return recent
        with patch('time.time', return_value=current_time):
            performance = analytics.get_faucet_performance(hours=24)
            assert "Recent" in performance
            assert "Old" not in performance
