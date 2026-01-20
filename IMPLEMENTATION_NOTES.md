# Implementation Notes

This document details all findings from research and implementation efforts to enhance the cryptobot's functionality, robustness, and profitability.

## Data Extraction Standardization

### Overview

All faucet modules now use standardized `get_balance()` and `get_timer()` methods from the `FaucetBot` base class, which leverage the `DataExtractor` utility for consistent parsing.

### Implementation Details

#### Core Extractor ([extractor.py](file:///c:/Users/azureuser/Repositories/cryptobot/core/extractor.py))

- **Timer Parsing**: Supports multiple formats including HH:MM:SS, MM:SS, "Xh Ym Zs", "X days", "X hours", "X minutes", "X seconds"
- **Balance Extraction**: Removes commas and extracts numeric values from text
- **Logging**: Debug-level logging for troubleshooting extraction issues

#### Base Class Integration ([base.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/base.py))

```python
async def get_timer(self, selector: str) -> float:
    """Extract timer value and convert to minutes"""
    
async def get_balance(self, selector: str) -> str:
    """Extract balance from selector"""
```

### Faucet-Specific Implementations

#### FreeBitcoin ([freebitcoin.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/freebitcoin.py))

- Balance: `#balance`
- Timer: `#time_remaining`
- **Status**: ✅ Fully standardized

#### DutchyCorp ([dutchy.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/dutchy.py))

- Balance: `.user-balance, .balance-text`
- Timer: `#timer, .count_down_timer, .timer`
- **Special Features**: Unlock button (`#unlockbutton`), Boost system (`#claim_boosted`)
- **Status**: ✅ Fully standardized

#### FireFaucet ([firefaucet.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/firefaucet.py))

- Balance: `.user-balance, .balance-text`
- Timer: `.fa-clock + span, #claim_timer, .timer`
- **Special Features**: Daily Bonus flow, Turnstile selection (`#select-turnstile`)
- **Status**: ✅ Fully standardized

#### FaucetCrypto ([faucetcrypto.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/faucetcrypto.py))

- Balance: `.user-balance, .balance-text`
- Timer: `.fa-clock, .timer-text`
- **Status**: ✅ Fully standardized

#### Cointiply ([cointiply.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/cointiply.py))

- Balance: `.user-balance-coins` (primary), `.user-balance` (fallback)
- Timer: `.timer_display, #timer_display, .timer-text`
- **Special Features**: Active tab focus required for PTC ads
- **Status**: ✅ Fully standardized

#### CoinPayU ([coinpayu.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/coinpayu.py))

- Balance: `.user-balance, .balance-text`
- **Special Features**: Multi-coin faucet (up to 4 per hour), Surf Ads
- **Status**: ✅ Fully standardized

#### AdBTC ([adbtc.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/adbtc.py))

- Balance: `.nomargbot > div.col.s6.l3.m3.left.hide-on-small-only > p > b, .balance-value, .user-balance`
- **Special Features**: Math captcha solver, withdrawal support
- **Status**: ✅ Fully standardized

#### Pick Family ([pick.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/pick.py))

- **Faucets**: LitePick, TronPick, DogePick, SolPick, BinPick, BchPick, TonPick, PolygonPick, DashPick, EthPick, UsdPick
- **Features**: Consolidated implementation, standardized registration, login, claim, and withdrawal
- **Status**: ✅ Fully standardized & consolidated

---

## Stealth and Persistence Enhancements

### Sticky Session Logic ([instance.py](file:///c:/Users/azureuser/Repositories/cryptobot/browser/instance.py))

- **Profile Persistence**: Browser contexts are bound to profiles (usernames)
- **Cookie Storage**: Encrypted cookie persistence for avoiding repeated logins
- **Proxy Binding**: Proxies are "stuck" to profiles in `proxy_bindings.json` to ensure IP consistency

### Anti-Detection Primitives ([base.py](file:///c:/Users/azureuser/Repositories/cryptobot/faucets/base.py))

- **Human Typing**: `human_type` with randomized delays between keystrokes
- **Idle Mouse**: `idle_mouse` mimics natural user behavior during waits
- **WebRTC Leak Prevention**: Automatically poisons WebRTC APIs to prevent real IP exposure through proxies

### Browser Health Monitoring

- **Auto-Restart**: Scheduler triggers browser restart after 5 consecutive job failures
- **Pulse Check**: Periodic health checks via `check_health()` verify browser responsiveness
- **Memory Management**: Restarting clears memory and hung processes from long-duration runs

---

## Solver Enhancements

### Captcha Solver ([captcha.py](file:///c:/Users/azureuser/Repositories/cryptobot/solvers/captcha.py))

#### Supported Types

- **Turnstile** (Cloudflare)
- **hCaptcha**
- **reCaptcha v2**
- **Image-based captchas** (coordinate/selection)

#### Providers

- **2Captcha** (default)
- **CapSolver**

#### Image Captcha Handling

- Detects custom image captchas
- Logs image sources and containers for debugging
- Falls back to manual solving with detailed logging
- **Future Enhancement**: OCR/VLM integration for automation

#### Token Injection

- Automatically injects solved tokens into DOM
- Triggers callback functions (`onCaptchaSuccess`, `onhCaptchaSuccess`, etc.)
- Dispatches change/input events for form validation

