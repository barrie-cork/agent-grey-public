# Vision: The Ideal Conflict Resolution Experience

## Design Principle

> A collegial seminar, not a court of law.

Two academics standing in front of a whiteboard, article in hand, working through the eligibility criteria together. Collaborative, intellectually satisfying, and efficient. Not a trial where each side presents their case and a judge rules.

## Mental Model

The conflict resolution interface should answer one question at every stage:

**"What does the evidence in this record tell us about the eligibility criteria?"**

Not "who was right?" Not "do you want to change your mind?" The framing matters because it determines whether reviewers engage with the evidence or with each other's positions.

## The Flow: Graduated Escalation

### Stage 0: Prevention

Before conflicts arise, the system helps prevent them:

- Clear eligibility criteria visible during screening (PIC framework sidebar)
- Mandatory brief rationale on every exclude decision (not just a category, but a sentence)
- Pilot screening phase with IRR check (already implemented)
- Ordered exclusion reason hierarchy (reduces reason-disagreement conflicts)

### Stage 1: The Reveal

When both reviewers complete screening and conflicts are detected:

- Each reviewer's *written rationale* is displayed alongside their decision (if collected during screening)
- Blinding lifts only for the conflict context -- you see the other person's decision and reasoning for *this specific record*, not their global screening pattern
- The original source material (title, abstract, URL) is displayed prominently alongside both decisions
- The system identifies and highlights whether this is a decision conflict (include vs exclude) or a reason conflict (same decision, different reasoning)

### Stage 2: Joint Investigation

This is the heart of the experience -- where "thinking together" happens.

**Layout**: Two-column. Left: source material + both decisions with rationale. Right: structured discussion.

**Entry point**: A structured prompt asks "Which criterion is in dispute?" (dropdown directly relating to reasons for exclusion). This:
- Anchors the discussion to evidence, not opinion
- Creates a natural audit trail for PRISMA
- Enables pattern analysis ("we always disagree about government agencies")

**Discussion thread**: Anchored to a specific criterion, not free-floating. The system copy sets the tone: "Help each other understand what the evidence shows" (not "defend your position").

**Temperature check**: Straw polls let the team see where they stand without committing. Presented as "sense check" (borrowed from Loomio), not "vote."

**Time-boxing**: Configurable SLA (default 72 hours, customisable by lead reviewer) with email reminders. Not a hard lock -- a nudge.

### Stage 3: Re-vote

After discussion, each reviewer independently re-casts their vote:

- Fresh, clean voting UI -- not a "change your mind?" prompt
- The framing is "based on the discussion, what is your assessment?" -- normalises updating beliefs
- If now aligned: auto-resolved, celebrated with a positive micro-interaction
- If still split: escalated to arbitration with the discussion record attached

### Stage 4: Arbitration

The designated arbitrator:

- Sees the source material, both original decisions, the discussion thread, and the re-vote results
- Does NOT see who voted which way (Covidence-style blinding for the arbitrator -- reduces bias toward the senior reviewer)
- Makes a binding final decision with mandatory rationale
- Decision is recorded with full audit trail for PRISMA reporting

### Stage 5: Batch Flow

For efficient resolution of many conflicts:

- Auto-advance to the next unresolved conflict after each resolution
- Progress bar: "Resolving 5 of 23 conflicts"
- Keyboard shortcuts for power users (n: next, p: previous, r: resolve)
- "Resolve all similar" option when multiple records share the same criterion dispute (future)

## Information Architecture

### What the Reviewer Sees During Resolution

```
+------------------------------------------------------------------+
| [< Back to list]  Conflict 5 of 23  [Progress: ████░░░░ 17%]    |
+------------------------------------------------------------------+
|                          |                                        |
| SOURCE MATERIAL          | DISCUSSION                             |
| ======================== | ====================================== |
|                          |                                        |
| Title: ...               | Criterion in dispute:                  |
| Authors: ...             | [Exclusion reason ▼]                   |
| Year: ...                |                                        |
| Snippet: (full snippet,  | --- Thread ---                         |
|  scrollable)             |                                        |
|                          | Reviewer A (rationale):                |
|                          | "The study population includes..."     |
| URL: [Open in new tab]   |                                        |
|                          | Reviewer B (rationale):                |
| DECISIONS                | "I interpreted the age range as..."    |
| ======================== |                                        |
|                          | [Add comment]                          |
| Reviewer 1: INCLUDE      |                                        |
| Reason: "Meets P, I, C" | --- Actions ---                        |
|                          |                                        |
| Reviewer 2: EXCLUDE      | [Propose Straw Poll]                   |
| Reason: "Population      | [Propose Re-vote]                      |
| doesn't meet age range"  | [Resolve]                              |
|                          |                                        |
+------------------------------------------------------------------+
```

### What the Arbitrator Sees

Same layout, but:
- Reviewer identities replaced with "Reviewer A" / "Reviewer B"
- Decision labels show decision + reasoning but not identity
- Arbitrator has a "Make Final Decision" button with mandatory rationale field

## Design Tokens

### Colour Semantics

| Colour | Meaning | Usage |
|--------|---------|-------|
| Blue/primary | Active investigation | Current conflict, active discussion |
| Green/success | Agreement/resolved | Consensus reached, conflict resolved |
| Amber/warning | Attention needed | Pending action, approaching SLA |
| Red/danger | Urgent/blocked | Overdue SLA, escalated without response |
| Grey/muted | Informational | Completed items, historical data |

### Micro-interactions

- **Consensus reached**: Subtle confetti or green pulse (not overwhelming, but a moment of satisfaction)
- **Re-vote submitted**: Calm acknowledgement ("Your assessment has been recorded")
- **Auto-advance**: Smooth slide transition to next conflict (not a hard page reload)
- **SLA approaching**: Gentle amber border that doesn't cause anxiety

### Copy Voice

| Instead of... | Say... |
|--------------|--------|
| "Your decision" | "Your assessment" |
| "Defend your position" | "Help each other understand" |
| "Who is correct?" | "What does the evidence show?" |
| "Change your mind" | "Update your assessment based on discussion" |
| "Conflict" (in user-facing copy) | "Disagreement" or "Discussion needed" |
| "Resolution" | "Consensus" or "Final assessment" |

Note: "Conflict" is fine in technical/admin contexts and PRISMA reporting. In the reviewer-facing UI, softer language reduces adversarial framing.

## Non-Goals

Things we deliberately choose NOT to do:

1. **Real-time collaborative editing**: Conflicts benefit from asynchronous, considered responses. Live editing creates pressure to respond quickly.
2. **AI-suggested resolutions**: The value is in the human discussion process. AI suggestions would short-circuit deliberation.
3. **Automatic deadline enforcement**: SLAs should nudge, not lock. Reviewers may have legitimate reasons for delay.
4. **Gamification**: No points, badges, or leaderboards for conflict resolution speed. This is academic work, not a game.
