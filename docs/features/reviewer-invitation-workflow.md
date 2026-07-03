# Reviewer Invitation Workflow - User Guide

**Feature**: Collaborative Review Sessions
**Version**: 1.0
**Last Updated**: 23 October 2025

---

## Overview

The Reviewer Invitation Workflow enables multiple reviewers to collaborate on systematic review sessions in Agent Grey. Session owners can invite colleagues via email to participate in dual screening, ensuring PRISMA 2020-compliant systematic reviews with inter-rater reliability measurement.

###  Key Features

✅ **Email Invitations**: Send secure magic link invitations to reviewers
✅ **Dashboard Visibility**: See both owned and shared sessions in one place
✅ **Role-Based Access**: Owners have full control, invited reviewers have read-only access to settings
✅ **Notification System**: Notification badge shows pending invitations
✅ **Secure Tokens**: Time-limited, single-use invitation links (7-day expiry)
✅ **Audit Trail**: Complete record of invitations for PRISMA reporting

---

## For Session Owners: Inviting Reviewers

### Step 1: Create or Open a Review Session

1. Navigate to your **Dashboard** (`/`)
2. Either:
   - Click **"New Review Session"** to create a new session, or
   - Click on an existing session to open it

### Step 2: Configure Review Settings

1. From the session detail page, click **"Review Configuration"**
2. Fill in the review configuration form:
   - **Screening Mode**: Choose "Dual Screening" or "Single Screening"
   - **Blind Screening**: Enable if reviewers should not see each other's decisions
   - **IRR Threshold**: Set minimum Cohen's Kappa (default: 0.70)

### Step 3: Invite Reviewers

In the "Invited Reviewers" section of the review configuration:

1. Click **"Add Reviewer"**
2. Enter reviewer details:
   - **Email**: The reviewer's email address (required)
   - **First Name**: Reviewer's first name (for personalisation)
   - **Last Name**: Reviewer's last name

3. Click **"Add"** to include them in the invitation list
4. Repeat for additional reviewers (you can invite multiple reviewers)

### Step 4: Save Configuration

1. Review your invited reviewers list
2. Click **"Save Review Configuration"**
3. Agent Grey will:
   - Create the review configuration
   - Generate secure invitation tokens
   - Send invitation emails to all invited reviewers
   - Show confirmation: "Review configured successfully. Invitations sent to X reviewer(s)."

### What Happens Next?

Each invited reviewer receives an email with:
- Session title and description
- Your name (as the inviter)
- A magic link to accept the invitation
- Information about what being a reviewer entails
- Expiry notice (7 days)

---

## For Invited Reviewers: Accepting Invitations

### Step 1: Receive Invitation Email

You'll receive an email with subject: **"Invitation to Review - [Session Title]"**

The email contains:
- Session details (title, description)
- Who invited you
- What you'll be doing as a reviewer
- A green "Accept Invitation" button
- Alternative: copy-paste link if button doesn't work
- Expiry warning: "This invitation expires in 7 days"

### Step 2: Click the Magic Link

1. Open the invitation email
2. Click the **"Accept Invitation"** button, or
3. Copy and paste the magic link into your browser

**Note**: You must be logged in to Agent Grey. If not logged in, you'll be redirected to the login page first.

### Step 3: Verify Email Match

The system will check that your logged-in email matches the invited email. If they don't match, you'll see an error:

> "This invitation is for [invited-email@example.com], but you are logged in as [your-email@example.com]"

**Solution**: Log in with the email address that received the invitation.

### Step 4: Confirm Acceptance

Upon successful acceptance:
- You'll see: "You have joined the review session: [Session Title]"
- You'll be redirected to the session detail page
- The session will appear in your **"Shared With Me"** section on the dashboard

### What Can You Do as an Invited Reviewer?

**You CAN**:
- ✅ View search results and screening queue
- ✅ Submit screening decisions (INCLUDE/EXCLUDE/MAYBE)
- ✅ Participate in consensus discussions for conflicts
- ✅ View session statistics and progress
- ✅ Access the final PRISMA report
- ✅ View duplicates and excluded results

**You CANNOT**:
- ❌ Edit the search strategy (PIC framework)
- ❌ Modify session settings
- ❌ Edit search queries
- ❌ Delete the session
- ❌ Invite additional reviewers

You'll see an info banner at the top of the session page:

> "You are a **reviewer** on this session. You can view results and submit decisions, but cannot modify search strategy or settings."

---

## Managing Invitations

### Viewing Pending Invitations

**As an Invited Reviewer**:

1. Log in to Agent Grey
2. Look for the notification badge in the navbar: **"Invitations"** with a red number badge
3. Click **"Invitations"** to view all pending invitations
4. You'll see cards showing:
   - Session title and description
   - Who invited you
   - Date invited
   - Expiry date
   - "Accept" and "Decline" buttons

### Declining an Invitation

If you don't want to participate:

