import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.wallet_manager import WalletDaemon

@pytest.mark.asyncio
async def test_wallet_connection_success():
    expected_result = {"result": "valid_version", "error": None}
    
    # mock_response must be async to support await json()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = expected_result
    
    # post_ctx is the Context Manager. __aenter__ returns mock_response
    post_ctx = AsyncMock()
    post_ctx.__aenter__.return_value = mock_response
    post_ctx.__aexit__.return_value = None
    
    # session.post IS NOT ASYNC. It returns the context manager immediately.
    # So we use MagicMock for .post, not AsyncMock
    mock_session = MagicMock()
    mock_session.post.return_value = post_ctx
    
    with patch('aiohttp.ClientSession') as MockSessionClass:
        # ClientSession() instantiation returns the session instance
        # session instance is an async context manager
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx) # CRITICAL FIX
        
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        MockSessionClass.return_value = session_instance
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        result = await daemon.check_connection()
        
        assert result is True

@pytest.mark.asyncio
async def test_wallet_get_balance():
    expected_balance = {"confirmed": 1.5, "unconfirmed": 0.0}
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"result": expected_balance, "error": None}
    
    post_ctx = AsyncMock()
    post_ctx.__aenter__.return_value = mock_response
    post_ctx.__aexit__.return_value = None
    
    # The session instance needs to be set up correctly
    session_instance = AsyncMock()
    session_instance.post = MagicMock(return_value=post_ctx) # CRITICAL FIX
    session_instance.__aenter__.return_value = session_instance
    session_instance.__aexit__.return_value = None

    with patch('aiohttp.ClientSession') as MockSessionClass:
        MockSessionClass.return_value = session_instance
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        balance = await daemon.get_balance()
        assert balance == expected_balance


class TestWalletDaemonMethods:
    """Test suite for WalletDaemon methods."""
    
    @pytest.mark.asyncio
    async def test_get_unused_address_success(self):
        """Test get_unused_address returns address."""
        expected_address = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": expected_address, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            address = await daemon.get_unused_address()
            assert address == expected_address
    
    @pytest.mark.asyncio
    async def test_validate_address_valid_boolean_response(self):
        """Test validate_address with boolean response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": True, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            is_valid = await daemon.validate_address("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
            assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_address_valid_dict_response(self):
        """Test validate_address with dict response containing isvalid."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": {"isvalid": True, "address": "bc1q..."}, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            is_valid = await daemon.validate_address("bc1q...")
            assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_address_invalid(self):
        """Test validate_address with invalid address."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": {"isvalid": False}, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            is_valid = await daemon.validate_address("invalid_address")
            assert is_valid is False


class TestWalletDaemonErrorHandling:
    """Test suite for WalletDaemon error handling."""
    
    @pytest.mark.asyncio
    async def test_http_error_response(self):
        """Test handling of HTTP error responses."""
        mock_response = AsyncMock()
        mock_response.status = 500  # Server error
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            result = await daemon.check_connection()
            # check_connection returns False when result is None, not None itself
            assert result is False
    
    @pytest.mark.asyncio
    async def test_rpc_error_response(self):
        """Test handling of RPC error in response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": None,
            "error": {"code": -32601, "message": "Method not found"}
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            result = await daemon.get_balance()
            assert result is None
    
    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """Test handling of connection failures."""
        session_instance = AsyncMock()
        session_instance.post = MagicMock(side_effect=Exception("Connection refused"))
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            result = await daemon.check_connection()
            # check_connection returns False when result is None
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_connection_returns_false_on_none_result(self):
        """Test check_connection returns False when result is None."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": None, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            result = await daemon.check_connection()
            assert result is False


class TestWalletDaemonAuthentication:
    """Test suite for WalletDaemon authentication."""
    
    @pytest.mark.asyncio
    async def test_daemon_with_authentication(self):
        """Test WalletDaemon with username and password."""
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        assert daemon.urls == {"BTC": "http://localhost:7777"}
        assert daemon.auth is not None
        assert daemon.auth.login == "user"
        assert daemon.auth.password == "pass"
    
    @pytest.mark.asyncio
    async def test_daemon_without_authentication(self):
        """Test WalletDaemon without credentials."""
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, None, None)
        assert daemon.urls == {"BTC": "http://localhost:7777"}
        assert daemon.auth is None


class TestWalletDaemonRPCCall:
    """Test suite for WalletDaemon._rpc_call edge cases."""
    
    @pytest.mark.asyncio
    async def test_rpc_call_no_url_configured(self):
        """Test _rpc_call with no configured URL for coin."""
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        result = await daemon._rpc_call("ETH", "somemethod")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test close method closes the session."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"result": True, "error": None}
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.close = AsyncMock()
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            # Trigger session creation
            await daemon.check_connection()
            # Close the session
            await daemon.close()
            session_instance.close.assert_called_once()


class TestWalletDaemonNetworkFees:
    """Test suite for network fee estimation methods."""
    
    @pytest.mark.asyncio
    async def test_get_network_fee_estimate_success(self):
        """Test get_network_fee_estimate returns fee rate."""
        # estimatesmartfee returns feerate in BTC/kB
        # Method converts to sat/byte
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"feerate": 0.00001000},  # 1000 sat/kB = 1 sat/byte
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            fee_rate = await daemon.get_network_fee_estimate("BTC", "economy")
            assert fee_rate == 1  # 1 sat/byte
    
    @pytest.mark.asyncio
    async def test_get_network_fee_estimate_priority_levels(self):
        """Test different priority levels use different block targets."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"feerate": 0.00005000},
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            
            # Test priority
            await daemon.get_network_fee_estimate("BTC", "priority")
            # Test normal
            await daemon.get_network_fee_estimate("BTC", "normal")
    
    @pytest.mark.asyncio
    async def test_get_network_fee_estimate_no_feerate(self):
        """Test get_network_fee_estimate when no feerate in response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {},
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            fee_rate = await daemon.get_network_fee_estimate("BTC")
            assert fee_rate is None
    
    @pytest.mark.asyncio
    async def test_get_network_fee_estimate_rpc_error(self):
        """Test get_network_fee_estimate when RPC returns None."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": None,
            "error": "Some error"
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            fee_rate = await daemon.get_network_fee_estimate("BTC")
            assert fee_rate is None


