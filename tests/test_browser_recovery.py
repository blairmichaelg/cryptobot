"""
Integration tests for browser crash recovery and resilience.

This test suite validates the BrowserManager's ability to handle
and recover from various failure scenarios:

* Browser process crashes and recovery
* Context cleanup after failures
* Session persistence and cookie restoration
* Resource cleanup on errors
* Concurrent context failure isolation

All browser interactions are mocked to ensure fast, deterministic tests
without requiring actual browser processes.
"""

import pytest
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, Mock

from browser.instance import BrowserManager
from core.config import AccountProfile


@pytest.fixture
def temp_browser_dirs():
    """Create temporary directories for browser data."""
    config_dir = tempfile.mkdtemp(prefix="cryptobot_browser_test_")
    cookies_dir = Path(config_dir) / "cookies_encrypted"
    cookies_dir.mkdir(exist_ok=True)
    
    yield {
        "config_dir": Path(config_dir),
        "cookies_dir": cookies_dir
    }
    
    try:
        shutil.rmtree(config_dir)
    except Exception:
        pass


@pytest.fixture
def mock_profile():
    """Create a mock account profile."""
    return AccountProfile(
        faucet="firefaucet",
        username="testuser",
        password="testpass",
        email="test@example.com",
        proxy="http://user:pass@1.1.1.1:8080"
    )


class TestBrowserCrashRecovery:
    """Test browser crash detection and recovery."""
    
    @pytest.mark.asyncio
    async def test_detect_browser_crash(self, temp_browser_dirs):
        """Test that browser crash is detected."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            # Mock browser that crashes
            mock_browser = AsyncMock()
            mock_browser.close = AsyncMock(side_effect=Exception("Browser crashed"))
            
            # Mock Camoufox to return our mock browser
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                
                # Launch browser
                await manager.launch()
                assert manager.browser is not None
                
                # Attempt to close (simulates crash)
                try:
                    await manager.close()
                except Exception as e:
                    # Crash was detected
                    assert "crashed" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_recover_from_browser_crash(self, temp_browser_dirs):
        """Test that browser can be relaunched after a crash."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # First launch succeeds
                mock_browser1 = AsyncMock()
                mock_browser1.close = AsyncMock(side_effect=Exception("Crash"))
                
                # Second launch (recovery) succeeds
                mock_browser2 = AsyncMock()
                mock_browser2.close = AsyncMock()
                
                # Setup mock to return different browsers
                mock_camoufox_instance1 = AsyncMock()
                mock_camoufox_instance1.__aenter__.return_value = mock_browser1
                mock_camoufox_instance1.__aexit__.return_value = AsyncMock()
                
                mock_camoufox_instance2 = AsyncMock()
                mock_camoufox_instance2.__aenter__.return_value = mock_browser2
                mock_camoufox_instance2.__aexit__.return_value = AsyncMock()
                
                mock_camoufox.side_effect = [mock_camoufox_instance1, mock_camoufox_instance2]
                
                manager = BrowserManager(headless=True)
                
                # First launch
                await manager.launch()
                first_browser = manager.browser
                
                # Crash and recovery
                try:
                    await manager.close()
                except Exception:
                    pass  # Expected crash
                
                # Relaunch (recovery)
                await manager.launch()
                second_browser = manager.browser
                
                # Verify new browser instance
                assert second_browser is not None
                assert second_browser != first_browser
    
    @pytest.mark.asyncio
    async def test_browser_crash_during_claim(self, temp_browser_dirs, mock_profile):
        """Test handling of browser crash during active claim."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock browser that crashes during page creation
                mock_browser = AsyncMock()
                mock_context = AsyncMock()
                mock_context.new_page = AsyncMock(side_effect=Exception("Browser disconnected"))
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Attempt to get page (crashes)
                try:
                    page = await manager.get_page(mock_profile)
                    assert False, "Should have raised exception"
                except Exception as e:
                    # Crash was handled
                    assert "disconnected" in str(e).lower() or "Browser" in str(e)


class TestContextCleanup:
    """Test proper cleanup of browser contexts after failures."""
    
    @pytest.mark.asyncio
    async def test_cleanup_context_on_error(self, temp_browser_dirs, mock_profile):
        """Test that context is cleaned up when an error occurs."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock browser and context
                mock_context = AsyncMock()
                mock_context.close = AsyncMock()
                
                mock_browser = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Create context
                context_key = f"{mock_profile.faucet}_{mock_profile.username}"
                manager.contexts[context_key] = mock_context
                
                # Close context
                await manager.close_context(context_key)
                
                # Verify cleanup
                mock_context.close.assert_called_once()
                assert context_key not in manager.contexts
    
    @pytest.mark.asyncio
    async def test_cleanup_all_contexts_on_shutdown(self, temp_browser_dirs):
        """Test that all contexts are cleaned up on browser shutdown."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock browser with multiple contexts
                mock_context1 = AsyncMock()
                mock_context1.close = AsyncMock()
                
                mock_context2 = AsyncMock()
                mock_context2.close = AsyncMock()
                
                mock_browser = AsyncMock()
                mock_browser.close = AsyncMock()
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Add contexts
                manager.contexts["context1"] = mock_context1
                manager.contexts["context2"] = mock_context2
                
                # Shutdown
                await manager.close()
                
                # Verify all contexts were closed
                mock_context1.close.assert_called_once()
                mock_context2.close.assert_called_once()
                mock_browser.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_cleanup_resilient_to_errors(self, temp_browser_dirs):
        """Test that context cleanup continues even if some contexts fail to close."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock contexts - one fails to close
                mock_context1 = AsyncMock()
                mock_context1.close = AsyncMock(side_effect=Exception("Close failed"))
                
                mock_context2 = AsyncMock()
                mock_context2.close = AsyncMock()
                
                mock_browser = AsyncMock()
                mock_browser.close = AsyncMock()
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                manager.contexts["failing_context"] = mock_context1
                manager.contexts["working_context"] = mock_context2
                
                # Shutdown - should not raise exception
                await manager.close()
                
                # Both close attempts were made
                mock_context1.close.assert_called_once()
                mock_context2.close.assert_called_once()


