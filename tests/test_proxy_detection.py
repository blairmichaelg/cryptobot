"""
Test suite for proxy detection and rotation functionality.
Tests proxy detection patterns, rotation strategies, pool exhaustion, and residential proxy handling.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from core.orchestrator import JobScheduler, Job
from core.config import BotSettings, AccountProfile
from faucets.base import FaucetBot, ClaimResult
from playwright.async_api import Page


@pytest.fixture
def mock_settings():
    """Create mock bot settings."""
    return BotSettings()


@pytest.fixture
def mock_browser_manager():
    """Create mock browser manager."""
    manager = AsyncMock()
    manager.create_context = AsyncMock(return_value=AsyncMock())
    manager.new_page = AsyncMock(return_value=AsyncMock())
    return manager


@pytest.fixture
def mock_page():
    """Create mock Playwright page."""
    page = AsyncMock(spec=Page)
    page.content = AsyncMock(return_value="<html><body>Test content</body></html>")
    page.url = "https://test.com"
    return page


@pytest.mark.asyncio
async def test_proxy_detection_patterns(mock_settings, mock_page):
    """Test that all proxy detection patterns are recognized."""
    bot = FaucetBot(mock_settings, mock_page)
    
    proxy_patterns = [
        "proxy detected",
        "vpn detected",
        "suspicious activity",
        "datacenter ip",
        "hosting provider",
        "please disable your proxy",
        "access denied",
        "forbidden",
        "your ip has been flagged",
        "unusual traffic"
    ]
    
    for pattern in proxy_patterns:
        mock_page.content = AsyncMock(return_value=f"<html><body>{pattern.upper()}</body></html>")
        result = await bot.check_failure_states()
        assert result == "Proxy Detected", f"Failed to detect pattern: {pattern}"


@pytest.mark.asyncio
async def test_account_ban_detection(mock_settings, mock_page):
    """Test that account ban patterns are recognized."""
    bot = FaucetBot(mock_settings, mock_page)
    
    ban_patterns = [
        "account banned",
        "account suspended",
        "account disabled",
        "account locked",
        "permanently banned",
        "violation of terms"
    ]
    
    for pattern in ban_patterns:
        mock_page.content = AsyncMock(return_value=f"<html><body>{pattern.upper()}</body></html>")
        result = await bot.check_failure_states()
        assert result == "Account Banned", f"Failed to detect pattern: {pattern}"


@pytest.mark.asyncio
async def test_maintenance_detection(mock_settings, mock_page):
    """Test that maintenance patterns are recognized."""
    bot = FaucetBot(mock_settings, mock_page)
    
    maintenance_patterns = [
        "maintenance",
        "under maintenance",
        "temporarily unavailable",
        "checking your browser",
        "cloudflare",
        "ddos protection",
        "security check"
    ]
    
    for pattern in maintenance_patterns:
        mock_page.content = AsyncMock(return_value=f"<html><body>{pattern.upper()}</body></html>")
        result = await bot.check_failure_states()
        assert result == "Site Maintenance / Blocked", f"Failed to detect pattern: {pattern}"


@pytest.mark.asyncio
async def test_proxy_rotation_round_robin(mock_settings, mock_browser_manager):
    """Test round-robin proxy rotation strategy."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy_pool=["proxy1", "proxy2", "proxy3"],
        proxy_rotation_strategy="round_robin"
    )
    
    # Get proxies in sequence
    proxy1 = scheduler.get_next_proxy(profile)
    proxy2 = scheduler.get_next_proxy(profile)
    proxy3 = scheduler.get_next_proxy(profile)
    proxy4 = scheduler.get_next_proxy(profile)  # Should wrap around
    
    assert proxy1 == "proxy1"
    assert proxy2 == "proxy2"
    assert proxy3 == "proxy3"
    assert proxy4 == "proxy1"  # Wrapped around


@pytest.mark.asyncio
async def test_proxy_rotation_random(mock_settings, mock_browser_manager):
    """Test random proxy rotation strategy."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy_pool=["proxy1", "proxy2", "proxy3"],
        proxy_rotation_strategy="random"
    )
    
    # Get multiple proxies
    proxies = [scheduler.get_next_proxy(profile) for _ in range(10)]
    
    # Should get proxies from the pool
    assert all(p in profile.proxy_pool for p in proxies)
    # Should have some variation (not all the same)
    assert len(set(proxies)) > 1


@pytest.mark.asyncio
async def test_proxy_rotation_health_based(mock_settings, mock_browser_manager):
    """Test health-based proxy rotation strategy."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy_pool=["proxy1", "proxy2", "proxy3"],
        proxy_rotation_strategy="health_based"
    )
    
    # Record failures for proxy2
    scheduler.record_proxy_failure("proxy2")
    scheduler.record_proxy_failure("proxy2")
    
    # Should prefer proxy1 or proxy3 (healthier)
    proxy = scheduler.get_next_proxy(profile)
    assert proxy in ["proxy1", "proxy3"]


@pytest.mark.asyncio
async def test_proxy_pool_exhaustion(mock_settings, mock_browser_manager):
    """Test handling when all proxies in pool have failed."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy="fallback_proxy",
        proxy_pool=["proxy1", "proxy2"],
        proxy_rotation_strategy="round_robin"
    )
    
    # Mark all proxies as failed recently
    for proxy in profile.proxy_pool:
        for _ in range(3):
            scheduler.record_proxy_failure(proxy)
    
    # Should fall back to single proxy
    proxy = scheduler.get_next_proxy(profile)
    assert proxy == "fallback_proxy"


@pytest.mark.asyncio
async def test_proxy_failure_recording(mock_settings, mock_browser_manager):
    """Test that proxy failures are recorded correctly."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    proxy = "test_proxy"
    
    # Record multiple failures
    scheduler.record_proxy_failure(proxy)
    scheduler.record_proxy_failure(proxy)
    scheduler.record_proxy_failure(proxy)
    
    # Check failure count
    assert scheduler.proxy_failures[proxy]['failures'] == 3
    assert scheduler.proxy_failures[proxy]['last_failure_time'] > 0


@pytest.mark.asyncio
async def test_proxy_rotation_on_detection(mock_settings, mock_browser_manager):
    """Test that proxy is rotated when detection occurs."""
    scheduler = JobScheduler(mock_settings, mock_browser_manager)
    
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy_pool=["proxy1", "proxy2"],
        proxy_rotation_strategy="round_robin"
    )
    
    async def job_with_proxy_detection(page):
        return ClaimResult(success=False, status="Proxy Detected", next_claim_minutes=0)
    
    job = Job(
        priority=1,
        next_run=time.time(),
        name="Test Job",
        profile=profile,
        func=job_with_proxy_detection,
        faucet_type="test"
    )
    
    # Execute job (will detect proxy)
    await scheduler._run_job_wrapper(job)
    
    # Check that proxy failure was recorded
    # The first proxy used should have a failure recorded
    assert len(scheduler.proxy_failures) > 0


@pytest.mark.asyncio
async def test_residential_proxy_flag(mock_settings, mock_browser_manager):
    """Test that residential proxy flag is properly set."""
    profile = AccountProfile(
        faucet="test",
        username="test_user",
        password="test_pass",
        proxy="residential_proxy",
        residential_proxy=True
    )
    
    assert profile.residential_proxy is True
    assert profile.proxy == "residential_proxy"