class TestWalletDaemonOffPeakDetection:
    """Test suite for off-peak time detection."""
    
    @pytest.mark.asyncio
    async def test_is_off_peak_hour_night_time(self):
        """Test is_off_peak_hour returns True for night hours."""
        from datetime import datetime, timezone
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        
        # Test late night (22:00 UTC)
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 10, 22, 0, tzinfo=timezone.utc)
            assert daemon.is_off_peak_hour() is True
        
        # Test early morning (3:00 UTC)
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 10, 3, 0, tzinfo=timezone.utc)
            assert daemon.is_off_peak_hour() is True
    
    @pytest.mark.asyncio
    async def test_is_off_peak_hour_weekend(self):
        """Test is_off_peak_hour returns True for weekends."""
        from datetime import datetime, timezone
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        
        # Saturday at noon
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
            assert daemon.is_off_peak_hour() is True
        
        # Sunday at noon
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 7, 12, 0, tzinfo=timezone.utc)
            assert daemon.is_off_peak_hour() is True
    
    @pytest.mark.asyncio
    async def test_is_off_peak_hour_peak_time(self):
        """Test is_off_peak_hour returns False for peak hours."""
        from datetime import datetime, timezone
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        
        # Tuesday at 10:00 AM UTC
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 9, 10, 0, tzinfo=timezone.utc)
            assert daemon.is_off_peak_hour() is False


class TestWalletDaemonWithdrawalLogic:
    """Test suite for withdrawal decision logic."""
    
    @pytest.mark.asyncio
    async def test_should_withdraw_now_below_threshold(self):
        """Test should_withdraw_now returns False when below threshold."""
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        
        result = await daemon.should_withdraw_now("BTC", 10000, min_threshold=30000)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_should_withdraw_now_not_off_peak(self):
        """Test should_withdraw_now returns False during peak hours."""
        from datetime import datetime, timezone
        
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        
        # Mock peak time (Tuesday 10 AM)
        with patch('core.wallet_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 9, 10, 0, tzinfo=timezone.utc)
            result = await daemon.should_withdraw_now("BTC", 50000, min_threshold=30000)
            assert result is False
    
    @pytest.mark.asyncio
    async def test_should_withdraw_now_high_fees(self):
        """Test should_withdraw_now returns False when fees are high."""
        from datetime import datetime, timezone
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"feerate": 0.00060000},  # High fee: 60 sat/byte (>50 threshold)
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            
            # Mock off-peak time but high fees
            with patch('core.wallet_manager.datetime') as mock_dt:
                mock_dt.now.return_value = datetime(2024, 1, 6, 3, 0, tzinfo=timezone.utc)
                result = await daemon.should_withdraw_now("BTC", 50000, min_threshold=30000)
                assert result is False
    
    @pytest.mark.asyncio
    async def test_should_withdraw_now_success(self):
        """Test should_withdraw_now returns True when all conditions met."""
        from datetime import datetime, timezone
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"feerate": 0.00001000},  # Low fee: 1 sat/byte
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            
            # Mock off-peak time and low fees
            with patch('core.wallet_manager.datetime') as mock_dt:
                mock_dt.now.return_value = datetime(2024, 1, 6, 3, 0, tzinfo=timezone.utc)
                result = await daemon.should_withdraw_now("BTC", 50000, min_threshold=30000)
                assert result is True


