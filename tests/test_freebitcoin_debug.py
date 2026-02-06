"""Quick debug test for FreeBitcoin claim."""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from core.config import BotSettings
from browser.instance import BrowserManager

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)

async def test_freebitcoin():
    settings = BotSettings()
    manager = BrowserManager()
    await manager.launch()
    
    session_id = 'dbgfb001'
    proxy_url = f'http://ub033d0d0583c05dd-zone-custom-session-{session_id}:ub033d0d0583c05dd@43.135.141.142:2334'
    
    context = await manager.create_context(profile_name='blazefoley97@gmail.com', proxy=proxy_url)
    page = await context.new_page()
    
    from faucets.freebitcoin import FreeBitcoinBot
    bot = FreeBitcoinBot(settings, page)
    
    print("\n" + "="*60)
    print("Testing FreeBitcoin claim")
    print("="*60)
    
    result = await bot.claim()
    
    print(f'\n{"="*60}')
    print(f'RESULT: {result}')
    print(f'{"="*60}')
    
    await manager.close()

if __name__ == "__main__":
    asyncio.run(test_freebitcoin())
