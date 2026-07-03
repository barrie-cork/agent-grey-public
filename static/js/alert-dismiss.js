/**
 * Alert Dismiss - Vanilla JS replacement for Bootstrap data-bs-dismiss
 * @source Phase 06 Django Base Template Migration
 */
document.addEventListener('DOMContentLoaded', function() {
  document.addEventListener('click', function(event) {
    const dismissButton = event.target.closest('[data-dismiss-alert]');

    if (dismissButton) {
      const alert = dismissButton.closest('[role="alert"]');

      if (alert) {
        alert.style.transition = 'opacity 0.2s ease-out, transform 0.2s ease-out';
        alert.style.opacity = '0';
        alert.style.transform = 'translateX(10px)';

        setTimeout(function() {
          alert.remove();
        }, 200);
      }
    }
  });
});
