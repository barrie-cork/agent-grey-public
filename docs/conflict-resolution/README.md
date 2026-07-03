# Conflict Resolution: Knowledge Base

Research-grounded design principles and implementation plan for Agent Grey's conflict resolution workflow in dual-screening (Workflow #2) systematic reviews.

## Index

| Document | Purpose |
|----------|---------|
| [Research Evidence](research-evidence.md) | Academic literature on consensus-building, Cochrane/PRISMA requirements, cognitive psychology |
| [Tool Landscape](tool-landscape.md) | How Covidence, Rayyan, EPPI-Reviewer, and DistillerSR handle conflict resolution |
| [Current State Audit](current-state-audit.md) | What Agent Grey has today, known bugs, UX gaps |
| [Vision](vision.md) | The ideal user journey and design principles |
| [Implementation Phases](implementation-phases.md) | Phased execution plan: Now / Next / Future |

## Core Design Principle

> A collegial seminar, not a court of law.

The best conflict resolution feels like two academics standing in front of a whiteboard, article in hand, working through the eligibility criteria together. It should feel collaborative, intellectually satisfying, and efficient. The worst version feels like a trial where each side presents their case and a judge rules.

## Context

- **Workflow**: Dual-screening (Workflow #2, `min_reviewers_per_result >= 2`)
- **Detection**: `session.current_configuration.is_workflow_2`
- **Models**: `ConflictResolution`, `ConflictComment`, `RevoteProposal`, `InDiscussionVote`, `InDiscussionVoteResponse`
- **Services**: `ReviewCoordinationService`, `BlindingService`
- **Frontend**: Vue 3 SPA at `/screening/conflicts?session_id=<uuid>`
- **Real-time**: SSE via `conflict_discussion_stream`

## Related Issues

- #85: Multiple conflict resolution bugs (FIXED 2026-02-27, Phase 1)
- #87: Conflict resolution stuck after exclude decision (FIXED 2026-02-27, Phase 1)
- #83: 404 after marking review complete (FIXED)
- #80: IRR not calculating on refresh (FIXED)
- #81: Dashboard shows 0% reviewed for WF2 (FIXED)
- #82: Mark complete shows wrong result counts (FIXED)
