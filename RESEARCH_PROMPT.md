# Research Prompt for Gemini/Perplexity
**Copy this entire prompt to Gemini, Perplexity, or ChatGPT for current market research**

---

## Context: What I Have Built

I've created an automated browser bot system with the following capabilities:

### Infrastructure
- **8 Azure VMs** (B1s instances in different regions) configured as rotating proxy servers
- **Main production VM** (DevNode01, Azure West US 2) running 24/7 as a systemd service
- **Proxies**: 8 geographic locations with tinyproxy configuration
- **Monthly cost**: ~$55/month Azure infrastructure

### Technical Capabilities
- **Stealth browser automation**: Camoufox (Firefox-based) with anti-detection features
  - WebRTC hardening
  - Human-like mouse movements and typing
  - Canvas/WebGL fingerprint randomization
  - Session persistence with encrypted cookies
- **Multi-account management**: 12 separate profiles with unique fingerprints
- **Captcha solving**: Integrated 2Captcha and CapSolver APIs (supports Turnstile, hCaptcha, reCaptcha, image captchas)
- **Proxy rotation**: Automatic rotation across 8 IPs with cooldown/burn windows
- **Analytics**: Detailed logging, earnings tracking, performance monitoring
- **Orchestration**: Job scheduler with retry logic, error handling, state persistence

### Tech Stack
- **Language**: Python 3.11+ with asyncio
- **Browser**: Playwright + Camoufox
- **Data**: Pydantic v2 models, JSON persistence
- **Deployment**: systemd service on Linux (Azure Ubuntu VM)
- **Version control**: GitHub with active development

### Current State (as of February 2026)
- ✅ Infrastructure fully operational
- ✅ Anti-detection working
- ✅ Multi-account system functional
- ❌ Previous target (crypto faucets) are unprofitable/dead
- 💰 Need profitable applications for this infrastructure

---

## Research Request

I need **specific, actionable, and current (2026) monetization strategies** that leverage my exact infrastructure. Focus on opportunities that are:

1. **Actually profitable in February 2026** (not outdated advice from 2023-2024)
2. **Require browser automation + proxies + multi-account + captcha solving**
3. **Either passive income OR high-upside opportunities worth the time**
4. **Legal and low-risk** (no obviously illegal activities)

---

## Specific Research Questions

### 1. Crypto Airdrop Farming (PRIORITY)
**Question**: What are the ACTIVE, CONFIRMED crypto airdrops in February 2026 that:
- Accept multiple wallets (Sybil-tolerant or hard to detect)
- Require repeated on-chain transactions or testnet activity
- Have estimated values of $100+ per qualified wallet
- Are still accepting new participants