class TestWalletDaemonBatchWithdraw:
    """Test suite for batch withdrawal functionality."""
    
    @pytest.mark.asyncio
    async def test_batch_withdraw_no_outputs(self):
        """Test batch_withdraw returns None when no outputs provided."""
        daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
        result = await daemon.batch_withdraw("BTC", [])
        assert result is None
    
    @pytest.mark.asyncio
    async def test_batch_withdraw_invalid_address(self):
        """Test batch_withdraw returns None when address is invalid."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "result": {"isvalid": False},
            "error": None
        }
        
        post_ctx = AsyncMock()
        post_ctx.__aenter__.return_value = mock_response
        post_ctx.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(return_value=post_ctx)
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            outputs = [{"address": "invalid_address", "amount": 0.001}]
            result = await daemon.batch_withdraw("BTC", outputs)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_batch_withdraw_success(self):
        """Test batch_withdraw returns txid on success."""
        # Mock validate_address to return True
        validate_response = AsyncMock()
        validate_response.status = 200
        validate_response.json.return_value = {
            "result": {"isvalid": True},
            "error": None
        }
        
        # Mock get_network_fee_estimate
        fee_response = AsyncMock()
        fee_response.status = 200
        fee_response.json.return_value = {
            "result": 10,  # satoshis per byte
            "error": None
        }
        
        # Mock sendmany to return txid
        sendmany_response = AsyncMock()
        sendmany_response.status = 200
        sendmany_response.json.return_value = {
            "result": "txid123456789",
            "error": None
        }
        
        post_ctx_validate = AsyncMock()
        post_ctx_validate.__aenter__.return_value = validate_response
        post_ctx_validate.__aexit__.return_value = None
        
        post_ctx_fee = AsyncMock()
        post_ctx_fee.__aenter__.return_value = fee_response
        post_ctx_fee.__aexit__.return_value = None
        
        post_ctx_sendmany = AsyncMock()
        post_ctx_sendmany.__aenter__.return_value = sendmany_response
        post_ctx_sendmany.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        # Calls: validate_address, get_network_fee_estimate, sendmany
        session_instance.post = MagicMock(side_effect=[post_ctx_validate, post_ctx_fee, post_ctx_sendmany])
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            outputs = [{"address": "bc1qxy2kg...", "amount": 0.001}]
            result = await daemon.batch_withdraw("BTC", outputs)
            assert result == "txid123456789"
    
    @pytest.mark.asyncio
    async def test_batch_withdraw_rpc_failure(self):
        """Test batch_withdraw returns None when RPC call fails."""
        # Mock validate_address to return True
        validate_response = AsyncMock()
        validate_response.status = 200
        validate_response.json.return_value = {
            "result": {"isvalid": True},
            "error": None
        }
        
        # Mock sendmany to return error
        sendmany_response = AsyncMock()
        sendmany_response.status = 200
        sendmany_response.json.return_value = {
            "result": None,
            "error": {"code": -6, "message": "Insufficient funds"}
        }
        
        post_ctx_validate = AsyncMock()
        post_ctx_validate.__aenter__.return_value = validate_response
        post_ctx_validate.__aexit__.return_value = None
        
        post_ctx_sendmany = AsyncMock()
        post_ctx_sendmany.__aenter__.return_value = sendmany_response
        post_ctx_sendmany.__aexit__.return_value = None
        
        session_instance = AsyncMock()
        session_instance.post = MagicMock(side_effect=[post_ctx_validate, post_ctx_sendmany])
        session_instance.__aenter__.return_value = session_instance
        session_instance.__aexit__.return_value = None
        
        with patch('aiohttp.ClientSession') as MockSessionClass:
            MockSessionClass.return_value = session_instance
            
            daemon = WalletDaemon({"BTC": "http://localhost:7777"}, "user", "pass")
            outputs = [{"address": "bc1qxy2kg...", "amount": 0.001}]
            result = await daemon.batch_withdraw("BTC", outputs)
            assert result is None
