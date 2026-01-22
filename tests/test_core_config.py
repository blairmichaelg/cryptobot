import pytest
import os
from core.config import BotSettings, AccountProfile

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "mock_key")
    monkeypatch.setenv("FIREFAUCET_USERNAME", "fire_user")
    monkeypatch.setenv("FIREFAUCET_PASSWORD", "fire_pass")
    monkeypatch.setenv("COINTIPLY_USERNAME", "coin_user")
    monkeypatch.setenv("COINTIPLY_PASSWORD", "coin_pass")
    monkeypatch.setenv("FAUCETCRYPTO_USERNAME", "faucet_user")
    monkeypatch.setenv("FAUCETCRYPTO_PASSWORD", "faucet_pass")
    monkeypatch.setenv("FREEBITCOIN_USERNAME", "free_user")
    monkeypatch.setenv("FREEBITCOIN_PASSWORD", "free_pass")

def test_bot_settings_init(mock_env):
    settings = BotSettings()
    assert settings.twocaptcha_api_key == "mock_key"
    assert settings.firefaucet_username == "fire_user"
    assert settings.cointiply_password == "coin_pass"
    # wallet_rpc_urls is now a dict with default values
    assert settings.wallet_rpc_urls["BTC"] == "http://127.0.0.1:7777"
    assert settings.captcha_provider == "2captcha"

def test_get_account(mock_env):
    settings = BotSettings()
    account = settings.get_account("firefaucet")
    assert account is not None
    assert account["username"] == "fire_user"
    assert account["password"] == "fire_pass"


class TestAccountProfile:
    """Test suite for AccountProfile model."""
    
    def test_account_profile_creation(self):
        """Test AccountProfile can be created with required fields."""
        profile = AccountProfile(faucet="test_faucet", username="test_user", password="test_pass")
        assert profile.faucet == "test_faucet"
        assert profile.username == "test_user"
        assert profile.password == "test_pass"
        assert profile.proxy is None
        assert profile.enabled is True
    
    def test_account_profile_with_proxy(self):
        """Test AccountProfile with proxy."""
        profile = AccountProfile(
            faucet="test", 
            username="user", 
            password="pass", 
            proxy="http://proxy:8080"
        )
        assert profile.proxy == "http://proxy:8080"
    
    def test_account_profile_disabled(self):
        """Test AccountProfile can be disabled."""
        profile = AccountProfile(
            faucet="test", 
            username="user", 
            password="pass", 
            enabled=False
        )
        assert profile.enabled is False


class TestBotSettingsConfiguration:
    """Test suite for BotSettings configuration fields."""
    
    def test_default_values(self):
        """Test BotSettings has correct default values."""
        settings = BotSettings()
        assert settings.log_level == "INFO"
        assert settings.headless is True
        assert settings.captcha_provider == "2captcha"
        assert settings.block_images is True
        assert settings.block_media is True
        assert settings.max_concurrent_bots == 3
        assert settings.max_concurrent_per_profile == 1
        assert settings.scheduler_tick_rate == 1.0
        assert settings.exploration_frequency_minutes == 30
        assert len(settings.user_agents) == 100  # fake_useragent generates 100 UAs
        # Check enabled_faucets includes core ones
        expected_faucets = ["fire_faucet", "cointiply", "dutchy", "litepick", "tronpick", 
                           "dogepick", "solpick", "binpick", "bchpick", "tonpick", 
                           "polygonpick", "dashpick", "ethpick", "usdpick"]
        assert settings.enabled_faucets == expected_faucets
    
    def test_capsolver_api_key(self, monkeypatch):
        """Test CapSolver API key configuration."""
        monkeypatch.setenv("CAPSOLVER_API_KEY", "capsolver_test_key")
        settings = BotSettings()
        assert settings.capsolver_api_key == "capsolver_test_key"
    
    def test_custom_concurrency_settings(self, monkeypatch):
        """Test custom concurrency settings."""
        monkeypatch.setenv("MAX_CONCURRENT_BOTS", "5")
        monkeypatch.setenv("MAX_CONCURRENT_PER_PROFILE", "2")
        settings = BotSettings()
        assert settings.max_concurrent_bots == 5
        assert settings.max_concurrent_per_profile == 2
    
    def test_custom_user_agents(self, monkeypatch):
        """Test custom user agents configuration."""
        import json
        custom_agents = ["Agent 1", "Agent 2"]
        monkeypatch.setenv("USER_AGENTS", json.dumps(custom_agents))
        settings = BotSettings()
        assert settings.user_agents == custom_agents
    
    def test_wallet_addresses(self, monkeypatch):
        """Test wallet addresses configuration."""
        import json
        addresses = {"BTC": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "LTC": "LTC_ADDRESS"}
        monkeypatch.setenv("WALLET_ADDRESSES", json.dumps(addresses))
        settings = BotSettings()
        assert settings.wallet_addresses == addresses
    
    def test_dutchy_credentials(self, monkeypatch):
        """Test Dutchy credentials configuration."""
        monkeypatch.setenv("DUTCHY_USERNAME", "dutchy_user")
        monkeypatch.setenv("DUTCHY_PASSWORD", "dutchy_pass")
        settings = BotSettings()
        assert settings.dutchy_username == "dutchy_user"
        assert settings.dutchy_password == "dutchy_pass"


