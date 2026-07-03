# Contributing to Agent Grey

Thank you for your interest in contributing to Agent Grey, a Django application for systematic grey literature search and review following PRISMA guidelines.

> **Note on the public mirror**: the public repository is a published snapshot of a private
> development repository. Issues and pull requests are welcome here; accepted changes are
> ported into the private repo by a maintainer and appear in the next "Public sync" commit.

## Quick Start for Developers

### Prerequisites
- Python 3.12+
- Node.js 18+ (for Playwright testing)
- Docker & Docker Compose
- Git

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/barrie-cork/agent-grey.git
   cd agent-grey
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements/local.txt
   ```

3. **Set up Node.js dependencies**
   ```bash
   npm install
   npm run install:playwright
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your local settings
   ```

5. **Set up database**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

6. **Run the application**
   ```bash
   python manage.py runserver
   ```

### Using Docker (Alternative)

```bash
docker compose up --build
```

## Project Structure

- `apps/` - Django applications (7 core apps)
- `grey_lit_project/` - Django project settings
- `requirements/` - Python dependencies (base, local, production)
- `templates/` - Django templates
- `static/` - Static assets (CSS, JS, images)
- `docs/` - Project documentation
- `tests/` - Test suites

## Key Features

- **9-state workflow** for systematic literature review
- **PIC framework** (Population, Interest, Context) for search queries
- **Serper API integration** for Google Search execution
- **PRISMA-compliant reporting** with PDF export
- **UUID-based models** for security and scalability
- **Celery background tasks** for search processing
- **>80% test coverage** with comprehensive test suites

## Development Guidelines

1. **Code Quality**
   - Follow PEP 8 standards
   - Write comprehensive tests for new features
   - Use Django best practices (CBVs, proper forms, etc.)

2. **Testing**
   ```bash
   python manage.py test                    # Django tests
   npm run test:playwright                  # E2E tests
   ```

3. **Database**
   - Always use UUID primary keys
   - Follow existing model patterns
   - Create proper migrations

4. **Security**
   - Never commit secrets or credentials
   - Use environment variables for sensitive data
   - Follow OWASP security guidelines

## Getting Help

- Check the documentation in `docs/`
- Review existing code patterns in `apps/`
- Open an issue for bugs or feature requests

## License

This project is licensed under the MIT License.
