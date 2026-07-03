class DashboardManager {
    constructor() {
        this.initialize_filters();
        this.initialize_cards();
        this.initialize_messages();
        this.initialize_stat_buttons();
    }

    initialize_filters() {
        // Real-time search
        const search_input = document.querySelector('input[name="q"]');
        if (search_input) {
            let debounce_timer;
            search_input.addEventListener('input', (e) => {
                clearTimeout(debounce_timer);
                debounce_timer = setTimeout(() => {
                    this.filter_sessions(e.target.value);
                }, 300);
            });
        }
    }

    initialize_stat_buttons() {
        // Add click handlers for stat filter buttons
        const stat_buttons = document.querySelectorAll('.stat-button');
        const status_input = document.getElementById('status-filter');
        const filter_form = document.getElementById('dashboard-filter-form');

        // Set initial active state based on current filter
        const current_filter = new URLSearchParams(window.location.search).get('status') || 'all';
        this.update_active_button(current_filter);

        stat_buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                const filter_value = e.currentTarget.dataset.filter;

                // Update active state
                this.update_active_button(filter_value);

                // Update the hidden input to match
                if (status_input) {
                    status_input.value = filter_value;
                }

                // Submit the form to trigger filter
                if (filter_form) {
                    filter_form.submit();
                }
            });
        });
    }

    update_active_button(filter_value) {
        // Remove active class from all buttons
        document.querySelectorAll('.stat-button').forEach(btn => {
            btn.classList.remove('active');
        });

        // Add active class to current button
        const active_button = document.querySelector(`.stat-button[data-filter="${filter_value}"]`);
        if (active_button) {
            active_button.classList.add('active');
        }
    }

    initialize_cards() {
        // Make cards clickable
        document.querySelectorAll('.session-card').forEach(card => {
            const link = card.querySelector('.primary-action');
            if (link) {
                card.style.cursor = 'pointer';
                card.addEventListener('click', (e) => {
                    if (!e.target.closest('a, button')) {
                        link.click();
                    }
                });
            }
        });
    }

    filter_sessions(query) {
        // Client-side filtering for immediate feedback
        const cards = document.querySelectorAll('.session-card');
        const lower_query = query.toLowerCase();

        cards.forEach(card => {
            const title = card.querySelector('.card-title').textContent.toLowerCase();
            const description = card.querySelector('.card-text');
            const desc_text = description ? description.textContent.toLowerCase() : '';

            if (title.includes(lower_query) || desc_text.includes(lower_query)) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
    }

    initialize_messages() {
        // Auto-dismiss messages
        document.querySelectorAll('.alert-dismissible').forEach(alert => {
            setTimeout(() => {
                const bs_alert = new bootstrap.Alert(alert);
                bs_alert.close();
            }, 5000);
        });
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new DashboardManager();
});
