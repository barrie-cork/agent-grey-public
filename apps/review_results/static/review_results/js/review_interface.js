// Review Results Interface JavaScript
// This file contains all JavaScript functionality for the review results overview page

// Global variables for current review session
let SESSION_ID = '';
let CSRF_TOKEN = '';

// Initialize review interface
function initialize_review_interface(session_id, csrf_token) {
    SESSION_ID = session_id;
    CSRF_TOKEN = csrf_token;

    console.log('Review interface initialized for session:', SESSION_ID);

    // Add keyboard shortcuts
    document.addEventListener('keydown', function (e) {
        // Ctrl/Cmd + A to select all
        if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !e.target.matches('input, textarea')) {
            e.preventDefault();
            select_all();
        }
        // Escape to deselect all
        else if (e.key === 'Escape') {
            deselect_all();
        }
    });

    // Initialize URL tracking
    initialize_url_tracking();
}

// URL parameter helper
function update_url_param(param_name, value) {
    const url = new URL(window.location);
    url.searchParams.set(param_name, value);
    url.searchParams.delete('page');
    window.location.href = url.toString();
}

// Filter functions
function filter_by_status(status) {
    update_url_param('review_status', status);
}

// Navigate to duplicates page
function navigateToDuplicates(sessionId) {
    window.location.href = `/review-results/duplicates/${sessionId}/`;
}

function change_per_page(value) {
    update_url_param('per_page', value);
}

// API request helper - consolidates fetch+error handling pattern
function api_request(endpoint, options = {}) {
    const { method = 'POST', body, onSuccess, successMessage, errorPrefix = 'Error' } = options;
    const headers = { 'X-CSRFToken': CSRF_TOKEN };
    if (!(body instanceof FormData)) {
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }
    return fetch(`/review-results/api/${SESSION_ID}/${endpoint}`, { method, headers, body })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (onSuccess) onSuccess(data);
                if (successMessage) alert(successMessage(data));
            } else {
                alert(`${errorPrefix}: ${data.error || 'Unknown error occurred'}`);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Network error occurred. Please try again.');
        });
}

// Decision making function (called by template tag buttons)
function make_decision(result_id, decision) {
    if (decision === 'exclude') {
        // Show exclusion reason modal
        show_exclusion_modal(result_id);
    } else {
        // Direct decision for include/maybe
        submit_decision(result_id, decision);
    }
}

function show_exclusion_modal(result_id) {
    document.getElementById('excludeResultId').value = result_id;
    document.getElementById('exclusionModal').showModal();
}

function confirm_exclusion() {
    const form = document.getElementById('exclusionForm');
    const form_data = new FormData(form);
    const result_id = form_data.get('result_id');
    const exclusion_reason = form_data.get('exclusion_reason');
    const notes = form_data.get('notes');

    if (!exclusion_reason) {
        alert('Please select an exclusion reason.');
        return;
    }

    submit_decision(result_id, 'exclude', exclusion_reason, notes);
    document.getElementById('exclusionModal').close();
}

function submit_decision(result_id, decision, exclusion_reason = null, notes = null) {
    const data = {
        result_id: result_id,
        decision: decision,
        csrfmiddlewaretoken: CSRF_TOKEN
    };

    if (exclusion_reason) {
        data.exclusion_reason = exclusion_reason;
    }
    if (notes) {
        data.notes = notes;
    }

    api_request('decision/', {
        body: new URLSearchParams(data),
        onSuccess: () => {
            update_result_card(result_id, decision);
            update_progress_bar();
        }
    });
}

