# Task List

## [ ] Deep Analysis & Fixes (Current Priority)

- [x] Fix `NameError: name 'os' is not defined` in `core/proxy_manager.py`
- [x] Standardize Deployment Script (`deploy.sh`) to sync between dev (`blairmichaelg`) and prod (`blazefoley97`)
- [x] Fix Proxy Rotation Logic (Sticky Sessions) to stop reusing dead proxies
- [x] Move hardcoded configs to `.env`

## [ ] GitHub Housekeeping

- [ ] Review and merge PR #23 (Core Module Test Coverage)
- [ ] Check and delegate any new urgent issues

## [ ] Security & Stealth Enhancements

- [x] Remove hardcoded registration proxy from `core/config.py` and move to env vars
- [ ] Implement dynamic User-Agent rotation (replace static list with `fake-useragent` or larger list)
- [ ] Verify 2Captcha Proxy fetching reliability

## [ ] Profitability & Analytics

- [x] Fix `FreeBitcoin` (stop wasting captchas)
- [x] Enable 11+ Pick.io Faucets
- [x] Implement Circuit Breaker for failing faucets
- [ ] Ensure `WithdrawalAnalytics` is integrated and working
- [ ] Verify `meta.py` CLI provides correct status reports

## [ ] Documentation

- [x] Update `README.md` with new deployment instructions
- [x] Add `LICENSE`, `CONTRIBUTING.md`, and `CHANGELOG.md`
- [x] Standardize GitHub Issue Templates
- [x] Consolidate Developer Documentation (`docs/DEVELOPER_GUIDE.md`)
