---
description: How to delegate tasks to Gemini CLI agent
---

# Gemini CLI Delegation Workflow

This workflow describes how to use Gemini CLI to delegate coding tasks to the Gemini agent for autonomous background work, complementing the existing Copilot delegation.

## Prerequisites

1. **Install Gemini CLI**: `npm install -g @google/gemini-cli`
2. **Authentication**:
    - Recommended: `gemini login` (follows browser prompt)
    - API Key: Set `GEMINI_API_KEY` in your environment.
3. **Verify Installation**: `gemini --version`

## Using Gemini CLI for Delegation

Gemini CLI can be used to perform codebase analysis, generate code, and run tasks.

### Basic Delegation

To delegate a task directly from the terminal:

```bash
gemini "Implement a new faucet module for LitePick.io in faucets/litepick.py"
```

### Context-Aware Delegation

To give Gemini more context about specific files:

```bash
gemini --include "faucets/base.py,IMPLEMENTATION_NOTES.md" "Refactor the base class to improve error handling"
```

### Non-Interactive Mode (for scripts)

```bash
gemini -p "Analyze the latest logs in faucet_bot.log and suggest fixes" --output-format json
```

## Optimization for Cryptobot Project

The Gemini CLI has been optimized for this workspace with the following:

- **Project Awareness**: It knows about the architecture (Gen 3.0), stealth (Camoufox), and solvers.
- **Trusted Folder**: The `cryptobot` root is marked as trusted for safe execution of tests/scripts.
- **Custom Instructions**: System prompts guide Gemini to follow the project's coding standards (standardized `get_balance`, `get_timer`, etc.).

## Best Use Cases

- ✅ **Research**: "Find out why FireFaucet login is failing based on recent logs"
- ✅ **Generation**: "Create a unit test for the new withdrawal analytics module"
- ✅ **Audit**: "Check all faucet modules for compliance with the base class standards"
- ✅ **Optimization**: "Suggest performance improvements for the job scheduler"

## Example Tasks

```bash
# Research and Solve
gemini "The 2Captcha balance is low, check if any faucets are failing due to this and report"

# Code Modification
gemini "Update selectors in faucets/firefaucet.py based on the latest IMPLEMENTATION_NOTES.md"

# Automated Testing
gemini "Run pytest on the solvers directory and fix any issues found"
```

## Monitoring Progress

Gemini CLI usually works synchronously in the terminal, but you can pipe its output to logs:

```bash
gemini "..." > logs/gemini_task.log 2>&1 &
```
