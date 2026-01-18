"""
Integration tests for WithdrawalAnalytics with faucet modules.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.base import FaucetBot, ClaimResult
from core.config import BotSettings
from core.withdrawal_analytics import get_analytics


@pytest.fixture
def mock_settings():
    """Create mock bot settings."""
    settings = MagicMock(spec=BotSettings)
    settings.use_faucetpay = True
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    return settings


@pytest.fixture
def mock_page():
    """Create mock Playwright page."""
    page = AsyncMock()
    return page


@pytest.fixture
def temp_analytics(tmp_path):
    """Create temporary analytics instance."""
    db_path = tmp_path / "test_integration.db"
    with patch("core.withdrawal_analytics.DB_FILE", str(db_path)):
        analytics = get_analytics()
        analytics.db_path = str(db_path)
        analytics._init_database()
        yield analytics


class TestWithdrawalAnalyticsIntegration:
    
    @pytest.mark.asyncio
    async def test_withdraw_wrapper_records_successful_withdrawal(
        self, mock_settings, mock_page, temp_analytics, tmp_path
    ):
        """Test that withdraw_wrapper records analytics on successful withdrawal."""
        # Patch the analytics DB path to use temp database
        with patch("core.withdrawal_analytics.DB_FILE", str(tmp_path / "test_integration.db")):
            # Create a faucet bot instance
            bot = FaucetBot(settings=mock_settings, page=mock_page)
            bot.faucet_name = "TestFaucet"
            
            # Mock the required methods
            bot.login_wrapper = AsyncMock(return_value=True)
            bot.get_balance = AsyncMock(side_effect=["5000", "4000"])  # Before and after
            
            # Mock the withdraw method to return success
            async def mock_withdraw():
                return ClaimResult(
                    success=True,
                    status="Withdrawal Successful",
                    amount="1000",
                    balance="4000"
                )
            bot.withdraw = mock_withdraw
            
            # Execute withdrawal wrapper
            result = await bot.withdraw_wrapper(mock_page)
            
            # Verify result
            assert result.success is True
            assert result.status == "Withdrawal Successful"
            
            # Verify analytics was recorded
            history = temp_analytics.get_withdrawal_history(limit=1)
            assert len(history) == 1
            
            record = history[0]
            assert record["faucet"] == "TestFaucet"
            assert record["amount"] == 1000.0
            assert record["status"] == "success"
            assert record["balance_before"] == 5000.0
            assert record["balance_after"] == 4000.0
    
    @pytest.mark.asyncio
    async def test_withdraw_wrapper_skips_below_threshold(
        self, mock_settings, mock_page, temp_analytics, tmp_path
    ):
        """Test that withdraw_wrapper doesn't record when balance is below threshold."""
        with patch("core.withdrawal_analytics.DB_FILE", str(tmp_path / "test_integration.db")):
            bot = FaucetBot(settings=mock_settings, page=mock_page)
            bot.faucet_name = "testfaucet"
            
            # Mock methods
            bot.login_wrapper = AsyncMock(return_value=True)
            bot.get_balance = AsyncMock(return_value="500")  # Below default threshold
            
            # Set threshold
            mock_settings.testfaucet_min_withdraw = 1000
            
            # Execute
            result = await bot.withdraw_wrapper(mock_page)
            
            # Should skip withdrawal
            assert result.success is True
            assert result.status == "Below Threshold"
            
            # No analytics should be recorded
            history = temp_analytics.get_withdrawal_history(limit=10)
            assert len(history) == 0
    
    def test_get_cryptocurrency_for_faucet(self, mock_settings, mock_page):
        """Test cryptocurrency detection from faucet name."""
        bot = FaucetBot(settings=mock_settings, page=mock_page)
        
        # Test various faucet names
        test_cases = [
            ("FreeBitcoin", "BTC"),
            ("LitePick", "LTC"),
            ("DogePick", "DOGE"),
            ("TronPick", "TRX"),
            ("EthPick", "ETH"),
            ("BinPick", "BNB"),
            ("SolPick", "SOL"),
            ("TonPick", "TON"),
            ("PolygonPick", "MATIC"),
            ("DashPick", "DASH"),
            ("BchPick", "BCH"),
            ("UsdPick", "USDT"),
            ("GenericFaucet", "UNKNOWN"),
        ]
        
        for faucet_name, expected_crypto in test_cases:
            bot.faucet_name = faucet_name
            crypto = bot._get_cryptocurrency_for_faucet()
            assert crypto == expected_crypto, f"Failed for {faucet_name}: got {crypto}, expected {expected_crypto}"
    
    @pytest.mark.asyncio
    async def test_withdraw_wrapper_handles_failed_withdrawal(
        self, mock_settings, mock_page, temp_analytics, tmp_path
    ):
        """Test that failed withdrawals are not recorded in analytics."""
        with patch("core.withdrawal_analytics.DB_FILE", str(tmp_path / "test_integration.db")):
            bot = FaucetBot(settings=mock_settings, page=mock_page)
            bot.faucet_name = "TestFaucet"
            
            # Mock methods
            bot.login_wrapper = AsyncMock(return_value=True)
            bot.get_balance = AsyncMock(return_value="5000")
            
            # Mock withdraw to fail
            async def mock_withdraw():
                return ClaimResult(
                    success=False,
                    status="Withdrawal Failed",
                    amount="0"
                )
            bot.withdraw = mock_withdraw
            
            # Execute
            result = await bot.withdraw_wrapper(mock_page)
            
            # Verify failure
            assert result.success is False
            
            # No analytics should be recorded for failed withdrawal
            history = temp_analytics.get_withdrawal_history(limit=10)
            assert len(history) == 0
    
    @pytest.mark.asyncio
    async def test_withdraw_wrapper_analytics_error_handling(
        self, mock_settings, mock_page, tmp_path
    ):
        """Test that analytics errors don't break withdrawal flow."""
        # Use invalid DB path to trigger analytics error
        with patch("core.withdrawal_analytics.DB_FILE", "/invalid/path/test.db"):
            bot = FaucetBot(settings=mock_settings, page=mock_page)
            bot.faucet_name = "TestFaucet"
            
            # Mock methods
            bot.login_wrapper = AsyncMock(return_value=True)
            bot.get_balance = AsyncMock(return_value="5000")
            
            # Mock successful withdraw
            async def mock_withdraw():
                return ClaimResult(
                    success=True,
                    status="Withdrawal Successful",
                    amount="1000"
                )
            bot.withdraw = mock_withdraw
            
            # Should complete successfully despite analytics error
            result = await bot.withdraw_wrapper(mock_page)
            
            assert result.success is True
            assert result.status == "Withdrawal Successful"