1. Navigate to **"Invitations"** in the navbar
2. Find the invitation you want to decline
3. Click the **"Decline"** button
4. Confirm your choice in the dialog
5. The invitation will be marked as declined and removed from your pending list

**Note**: Declining notifies the session owner that you've declined.

### What if an Invitation Expires?

Invitations expire after 7 days. If you try to accept an expired invitation:

- You'll see: "Invitation expired"
- The invitation status auto-updates to EXPIRED
- Contact the session owner to request a new invitation

**Session owners**: To resend an expired invitation, edit the review configuration and re-invite the reviewer.

---

## Dashboard Organisation

### For Session Owners

Your dashboard shows two sections:

**My Reviews** (Sessions you own):
- Full control over these sessions
- Can edit, delete, configure, and invite reviewers
- Badge shows your role as "Owner"

**Shared With Me** (Sessions you're invited to):
- Sessions where you've accepted invitations
- Read-only access to settings
- Can participate in screening and consensus
- Badge shows your role as "Reviewer"

### For Invited Reviewers

After accepting an invitation, the session appears in **"Shared With Me"**. You'll see:
- Session title and description
- Session owner's name
- Current screening stage
- Your progress (e.g., "5 of 20 results screened")

---

## Troubleshooting

### Problem: I didn't receive the invitation email

**Solutions**:
1. **Check spam/junk folder**: Sometimes invitation emails are filtered
2. **Verify email address**: Ensure the session owner used the correct email
3. **Wait a few minutes**: Email delivery can be delayed
4. **Check with session owner**: Ask them to confirm they sent the invitation
5. **Request re-send**: Session owner can re-save the review configuration to resend

### Problem: "Email mismatch" error when accepting

**Cause**: You're logged in with a different email than the one invited.

**Solution**:
1. Log out of Agent Grey
2. Log in with the email that received the invitation
3. Click the magic link again

### Problem: "Invitation expired" error

**Cause**: The invitation was sent more than 7 days ago.

**Solution**:
1. Contact the session owner
2. Ask them to re-invite you by:
   - Opening the session
   - Editing review configuration
   - Re-adding your email to invited reviewers
   - Saving the configuration

### Problem: I can't see the session in my dashboard after accepting

**Possible Causes**:
1. **Check "Shared With Me" section**: Don't look in "My Reviews"
2. **Refresh the page**: Sometimes the dashboard needs a refresh
3. **Verify acceptance**: Check if you saw the success message
4. **Check invitation status**: Go to "Invitations" – it should show as accepted

**Solution**: If still not visible, contact the session owner to verify the invitation was created correctly.

### Problem: I can't edit the search strategy

**Expected Behaviour**: This is intentional! Invited reviewers have read-only access to search settings to preserve the integrity of the systematic review.

**What You Can Do**:
- Suggest changes to the session owner
- Participate in screening with the existing strategy
- View all search queries and results

### Problem: The "Accept Invitation" button doesn't work

**Solutions**:
1. **Copy the magic link**: Email includes a plain text link you can copy-paste
2. **Check browser**: Try a different browser or incognito mode
3. **Disable browser extensions**: Ad blockers sometimes interfere with buttons
4. **Use mobile**: Try accepting on your mobile device

---

## Frequently Asked Questions (FAQ)

### Q: Can I invite multiple reviewers to one session?

**A**: Yes! You can invite as many reviewers as needed. Simply add multiple emails in the review configuration form before saving.

### Q: Can invited reviewers see each other's screening decisions?

**A**: It depends on your **"Blind Screening"** setting:
- **Blind Screening = ON**: Reviewers cannot see each other's decisions until both have voted
- **Blind Screening = OFF**: All decisions are visible immediately

For PRISMA-compliant systematic reviews, we recommend enabling blind screening.

### Q: What happens if a reviewer changes their email address?

**A**: Invitations are tied to the email address used when invited. If a reviewer changes their email:
1. They'll need to accept the invitation using the original email, or
2. The session owner can revoke the old invitation and send a new one to the new email

### Q: Can I revoke an invitation after sending it?

**A**: Yes, but this feature is currently only accessible via the admin interface. Contact your Agent Grey administrator to revoke pending invitations.

**Future Enhancement**: Session owners will be able to manage invitations directly from the session detail page.

### Q: Do invited reviewers count towards my organisation's user limit?

**A**: Yes, each invited reviewer must have an Agent Grey user account. If they don't have one, they'll need to register before accepting the invitation.

### Q: Can I invite someone who doesn't have an Agent Grey account?

**A**: You can send the invitation, but they'll need to:
1. Register for an Agent Grey account using the invited email
2. Then click the magic link to accept

**Tip**: Ask them to register first, then send the invitation to avoid confusion.

### Q: What if I accidentally decline an invitation I wanted to accept?

**A**: Contact the session owner and ask them to re-invite you. Declined invitations cannot be undone, but a new invitation can be sent.

### Q: How long does an invitation last?

**A**: Invitations expire after **7 days**. After expiry, the session owner must send a new invitation.

### Q: Can I accept an invitation and then leave the session later?

**A**: Currently, there's no "leave session" feature. Once you accept, you remain a reviewer on that session. If you need to be removed, contact the session owner or an administrator.

**Future Enhancement**: Self-service "leave session" functionality may be added.

### Q: What data is tracked for PRISMA reporting?

**A**: The system tracks:
- Who was invited and when
- Who accepted and when
- All screening decisions with timestamps
- Conflicts and their resolutions
- Inter-rater reliability (Cohen's Kappa)

This audit trail ensures full PRISMA 2020 compliance.

### Q: Can I forward an invitation to a colleague?

**A**: No, invitations are email-specific and include security tokens. Forwarding won't work because:
1. The magic link checks that the logged-in email matches the invited email
2. Tokens are single-use and expire after 7 days

**Solution**: Ask the session owner to invite your colleague directly.

### Q: What if I want to be a reviewer on my own session?

**A**: You don't need an invitation! As the session owner, you automatically have full access, including the ability to submit screening decisions. You can participate in dual screening alongside invited reviewers.

### Q: Can I see who else has been invited to a session?

**A**: Currently, this information is only visible to the session owner in the review configuration page. Invited reviewers cannot see the list of other invited reviewers.

**Future Enhancement**: A "Team" or "Reviewers" tab may be added to show all reviewers on a session.

---

## Best Practices

### For Session Owners

1. **Invite Early**: Send invitations as soon as your search strategy is finalised to give reviewers time to prepare
2. **Include Context**: Write a clear session description so reviewers understand the review's purpose
3. **Set Expectations**: Communicate deadlines and screening expectations via email or chat before sending the invitation
4. **Monitor Acceptance**: Check the review configuration page to see who has accepted invitations
5. **Enable Blind Screening**: For PRISMA compliance, always enable blind screening for dual reviewer studies

### For Invited Reviewers

1. **Accept Promptly**: Don't wait until the last day – invitations expire after 7 days
2. **Review Session Details**: Read the session description to understand what you're reviewing
3. **Ask Questions**: If unclear about the review scope or process, contact the session owner before starting
4. **Stay Updated**: Check the session regularly for new results to screen
5. **Participate in Consensus**: If conflicts arise, engage in discussion to reach consensus

### For Teams

1. **Standard Operating Procedure (SOP)**: Develop an SOP for your team's invitation workflow
2. **Email Templates**: Use consistent language when communicating with invited reviewers
3. **Training**: Ensure all team members understand the difference between owner and reviewer roles
4. **Regular Check-ins**: Schedule brief check-ins to discuss progress and resolve any conflicts
5. **Document Everything**: Save all invitation emails and acceptance confirmations for audit trails

---

## Technical Details

For developers and administrators:

### Database Schema

**ReviewInvitation Model**:
- `id`: UUID (primary key)
- `session`: ForeignKey to SearchSession
- `inviter`: ForeignKey to User (session owner)
- `invitee_email`: EmailField (invited reviewer's email)
- `invitee_name`: CharField (display name)
- `invitee`: ForeignKey to User (linked on acceptance)
- `status`: CharField (PENDING, ACCEPTED, DECLINED, EXPIRED, REVOKED)
- `token`: CharField (64-character URL-safe magic link token)
- `invited_at`: DateTimeField (auto_now_add)
- `expires_at`: DateTimeField (7 days from creation)
- `responded_at`: DateTimeField (when accepted/declined)

### Security Features

- **Token Generation**: `secrets.token_urlsafe(48)` (64-character URL-safe tokens)
- **Email Verification**: System checks that logged-in email matches invitee_email
- **Single-Use Tokens**: Tokens are marked as used after acceptance
- **Time-Limited**: 7-day expiry with automatic status update to EXPIRED
- **HTTPS Enforcement**: Magic links use HTTPS in production

### API Endpoints

- **Accept Invitation**: `GET /invitations/accept/<token>/`
- **Decline Invitation**: `POST /invitations/decline/<token>/`
- **View Pending**: `GET /invitations/`

### Email Templates

Invitation emails use the template:
`templates/emails/dual_screening/reviewer_invitation.html`

Emails include:
- Personalised greeting
- Session details
- What being a reviewer means
- Magic link button
- Copy-paste link fallback
- Expiry warning

---

## Support

### Getting Help

If you encounter issues not covered in this guide:

1. **Check the RCA**: See `docs/fixes/issue-16-invited-reviewers-cannot-access-sessions-rca.md` for technical details
2. **Contact Support**: Email your Agent Grey administrator
3. **GitHub Issues**: Report bugs at https://github.com/[your-org]/agent-grey/issues

### Feedback

We're continuously improving the reviewer invitation workflow. If you have suggestions or feature requests, please contact:

- **Product Team**: [product@example.com]
- **GitHub Discussions**: [your-repo]/discussions

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-23 | Initial release of reviewer invitation workflow |

---

**Last Updated**: 23 October 2025
**Author**: Agent Grey Development Team
**Status**: Production
