import sys
import os
sys.path.append(os.getcwd())
from core.orchestrator import JobScheduler
from core.config import BotSettings, AccountProfile
from unittest.mock import AsyncMock

def test_rotation():
    settings = BotSettings()
    manager = AsyncMock()
    scheduler = JobScheduler(settings, manager)
    
    proxies = ["p1", "p2", "p3"]
    profile = AccountProfile(
        faucet="f", 
        username="rr", 
        password="p", 
        proxy_pool=proxies, 
        proxy_rotation_strategy="round_robin",
        enabled=True
    )
    
    p1 = scheduler.get_next_proxy(profile)
    print(f"Call 1: {p1}")
    
    p2 = scheduler.get_next_proxy(profile)
    print(f"Call 2: {p2}")
    
    if p1 == "p1" and p2 == "p2":
        print("✅ Rotation Working")
    else:
        print("❌ Rotation Failed")
        print(f"Index state: {scheduler.proxy_index}")

if __name__ == "__main__":
    test_rotation()
