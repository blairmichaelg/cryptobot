# Contributing to Crypto Faucet Farm (Gen 3.0)

Thank you for your interest in contributing to the Gen 3.0 Crypto Faucet Farm! This project aims to build a robust, stealthy, and professional-grade automation system.

## 🤝 Getting Started

1. **Fork the Repository**: Start by forking this repo to your own GitHub account.
2. **Clone the Repo**:

    ```bash
    git clone https://github.com/<your-username>/cryptobot.git
    cd cryptobot
    ```

3. **Set Up Environment**:
    We provide a deployment script to handle setup.

    ```bash
    ./deploy/deploy.sh
    ```

    Alternatively, manually:

    ```bash
    python -m venv venv
    source venv/bin/activate  # or venv\Scripts\activate on Windows
    pip install -r requirements.txt
    ```

## 🧪 Running Tests

Before submitting any changes, please ensure all tests pass.

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_proxy_manager.py
```

## 🛠 Development Guidelines

- **Code Style**: We follow standard Python PEP 8 guidelines.
- **Docstrings**: All new functions and classes must have docstrings explaining their purpose, arguments, and return values.
- **Type Hinting**: Use Python type hints (`typing` module) for all function signatures.
- **Logging**: Use `logging.getLogger(__name__)` instead of `print()`.

## 📝 Submitting a Pull Request (PR)

1. **Create a Branch**: `git checkout -b feature/my-new-feature`
2. **Commit Changes**: `git commit -m "feat: add new claim logic for FireFaucet"` (Use conventional commits if possible).
3. **Push**: `git push origin feature/my-new-feature`
4. **Open PR**: Go to the GitHub repository and open a Pull Request.
    - Fill out the PR Template completely.
    - Link any relevant issues.

## 🐛 Reporting Bugs

Please use the **Bug Report** issue template when reporting bugs. Include:

- Steps to reproduce
- Expected vs. actual behavior
- Logs (scrubbed of sensitive info like passwords/API keys)

## 💡 Feature Requests

Have an idea? Use the **Feature Request** issue template to describe:

- The problem you're solving
- Your proposed solution
- Alternatives you've considered

Thank you for helping make this bot better! 🚀