### Shortlink Solver ([shortlink.py](file:///c:/Users/azureuser/Repositories/cryptobot/solvers/shortlink.py))

#### Features

- **Timer Detection**: Uses `DataExtractor` for consistent parsing
- **Captcha Handling**: Integrates with `CaptchaSolver`
- **Popup Management**: Automatically closes popup windows
- **Smart Button Detection**: Heuristics to avoid ad elements
- **Resource Blocker Control**: Disables blocker during traversal to avoid detection

#### Traversal Flow

1. Navigate to shortlink URL
2. Wait for timers (up to 45 seconds)
3. Solve captchas if present
4. Click "Get Link", "Continue", or "Next" buttons
5. Handle popups and redirects
6. Repeat until destination reached (max 12 steps)

---

## Site-Specific Research Findings

### Common Security Patterns

1. **Cloudflare Turnstile**: Nearly universal across all faucets
2. **Proxy Detection**: DutchyCorp, CoinPayU, AdBTC block cloud IPs
3. **Active Focus Requirements**: Cointiply PTC, CoinPayU Window Ads require active tab
4. **Custom Captchas**: FireFaucet (numeric), Cointiply (unique image), AdBTC (math)

### DutchyCorp Findings

- **Critical Blocker**: Aggressive proxy detection
- **New Unlock Step**: `#unlockbutton` must be clicked before roll
- **Updated Selectors**: All earning methods verified and updated

### FireFaucet Findings

- **Daily Bonus Flow**: Unlock → Captcha Selection → Claim
- **PTC Custom Captcha**: Numeric image captcha (`#description > img`)
- **Turnstile Preference**: `#select-turnstile` for captcha type selection

### Cointiply Findings

- **Active Tab Requirement**: PTC ads require focus (35s wait)
- **Unique Image Captcha**: `#captcha-images` with clickable `.captcha-image` elements
- **Balance Fallback**: Dual selector strategy for reliability

### CoinPayU Findings

- **Multi-Coin Faucet**: Up to 4 different coins every 60 minutes
- **Surf Ads Efficiency**: Timer runs on main tab, ad tab just needs to exist
- **Unclicked Filter**: `.clearfix.ags-list-box:not(.gray-all)` for available ads

---

## Job-Based Scheduler

### Architecture ([orchestrator.py](file:///c:/Users/azureuser/Repositories/cryptobot/core/orchestrator.py))

- **Job Dataclass**: Tracks owner profile, job type, next run time, execution function
- **JobScheduler**: Global priority queue with concurrency limits
- **Event-Driven Loop**: Wakes exactly when next job is ready
- **Filler Mechanism**: Schedules exploration jobs when slots available

### Benefits

- **Zero Idle Time**: Maximizes crypto extraction across all methods
- **Granular Scheduling**: Individual jobs for Faucet, PTC, Shortlinks
- **Concurrency Control**: Global and per-profile limits prevent bans
- **Priority System**: High-priority jobs (Faucet) execute first

---

## Known Limitations

### Proxy Detection

- **Affected Sites**: DutchyCorp, CoinPayU, AdBTC
- **Solution**: Residential proxy rotation and sticky session management
- **Status**: 🛠️ Implemented! Now supports 2Captcha residential proxies with IP persistence.

### Image Captchas

- **Current Status**: Manual solving required
- **Future Enhancement**: OCR/VLM integration for automation
- **Affected Sites**: Cointiply (unique image), FireFaucet (numeric)

### Active Tab Requirements

- **Affected Sites**: Cointiply PTC, CoinPayU Window Ads
- **Implementation**: Extended wait times with focus management
- **Limitation**: Cannot run fully headless for these specific tasks

---

## Testing Coverage

### Automated Tests

- `test_extractor.py`: Data extraction regex patterns
- `test_shortlink_verification.py`: Shortlink solver logic
- `test_captcha_verification.py`: Captcha detection
- `test_dutchy.py`: Faucet structure validation
- `test_core_config.py`: Configuration loading

### Manual Verification

- Visible browser mode (`--visible`) for debugging
- Single faucet testing (`--single <faucet>`)
- Log monitoring for balance/timer extraction

---

## Future Enhancements

1. **Residential Proxy Rotation**: Overcome proxy detection on DutchyCorp, CoinPayU, AdBTC
2. **OCR/VLM Integration**: Automate image-based captchas
3. **Advanced PTC Logic**: Optimize ad-watching strategies
4. **Performance Metrics**: Track earnings per faucet/method
5. **Adaptive Scheduling**: Machine learning for optimal timing

---

## Optimized Workflow & Delegation

### Delegation Strategy

* **Gemini CLI (`gemini`)**: Use for complex research, architectural changes, and debugging.
  - *Example*: `gemini "Explain why FireFaucet is failing login"`
- **GitHub Copilot (`@copilot`)**: Use for specific coding tasks and test generation.
  - *Example*: Assign issue "Add tests for extractor.py" to @copilot.

### Deployment & Consistency

* **Cross-Platform**: Use `pathlib` for all file paths.
- **Proxies**: `ProxyManager` dynamically whitelists the current public IP (Dev or Prod) with 2Captcha to fetch usable proxies (`use_2captcha_proxies=True`).
- **Deployment**: Runs on Azure VM (Linux) via `systemd` service (`faucet_worker.service`). Enforces simple, headless execution.
