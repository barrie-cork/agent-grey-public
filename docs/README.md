# Agent Grey Documentation

## Quick Navigation

| I want to... | Go to... |
|-------------|----------|
| Understand the full application flow | [architecture/E2E-APPLICATION-FLOW.md](./architecture/E2E-APPLICATION-FLOW.md) |
| Learn the dual-workflow architecture | [workflows/DUAL_WORKFLOW_ARCHITECTURE.md](./workflows/DUAL_WORKFLOW_ARCHITECTURE.md) |
| Browse the API reference | [api/README.md](./api/README.md) |
| Set up my development environment | [development/IDE_SETUP.md](./development/IDE_SETUP.md) |
| Understand code quality standards | [development/CODE_QUALITY.md](./development/CODE_QUALITY.md) |
| Work with Docker | [docker/DOCKER-TROUBLESHOOTING.md](./docker/DOCKER-TROUBLESHOOTING.md) |
| Deploy to production | [deployment/](./deployment/) |
| Learn the Git workflow | [development/git-workflow-guide.md](./development/git-workflow-guide.md) |
| Use the dual-workflow as a reviewer | [user-guide/consensus-discussion-reviewer-guide.md](./user-guide/consensus-discussion-reviewer-guide.md) |
| Understand conflict resolution design | [conflict-resolution/README.md](./conflict-resolution/README.md) |
| Fix migration issues | [guides/MIGRATION_TROUBLESHOOTING.md](./guides/MIGRATION_TROUBLESHOOTING.md) |
| Handle stuck sessions | [runbooks/stuck-sessions.md](./runbooks/stuck-sessions.md) |
| Understand observability (Sentry + /metrics) | [monitoring/README.md](./monitoring/README.md) |
| Review recurring-pattern RCAs | [fixes/](./fixes/) |
| SERP execution reference | [features/features/serp_execution/](./features/features/serp_execution/) |

## Documentation Structure

### Core References

**Architecture, API, and workflow documentation.**

```
architecture/                          # System architecture and decisions
├── E2E-APPLICATION-FLOW.md            # Full end-to-end application flow
├── ADR-001-dual-screening-concurrency.md
├── authentication-backend-architecture.md
├── check-strategy-completion-call-chain.md  # Signal call chain for auto-transition
└── consensus-discussion-architecture.md

api/                                   # API reference and schemas (7 files)
├── README.md                          # API overview
├── DUAL_WORKFLOW_API.md               # Dual-workflow endpoints
├── API-EXAMPLES.md                    # Usage examples
├── consensus-discussion-endpoints.md
├── consensus-discussion-schemas.md
├── openapi.json
└── openapi.yaml

conflict-resolution/                   # Conflict resolution knowledge base
├── README.md                          # Index and context
├── current-state-audit.md             # Models, services, known bugs, UX gaps
├── implementation-phases.md           # Phased execution plan (Phase 1 complete, Phase 2A complete, Phase 2C complete)
├── phase2a-frontend-ux.md            # Phase 2A PRP: source prominence, collegial copy, progress bar
├── phase2b-criterion-prompt.md       # Phase 2B PRP: structured criterion prompt (dropped -- moved to comment-level tags)
├── phase2c-time-boxing.md            # Phase 2C PRP: configurable SLA time-boxing (implemented 2026-02-27)
├── research-evidence.md               # Academic literature review
├── tool-landscape.md                  # Competitor analysis
└── vision.md                          # Ideal user journey and design principles

workflows/                             # Workflow architecture
└── DUAL_WORKFLOW_ARCHITECTURE.md
```

### Development

**Environment setup, code quality, CI/CD, Docker, and Git.**

```
development/                           # Dev environment and standards (11 files)
├── CODE_QUALITY.md                    # Code quality standards and linting
├── IDE_SETUP.md                       # IDE configuration (VS Code, PyCharm)
├── README.md                          # Development overview
├── TEMPLATE-COMMENT-GUIDELINES.md     # Safe Django template comment syntax
├── git-workflow-guide.md              # Git workflow and commit conventions
├── database-migrations-guide.md       # Migration authoring guide
├── migrations-quick-reference.md      # Migration commands cheat sheet
├── ENVIRONMENT-REBUILD-GUIDE.md       # Rebuilding dev environment
├── EDIT-TOOL-VERIFICATION.md
├── ai-code-review.md
└── ci-improvements-summary.md

docker/                                # Docker guides
├── DOCKER-REBUILD-GUIDE.md
└── DOCKER-TROUBLESHOOTING.md

ci-cd/                                 # CI/CD pipeline
├── QUICK-START.md
├── CI-BUILD-OPTIMIZATIONS.md
└── GITHUB-ACTIONS-OPTIMIZATION.md

git/                                   # Git and GitHub
└── github-actions-secrets-context.md
```

### Guides and User Docs

**How-to guides, user documentation, deployment, and troubleshooting.**

```
guides/                                # Step-by-step guides
├── DUAL_WORKFLOW_USER_GUIDE.md        # Dual-workflow user guide
├── MIGRATING_TO_DUAL_WORKFLOW.md      # Migration to dual workflow
├── MIGRATION_TROUBLESHOOTING.md       # Database migration issues
└── ZERO_RESULTS_FIX_GUIDE.md         # Fixing zero results bug

user-guide/                            # End-user documentation
├── consensus-discussion-admin-guide.md
└── consensus-discussion-reviewer-guide.md

deployment/                            # Deployment procedures
├── CELERY-BEAT-DEPLOYMENT-GUIDE.md    # SUPERSEDED: beat now embedded in celery-worker
├── CUSTOM-DOMAIN-SETUP.md
└── nginx-sse-config.md

troubleshooting/                       # Recovery procedures
└── MIGRATION-INCONSISTENCY-RECOVERY.md

runbooks/                              # Operational runbooks
├── TEMPLATE.md
└── stuck-sessions.md
```

