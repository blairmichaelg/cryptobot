"""
Test error classification and recovery system.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from core.orchestrator import ErrorType, JobScheduler
from faucets.base import FaucetBot, ClaimResult
from core.config import BotSettings, AccountProfile


class TestErrorClassification:
    """Test the error classification system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.settings = BotSettings()
        self.page = AsyncMock()
        self.bot = FaucetBot(self.settings, self.page)
    
    def test_classify_error_permanent_banned(self):
        """Test classification of permanent errors - banned account."""
        page_content = "<html><body>Your account has been banned</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PERMANENT
    
    def test_classify_error_permanent_suspended(self):
        """Test classification of permanent errors - suspended account."""
        page_content = "<html><body>Account suspended due to violations</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PERMANENT
    
    def test_classify_error_permanent_invalid_credentials(self):
        """Test classification of permanent errors - invalid credentials."""
        page_content = "<html><body>Invalid credentials. Please check your password.</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PERMANENT
    
    def test_classify_error_rate_limit_status_429(self):
        """Test classification of rate limit - HTTP 429."""
        error_type = self.bot.classify_error(None, None, 429)
        assert error_type == ErrorType.RATE_LIMIT
    
    def test_classify_error_rate_limit_too_many_requests(self):
        """Test classification of rate limit - too many requests message."""
        page_content = "<html><body>Too many requests. Please slow down.</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.RATE_LIMIT
    
    def test_classify_error_rate_limit_cloudflare(self):
        """Test classification of rate limit - Cloudflare challenge."""
        page_content = "<html><body>Checking your browser... Cloudflare</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.RATE_LIMIT
    
    def test_classify_error_proxy_issue_detected(self):
        """Test classification of proxy issues - proxy detected."""
        page_content = "<html><body>Proxy detected. Please disable VPN.</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PROXY_ISSUE
    
    def test_classify_error_proxy_issue_vpn(self):
        """Test classification of proxy issues - VPN detected."""
        page_content = "<html><body>VPN detected. Access denied.</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PROXY_ISSUE
    
    def test_classify_error_proxy_issue_bot_detected(self):
        """Test classification of proxy issues - bot detected."""
        page_content = "<html><body>Bot detected. Automated access is prohibited.</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.PROXY_ISSUE
    
    def test_classify_error_faucet_down_500(self):
        """Test classification of faucet down - HTTP 500."""
        error_type = self.bot.classify_error(None, None, 500)
        assert error_type == ErrorType.FAUCET_DOWN
    
    def test_classify_error_faucet_down_503(self):
        """Test classification of faucet down - HTTP 503."""
        error_type = self.bot.classify_error(None, None, 503)
        assert error_type == ErrorType.FAUCET_DOWN
    
    def test_classify_error_transient_timeout(self):
        """Test classification of transient errors - timeout."""
        exception = Exception("Connection timed out")
        error_type = self.bot.classify_error(exception, None, None)
        assert error_type == ErrorType.TRANSIENT
    
    def test_classify_error_transient_connection_reset(self):
        """Test classification of transient errors - connection reset."""
        exception = Exception("Connection reset by peer")
        error_type = self.bot.classify_error(exception, None, None)
        assert error_type == ErrorType.TRANSIENT
    
    def test_classify_error_captcha_failed(self):
        """Test classification of captcha failures."""
        exception = Exception("Captcha solve failed: timeout")
        error_type = self.bot.classify_error(exception, None, None)
        assert error_type == ErrorType.CAPTCHA_FAILED
    
    def test_classify_error_unknown(self):
        """Test classification of unknown errors."""
        page_content = "<html><body>Some random error</body></html>"
        error_type = self.bot.classify_error(None, page_content, None)
        assert error_type == ErrorType.UNKNOWN


