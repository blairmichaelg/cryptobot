
import sys
import os
import time
from unittest.mock import AsyncMock

# Add repo root to path
sys.path.append(os.getcwd())

try:
    from core.orchestrator import Job
    from core.config import AccountProfile
    
    print("Job imported successfully.")
    print(f"Job annotations: {Job.__annotations__}")
    
    profile = AccountProfile(faucet="test", username="u", password="p")
    func = AsyncMock()
    
    print("Attempting to create Job...")
    job = Job(
        priority=1,
        next_run=time.time(),
        name="Test Job",
        profile=profile,
        func=func,
        faucet_type="test"
    )
    print("Job created successfully:", job)
    
except Exception as e:
    print(f"Caught exception: {e}")
    import traceback
    traceback.print_exc()
