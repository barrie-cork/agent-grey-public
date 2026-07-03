# Consensus Discussion: Reviewer Guide

**Version:** 1.0
**Last Updated:** 21 October 2025
**Audience:** Systematic Review Researchers and Reviewers

---

## Table of Contents

1. [Introduction](#introduction)
2. [What is Consensus Discussion?](#what-is-consensus-discussion)
3. [When to Use Consensus Discussion](#when-to-use-consensus-discussion)
4. [Accessing Conflicts](#accessing-conflicts)
5. [Understanding the Conflict Discussion Page](#understanding-the-conflict-discussion-page)
6. [Posting Comments](#posting-comments)
7. [Replying to Comments](#replying-to-comments)
8. [Using Markdown Formatting](#using-markdown-formatting)
9. [Proposing a Re-Vote](#proposing-a-re-vote)
10. [Accepting Re-Vote Proposals](#accepting-re-vote-proposals)
11. [Submitting Re-Vote Decisions](#submitting-re-vote-decisions)
12. [Understanding Consensus](#understanding-consensus)
13. [Real-Time Updates](#real-time-updates)
14. [Email Notifications](#email-notifications)
15. [Troubleshooting](#troubleshooting)
16. [Frequently Asked Questions](#frequently-asked-questions)
17. [Best Practices](#best-practices)

---

## Introduction

This guide explains how to use the Consensus Discussion feature in Agent Grey to resolve conflicts that arise during dual screening of systematic review results. The feature enables reviewers with conflicting decisions to discuss the disputed result, share their reasoning, and reach consensus through structured communication.

Consensus Discussion is designed to meet PRISMA 2020 and Cochrane systematic review standards for transparent conflict resolution.

---

## What is Consensus Discussion?

Consensus Discussion is a structured process for resolving conflicts when two reviewers disagree on whether to include or exclude a search result. The discussion:

- Takes place in a dedicated discussion page for each conflict
- Allows reviewers to post comments explaining their reasoning
- Supports re-voting when new insights emerge from discussion
- Maintains a complete audit trail for PRISMA reporting
- Sends email notifications to keep reviewers informed
- Updates in real time so all reviewers see the latest information

---

## When to Use Consensus Discussion

Use Consensus Discussion when:

1. **Conflict Detected**: Two reviewers have made different decisions (one voted INCLUDE, the other voted EXCLUDE) on the same search result
2. **Discussion Needed**: The conflict cannot be resolved immediately and requires discussion
3. **Re-Vote May Help**: After discussion, reviewers may change their position and want to vote again
4. **Consensus Goal**: The aim is to reach agreement without requiring arbitration

---

## Accessing Conflicts

### From the Session Dashboard

1. Navigate to your Search Session dashboard
2. Look for the "Conflicts" section or tab
3. Click on the conflict count (e.g., "5 conflicts pending")
4. You will see a list of all conflicts for this session

### From the Conflicts List

1. Each conflict shows:
   - The search result title
   - Conflict type (INCLUDE vs EXCLUDE)
   - Status (PENDING, IN_DISCUSSION, or RESOLVED)
   - When the conflict was detected
2. Click on any conflict to open the discussion page

---

## Understanding the Conflict Discussion Page

The Conflict Discussion page has several sections:

### 1. Page Header
- **Title**: "Conflict Discussion"
- **Description**: Brief explanation of the page purpose
- **Connection Status**: Shows if real-time updates are active (green = connected, amber = reconnecting)

### 2. Conflict Details
Displays information about the disputed result:
- **Title**: The title of the search result
- **Snippet**: A brief excerpt from the result
- **URL**: Link to the original source
- **Organisation**: Source organisation (if available)
- **Result Type**: Type of grey literature (e.g., policy document, guideline)
- **Conflict Type**: Whether this is an INCLUDE vs EXCLUDE disagreement
- **Detected**: When the conflict was first identified

### 3. Conflicting Decisions
Shows cards for each reviewer's decision:
- **Reviewer Name**: Who made the decision
- **Decision**: INCLUDE, EXCLUDE, or MAYBE
- **Confidence Level**: How confident the reviewer was (0-100%)
- **Notes**: The reviewer's reasoning for their decision
- **Timestamp**: When the decision was made

### 4. Conflict Status
Displays the current status:
- **PENDING**: Conflict detected, discussion not yet started
- **IN_DISCUSSION**: Reviewers are discussing
- **RESOLVED**: Consensus reached or arbitration completed

### 5. Re-Vote Panel (when active)
Shows when a re-vote proposal is pending or active:
- **Proposal Details**: Who proposed it and why
- **Acceptance Status**: Which reviewers have accepted
- **Voting Status**: Which reviewers have voted
- **Time Remaining**: Time until proposal expires (48 hours)

### 6. Discussion Thread
The main area for comments:
- **Comment Count**: Total number of comments
- **Comments**: Threaded discussion with replies
- **Comment Form**: Text area to post new comments

---

## Posting Comments

### Step 1: Navigate to the Conflict
Open the conflict discussion page for the conflict you want to comment on.

### Step 2: Scroll to the Discussion Section
The discussion section is below the conflict details and re-vote panel.

### Step 3: Type Your Comment
In the text area labelled "Add a comment", type your message. You can:
- Explain your reasoning for your decision
- Ask questions about the other reviewer's reasoning
- Share relevant information about the source
- Suggest a re-vote if you've changed your mind

### Step 4: Format Your Comment (Optional)
Use markdown formatting to make your comment clearer (see [Using Markdown Formatting](#using-markdown-formatting)).

### Step 5: Post Your Comment
Click the **"Post Comment"** button.

Your comment will appear immediately in the discussion thread. The other reviewer will receive an email notification.

---

## Replying to Comments

### Step 1: Find the Comment to Reply To
Scroll through the discussion thread to find the specific comment you want to respond to.

### Step 2: Click "Reply"
Below each comment, you will see a **"Reply"** button. Click it.

### Step 3: Type Your Reply
A reply form will appear indented beneath the original comment. Type your response.

### Step 4: Post Your Reply
Click the **"Post Reply"** button.

Your reply will appear threaded under the original comment, making it clear which comment you are responding to.

---

## Using Markdown Formatting

Consensus Discussion supports markdown formatting to help you structure your comments clearly.

### Bold Text
```
**This text will be bold**
```
**This text will be bold**

### Italic Text
```
*This text will be italic*
```
*This text will be italic*

### Bullet Lists
```
- First point
- Second point
- Third point
```
- First point
- Second point
- Third point

### Numbered Lists
```
1. First step
2. Second step
3. Third step
```
1. First step
2. Second step
3. Third step

### Links
```
[Agent Grey Documentation](https://docs.agentgrey.com)
```
[Agent Grey Documentation](https://docs.agentgrey.com)

### Inline Code
```
Use `filetype:pdf` to search for PDF documents
```
Use `filetype:pdf` to search for PDF documents

### Block Quotes
```
> This is a quote from the original document
```
> This is a quote from the original document

### Headings
```
### Subheading
```
### Subheading

---

## Proposing a Re-Vote

If, after discussion, you believe a re-vote would help reach consensus, you can propose one.

### When to Propose a Re-Vote

Consider proposing a re-vote when:
- New information has emerged during discussion
- You have changed your mind based on the other reviewer's reasoning
- Both reviewers seem closer to agreement
- The discussion has clarified the inclusion/exclusion criteria

### How to Propose a Re-Vote

#### Step 1: Locate the Re-Vote Button
Look for the **"Propose Re-Vote"** button near the top of the conflict discussion page (if no re-vote is already active).

#### Step 2: Click "Propose Re-Vote"
A form will appear asking for your rationale.

#### Step 3: Provide Your Rationale
In the text area, explain:
- Why you are proposing a re-vote
- What new insights have emerged from the discussion
- What you think the outcome might be

Be clear and specific. This helps the other reviewer(s) understand why re-voting would be beneficial.

#### Step 4: Submit the Proposal
Click **"Submit Proposal"**.

Your proposal will be sent to all other reviewers, who will receive an email notification.

### What Happens Next

1. **Proposal Pending**: The proposal appears in the Re-Vote Panel with status "Pending Acceptance"
2. **Reviewers Notified**: All conflicting reviewers receive an email
3. **Acceptance Required**: All reviewers must accept the proposal before voting can begin
4. **Expiry**: If not all reviewers accept within 48 hours, the proposal expires

---

## Accepting Re-Vote Proposals

When another reviewer proposes a re-vote, you will receive an email notification and see the proposal in the Re-Vote Panel.

### Step 1: Review the Proposal
Read:
- Who proposed the re-vote
- Their rationale for proposing it
- When it was proposed
- When it will expire (48 hours from proposal)

### Step 2: Consider Whether to Accept
Ask yourself:
- Does the discussion justify a re-vote?
- Am I willing to reconsider my decision?
- Could a re-vote help reach consensus?

### Step 3: Accept or Decline

#### To Accept:
Click the **"Accept Re-Vote"** button in the Re-Vote Panel.

#### To Decline:
You can either:
- Ignore the proposal (it will expire after 48 hours)
- Post a comment explaining why you do not think a re-vote is appropriate

### What Happens When You Accept

1. Your acceptance is recorded
2. Other reviewers are notified
3. When all reviewers have accepted, the proposal status changes to "Accepted"
4. The voting period begins
5. All reviewers can now submit their re-vote decisions

---

## Submitting Re-Vote Decisions

Once a re-vote proposal has been accepted by all reviewers, you can submit your new decision.

### Step 1: Locate the Voting Form
In the Re-Vote Panel, you will see a **"Submit Your Vote"** section.

### Step 2: Select Your Decision
Choose one of:
- **INCLUDE**: Include this result in the review
- **EXCLUDE**: Exclude this result from the review
- **MAYBE**: Uncertain, requires arbitration

### Step 3: Add Notes (Optional but Recommended)
In the notes field, explain:
- Why you made this decision
- How the discussion influenced your thinking
- What criteria you applied

### Step 4: Set Confidence Level (Optional)
Use the slider to indicate your confidence level (0-100%). This helps track decision quality.

### Step 5: Submit Your Vote
Click **"Submit Vote"**.

Your vote is recorded immediately and the other reviewer is notified.

### What Happens When All Reviewers Vote

1. **Consensus Check**: The system checks if all reviewers now agree
2. **If Consensus Reached**:
   - Conflict status changes to "RESOLVED"
   - All reviewers receive a congratulatory email
   - The result is marked with the consensus decision
3. **If Still No Consensus**:
   - Conflict remains PENDING
   - May require arbitration or further discussion

---

## Understanding Consensus

Consensus is reached when:

1. **All Reviewers Agree**: All conflicting reviewers have made the same decision (all INCLUDE or all EXCLUDE)
2. **After Re-Vote**: This can happen during the original screening or after a re-vote
3. **Verified by System**: The system automatically detects consensus and updates the conflict status

### What Happens When Consensus is Reached

1. **Status Update**: Conflict status changes from PENDING to RESOLVED
2. **Email Notification**: All reviewers receive an email confirming consensus
3. **Audit Trail**: The complete discussion and voting history is preserved
4. **PRISMA Reporting**: The consensus is recorded for inclusion in the PRISMA flow diagram

### If Consensus Cannot Be Reached

If after discussion and re-voting, consensus still cannot be reached:
1. The conflict remains PENDING
2. The session manager may assign an arbitrator
3. The arbitrator reviews the discussion and makes a final decision
4. The arbitration decision is binding and resolves the conflict

---

## Real-Time Updates

Consensus Discussion uses Server-Sent Events (SSE) to provide real-time updates without requiring page refreshes.

### What Updates Automatically

- **New Comments**: Comments posted by other reviewers appear instantly
- **Re-Vote Proposals**: Proposals appear as soon as they are created
- **Acceptance Status**: Updates when other reviewers accept proposals
- **Vote Submissions**: Updates when other reviewers submit votes
- **Consensus Achievement**: Immediate notification when consensus is reached

### Connection Status Indicator

In the top-right corner of the page, you may see a connection status indicator:
- **Green (Connected)**: Real-time updates are active
- **Amber (Reconnecting)**: Temporary connection issue, reconnecting automatically
- **Red (Error)**: Connection failed, updates may be delayed

### What to Do if Updates Stop

1. **Check Connection Indicator**: Look for the status message
2. **Wait for Reconnection**: The system will automatically attempt to reconnect
3. **Refresh Manually**: If connection does not restore, refresh the page
4. **Check Network**: Ensure you have a stable internet connection

---

## Email Notifications

You will receive email notifications for important events:

### Comment Posted
- **When**: Another reviewer posts a comment or reply
- **Content**: Preview of the comment (first 200 characters)
- **Action**: Link to view the full discussion

### Re-Vote Proposed
- **When**: Another reviewer proposes a re-vote
- **Content**: Who proposed it and their rationale
- **Action**: Link to accept or decline the proposal
- **Urgency**: Reminder that the proposal expires in 48 hours

### Re-Vote Ready
- **When**: All reviewers have accepted a re-vote proposal
- **Content**: Confirmation that voting is now open
- **Action**: Link to submit your vote

### Consensus Reached
- **When**: All reviewers agree on a decision
- **Content**: Celebration message and consensus decision
- **Action**: Link to view the resolved conflict

### Managing Email Notifications

Email notifications are enabled by default. If you wish to change your notification preferences, contact your session manager or system administrator.

---

## Troubleshooting

### Problem: I Cannot See Any Conflicts

**Possible Causes:**
- You are not assigned as a reviewer for this session
- No conflicts have been detected yet (both reviewers agreed on all results)
- You are viewing the wrong session

**Solutions:**
1. Check that you are assigned as PRIMARY or SECONDARY reviewer
2. Contact your session manager to verify your reviewer role
3. Ensure you are viewing the correct search session

### Problem: I Cannot Post Comments

**Possible Causes:**
- You are not one of the conflicting reviewers for this specific conflict
- The conflict has already been resolved
- You do not have permission to comment

**Solutions:**
1. Verify you are one of the reviewers whose decisions conflict
2. Check the conflict status (resolved conflicts cannot receive new comments)
3. Contact your session manager if you believe you should have access

### Problem: My Comment Did Not Appear

**Possible Causes:**
- Network error during submission
- Server error
- Validation error (e.g., empty comment)

**Solutions:**
1. Check for error messages on the page
2. Try refreshing the page to see if the comment appears
3. Re-type and re-submit the comment
4. Contact your session manager if the problem persists

### Problem: I Do Not See Real-Time Updates

**Possible Causes:**
- SSE connection failed
- Browser does not support EventSource API
- Network issue

**Solutions:**
1. Check the connection status indicator in the top-right corner
2. Try refreshing the page
3. Check your internet connection
4. Try a different browser (Chrome, Firefox, or Edge recommended)
5. Manual refresh will still show new content

### Problem: Re-Vote Proposal Expired

**Explanation:**
Re-vote proposals expire after 48 hours if not all reviewers accept them. This prevents stale proposals from remaining open indefinitely.

**Solution:**
If you still think a re-vote would be helpful, post a comment in the discussion explaining why, and someone can propose a new re-vote.

### Problem: I Changed My Mind After Voting

**Explanation:**
Votes are immutable to maintain the audit trail for PRISMA compliance. Once submitted, a vote cannot be edited or deleted.

**Solution:**
If you realise you made an error:
1. Post a comment explaining the situation
2. Propose another re-vote if appropriate
3. Contact your session manager if urgent

---

## Frequently Asked Questions

### 1. Can I Edit or Delete My Comments?

No. All comments are immutable to preserve the complete audit trail for PRISMA reporting. If you make an error, post a follow-up comment to clarify.

### 2. Can Other People See My Comments?

Yes, but only the reviewers involved in the specific conflict can see the discussion. Session managers may also have access for monitoring purposes.

### 3. How Long Does a Re-Vote Proposal Last?

Re-vote proposals expire 48 hours after creation if not all reviewers accept them. This ensures proposals do not remain open indefinitely.

### 4. What if We Cannot Reach Consensus?

If consensus cannot be reached through discussion and re-voting, the session manager will assign an arbitrator who will review the discussion and make a binding decision.

### 5. Can I Propose Multiple Re-Votes?

Yes, but only one re-vote proposal can be active at a time. If the first re-vote does not resolve the conflict, you can propose another one.

### 6. Do I Have to Accept Every Re-Vote Proposal?

No. You should only accept a proposal if you believe the discussion justifies reconsidering your decision. If you do not accept, the proposal will expire after 48 hours.

### 7. What if the Other Reviewer Does Not Respond?

If a reviewer is unresponsive:
1. Try sending them a reminder via email outside the system
2. Contact your session manager
3. The session manager may reassign the conflict or escalate to arbitration

### 8. Can I Discuss Multiple Conflicts at Once?

Yes. Each conflict has its own separate discussion page. You can have multiple discussions open simultaneously.

### 9. Is the Discussion Private?

Yes. Only the conflicting reviewers and session managers can see the discussion. Discussions are not visible to other reviewers or external parties.

### 10. What Happens to the Discussion After Consensus?

The complete discussion history is preserved permanently as part of the audit trail. It can be exported for PRISMA reporting and remains accessible to session managers.

### 11. Can I Use Emojis in Comments?

Yes, you can use emojis in comments, but use them sparingly in formal systematic review discussions.

### 12. What if I Spot an Error in the Result Details?

If you notice an error in the result title, snippet, or other metadata, contact your session manager. These details are imported from the original search and cannot be edited by reviewers.

### 13. How Do I Know if My Email Notifications Are Working?

Email notifications are sent automatically. To test them, try posting a comment and check if the other reviewer receives an email. If not, contact your system administrator.

### 14. Can I Work on Conflicts Offline?

No. Consensus Discussion requires an internet connection for real-time updates and to ensure all actions are properly recorded in the audit trail.

### 15. What Browsers Are Supported?

Consensus Discussion works best in modern browsers:
- **Recommended**: Chrome, Firefox, Edge, Safari (latest versions)
- **Not Supported**: Internet Explorer, older browser versions

---

## Best Practices

### 1. Be Clear and Specific
When posting comments:
- Explain your reasoning with specific references to the inclusion/exclusion criteria
- Quote relevant passages from the result if helpful
- Avoid vague statements like "I just think it should be excluded"

### 2. Be Respectful
Remember that disagreements are a normal part of systematic review:
- Use professional language
- Acknowledge the validity of different perspectives
- Focus on the evidence, not the person

### 3. Respond Promptly
To keep the review moving:
- Check for conflicts regularly
- Respond to comments within 24-48 hours
- Accept or decline re-vote proposals promptly

### 4. Use Re-Votes Judiciously
Propose re-votes when:
- The discussion has revealed new information
- You have genuinely changed your mind
- There is a clear path to consensus

Do not propose re-votes:
- Just to speed up the process without new information
- If you are not genuinely reconsidering your position

### 5. Provide Detailed Notes
When voting (original or re-vote):
- Explain which inclusion/exclusion criteria you applied
- Note any edge cases or uncertainties
- Reference specific parts of the result that influenced your decision

### 6. Keep the Audit Trail in Mind
Remember that all discussions will be:
- Preserved permanently
- Potentially reviewed by arbitrators
- Included in PRISMA reporting
- Subject to external audit

Ensure all comments are professional and evidence-based.

### 7. Use Markdown for Clarity
Take advantage of markdown formatting to:
- Highlight key points with bold
- Structure complex arguments with lists
- Quote relevant passages with block quotes
- Make your comments easier to read

### 8. Check for Updates Regularly
Even with real-time updates:
- Refresh the page periodically to ensure you have the latest information
- Check the connection status indicator
- Verify that your comments and votes have been recorded

---

## Support

If you encounter issues not covered in this guide:

- **Session Manager**: Contact your search session manager for session-specific questions
- **System Administrator**: Contact your system administrator for technical issues
- **Documentation**: Refer to the Agent Grey main documentation at [internal documentation link]

---

**Document Version:** 1.0
**Last Updated:** 21 October 2025
**Feedback:** Please report any issues or suggestions to your session manager
