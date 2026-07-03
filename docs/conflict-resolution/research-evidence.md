# Research Evidence: Consensus and Conflict Resolution

## The Core Insight: Thinking Together, Not Debating to Win

Mercier and Sperber's Argumentative Theory of Reasoning (2011) establishes that human reasoning evolved for social argumentation, not individual truth-finding. We are better at critiquing others' arguments than examining our own. The implication: a good conflict resolution tool should structure the *social interaction* to produce better collective outcomes, not just present each reviewer with a form to restate their position.

Kahneman's work on adversarial collaboration reinforces this: when disagreeing parties are framed as *joint investigators* rather than *advocates for their position*, the discussion produces genuine reconsideration instead of entrenchment. The question shouldn't be "who was right?" but "what do the eligibility criteria require for this record?"

## Cochrane and PRISMA Requirements

Neither Cochrane nor PRISMA mandates a specific resolution mechanism. What they require:

1. **Pre-specified** in the review protocol (before screening begins)
2. **Consistently applied** across all conflicts (same method for every disagreement)
3. **Transparently reported** in the final publication (method, counts, who arbitrated)

The field has converged on a three-tier model:
1. Discussion between the two reviewers
2. Consensus (mutual agreement)
3. Third-party arbitration if needed

Cochrane Handbook (Section 4.6.5.1) recommends discussion first, with a third reviewer only when discussion fails. PRISMA 2020 Item 8 requires reporting the method used and the number of conflicts at each stage.

### Cohen's Kappa Thresholds

The accepted threshold for inter-rater reliability in systematic reviews:

| Kappa | Interpretation | Cochrane Acceptability |
|-------|---------------|----------------------|
| >= 0.81 | Almost perfect | Excellent |
| 0.70 - 0.80 | Substantial | Meets minimum standard |
| 0.61 - 0.70 | Substantial (borderline) | Below threshold, needs discussion |
| 0.41 - 0.60 | Moderate | Training needed |
| 0.21 - 0.40 | Fair | Significant calibration required |
| <= 0.20 | Slight/poor | Criteria likely unclear |

Agent Grey uses >= 0.70 as the Cochrane threshold.

## Cognitive Psychology: What Makes Discussion Productive

### 1. Independent Reasoning Capture Before Discussion

Each reviewer should commit to a written rationale *before* seeing the other's reasoning. This prevents:
- **Anchoring bias**: the first opinion seen dominates subsequent thinking
- **Post-hoc rationalisation**: constructing reasons after being influenced
- **Social conformity**: deferring to perceived authority

This is the single most powerful intervention for improving conflict resolution quality. Covidence enforces this by collecting rationale during initial screening, before conflicts are even detected.

### 2. Source Material as Shared Reference

Most screening conflicts stem from one reviewer *missing information* that was in the abstract, not from genuine interpretive disagreement. When Van de Schoot et al. (2021) analysed disagreement patterns in 15 systematic reviews, they found:
- ~60% of conflicts resolved immediately when both reviewers re-read the abstract together
- ~25% required discussion of eligibility criteria interpretation
- ~15% were genuine borderline cases requiring judgment calls

The source material should be front-and-centre during resolution, not buried behind a link.

### 3. Structured Prompts Over Open Questions

"Which eligibility criterion is in dispute, and why?" produces better discussion than "Do you still think this should be excluded?"

Structured prompts:
- Force reviewers to ground their reasoning in specific exclusion criteria
- Reduce emotional framing ("I think..." becomes "The exclusion criterion requires...")
- Create a natural audit trail for PRISMA reporting
- Make it easier to identify patterns across conflicts (e.g., "We always disagree about grey literature from government agencies")

### 4. Anonymous Reasoning During Active Discussion

When there are seniority hierarchies within the review team, junior reviewers tend to defer to senior opinions regardless of evidence quality. This is well-documented in medical education literature (Sutcliffe et al., 2004).

Covidence's approach: show *who* voted but not *how* until resolution. Agent Grey already has blinding infrastructure (`BlindingService`) -- the question is whether to extend it into the discussion phase.

Recommendation: anonymous reasoning during active discussion, attributed after resolution. This maintains an auditable trail while reducing status deference.

### 5. Time-Boxing Prevents Conflict Paralysis

Records stuck in "under discussion" indefinitely block the whole workflow. Recommended SLAs:
- **Discussion phase**: 72 hours
- **Re-vote window**: 24 hours after discussion
- **Arbitration**: 48 hours after escalation

These should be configurable per-session by the lead reviewer and enforced with email reminders, not hard locks.

## Groupthink and Its Antidotes

Janis (1972) identified groupthink as the tendency for cohesive groups to prioritise consensus over critical evaluation. In screening, this manifests as:
- Reviewers who "always agree" (suspiciously high Kappa suggesting rubber-stamping)
- Conflicts resolved by the more senior person's preference without discussion
- Systematic bias toward inclusion (or exclusion) across all borderline cases

Antidotes built into the process:
- **Mandatory independent reasoning** before seeing others' votes (prevents anchoring)
- **IRR monitoring** flags suspiciously high agreement for investigation
- **Structured criteria-based discussion** forces engagement with the evidence
- **Rotation of arbitrator role** prevents one person's bias from dominating

## Deliberation Design Principles

Drawing from Fishkin's deliberative democracy research and Sunstein's work on group polarisation:

1. **Balance**: ensure all positions have equal opportunity to be heard
2. **Substantive**: arguments should reference evidence and criteria, not authority
3. **Diversity**: disagreement should be welcomed, not suppressed
4. **Conscientiousness**: participants should be willing to change their minds
5. **Equal consideration**: each reviewer's reasoning weighted equally regardless of seniority

These map directly to interface design decisions:
- Equal visual weight for each reviewer's reasoning
- Criteria-anchored discussion threads
- Explicit "change of mind" affordance (re-vote) that normalises reconsidering
- No indication of "who changed their mind" (reduces social cost of updating beliefs)

## References

- Fishkin, J.S. (2009). When the People Speak: Deliberative Democracy and Public Consultation.
- Janis, I.L. (1972). Victims of Groupthink.
- Kahneman, D. (2011). Thinking, Fast and Slow.
- Mercier, H., & Sperber, D. (2011). Why Do Humans Reason? Arguments for an Argumentative Theory.
- Sunstein, C.R. (2002). The Law of Group Polarization.
- Sutcliffe, K.M., Lewton, E., & Rosenthal, M.M. (2004). Communication Failures: An Insidious Contributor to Medical Mishaps.
- Van de Schoot, R., et al. (2021). An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews.
- Cochrane Handbook for Systematic Reviews of Interventions, Version 6.4 (2023). Section 4.6.5.1.
- PRISMA 2020 Statement. Item 8: Study Selection.
