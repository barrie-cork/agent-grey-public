/**
 * Search Strategy Form JavaScript
 * Handles real-time preview, validation, and interactive features
 */

class SearchStrategyForm {
    constructor() {
        this.form = document.getElementById('strategy-form');
        this.previewTimeout = null;
        this.debounceDelay = 1500;  // Increased from 1000ms
        this.isUpdating = false;     // Prevent duplicate requests
        this.sessionId = this.getSessionId();

        this.init();
    }

    init() {
        this.bindEvents();
        this.initAutoPreview();
        this.loadInitialPreview();
    }

    getSessionId() {
        // Extract session ID from URL or data attribute
        const path = window.location.pathname;
        const match = path.match(/session\/([a-f0-9-]+)\//);
        return match ? match[1] : null;
    }

    bindEvents() {
        // Preview button
        const previewBtn = document.querySelector('[onclick="previewChanges()"]');
        if (previewBtn) {
            previewBtn.onclick = () => this.previewChanges();
        }

        // Validate button
        const validateBtn = document.querySelector('[onclick="validateStrategy()"]');
        if (validateBtn) {
            validateBtn.onclick = () => this.validateStrategy();
        }

        // Form submission
        this.form.addEventListener('submit', (e) => this.handleFormSubmit(e));

        // Auto-save functionality - disabled to prevent duplicate warnings
        // window.addEventListener('beforeunload', (e) => {
        //     if (this.hasUnsavedChanges()) {
        //         e.preventDefault();
        //         e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        //     }
        // });
    }

    initAutoPreview() {
        // Add auto-preview to all relevant form fields
        const watchedFields = [
            'population_terms_text',
            'interest_terms_text',
            'context_terms_text',
            'organization_domains',
            'include_general_search',
            'include_guidelines_filter',
            'search_pdf',
            'search_doc',
            'use_google_search',
            'use_google_scholar',
            'enable_query_splitting',
            'splitting_strategy',
            'max_query_length'
        ];

        watchedFields.forEach(fieldName => {
            const field = document.getElementById(`id_${fieldName}`);
            if (field) {
                if (field.type === 'checkbox') {
                    field.addEventListener('change', () => this.debouncedPreview());
                } else {
                    field.addEventListener('input', () => this.debouncedPreview());
                }
            }
        });

        // SERP provider checkboxes use CheckboxSelectMultiple (dynamic IDs)
        document.querySelectorAll('input[name="serp_providers"]').forEach(cb => {
            cb.addEventListener('change', () => this.debouncedPreview());
        });
    }

    debouncedPreview() {
        clearTimeout(this.previewTimeout);
        this.previewTimeout = setTimeout(() => this.previewChanges(), this.debounceDelay);
    }

    loadInitialPreview() {
        // Load initial preview if there's existing data
        const hasData = this.collectFormData().population_terms.length > 0 ||
                       this.collectFormData().interest_terms.length > 0 ||
                       this.collectFormData().context_terms.length > 0;

        if (hasData) {
            this.previewChanges();
        }
    }

    collectFormData() {
        // Check if we're using the global keywordData (inline JS)
        if (typeof window.keywordData !== 'undefined' && window.keywordData) {
            // Use the global keywordData that the inline JS manages
            const getCheckboxValue = (fieldName) => {
                const field = document.getElementById(`id_${fieldName}`);
                return field ? field.checked : false;
            };

            return {
                population_terms: window.keywordData.population || [],
                interest_terms: window.keywordData.interest || [],
                context_terms: window.keywordData.context || [],
                search_config: {
                    domains: window.keywordData.domains || [],
                    include_general_search: getCheckboxValue('include_general_search'),
                    include_guidelines_filter: getCheckboxValue('include_guidelines_filter'),
                    file_types: [
                        ...(getCheckboxValue('search_pdf') ? ['pdf'] : []),
                        ...(getCheckboxValue('search_doc') ? ['doc'] : [])
                    ],
                    search_types: [
                        ...(getCheckboxValue('use_google_search') ? ['google'] : []),
                        ...(getCheckboxValue('use_google_scholar') ? ['scholar'] : [])
                    ].length ? [
                        ...(getCheckboxValue('use_google_search') ? ['google'] : []),
                        ...(getCheckboxValue('use_google_scholar') ? ['scholar'] : [])
                    ] : ['google'],
                    max_results: parseInt(document.getElementById('id_max_results_per_query')?.value) || 100,
                    serp_providers: Array.from(
                        document.querySelectorAll('input[name="serp_providers"]:checked')
                    ).map(cb => cb.value)
                }
            };
        } else {
            // Fallback to reading from form fields
            const getFieldValue = (fieldName) => {
                const field = document.getElementById(`id_${fieldName}`);
                return field ? field.value : '';
            };

            const getCheckboxValue = (fieldName) => {
                const field = document.getElementById(`id_${fieldName}`);
                return field ? field.checked : false;
            };

            const parseTerms = (text) => {
                if (!text || typeof text !== 'string') {
                    return [];
                }
                return text.split('\n')
                          .map(t => t.trim())
                          .filter(t => t.length > 0);
            };

            return {
                population_terms: parseTerms(getFieldValue('population_terms_text')),
                interest_terms: parseTerms(getFieldValue('interest_terms_text')),
                context_terms: parseTerms(getFieldValue('context_terms_text')),
                search_config: {
                    domains: parseTerms(getFieldValue('organization_domains')),
                    include_general_search: getCheckboxValue('include_general_search'),
                    include_guidelines_filter: getCheckboxValue('include_guidelines_filter'),
                    file_types: [
                        ...(getCheckboxValue('search_pdf') ? ['pdf'] : []),
                        ...(getCheckboxValue('search_doc') ? ['doc'] : [])
                    ],
                    search_types: [
                        ...(getCheckboxValue('use_google_search') ? ['google'] : []),
                        ...(getCheckboxValue('use_google_scholar') ? ['scholar'] : [])
                    ].length ? [
                        ...(getCheckboxValue('use_google_search') ? ['google'] : []),
                        ...(getCheckboxValue('use_google_scholar') ? ['scholar'] : [])
                    ] : ['google'],
                    max_results: parseInt(getFieldValue('max_results_per_query')) || 100,
                    serp_providers: Array.from(
                        document.querySelectorAll('input[name="serp_providers"]:checked')
                    ).map(cb => cb.value)
                }
            };
        }
    }

    async previewChanges() {
        // Prevent duplicate requests
        if (this.isUpdating) {
            console.log('Preview already in progress, skipping...');
            return;
        }

        if (!this.sessionId) {
            console.error('No session ID found');
            console.error('Current URL:', window.location.pathname);
            console.error('Session ID extraction failed');
            this.showError('Unable to find session ID. Please refresh the page.');
            return;
        }

        this.isUpdating = true;  // Set flag
        console.log('Preview update for session:', this.sessionId);

        const formData = this.collectFormData();
        const previewContainer = document.getElementById('query-preview');

        // Show loading state
        if (previewContainer) {
            previewContainer.classList.add('loading');
        }

        try {
            const response = await fetch(`/search-strategy/api/session/${this.sessionId}/update/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(formData)
            });

            // Check if response is ok before parsing
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // DEBUG: Log what the API returns
            console.log('API Response:', data);
            console.log('Queries received:', data.queries);
            console.log('Number of queries:', data.queries ? data.queries.length : 0);

            if (data.success) {
                this.updateQueryPreview(data.queries);
                this.updateProgressIndicators(data.stats);
                this.updateValidationStatus(data.is_complete, data.validation_errors);
            } else {
                console.error('Preview failed:', data.error);
                this.showError('Failed to update preview: ' + data.error);
            }
        } catch (error) {
            console.error('Preview update error:', error);
            console.error('Error stack:', error.stack);
            console.error('Error message:', error.message);
            this.showError(`Error updating preview: ${error.message || 'Network error occurred'}`);
        } finally {
            this.isUpdating = false;  // Clear flag
            // Remove loading state
            if (previewContainer) {
                previewContainer.classList.remove('loading');
            }
        }

        // Check query lengths after preview update
        await this.checkQueryLengths();
    }

    async checkQueryLengths() {
        if (!this.sessionId) {
            return;
        }

        const formData = this.collectFormData();

        // Add splitting configuration to form data
        const splittingEnabled = document.getElementById('id_enable_query_splitting')?.checked;
        const splittingStrategy = document.getElementById('id_splitting_strategy')?.value;
        const maxQueryLength = document.getElementById('id_max_query_length')?.value;

        if (formData.search_config) {
            formData.search_config.query_splitting = {
                enabled: splittingEnabled || false,
                strategy: splittingStrategy || 'by_pic_terms',
                max_query_length: parseInt(maxQueryLength) || 2000
            };
        }

        try {
            const response = await fetch(`/search-strategy/session/${this.sessionId}/check-query-lengths/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(formData)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            if (result.has_issues) {
                this.showLengthWarning(result.issues);
            } else {
                this.hideLengthWarning();
            }

            // Update splitting preview if enabled
            if (splittingEnabled && result.split_count !== undefined) {
                this.updateSplittingPreview(result.split_count);
            } else {
                this.hideSplittingPreview();
            }

        } catch (error) {
            console.error('Error checking query lengths:', error);
        }
    }

    showLengthWarning(issues) {
        const warningDiv = document.getElementById('query-length-warning');
        const warningMessage = document.getElementById('warning-message');

        if (warningDiv && warningMessage) {
            const totalExcess = issues.reduce((sum, issue) => sum + issue.excess, 0);
            const avgExcess = Math.round(totalExcess / issues.length);

            let message = `<strong>${issues.length} queries exceed the recommended length limit.</strong><br>`;
            message += `<small>Average excess: ${avgExcess} characters. Consider enabling query splitting.</small>`;

            // Show details for first few issues
            if (issues.length <= 3) {
                message += '<ul class="mb-0 mt-2">';
                issues.forEach(issue => {
                    message += `<li><small>${issue.type} query ${issue.domain ? `(${issue.domain})` : ''}: ${issue.length} chars (${issue.excess} over limit)</small></li>`;
                });
                message += '</ul>';
            }

            warningMessage.innerHTML = message;
            warningDiv.classList.remove('d-none');
        }
    }

    hideLengthWarning() {
        const warningDiv = document.getElementById('query-length-warning');
        if (warningDiv) {
            warningDiv.classList.add('d-none');
        }
    }

    updateSplittingPreview(splitCount) {
        const previewDiv = document.getElementById('split-preview');
        const previewMessage = document.getElementById('split-preview-message');

        if (previewDiv && previewMessage) {
            previewMessage.textContent = `Query splitting enabled: Will generate ${splitCount} queries after splitting.`;
            previewDiv.classList.remove('d-none');
        }
    }

    hideSplittingPreview() {
        const previewDiv = document.getElementById('split-preview');
        if (previewDiv) {
            previewDiv.classList.add('d-none');
        }
    }

    updateQueryPreview(queries) {
        const preview = document.getElementById('query-preview');
        if (!preview) return;

        // DEBUG: Log what we're trying to display
        console.log('updateQueryPreview called with:', queries);
        console.log('Preview element found:', preview);

        if (queries && queries.length > 0) {
            let html = '<p class="text-muted small mb-3">Base preview - actual query may include additional filters</p>';
            queries.forEach((query, index) => {
                const domain = query.domain || 'General Search';
                const typeColor = query.type === 'domain-specific' ? 'primary' : 'secondary';

                console.log(`Building HTML for query ${index + 1}:`, query);

                html += `
                    <div class="query-item mb-3">
                        <div class="d-flex justify-content-between mb-2">
                            <span class="font-weight-bold">${this.escapeHtml(domain)}</span>
                            <small class="badge badge-${typeColor}">${query.type}</small>
                        </div>
                        <code class="small">${this.escapeHtml(query.query)}</code>
                    </div>
                `;
            });
            console.log('Final HTML:', html);
            preview.innerHTML = html;
        } else {
            console.log('No queries to display');
            preview.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-search fa-2x mb-2"></i>
                    <p>Add PIC terms to see query preview</p>
                </div>
            `;
        }
    }

    updateProgressIndicators(stats) {
        // Update progress counters
        const counters = document.querySelectorAll('.badge-counter');
        const counts = [stats.population_count, stats.interest_count, stats.context_count];

        counters.forEach((counter, index) => {
            if (counts[index] !== undefined) {
                counter.textContent = counts[index];
            }
        });

        // Update progress item classes
        const items = document.querySelectorAll('.strategy-progress-item');
        items.forEach((item, index) => {
            if (counts[index] !== undefined) {
                item.className = 'strategy-progress-item ' + (counts[index] > 0 ? 'complete' : 'empty');
            }
        });

        // Update total terms counter with specific selector
        const progressBody = document.getElementById('strategy-progress-body');
        if (progressBody) {
            const totalElement = progressBody.querySelector('strong');
            if (totalElement && stats.total_terms !== undefined) {
                totalElement.textContent = `Total Terms: ${stats.total_terms}`;
            }
        } else {
            console.warn('Strategy progress body not found');
        }
    }

    updateValidationStatus(isComplete, validationErrors) {
        // Update completion badge with specific selector
        const statusBadges = document.querySelectorAll('[data-completion-status]');
        statusBadges.forEach(badge => {
            badge.className = isComplete ? 'badge badge-success' : 'badge badge-warning';
            badge.textContent = isComplete ? 'Complete' : 'In Progress';
        });

        // Show/hide continue button
        const continueBtn = document.querySelector('[name="save_and_continue"]');
        if (continueBtn) {
            continueBtn.style.display = isComplete ? 'inline-block' : 'none';
        }

        // Update validation errors (if any)
        this.displayValidationErrors(validationErrors);
    }

    displayValidationErrors(errors) {
        // Remove existing error alerts
        const existingAlerts = document.querySelectorAll('.alert-warning');
        existingAlerts.forEach(alert => {
            if (alert.textContent.includes('Please address these issues')) {
                alert.remove();
            }
        });

        if (errors && Object.keys(errors).length > 0) {
            const errorHtml = `
                <div class="alert alert-warning">
                    <h6>Please address these issues:</h6>
                    <ul>
                        ${Object.values(errors).map(error => `<li>${this.escapeHtml(error)}</li>`).join('')}
                    </ul>
                </div>
            `;

            const formBody = document.getElementById('strategy-form-body');
            if (formBody) {
                formBody.insertAdjacentHTML('afterbegin', errorHtml);
            } else {
                console.error('Strategy form body not found - cannot display validation errors');
            }
        }
    }

    validateStrategy() {
        const formData = this.collectFormData();
        let errors = [];

        // Check PIC terms
        const totalTerms = formData.population_terms.length +
                          formData.interest_terms.length +
                          formData.context_terms.length;

        if (totalTerms === 0) {
            errors.push('At least one PIC category must have terms');
        }

        // Check domains or general search
        if (formData.search_config.domains.length === 0 &&
            !formData.search_config.include_general_search) {
            errors.push('Must specify domains or enable general search');
        }

        // File types are optional - users can search webpages without file type filters

        // Only show errors if validation fails
        if (errors.length > 0) {
            this.showError('Please fix the following issues:\n\n• ' + errors.join('\n• '));
        }

        return errors.length === 0;
    }

    handleFormSubmit(e) {
        // Prevent default to handle validation first
        e.preventDefault();

        // Prevent double submission
        if (this.form.dataset.submitting === 'true') {
            console.log('Form already submitting, ignoring duplicate submission');
            return false;
        }
        this.form.dataset.submitting = 'true';

        // Check which button triggered the submission
        const submitButton = e.submitter || document.activeElement;
        const isExecuteSearch = submitButton && (
            submitButton.name === 'execute_search' ||
            (submitButton.name === 'action' && submitButton.value === 'save_and_monitor')
        );

        // For execute search, do validation only
        if (isExecuteSearch) {
            // Basic validation
            if (!this.validateStrategy()) {
                // Reset submission flag on validation failure
                this.form.dataset.submitting = 'false';
                return false;
            }

            // Add hidden input to ensure button value is included
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = 'action';
            hiddenInput.value = 'save_and_monitor';
            this.form.appendChild(hiddenInput);
        }

        // Disable beforeunload temporarily
        window.onbeforeunload = null;

        // Show loading state
        const submitBtns = this.form.querySelectorAll('button[type="submit"]');
        submitBtns.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' +
                           (isExecuteSearch ? 'Starting execution...' : 'Saving...');
        });

        // Actually submit the form
        this.form.submit();
        return true;
    }

    hasUnsavedChanges() {
        // Simple check for unsaved changes
        const formData = this.collectFormData();
        return formData.population_terms.length > 0 ||
               formData.interest_terms.length > 0 ||
               formData.context_terms.length > 0;
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showError(message) {
        // Simple alert for now - could be enhanced with toast notifications
        alert(message);
    }

    showSuccess(message) {
        // Simple alert for now - could be enhanced with toast notifications
        alert(message);
    }
}

// Legacy function support for inline onclick handlers
function previewChanges() {
    if (window.strategyForm) {
        window.strategyForm.previewChanges();
    }
}

function validateStrategy() {
    if (window.strategyForm) {
        window.strategyForm.validateStrategy();
    }
}

// Initialize only once - prevent duplicate instances
window.strategyForm = null;
document.addEventListener('DOMContentLoaded', () => {
    if (!window.strategyForm) {
        window.strategyForm = new SearchStrategyForm();
    }
});