function update_result_card(result_id, decision) {
    const card = document.querySelector(`[data-result-id="${result_id}"]`);
    if (!card) return;

    // Tailwind class definitions matching the template tags
    const button_styles = {
        include: {
            active: 'bg-success text-white hover:bg-success/90',
            inactive: 'border border-success text-success hover:bg-success/10'
        },
        exclude: {
            active: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
            inactive: 'border border-destructive text-destructive hover:bg-destructive/10'
        },
        maybe: {
            active: 'bg-warning text-white hover:bg-warning/90',
            inactive: 'border border-warning text-warning hover:bg-warning/10'
        }
    };

    // All style classes that need to be stripped before applying new ones
    const all_style_classes = [
        'bg-success', 'text-white', 'hover:bg-success/90',
        'border', 'border-success', 'text-success', 'hover:bg-success/10',
        'bg-destructive', 'text-destructive-foreground', 'hover:bg-destructive/90',
        'border-destructive', 'text-destructive', 'hover:bg-destructive/10',
        'bg-warning', 'hover:bg-warning/90',
        'border-warning', 'text-warning', 'hover:bg-warning/10'
    ];

    // Update button states
    const buttons = card.querySelectorAll('.decision-buttons button');
    buttons.forEach(button => {
        const testid = button.getAttribute('data-testid') || '';
        let button_type = null;

        if (testid.startsWith('include-btn')) button_type = 'include';
        else if (testid.startsWith('exclude-btn')) button_type = 'exclude';
        else if (testid.startsWith('maybe-btn')) button_type = 'maybe';

        if (!button_type || !button_styles[button_type]) return;

        // Strip all decision-related style classes
        all_style_classes.forEach(cls => button.classList.remove(cls));

        // Apply active or inactive styles
        const is_active = (button_type === decision);
        const classes = is_active ? button_styles[button_type].active : button_styles[button_type].inactive;
        classes.split(' ').forEach(cls => button.classList.add(cls));
    });

    // Add reviewed indicator to the card (clear previous first)
    card.classList.remove('border-border',
        'border-success/50', 'bg-success/5',
        'border-destructive/50', 'bg-destructive/5',
        'border-warning/50', 'bg-warning/5');
    switch (decision) {
        case 'include':
            card.classList.add('border-success/50', 'bg-success/5');
            break;
        case 'exclude':
            card.classList.add('border-destructive/50', 'bg-destructive/5');
            break;
        case 'maybe':
            card.classList.add('border-warning/50', 'bg-warning/5');
            break;
    }
}

function update_progress_bar() {
    // Reload progress bar component and Quick Actions statistics
    // Use both cache: 'no-store' and a timestamp to aggressively bust browser caches
    fetch(`/review-results/api/${SESSION_ID}/progress/?_t=${new Date().getTime()}`, { cache: 'no-store' })
        .then(response => response.json())
        .then(data => {
            // Update progress bar if element exists
            const progress_bar = document.querySelector('[role="progressbar"]');
            if (progress_bar && data.progress) {
                progress_bar.style.width = data.progress.completion_percentage + '%';
                progress_bar.textContent = `${data.progress.completion_percentage}%`;

                // Update the completion text label if it exists
                const completion_text = document.querySelector('.session-summary span:last-child');
                if (completion_text) {
                    completion_text.textContent = `${data.progress.reviewed_count}/${data.progress.total_results} Reviewed`;
                }
            }

            // Update Quick Actions badges with real-time statistics
            if (data.progress) {
                update_quick_actions_badges(data.progress);
            }
        })
        .catch(error => console.error('Progress update error:', error));
}

function update_quick_actions_badges(progress) {
    // Update badge counts in Quick Actions sidebar
    const badges = {
        'pending': progress.pending_count || 0,
        'include': progress.include_count || 0,
        'exclude': progress.exclude_count || 0,
        'maybe': progress.maybe_count || 0,
        'retrieved': progress.retrieved_count || 0
    };

    // Update each badge by finding the corresponding button and badge element
    Object.keys(badges).forEach(status => {
        // Find button that contains the specific data-testid for the filter
        const selector = `button[data-testid="filter-${status === 'include' ? 'included' : status === 'exclude' ? 'excluded' : status}-btn"]`;
        const buttons = document.querySelectorAll(selector);

        console.log(`[QuickActions] Updating '${status}': Found ${buttons.length} buttons using selector ${selector}`);

        buttons.forEach(button => {
            // The badge is the last span inside the button
            const badge = button.querySelector('span:last-child');
            if (badge && badge.classList.contains('font-mono')) {
                const oldVal = badge.textContent.trim();
                const newVal = String(badges[status]).trim();
                console.log(`[QuickActions] Changing badge value from '${oldVal}' to '${newVal}'`);
                badge.textContent = newVal;
            } else {
                console.warn(`[QuickActions] Badge not found or missing font-mono in button`, button);
            }
        });
    });

    // Update "All Results" badge (an <a> tag, not a button)
    const allBtn = document.querySelector('[data-testid="filter-all-btn"]');
    if (allBtn) {
        const badge = allBtn.querySelector('span:last-child');
        if (badge && badge.classList.contains('font-mono')) {
            badge.textContent = String(progress.total_results || 0);
        }
    }
}

