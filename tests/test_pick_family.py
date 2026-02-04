"""
Comprehensive test suite for all 11 Pick.io family faucets.

This test suite verifies:
1. All 11 faucets can be imported and initialized
2. Each faucet inherits from PickFaucetBase correctly
3. Login method is available via inheritance
4. Registry loads all faucets correctly
5. All faucets have correct configuration (base_url, faucet_name)
6. get_balance(), get_timer(), and claim() methods are implemented
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from core.config import BotSettings
from core.registry import get_faucet_class, FAUCET_REGISTRY
from faucets.pick_base import PickFaucetBase


# All 11 Pick.io family faucets
PICK_FAUCETS = [
    ("litepick", "LitePickBot", "LitePick", "https://litepick.io", "LTC"),
    ("tronpick", "TronPickBot", "TronPick", "https://tronpick.io", "TRX"),
    ("dogepick", "DogePickBot", "DogePick", "https://dogepick.io", "DOGE"),
    ("bchpick", "BchPickBot", "BchPick", "https://bchpick.io", "BCH"),
    ("solpick", "SolPickBot", "SolPick", "https://solpick.io", "SOL"),
    ("tonpick", "TonPickBot", "TonPick", "https://tonpick.io", "TON"),
    ("polygonpick", "PolygonPickBot", "PolygonPick", "https://polygonpick.io", "MATIC"),
    ("binpick", "BinPickBot", "BinPick", "https://binpick.io", "BNB"),
    ("dashpick", "DashPickBot", "DashPick", "https://dashpick.io", "DASH"),
    ("ethpick", "EthPickBot", "EthPick", "https://ethpick.io", "ETH"),
    ("usdpick", "UsdPickBot", "UsdPick", "https://usdpick.io", "USDT"),
]


@pytest.fixture
def mock_settings():
    """Mock BotSettings for all Pick faucets."""
    settings = MagicMock(spec=BotSettings)
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_api_key"
    
    # Mock get_account to return credentials for any faucet
    def get_account_side_effect(faucet_name):
        return {
            "email": f"test_{faucet_name.lower()}@example.com",
            "password": "testpassword123"
        }
    settings.get_account.side_effect = get_account_side_effect
    
    return settings


@pytest.fixture
def mock_page():
    """Mock Playwright Page."""
    page = AsyncMock()
    page.title.return_value = "Pick Faucet"
    page.viewport_size = {"width": 1920, "height": 1080}
    page.url = "https://example.io"
    
    # Setup locator chain
    page.locator = MagicMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.locator.return_value.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.text_content = AsyncMock(return_value="")
    page.locator.return_value.first = MagicMock()
    page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.first.text_content = AsyncMock(return_value="")
    
    # Mock navigation
    page.goto = AsyncMock(return_value=MagicMock(ok=True, status=200))
    page.wait_for_load_state = AsyncMock()
    page.content = AsyncMock(return_value="<html></html>")
    
    return page


@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
def test_pick_registry_has_all_faucets(registry_key, class_name, faucet_name, base_url, coin):
    """Test that all 11 Pick faucets are registered in the registry."""
    assert registry_key in FAUCET_REGISTRY, f"{registry_key} not found in FAUCET_REGISTRY"
    
    # Verify the registry entry is a string path (lazy loading)
    registry_entry = FAUCET_REGISTRY[registry_key]
    assert isinstance(registry_entry, str), f"{registry_key} registry entry should be a string path"
    assert class_name in registry_entry, f"{class_name} not in registry path for {registry_key}"


@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
def test_pick_class_can_be_loaded(registry_key, class_name, faucet_name, base_url, coin):
    """Test that all 11 Pick faucet classes can be loaded from registry."""
    faucet_class = get_faucet_class(registry_key)
    assert faucet_class is not None, f"Failed to load {registry_key} from registry"
    assert faucet_class.__name__ == class_name, f"Expected {class_name}, got {faucet_class.__name__}"


@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
def test_pick_inherits_from_base(registry_key, class_name, faucet_name, base_url, coin):
    """Test that all 11 Pick faucets inherit from PickFaucetBase."""
    faucet_class = get_faucet_class(registry_key)
    assert issubclass(faucet_class, PickFaucetBase), f"{class_name} does not inherit from PickFaucetBase"


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
async def test_pick_initialization(registry_key, class_name, faucet_name, base_url, coin, mock_settings, mock_page):
    """Test that all 11 Pick faucets can be initialized correctly."""
    faucet_class = get_faucet_class(registry_key)
    bot = faucet_class(mock_settings, mock_page)
    
    # Verify correct initialization
    assert bot.faucet_name == faucet_name, f"Expected faucet_name={faucet_name}, got {bot.faucet_name}"
    assert bot.base_url == base_url, f"Expected base_url={base_url}, got {bot.base_url}"
    
    # Verify PickFaucetBase properties
    assert hasattr(bot, 'min_claim_amount'), f"{class_name} missing min_claim_amount"
    assert hasattr(bot, 'claim_interval_minutes'), f"{class_name} missing claim_interval_minutes"


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
async def test_pick_has_required_methods(registry_key, class_name, faucet_name, base_url, coin, mock_settings, mock_page):
    """Test that all 11 Pick faucets have required methods."""
    faucet_class = get_faucet_class(registry_key)
    bot = faucet_class(mock_settings, mock_page)
    
    # Verify required methods exist (from FaucetBot and PickFaucetBase)
    assert hasattr(bot, 'login'), f"{class_name} missing login method"
    assert hasattr(bot, 'get_balance'), f"{class_name} missing get_balance method"
    assert hasattr(bot, 'get_timer'), f"{class_name} missing get_timer method"
    assert hasattr(bot, 'claim'), f"{class_name} missing claim method"
    assert hasattr(bot, 'is_logged_in'), f"{class_name} missing is_logged_in method"
    
    # Verify methods are callable
    assert callable(bot.login), f"{class_name}.login is not callable"
    assert callable(bot.get_balance), f"{class_name}.get_balance is not callable"
    assert callable(bot.get_timer), f"{class_name}.get_timer is not callable"
    assert callable(bot.claim), f"{class_name}.claim is not callable"


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
async def test_pick_login_inherited(registry_key, class_name, faucet_name, base_url, coin, mock_settings, mock_page):
    """Test that login method is inherited from PickFaucetBase and can be called."""
    faucet_class = get_faucet_class(registry_key)
    bot = faucet_class(mock_settings, mock_page)
    
    # Mock necessary methods for login
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.human_type = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    # Mock is_logged_in to return True (simulate successful login)
    bot.is_logged_in = AsyncMock(return_value=True)
    
    # Call login - should not raise an error
    try:
        result = await bot.login()
        # If login completes without error, that's a success
        # (result may be True or False depending on mocks, but shouldn't crash)
        assert isinstance(result, bool), f"{class_name}.login() should return bool"
    except Exception as e:
        pytest.fail(f"{class_name}.login() raised unexpected exception: {e}")


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
async def test_pick_get_balance(registry_key, class_name, faucet_name, base_url, coin, mock_settings, mock_page):
    """Test get_balance method for all faucets."""
    faucet_class = get_faucet_class(registry_key)
    bot = faucet_class(mock_settings, mock_page)
    
    # Mock balance element
    balance_loc = AsyncMock()
    balance_loc.count.return_value = 1
    balance_loc.first.is_visible.return_value = True
    balance_loc.first.text_content.return_value = f"0.123 {coin}"
    
    # Make locator return our mock
    mock_page.locator.return_value = balance_loc
    
    balance = await bot.get_balance()
    assert isinstance(balance, str), f"{class_name}.get_balance() should return str"


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_key,class_name,faucet_name,base_url,coin", PICK_FAUCETS)
async def test_pick_get_timer(registry_key, class_name, faucet_name, base_url, coin, mock_settings, mock_page):
    """Test get_timer method for all faucets."""
    faucet_class = get_faucet_class(registry_key)
    bot = faucet_class(mock_settings, mock_page)
    
    # Mock timer element showing 30 minutes
    timer_loc = AsyncMock()
    timer_loc.count.return_value = 1
    timer_loc.first.text_content.return_value = "30:00"
    
    mock_page.locator.return_value = timer_loc
    
    timer = await bot.get_timer()
    assert isinstance(timer, (int, float)), f"{class_name}.get_timer() should return int or float"


@pytest.mark.asyncio
async def test_all_pick_faucets_count():
    """Verify we have exactly 11 Pick faucets in registry."""
    pick_keys = [key for key in FAUCET_REGISTRY.keys() if "pick" in key.lower()]
    
    # Should be exactly 11 (one for each faucet)
    assert len(pick_keys) == 11, f"Expected 11 Pick faucets in registry, found {len(pick_keys)}: {pick_keys}"


@pytest.mark.asyncio
async def test_pick_base_urls_unique():
    """Verify all Pick faucets have unique base URLs."""
    base_urls = set()
    
    for registry_key, class_name, faucet_name, base_url, coin in PICK_FAUCETS:
        assert base_url not in base_urls, f"Duplicate base URL: {base_url}"
        base_urls.add(base_url)
    
    assert len(base_urls) == 11, "All 11 Pick faucets should have unique base URLs"


@pytest.mark.asyncio
async def test_pick_coins_unique():
    """Verify all Pick faucets have unique coins."""
    coins = set()
    
    for registry_key, class_name, faucet_name, base_url, coin in PICK_FAUCETS:
        assert coin not in coins, f"Duplicate coin: {coin}"
        coins.add(coin)
    
    assert len(coins) == 11, "All 11 Pick faucets should have unique coins"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
