"""
Test suite for faucet get_jobs() implementations.
Tests that all faucets return valid Job objects with correct priorities and callable functions.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from core.config import BotSettings
from faucets.firefaucet import FireFaucetBot
from faucets.faucetcrypto import FaucetCryptoBot
from faucets.freebitcoin import FreeBitcoinBot
from faucets.dutchy import DutchyBot
from faucets.cointiply import CointiplyBot
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot


@pytest.fixture
def mock_settings():
    """Create mock bot settings."""
    return BotSettings()


@pytest.fixture
def mock_page():
    """Create mock Playwright page."""
    return AsyncMock()


def test_firefaucet_get_jobs(mock_settings, mock_page):
    """Test FireFaucetBot returns correct jobs."""
    bot = FireFaucetBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 4, "FireFaucet should have 4 jobs"
    
    # Check job names
    job_names = [job.name for job in jobs]
    assert "FireFaucet Claim" in job_names
    assert "FireFaucet Daily Bonus" in job_names
    assert "FireFaucet PTC" in job_names
    assert "FireFaucet Shortlinks" in job_names
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 2  # Daily Bonus
    assert jobs[2].priority == 3  # PTC
    assert jobs[3].priority == 4  # Shortlinks
    
    # Check functions are callable
    for job in jobs:
        assert callable(job.func)


def test_faucetcrypto_get_jobs(mock_settings, mock_page):
    """Test FaucetCryptoBot returns correct jobs."""
    bot = FaucetCryptoBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "FaucetCrypto should have 2 jobs (claim + PTC)"
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 3  # PTC
    
    # Check functions are callable
    for job in jobs:
        assert callable(job.func)


def test_freebitcoin_get_jobs(mock_settings, mock_page):
    """Test FreeBitcoinBot returns correct jobs."""
    bot = FreeBitcoinBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 1, "FreeBitcoin should have 1 job (claim only, no PTC)"
    
    # Check priority
    assert jobs[0].priority == 1
    assert "FreeBitcoin Claim" in jobs[0].name
    
    # Check function is callable
    assert callable(jobs[0].func)


def test_dutchy_get_jobs(mock_settings, mock_page):
    """Test DutchyBot returns correct jobs."""
    bot = DutchyBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 1, "Dutchy should have 1 job (claim includes rolls and shortlinks)"
    
    # Check priority
    assert jobs[0].priority == 1
    assert "DutchyCorp Claim" in jobs[0].name
    
    # Check function is callable
    assert callable(jobs[0].func)


def test_cointiply_get_jobs(mock_settings, mock_page):
    """Test CointiplyBot returns correct jobs."""
    bot = CointiplyBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "Cointiply should have 2 jobs (claim + PTC)"
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 3  # PTC
    
    # Check functions are callable
    for job in jobs:
        assert callable(job.func)


def test_coinpayu_get_jobs(mock_settings, mock_page):
    """Test CoinPayUBot returns correct jobs."""
    bot = CoinPayUBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "CoinPayU should have 2 jobs (claim + PTC)"
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 3  # PTC
    
    # Check functions are callable
    for job in jobs:
        assert callable(job.func)


def test_adbtc_get_jobs(mock_settings, mock_page):
    """Test AdBTCBot returns correct jobs."""
    bot = AdBTCBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "AdBTC should have 2 jobs (claim + PTC/surf)"
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 3  # PTC
    
    # Check functions are callable
    for job in jobs:
        assert callable(job.func)


def test_all_jobs_have_required_fields():
    """Test that all jobs have required fields."""
    mock_settings = BotSettings()
    mock_page = AsyncMock()
    
    bots = [
        FireFaucetBot(mock_settings, mock_page),
        FaucetCryptoBot(mock_settings, mock_page),
        FreeBitcoinBot(mock_settings, mock_page),
        DutchyBot(mock_settings, mock_page),
        CointiplyBot(mock_settings, mock_page),
        CoinPayUBot(mock_settings, mock_page),
        AdBTCBot(mock_settings, mock_page)
    ]
    
    for bot in bots:
        jobs = bot.get_jobs()
        for job in jobs:
            assert hasattr(job, 'priority')
            assert hasattr(job, 'next_run')
            assert hasattr(job, 'name')
            assert hasattr(job, 'func')
            assert hasattr(job, 'faucet_type')
            assert isinstance(job.priority, int)
            assert isinstance(job.name, str)
            assert callable(job.func)


def test_job_schedules_are_reasonable():
    """Test that initial job schedules are reasonable."""
    import time
    mock_settings = BotSettings()
    mock_page = AsyncMock()
    
    # Capture time BEFORE creating bot to avoid timing precision issues
    current_time = time.time()
    bot = FireFaucetBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    for job in jobs:
        # All jobs should be scheduled within the next hour (with 1 second tolerance for test execution time)
        assert job.next_run >= current_time - 1, f"Job {job.name} scheduled in the past"
        assert job.next_run <= current_time + 3600, f"Job {job.name} scheduled too far in future"