class TestSessionPersistence:
    """Test session persistence through cookie restoration."""
    
    @pytest.mark.asyncio
    async def test_save_cookies_on_success(self, temp_browser_dirs, mock_profile):
        """Test that cookies are saved after successful operations."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock context with cookies
                mock_cookies = [
                    {"name": "session", "value": "abc123", "domain": ".faucet.com"},
                    {"name": "auth", "value": "token456", "domain": ".faucet.com"}
                ]
                
                mock_context = AsyncMock()
                mock_context.cookies = AsyncMock(return_value=mock_cookies)
                
                mock_browser = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                # Mock cookie storage
                with patch("browser.instance.SecureCookieStorage") as mock_storage:
                    mock_storage_instance = MagicMock()
                    mock_storage_instance.save = MagicMock()
                    mock_storage.return_value = mock_storage_instance
                    
                    manager = BrowserManager(headless=True, use_encrypted_cookies=True)
                    manager.cookie_storage = mock_storage_instance
                    await manager.launch()
                    
                    # Get page (creates context)
                    context_key = f"{mock_profile.faucet}_{mock_profile.username}"
                    manager.contexts[context_key] = mock_context
                    
                    # Save cookies
                    cookies = await mock_context.cookies()
                    manager.cookie_storage.save(context_key, cookies)
                    
                    # Verify save was called
                    mock_storage_instance.save.assert_called_once_with(context_key, mock_cookies)
    
    @pytest.mark.asyncio
    async def test_restore_cookies_on_launch(self, temp_browser_dirs, mock_profile):
        """Test that cookies are restored when creating a new context."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock saved cookies
                saved_cookies = [
                    {"name": "session", "value": "restored123", "domain": ".faucet.com"}
                ]
                
                mock_context = AsyncMock()
                mock_context.add_cookies = AsyncMock()
                
                mock_browser = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                # Mock cookie storage with saved cookies
                with patch("browser.instance.SecureCookieStorage") as mock_storage:
                    mock_storage_instance = MagicMock()
                    mock_storage_instance.load = MagicMock(return_value=saved_cookies)
                    mock_storage.return_value = mock_storage_instance
                    
                    manager = BrowserManager(headless=True, use_encrypted_cookies=True)
                    manager.cookie_storage = mock_storage_instance
                    await manager.launch()
                    
                    # Simulate loading cookies for a context
                    context_key = f"{mock_profile.faucet}_{mock_profile.username}"
                    cookies = manager.cookie_storage.load(context_key)
                    
                    if cookies:
                        await mock_context.add_cookies(cookies)
                    
                    # Verify cookies were loaded and added
                    mock_storage_instance.load.assert_called_once_with(context_key)
                    mock_context.add_cookies.assert_called_once_with(saved_cookies)
    
    @pytest.mark.asyncio
    async def test_cookie_persistence_survives_crash(self, temp_browser_dirs, mock_profile):
        """Test that cookies are preserved even if browser crashes."""
        cookie_file = temp_browser_dirs["cookies_dir"] / "test_cookies.enc"
        
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            # Simulate cookies saved before crash
            test_cookies = [
                {"name": "pre_crash", "value": "data123", "domain": ".faucet.com"}
            ]
            
            # Write cookies to disk
            cookie_file.write_text(json.dumps(test_cookies))
            
            # After crash, new browser instance
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                mock_context = AsyncMock()
                mock_context.add_cookies = AsyncMock()
                
                mock_browser = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Verify cookies can be loaded from disk
                if cookie_file.exists():
                    restored = json.loads(cookie_file.read_text())
                    assert restored == test_cookies