**What I need**:
- List of 5-10 active airdrops with names and deadlines
- Qualification requirements for each (# of transactions, actions needed)
- Estimated reward range per wallet
- Any known Sybil detection methods to avoid
- Links to official sources or tutorials (Twitter threads, Discord servers, etc.)

### 2. Paid Task Platforms
**Question**: Which micro-task or paid survey platforms in 2026:
- Allow automation (or don't actively detect it)
- Accept workers from multiple accounts/IPs
- Pay in crypto or PayPal
- Have tasks suitable for bots (form filling, data entry, simple clicks)

**What I need**:
- Platform names with current status (active? legit payments?)
- Average pay per task
- Whether they have anti-bot detection
- Current user reviews or Reddit discussions (2026)

### 3. E-commerce Opportunities
**Question**: What e-commerce automation opportunities exist in 2026:
- **Sneaker bots**: Are they still profitable? Which releases are hot?
- **Limited edition drops**: NFTs, collectibles, concert tickets
- **Retail arbitrage**: Automated price monitoring and purchasing
- **Product scalping**: What products have high resale demand?

**What I need**:
- Current state of sneaker bot market (dead or alive?)
- Specific upcoming drops/releases worth targeting
- Required tools or APIs (Discord monitors, etc.)
- Estimated profit margins after fees

### 4. Web Scraping Services
**Question**: What's the demand for web scraping services in 2026:
- Freelance platforms (Fiverr, Upwork) current rates
- Types of scraping in highest demand
- Premium for using multiple geographic IPs (my 8 Azure VMs)
- Legal considerations and common client needs

**What I need**:
- Current Fiverr/Upwork pricing for scraping gigs
- Most requested data types (e-commerce, leads, real estate, etc.)
- How to position "8 geographic locations" as selling point
- Sample gig titles/descriptions that work in 2026

### 5. Social Media Automation
**Question**: Which social media platforms in 2026:
- Allow (or struggle to detect) automation for growth
- Have demand for growth services (followers, engagement)
- Can be monetized via clients or affiliate marketing
- Are worth the risk vs. account bans

**What I need**:
- Current state of Instagram/Twitter/TikTok bot detection (2026)
- Pricing for social media growth services
- Safest automation tactics (warm-up, limits, humanization)
- Alternative platforms (Discord, Telegram, Reddit automation)

### 6. Passive Income Opportunities
**Question**: What passive income can I extract from my 8 VMs in 2026:
- **Bandwidth sharing**: Earnapp, Peer2Profit, Honeygain (still paying? rates?)
- **Proxy reselling**: Can I resell my 8 Azure proxies?
- **Computing power**: Any CPU/GPU rental markets?
- **Network participation**: Helium, Mysterium, other decentralized networks?

**What I need**:
- Current rates per VM/month for each platform
- Which platforms allow cloud VMs (some ban datacenters)
- Expected monthly income from 8 B1s VMs
- Payout minimums and frequency

### 7. Emerging Opportunities (2026-specific)
**Question**: What NEW opportunities emerged in 2025-2026:
- Web3/AI-related income streams
- New bounty programs or testnets
- Platforms that launched recently
- Trends I might not know about

**What I need**:
- Specific names and links
- How to get started
- Estimated effort vs. reward
- Community discussions (Reddit threads, Discord servers)

---

## Output Format I Need

For each opportunity, provide:

```
OPPORTUNITY: [Name]
STATUS: [Active/Dead/Risky]
DIFFICULTY: [Easy/Medium/Hard]
TIME INVESTMENT: [Hours per week]
STARTUP COSTS: [$X or None]
PROFIT POTENTIAL: [$X-Y per month OR $Z one-time]
FITS MY INFRASTRUCTURE: [Yes/No - explain why]
CURRENT 2026 STATUS: [Latest news, is it saturated, any changes]
NEXT STEPS: [1-2-3 specific actions to start]
SOURCES: [Links to recent discussions, official sites, tutorials]
```

---

## Critical Requirements

1. **Must be current as of February 2026** - Don't give me outdated 2023 advice
2. **Verify the opportunity still exists** - Check if platforms closed, airdrops ended, etc.
3. **Include recent community sentiment** - Reddit, Twitter, Discord discussions from last 3 months
4. **Be realistic about profitability** - Don't overhype, I want conservative estimates
5. **Prioritize by best fit** - I have: browser automation, 8 proxies, multi-account, captchas, Python skills

---

## What I DON'T Need

- General advice about "starting a business"
- Suggestions to "just get a job" (I have the infrastructure, want to use it)
- Illegal schemes (carding, account takeovers, fraud)
- Anything requiring significant capital ($1000+)
- Outdated opportunities that died in 2024-2025

---

## Bonus Question

**Is my infrastructure itself valuable?**
- Could I sell this codebase as a product? (SaaS, one-time sale, licensing?)
- What would it be worth?
- Where would I find buyers? (GitHub, marketplaces, forums?)

---

## Example of Good Output

```
OPPORTUNITY: LayerZero Airdrop Farming
STATUS: Active (ending March 2026)
DIFFICULTY: Medium
TIME INVESTMENT: 2-4 weeks per wallet batch
STARTUP COSTS: $50-200 in gas fees per wallet
PROFIT POTENTIAL: $200-1000 per qualified wallet (estimated based on early users)
FITS MY INFRASTRUCTURE: YES - Requires multi-account, proxies, and repeated transactions
CURRENT 2026 STATUS: Still accepting new wallets as of Feb 11, 2026. Community estimates 
  $ZRO airdrop at $0.50-2.00 per token. Need 10-50 cross-chain transactions to qualify.
  Sybil detection concerns but not aggressively enforced yet.
NEXT STEPS:
  1. Research @0xLarry's LayerZero farming guide (Twitter, Jan 2026)
  2. Test with 1 wallet: Bridge $20 ETH → Arbitrum → Polygon via Stargate
  3. Join LayerZero Discord for latest qualification updates
SOURCES:
  - https://twitter.com/0xLarry/status/... (Feb 2026 guide)
  - https://discord.gg/layerzero (official)
  - r/CryptoAirdrop megathread (Feb 2026)
```

---

## Thank You!

I appreciate thorough, current, and well-sourced research. This infrastructure represents hundreds of hours of work - I just need help finding the right market for it.

**Current date**: February 11, 2026  
**My location**: United States (VMs are global, I prefer USD/crypto payments)  
**Risk tolerance**: Medium (willing to experiment, but no obviously illegal stuff)  
**Time available**: 10-20 hours/week to implement profitable strategies