// Notes modal functions
function show_notes_modal(result_id, result_title) {
    document.getElementById('resultId').value = result_id;
    document.getElementById('resultTitle').value = result_title;

    // Load existing notes
    fetch(`/review-results/api/${SESSION_ID}/notes/?result_id=${result_id}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('reviewNotes').value = data.notes || '';
            }
        })
        .catch(error => console.error('Error loading notes:', error));

    document.getElementById('notesModal').showModal();
}

function save_notes() {
    const form = document.getElementById('notesForm');
    const form_data = new FormData(form);

    api_request('notes/save/', {
        body: form_data,
        errorPrefix: 'Error saving notes',
        onSuccess: () => {
            document.getElementById('notesModal').close();
            const result_id = form_data.get('result_id');
            const card = document.querySelector(`[data-result-id="${result_id}"]`);
            if (card) {
                const notes_preview = card.querySelector('.review-notes-preview small');
                if (notes_preview) {
                    const notes = form_data.get('notes');
                    const preview = notes ? (notes.length > 100 ? notes.substring(0, 100) + '...' : notes) : 'No notes';
                    notes_preview.innerHTML = '<svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg> ' + preview;
                }
            }
        }
    });
}

// Bulk Action Functions
function update_bulk_selection() {
    const checkboxes = document.querySelectorAll('.result-checkbox:checked');
    const count = checkboxes.length;
    document.getElementById('selectedCount').textContent = count;

    // Auto-open bulk actions if items are selected
    const bulkActionsDetails = document.getElementById('bulkActionsContainer');
    if (bulkActionsDetails) {
        if (count > 0) {
            bulkActionsDetails.open = true;
        }
    }

    // Update visual state of result cards
    document.querySelectorAll('.result-card').forEach(card => {
        const checkbox = card.querySelector('.result-checkbox');
        if (checkbox && checkbox.checked) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });
}

function select_all() {
    const checkboxes = document.querySelectorAll('.result-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
    });
    update_bulk_selection();
}

function deselect_all() {
    const checkboxes = document.querySelectorAll('.result-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });
    update_bulk_selection();
}

function get_selected_result_ids() {
    const checkboxes = document.querySelectorAll('.result-checkbox:checked');
    return Array.from(checkboxes).map(checkbox => checkbox.value);
}

function bulk_decision(decision) {
    const selected_ids = get_selected_result_ids();

    if (selected_ids.length === 0) {
        alert('Please select at least one result.');
        return;
    }

    if (!confirm(`Are you sure you want to mark ${selected_ids.length} results as "${decision}"?`)) {
        return;
    }

    // Prepare data for bulk API
    const form_body = new URLSearchParams();
    form_body.append('decision', decision);
    form_body.append('csrfmiddlewaretoken', CSRF_TOKEN);

    selected_ids.forEach(id => {
        form_body.append('result_ids[]', id);
    });

    api_request('bulk-decision/', {
        body: form_body,
        onSuccess: () => {
            selected_ids.forEach(result_id => {
                update_result_card(result_id, decision);
            });
            update_progress_bar();
            deselect_all();
        },
        successMessage: (data) => `Successfully marked ${data.processed_count} results as "${decision}".`
    });
}

function show_bulk_exclusion_modal() {
    const selected_ids = get_selected_result_ids();

    if (selected_ids.length === 0) {
        alert('Please select at least one result.');
        return;
    }

    // Store selected IDs for bulk exclusion
    window.bulk_exclusion_ids = selected_ids;

    // Update count in modal
    document.getElementById('bulkExcludeCount').textContent = selected_ids.length;

    // Show the bulk exclusion modal
    document.getElementById('bulkExclusionModal').showModal();
}

function confirm_bulk_exclusion() {
    const form = document.getElementById('bulkExclusionForm');
    const form_data = new FormData(form);
    const exclusion_reason = form_data.get('exclusion_reason');
    const notes = form_data.get('notes');

    if (!exclusion_reason) {
        alert('Please select an exclusion reason.');
        return;
    }

    const selected_ids = window.bulk_exclusion_ids || [];

    if (!confirm(`Are you sure you want to exclude ${selected_ids.length} results?`)) {
        return;
    }

    // Call new bulk API endpoint
    const form_body = new URLSearchParams();
    form_body.append('decision', 'exclude');
    form_body.append('exclusion_reason', exclusion_reason);
    form_body.append('notes', notes || '');
    form_body.append('csrfmiddlewaretoken', CSRF_TOKEN);

    // Add each result_id separately for Django's getlist()
    selected_ids.forEach(id => {
        form_body.append('result_ids[]', id);
    });

    api_request('bulk-decision/', {
        body: form_body,
        onSuccess: () => {
            selected_ids.forEach(result_id => {
                update_result_card(result_id, 'exclude');
            });
            update_progress_bar();
            document.getElementById('bulkExclusionModal').close();
            deselect_all();
        },
        successMessage: (data) => `Successfully excluded ${data.processed_count} results.`
    });
}

// URL Access Tracking
function track_url_access(result_id, success = true, failure_reason = '') {
    fetch(`/review-results/api/${SESSION_ID}/track-url/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': CSRF_TOKEN
        },
        body: new URLSearchParams({
            result_id: result_id,
            success: success ? 'true' : 'false',
            failure_reason: failure_reason,
            csrfmiddlewaretoken: CSRF_TOKEN
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Update statistics when URL access is successfully tracked
                // Added a slight delay to avoid racing the Django transaction commit
                setTimeout(update_progress_bar, 250);
            } else {
                console.error('Failed to track URL access:', data.error);
            }
        })
        .catch(error => {
            console.error('Error tracking URL access:', error);
        });
}

