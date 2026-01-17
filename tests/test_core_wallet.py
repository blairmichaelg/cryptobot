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
