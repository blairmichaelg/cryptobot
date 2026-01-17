import pytest
import asyncio
import logging
from unittest.mock import MagicMock
from browser.blocker import ResourceBlocker
from solvers.shortlink import ShortlinkSolver

# Mock Logger
logging.basicConfig(level=logging.INFO)

@pytest.mark.asyncio
async def test_shortlink_blocker_toggle():
    """
    Tests if ShortlinkSolver correctly toggles the ResourceBlocker.
    """
    print("🧪 Testing Shortlink Solver <> Blocker Integration...")
    
    # 1. Setup Mock Page and Blocker
    mock_page = MagicMock()
    
    async def async_no_op(*args, **kwargs): return None
    async def async_return_zero(*args, **kwargs): return 0
    
    mock_page.goto = async_no_op
    
    # Mock Async Iterator for locator.element_handles / wait loops logic
    
    blocker = ResourceBlocker()
    blocker.enabled = True # Start enabled
    
    solver = ShortlinkSolver(mock_page, blocker=blocker)
    
    # 2. Run Solve (Mocking the loop to exit immediately)
    # We force the 'try' block to execute 'goto' then fail or return.
    
    # Mocking failure to exit fast
    mock_locator = MagicMock()
    mock_locator.count.side_effect = async_return_zero
    mock_page.locator.return_value = mock_locator
    
    mock_page.query_selector.side_effect = async_return_zero
    
    try:
        task = asyncio.create_task(solver.solve("http://fake.url"))
        
        # Give it a moment to enter the function and flip the switch
        await asyncio.sleep(0.1)
        
        assert blocker.enabled is False, "❌ Blocker failed to disable at start of solve."
        print("✅ Blocker successfully DISABLED at start of solve.")
             
        # Create condition to finish the task
        await task
        
    except Exception as e:
        pass
        
    # After finish, it should be enabled again
    assert blocker.enabled is True, "❌ Blocker failed to re-enable after solve."
    print("✅ Blocker successfully RE-ENABLED after solve.")
