# Agent Grey

[![Django](https://img.shields.io/badge/Django-5.1.13-green.svg)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Demo-agentgrey.app-brightgreen.svg)](https://agentgrey.app)

## Overview

**Status**: Production - single and dual reviewer screening complete

Agent Grey is a grey literature search and review application aligned with PRISMA 2020 systematic review reporting guidelines. The application helps researchers systematically find, manage, and review non-traditional research sources (government reports, clinical guidelines, policy documents, web resources) that lack structured abstracts and bibliographic metadata.

**🌐 Live Demo**: [https://agentgrey.app](https://agentgrey.app)

**Current Phase**: Deployed and operational - dual-reviewer screening (blinding, conflict resolution, Cohen's Kappa IRR) meets Cochrane standards.

### 🎯 What is Grey Literature?

Grey literature refers to research and information produced by organisations outside of traditional academic and commercial publishing channels. This includes:
- Clinical guidelines and practice recommendations
- Health Technology Assessment (HTA) reports
- Public health strategy reports and policy briefs
- Other evidence synthesis published on websites rather than in journal databases
- Government reports and white papers
- Technical reports from research institutions
- Conference proceedings and presentations
- Dissertations and theses
- Policy documents and working papers

### 🔬 PRISMA 2020 Alignment

Agent Grey aligns with **[PRISMA 2020 (Preferred Reporting Items for Systematic Reviews and Meta-Analyses)](https://www.prisma-statement.org/prisma-2020)** systematic review reporting guidelines, providing:
- Structured search methodology using PIC framework (Population, Interest, Context)
- Systematic result screening and classification based on title/snippet/URL (grey literature adaptation)
- Transparent reporting with flow diagrams
- Standardised export formats for academic publishing
- **NEW**: Dual-reviewer screening with blind independent review (meeting Cochrane standards)

## ✨ Core Features

### MVP Features (Production Ready)
- **🔄 9-State Automated Workflow**: Intelligent progression from draft to completion
- **🎯 PIC Framework**: Population, Interest, Context-based search query builder optimised for grey literature
- **⚡ Automated Search Execution**: Serper API integration for Google Search with background processing
- **📡 Real-Time Updates**: Server-Sent Events (SSE) for instant progress monitoring with automatic polling fallback
- **🤖 Smart Processing Pipeline**: Automated result normalisation, deduplication, and ranking
- **📊 PRISMA 2020 Reporting**: Export reports aligned with systematic review reporting standards
- **👤 Single Reviewer Interface**: Streamlined include/exclude decisions based on title/snippet/URL
- **🔐 Enterprise Security**: UUID primary keys, distributed locking, comprehensive authentication
- **📈 Observability**: Sentry error tracking + custom Prometheus metrics at `/prometheus/metrics`

### Dual Screening (Workflow #2)
- **👥 Dual-Reviewer Screening**: Blind independent review with automatic conflict detection
- **📏 Inter-Rater Reliability**: Cohen's Kappa tracking (≥ 0.70 target)
- **🔀 Conflict Resolution**: Threaded discussion, re-voting, and arbitration workflows
- **🧩 Browser Extension**: Source capture during screening (WXT + Vue 3, token-authenticated ingestion)

## 🚀 Quick Start

### Try the Live Demo

**🌐 Visit**: [https://agentgrey.app](https://agentgrey.app)

Experience Agent Grey without any installation! The live demo is fully functional and includes:
- ✅ Complete PRISMA 2020-aligned workflow
- ✅ Real search functionality (Serper API integration)
- ✅ Sample data and test sessions
- ✅ Full report generation capabilities
- ✅ Enterprise monitoring and performance tracking

**Demo Credentials**: Create your own account or use the demo mode

---

### Local Installation

#### Prerequisites

- **Docker** and **Docker Compose** installed
- **Serper API Key** (required for search functionality) - Get yours at [serper.dev](https://serper.dev)
- **8GB RAM** recommended
- **2GB free disk space**

### Option 1: Easy Installation (Recommended for Non-Developers)

**🎯 One-Command Installation**

1. **Download from Releases**:
   - Visit [Releases Page](https://github.com/barrie-cork/agent-grey/releases/latest)
   - Download: `install.sh`, `docker-compose.yml`, `.env.example`

2. **Run Automated Installer**:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. **Access Agent Grey**:
   - **Application**: http://localhost:8000
   - **Login**: `admin` / `admin123`

The installer automatically:
- ✅ Checks Docker installation
- ✅ Downloads pre-built images (faster than building)
- ✅ Sets up configuration
- ✅ Starts all services
- ✅ Creates admin account

**Benefits:**
- 🚀 **5x faster** - No build time, just download and run
- 🎯 **Non-technical friendly** - Automated setup and validation
- 📦 **Always up-to-date** - Uses latest stable release
- 🔧 **Easy updates** - Simple `docker compose pull` command

### Option 2: Development Installation

For developers who want to modify the code or contribute:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/barrie-cork/agent-grey.git
   cd agent-grey
   ```

2. **Set up environment**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local and add your Serper API key
   nano .env.local
   ```

3. **Start the application**:
   ```bash
   docker compose up -d
   ```

4. **Initialize the database**:
   ```bash
   docker compose exec web python manage.py migrate
   ```

5. **Create admin user**:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

6. **Access the application**:
   - **Main Application**: http://localhost:8000
   - **Admin Panel**: http://localhost:8000/admin/
   - **Celery Monitoring (flower)**: http://localhost:5555 (`--profile monitoring`)
   - **Custom Metrics**: http://localhost:8000/prometheus/metrics (staff/DEBUG-gated)

### Test with Sample Data

```bash
# Load test fixtures (optional)
docker compose exec web python manage.py loaddata fixtures/test_users.json
```

**Test User**: `testadmin` / `admin123`

## 📊 Core Requirements Workflow

### 1. **Define Search Strategy** (PIC Framework)
- **Population**: Define your target population
- **Interest**: Specify research interests/phenomena
- **Context**: Set geographical, temporal, or sectoral context

### 2. **Automated Search Execution**
- Queries generated from PIC inputs
- Automated execution via Serper API
- Real-time progress monitoring via Server-Sent Events (SSE)
- Instant status updates without polling
- Distributed processing with Redis

### 3. **Results Processing**
- Automatic normalisation and deduplication
- URL validation and metadata extraction
- Document type classification (PDF, Word, webpage)
- Smart ranking algorithms

### 4. **Manual Review Interface**
- Streamlined include/exclude decisions
- Tagging system for classification
- Researcher notes and comments
- "Maybe" category for uncertain results

### 5. **PRISMA 2020 Report Generation**
- **PRISMA 2020 Flow Diagram** (PDF, 300 DPI)
- **Full PRISMA 2020 Report** (PDF, CSV, HTML)
- **Study Lists** (CSV, HTML) with essential fields
- **90-day retention** with archive options

## 🏗️ Architecture

### Django Applications

| App | Purpose | Key Models |
|-----|---------|------------|
| **accounts** | UUID-based authentication | User |
| **review_manager** | 9-state workflow orchestration | SearchSession |
| **search_strategy** | PIC framework query builder | SearchQuery |
| **serp_execution** | Serper API integration | SearchExecution |
| **results_manager** | Processing & deduplication | ProcessedResult |
| **review_results** | Manual review interface | SimpleReviewDecision |
| **reporting** | PRISMA 2020-compliant exports | ExportReport |
| **core** | Metrics, monitoring, shared utilities | - |

### 9-State Workflow

| State | Type | Description |
|-------|------|-------------|
| `draft` | Manual | Create session |
| `defining_search` | Manual | Define PIC strategy |
| `ready_to_execute` | Auto | Validation complete |
| `executing` | **AUTO** | API calls via Celery |
| `processing_results` | **AUTO** | Normalise & deduplicate |
| `ready_for_review` | **AUTO** | Processing complete |
| `under_review` | Auto | Review interface accessed |
| `completed` | Manual | Generate reports |
| `archived` | Terminal | Session complete |

States in **bold** transition automatically without user intervention.

## 🔧 Configuration

### Required Environment Variables

```bash
# Core Configuration
SECRET_KEY=your-secret-key-here
DEBUG=True
DJANGO_SETTINGS_MODULE=grey_lit_project.settings.local

# Database (PostgreSQL via Docker)
DATABASE_URL=postgres://postgres:postgres@db:5432/thesis_grey_dev_db

# Redis (Background processing)
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Search API (REQUIRED)
SERPER_API_KEY=your-serper-api-key-here
```

### Optional Configuration

```bash
# Email notifications
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=your-smtp-host
EMAIL_HOST_USER=your-email
EMAIL_HOST_PASSWORD=your-password

# Performance monitoring
LOG_LEVEL=INFO
ENABLE_DEBUG_TOOLBAR=True
```

## 🧪 Testing

### Run All Tests
```bash
docker compose exec web python manage.py test
```

### Run Specific App Tests
```bash
docker compose exec web python manage.py test apps.review_manager
```

### Generate Coverage Report
```bash
docker compose exec web coverage run --source='.' manage.py test
docker compose exec web coverage report
```

## 📈 Performance Specifications

- **Dataset Size**: Handles up to 2,000 results (100 results × 20 queries)
- **Concurrent Users**: Supports 2-3 simultaneous users
- **Search Rate**: 30 requests/minute per user (API limit)
- **Processing Speed**: ~50 results/second batch processing
- **File Sizes**: No limits on report generation
- **Metrics Retention**: 15 days (configurable)
- **Alert Response**: 10s for critical, 30s for warnings

## 📊 Monitoring & Observability

- **Error tracking**: Sentry (SaaS) — exceptions, performance, and release health.
- **Custom application metrics**: `prometheus_client` counters/gauges/histograms in
  `apps/core/metrics/` (search timing, session state transitions, review decisions, etc.),
  exposed at `/prometheus/metrics` — staff/DEBUG-gated, toggled by `PROMETHEUS_METRICS_ENABLED`.
  The endpoint is portable for any external scraper (Grafana Cloud, DigitalOcean, etc.).

```bash
# View custom application metrics (authenticate as staff, or in DEBUG)
curl http://localhost:8000/prometheus/metrics
```

> The self-hosted **Prometheus + Grafana + AlertManager** stack and **`django-prometheus`** were
> removed on 2026-06-17 (dev-only, never run in production). See
> [docs/monitoring/README.md](docs/monitoring/README.md) for the retained Sentry guidance and the
> historical self-hosted setup.

## 🌐 Deployment

Agent Grey is self-hosted with Docker Compose, designed to run behind a reverse proxy or
tunnel that terminates HTTPS.

**Live Instance**: [https://agentgrey.app](https://agentgrey.app)

**Reference production stack**:
- **Web**: Gunicorn + Uvicorn (ASGI), multi-stage Docker build (Vite frontend build included)
- **Background**: Celery workers + Celery beat
- **Data**: PostgreSQL 15, Redis 7
- **Monitoring**: Sentry + custom Prometheus metrics endpoint (`/prometheus/metrics`)

Use `docker-compose.production.yml` as a starting point together with
`.env.production.example`. HTTPS is expected to be terminated upstream; keep
`CSRF_COOKIE_SECURE=True` and `SESSION_COOKIE_SECURE=True` in production.

## 🔍 API Integration

### Serper Search API

Agent Grey uses [Serper](https://serper.dev) for search functionality:

1. **Sign up** at serper.dev
2. **Get API key** from dashboard
3. **Add to environment**: `SERPER_API_KEY=your_key_here`
4. **Budget control**: Optional daily/monthly limits

**API Features Used**:
- Google Search results
- Pagination support (up to 100 results per query)
- Metadata extraction (titles, descriptions, URLs)
- Rate limiting compliance

## 📋 Usage Guide

### Starting a New Review

1. **Login** to the application
2. **Create New Session** from dashboard
3. **Define Search Strategy** using PIC framework:
   - Population: "healthcare workers"
   - Interest: "burnout interventions"
   - Context: "COVID-19 pandemic"
4. **Review Generated Queries** (automatic from PIC inputs)
5. **Set Limits**: Max results per query (default: 100)
6. **Execute Search** - automated processing begins
7. **Monitor Progress** - real-time updates
8. **Review Results** - include/exclude decisions
9. **Generate Reports** - PRISMA-compliant outputs

### Best Practices

- **PIC Specificity**: More specific terms = better results
- **Query Limits**: Start with 50-100 results per query for testing
- **Review Strategy**: Use "maybe" category for uncertain results
- **Documentation**: Add notes during review for transparency
- **Regular Saves**: System auto-saves, but manual checkpoints recommended

## 🛠️ Development

### Project Structure
```
agent-grey/
├── README.md                    # This file
├── docker-compose.yml           # Docker configuration
├── manage.py                    # Django management
├── requirements/                # Dependencies
├── .env.example                 # Environment template
├── apps/                        # Django applications
│   ├── accounts/               # Authentication
│   ├── core/                   # Metrics & shared utilities
│   ├── review_manager/         # Workflow
│   ├── search_strategy/        # PIC framework
│   ├── serp_execution/         # Search API
│   ├── results_manager/        # Processing
│   ├── review_results/         # Review interface
│   └── reporting/              # PRISMA exports
├── docs/                        # Documentation
│   └── runbooks/               # Incident response
├── templates/                   # HTML templates
├── static/                      # CSS, JS, images
└── tests/                       # Test suite
```

### Custom Commands

```bash
# Database management
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py flush

# Development tools
docker compose exec web python manage.py shell
docker compose exec web python manage.py collectstatic
docker compose exec web python manage.py check --deploy

# Observability commands
docker compose --profile monitoring logs flower    # Celery monitoring (flower) logs
curl http://localhost:8000/prometheus/metrics      # Custom application metrics (staff/DEBUG)
```

## 🚨 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **Port 8000 in use** | `docker compose down && docker compose up -d` |
| **Database connection error** | `docker compose restart db && sleep 10` |
| **Celery not working** | `docker compose restart web celery_worker` |
| **Search API error** | Check SERPER_API_KEY in .env.local |
| **Permission denied** | `chmod +x docker/dev-entrypoint.sh` |
| **Pre-built images not found** | Check [latest release](https://github.com/barrie-cork/agent-grey/releases/latest) |
| **/prometheus/metrics 403/404** | Authenticate as staff (or run with DEBUG); ensure `PROMETHEUS_METRICS_ENABLED=True` |

### Installation Method Differences

| Feature | Easy Installation (Option 1) | Development Installation (Option 2) |
|---------|------------------------------|-------------------------------------|
| **Speed** | 🚀 2-3 minutes | ⏳ 10-15 minutes (build time) |
| **Target Users** | Non-developers, end users | Developers, contributors |
| **Updates** | `docker compose pull && up -d` | `git pull && docker compose build` |
| **Customisation** | Limited to configuration | Full source code access |
| **Requirements** | Docker only | Docker + Git + Development tools |

### Debug Commands

```bash
# Check service status
docker compose ps

# View logs
docker compose logs web
docker compose logs celery_worker
docker compose logs db

# Database connection test
docker compose exec web python manage.py dbshell

# Redis connection test
docker compose exec redis redis-cli ping
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Database optimization
docker compose exec web python manage.py optimize_db

# Clear Redis cache
docker compose exec redis redis-cli FLUSHALL
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📞 Support

For questions about Agent Grey:

1. **Try the Live Demo**: [https://agentgrey.app](https://agentgrey.app)
2. **Check Documentation**:
   - Documentation index in [docs/README.md](docs/README.md)
   - App-specific guides in `apps/*/CLAUDE.md`
   - Monitoring guide in [docs/monitoring/README.md](docs/monitoring/README.md)
   - Incident runbooks in `docs/runbooks/`
3. **Search Issues**: Look for similar problems in repository issues
4. **Create Issue**: Provide detailed error messages and steps to reproduce

## 📚 Academic Citation

If you use Agent Grey in your research, please cite:

```bibtex
@software{agent_grey_2025,
  title={Agent Grey: Grey Literature Search and Review Application},
  author={Cork, Barrie},
  year={2025},
  url={https://agentgrey.app},
  repository={https://github.com/barrie-cork/agent-grey},
  note={Production MVP with dual screening features in development}
}
```

---

**🎯 Agent Grey** - Grey literature search and review application aligned with PRISMA 2020 systematic review reporting guidelines.

**🌐 Live Demo**: [https://agentgrey.app](https://agentgrey.app)

**Status**: MVP complete and deployed | Feature additions in progress (Dual Screening)
