// Workflow Editor JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Get workflow ID
    const workflowId = document.getElementById('workflow-id').value;
    console.log('Workflow editor initialized with ID:', workflowId);
    
    // Initialize jsPlumb with simplified configuration
    const jsPlumbInstance = jsPlumb.getInstance({
        Container: "workflow-canvas",
        ConnectionsDetachable: false,
        PaintStyle: { 
            stroke: "#6c757d", 
            strokeWidth: 2 
        },
        HoverPaintStyle: { 
            stroke: "#dc3545", 
            strokeWidth: 3 
        },
        ConnectionOverlays: [
            ["Arrow", { 
                location: 1, 
                width: 12, 
                length: 12, 
                id: "arrow",
                foldback: 0.8
            }],
            ["Label", { 
                label: "Click to delete", 
                id: "label", 
                cssClass: "connection-label",
                visible: false
            }]
        ],
        // Use Flowchart connector for more horizontal connections
        Connector: ["Flowchart", { stub: 10, gap: 10, cornerRadius: 5, alwaysRespectStubs: true }],
        // Ensure connections flow left to right with precise positioning
        Anchors: [[1, 0.5, 1, 0], [0, 0.5, -1, 0]]
    });
    
    const canvas = document.getElementById('workflow-canvas');
    let nodes = {};
    let edges = {};
    let connecting = false;
    let sourceNodeId = null;
    
    // Initialize drag and drop with a slight delay to ensure DOM is fully processed
    setTimeout(function() {
        initDragAndDrop();
        console.log('Drag and drop initialized');
    }, 500);
    
    // Initialize drag and drop functionality
    function initDragAndDrop() {
        // Get all draggable items
        const draggableItems = document.querySelectorAll('.draggable-item');
        
        // Add dragstart event listener to each item
        draggableItems.forEach(function(item) {
            item.addEventListener('dragstart', function(e) {
                const data = {
                    type: this.getAttribute('data-type'),
                    id: this.getAttribute('data-id'),
                    name: this.getAttribute('data-name')
                };
                
                e.dataTransfer.setData('text/plain', JSON.stringify(data));
                e.dataTransfer.effectAllowed = 'copy';
                console.log('Drag started:', data);
            });
        });
        
        // Add dragover event listener to canvas
        canvas.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });
        
        // Add drop event listener to canvas
        canvas.addEventListener('drop', function(e) {
            e.preventDefault();
            
            try {
                // Get the data
                const dataStr = e.dataTransfer.getData('text/plain');
                if (!dataStr) {
                    console.error('No data received in drop event');
                    return;
                }
                
                console.log('Drop data received:', dataStr);
                const data = JSON.parse(dataStr);
                
                // Calculate position relative to canvas
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                // Create node on the backend
                const xhr = new XMLHttpRequest();
                xhr.open('POST', `/api/workflow/${workflowId}/nodes`, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        const response = JSON.parse(xhr.responseText);
                        createNode(response.id, data.type, data.id, x, y, data.name);
                    } else {
                        console.error('Error creating node:', xhr.statusText);
                        console.error('Failed to create node: ' + xhr.statusText);
                    }
                };
                xhr.onerror = function() {
                    console.error('Error creating node:', xhr.statusText);
                    console.error('Failed to create node: ' + xhr.statusText);
                };
                // For input/output nodes, use null for reference_id since they don't reference external entities
                const referenceId = (data.type === 'input' || data.type === 'output') ? null : data.id;
                
                xhr.send(JSON.stringify({
                    node_type: data.type,
                    reference_id: referenceId,
                    position_x: x,
                    position_y: y
                }));
            } catch (err) {
                console.error('Error processing drop:', err);
                console.error('Error processing drop: ' + err.message);
            }
        });
    }
    
    // Create a node
    window.createNode = function(nodeId, type, referenceId, x, y, name) {
        // Create node element
        const nodeEl = document.createElement('div');
        nodeEl.id = `node-${nodeId}`;
        nodeEl.className = `node ${type}-node`;
        nodeEl.style.left = `${x}px`;
        nodeEl.style.top = `${y}px`;
        
        // Add node content
        let nodeTitle = name;
        let nodeIcon = '';
        
        if (type === 'input') {
            nodeTitle = 'Input (Start)';
            nodeIcon = '<i class="fas fa-sign-in-alt me-1"></i>';
        } else if (type === 'output') {
            nodeTitle = 'Output (End)';
            nodeIcon = '<i class="fas fa-sign-out-alt me-1"></i>';
        } else if (type === 'agent') {
            nodeIcon = '<i class="fas fa-robot me-1"></i>';
            nodeTitle = name || `Agent ${referenceId}`;
        } else if (type === 'tool') {
            nodeIcon = '<i class="fas fa-tools me-1"></i>';
            nodeTitle = name || `Tool ${referenceId}`;
        }
        
        // Create node title div with safe DOM manipulation
        const nodeTitleDiv = document.createElement('div');
        nodeTitleDiv.className = 'node-title';
        
        // Create and append icon element safely
        if (nodeIcon) {
            const iconElement = document.createElement('i');
            // Extract icon classes from the nodeIcon string safely
            if (type === 'input') {
                iconElement.className = 'fas fa-sign-in-alt me-1';
            } else if (type === 'output') {
                iconElement.className = 'fas fa-sign-out-alt me-1';
            } else if (type === 'agent') {
                iconElement.className = 'fas fa-robot me-1';
            } else if (type === 'tool') {
                iconElement.className = 'fas fa-tools me-1';
            }
            nodeTitleDiv.appendChild(iconElement);
        }
        
        // Add title text safely using textContent to prevent XSS
        const titleText = document.createTextNode(' ' + nodeTitle);
        nodeTitleDiv.appendChild(titleText);
        
        // Create node controls div
        const nodeControlsDiv = document.createElement('div');
        nodeControlsDiv.className = 'node-controls';
        
        // Create connect button
        const connectBtn = document.createElement('button');
        connectBtn.className = 'btn btn-sm btn-outline-primary connect-btn';
        const connectIcon = document.createElement('i');
        connectIcon.className = 'fas fa-link';
        connectBtn.appendChild(connectIcon);
        
        // Create delete button
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-outline-danger delete-btn';
        const deleteIcon = document.createElement('i');
        deleteIcon.className = 'fas fa-times';
        deleteBtn.appendChild(deleteIcon);
        
        // Append buttons to controls div
        nodeControlsDiv.appendChild(connectBtn);
        nodeControlsDiv.appendChild(deleteBtn);
        
        // Append all elements to node
        nodeEl.appendChild(nodeTitleDiv);
        nodeEl.appendChild(nodeControlsDiv);
        
        canvas.appendChild(nodeEl);
        
        // Store node data
        nodes[nodeId] = {
            element: nodeEl,
            type: type,
            referenceId: referenceId
        };
        
        // Make node draggable with jsPlumb
        jsPlumbInstance.draggable(nodeEl, {
            containment: "parent",
            stop: function(event) {
                // Get the new position
                const position = nodeEl.getBoundingClientRect();
                const canvasPosition = canvas.getBoundingClientRect();
                const x = position.left - canvasPosition.left;
                const y = position.top - canvasPosition.top;
                
                // Update node position in backend
                const xhr = new XMLHttpRequest();
                xhr.open('PUT', `/api/workflow/${workflowId}/nodes/${nodeId}`, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.send(JSON.stringify({
                    position_x: x,
                    position_y: y
                }));
            }
        });
        
        // Add endpoints based on node type - simplified approach
        if (type === 'input') {
            // Input nodes only have output (right side) - using precise positioning
            jsPlumbInstance.addEndpoint(nodeEl, {
                anchor: [1, 0.5, 1, 0],  // x=1 (right edge), y=0.5 (middle), dx=1 (pointing right), dy=0 (no vertical orientation)
                isSource: true,
                isTarget: false,
                maxConnections: -1,
                endpoint: ["Dot", { radius: 8 }],
                paintStyle: { fill: "#0d6efd", stroke: "#0d6efd", strokeWidth: 2 }
            });
        } else if (type === 'output') {
            // Output nodes only have input (left side) - using precise positioning
            jsPlumbInstance.addEndpoint(nodeEl, {
                anchor: [0, 0.5, -1, 0],  // x=0 (left edge), y=0.5 (middle), dx=-1 (pointing left), dy=0 (no vertical orientation)
                isSource: false,
                isTarget: true,
                maxConnections: -1,
                endpoint: ["Dot", { radius: 8 }],
                paintStyle: { fill: "#dc3545", stroke: "#dc3545", strokeWidth: 2 }
            });
        } else {
            // Regular nodes have both input and output
            // Output endpoint (right side) - using precise positioning
            jsPlumbInstance.addEndpoint(nodeEl, {
                anchor: [1, 0.5, 1, 0],  // x=1 (right edge), y=0.5 (middle), dx=1 (pointing right), dy=0 (no vertical orientation)
                isSource: true,
                isTarget: false,
                maxConnections: -1,
                endpoint: ["Dot", { radius: 8 }],
                paintStyle: { fill: "#198754", stroke: "#198754", strokeWidth: 2 }
            });
            
            // Input endpoint (left side) - using precise positioning
            jsPlumbInstance.addEndpoint(nodeEl, {
                anchor: [0, 0.5, -1, 0],  // x=0 (left edge), y=0.5 (middle), dx=-1 (pointing left), dy=0 (no vertical orientation)
                isSource: false,
                isTarget: true,
                maxConnections: -1,
                endpoint: ["Dot", { radius: 8 }],
                paintStyle: { fill: "#0dcaf0", stroke: "#0dcaf0", strokeWidth: 2 }
            });
        }
        
        // Connect button handler
        connectBtn.addEventListener('click', function() {
            if (connecting) {
                connecting = false;
                document.querySelectorAll('.node').forEach(function(n) {
                    n.classList.remove('connecting');
                });
                sourceNodeId = null;
            } else {
                connecting = true;
                sourceNodeId = nodeId;
                document.querySelectorAll('.node').forEach(function(n) {
                    n.classList.remove('connecting');
                });
                nodeEl.classList.add('connecting');
            }
        });
        
        // Node click handler for creating connections
        nodeEl.addEventListener('click', function() {
            if (connecting && sourceNodeId !== nodeId) {
                // Validate connection logic
                const sourceNode = nodes[sourceNodeId];
                const targetNode = nodes[nodeId];
                
                // Check if connection is valid
                if (!canConnect(sourceNode.type, targetNode.type)) {
                    console.warn('Invalid connection: Cannot connect these node types');
                    return;
                }
                
                // Create edge on the backend
                const xhr = new XMLHttpRequest();
                xhr.open('POST', `/api/workflow/${workflowId}/edges`, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        const response = JSON.parse(xhr.responseText);
                        createEdge(response.id, sourceNodeId, nodeId);
                        connecting = false;
                        document.querySelectorAll('.node').forEach(function(n) {
                            n.classList.remove('connecting');
                        });
                        sourceNodeId = null;
                    }
                };
                xhr.send(JSON.stringify({
                    source_node_id: sourceNodeId,
                    target_node_id: nodeId
                }));
            }
        });
        
        // Delete button handler
        deleteBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            
            // Delete node on the backend
            const xhr = new XMLHttpRequest();
            xhr.open('DELETE', `/api/workflow/${workflowId}/nodes/${nodeId}`, true);
            xhr.onload = function() {
                if (xhr.status === 200) {
                    // Remove all connections
                    jsPlumbInstance.remove(nodeEl);
                    delete nodes[nodeId];
                }
            };
            xhr.send();
        });
    }
    
    // Check if two node types can be connected
    function canConnect(sourceType, targetType) {
        // Output nodes cannot be sources
        if (sourceType === 'output') return false;
        // Input nodes cannot be targets
        if (targetType === 'input') return false;
        // All other combinations are valid
        return true;
    }
    
    // Create an edge using jsPlumb's programmatic connection
    window.createEdge = function(edgeId, sourceId, targetId) {
        // Find the source and target endpoints
        const sourceEl = document.getElementById(`node-${sourceId}`);
        const targetEl = document.getElementById(`node-${targetId}`);
        
        if (!sourceEl || !targetEl) {
            console.error('Source or target element not found', { sourceId, targetId });
            return;
        }
        
        // Get endpoints for the nodes
        const sourceEndpoints = jsPlumbInstance.getEndpoints(sourceEl);
        const targetEndpoints = jsPlumbInstance.getEndpoints(targetEl);
        
        // Find the right source endpoint (should be isSource=true)
        const sourceEndpoint = sourceEndpoints ? sourceEndpoints.find(ep => ep.isSource) : null;
        // Find the right target endpoint (should be isTarget=true)
        const targetEndpoint = targetEndpoints ? targetEndpoints.find(ep => ep.isTarget) : null;
        
        if (!sourceEndpoint || !targetEndpoint) {
            console.error('Could not find appropriate endpoints', { 
                sourceEndpoints, 
                targetEndpoints,
                sourceEndpoint,
                targetEndpoint
            });
            return;
        }
        
        // Create the connection with explicit connector settings to ensure left-to-right flow
        const connection = jsPlumbInstance.connect({
            source: sourceEndpoint,
            target: targetEndpoint,
            deleteEndpointsOnDetach: false,
            connector: ["Flowchart", { stub: 10, gap: 10, cornerRadius: 5, alwaysRespectStubs: true }],
            anchors: [[1, 0.5, 1, 0], [0, 0.5, -1, 0]]  // Precise positioning for source and target anchors
        });
        
        if (!connection) {
            console.error('Failed to create connection');
            return;
        }
        
        edges[edgeId] = {
            connection: connection,
            sourceId: sourceId,
            targetId: targetId
        };
        
        // Show delete label on hover
        connection.bind('mouseenter', function() {
            connection.showOverlay('label');
        });
        
        connection.bind('mouseexit', function() {
            connection.hideOverlay('label');
        });
        
        // Add delete handler
        connection.bind('click', function() {
            if (confirm('Delete this connection?')) {
                const xhr = new XMLHttpRequest();
                xhr.open('DELETE', `/api/workflow/${workflowId}/edges/${edgeId}`, true);
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        jsPlumbInstance.deleteConnection(connection);
                        delete edges[edgeId];
                    }
                };
                xhr.send();
            }
        });
    }
    
    // Function to capture the workflow canvas as an image
    function captureCanvas() {
        try {
            // Create a temporary canvas for our icon
            const tempCanvas = document.createElement('canvas');
            const ctx = tempCanvas.getContext('2d');
            
            // Set a reasonable size for the icon
            tempCanvas.width = 128;
            tempCanvas.height = 128;
            
            // Fill with a gradient background
            const gradient = ctx.createLinearGradient(0, 0, 128, 128);
            gradient.addColorStop(0, '#4361ee');
            gradient.addColorStop(1, '#3f37c9');
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 128, 128);
            
            // Draw a simple diagram representation
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.lineWidth = 3;
            
            // Draw some connection lines
            ctx.beginPath();
            ctx.moveTo(30, 40);
            ctx.lineTo(60, 60);
            ctx.lineTo(90, 40);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(30, 80);
            ctx.lineTo(60, 60);
            ctx.lineTo(90, 80);
            ctx.stroke();
            
            // Draw some nodes
            ctx.fillStyle = '#cfe2ff';
            ctx.beginPath();
            ctx.arc(30, 40, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            
            ctx.fillStyle = '#d1ecf1';
            ctx.beginPath();
            ctx.arc(60, 60, 15, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            
            ctx.fillStyle = '#d4edda';
            ctx.beginPath();
            ctx.arc(90, 40, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            
            ctx.fillStyle = '#f8d7da';
            ctx.beginPath();
            ctx.arc(30, 80, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            
            ctx.fillStyle = '#fff3cd';
            ctx.beginPath();
            ctx.arc(90, 80, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            
            // Return the data URL
            return tempCanvas.toDataURL('image/png');
        } catch (e) {
            console.error("Error capturing canvas:", e);
            return null;
        }
    }
    
    // Update workflow details
    document.getElementById('workflow-details-form').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const name = document.getElementById('workflow-name').value;
        const description = document.getElementById('workflow-description').value;
        const model_id = document.getElementById('workflow-model').value;
        const saveIcon = document.getElementById('save-graph-icon').checked;
        
        // Prepare data for the API call
        const data = {
            name: name,
            description: description,
            model_id: model_id,
            generate_icon: saveIcon
        };
        
        // If saving icon is enabled, capture the canvas
        if (saveIcon) {
            const canvasData = captureCanvas();
            if (canvasData) {
                data.canvas_data = canvasData;
            }
        }
        
        // Update workflow details
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', `/api/workflow/${workflowId}`, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onload = function() {
            if (xhr.status === 200) {
                console.log('Workflow details updated successfully');
            } else {
                console.error('Error updating workflow details: ' + xhr.responseText);
            }
        };
        xhr.onerror = function() {
            console.error('Error updating workflow details: ' + xhr.statusText);
        };
        xhr.send(JSON.stringify(data));
    });
});
