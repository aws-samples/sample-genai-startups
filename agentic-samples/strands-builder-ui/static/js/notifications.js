/**
 * Notification system for Strands GUI
 * Provides modal-based notifications instead of browser alerts
 */

// Create the modal element if it doesn't exist
function ensureModalExists() {
    if ($('#notification-modal').length === 0) {
        const modalHtml = `
            <div class="modal fade" id="notification-modal" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="notification-title">Notification</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" id="notification-body">
                            Message goes here
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary" data-bs-dismiss="modal">OK</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        $('body').append(modalHtml);
    }
}

// Create the confirmation modal if it doesn't exist
function ensureConfirmModalExists() {
    if ($('#confirm-modal').length === 0) {
        const modalHtml = `
            <div class="modal fade" id="confirm-modal" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="confirm-title">Confirm</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" id="confirm-body">
                            Are you sure?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-danger" id="confirm-ok-btn">Confirm</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        $('body').append(modalHtml);
    }
}

// Show a notification modal
function showNotification(message, title = 'Notification') {
    ensureModalExists();
    $('#notification-title').text(title);
    $('#notification-body').text(message);
    
    const modal = new bootstrap.Modal(document.getElementById('notification-modal'));
    modal.show();
}

// Show a success notification
function showSuccess(message) {
    showNotification(message, 'Success');
}

// Show an error notification
function showError(message) {
    showNotification(message, 'Error');
}

// Show a confirmation dialog and execute callback if confirmed
function showConfirmation(message, callback, title = 'Confirm') {
    ensureConfirmModalExists();
    $('#confirm-title').text(title);
    $('#confirm-body').text(message);
    
    // Remove previous event handlers
    $('#confirm-ok-btn').off('click');
    
    // Add new event handler
    $('#confirm-ok-btn').on('click', function() {
        $('#confirm-modal').modal('hide');
        callback();
    });
    
    const modal = new bootstrap.Modal(document.getElementById('confirm-modal'));
    modal.show();
}