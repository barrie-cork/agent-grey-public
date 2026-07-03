// Auto-dismiss Django messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const messages = document.querySelectorAll('.messages .alert');

    messages.forEach(message => {
        // Only auto-dismiss if it has the dismissible class
        if (message.classList.contains('alert-dismissible')) {
            setTimeout(() => {
                // Use Bootstrap's alert API if available
                if (typeof bootstrap !== 'undefined' && bootstrap.Alert) {
                    const alert = new bootstrap.Alert(message);
                    alert.close();
                } else {
                    // Fallback to simple removal
                    message.style.transition = 'opacity 0.5s';
                    message.style.opacity = '0';
                    setTimeout(() => {
                        message.remove();
                    }, 500);
                }
            }, 5000);
        }
    });
});
