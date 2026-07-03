// Review Workflow #2 utilities
// Shared functions for multi-reviewer workflow and general review UI

function showMessage(type, message) {
    const alertDiv = document.createElement('div');
    const isSuccess = type === 'success';
    alertDiv.className = `relative flex items-start rounded-lg border-l-4 p-4 mb-4 ${isSuccess ? 'border-success bg-success-light' : 'border-destructive bg-error-light'}`;
    alertDiv.innerHTML = `
        <svg class="w-5 h-5 ${isSuccess ? 'text-success' : 'text-error'} mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            ${isSuccess
                ? '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>'
                : '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>'
            }
        </svg>
        <div class="flex-1 ${isSuccess ? 'text-success-foreground' : 'text-error-foreground'}">${message}</div>
        <button type="button" onclick="this.parentElement.remove()" class="${isSuccess ? 'text-success hover:text-success-foreground' : 'text-error hover:text-error-foreground'} ml-2">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg>
        </button>
    `;

    const mainContent = document.querySelector('.order-2.lg\\:order-1');
    if (!mainContent) return;
    mainContent.insertBefore(alertDiv, mainContent.firstChild);

    if (type === 'success') {
        setTimeout(() => {
            alertDiv.style.opacity = '0';
            alertDiv.style.transition = 'opacity 150ms';
            setTimeout(() => alertDiv.remove(), 150);
        }, 10000);
    }
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function markReviewerComplete(markCompleteUrl, sessionDetailUrl) {
    const loadingDiv = document.getElementById('completionLoading');
    const errorDiv = document.getElementById('completionError');
    const confirmBtn = document.getElementById('confirmCompleteBtn');

    loadingDiv.style.display = 'block';
    errorDiv.style.display = 'none';
    confirmBtn.disabled = true;

    fetch(markCompleteUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({})
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'error') {
                errorDiv.style.display = 'block';
                document.getElementById('completionErrorMessage').textContent = data.message;
                loadingDiv.style.display = 'none';
                confirmBtn.disabled = false;
            } else if (data.status === 'waiting') {
                loadingDiv.innerHTML = `
                <div class="rounded-lg border-l-4 border-info bg-info-light p-4">
                    <div class="flex items-start">
                        <svg class="w-5 h-5 text-info mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"></path></svg>
                        <div class="text-info-foreground">
                            <strong>Waiting for other reviewers...</strong>
                            <ul class="mt-2 list-disc list-inside text-sm">
                                ${data.progress.map(p => `
                                    <li>${p.reviewer}: ${p.reviewed}/${p.total} ${p.complete ? '<span class="text-success">✓ Complete</span>' : ''}</li>
                                `).join('')}
                            </ul>
                        </div>
                    </div>
                </div>
            `;
                setTimeout(() => location.reload(), 3000);
            } else if (data.status === 'complete') {
                alert(`All reviewers complete! ${data.conflicts_count || 0} conflicts detected.`);
                window.location.href = data.redirect_url || sessionDetailUrl;
            } else if (data.status === 'success') {
                alert('Review marked complete successfully!');
                location.reload();
            }
        })
        .catch(error => {
            console.error('Error:', error);
            errorDiv.style.display = 'block';
            document.getElementById('completionErrorMessage').textContent =
                'An error occurred. Please try again.';
            loadingDiv.style.display = 'none';
            confirmBtn.disabled = false;
        });
}

function submitWf1Completion() {
    const modal = document.getElementById('wf1CompletionModal');
    const form = document.getElementById('wf1CompleteForm');
    const formData = new FormData(form);

    modal.close();

    fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json().then(data => ({ json: data, redirected: false }));
        }
        if (response.redirected) {
            return { redirected: true, url: response.url };
        }
        return { redirected: true, url: response.url };
    })
    .then(result => {
        if (result.redirected) {
            window.location.href = result.url;
        } else if (result.json) {
            const data = result.json;
            if (data.status === 'confirm_required') {
                // Show confirmation dialog for hidden results
                if (confirm(data.message)) {
                    // Resubmit with confirm_hidden flag
                    const confirmedData = new FormData(form);
                    confirmedData.append('confirm_hidden', 'true');
                    fetch(form.action, {
                        method: 'POST',
                        body: confirmedData,
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    })
                    .then(resp => {
                        if (resp.redirected) {
                            window.location.href = resp.url;
                        } else {
                            window.location.reload();
                        }
                    })
                    .catch(() => window.location.reload());
                }
            } else {
                // Error or unexpected response - reload to show messages
                window.location.reload();
            }
        }
    })
    .catch(() => {
        // Fallback to regular form submission
        form.submit();
    });
}

// Make functions available globally
window.showMessage = showMessage;
window.getCookie = getCookie;
window.markReviewerComplete = markReviewerComplete;
window.submitWf1Completion = submitWf1Completion;
