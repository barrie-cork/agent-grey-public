# ScreeningDecision.vue Implementation Summary

**Date:** 19 October 2025
**Component:** `/frontend/src/views/ScreeningDecision.vue`
**Status:** ✅ Complete

## Overview

Full implementation of the dual-reviewer screening decision component for Agent Grey. This component allows reviewers to make independent screening decisions on grey literature search results.

## Features Implemented

### 1. Result Display (Left Column)
- **Title**: Full result title prominently displayed
- **Snippet**: Preview text from search result
- **URL**: Clickable external link with icon
- **Metadata Display**:
  - Source name (if available)
  - Published date (formatted in UK English)
  - Authors (if available)
  - Duplicate warning badge
- **Timer Display**: Live review time tracker in MM:SS format

### 2. Decision Form (Right Column - Sticky)

#### A. Three Decision Buttons
- **Include Button** (Green)
  - Custom CSS class: `btn-include`
  - Icon: Bootstrap Icons check-circle
  - Keyboard shortcut: `I`

- **Maybe Button** (Amber/Warning)
  - Custom CSS class: `btn-maybe`
  - Icon: Bootstrap Icons question-circle
  - Keyboard shortcut: `M`

- **Exclude Button** (Red)
  - Custom CSS class: `btn-exclude`
  - Icon: Bootstrap Icons x-circle
  - Keyboard shortcut: `E`

**Button Features**:
- Visual feedback when selected (active state with border)
- Disabled during submission
- Keyboard shortcut badges displayed
- Hover transform effect (lift on hover)

#### B. Exclusion Reason Dropdown (Conditional)
- **Visibility**: Only shown when EXCLUDE decision selected
- **Required Field**: Validation enforced
- **Options** (from Django model):
  - Not relevant to research question
  - Not grey literature
  - Duplicate result
  - Full text unavailable
  - Inappropriate document type
  - Language other than English
  - Wrong population
  - Wrong intervention/interest
  - Other reason

#### C. Confidence Level Slider
- **Range**: 1-3 (Low/Medium/High)
- **Default**: Medium (2)
- **Visual Feedback**:
  - Low: Warning colour (amber)
  - Medium: Info colour (blue)
  - High: Success colour (green)
- **Labels**: Clear min/max/current labels

#### D. Notes Textarea
- **Optional**: Not required
- **Placeholder**: Guidance text
- **Rows**: 4 lines
- **Purpose**: Additional context for decision

#### E. Submit Button
- **Validation**: Disabled until form is valid
- **Loading State**: Spinner during submission
- **Error Handling**: Displays error message and allows retry

### 3. Response Handling

#### Success Modal
Displays different content based on API response status:

**A. Consensus Reached**
- Header: Green background
- Title: "Consensus Reached"
- Message: From API response
- Action: "Next Result" button

**B. Awaiting Second Reviewer**
- Header: Blue background
- Title: "Decision Recorded"
- Message: Confirmation text
- Action: "Next Result" button

**C. Conflict Detected**
- Header: Amber background
- Title: "Conflict Detected"
- Message: From API response
- Conflict type display
- Actions:
  - "View Conflict" button (navigates to conflict resolution)
  - "Continue to Next Result" button

### 4. Auto-Advance Logic
After successful submission, modal offers navigation to:
- Work queue (`/work-queue`) for next result
- Conflict resolution (`/conflicts/:id`) if conflict detected

### 5. Timer Implementation
- **Start**: Automatically when component loads
- **Display**: Live updating MM:SS format
- **Capture**: Total elapsed seconds sent to API
- **Stop**: On submission (success or failure)
- **Restart**: If submission fails (allows correction)

### 6. Keyboard Shortcuts
- **I**: Select Include
- **M**: Select Maybe
- **E**: Select Exclude
- **Smart Detection**: Disabled when typing in input fields

### 7. Form Validation
- Decision selection required
- Exclusion reason required if EXCLUDE selected
- Visual error messages below fields
- Submit button disabled until valid

### 8. State Management
- **Loading State**: Spinner on initial load
- **Error State**: Error message with retry button
- **Submitting State**: Disabled form during submission
- **Success State**: Modal with response handling

## Technical Implementation

### Vue 3 Composition API
- `<script setup>` syntax
- TypeScript support
- Reactive refs and computed properties

