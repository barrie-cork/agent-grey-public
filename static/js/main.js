/**
 * Thesis Grey - Main JavaScript
 * Contains common functionality used across the application
 * Uses vanilla JS for toasts (no Bootstrap dependencies)
 */

// Main application object
const ThesisGrey = {
    // Application configuration
    config: {
        // CSRF token for AJAX requests
        csrfToken: document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
        // API endpoints
        apiEndpoints: {
            // Will be populated as needed by individual pages
        },
        // UI settings
        ui: {
            animationDuration: 300,
            toastDuration: 5000,
            loadingDelay: 200
        }
    },

    // Initialize the application
    init: function() {
        this.setupCSRF();
        this.setupToasts();
        this.setupLoadingStates();
        this.setupFormValidation();
        console.log('Thesis Grey initialized');
    },

    // Setup CSRF token for all AJAX requests
    setupCSRF: function() {
        // Add CSRF token to all AJAX requests
        const csrfToken = this.config.csrfToken;
        if (csrfToken) {
            // For jQuery if it's loaded
            if (typeof $ !== 'undefined') {
                $.ajaxSetup({
                    beforeSend: function(xhr, settings) {
                        if (!this.crossDomain) {
                            xhr.setRequestHeader('X-CSRFToken', csrfToken);
                        }
                    }
                });
            }

            // For fetch API
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                if (!options.headers) {
                    options.headers = {};
                }
                if (!options.headers['X-CSRFToken']) {
                    options.headers['X-CSRFToken'] = csrfToken;
                }
                return originalFetch(url, options);
            };
        }
    },

    // Setup toast notifications with vanilla JS
    setupToasts: function() {
        // Auto-show any toasts that are initially visible (e.g., Django messages)
        // Skip toasts that are hidden (these are managed elsewhere like feedback system)
        const toastElList = Array.from(document.querySelectorAll('.toast, [data-toast]')).filter(function(toastEl) {
            return toastEl && window.getComputedStyle(toastEl).display !== 'none';
        });

        // Only proceed if there are actually visible toast elements on the page
        if (toastElList.length === 0) {
            return;
        }

        // Auto-hide each toast after the configured duration
        toastElList.forEach(function(toastEl) {
            if (!toastEl || !toastEl.classList) {
                return;
            }

            // Set aria attributes for accessibility
            toastEl.setAttribute('aria-live', 'assertive');
            toastEl.setAttribute('aria-atomic', 'true');

            // Auto-hide after delay
            setTimeout(function() {
                ThesisGrey.ui.hideToast(toastEl);
            }, ThesisGrey.config.ui.toastDuration);

            // Setup close button handlers
            const closeBtn = toastEl.querySelector('[data-toast-close], .btn-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', function() {
                    ThesisGrey.ui.hideToast(toastEl);
                });
            }
        });
    },

    // Setup loading states for buttons and forms
    setupLoadingStates: function() {
        // Add loading state to buttons when forms are submitted
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn && !submitBtn.disabled) {
                    ThesisGrey.ui.setButtonLoading(submitBtn, true);

                    // Set a timeout to prevent infinite loading if something goes wrong
                    setTimeout(() => {
                        ThesisGrey.ui.setButtonLoading(submitBtn, false);
                    }, 30000); // 30 seconds
                }
            });
        });
    },

    // Setup client-side form validation
    setupFormValidation: function() {
        // Add validation classes on form submission
        const forms = document.querySelectorAll('.needs-validation');
        Array.prototype.slice.call(forms).forEach(function(form) {
            form.addEventListener('submit', function(event) {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('validated');
            }, false);
        });
    },

    // UI utility functions
    ui: {
        // Show/hide loading spinner on buttons
        setButtonLoading: function(button, isLoading) {
            if (isLoading) {
                button.disabled = true;
                button.dataset.originalText = button.innerHTML;
                button.innerHTML = '<span class="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2"></span>Loading...';
                button.classList.add('loading');
            } else {
                button.disabled = false;
                button.innerHTML = button.dataset.originalText || button.innerHTML;
                button.classList.remove('loading');
            }
        },

        // Show toast notification (vanilla JS implementation)
        showToast: function(message, type = 'info') {
            const toastContainer = document.getElementById('toast-container') || this.createToastContainer();
            const toast = this.createToast(message, type);
            toastContainer.appendChild(toast);

            // Trigger reflow for animation
            toast.offsetHeight;

            // Show toast with animation
            toast.classList.remove('opacity-0', 'translate-y-2');
            toast.classList.add('opacity-100', 'translate-y-0');

            // Auto-hide after delay
            setTimeout(() => {
                this.hideToast(toast);
            }, ThesisGrey.config.ui.toastDuration);
        },

        // Hide toast with animation
        hideToast: function(toast) {
            if (!toast) return;

            // Animate out
            toast.classList.remove('opacity-100', 'translate-y-0');
            toast.classList.add('opacity-0', 'translate-y-2');

            // Remove after animation
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        },

        // Create toast container if it doesn't exist
        createToastContainer: function() {
            const container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
            document.body.appendChild(container);
            return container;
        },

        // Create a toast element with Tailwind classes
        createToast: function(message, type) {
            const toast = document.createElement('div');

            // Map type to Tailwind color classes
            const typeClasses = {
                'success': 'bg-green-600 text-white',
                'danger': 'bg-red-600 text-white',
                'error': 'bg-red-600 text-white',
                'warning': 'bg-yellow-500 text-white',
                'info': 'bg-blue-600 text-white',
                'primary': 'bg-primary text-white'
            };

            const colorClass = typeClasses[type] || typeClasses['info'];

            toast.className = `flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg ${colorClass} opacity-0 translate-y-2 transition-all duration-300`;
            toast.setAttribute('role', 'alert');
            toast.setAttribute('aria-live', 'assertive');
            toast.setAttribute('aria-atomic', 'true');

            toast.innerHTML = `
                <div class="flex-1">${message}</div>
                <button type="button" class="text-white/80 hover:text-white" data-toast-close aria-label="Close">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            `;

            // Bind close button
            const closeBtn = toast.querySelector('[data-toast-close]');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    this.hideToast(toast);
                });
            }

            return toast;
        },

        // Show/hide loading overlay
        showLoadingOverlay: function(show = true, message = 'Loading...') {
            let overlay = document.getElementById('loading-overlay');

            if (show) {
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.id = 'loading-overlay';
                    overlay.className = 'fixed inset-0 flex items-center justify-center bg-black/50 z-[9999]';
                    overlay.innerHTML = `
                        <div class="text-center text-white">
                            <div class="inline-block w-12 h-12 border-4 border-white border-t-transparent rounded-full animate-spin mb-2"></div>
                            <div>${message}</div>
                        </div>
                    `;
                    document.body.appendChild(overlay);
                }
                overlay.style.display = 'flex';
            } else if (overlay) {
                overlay.style.display = 'none';
            }
        },

        // Smooth scroll to element
        scrollToElement: function(selector, offset = 0) {
            const element = document.querySelector(selector);
            if (element) {
                const top = element.offsetTop - offset;
                window.scrollTo({
                    top: top,
                    behavior: 'smooth'
                });
            }
        },

        // Debounce function for search inputs
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    },

    // API utility functions
    api: {
        // Generic GET request
        get: function(url) {
            return fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            }).then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            });
        },

        // Generic POST request
        post: function(url, data) {
            return fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            }).then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            });
        }
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    ThesisGrey.init();
});

// Export for use in other scripts
window.ThesisGrey = ThesisGrey;
