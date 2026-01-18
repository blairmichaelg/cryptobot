import pytest
import asyncio
import json
import base64
import time
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from solvers.captcha import CaptchaSolver

@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.url = "https://faucet.com"
    return page

class TestCaptchaExtra:
    
    @pytest.mark.asyncio
    async def test_budget_logic(self):
        """Test daily budget and cost tracking (lines 69-104)."""
        solver = CaptchaSolver(api_key="12345678901234567890123456789012", daily_budget=0.01)
        
        # 1. Initial state
        stats = solver.get_budget_stats()
        assert stats["spent_today"] == 0
        
        # 2. Can afford
        assert solver._can_afford_solve("hcaptcha") is True
        
        # 3. Record solve
        solver._record_solve("hcaptcha", True)
        assert solver._daily_spend == 0.003
        
        # 4. Exhaust budget
        solver._record_solve("hcaptcha", True) # 0.006
        solver._record_solve("hcaptcha", True) # 0.009
        assert solver._can_afford_solve("hcaptcha") is False
        
        # 5. Reset day (mocked)
        solver._budget_reset_date = "2000-01-01"
        solver._check_and_reset_daily_budget()
        assert solver._daily_spend == 0
        assert solver._budget_reset_date == time.strftime("%Y-%m-%d")

    def test_proxy_parsing(self):
        """Test proxy component parsing (lines 106-126)."""
        solver = CaptchaSolver()
        p1 = solver._parse_proxy("socks5://user:pass@1.2.3.4:8888")
        assert p1["proxytype"] == "SOCKS5"
        assert p1["proxy"] == "user:pass@1.2.3.4:8888"

    @pytest.mark.asyncio
    async def test_detection_logic(self, mock_page):
        """Test various detection methods (lines 153-220)."""
        solver = CaptchaSolver(api_key=None) # Manual mode
        
        # Mock various captcha elements
        async def mock_selectors(selector):
            if "iframe[src*='hcaptcha']" in selector:
                m = AsyncMock()
                m.get_attribute.return_value = "https://hcaptcha.com?sitekey=h-key"
                return m
            return None
        
        mock_page.query_selector.side_effect = mock_selectors
        
        with patch.object(solver, "_wait_for_human", AsyncMock(return_value=True)):
            await solver.solve_captcha(mock_page, timeout=1)

    @pytest.fixture
    def mock_session(self):
        """Correctly mock aiohttp session for 'async with' usage."""
        session = MagicMock() # Use MagicMock for the session itself
        session.closed = False
        
        # post() and get() return context managers synchronously
        mock_post_ctx = MagicMock()
        mock_get_ctx = MagicMock()
        
        session.post.return_value = mock_post_ctx
        session.get.return_value = mock_get_ctx
        
        # The context managers have async __aenter__ and __aexit__
        mock_post_ctx.__aenter__ = AsyncMock()
        mock_post_ctx.__aexit__ = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock()
        mock_get_ctx.__aexit__ = AsyncMock()
        
        return session

    @pytest.mark.asyncio
    async def test_solve_2captcha_hcaptcha_with_proxy(self, mock_page, mock_session):
        """Test 2Captcha hCaptcha solve with proxy (lines 376-437)."""
        solver = CaptchaSolver(api_key="12345678901234567890123456789012", provider="2captcha")
        solver.set_proxy("http://p:p@1.1.1.1:80")
        solver.session = mock_session
        
        m_resp_in = AsyncMock()
        m_resp_in.json.return_value = {"status": 1, "request": "req123"}
        m_resp_res = AsyncMock()
        m_resp_res.json.return_value = {"status": 1, "request": "token123"}
        
        mock_session.post.return_value.__aenter__.return_value = m_resp_in
        mock_session.get.return_value.__aenter__.return_value = m_resp_res
        
        with patch.object(solver, "_extract_sitekey_from_scripts", AsyncMock(return_value="h-key")), \
             patch.object(solver, "_inject_token", AsyncMock()):
            res = await solver._solve_2captcha("h-key", "http://url", "hcaptcha")
            assert res == "token123"

    @pytest.mark.asyncio
    async def test_solve_capsolver_turnstile(self, mock_page, mock_session):
        """Test CapSolver Turnstile solve (lines 440-510)."""
        solver = CaptchaSolver(api_key="12345678901234567890123456789012", provider="capsolver")
        solver.session = mock_session
        
        m_resp_create = AsyncMock()
        m_resp_create.json.return_value = {"errorId": 0, "taskId": "t1"}
        m_resp_result = AsyncMock()
        m_resp_result.json.return_value = {"status": "ready", "solution": {"token": "cap-token"}}
        
        mock_session.post.return_value.__aenter__.side_effect = [m_resp_create, m_resp_result]
        
        with patch("asyncio.sleep", AsyncMock()):
            token = await solver._solve_capsolver("s-key", "http://u", "turnstile")
            assert token == "cap-token"

    @pytest.mark.asyncio
    async def test_solve_image_captcha_coordinates(self, mock_page, mock_session):
        """Test coordinates-based image captcha (lines 246-375)."""
        solver = CaptchaSolver(api_key="12345678901234567890123456789012")
        solver.session = mock_session
        
        mock_el = AsyncMock()
        mock_page.query_selector.return_value = mock_el
        mock_el.bounding_box.return_value = {"x": 10, "y": 20, "width": 100, "height": 100}
        mock_el.screenshot.return_value = b"bytes"
        
        m_in = AsyncMock()
        m_in.json.return_value = {"status": 1, "request": "i1"}
        m_res = AsyncMock()
        m_res.json.return_value = {"status": 1, "request": "10,20"}
        
        mock_session.post.return_value.__aenter__.return_value = m_in
        mock_session.get.return_value.__aenter__.return_value = m_res
        
        with patch("asyncio.sleep", AsyncMock()):
            res = await solver._solve_image_captcha(mock_page)
            assert res is True
            mock_page.mouse.click.assert_called()

    @pytest.mark.asyncio
    async def test_manual_solve_detection(self, mock_page):
        """Test manual solve polling."""
        solver = CaptchaSolver()
        mock_page.evaluate.side_effect = ["", "token"]
        with patch("asyncio.sleep", AsyncMock()):
            assert await solver._wait_for_human(mock_page, timeout=10) is True

    @pytest.mark.asyncio
    async def test_inject_token_generic(self, mock_page):
        """Test token injection."""
        solver = CaptchaSolver()
        await solver._inject_token(mock_page, "turnstile", "t")
        assert mock_page.evaluate.call_count > 0

    @pytest.mark.asyncio
    async def test_error_paths_2(self, mock_page, mock_session):
        """Test error paths again with correct session mock."""
        solver = CaptchaSolver(api_key="12345678901234567890123456789012")
        solver.session = mock_session
        
        # 1. JSON error
        m_resp = AsyncMock()
        m_resp.json.side_effect = Exception("Invalid JSON")
        mock_session.post.return_value.__aenter__.return_value = m_resp
        assert await solver._solve_2captcha("k", "u", "hcaptcha") is None
        
        # 2. Status 0 error
        m_resp.json.side_effect = None
        m_resp.json.return_value = {"status": 0, "request": "ERROR"}
        assert await solver._solve_2captcha("k", "u", "hcaptcha") is None
        
        # 3. Poll status 0
        m_in = AsyncMock()
        m_in.json.return_value = {"status": 1, "request": "r1"}
        m_res = AsyncMock()
        m_res.json.return_value = {"status": 0, "request": "ERROR_POLL"}
        mock_session.post.return_value.__aenter__.return_value = m_in
        mock_session.get.return_value.__aenter__.return_value = m_res
        with patch("asyncio.sleep", AsyncMock()):
            assert await solver._solve_2captcha("k", "u", "hcaptcha") is None

    @pytest.mark.asyncio
    async def test_capsolver_error_paths(self, mock_page, mock_session):
        """Test CapSolver error paths."""
        solver = CaptchaSolver(api_key="KEY", provider="capsolver")
        solver.session = mock_session
        
        # 1. CreateTask fail (errorId != 0)
        m_resp = AsyncMock()
        m_resp.json.return_value = {"errorId": 1, "errorDescription": "Fail"}
        mock_session.post.return_value.__aenter__.return_value = m_resp
        assert await solver._solve_capsolver("k", "u", "hcaptcha") is None
        
        # 2. Connection error
        mock_session.post.return_value.__aenter__.side_effect = Exception("Conn error")
        assert await solver._solve_capsolver("k", "u", "hcaptcha") is None
        
        # 3. Ready but status failed
        mock_session.post.return_value.__aenter__.side_effect = None
        m_create = AsyncMock()
        m_create.json.return_value = {"errorId": 0, "taskId": "t"}
        m_res_fail = AsyncMock()
        m_res_fail.json.return_value = {"status": "failed", "errorDescription": "Task failed"}
        mock_session.post.return_value.__aenter__.side_effect = [m_create, m_res_fail]
        
        with patch("asyncio.sleep", AsyncMock()):
            assert await solver._solve_capsolver("k", "u", "hcaptcha") is None
            
    @pytest.mark.asyncio
    async def test_close_logic(self):
        solver = CaptchaSolver()
        s = await solver._get_session()
        assert not s.closed
        await solver.close()
        assert s.closed
