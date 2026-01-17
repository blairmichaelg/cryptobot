"""
Test suite for faucet get_jobs() implementations.
Tests that all faucets return valid Job objects with correct priorities and job types.
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
    
    assert len(jobs) == 5, "FireFaucet should have 5 jobs"
    
    # Check job names
    job_names = [job.name for job in jobs]
    assert "FireFaucet Claim" in job_names
    assert "FireFaucet Daily Bonus" in job_names
    assert "FireFaucet PTC" in job_names
    assert "FireFaucet Shortlinks" in job_names
    assert "FireFaucet Withdraw" in job_names
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 2  # Daily Bonus
    assert jobs[2].priority == 3  # PTC
    assert jobs[3].priority == 4  # Shortlinks
    assert jobs[4].priority == 5  # Withdraw
    
    # Check job types exist on bot
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)
        assert callable(getattr(bot, job.job_type))


def test_faucetcrypto_get_jobs(mock_settings, mock_page):
    """Test FaucetCryptoBot returns correct jobs."""
    bot = FaucetCryptoBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3, "FaucetCrypto should have 3 jobs (claim + PTC + withdraw)"
    
    # Check priorities
    assert jobs[0].priority == 1  # Claim
    assert jobs[1].priority == 5  # Withdraw
    assert jobs[2].priority == 3  # PTC
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


def test_freebitcoin_get_jobs(mock_settings, mock_page):
    """Test FreeBitcoinBot returns correct jobs."""
    bot = FreeBitcoinBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "FreeBitcoin should have 2 jobs (claim + withdraw)"
    
    assert jobs[0].priority == 1
    assert "FreeBitcoin Claim" in jobs[0].name
    assert jobs[1].priority == 5
    assert "FreeBitcoin Withdraw" in jobs[1].name
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


def test_dutchy_get_jobs(mock_settings, mock_page):
    """Test DutchyBot returns correct jobs."""
    bot = DutchyBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2, "Dutchy should have 2 jobs (claim + withdraw)"
    
    assert jobs[0].priority == 1
    assert "DutchyCorp Claim" in jobs[0].name
    assert jobs[1].priority == 5
    assert "DutchyCorp Withdraw" in jobs[1].name
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


def test_cointiply_get_jobs(mock_settings, mock_page):
    """Test CointiplyBot returns correct jobs."""
    bot = CointiplyBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3, "Cointiply should have 3 jobs (claim + PTC + withdraw)"
    
    assert jobs[0].priority == 1
    assert jobs[1].priority == 5
    assert jobs[2].priority == 3
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


def test_coinpayu_get_jobs(mock_settings, mock_page):
    """Test CoinPayUBot returns correct jobs."""
    bot = CoinPayUBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 4, "CoinPayU should have 4 jobs (claim + PTC + consolidate + withdraw)"
    
    assert jobs[0].priority == 1
    assert jobs[1].priority == 3
    assert jobs[2].priority == 4
    assert jobs[3].priority == 5
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


def test_adbtc_get_jobs(mock_settings, mock_page):
    """Test AdBTCBot returns correct jobs."""
    bot = AdBTCBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3, "AdBTC should have 3 jobs (claim + surf + withdraw)"
    
    assert jobs[0].priority == 1
    assert jobs[1].priority == 5
    assert jobs[2].priority == 2
    
    for job in jobs:
        assert isinstance(job.job_type, str)
        assert hasattr(bot, job.job_type)


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
            assert hasattr(job, 'job_type')
            assert hasattr(job, 'faucet_type')
            assert isinstance(job.priority, int)
            assert isinstance(job.name, str)
            assert isinstance(job.job_type, str)
            assert hasattr(bot, job.job_type)


def test_job_schedules_are_reasonable():
    """Test that initial job schedules are reasonable."""
    import time
    mock_settings = BotSettings()
    mock_page = AsyncMock()
    
    current_time = time.time()
    bot = FireFaucetBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    for job in jobs:
        assert job.next_run >= current_time - 1, f"Job {job.name} scheduled in the past"
        # Increased limit for daily bonus/withdraw/shortlinks which might be scheduled later
        assert job.next_run <= current_time + 86400, f"Job {job.name} scheduled too far in future"
