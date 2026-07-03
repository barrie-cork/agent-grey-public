# Tool Landscape: How Others Handle Conflict Resolution

Comparison of conflict resolution approaches in systematic review tools, plus relevant patterns from deliberation platforms.

## Systematic Review Tools

### Covidence (Market Leader)

**Approach**: Minimal, focused on vote-based resolution.

| Feature | Implementation |
|---------|---------------|
| Conflict detection | Automatic after both reviewers screen |
| Discussion | None built-in (relies on external communication) |
| Blinding | Resolver sees *who* voted but not *how* (forces independent judgment) |
| Resolution | Single click: Include/Exclude by designated resolver |
| Batch flow | Yes -- auto-advances through conflict queue |
| Rationale capture | Optional notes field during initial screening |
| Time-boxing | None |
| Audit trail | Who resolved, when, what decision |

**Strengths**: Fast, simple, no context-switching to external tools for straightforward conflicts.
**Weaknesses**: No threaded discussion. Complex conflicts require email/call side-channels with no record in the tool. No straw polls or re-vote mechanism.

**Key insight**: Covidence's blinding-during-resolution is a genuinely useful pattern. The resolver can't see which reviewer said what, preventing bias toward the more senior person.

### Rayyan

**Approach**: Labels and filtering, minimal conflict resolution.

| Feature | Implementation |
|---------|---------------|
| Conflict detection | Visual indicators in list view |
| Discussion | No in-app discussion |
| Resolution | Manual: one reviewer changes their vote |
| Blinding | "Blind mode" during screening, turns off for resolution |
| Batch flow | Filter to show only conflicts |
| Rationale capture | Labels and notes |

**Strengths**: Clean, fast screening interface. Good labelling system for categorising reasons.
**Weaknesses**: Conflict resolution is essentially "talk it out offline and someone changes their vote." No structured process.

### EPPI-Reviewer

**Approach**: More structured, supports larger review teams.

| Feature | Implementation |
|---------|---------------|
| Conflict detection | Automatic, configurable thresholds |
| Discussion | Comments on individual records |
| Resolution | Reconciliation screen comparing decisions side-by-side |
| Blinding | Configurable per-project |
| Batch flow | Reconciliation queue |
| Rationale capture | Structured coding with predefined categories |

**Strengths**: Structured coding means conflicts can be analysed by category. Good for large reviews with many criteria.
**Weaknesses**: Complex UI. Steep learning curve. Comments aren't threaded.

### DistillerSR

**Approach**: Form-based with configurable conflict handling.

| Feature | Implementation |
|---------|---------------|
| Conflict detection | Automatic, supports multiple levels |
| Discussion | No in-app discussion |
| Resolution | Configurable: majority vote, arbitrator, or consensus forms |
| Blinding | Per-level blinding |
| Batch flow | Level-based workflow (L1 title/abstract, L2 full text) |
| Rationale capture | Structured forms with inclusion/exclusion criteria |

**Strengths**: Highly configurable. Good for teams with strict protocols.
**Weaknesses**: Over-engineered for simple reviews. No real-time discussion.

## Comparison Matrix

| Feature | Covidence | Rayyan | EPPI | DistillerSR | Agent Grey (Current) | Agent Grey (Vision) |
|---------|-----------|--------|------|-------------|---------------------|-------------------|
| In-app discussion | No | No | Basic | No | Yes (threaded) | Yes (criterion-anchored) |
| Straw polls | No | No | No | No | Yes | Yes (improved) |
| Re-vote mechanism | No | No | No | No | Yes | Yes |
| SSE real-time | No | No | No | No | Yes | Yes |
| Blinding in resolution | Partial | No | Config | Config | Yes | Yes (enhanced) |
| Auto-advance | Yes | No | Yes | Yes | No (bug) | Yes |
| Batch progress | Yes | No | Yes | Yes | No | Yes |
| Time-boxing | No | No | No | No | No | Yes |
| Structured prompts | No | Labels | Categories | Forms | No | Yes (exclusion-reason-based) |
| Arbitrator blinding | No | No | Config | Config | No | Yes |
| Rationale during screening | Optional | Labels | Structured | Forms | No | Planned |

## Agent Grey's Differentiator

Agent Grey already has the most sophisticated in-app discussion system of any systematic review tool:
- Threaded comments
- Straw polls (in-discussion votes)
- Formal re-vote proposals with acceptance tracking
- SSE real-time updates
- Multiple resolution methods (consensus, lead arbitration, designated arbitrator, majority)

The gap isn't features -- it's **structure and flow**. The discussion exists but isn't guided. The tools are there but aren't connected into a coherent experience. The research says structure matters more than features.

## Deliberation Platforms (Outside Systematic Review)

### Kialo

**Approach**: Pro/con argument mapping with weighted voting.

Relevant patterns:
- Arguments visually connected to the specific claim they address
- Clear separation between "understanding the argument" and "agreeing/disagreeing"
- Impact voting: "How much did this argument change your thinking?"

### Loomio

**Approach**: Cooperative decision-making with multiple decision types.

Relevant patterns:
- "Proposal" model: someone proposes a resolution, others respond (agree/abstain/disagree/block)
- Discussion phase explicitly separated from decision phase
- "Sense check" (equivalent to straw poll) before formal proposal
- Clear visualisation of where the group stands before committing

### Pol.is

**Approach**: Automated clustering of opinions to find consensus.

Relevant patterns:
- Identifies areas of agreement even among disagreeing groups
- Separates "what we agree on" from "what we disagree about"
- Reduces the feeling of opposition by highlighting common ground first

## Design Patterns Worth Adopting

1. **From Covidence**: Resolver blinding (see who, not how they voted)
2. **From Covidence**: Auto-advance through conflict queue
3. **From EPPI-Reviewer**: Structured coding/categorisation of conflict reasons
4. **From Kialo**: Arguments anchored to specific claims (map to eligibility criteria)
5. **From Loomio**: Explicit phase separation (discuss, then decide)
6. **From Pol.is**: Start with common ground, narrow to disagreement