### API Integration
- `getResult(id)`: Fetch result details
- `submitDecision(id, data)`: Submit reviewer decision
- Error handling with try/catch

### Route Integration
- Route param: `id` (result UUID)
- Props: `true` (automatic prop passing)
- Navigation: Vue Router for programmatic routing

### CSS Styling
- **Custom Classes**: Uses main.css decision button styles
- **Bootstrap 5**: Grid, cards, buttons, badges
- **Responsive**: Two-column layout (col-lg-8/col-lg-4)
- **Sticky Sidebar**: Decision form stays visible on scroll
- **Accessibility**: Focus styles, semantic HTML, ARIA labels

### TypeScript Types
All types imported from `../types/index.ts`:
- `ProcessedResult`
- `DecisionType`
- `ConfidenceLevel`
- `DecisionResponse`

## Data Flow

```
1. Component Mounts
   ↓
2. Load Result (API: getResult)
   ↓
3. Start Timer
   ↓
4. User Makes Decision
   ↓
5. Validate Form
   ↓
6. Submit Decision (API: submitDecision)
   ↓
7. Stop Timer
   ↓
8. Handle Response:
   - Consensus → Show success modal
   - Awaiting → Show pending modal
   - Conflict → Show conflict modal + navigation option
   ↓
9. Auto-Advance
   - Navigate to Work Queue (claim next)
   - OR Navigate to Conflict Resolution
```

## Integration Points

### Backend API Endpoints
- `GET /api/results/{id}/` - Get result details
- `POST /api/results/{id}/decide/` - Submit decision

### Expected Request Format
```typescript
{
  decision: 'INCLUDE' | 'EXCLUDE' | 'MAYBE',
  exclusion_reason?: string,  // Required if EXCLUDE
  confidence_level: 'LOW' | 'MEDIUM' | 'HIGH',
  notes?: string,
  time_spent_seconds: number,
  screening_stage: 'SCREENING' | 'FULL_TEXT'
}
```

### Expected Response Format
```typescript
{
  id: string,
  decision: 'INCLUDE' | 'EXCLUDE' | 'MAYBE',
  status: 'consensus_reached' | 'awaiting_second_reviewer' | 'conflict_detected',
  message: string,
  conflict_id?: string,
  conflict_type?: string
}
```

## PRISMA Compliance
- Captures time spent (audit trail)
- Records confidence level (quality metric)
- Mandatory exclusion reason (PRISMA reporting requirement)
- Optional notes (additional context)
- Immutable decision tracking (via API)

## Accessibility Features
- Semantic HTML (`<label>`, `<button>`, `<select>`)
- ARIA labels via Bootstrap classes
- Keyboard navigation support (tab index)
- Focus-visible styles
- Screen reader text (`visually-hidden`)
- Colour contrast (WCAG 2.1 AA compliant)

## Browser Compatibility
- Modern browsers (Chrome, Firefox, Safari, Edge)
- ES6+ features via Vite transpilation
- Bootstrap 5 compatibility

## Testing Recommendations

### Unit Tests
- Timer accuracy
- Form validation logic
- Decision button selection
- Keyboard shortcut handling

### Integration Tests
- API error handling
- Success modal states
- Navigation after submission
- Timer persistence across errors

### E2E Tests
- Complete screening workflow
- Conflict detection flow
- Auto-advance to next result
- Keyboard-only navigation

## Known Limitations
1. **Bootstrap Icons**: Requires Bootstrap Icons CSS to be loaded
2. **Screening Stage**: Currently hardcoded to 'SCREENING' (could be prop)
3. **Session Context**: Not explicitly validated (assumes valid from route)

## Future Enhancements
- [ ] Add "Report Accessed" tracking (checkbox for full-text review)
- [ ] Support for FULL_TEXT screening stage
- [ ] Bulk decision mode
- [ ] Decision history/audit trail view
- [ ] Timer pause/resume functionality
- [ ] Offline support with local storage

## File References
- **Component**: `/frontend/src/views/ScreeningDecision.vue`
- **API Client**: `/frontend/src/api/results.ts`
- **Types**: `/frontend/src/types/index.ts`
- **Styles**: `/frontend/src/assets/styles/main.css`
- **Router**: `/frontend/src/router/index.ts`

---

**Implementation Complete**: All requirements from PRP Phase 5 lines 94-146 fulfilled.
