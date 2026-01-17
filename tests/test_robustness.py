import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from faucets.base import FaucetBot, ClaimResult, BotSettings

class TestFaucetBotRobustness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = BotSettings()
        self.page = AsyncMock()
        self.bot = FaucetBot(self.settings, self.page)
        self.bot.solver = AsyncMock() # Mock solver logic
        self.bot.solver.close = AsyncMock()
        
        # Mock abstract methods
        self.bot.login = AsyncMock(return_value=True)
        self.bot.claim = AsyncMock()
        
        # Add a mock earning task
        self.bot.view_ptc_ads = AsyncMock()

    async def test_run_executes_all_tasks_even_after_failure(self):
        """
        Verify that if claim() raises an exception, view_ptc_ads() still runs.
        """
        # Setup: claim fails
        self.bot.claim.side_effect = Exception("Simulated Failure")
        
        # Run
        result = await self.bot.run()
        
        # Assert claim was called
        self.bot.claim.assert_called()
        
        # CRITICAL: Assert ptc was called despite claim failure
        self.bot.view_ptc_ads.assert_called()
        
        # Assert result reflects failure and captured the exception
        self.assertFalse(result.success)
        self.assertIn("Simulated Failure", result.status) 
        self.assertEqual(result.next_claim_minutes, 15)

    async def test_run_scheduling_update(self):
        """
        Verify that a successful claim updates the final result.
        """
        success_res = ClaimResult(success=True, status="OK", next_claim_minutes=30)
        self.bot.claim.side_effect = None
        self.bot.claim.return_value = success_res
        
        result = await self.bot.run()
        
        self.bot.view_ptc_ads.assert_called()
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.next_claim_minutes, 30)

if __name__ == "__main__":
    unittest.main()
