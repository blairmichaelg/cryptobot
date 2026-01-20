# Efficient Delegation Workflow

## Overview

This document outlines the optimal workflow for delegating tasks to AI agents (Gemini and GitHub Copilot) within the `cryptobot` project.

## 1. Task Delegation Strategy

### A. Complex Research & Architecture (Gemini)

Use the `gemini` CLI for tasks requiring broad context, file analysis, or architectural decisions.

- **Command**: `gemini "Your instruction here"`
- **Scope**: Researching API documentation, auditing stricture, refactoring modules, analyzing logs.
- **Example**: `gemini "Audit core/orchestrator.py for race conditions"`

### B. Specific Code Generation (Copilot)

Use GitHub Copilot CLI for generating specific code snippets, unit tests, or small refactors.

- **Command**: `gh copilot suggest "Python script to..."` or `gh copilot explain`
- **Scope**: Regex patterns, shell commands, unit test logic, small function implementations.

## 2. Managing Changes

### Pull Requests

When an agent creates a PR (or when you push changes):

1. **Review**: `gh pr list` to see open items.
2. **Diff**: `gh pr diff <id>` to inspect changes.
3. **Merge**: `gh pr merge <id> --merge --delete-branch` once tests pass.

## 3. Deployment Consistency

To ensure behavior matches between Local and Production:

1. **Tests**: Always run `pytest` before pushing.
2. **Proxies**: Ensure `config/proxies.txt` on the server contains at least one valid base proxy. The `ProxyManager` will auto-generate session-based proxies from it.
3. **Environment**: Use `scripts/check_environment.py` on the VM to verify dependencies and stealth settings.
4. **Service**: Restart the service after deployment: `sudo systemctl restart faucet_worker`.

## 4. Best Practices

- **Atomic Tasks**: Break down large requests into smaller, verifiable steps for agents.
- **Context**: Provide file paths when asking agents to edit code.
- **Verification**: Always verify agent output (run the script, check the syntax) before committing.
