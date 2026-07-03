// Offline Backup Functionality
// Handles generating and polling for offline backup Excel files

function initializeOfflineBackup(generateUrl, csrfToken) {
    const backupBtn = document.getElementById('offline-backup-btn');
    if (!backupBtn) return;

    backupBtn.addEventListener('click', function () {
        generateOfflineBackup(generateUrl, csrfToken);
    });
}

function generateOfflineBackup(generateUrl, csrfToken) {
    const btn = document.getElementById('offline-backup-btn');
    const originalContent = btn.innerHTML;

    btn.innerHTML = '<span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent mr-2"></span>Generating...';
    btn.disabled = true;

    fetch(generateUrl, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json',
        }
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => Promise.reject(err));
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'generating') {
                showMessage('success', 'Offline backup generation started! You will be notified when ready for download.');
                pollBackupProgress(data.report_id, data.download_url);
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            console.error('Backup generation failed:', error);
            showMessage('error', error.error || error.message || 'Failed to start backup generation');
            btn.innerHTML = originalContent;
            btn.disabled = false;
        });
}

const BACKUP_BTN_DEFAULT_HTML = '<svg class="w-4 h-4 mr-1.5 inline" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg> Offline Backup';

function resetBackupButton() {
    const btn = document.getElementById('offline-backup-btn');
    btn.innerHTML = BACKUP_BTN_DEFAULT_HTML;
    btn.disabled = false;
}

function pollBackupProgress(reportId, downloadUrl) {
    const pollInterval = setInterval(() => {
        fetch(`/reporting/api/reports/${reportId}/status/`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    resetBackupButton();

                    const freshDownloadUrl = data.download_url || downloadUrl;
                    showMessage('success',
                        `Offline backup ready! <a href="${freshDownloadUrl}" class="font-medium underline hover:text-success-foreground">Click here to download</a>`
                    );
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    resetBackupButton();
                    showMessage('error', 'Backup generation failed. Please try again.');
                }
            })
            .catch(error => {
                console.error('Error polling backup status:', error);
                clearInterval(pollInterval);
                resetBackupButton();
            });
    }, 3000);

    // Stop polling after 5 minutes
    setTimeout(() => {
        clearInterval(pollInterval);
        resetBackupButton();
    }, 300000);
}

window.initializeOfflineBackup = initializeOfflineBackup;
