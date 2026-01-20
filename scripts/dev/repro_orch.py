import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from core.orchestrator import JobScheduler, Job
from core.config import BotSettings, AccountProfile

async def run_test():
    print("Starting reproduction test...")
    
    # Mock deps
    settings = BotSettings(
        max_concurrent_bots=2,
        max_concurrent_per_profile=1,
        user_agents=["Test Agent"]
    )
    mock_browser_manager = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    
    # Setup returns
    mock_browser_manager.create_context.return_value = mock_context
    mock_browser_manager.new_page.return_value = mock_page
    
    scheduler = JobScheduler(settings, mock_browser_manager)
    profile = AccountProfile(faucet="test", username="user1", password="pass1")
    
    # Job func
    mock_result = MagicMock()
    mock_result.next_claim_minutes = 60
    job_func = AsyncMock(return_value=mock_result)
    
    job = Job(
        priority=1,
        next_run=time.time(),
        name="test_job",
        profile=profile,
        func=job_func,
        faucet_type="test"
    )
    
    print(f"Job created: {job}")
    
    try:
        await scheduler._run_job_wrapper(job)
        print("Wrapper finished.")
    except Exception as e:
        print(f"Wrapper raised exception: {e}")
        
    print(f"Queue length: {len(scheduler.queue)}")
    if len(scheduler.queue) > 0:
        print(f"Job retry count: {scheduler.queue[0].retry_count}")
        if scheduler.queue[0].retry_count > 0:
            print("FAILURE: Job was retried, meaning an error occurred inside wrapper.")
    
    # Check if mocks called
    print(f"create_context called: {mock_browser_manager.create_context.called}")
    print(f"job_func called: {job_func.called}")

if __name__ == "__main__":
    asyncio.run(run_test())