class TestRecoveryStrategies:
    """Test the recovery strategies for different error types."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.settings = BotSettings()
        self.browser_manager = Mock()
        self.proxy_manager = Mock()
        self.proxy_manager.proxies = ["proxy1", "proxy2", "proxy3"]  # Mock proxies list
        self.scheduler = JobScheduler(self.settings, self.browser_manager, self.proxy_manager)
    
    def test_recovery_transient_immediate_retry(self):
        """Test recovery for transient errors - immediate retry."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.TRANSIENT, 0, "proxy")
        assert delay == 0
        assert "immediately" in action.lower()
    
    def test_recovery_transient_requeue_after_retry(self):
        """Test recovery for transient errors - requeue after retry."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.TRANSIENT, 1, "proxy")
        assert delay == 300  # 5 minutes
        assert "5min" in action.lower()
    
    def test_recovery_rate_limit_exponential_backoff(self):
        """Test recovery for rate limit - exponential backoff."""
        # First retry: 10 minutes
        delay1, action1 = self.scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 0, "proxy")
        assert delay1 == 600
        assert "10min" in action1.lower()
        
        # Second retry: 30 minutes
        delay2, action2 = self.scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 1, "proxy")
        assert delay2 == 1800
        assert "30min" in action2.lower()
        
        # Third retry: 2 hours
        delay3, action3 = self.scheduler._get_recovery_delay(ErrorType.RATE_LIMIT, 2, "proxy")
        assert delay3 == 7200
        assert "120min" in action3.lower()
    
    def test_recovery_proxy_issue_rotate(self):
        """Test recovery for proxy issues - rotate proxy."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.PROXY_ISSUE, 0, "proxy")
        assert delay == 1800  # 30 minutes
        assert "rotate" in action.lower() or "30min" in action.lower()
    
    def test_recovery_permanent_no_requeue(self):
        """Test recovery for permanent errors - no requeue."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.PERMANENT, 0, "proxy")
        assert delay == float('inf')
        assert "permanent" in action.lower() or "disabled" in action.lower()
    
    def test_recovery_faucet_down_4_hours(self):
        """Test recovery for faucet down - 4 hours."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.FAUCET_DOWN, 0, "proxy")
        assert delay == 14400  # 4 hours
        assert "4" in action.lower() and "hour" in action.lower()
    
    def test_recovery_captcha_failed_15_min(self):
        """Test recovery for captcha failures - 15 minutes."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.CAPTCHA_FAILED, 0, "proxy")
        assert delay == 900  # 15 minutes
        assert "15min" in action.lower()
    
    def test_recovery_unknown_default_delay(self):
        """Test recovery for unknown errors - default delay."""
        delay, action = self.scheduler._get_recovery_delay(ErrorType.UNKNOWN, 0, "proxy")
        assert delay == 600  # 10 minutes
        assert "10min" in action.lower()


class TestCircuitBreaker:
    """Test the enhanced circuit breaker logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.settings = BotSettings()
        self.browser_manager = Mock()
        self.proxy_manager = Mock()
        self.proxy_manager.proxies = ["proxy1", "proxy2", "proxy3"]  # Mock proxies list
        self.scheduler = JobScheduler(self.settings, self.browser_manager, self.proxy_manager)
    
    def test_circuit_breaker_not_trip_on_transient(self):
        """Test that transient errors don't trip circuit breaker."""
        should_trip = self.scheduler._should_trip_circuit_breaker("test_faucet", ErrorType.TRANSIENT)
        assert should_trip is False
    
    def test_circuit_breaker_trip_on_permanent(self):
        """Test that permanent errors trip circuit breaker."""
        should_trip = self.scheduler._should_trip_circuit_breaker("test_faucet", ErrorType.PERMANENT)
        assert should_trip is True
    
    def test_circuit_breaker_proxy_issue_repeated(self):
        """Test that repeated proxy issues trip circuit breaker."""
        faucet = "test_faucet"
        
        # First proxy error - should not trip
        self.scheduler._track_error_type(faucet, ErrorType.PROXY_ISSUE)
        should_trip1 = self.scheduler._should_trip_circuit_breaker(faucet, ErrorType.PROXY_ISSUE)
        assert should_trip1 is False
        
        # Second proxy error - should not trip
        self.scheduler._track_error_type(faucet, ErrorType.PROXY_ISSUE)
        should_trip2 = self.scheduler._should_trip_circuit_breaker(faucet, ErrorType.PROXY_ISSUE)
        assert should_trip2 is False
        
        # Third proxy error - should trip
        self.scheduler._track_error_type(faucet, ErrorType.PROXY_ISSUE)
        should_trip3 = self.scheduler._should_trip_circuit_breaker(faucet, ErrorType.PROXY_ISSUE)
        assert should_trip3 is True
    
    def test_error_type_tracking_limit(self):
        """Test that error type tracking is limited to 10 recent errors."""
        faucet = "test_faucet"
        
        # Add 15 errors
        for _ in range(15):
            self.scheduler._track_error_type(faucet, ErrorType.TRANSIENT)
        
        # Should only keep last 10
        assert len(self.scheduler.faucet_error_types[faucet]) == 10


@pytest.mark.asyncio
async def test_claim_wrapper_error_classification():
    """Test that claim_wrapper properly classifies errors."""
    settings = BotSettings()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Account banned</body></html>")
    
    bot = FaucetBot(settings, page)
    bot.login_wrapper = AsyncMock(return_value=False)
    
    result = await bot.claim_wrapper(page)
    
    assert result.success is False
    assert result.error_type == ErrorType.PERMANENT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
