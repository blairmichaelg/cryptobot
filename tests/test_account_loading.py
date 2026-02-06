"""Simple test to verify job creation and account loading"""
import asyncio
from core.config import BotSettings
from core.registry import get_faucet_class

async def test_account_loading():
    """Test that accounts load correctly"""
    settings = BotSettings()
    
    print(f"Total accounts in settings: {len(settings.accounts)}")
    print("\nAccounts:")
    for acc in settings.accounts:
        if acc.enabled:
            print(f"  ✓ {acc.faucet}: {acc.username} (enabled)")
        else:
            print(f"  ✗ {acc.faucet}: {acc.username} (DISABLED)")
    
    print(f"\nCreating jobs for each account...")
    jobs_created = 0
    for profile in [acc for acc in settings.accounts if acc.enabled]:
        f_type = profile.faucet.lower()
        bot_class = get_faucet_class(f_type)
        
        if bot_class:
            bot = bot_class(settings, None)
            jobs = bot.get_jobs()
            print(f"  {profile.faucet} ({profile.username}): {len(jobs)} jobs created")
            jobs_created += len(jobs)
        else:
            print(f"  {profile.faucet}: ❌ NO BOT CLASS FOUND")
    
    print(f"\n✅ Total jobs created: {jobs_created}")
    
    return jobs_created

if __name__ == "__main__":
    total = asyncio.run(test_account_loading())
    exit(0 if total > 0 else 1)
