# Task List

## [ ] GitHub Housekeeping

- [ ] Review and merge PR #23 (Core Module Test Coverage)
- [ ] Check and delegate any new urgent issues

## [ ] Deployment Standardization

- [ ] Create `deploy.sh` script for consistent deployment to Azure VM
- [ ] Update `deploy/faucet_worker.service` to ensuring all environment variables are correctly loaded (currently hardcoded paths)
- [ ] Validate `logrotate.conf` usage

## [ ] Security & Stealth Enhancements

- [ ] Remove hardcoded registration proxy from `core/config.py` and move to env vars
- [ ] Implement dynamic User-Agent rotation (replace static list with `fake-useragent` or larger list)
- [ ] Verify 2Captcha Proxy fetching reliability

## [ ] Profitability & Analytics

- [ ] Ensure `WithdrawalAnalytics` is integrated and working
- [ ] Verify `meta.py` CLI provides correct status reports

## [ ] Documentation

- [ ] Update `README.md` with new deployment instructions
