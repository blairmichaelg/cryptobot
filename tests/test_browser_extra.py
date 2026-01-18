import pytest
import asyncio
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from browser.instance import BrowserManager

@pytest.fixture
def mock_camoufox():
    with patch("browser.instance.AsyncCamoufox") as mock:
        yield mock

class TestBrowserExtra:
    
    @pytest.mark.asyncio
    async def test_launch_and_close(self, mock_camoufox):
        """Test browser launch and close lifecycle (lines 46-64, 286-295)."""
        manager = BrowserManager()
        mock_instance = MagicMock()
        mock_camoufox.return_value = mock_instance
        mock_instance.__aenter__ = AsyncMock(return_value="browser")
        mock_instance.__aexit__ = AsyncMock()
        
        await manager.launch()
        assert manager.browser == "browser"
        
        await manager.close()
        assert manager.browser is None
        mock_instance.__aexit__.assert_called()

    @pytest.mark.asyncio
    async def test_create_context_proxy_formats(self):
        """Test create_context with various proxy formats (lines 115-127)."""
        manager = BrowserManager()
        manager.browser = AsyncMock()
        manager.load_proxy_binding = AsyncMock(return_value=None)
        manager.save_proxy_binding = AsyncMock()
        
        # 1. URL format
        proxy_url = "http://user:pass@1.2.3.4:8080"
        await manager.create_context(proxy=proxy_url)
        args, kwargs = manager.browser.new_context.call_args
        assert kwargs["proxy"]["server"] == "http://1.2.3.4:8080"
        assert kwargs["proxy"]["username"] == "user"
        assert kwargs["proxy"]["password"] == "pass"
        
        # 2. String format
        proxy_str = "1.2.3.4:8080"
        await manager.create_context(proxy=proxy_str)
        args, kwargs = manager.browser.new_context.call_args
        assert kwargs["proxy"]["server"] == "1.2.3.4:8080"
        
        # 3. No browser exception (72)
        manager.browser = None
        with pytest.raises(RuntimeError, match="Browser not launched"):
            await manager.create_context()

    @pytest.mark.asyncio
    async def test_sticky_proxy_logic_flow(self):
        """Test create_context sticky logic flow (lines 98-114)."""
        manager = BrowserManager()
        manager.browser = AsyncMock()
        
        # 1. New binding (110-113)
        manager.load_proxy_binding = AsyncMock(return_value=None)
        manager.save_proxy_binding = AsyncMock()
        await manager.create_context(proxy="p1", profile_name="u1")
        manager.save_proxy_binding.assert_called_with("u1", "p1")
        
        # 2. Use existing binding (107-109)
        manager.load_proxy_binding = AsyncMock(return_value="p1")
        manager.save_proxy_binding.reset_mock()
        await manager.create_context(proxy=None, profile_name="u1")
        args, kwargs = manager.browser.new_context.call_args
        assert kwargs["proxy"]["server"] == "p1"
        
        # 3. Mismatch update (103-106)
        await manager.create_context(proxy="p2", profile_name="u1")
        manager.save_proxy_binding.assert_called_with("u1", "p2")

    @pytest.mark.asyncio
    async def test_proxy_binding_persistence(self):
        """Test actual proxy binding file I/O (lines 213-246)."""
        manager = BrowserManager()
        
        with patch("browser.instance.open", create=True) as mock_open, \
             patch("browser.instance.os.path.exists", return_value=True):
            
            # 1. Load: Read valid JSON
            m_read = MagicMock()
            m_read.__enter__.return_value.read.return_value = json.dumps({"u1": "p1"})
            mock_open.return_value = m_read
            assert await manager.load_proxy_binding("u1") == "p1"
            
            # 2. Save: Read valid JSON, then Write
            m_read2 = MagicMock()
            m_read2.__enter__.return_value.read.return_value = json.dumps({"u1": "p1"})
            m_write = MagicMock()
            mock_open.reset_mock()
            mock_open.side_effect = [m_read2, m_write]
            await manager.save_proxy_binding("u2", "p2")
            assert mock_open.call_count == 2
            # Verify second call was 'w'
            assert mock_open.call_args_list[1][0][1] == "w"

            # 3. Corrupt JSON in save (branch 223)
            m_read_corrupt = MagicMock()
            m_read_corrupt.__enter__.return_value.read.return_value = "invalid json"
            m_write2 = MagicMock()
            mock_open.reset_mock()
            mock_open.side_effect = [m_read_corrupt, m_write2]
            await manager.save_proxy_binding("u3", "p3")
            
            # 4. Corrupt JSON in load (branch 242)
            m_read_corrupt2 = MagicMock()
            m_read_corrupt2.__enter__.return_value.read.return_value = "invalid json"
            mock_open.reset_mock()
            mock_open.side_effect = None
            mock_open.return_value = m_read_corrupt2
            assert await manager.load_proxy_binding("u1") is None
            
            # 5. Save global exception (branch 230)
            mock_open.side_effect = Exception("Fatal write error")
            await manager.save_proxy_binding("u4", "p4") # Should handle
            
            # 6. Load global exception (branch 245)
            mock_open.side_effect = Exception("Fatal read error")
            assert await manager.load_proxy_binding("u1") is None

    @pytest.mark.asyncio
    async def test_cookie_persistence_unencrypted(self):
        """Test unencrypted cookie save/load (lines 162-168, 193-200)."""
        manager = BrowserManager(use_encrypted_cookies=False)
        mock_context = AsyncMock()
        mock_context.cookies.return_value = [{"name": "c1", "value": "v1"}]
        
        with patch("browser.instance.open", create=True) as mock_open, \
             patch("browser.instance.os.path.exists", return_value=True), \
             patch("browser.instance.os.makedirs"):
            # Save
            await manager.save_cookies(mock_context, "u1")
            mock_open.assert_called()
            
            # Load
            m = mock_open.return_value.__enter__.return_value
            m.read.return_value = json.dumps([{"name": "c1", "value": "v1"}])
            assert await manager.load_cookies(mock_context, "u1") is True
            mock_context.add_cookies.assert_called()

    @pytest.mark.asyncio
    async def test_cookie_persistence_encrypted(self):
        """Test encrypted cookie path (lines 159-160, 188-189)."""
        manager = BrowserManager(use_encrypted_cookies=True)
        manager._secure_storage = AsyncMock()
        mock_context = AsyncMock()
        
        await manager.save_cookies(mock_context, "u1")
        manager._secure_storage.save_cookies.assert_called()
        
        await manager.load_cookies(mock_context, "u1")
        manager._secure_storage.load_cookies.assert_called()

    @pytest.mark.asyncio
    async def test_restart_and_health_check(self):
        """Test restart and health check methods (lines 264-284)."""
        manager = BrowserManager()
        manager.browser = AsyncMock()
        mock_instance = MagicMock()
        manager.camoufox = mock_instance
        mock_instance.__aexit__ = AsyncMock()
        
        # Restart
        with patch("asyncio.sleep"), \
             patch("browser.instance.AsyncCamoufox", return_value=mock_instance):
            mock_instance.__aenter__ = AsyncMock(return_value=AsyncMock())
            await manager.restart()
            assert mock_instance.__aexit__.called
            assert manager.browser is not None

        # Health
        manager.browser.new_context = AsyncMock()
        assert await manager.check_health() is True
        
        manager.browser.new_context.side_effect = Exception("Fail")
        assert await manager.check_health() is False 
        
        # No browser (275)
        manager.browser = None
        assert await manager.check_health() is False

    @pytest.mark.asyncio
    async def test_new_page(self):
        """Test new_page (lines 249-262)."""
        manager = BrowserManager()
        manager.browser = AsyncMock()
        
        # 1. With context
        mock_context = AsyncMock()
        await manager.new_page(mock_context)
        mock_context.new_page.assert_called_once()
        
        # 2. Without context (includes auto-launch) (251)
        manager.browser = None
        with patch.object(manager, "launch", new_callable=AsyncMock) as mock_launch:
            def set_browser(): manager.browser = AsyncMock()
            mock_launch.side_effect = set_browser
            await manager.new_page()
            mock_launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_stealth_browser_factory(self):
        """Test factory (lines 296-307)."""
        from browser.instance import create_stealth_browser
        with patch("browser.instance.AsyncCamoufox") as mock:
            await create_stealth_browser(proxy="http://p")
            mock.assert_called()

    @pytest.mark.asyncio
    async def test_exception_paths(self):
        """Test miscellaneous exception paths (lines 169-170, 209-211, 230, 245, 291-292)."""
        manager = BrowserManager()
        manager.browser = AsyncMock()
        manager.camoufox = AsyncMock()
        manager.camoufox.__aexit__.side_effect = Exception("Exit fail")
        
        # Close exception (291-292)
        await manager.close() # Should catch and not crash
        
        # Save cookies exception (169-170)
        mock_context = AsyncMock()
        mock_context.cookies.side_effect = Exception("Cookie fail")
        await manager.save_cookies(mock_context, "u1")
        
        # Load cookies exception (209-211)
        mock_context.add_cookies.side_effect = Exception("Add fail")
        with patch("browser.instance.os.path.exists", return_value=True), \
             patch("builtins.open", side_effect=Exception("Open fail")):
            assert await manager.load_cookies(mock_context, "u1") is False
