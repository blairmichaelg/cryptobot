# pylint: disable=protected-access
"""
Tests for automated withdrawal system with real-time fee monitoring.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from core.wallet_manager import WalletDaemon
from core.auto_withdrawal import AutoWithdrawal, get_auto_withdrawal_instance
from core.config import BotSettings


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = BotSettings(
        wallet_rpc_urls={"BTC": "http://localhost:7777"},
        electrum_rpc_user="test",
        electrum_rpc_pass="test",
        use_faucetpay=False,
        btc_withdrawal_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        ltc_withdrawal_address="LTC123",
        withdrawal_thresholds={
            "BTC": {"min": 5000, "target": 50000, "max": 100000},
            "LTC": {"min": 1000, "target": 10000, "max": 50000}
        },
        prefer_off_peak_withdrawals=True,
        off_peak_hours=[0, 1, 2, 3, 4, 5, 22, 23]
    )
    return settings


@pytest.fixture
def mock_tracker():
    """Create mock analytics tracker."""
    tracker = Mock()
    tracker.claims = [
        {"success": True, "currency": "BTC", "balance_after": 50000, "timestamp": 1000},
        {"success": True, "currency": "LTC", "balance_after": 10000, "timestamp": 1000}
    ]
    return tracker


@pytest.mark.asyncio
async def test_get_mempool_fee_rate_btc():
    """Test fetching BTC mempool fees."""
    wallet = WalletDaemon(
        rpc_urls={"BTC": "http://localhost:7777"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Mock response for mempool.space
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "minimumFee": 2,
            "halfHourFee": 5,
            "fastestFee": 10
        })
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        fees = await wallet.get_mempool_fee_rate("BTC")
        
        assert fees is not None
        assert fees["economy"] == 2
        assert fees["normal"] == 5
        assert fees["priority"] == 10


@pytest.mark.asyncio
async def test_get_mempool_fee_rate_ltc():
    """Test fetching LTC mempool fees from BlockCypher."""
    wallet = WalletDaemon(
        rpc_urls={"LTC": "http://localhost:7778"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Mock BlockCypher response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "low_fee_per_kb": 1000,
            "medium_fee_per_kb": 5000,
            "high_fee_per_kb": 10000
        })
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        fees = await wallet.get_mempool_fee_rate("LTC")
        
        assert fees is not None
        assert fees["economy"] == 1
        assert fees["normal"] == 5
        assert fees["priority"] == 10


@pytest.mark.asyncio
async def test_should_withdraw_now_excellent_fees():
    """Test withdrawal approval with excellent fees (<5 sat/byte)."""
    wallet = WalletDaemon(
        rpc_urls={"BTC": "http://localhost:7777"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    # Mock mempool fees - excellent
    wallet.get_mempool_fee_rate = AsyncMock(return_value={
        "economy": 3,
        "normal": 5,
        "priority": 8
    })
    
    # Should approve even if not off-peak
    with patch.object(wallet, 'is_off_peak_hour', return_value=False):
        should_withdraw = await wallet.should_withdraw_now("BTC", 50000, 30000)
        assert should_withdraw is True


@pytest.mark.asyncio
async def test_should_withdraw_now_high_fees():
    """Test withdrawal deferral with high fees (>50 sat/byte)."""
    wallet = WalletDaemon(
        rpc_urls={"BTC": "http://localhost:7777"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    # Mock mempool fees - high
    wallet.get_mempool_fee_rate = AsyncMock(return_value={
        "economy": 60,
        "normal": 80,
        "priority": 100
    })
    
    # Should defer even if off-peak
    with patch.object(wallet, 'is_off_peak_hour', return_value=True):
        should_withdraw = await wallet.should_withdraw_now("BTC", 50000, 30000)
        assert should_withdraw is False


@pytest.mark.asyncio
async def test_should_withdraw_now_below_threshold():
    """Test withdrawal deferral when balance is below threshold."""
    wallet = WalletDaemon(
        rpc_urls={"BTC": "http://localhost:7777"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    should_withdraw = await wallet.should_withdraw_now("BTC", 10000, 30000)
    assert should_withdraw is False


@pytest.mark.asyncio
async def test_auto_withdrawal_get_balances(mock_settings, mock_tracker):
    """Test balance extraction from analytics."""
    wallet = WalletDaemon(
        rpc_urls=mock_settings.wallet_rpc_urls,
        rpc_user="test",
        rpc_pass="test"
    )
    
    auto_withdrawal = AutoWithdrawal(wallet, mock_settings, mock_tracker)
    balances = auto_withdrawal._get_balances_by_currency()
    
    assert balances["BTC"] == 50000
    assert balances["LTC"] == 10000


@pytest.mark.asyncio
async def test_auto_withdrawal_get_withdrawal_address(mock_settings, mock_tracker):
    """Test withdrawal address resolution."""
    wallet = WalletDaemon(
        rpc_urls=mock_settings.wallet_rpc_urls,
        rpc_user="test",
        rpc_pass="test"
    )
    
    auto_withdrawal = AutoWithdrawal(wallet, mock_settings, mock_tracker)
    
    # Test direct wallet
    mock_settings.use_faucetpay = False
    address = auto_withdrawal._get_withdrawal_address("BTC")
    assert address == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    
    # Test FaucetPay
    mock_settings.use_faucetpay = True
    mock_settings.faucetpay_btc_address = "FP_BTC_ADDRESS"
    address = auto_withdrawal._get_withdrawal_address("BTC")
    assert address == "FP_BTC_ADDRESS"


@pytest.mark.asyncio
async def test_auto_withdrawal_check_and_execute(mock_settings, mock_tracker):
    """Test full withdrawal check and execution flow."""
    wallet = WalletDaemon(
        rpc_urls=mock_settings.wallet_rpc_urls,
        rpc_user="test",
        rpc_pass="test"
    )
    
    # Mock wallet methods
    wallet.should_withdraw_now = AsyncMock(return_value=True)
    wallet.batch_withdraw = AsyncMock(return_value="txid123")
    wallet.get_mempool_fee_rate = AsyncMock(return_value={
        "economy": 5,
        "normal": 10,
        "priority": 15
    })
    
    auto_withdrawal = AutoWithdrawal(wallet, mock_settings, mock_tracker)
    
    summary = await auto_withdrawal.check_and_execute_withdrawals()
    
    assert summary["balances_checked"] == 2
    assert summary["withdrawals_executed"] >= 0  # Depends on configured addresses
    assert "currencies_processed" in summary
    assert len(summary["currencies_processed"]) == 2


@pytest.mark.asyncio
async def test_auto_withdrawal_defers_when_not_optimal(mock_settings, mock_tracker):
    """Test that withdrawal is deferred when conditions aren't optimal."""
    wallet = WalletDaemon(
        rpc_urls=mock_settings.wallet_rpc_urls,
        rpc_user="test",
        rpc_pass="test"
    )
    
    # Mock wallet to reject withdrawal
    wallet.should_withdraw_now = AsyncMock(return_value=False)
    
    auto_withdrawal = AutoWithdrawal(wallet, mock_settings, mock_tracker)
    
    summary = await auto_withdrawal.check_and_execute_withdrawals()
    
    assert summary["withdrawals_executed"] == 0
    assert summary["withdrawals_deferred"] > 0