class TestGetAccountMethod:
    """Test suite for BotSettings.get_account() method."""
    
    def test_get_account_from_profiles(self):
        """Test get_account retrieves from accounts list."""
        profile1 = AccountProfile(faucet="firefaucet", username="profile_user", password="profile_pass")
        profile2 = AccountProfile(faucet="cointiply", username="coin_profile", password="coin_pass")
        
        settings = BotSettings(accounts=[profile1, profile2])
        
        account = settings.get_account("firefaucet")
        assert account is not None
        assert account["username"] == "profile_user"
        assert account["password"] == "profile_pass"
        assert account["proxy"] is None
    
    def test_get_account_with_proxy(self):
        """Test get_account includes proxy from profile."""
        profile = AccountProfile(
            faucet="test", 
            username="user", 
            password="pass", 
            proxy="http://proxy:8080"
        )
        settings = BotSettings(accounts=[profile])
        
        account = settings.get_account("test")
        assert account["proxy"] == "http://proxy:8080"
    
    def test_get_account_disabled_profile_skipped(self):
        """Test get_account skips disabled profiles."""
        profile1 = AccountProfile(faucet="test", username="user1", password="pass1", enabled=False)
        profile2 = AccountProfile(faucet="test", username="user2", password="pass2", enabled=True)
        
        settings = BotSettings(accounts=[profile1, profile2])
        
        account = settings.get_account("test")
        assert account is not None
        assert account["username"] == "user2"  # Should get enabled profile
    
    def test_get_account_case_insensitive(self):
        """Test get_account is case-insensitive."""
        profile = AccountProfile(faucet="FireFaucet", username="user", password="pass")
        settings = BotSettings(accounts=[profile])
        
        # Try different cases
        assert settings.get_account("firefaucet") is not None
        assert settings.get_account("FIREFAUCET") is not None
        assert settings.get_account("FireFaucet") is not None
    
    def test_get_account_fallback_to_legacy_firefaucet(self, monkeypatch):
        """Test get_account falls back to legacy firefaucet credentials."""
        monkeypatch.setenv("FIREFAUCET_USERNAME", "legacy_fire")
        monkeypatch.setenv("FIREFAUCET_PASSWORD", "legacy_pass")
        
        settings = BotSettings()  # No accounts list
        account = settings.get_account("fire_faucet")
        
        assert account is not None
        assert account["username"] == "legacy_fire"
        assert account["password"] == "legacy_pass"
    
    def test_get_account_fallback_to_legacy_cointiply(self, monkeypatch):
        """Test get_account falls back to legacy cointiply credentials."""
        monkeypatch.setenv("COINTIPLY_USERNAME", "legacy_coin")
        monkeypatch.setenv("COINTIPLY_PASSWORD", "legacy_coin_pass")
        
        settings = BotSettings()
        account = settings.get_account("cointiply")
        
        assert account is not None
        assert account["username"] == "legacy_coin"
        assert account["password"] == "legacy_coin_pass"
    
    def test_get_account_fallback_to_legacy_freebitcoin(self, monkeypatch):
        """Test get_account falls back to legacy freebitcoin credentials."""
        monkeypatch.setenv("FREEBITCOIN_USERNAME", "legacy_free")
        monkeypatch.setenv("FREEBITCOIN_PASSWORD", "legacy_free_pass")
        
        settings = BotSettings()
        account = settings.get_account("freebitcoin")
        
        assert account is not None
        assert account["username"] == "legacy_free"
        assert account["password"] == "legacy_free_pass"
    
    def test_get_account_fallback_to_legacy_dutchy(self, monkeypatch):
        """Test get_account falls back to legacy dutchy credentials."""
        monkeypatch.setenv("DUTCHY_USERNAME", "legacy_dutchy")
        monkeypatch.setenv("DUTCHY_PASSWORD", "legacy_dutchy_pass")
        
        settings = BotSettings()
        account = settings.get_account("dutchy")
        
        assert account is not None
        assert account["username"] == "legacy_dutchy"
        assert account["password"] == "legacy_dutchy_pass"
    
    def test_get_account_profiles_take_priority_over_legacy(self, monkeypatch):
        """Test that accounts list takes priority over legacy credentials."""
        monkeypatch.setenv("FIREFAUCET_USERNAME", "legacy_user")
        monkeypatch.setenv("FIREFAUCET_PASSWORD", "legacy_pass")
        
        profile = AccountProfile(faucet="firefaucet", username="profile_user", password="profile_pass")
        settings = BotSettings(accounts=[profile])
        
        account = settings.get_account("firefaucet")
        assert account["username"] == "profile_user"  # Should use profile, not legacy
    
    def test_get_account_no_match_returns_none(self):
        """Test get_account returns None when no match found."""
        settings = BotSettings()
        account = settings.get_account("nonexistent_faucet")
        assert account is None
    
    def test_get_account_underscore_normalization(self):
        """Test get_account normalizes underscores in faucet names."""
        profile = AccountProfile(faucet="firefaucet", username="user", password="pass")
        settings = BotSettings(accounts=[profile])
        
        # Should match even with underscores
        account = settings.get_account("fire_faucet")
        assert account is not None
        assert account["username"] == "user"