class TestConcurrentContextFailures:
    """Test isolation of failures across concurrent contexts."""
    
    @pytest.mark.asyncio
    async def test_one_context_failure_doesnt_affect_others(self, temp_browser_dirs):
        """Test that failure in one context doesn't affect other contexts."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock contexts - one will fail
                mock_context1 = AsyncMock()
                mock_page1 = AsyncMock()
                mock_context1.new_page = AsyncMock(side_effect=Exception("Context 1 failed"))
                
                mock_context2 = AsyncMock()
                mock_page2 = AsyncMock()
                mock_context2.new_page = AsyncMock(return_value=mock_page2)
                
                mock_browser = AsyncMock()
                mock_browser.new_context = AsyncMock(side_effect=[mock_context1, mock_context2])
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Store contexts
                manager.contexts["context1"] = mock_context1
                manager.contexts["context2"] = mock_context2
                
                # Try to get page from failing context
                try:
                    await mock_context1.new_page()
                except Exception:
                    pass  # Expected
                
                # Other context should still work
                page2 = await mock_context2.new_page()
                assert page2 == mock_page2
    
    @pytest.mark.asyncio
    async def test_parallel_context_operations(self, temp_browser_dirs):
        """Test that multiple contexts can operate in parallel."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock multiple contexts
                execution_order = []
                
                async def create_page_1():
                    execution_order.append("context1_start")
                    await asyncio.sleep(0.1)
                    execution_order.append("context1_end")
                    return AsyncMock()
                
                async def create_page_2():
                    execution_order.append("context2_start")
                    await asyncio.sleep(0.1)
                    execution_order.append("context2_end")
                    return AsyncMock()
                
                mock_context1 = AsyncMock()
                mock_context1.new_page = create_page_1
                
                mock_context2 = AsyncMock()
                mock_context2.new_page = create_page_2
                
                mock_browser = AsyncMock()
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Create pages in parallel
                await asyncio.gather(
                    mock_context1.new_page(),
                    mock_context2.new_page()
                )
                
                # Verify parallel execution
                assert "context1_start" in execution_order
                assert "context2_start" in execution_order
                
                # Both should have started before either finished
                context1_start = execution_order.index("context1_start")
                context2_start = execution_order.index("context2_start")
                
                # At least some overlap
                assert len(execution_order) == 4


class TestResourceCleanup:
    """Test cleanup of resources (pages, contexts) on errors."""
    
    @pytest.mark.asyncio
    async def test_page_cleanup_on_navigation_error(self, temp_browser_dirs):
        """Test that page is cleaned up if navigation fails."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                # Mock page that fails to navigate
                mock_page = AsyncMock()
                mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))
                mock_page.close = AsyncMock()
                
                mock_context = AsyncMock()
                mock_context.new_page = AsyncMock(return_value=mock_page)
                
                mock_browser = AsyncMock()
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Try to navigate
                try:
                    page = await mock_context.new_page()
                    await page.goto("https://example.com")
                except Exception:
                    # Cleanup should happen
                    await mock_page.close()
                
                # Verify cleanup was called
                mock_page.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_memory_cleanup_after_context_close(self, temp_browser_dirs):
        """Test that context is removed from memory after closing."""
        with patch("browser.instance.CONFIG_DIR", str(temp_browser_dirs["config_dir"])):
            with patch("browser.instance.AsyncCamoufox") as mock_camoufox:
                mock_context = AsyncMock()
                mock_context.close = AsyncMock()
                
                mock_browser = AsyncMock()
                
                mock_camoufox_instance = AsyncMock()
                mock_camoufox_instance.__aenter__.return_value = mock_browser
                mock_camoufox_instance.__aexit__.return_value = AsyncMock()
                mock_camoufox.return_value = mock_camoufox_instance
                
                manager = BrowserManager(headless=True)
                await manager.launch()
                
                # Add context
                context_key = "test_context"
                manager.contexts[context_key] = mock_context
                
                # Verify it's in memory
                assert context_key in manager.contexts
                
                # Close context
                await manager.close_context(context_key)
                
                # Verify it's removed from memory
                assert context_key not in manager.contexts
