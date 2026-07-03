# Consensus Discussion: Administrator Guide

**Version:** 1.0
**Last Updated:** 21 October 2025
**Audience:** Search Session Managers and System Administrators

---

## Table of Contents

1. [Introduction](#introduction)
2. [Administrator Responsibilities](#administrator-responsibilities)
3. [Setting Up Dual Screening](#setting-up-dual-screening)
4. [Reviewer Assignment](#reviewer-assignment)
5. [Monitoring Conflicts](#monitoring-conflicts)
6. [Intervention Procedures](#intervention-procedures)
7. [Understanding Inter-Rater Reliability (IRR)](#understanding-inter-rater-reliability-irr)
8. [Managing Arbitration](#managing-arbitration)
9. [PRISMA Reporting Requirements](#prisma-reporting-requirements)
10. [Email Notification Management](#email-notification-management)
11. [Troubleshooting Common Issues](#troubleshooting-common-issues)
12. [System Configuration](#system-configuration)
13. [Best Practices](#best-practices)

---

## Introduction

This guide explains how to administer Consensus Discussion workflows for systematic review search sessions. As a session manager, you are responsible for:

- Setting up dual screening correctly
- Assigning reviewers appropriate roles
- Monitoring conflict resolution progress
- Intervening when necessary
- Ensuring PRISMA compliance
- Managing the arbitration process when consensus cannot be reached

This guide assumes you have session manager or administrator permissions in Agent Grey.

---

## Administrator Responsibilities

### Core Responsibilities

1. **Configuration**
   - Enable dual screening for search sessions
   - Configure conflict detection rules
   - Set up email notification preferences

2. **Reviewer Management**
   - Assign PRIMARY and SECONDARY reviewers
   - Assign ARBITRATOR roles when needed
   - Monitor reviewer workload and performance

3. **Conflict Monitoring**
   - Track conflict resolution rates
   - Identify stalled discussions
   - Monitor time-to-consensus metrics

4. **Intervention**
   - Escalate conflicts to arbitration when needed
   - Reassign conflicts if reviewers are unresponsive
   - Resolve technical issues

5. **Quality Assurance**
   - Monitor inter-rater reliability (Cohen's Kappa)
   - Review consensus discussions for quality
   - Ensure PRISMA reporting requirements are met

6. **Reporting**
   - Generate PRISMA flow diagrams
   - Export conflict resolution data
   - Document arbitration decisions

---

## Setting Up Dual Screening

### Prerequisites

Before enabling consensus discussion:
1. Ensure search execution is complete
2. Confirm results are ready for screening
3. Identify at least two qualified reviewers

### Configuration Steps

#### Step 1: Access Session Settings

1. Navigate to your Search Session dashboard
2. Click on **"Session Settings"** or **"Configure Screening"**
3. Locate the **"Screening Method"** section

#### Step 2: Enable Dual Screening

1. Select **"Dual Screening"** as the screening method
2. Choose conflict detection mode:
   - **Strict** (recommended): Only INCLUDE vs EXCLUDE creates conflicts
   - **Moderate**: MAYBE decisions also trigger conflicts if not unanimous

#### Step 3: Configure Conflict Resolution Options

Set preferences for:
- **Automatic Consensus Detection**: Enable (recommended)
- **Re-Vote Expiry Time**: Default is 48 hours
- **Email Notifications**: Enable for all conflict events
- **Arbitration Trigger**: Automatic after X days or manual only

#### Step 4: Save Configuration

Click **"Save Settings"** to apply changes.

---

## Reviewer Assignment

### Reviewer Roles

#### PRIMARY Reviewer
- **Purpose**: First reviewer to screen results
- **Responsibilities**: Make independent screening decisions
- **Access**: Can see and vote on all assigned results
- **Number**: Typically 1 per session

#### SECONDARY Reviewer
- **Purpose**: Second reviewer for dual screening
- **Responsibilities**: Make independent screening decisions without seeing PRIMARY's votes
- **Access**: Same as PRIMARY, but blinded to PRIMARY decisions until both vote
- **Number**: Typically 1 per session (same person screens all results)

#### ARBITRATOR
- **Purpose**: Break ties when consensus cannot be reached
- **Responsibilities**: Review discussion, make final binding decision
- **Access**: Can see all decisions and discussions
- **Number**: 1-2 per session (assigned as needed)

### Assignment Process

#### Step 1: Navigate to Reviewer Management

1. Go to Search Session dashboard
2. Click **"Manage Reviewers"** or **"Reviewer Assignment"**

#### Step 2: Add Reviewers

For each reviewer:
1. Click **"Add Reviewer"**
2. Search for the user by name or email
3. Select the reviewer role (PRIMARY, SECONDARY, or ARBITRATOR)
4. Set assignment parameters:
   - **Screening Stage**: Grey Literature Screening (Title/Snippet/URL)
   - **Assignment Type**: All results or specific subset
5. Click **"Assign Reviewer"**

#### Step 3: Verify Assignments

Check that:
- All results have both PRIMARY and SECONDARY reviewers assigned
- Reviewer workloads are balanced
- ARBITRATOR is available if needed

#### Step 4: Notify Reviewers

Send email notifications to reviewers informing them of their assignment:
1. Click **"Notify All Reviewers"**
2. Customise notification message if needed
3. Click **"Send Notifications"**

### Best Practices for Reviewer Assignment

1. **Independent Screening**: Ensure PRIMARY and SECONDARY reviewers work independently
2. **Expertise Balance**: Assign reviewers with complementary expertise
3. **Workload Management**: Monitor screening progress and redistribute if needed
4. **Arbitrator Selection**: Choose experienced reviewers with strong domain knowledge
5. **Training**: Ensure all reviewers understand the inclusion/exclusion criteria

---

## Monitoring Conflicts

### Accessing the Conflicts Dashboard

1. Navigate to Search Session dashboard
2. Click **"Conflicts"** tab or **"Conflict Monitor"**
3. View the conflicts dashboard

### Key Metrics

#### Conflict Rate
- **Definition**: Percentage of results with conflicting decisions
- **Target**: 10-20% is typical for well-defined criteria
- **High Rate (>30%)**: May indicate unclear inclusion criteria
- **Low Rate (<5%)**: May indicate reviewers are not independent

#### Time to Consensus
- **Definition**: Average time from conflict detection to resolution
- **Target**: <7 days for most conflicts
- **Monitoring**: Flag conflicts open >14 days

#### Consensus Method
Track how conflicts are being resolved:
- **Discussion Only**: Consensus through comments (ideal)
- **Re-Vote**: Consensus through re-voting (common)
- **Arbitration**: Third-party decision (should be <20%)

#### Inter-Rater Reliability (see dedicated section)
- **Cohen's Kappa**: Statistical measure of agreement
- **Target**: ≥0.70 (Cochrane minimum)

### Conflict List View

The conflicts dashboard shows:
- **Status**: PENDING, IN_DISCUSSION, RESOLVED
- **Result Details**: Title, URL, organisation
- **Reviewers**: Who is involved in each conflict
- **Last Activity**: When the last comment or action occurred
- **Discussion Count**: Number of comments posted
- **Re-Vote Status**: Whether a re-vote is active

### Filtering and Sorting

Use filters to focus on specific conflicts:
- **Status Filter**: Show only PENDING or IN_DISCUSSION
- **Age Filter**: Show conflicts older than X days
- **Reviewer Filter**: Show conflicts involving specific reviewers
- **Sort Options**: By age, activity, result title

### Export Options

Export conflict data for external analysis:
1. Click **"Export Conflicts"**
2. Choose format: CSV, Excel, or PDF
3. Select fields to include
4. Click **"Download"**

---

## Intervention Procedures

### When to Intervene

Intervene when:
1. **Stalled Discussion**: No activity for >7 days
2. **Unproductive Argument**: Reviewers are not making progress
3. **Reviewer Unresponsive**: One reviewer has not participated
4. **Technical Issues**: System errors preventing resolution
5. **Urgent Resolution Needed**: Time-sensitive project requirements

### Intervention Options

#### Option 1: Send Reminder

1. Navigate to the specific conflict
2. Click **"Send Reminder"**
3. Customise reminder message
4. Select recipients (all reviewers or specific reviewer)
5. Click **"Send"**

#### Option 2: Post Administrative Comment

1. Navigate to the conflict discussion page
2. Post a comment as the administrator:
   - Clarify inclusion/exclusion criteria
   - Provide additional context
   - Suggest a path forward
   - Set a deadline for resolution

#### Option 3: Escalate to Arbitration

If consensus cannot be reached:
1. Navigate to the conflict
2. Click **"Escalate to Arbitration"**
3. Assign an arbitrator from the dropdown
4. Add notes explaining why arbitration is needed
5. Click **"Assign Arbitrator"**

The arbitrator will receive an email notification and can review the discussion to make a final decision.

#### Option 4: Reassign Conflict

If a reviewer is unresponsive or unavailable:
1. Navigate to the conflict
2. Click **"Reassign Reviewer"**
3. Select the reviewer to replace (PRIMARY or SECONDARY)
4. Choose a new reviewer from the dropdown
5. Add reassignment notes
6. Click **"Reassign"**

The new reviewer will see the original decision but can vote independently.

#### Option 5: Override Decision

In rare cases, an administrator may need to override a conflict:
1. Navigate to the conflict
2. Click **"Administrative Override"**
3. Select final decision (INCLUDE or EXCLUDE)
4. Provide detailed justification (this will be part of the audit trail)
5. Click **"Override"**

**Warning**: Use overrides sparingly. They bypass the consensus process and should be reserved for exceptional circumstances (e.g., obvious errors, project deadlines).

---

## Understanding Inter-Rater Reliability (IRR)

### What is IRR?

Inter-Rater Reliability measures the level of agreement between two reviewers. In systematic reviews, it is typically measured using **Cohen's Kappa (κ)**.

### Cohen's Kappa Scale

- **κ < 0.00**: Poor agreement (worse than chance)
- **κ = 0.00-0.20**: Slight agreement
- **κ = 0.21-0.40**: Fair agreement
- **κ = 0.41-0.60**: Moderate agreement
- **κ = 0.61-0.80**: Substantial agreement
- **κ = 0.81-1.00**: Almost perfect agreement

**Cochrane Minimum**: κ ≥ 0.70 (substantial agreement)

### Accessing IRR Reports

1. Navigate to Search Session dashboard
2. Click **"IRR Report"** or **"Inter-Rater Reliability"**
3. View Cohen's Kappa scores for each reviewer pair

### Interpreting IRR Results

#### High IRR (κ ≥ 0.70)
- **Interpretation**: Good agreement, criteria are clear
- **Action**: No action needed, monitoring only

#### Moderate IRR (κ = 0.50-0.69)
- **Interpretation**: Acceptable but improvable
- **Action**:
  - Review conflicts to identify patterns
  - Clarify inclusion/exclusion criteria
  - Provide additional training if needed

#### Low IRR (κ < 0.50)
- **Interpretation**: Poor agreement, criteria unclear or reviewers need training
- **Action**:
  - Conduct additional reviewer training
  - Revise and clarify inclusion/exclusion criteria
  - Consider re-screening with updated criteria
  - Discuss specific disagreements with reviewers

### Factors Affecting IRR

1. **Criteria Clarity**: Vague criteria lead to low IRR
2. **Reviewer Training**: Insufficient training reduces agreement
3. **Result Ambiguity**: Grey literature often has limited information
4. **Reviewer Experience**: Inexperienced reviewers may have lower IRR
5. **Fatigue**: Screening fatigue can reduce agreement

### Improving IRR

1. **Pilot Screening**: Have reviewers screen 50-100 results together first
2. **Calibration Meetings**: Discuss disagreements and refine understanding
3. **Criteria Refinement**: Update inclusion/exclusion criteria based on pilot
4. **Regular Check-ins**: Monitor IRR throughout screening, not just at the end

---

## Managing Arbitration

### When Arbitration is Needed

Arbitration is required when:
1. Consensus cannot be reached through discussion
2. Discussion has stalled for >14 days
3. Reviewers explicitly request arbitration
4. Re-votes have not resolved the conflict

### Assigning an Arbitrator

1. Navigate to the conflict
2. Click **"Assign Arbitrator"**
3. Select an arbitrator from the dropdown:
   - Must have ARBITRATOR role
   - Should not have prior involvement in the conflict
   - Should have relevant domain expertise
4. Add assignment notes
5. Click **"Assign"**

### Arbitration Process

1. **Notification**: Arbitrator receives email with conflict details and discussion history
2. **Review**: Arbitrator reviews:
   - Original decisions from both reviewers
   - Complete discussion thread
   - The search result itself
   - Inclusion/exclusion criteria
3. **Decision**: Arbitrator makes final decision (INCLUDE or EXCLUDE)
4. **Justification**: Arbitrator provides rationale for decision
5. **Resolution**: Conflict status changes to RESOLVED, audit trail preserved

### Arbitrator Guidelines

Provide arbitrators with these guidelines:
1. **Read Everything**: Review the complete discussion history
2. **Check Criteria**: Verify decisions against inclusion/exclusion criteria
3. **Be Objective**: Base decision on evidence, not preferences
4. **Document Reasoning**: Provide clear justification
5. **Respect Both Views**: Acknowledge valid points from both reviewers

### Monitoring Arbitration

Track arbitration metrics:
- **Arbitration Rate**: Percentage of conflicts requiring arbitration (target: <20%)
- **Arbitrator Consistency**: Whether arbitrator tends to favour one reviewer
- **Time to Decision**: How long arbitration takes (target: <7 days)

### High Arbitration Rates

If >20% of conflicts require arbitration:
1. **Review Criteria**: Criteria may be too vague or complex
2. **Additional Training**: Reviewers may need more guidance
3. **Calibration**: Conduct calibration exercises with all reviewers
4. **Criteria Refinement**: Update inclusion/exclusion criteria

---

## PRISMA Reporting Requirements

### Why PRISMA Compliance Matters

PRISMA 2020 requires systematic reviews to:
- Document the number of conflicts detected
- Report how conflicts were resolved (discussion, arbitration, etc.)
- Calculate and report inter-rater reliability
- Maintain a complete audit trail

Consensus Discussion is designed to meet these requirements automatically.

### Data Required for PRISMA Reporting

#### 1. Conflict Statistics
- Total number of results screened
- Number of conflicts detected
- Conflict rate (%)

#### 2. Resolution Methods
- Number resolved through discussion only
- Number resolved through re-vote
- Number resolved through arbitration
- Number resolved through administrative override

#### 3. Inter-Rater Reliability
- Cohen's Kappa (κ) for each reviewer pair
- Overall agreement percentage

#### 4. Timeframes
- Average time from conflict detection to resolution
- Range of resolution times

### Generating PRISMA Reports

#### Step 1: Access Reporting Module

1. Navigate to Search Session dashboard
2. Click **"Reports"** or **"PRISMA Report"**

#### Step 2: Select Report Type

Choose from:
- **PRISMA Flow Diagram**: Visual representation of screening process
- **Conflict Resolution Report**: Detailed statistics on conflicts
- **IRR Report**: Cohen's Kappa and agreement metrics
- **Complete Audit Trail**: Full export of all decisions and discussions

#### Step 3: Configure Report

Set parameters:
- **Date Range**: All data or specific period
- **Screening Stage**: Grey Literature Screening (single-stage)
- **Include Details**: Summary only or full details
- **Format**: PDF, Excel, or Word

#### Step 4: Generate and Export

1. Click **"Generate Report"**
2. Wait for report generation (may take a few minutes for large sessions)
3. Click **"Download"** to save the report

### PRISMA Flow Diagram Elements

Ensure your flow diagram includes:
- Number of records screened by PRIMARY reviewer
- Number of records screened by SECONDARY reviewer
- Number of conflicts detected
- Number of conflicts resolved through discussion
- Number of conflicts resolved through arbitration
- Final number of records included/excluded

### Audit Trail Export

For maximum transparency, export the complete audit trail:
1. Navigate to **"Export"** section
2. Select **"Complete Audit Trail"**
3. Choose format: Excel (for analysis) or PDF (for archiving)
4. Click **"Export"**

The audit trail includes:
- All reviewer decisions (original and re-votes)
- Complete discussion threads
- Re-vote proposals and acceptances
- Arbitration decisions
- Administrative actions
- Timestamps for all events

---

## Email Notification Management

### Email Notification Types

The system sends automatic emails for:
1. **Reviewer Assignment**: When a reviewer is assigned to a session
2. **Conflict Detected**: When a new conflict is identified
3. **Comment Posted**: When someone posts a comment
4. **Reply Posted**: When someone replies to your comment
5. **Re-Vote Proposed**: When a re-vote is proposed
6. **Re-Vote Accepted**: When all reviewers accept a re-vote proposal
7. **Consensus Reached**: When a conflict is resolved
8. **Arbitration Assigned**: When an arbitrator is assigned
9. **Reminders**: Manual reminders sent by administrators

### Configuring Email Notifications

#### System-Wide Settings (Administrator Only)

1. Navigate to **"System Settings"**
2. Click **"Email Configuration"**
3. Configure:
   - SMTP server settings
   - From address and reply-to address
   - Email templates
   - Notification frequency (immediate or digest)
4. Click **"Save Settings"**

#### Session-Level Settings

1. Navigate to Search Session settings
2. Click **"Notifications"**
3. Enable/disable specific notification types
4. Set reminder frequency
5. Click **"Save"**

#### Per-User Settings (if enabled)

Some systems allow users to manage their own notification preferences:
1. Users navigate to **"My Account"** → **"Notifications"**
2. Users can opt out of non-critical notifications
3. Critical notifications (arbitration assigned, session complete) cannot be disabled

### Email Troubleshooting

#### Issue: Reviewers Not Receiving Emails

**Possible Causes:**
- Email addresses incorrect in user profiles
- Emails being caught by spam filters
- SMTP server configuration error

**Solutions:**
1. Verify email addresses in user profiles
2. Ask users to check spam/junk folders
3. Whitelist the system's sending address
4. Test email delivery with **"Send Test Email"** function
5. Check SMTP server logs for delivery errors

#### Issue: Email Delays

**Possible Causes:**
- High email volume
- Email queue backed up
- SMTP server throttling

**Solutions:**
1. Check email queue status in system admin
2. Increase email processing workers if possible
3. Contact system administrator for server-side investigation

---

## Troubleshooting Common Issues

### Issue: High Conflict Rate (>30%)

**Diagnosis:**
- Review a sample of conflicts to identify patterns
- Check if disagreements are on specific types of results
- Assess clarity of inclusion/exclusion criteria

**Solutions:**
1. Conduct calibration meeting with reviewers
2. Clarify ambiguous criteria
3. Provide examples of edge cases
4. Consider updating criteria and re-screening

### Issue: Low IRR (κ < 0.50)

**Diagnosis:**
- Analyse which types of results cause most disagreement
- Review reviewer training and experience
- Assess if criteria are too subjective

**Solutions:**
1. Additional reviewer training
2. Pilot screening with feedback
3. Criteria refinement
4. Consider replacing inexperienced reviewers

### Issue: Stalled Discussions (>14 Days with No Activity)

**Diagnosis:**
- Check if one or both reviewers are unresponsive
- Assess if discussion is productive or going in circles

**Solutions:**
1. Send reminder emails
2. Post administrative comment with deadline
3. Escalate to arbitration if no progress
4. Reassign reviewer if completely unresponsive

### Issue: Reviewer Complaints About Workload

**Diagnosis:**
- Check number of conflicts assigned to each reviewer
- Assess complexity of conflicts (simple vs complex results)

**Solutions:**
1. Redistribute conflicts if unbalanced
2. Add additional reviewers to share workload
3. Set realistic timelines
4. Prioritise high-impact conflicts

### Issue: Technical Errors (SSE Connection Failures, Page Not Loading)

**Diagnosis:**
- Check browser console for errors
- Test in different browsers
- Verify server status

**Solutions:**
1. Ask users to refresh the page
2. Clear browser cache
3. Try a different browser (Chrome/Firefox recommended)
4. Contact system administrator if problem persists

---

## System Configuration

### Advanced Configuration Options

#### Conflict Detection Rules

Configure what constitutes a "conflict":
- **Strict Mode**: Only INCLUDE vs EXCLUDE
- **Moderate Mode**: MAYBE also triggers conflicts
- **Flexible Mode**: Confidence level thresholds (e.g., both reviewers <50% confident)

#### Re-Vote Settings

- **Expiry Time**: Default 48 hours, configurable 24-96 hours
- **Auto-Accept**: Automatically accept proposals after X hours (not recommended)
- **Multiple Re-Votes**: Allow unlimited or limit to 2-3 per conflict

#### Arbitration Triggers

- **Manual Only**: Administrator decides when to assign arbitrator
- **Time-Based**: Automatic after X days (e.g., 14 days)
- **Activity-Based**: Automatic if no comments for X days (e.g., 7 days)

#### SSE Configuration (Advanced)

- **Connection Timeout**: How long to wait before reconnection attempt
- **Max Reconnection Attempts**: Number of times to try reconnecting
- **Event Types**: Which events trigger notifications

---

## Best Practices

### 1. Set Clear Expectations

At the start of screening:
- Brief all reviewers on the process
- Provide written inclusion/exclusion criteria
- Conduct pilot screening with feedback
- Set realistic timelines for conflict resolution

### 2. Monitor Early and Often

- Check IRR after first 50-100 results
- Identify and address issues early
- Conduct calibration meetings as needed
- Regular progress check-ins with reviewers

### 3. Intervene Proactively

- Send reminders before discussions stall completely
- Escalate to arbitration when discussion becomes unproductive
- Do not let conflicts languish for weeks without action

### 4. Document Everything

- Keep notes on why criteria were updated
- Document training sessions and calibration meetings
- Preserve all administrative decisions
- Maintain clear audit trail for PRISMA reporting

### 5. Balance Speed and Quality

- Do not rush conflict resolution (quality matters)
- Do not let conflicts drag on indefinitely (progress matters)
- Typical target: 90% of conflicts resolved within 14 days

### 6. Support Your Reviewers

- Be available to answer questions
- Provide clarification when criteria are ambiguous
- Recognise that disagreement is normal and valuable
- Create a supportive environment for discussion

### 7. Learn and Iterate

- Review conflict patterns after each session
- Update criteria and processes based on learnings
- Share insights with future screening teams
- Contribute to organisational knowledge base

---

## Support

For additional assistance:

- **Technical Issues**: Contact system administrator
- **Methodological Questions**: Consult systematic review methodologist
- **Training Materials**: Refer to Agent Grey main documentation
- **PRISMA Guidance**: See PRISMA 2020 statement at https://www.prisma-statement.org/

---

**Document Version:** 1.0
**Last Updated:** 21 October 2025
**Feedback:** Please report issues or suggestions to the system administrator
