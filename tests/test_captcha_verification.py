import pytest
import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from solvers.captcha import CaptchaSolver

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

@pytest.mark.asyncio
async def test_solver_logic():
    print("\n--- Testing 2Captcha Logic (Mocked) ---")
    
    # 1. Setup Mock Page
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    
    # Mock finding a Turnstile element
    mock_element = AsyncMock()
    mock_element.get_attribute.return_value = "0x4AAAAAAAC3aaaaaaaaaaaa" # Fake sitekey
    
    async def query_selector_side_effect(selector):
        if "turnstile" in selector:
            return mock_element
        return None
        
    mock_page.query_selector = AsyncMock(side_effect=query_selector_side_effect)
    mock_page.evaluate = AsyncMock()

    # 2. Setup Solver with Mocked Session
    solver = CaptchaSolver(api_key="TEST_API_KEY")
    
    # Mock the internal session and response objects
    mock_response_submit = AsyncMock()
    mock_response_submit.json.return_value = {"status": 1, "request": "12345"}
    
    mock_response_poll_not_ready = AsyncMock()
    mock_response_poll_not_ready.json.return_value = {"status": 0, "request": "CAPCHA_NOT_READY"}
    
    mock_response_poll_ready = AsyncMock()
    mock_response_poll_ready.json.return_value = {"status": 1, "request": "SOLVED_TOKEN_XYZ"}

    # We need to mock aiohttp.ClientSession context manager
    
    mock_session = MagicMock()
    mock_get_ctx = AsyncMock()
    mock_post_ctx = AsyncMock()
    
    mock_session.post.return_value = mock_post_ctx
    mock_session.get.return_value = mock_get_ctx
    
    mock_post_ctx.__aenter__.return_value = mock_response_submit
    mock_post_ctx.__aexit__.return_value = None
    
    # Simulate: Not Ready -> Ready
    mock_get_ctx.__aenter__.side_effect = [mock_response_poll_not_ready, mock_response_poll_ready]
    mock_get_ctx.__aexit__.return_value = None

    # Inject the mock session
    mock_session.closed = False
    mock_session.close = AsyncMock() # Fix: Ensure close is awaitable
    solver.session = mock_session

    print("Running solve_captcha...")
    result = await solver.solve_captcha(mock_page)
    
    assert result is True, "❌ FAILURE: Solver returned False"
    print("✅ SUCCESS: Solver returned True")
        
    # Verify Injection
    print("Verifying Token Injection...")
    mock_page.evaluate.assert_called()
    
    # Check if ANY of the calls contains the token
    found_token = False
    for call in mock_page.evaluate.call_args_list:
        if "SOLVED_TOKEN_XYZ" in call[0][0]:
            found_token = True
            break
            
    assert found_token, f"❌ FAILURE: Token NOT found in any injection script calls."
    print("✅ SUCCESS: Token found in one of the injection script calls")

    await solver.close()
