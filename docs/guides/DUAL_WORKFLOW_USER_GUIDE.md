# Dual-Workflow User Guide

**Version**: 1.0.0
**Date**: November 2025
**Audience**: Researchers, Review Coordinators, Systematic Reviewers

---

## Table of Contents

1. [Introduction](#introduction)
2. [Choosing the Right Workflow](#choosing-the-right-workflow)
3. [Workflow #1: Work Distribution](#workflow-1-work-distribution)
4. [Workflow #2: Independent Screening](#workflow-2-independent-screening)
5. [Resolving Conflicts](#resolving-conflicts)
6. [Understanding IRR Metrics](#understanding-irr-metrics)
7. [FAQ](#frequently-asked-questions)

---

## Introduction

Agent Grey supports two distinct review workflows designed for different research scenarios:

### Workflow #1: Work Distribution
**Best for**: Large datasets, time constraints, efficiency
**Pattern**: Divide results amongst team members - each person reviews different results
**Output**: Fast completion, no inter-rater reliability metrics

### Workflow #2: Independent Screening
**Best for**: PRISMA 2020/Cochrane compliance, systematic reviews
**Pattern**: All reviewers independently review ALL results
**Output**: Quality assurance, Cohen's Kappa IRR metrics, conflict resolution

**Key Point**: These workflows are mutually exclusive per session. Choose one when creating your session.

---

## Choosing the Right Workflow

### Decision Tree

```
Do you need PRISMA 2020 or Cochrane compliance?
├─ YES → Workflow #2: Independent Screening
└─ NO → Continue...
    │
    Do you need inter-rater reliability (Cohen's Kappa) metrics?
    ├─ YES → Workflow #2: Independent Screening
    └─ NO → Continue...
        │
        Do you have >500 results and time constraints?
        ├─ YES → Workflow #1: Work Distribution
        └─ NO → Workflow #2: Independent Screening (safer choice)
```

### Use Cases

| Your Scenario | Recommended Workflow |
|---------------|---------------------|
| Systematic review for publication | **Workflow #2** |
| Clinical guideline development | **Workflow #2** |
| PhD thesis systematic review | **Workflow #2** |
| Meta-analysis | **Workflow #2** |
| Scoping review (exploratory) | **Workflow #1** |
| Literature scan for internal report | **Workflow #1** |
| Large dataset (1000+ results) | **Workflow #1** |

---

## Workflow #1: Work Distribution

### Overview

Divide your results amongst team members to complete the review faster. Each reviewer works on a different subset of results.

### Step-by-Step Instructions

#### Step 1: Create Session with Work Distribution Configuration

1. Navigate to **Create New Session**
2. Fill in session details (title, description)
3. Configure review settings:
   - **Reviewers per Result**: Set to `1` ← **This triggers Workflow #1**
   - **Conflict Resolution**: Not needed (leave blank)
4. Click **Create Session**

#### Step 2: Invite Team Members (Optional)

1. Go to **Session Detail** page
2. Click **Invite Reviewers**
3. Enter email addresses of team members
4. Each receives a magic link invitation (valid 7 days)
5. When they accept, a progress tracker is automatically created

**Note**: You can work alone or with helpers. Helpers see only the results they claim.

#### Step 3: Execute Search and Process Results

1. Define your search strategy (Population, Interest, Context terms)
2. Click **Execute Search**
3. Wait for results to be processed (automated)
4. Session automatically transitions to **Ready for Review**

#### Step 4: Claim and Review Results

**Option A: Vue SPA Work Queue (Recommended)**

1. Navigate to **Review Results** → **Work Queue**
2. Click **Claim Next 10 Results**
3. Review each result:
   - Read title, snippet, URL
   - Choose: **Include**, **Exclude**, or **Maybe**
   - If Exclude, select reason (Not Relevant, Wrong Study Type, etc.)
   - Add notes (optional)
4. **10-Minute Timer**: Complete your batch within 10 minutes or results are auto-released
5. Click **Submit Batch**
6. Repeat until all results reviewed

**Option B: Django Template Interface**

1. Navigate to **Review Results** → **Results Overview**
2. See list of all unreviewed results
3. For each result:
   - Click **Include** or **Exclude** button
   - Result is immediately marked
4. Use pagination to navigate (25/50/100 per page)
5. Export to Excel for offline review if needed

#### Step 5: Track Progress

1. Go to **Session Detail** page
2. View **Reviewer Progress** panel:
   ```
   Alice (You):     180 / 200 (90%)
   Bob (Helper):    150 / 200 (75%)
   Carol (Helper):  200 / 200 (100%) ✅
   ```
3. Each reviewer's progress updates automatically as they submit decisions

#### Step 6: Mark Your Portion Complete

1. When you've reviewed all your results, click **Mark My Review Complete**
2. System validates:
   - ✅ All your claimed results have decisions
   - ⚠️ Warning if incomplete
3. You can't undo this action

#### Step 7: Complete Session

1. **Session Owner Only**: When all invited reviewers complete, click **Complete Session**
2. System validates:
   - ✅ All invited reviewers marked complete
   - ❌ Blocks if anyone incomplete
3. Session transitions to **Completed** status
4. Redirect to PRISMA report generation

---

## Workflow #2: Independent Screening

### Overview

PRISMA 2020/Cochrane compliant dual-screening where all reviewers independently review ALL results. System compares decisions, calculates Cohen's Kappa, and manages conflict resolution.

### Step-by-Step Instructions

#### Step 1: Create Session with Independent Screening Configuration

1. Navigate to **Create New Session**
2. Fill in session details (title, description)
3. Configure review settings:
   - **Reviewers per Result**: Set to `2` or `3` ← **This triggers Workflow #2**
   - **Conflict Resolution Method**: Choose one:
     - **Consensus** - Reviewers discuss until agreement (recommended)
     - **Lead Arbitration** - Lead reviewer makes final decision
     - **Designated Arbitrator** - Third-party expert resolves
     - **Majority Vote** - Requires 3+ reviewers
   - **Blind Screening**: Enable (recommended for PRISMA)
   - **IRR Threshold**: Set to `0.70` (PRISMA 2020 standard)
4. Click **Create Session**

#### Step 2: Invite Independent Reviewers (Required)

1. Go to **Session Detail** page
2. Click **Invite Reviewers**
3. Enter email addresses (at least 2 reviewers)
4. Assign roles (optional):
   - **Primary Reviewer**
   - **Secondary Reviewer**
   - **Arbitrator** (for designated arbitrator method)
5. Send invitations
6. **Important**: All reviewers must accept before review begins

#### Step 3: Execute Search and Process Results

Same as Workflow #1 (Step 3)

#### Step 4: Independent Blinded Review

**Blinding Notice**: When you start reviewing, you'll see:

```
⚠️ BLINDED MODE ACTIVE

Your decisions are hidden from other reviewers until everyone completes.
This ensures independent evaluation for PRISMA compliance.
```

**Review Process**:

1. Navigate to **Review Results** → **Results Overview**
2. You see **ALL 200 results** (same list as other reviewers)
3. For each result:
   - Read title, snippet, URL
   - Choose: **Include**, **Exclude**, or **Maybe**
   - Select **Confidence Level**: High, Medium, or Low
   - If Exclude, select reason
   - Add notes
4. System tracks your progress: `150 / 200 (75%)`
5. **You cannot see** other reviewers' decisions (blinded)

#### Step 5: Mark Your Review Complete

1. When you've reviewed all results, click **Mark My Review Complete**
2. **Warning Modal** appears if incomplete:
   ```
   ⚠️ Incomplete Review Warning

   You have reviewed 150 of 200 results.

   Are you sure you want to mark your review as complete?

   • Your decisions will be locked
   • Results compared with other reviewers when all complete
   • Conflicts may require discussion

   [Cancel] [Accept - Mark Complete]
   ```
3. If you accept:
   - Your decisions are locked (cannot edit)
   - UI shows: **Waiting for other reviewers...**
   - Progress of other reviewers displayed:
     ```
     Reviewer 1 (You): ✅ Complete
     Reviewer 2 (Bob): ⏳ 180 / 200 (90%)
     ```

#### Step 6: Automated Comparison (Triggered When All Complete)

When the last reviewer marks complete, the system automatically:

1. **Detects Conflicts**:
   - Compares all decisions for each result
   - Creates conflict records for disagreements:
     - **INCLUDE vs EXCLUDE** (hardest conflicts)
     - **Different Exclusion Reasons**
     - **Low Confidence** (either reviewer unsure)
   - Shows: `15 conflicts detected across 200 results`

2. **Calculates Inter-Rater Reliability**:
   - Cohen's Kappa for each reviewer pair
   - Interpretation:
     - `>0.70` = Good/Substantial (PRISMA compliant ✅)
     - `0.40-0.70` = Fair/Moderate (⚠️ May need discussion)
     - `<0.40` = Poor/Slight (❌ Recalibration needed)
   - Creates IRR records for PRISMA reporting

3. **Routes to Resolution**:
   - Based on your configured resolution method
   - Email notifications sent to all reviewers

#### Step 7: Resolve Conflicts (Method Dependent)

**Option A: Consensus Method** (Recommended)

1. System redirects to **Conflict Discussion** page (Vue SPA)
2. For each conflict:
   ```
   Conflict #1 of 15

   Result: "Mobile apps for obesity interventions - systematic review"

   Reviewer 1 (You): INCLUDE
   "Relevant intervention study with clear methods"
   Confidence: High

   Reviewer 2 (Bob): EXCLUDE
   "Conference abstract, not full-text article"
   Confidence: Medium

   ═══ Threaded Discussion ═══

   [Start discussion thread]
   ```
3. **Discuss Until Agreement**:
   - Post comments (markdown supported)
   - Reply to specific points (threaded)
   - Real-time updates (SSE - comments appear live)
   - Propose re-vote if needed
4. **Mark Resolved**:
   - When both agree, click **Mark Resolved: INCLUDE** or **EXCLUDE**
   - Final decision recorded
   - Move to next conflict
5. Repeat for all 15 conflicts

**Option B: Lead Arbitration**

1. Lead reviewer sees conflict list
2. Views both decisions side-by-side
3. Selects final decision
4. No discussion required

**Option C: Designated Arbitrator**

1. Third-party arbitrator assigned
2. Reviews conflict independently (blinded from discussion)
3. Makes final decision
4. Higher authority resolution

**Option D: Majority Vote** (3+ Reviewers)

1. System automatically resolves based on majority
2. No manual intervention needed
3. Example: 2 INCLUDE, 1 EXCLUDE → Final: INCLUDE

#### Step 8: Complete Session

1. When all conflicts resolved, click **Complete Session**
2. System validates:
   - ✅ All conflicts status = RESOLVED
   - ✅ Cohen's Kappa calculated
   - ✅ All reviewers completed independent review
3. Session transitions to **Completed** status
4. PRISMA report includes:
   - Cohen's Kappa scores
   - Number of conflicts and resolution method
   - Consensus discussion summary (if applicable)
   - Full audit trail

---

## Resolving Conflicts

### Consensus Discussion Best Practices

**Tips for Productive Consensus**:

1. **Be Specific**: "I excluded this because it's a conference abstract, not peer-reviewed full-text" is better than "Doesn't meet criteria"
2. **Cite Evidence**: Reference inclusion/exclusion criteria
3. **Ask Questions**: "Did you see the methods section on page 3?" encourages re-evaluation
4. **Propose Re-vote**: If new information emerges, use **Propose Re-vote** button
5. **Document Reasoning**: Future you (and peer reviewers) will thank you

**Markdown Support**:

```markdown
I think we should **include** this study because:

1. It meets the population criteria (adults with BMI >30)
2. The intervention is clearly described
3. Full-text is available

However, I see your concern about the conference abstract.
I found the full-text here: [Link to PDF]
```

**Common Conflict Types**:

| Conflict Type | Resolution Strategy |
|---------------|-------------------|
| **INCLUDE vs EXCLUDE** | Review inclusion criteria together, cite specific points |
| **Different Exclusion Reasons** | Discuss which reason is primary, document both if applicable |
| **Low Confidence** | More thorough review, search for additional information |

### Real-Time Updates

Comments appear instantly (< 2s latency) via Server-Sent Events (SSE). No need to refresh the page.

---

## Understanding IRR Metrics

### What is Cohen's Kappa?

Cohen's Kappa (κ) measures agreement between reviewers beyond chance. It ranges from -1.0 to 1.0.

**Interpretation** (based on Landis & Koch, 1977):

| Kappa Value | Interpretation | Action |
|-------------|---------------|--------|
| 0.81 - 1.00 | Almost Perfect | ✅ Excellent agreement |
| 0.61 - 0.80 | Substantial | ✅ Good agreement |
| 0.41 - 0.60 | Moderate | ⚠️ Acceptable, but discuss patterns |
| 0.21 - 0.40 | Fair | ⚠️ Review training, recalibrate |
| 0.00 - 0.20 | Slight | ❌ Poor agreement, restart needed |
| < 0.00 | Worse than Chance | ❌ Systematic disagreement |

**PRISMA 2020 Standard**: κ ≥ 0.70 recommended for systematic reviews

### Viewing IRR Metrics

1. Navigate to **Team Dashboard**
2. Scroll to **Inter-Rater Reliability** section
3. View table:
   ```
   Reviewer Pair       | Kappa | Interpretation | Agreement %
   --------------------|-------|----------------|------------
   Alice ↔ Bob         | 0.85  | Almost Perfect | 92%
   Alice ↔ Carol       | 0.72  | Substantial    | 85%
   Bob ↔ Carol         | 0.68  | Substantial    | 82%
   ```
4. **Confusion Matrix** shows:
   - Both Include: 150
   - Both Exclude: 30
   - Disagreements: 20

### Low Kappa Alert

If Kappa < 0.70, you'll receive email notification:

```
Subject: IRR Threshold Alert - Session #ABC123

Cohen's Kappa: 0.55 (Moderate)
Threshold: 0.70

Recommendation:
1. Review inclusion/exclusion criteria together
2. Discuss patterns in disagreements
3. Consider recalibration session
4. Document reason for lower IRR in PRISMA report if proceeding
```

---

## For Session Owners: Monitoring Review Progress

### Viewing Cohen's Kappa

All reviewers can see the session-wide Cohen's Kappa metric in the right panel of the results overview page.

**To refresh Kappa**:
1. Navigate to the session's results overview page
2. Look for the "Inter-Rater Reliability" widget in the right sidebar
3. Click the **Refresh** button to update with latest calculations

**Interpreting Kappa**:
- **≥0.70** (Green): Acceptable agreement - PRISMA compliant, proceed with confidence
- **0.40-0.69** (Yellow): Moderate agreement - consider team calibration before continuing
- **<0.40** (Red): Poor agreement - calibration meeting required before proceeding

The widget shows:
- Session-wide average Cohen's Kappa
- Percentage agreement across all reviewer pairs
- Total number of result comparisons
- Whether the session meets Cochrane quality standards (≥0.70)

### Viewing Conflicts Early (Session Owners Only)

As a session owner, you can view conflicts **during the review phase** to identify calibration needs, even before all reviewers have completed their assessments.

**What you can see**:
- List of results with conflicts between reviewers
- Type of conflict (INCLUDE_EXCLUDE, EXCLUSION_REASON, LOW_CONFIDENCE)
- Your own decision (if you reviewed that result)
- Number of reviewers who have decided (e.g., "2 of 3 reviewers")
- Current conflict status (PENDING, IN_DISCUSSION, RESOLVED)

**What you cannot see** (unless you are also an arbitrator):
- Individual reviewers' decisions
- Reviewers' names associated with decisions
- Reviewers' notes or justifications

**To view conflicts early**:
1. Go to your session's overview page
2. Click the **"View Conflicts"** button in the right panel
3. Browse the conflict list in blinded mode
4. Use this information to plan calibration meetings

**Important Note**: Regular reviewers cannot access conflicts until all reviews are complete. Only session owners and arbitrators have early access, and all access is logged for PRISMA audit compliance.

### When to Schedule Calibration

Consider scheduling a team calibration meeting if you observe any of the following:

**Based on Cohen's Kappa**:
- Kappa score below 0.70 (Cochrane threshold)
- Declining Kappa trend over time
- Large variance between reviewer pairs

**Based on Conflict Patterns**:
- High number of INCLUDE_EXCLUDE conflicts
- Frequent disagreements on exclusion reasons
- Recurring conflicts on specific types of results (e.g., policy documents vs. clinical guidelines)
- Low confidence decisions becoming conflicts

**Calibration Meeting Best Practices**:
1. **Prepare**: Review 5-10 conflict examples before the meeting
2. **Discuss**: Focus on understanding different interpretations of inclusion criteria
3. **Align**: Clarify ambiguous criteria and document decisions
4. **Practice**: Review 2-3 new results together to verify alignment
5. **Document**: Update session notes with clarified criteria
6. **Re-measure**: Check Kappa after 20-30 additional reviews to confirm improvement

**After Calibration**:
- Monitor Kappa for next 50 results
- If Kappa remains below 0.70, consider revising inclusion criteria
- Document calibration sessions and IRR scores in PRISMA report
- Low IRR with documented calibration is acceptable if inclusion criteria are inherently subjective

---

## Frequently Asked Questions

### General Questions

**Q: Can I switch workflows mid-session?**

A: No. Workflows are mutually exclusive per session. If you need to switch, create a new session with the desired configuration.

**Q: What if a reviewer drops out?**

A:
- **Workflow #1**: Their claimed results are automatically released for reassignment
- **Workflow #2**: Cannot complete without all reviewers. Invite replacement reviewer.

**Q: Can I review offline?**

A: Yes, for **Workflow #1** only. Export results to Excel, review offline, import decisions. **Workflow #2** requires online review for blinding.

### Workflow #1 Questions

**Q: How does the 10-minute timer work?**

A: When you claim a batch of 10 results, you have 10 minutes to complete. If time expires, results are released for others to claim. Prevents bottlenecks.

**Q: Can I claim more than 10 results at a time?**

A: No. Batch size is fixed at 10 for fairness and to prevent work-hoarding.

**Q: What if I accidentally mark the wrong decision?**

A: Django template mode: You can change your decision before marking complete. Vue SPA mode: Release batch and reclaim to start over.

### Workflow #2 Questions

**Q: Why can't I see the other reviewer's decisions?**

A: **Blinding** ensures independent evaluation. Decisions are revealed only after all reviewers mark complete. This is a PRISMA 2020 requirement.

**Q: What if we can't reach consensus?**

A:
1. Use **Propose Re-vote** if new information emerges
2. Escalate to **Lead Arbitration** (session owner makes final decision)
3. Assign **Designated Arbitrator** (third-party expert)

**Q: Do we have to resolve ALL conflicts?**

A: Yes. Session cannot be completed until all conflicts have status = RESOLVED. This ensures complete audit trail.

**Q: Can I change my decision after marking complete?**

A: No. Decisions are locked after completion to maintain audit trail integrity. Use **Propose Re-vote** during consensus discussion if needed.

### IRR Questions

**Q: What if our Kappa is < 0.70?**

A: Document the reason in your PRISMA report. Common reasons:
- Complex inclusion criteria requiring interpretation
- Edge cases in grey literature (lack of full abstracts)
- Reviewer training needed
- Acceptable if consensus reached on all conflicts

**Q: Is Cohen's Kappa required for all systematic reviews?**

A: PRISMA 2020 recommends reporting IRR metrics. Cochrane requires it. Check your journal's submission guidelines.

**Q: How is Kappa different from simple agreement percentage?**

A: Agreement percentage doesn't account for chance. If you both exclude 90% of results, high agreement is expected by chance. Kappa corrects for this.

---

## Support and Resources

**Documentation**:
- Technical Architecture: `docs/workflows/DUAL_WORKFLOW_ARCHITECTURE.md`
- API Documentation: `docs/api/DUAL_WORKFLOW_API.md`
- Migration Guide: `docs/guides/MIGRATING_TO_DUAL_WORKFLOW.md`

**External Resources**:
- [PRISMA 2020 Guidelines](https://www.prisma-statement.org/prisma-2020)
- [Cochrane Handbook](https://training.cochrane.org/handbook)
- [Cohen's Kappa Interpretation (Landis & Koch, 1977)](https://doi.org/10.2307/2529310)

**Questions or Issues?**:
- Email: support@agent-grey.example.com
- Slack: #agent-grey-support
- GitHub: Submit issue with label `user-guide`

---

**Document Version**: 1.0.0
**Last Updated**: November 2025
**Next Review**: March 2026
