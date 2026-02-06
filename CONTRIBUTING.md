# Contributing to Job Radar

Thanks for your interest in contributing! This guide covers development setup, testing, and PR guidelines.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/<your-username>/job-radar.git
cd job-radar

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Copy config templates
cp .env.example .env
cp config/profile.yaml.example config/profile.yaml
```

## Running Tests

```bash
# Run full test suite
pytest tests/ -v

# Run a specific test file
pytest tests/test_services.py -v

# Run a specific test class
pytest tests/test_services.py::TestTryLinkToJob -v

# Run security tests only
pytest tests/security/ -v
```

All tests use an in-memory SQLite database — no external services needed.

## Project Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a full system overview. Key patterns:

- **Collectors** inherit from `BaseCollector` and implement async `collect()`
- **Services** (`ApplicationService`, `ResumeService`) take a SQLAlchemy session
- **Dashboard pages** use `dashboard/common.py` for shared init
- **Settings** loaded via Pydantic from environment variables

## Code Style

- Python 3.11+ with type hints
- SQLAlchemy 2.0 style queries (`select()` not `session.query()`)
- Async collectors with `aiohttp`
- Streamlit for the dashboard (single-line HTML for `unsafe_allow_html` calls)

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Write tests for new functionality (TDD encouraged)
3. Ensure all tests pass: `pytest tests/ -v`
4. Keep commits focused and well-described
5. Open a PR against `main` with a clear description of changes

## Reporting Issues

Open a GitHub issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Relevant log output
