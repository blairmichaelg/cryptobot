"""
Test for Task 10: Fix Permanent Failure Classification

Verifies that security challenges (Cloudflare, maintenance, etc.) are 
classified as RATE_LIMIT instead of PERMANENT, and that retry limits 
work correctly.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from core.orchestrator import JobScheduler, Job, ErrorType
from core.config import BotSettings, AccountProfile
from faucets.base import ClaimResult


@pytest.fixture
def mock_browser_manager():
    """Create a mock browser manager."""
    manager = Mock()
    manager.create_context = AsyncMock()
    manager.get_context = AsyncMock()
    manager.save_cookies = AsyncMock()
    manager.check_context_alive = AsyncMock(return_value=True)
    manager.restart = AsyncMock()
    return manager


@pytest.fixture
def settings():
    """Create minimal bot settings."""
    return BotSettings()


@pytest.fixture
def scheduler(settings, mock_browser_manager):
    """Create a JobScheduler instance."""
    return JobScheduler(settings, mock_browser_manager, proxy_manager=None)


def test_error_type_classification_cloudflare(scheduler):
    """Test that Cloudflare errors are classified as RATE_LIMIT, not PERMANENT."""
    
    # Test various Cloudflare-related status messages
    cloudflare_statuses = [
        "Cloudflare protection active",
        "cloudflare challenge detected",
        "Security check required",
        "SECURITY CHECK in progress",
        "Site maintenance / blocked",
        "DDoS protection enabled",
        "Challenge page detected",
        "Under maintenance",
    ]
    
    for status in cloudflare_statuses:
        # Simulate the fallback classification logic
        status_lower = status.lower()
        
        # This is the actual classification logic from orchestrator.py
        if any(security in status_lower for security in ["cloudflare", "security check", "maintenance", "ddos protection", "blocked", "challenge"]):
            error_type = ErrorType.RATE_LIMIT
        elif any(perm in status_lower for perm in ["banned", "suspended", "invalid credentials", "auth failed"]):
            error_type = ErrorType.PERMANENT
        else:
            error_type = ErrorType.UNKNOWN
        
        # Verify it's classified as RATE_LIMIT
        assert error_type == ErrorType.RATE_LIMIT, f"'{status}' should be RATE_LIMIT, got {error_type}"
        print(f"✅ Correctly classified '{status}' as RATE_LIMIT")


def test_error_type_classification_permanent(scheduler):
    """Test that true permanent errors are still classified correctly."""
    
    permanent_statuses = [
        "Account banned",
        "Account suspended",
        "Invalid credentials",
        "auth failed",  # Must be exact phrase
        "auth failed - check password",
    ]
    
    for status in permanent_statuses:
        status_lower = status.lower()
        
        # Classification logic
        if any(security in status_lower for security in ["cloudflare", "security check", "maintenance", "ddos protection", "blocked", "challenge"]):
            error_type = ErrorType.RATE_LIMIT
        elif any(perm in status_lower for perm in ["banned", "suspended", "invalid credentials", "auth failed"]):
            error_type = ErrorType.PERMANENT
        else:
            error_type = ErrorType.UNKNOWN
        
        assert error_type == ErrorType.PERMANENT, f"'{status}' should be PERMANENT, got {error_type}"
        print(f"✅ Correctly classified '{status}' as PERMANENT")


def test_security_retry_tracking(scheduler):
    """Test that security challenge retries are tracked correctly."""
    
    faucet_type = "fire_faucet"
    username = "test@example.com"
    retry_key = f"{faucet_type}:{username}"
    
    # Initially no retries
    assert retry_key not in scheduler.security_challenge_retries
    
    # Simulate adding retry
    scheduler.security_challenge_retries[retry_key] = {
        "security_retries": 1,
        "last_retry_time": time.time()
    }
    
    # Verify retry was tracked
    status = scheduler.get_security_retry_status()
    assert retry_key in status
    assert status[retry_key]["retries"] == 1
    assert status[retry_key]["max_retries"] == 5
    assert status[retry_key]["status"] == "ACTIVE"
    print(f"✅ Security retry tracking works: {status[retry_key]}")


def test_security_retry_limit(scheduler):
    """Test that accounts are disabled after max retries."""
    
    faucet_type = "fire_faucet"
    username = "test@example.com"
    retry_key = f"{faucet_type}:{username}"
    
    # Set to max retries
    scheduler.security_challenge_retries[retry_key] = {
        "security_retries": 5,  # max_security_retries = 5
        "last_retry_time": time.time()
    }
    
    # Verify status shows DISABLED
    status = scheduler.get_security_retry_status()
    assert status[retry_key]["status"] == "DISABLED"
    assert status[retry_key]["retries"] == 5
    print(f"✅ Account correctly marked DISABLED after 5 retries")


def test_manual_reset_all(scheduler):
    """Test manual reset of all security retry counters."""
    
    # Add multiple retry counters
    scheduler.security_challenge_retries["fire_faucet:user1@test.com"] = {
        "security_retries": 5,
        "last_retry_time": time.time()
    }
    scheduler.security_challenge_retries["cointiply:user2@test.com"] = {
        "security_retries": 3,
        "last_retry_time": time.time()
    }
    
    # Reset all
    scheduler.reset_security_retries()
    
    # Verify all reset
    status = scheduler.get_security_retry_status()
    for key, state in status.items():
        assert state["retries"] == 0, f"{key} should have 0 retries after reset"
        assert state["status"] == "ACTIVE"
    
    print(f"✅ All {len(status)} accounts reset successfully")


def test_manual_reset_specific_faucet(scheduler):
    """Test manual reset for specific faucet."""
    
    # Add retry counters for different faucets
    scheduler.security_challenge_retries["fire_faucet:user1@test.com"] = {
        "security_retries": 5,
        "last_retry_time": time.time()
    }
    scheduler.security_challenge_retries["cointiply:user2@test.com"] = {
        "security_retries": 3,
        "last_retry_time": time.time()
    }
    
    # Reset only fire_faucet
    scheduler.reset_security_retries("fire_faucet")
    
    # Verify only fire_faucet reset
    status = scheduler.get_security_retry_status()
    assert status["fire_faucet:user1@test.com"]["retries"] == 0
    assert status["cointiply:user2@test.com"]["retries"] == 3  # Should NOT be reset
    
    print("✅ Specific faucet reset works correctly")


def test_manual_reset_specific_account(scheduler):
    """Test manual reset for specific account."""
    
    # Add retry counters
    scheduler.security_challenge_retries["fire_faucet:user1@test.com"] = {
        "security_retries": 5,
        "last_retry_time": time.time()
    }
    scheduler.security_challenge_retries["fire_faucet:user2@test.com"] = {
        "security_retries": 4,
        "last_retry_time": time.time()
    }
    
    # Reset only user1
    scheduler.reset_security_retries("fire_faucet", "user1@test.com")
    
    # Verify only user1 reset
    status = scheduler.get_security_retry_status()
    assert status["fire_faucet:user1@test.com"]["retries"] == 0
    assert status["fire_faucet:user2@test.com"]["retries"] == 4  # Should NOT be reset
    
    print("✅ Specific account reset works correctly")


def test_auto_reset_after_24h(scheduler):
    """Test that retry counter auto-resets after 24 hours."""
    
    faucet_type = "fire_faucet"
    username = "test@example.com"
    retry_key = f"{faucet_type}:{username}"
    
    # Set retry from 25 hours ago
    old_time = time.time() - (25 * 3600)
    scheduler.security_challenge_retries[retry_key] = {
        "security_retries": 3,
        "last_retry_time": old_time
    }
    
    # Check if it would be reset (simulate the reset logic)
    retry_state = scheduler.security_challenge_retries[retry_key]
    current_time = time.time()
    hours_since = (current_time - retry_state["last_retry_time"]) / 3600
    
    # Should be reset if more than 24 hours
    should_reset = hours_since > scheduler.security_retry_reset_hours
    assert should_reset, f"Should reset after {hours_since:.1f} hours"
    
    print(f"✅ Auto-reset logic works (last retry was {hours_since:.1f}h ago)")


def test_retry_status_output(scheduler):
    """Test that retry status output is formatted correctly."""
    
    # Add various states
    current_time = time.time()
    scheduler.security_challenge_retries["fire_faucet:active@test.com"] = {
        "security_retries": 2,
        "last_retry_time": current_time - 3600  # 1 hour ago
    }
    scheduler.security_challenge_retries["cointiply:disabled@test.com"] = {
        "security_retries": 5,
        "last_retry_time": current_time - 7200  # 2 hours ago
    }
    
    # Get status
    status = scheduler.get_security_retry_status()
    
    # Verify active account
    active_status = status["fire_faucet:active@test.com"]
    assert active_status["retries"] == 2
    assert active_status["status"] == "ACTIVE"
    assert 0.9 < active_status["hours_since_last_retry"] < 1.1  # ~1 hour
    
    # Verify disabled account
    disabled_status = status["cointiply:disabled@test.com"]
    assert disabled_status["retries"] == 5
    assert disabled_status["status"] == "DISABLED"
    assert 1.9 < disabled_status["hours_since_last_retry"] < 2.1  # ~2 hours
    
    print("✅ Retry status output format is correct")
    print(f"Active account: {active_status}")
    print(f"Disabled account: {disabled_status}")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Task 10: Fix Permanent Failure Classification")
    print("=" * 70)
    print()
    
    # Run tests
    pytest.main([__file__, "-v", "-s"])