### Features and Changes

**Feature implementations, design system, and frontend.**

```
features/                              # Feature implementation docs
├── adaptive-batching/                 # Adaptive batching (3 files)
├── realtime-progress/                 # Real-time progress (3 files)
├── rate-limiting/                     # Rate limiting
├── features/serp_execution/           # SERP execution reference (5 files)
├── reviewer-invitation-workflow.md
└── server-sent-events.md

feature_changes/                       # Feature change records
├── UI/                                # UI changes
├── organisation-accounts-focus-group.md
└── github-releases-next-steps.md

design-system/                         # Design tokens
└── COLOURS.md

frontend/                              # Frontend architecture
└── ARCHITECTURE-DEVIATIONS.md
```

### Quality and Testing

**Testing, code reviews, and security.**

```
testing/                               # Testing docs (5 files)
├── TESTID-NAMING-CONVENTION.md        # Test ID naming standards
├── TESTSPRITE.md                      # TestSprite overview
├── browser-compatibility-matrix.md
├── dual-screening-workflow-test-plan.md
├── sse-manual-testing.md
└── testsprite/                        # TestSprite config

code-reviews/                          # Systematic code review (10 files)
├── dependency-baseline.md             # Cross-app dependency matrix
├── health.md                          # Phase 1A: health app
├── feedback.md                        # Phase 1B: feedback app
├── phase2-identity-layer.md           # Phase 2: accounts + organisation
├── search-strategy.md                 # Phase 3A: search_strategy
├── serp-execution.md                  # Phase 3B: serp_execution
├── results-manager.md                 # Phase 4: results_manager
├── review-system.md                   # Phase 5: review_manager + review_results
├── core.md                            # Phase 6A: core app
└── reporting.md                       # Phase 6B: reporting app

security/                              # Security audits
├── VULNERABILITY-SCAN-ANALYSIS-2025-10-13.md
└── template-tag-xss-review.md
```

### Operations

**Monitoring and recurring-pattern RCAs.**

```
monitoring/                            # Observability (Sentry + custom /prometheus/metrics)
├── README.md                          # Sentry guide + custom metrics; self-hosted stack removed 2026-06-17
└── optimisation-log.md                # Performance history

fixes/                                 # Recurring-pattern RCAs (17 files)
├── COMPREHENSIVE-DEPLOYMENT-GUIDE.md  # Synthesises 7 recurring failure patterns
├── DOCKER-BUILD-CACHE-RCA-2025-10-20.md
├── MIGRATION-CONFLICTS-RCA-2025-10-20.md
├── migration-state-sync-rca-2025-10-20.md
├── migration-inconsistency-rca-2025-11-02.md
├── SQLITE-MIGRATION-COMPATIBILITY.md
├── SEARCH-EXECUTION-DELAY-RCA.md
├── django-test-suite-failures-rca-2025-10-23.md
├── docker-logging-reduction-2025-11-01.md
├── dual-screening-blinding-violation-rca-2025-11-02.md
├── issue-blinding-not-enforced-rca-2025-10-28.md
├── issue-24-frontend-blinding-violations-fix.md
├── issue-16-invited-reviewers-cannot-access-sessions-rca.md
├── e2e-authentication-session-creation-rca-2025-11-02.md
├── e2e-route-persistence-mystery-solved-2025-11-02.md
├── issue-email-configuration-fix-rca.md
└── issue-17-sse-testing-rca.md
```

### Planning and Reference

**Roadmap, prompts, and integrations.**

```
roadmap/                               # Future enhancements
└── consensus-discussion-future-enhancements.md

prompts/                               # AI prompt templates
├── add-testid-attributes.md
└── archive/

MCP/                                   # MCP server docs
├── README.md
├── TESTSPRITE-MCP-SETUP.md
└── zen-mcp-implementation-plan.md

serp/                                  # SERP provider reference
└── google-search-operators.md         # Google operator syntax, filetype rules, known limitations

integrations/                          # External service integration
├── celery/                            # Celery task registration
└── github/                            # GitHub API issues
```

### Archive

**Historical documentation, screenshots, and reports.**

```
archive/
└── session-4ed7286b-report.md

screenshots/                           # Test and UI screenshots
├── test_invalid_email_validation.png
└── test_majority_vote_single_reviewer_validation.png
```

## Documentation Standards

### Creating New Documentation

1. **Choose the right folder**: See structure above
2. **Follow naming conventions**: Use kebab-case (lowercase-with-hyphens)
3. **Use templates**: See [runbooks/TEMPLATE.md](./runbooks/TEMPLATE.md) for runbooks
4. **Cross-reference**: Link to related documentation
5. **Update this README**: Add entry to relevant section

### File Naming Conventions

- **Guides**: Descriptive names (e.g., `zero-results-fix-guide.md`)
- **Feature docs**: Feature name as folder, descriptive file names
- **RCAs**: Descriptive name with date suffix (e.g., `migration-conflicts-rca-2025-10-20.md`)
- **Date suffix**: Use ISO format for dated docs (`*-2025-10-10.md`)
- **Consistency**: Use kebab-case, avoid underscores and mixed case

---

**Last Updated**: 2026-02-27
