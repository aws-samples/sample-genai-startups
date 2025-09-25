// Delete handlers for workflows, agents, and tools

// Delete workflow handler
function setupWorkflowDeleteHandlers() {
    $('.delete-workflow').on('click', function() {
        const workflowId = $(this).data('id');
        const card = $(this).closest('.col');
        
        showConfirmation('Are you sure you want to delete this workflow? This action cannot be undone.', function() {
            $.ajax({
                url: `/api/workflow/${workflowId}`,
                method: 'DELETE',
                success: function() {
                    card.fadeOut(300, function() {
                        $(this).remove();
                        
                        // Show "no workflows" message if all are deleted
                        if ($('.col').length === 0) {
                            $('.row').replaceWith(`
                                <div class="card">
                                    <div class="card-body text-center">
                                        <p class="mb-0">No workflows found. Create your first workflow to get started.</p>
                                    </div>
                                </div>
                            `);
                        }
                    });
                },
                error: function() {
                    showError('Error deleting workflow');
                }
            });
        }, 'Delete Workflow');
    });
}

// Delete agent handler
function setupAgentDeleteHandlers() {
    $('.delete-agent').on('click', function() {
        const agentId = $(this).data('id');
        const card = $(this).closest('.col');
        
        showConfirmation('Are you sure you want to delete this agent? This action cannot be undone.', function() {
            $.ajax({
                url: `/api/agent/${agentId}`,
                method: 'DELETE',
                success: function() {
                    card.fadeOut(300, function() {
                        $(this).remove();
                        
                        // Show "no agents" message if all are deleted
                        if ($('.col').length === 0) {
                            $('.row').replaceWith(`
                                <div class="card">
                                    <div class="card-body text-center">
                                        <p class="mb-0">No agents found. Create your first agent to get started.</p>
                                    </div>
                                </div>
                            `);
                        }
                    });
                },
                error: function() {
                    showError('Error deleting agent');
                }
            });
        }, 'Delete Agent');
    });
}

// Delete tool handler
function setupToolDeleteHandlers() {
    $('.delete-tool').on('click', function() {
        const toolId = $(this).data('id');
        const card = $(this).closest('.col');
        
        showConfirmation('Are you sure you want to delete this tool? This action cannot be undone.', function() {
            $.ajax({
                url: `/api/tool/${toolId}`,
                method: 'DELETE',
                success: function() {
                    card.fadeOut(300, function() {
                        $(this).remove();
                        
                        // Show "no tools" message if all are deleted
                        if ($('.col').length === 0) {
                            $('.row').replaceWith(`
                                <div class="card">
                                    <div class="card-body text-center">
                                        <p class="mb-0">No tools found. Create your first tool to get started.</p>
                                    </div>
                                </div>
                            `);
                        }
                    });
                },
                error: function() {
                    showError('Error deleting tool');
                }
            });
        }, 'Delete Tool');
    });
}

// Initialize all delete handlers when document is ready
$(document).ready(function() {
    setupWorkflowDeleteHandlers();
    setupAgentDeleteHandlers();
    setupToolDeleteHandlers();
});
