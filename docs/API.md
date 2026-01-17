# Cryptobot API Documentation

## Core

### WalletDaemon
`core.wallet_manager.WalletDaemon`

Interface for local crypto wallet daemons (Electrum, Core). Uses JSON-RPC to manage keys and sign transactions headless.

**Init**:
`__init__(self, rpc_url: str, rpc_user: str, rpc_pass: str)`
- `rpc_url`: The URL of the RPC server.
- `rpc_user`: The username for RPC authentication.
- `rpc_pass`: The password for RPC authentication.

**Methods**:
- `get_balance()`: Get confirmed and unconfirmed balance.
- `get_unused_address()`: Generate a new receiving address.
- `validate_address(address)`: Check if address is valid.
- `check_connection()`: Health check.

## Browser

### BrowserManager
`browser.instance.BrowserManager`

Wraps `AsyncCamoufox` to provide a stealthy browser context.

**Init**:
`__init__(self, headless: bool = True, proxy: Optional[str] = None)`
- `headless`: Whether to run the browser in headless mode.
- `proxy`: Optional proxy server address.

**Methods**:
- `launch() -> Page`: Launches a new page in a stealth context.
- `close()`: Cleans up resources.

## Faucets

### FaucetBot (Base Class)
`faucets.base.FaucetBot`

Base class for all faucet implementations.

**Init**:
`__init__(self, settings: BotSettings, page: Page)`

**Methods**:
- `random_delay(min_s, max_s)`: Waits for a random duration.
- `human_like_click(locator)`: Clicks an element with human-like delays.
- `login() -> bool`: Abstract method to perform login.
- `claim() -> bool`: Abstract method to perform the claim.

## Solvers

### CaptchaSolver
`solvers.captcha.CaptchaSolver`

Hybrid solver that uses 2Captcha API or falls back to manual solving.

**Init**:
`__init__(self, api_key: str = None, provider: str = "2captcha")`

**Methods**:
- `solve_captcha(page, timeout) -> bool`: Main entry point to solve captcha.
- `close()`: Closes the session.