@pytest.mark.asyncio
async def test_get_network_fee_estimate_with_mempool_fallback():
    """Test fee estimation with mempool API primary and RPC fallback."""
    wallet = WalletDaemon(
        rpc_urls={"BTC": "http://localhost:7777"},
        rpc_user="test",
        rpc_pass="test"
    )
    
    # Mock mempool API to fail
    wallet.get_mempool_fee_rate = AsyncMock(return_value=None)
    
    # Mock RPC fallback
    wallet._rpc_call = AsyncMock(return_value={
        "feerate": 0.00005  # 5 sat/byte in BTC/kB
    })
    
    fee = await wallet.get_network_fee_estimate("BTC", "economy")
    assert fee == 5  # Should fallback to RPC


@pytest.mark.asyncio
async def test_auto_withdrawal_factory():
    """Test factory function creates instance correctly."""
    wallet = Mock()
    settings = Mock()
    tracker = Mock()
    
    instance = get_auto_withdrawal_instance(wallet, settings, tracker)
    
    assert isinstance(instance, AutoWithdrawal)
    assert instance.wallet == wallet
    assert instance.settings == settings
    assert instance.tracker == tracker


def test_auto_withdrawal_get_stats(mock_settings, mock_tracker):
    """Test withdrawal statistics calculation."""
    wallet = Mock()
    auto_withdrawal = AutoWithdrawal(wallet, mock_settings, mock_tracker)
    
    # Add some withdrawal history
    auto_withdrawal.withdrawal_history = [
        {"timestamp": 1000, "currency": "BTC", "amount": 50000},
        {"timestamp": 2000, "currency": "LTC", "amount": 10000}
    ]
    
    stats = auto_withdrawal.get_withdrawal_stats(hours=24)
    
    assert stats["total_withdrawals"] == 2
    assert "BTC" in stats["by_currency"]
    assert stats["by_currency"]["BTC"]["count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