function initialize_url_tracking() {
    // Track clicks on result URLs
    document.querySelectorAll('.result-card a[target="_blank"]').forEach(link => {
        link.addEventListener('click', function (e) {
            const result_card = this.closest('.result-card');
            if (!result_card) return;
            const result_id = result_card.getAttribute('data-result-id');

            // Track successful access (user clicked the link)
            track_url_access(result_id, true);

            // Add "Report Broken Link" button if not already present
            if (!result_card.querySelector('.report-broken-link')) {
                const actions_div = result_card.querySelector('.additional-actions');
                if (!actions_div) return;
                const report_button = document.createElement('button');
                report_button.className = 'inline-flex items-center px-2 py-1 text-xs border border-destructive text-destructive rounded hover:bg-destructive/10 report-broken-link mt-2';
                report_button.innerHTML = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg> Report Broken Link';
                report_button.onclick = function () {
                    report_broken_link(result_id);
                };
                actions_div.appendChild(report_button);
            }
        });
    });
}

function report_broken_link(result_id) {
    if (confirm('Are you sure this link is broken or inaccessible?')) {
        // Track failed access
        track_url_access(result_id, false, 'broken_link');

        // Automatically exclude with "Cannot Access" reason
        submit_decision(result_id, 'exclude', 'no_access', 'URL is broken or inaccessible');

        // Update UI
        const result_card = document.querySelector(`[data-result-id="${result_id}"]`);
        if (!result_card) return;
        const report_button = result_card.querySelector('.report-broken-link');
        if (report_button) {
            report_button.disabled = true;
            report_button.innerHTML = '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg> Reported';
        }
    }
}

// Make functions available globally for inline onclick handlers
window.filter_by_status = filter_by_status;
window.change_per_page = change_per_page;
window.make_decision = make_decision;
window.show_exclusion_modal = show_exclusion_modal;
window.confirm_exclusion = confirm_exclusion;
window.show_notes_modal = show_notes_modal;
window.save_notes = save_notes;
window.update_bulk_selection = update_bulk_selection;
window.select_all = select_all;
window.deselect_all = deselect_all;
window.bulk_decision = bulk_decision;
window.show_bulk_exclusion_modal = show_bulk_exclusion_modal;
window.confirm_bulk_exclusion = confirm_bulk_exclusion;
window.report_broken_link = report_broken_link;
window.initialize_review_interface = initialize_review_interface;

// Legacy compatibility aliases
window.filterByStatus = filter_by_status;
window.changePerPage = change_per_page;
window.makeDecision = make_decision;
window.makeReviewerDecision = make_decision;  // Alias for Workflow #2 (same API endpoint)
window.showExclusionModal = show_exclusion_modal;
window.confirmExclusion = confirm_exclusion;
window.showNotesModal = show_notes_modal;
window.saveNotes = save_notes;
window.updateBulkSelection = update_bulk_selection;
window.selectAll = select_all;
window.deselectAll = deselect_all;
window.bulkDecision = bulk_decision;
window.showBulkExclusionModal = show_bulk_exclusion_modal;
window.confirmBulkExclusion = confirm_bulk_exclusion;
window.reportBrokenLink = report_broken_link;
window.initializeReviewInterface = initialize_review_interface;
