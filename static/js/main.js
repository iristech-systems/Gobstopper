// Tempest Framework - Main JavaScript

// Global variables
let websocket = null;
let isConnected = false;

// Modal Functions
function openTasksModal() {
    document.getElementById('tasksModal').style.display = 'block';
}

function closeTasksModal() {
    document.getElementById('tasksModal').style.display = 'none';
}

function openWebSocketDemo() {
    document.getElementById('websocketModal').style.display = 'block';
}

function closeWebSocketModal() {
    document.getElementById('websocketModal').style.display = 'none';
    if (websocket) {
        disconnectWebSocket();
    }
}

// Close modals when clicking outside
window.onclick = function(event) {
    const tasksModal = document.getElementById('tasksModal');
    const websocketModal = document.getElementById('websocketModal');
    
    if (event.target === tasksModal) {
        closeTasksModal();
    }
    if (event.target === websocketModal) {
        closeWebSocketModal();
    }
}

// Task Management Functions
async function queueEmailTask() {
    updateTaskResults('Queueing email task...');
    
    try {
        const response = await fetch('/api/tasks/email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({
                to: 'demo@example.com',
                subject: 'Test Email from Tempest',
                body: 'This is a test email generated from the Tempest demo!'
            })
        });
        
        const data = await response.json();
        updateTaskResults(`✅ Email task queued!\nTask ID: ${data.task_id}\nPriority: ${data.priority}`);
        
        // Monitor task progress
        setTimeout(() => monitorTask(data.task_id), 1000);
        
    } catch (error) {
        updateTaskResults(`❌ Error queueing email task: ${error.message}`);
    }
}

async function queueProcessingTask() {
    updateTaskResults('Queueing processing task...');
    
    try {
        const response = await fetch('/api/tasks/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({
                items: ['item1', 'item2', 'item3', 'item4', 'item5']
            })
        });
        
        const data = await response.json();
        updateTaskResults(`✅ Processing task queued!\nTask ID: ${data.task_id}\nMessage: ${data.message}`);
        
        // Monitor task progress
        setTimeout(() => monitorTask(data.task_id), 1000);
        
    } catch (error) {
        updateTaskResults(`❌ Error queueing processing task: ${error.message}`);
    }
}

async function queueLongTask() {
    updateTaskResults('Queueing long running task...');
    
    try {
        const response = await fetch('/api/tasks/long', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({
                duration: 15
            })
        });
        
        const data = await response.json();
        updateTaskResults(`✅ Long task queued!\nTask ID: ${data.task_id}\nMessage: ${data.message}\nMax Retries: ${data.max_retries}`);
        
        // Monitor task progress
        setTimeout(() => monitorTask(data.task_id), 1000);
        
    } catch (error) {
        updateTaskResults(`❌ Error queueing long task: ${error.message}`);
    }
}

async function getTaskStats() {
    updateTaskResults('Fetching task statistics...');
    
    try {
        const response = await fetch('/api/tasks');
        const data = await response.json();
        
        const statsText = `📊 Task Statistics:
Total Tasks: ${data.stats.total}
Running Tasks: ${data.stats.running}
Queued Tasks: ${data.stats.queued}

Status Breakdown:
${Object.entries(data.stats.by_status).map(([status, count]) => `  ${status}: ${count}`).join('\n')}

Category Breakdown:
${Object.entries(data.stats.by_category).map(([category, count]) => `  ${category}: ${count}`).join('\n')}`;
        
        updateTaskResults(statsText);
        
    } catch (error) {
        updateTaskResults(`❌ Error fetching task stats: ${error.message}`);
    }
}

async function monitorTask(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}`);
        const task = await response.json();
        
        if (response.ok) {
            const statusEmoji = {
                'pending': '⏳',
                'started': '🔄',
                'success': '✅',
                'failed': '❌',
                'cancelled': '🚫',
                'retry': '🔄'
            }[task.status] || '❓';
            
            let taskInfo = `${statusEmoji} Task ${task.id}:
Name: ${task.name}
Status: ${task.status}
Progress: ${task.progress}%`;
            
            if (task.result) {
                taskInfo += `\nResult: ${JSON.stringify(task.result, null, 2)}`;
            }
            
            if (task.error) {
                taskInfo += `\nError: ${task.error}`;
            }
            
            updateTaskResults(taskInfo);
            
            // Continue monitoring if task is still running
            if (task.status === 'started' || task.status === 'pending') {
                setTimeout(() => monitorTask(taskId), 2000);
            }
        } else {
            updateTaskResults(`❌ Task ${taskId} not found`);
        }
    } catch (error) {
        updateTaskResults(`❌ Error monitoring task: ${error.message}`);
    }
}

function updateTaskResults(message) {
    const resultsDiv = document.getElementById('taskResults');
    const timestamp = new Date().toLocaleTimeString();
    resultsDiv.textContent = `[${timestamp}] ${message}`;
    resultsDiv.scrollTop = resultsDiv.scrollHeight;
}

// WebSocket Functions
function connectWebSocket() {
    if (websocket) {
        return;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/echo`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = function(event) {
        isConnected = true;
        updateConnectionStatus(true);
        addWebSocketMessage('Connected to WebSocket server', 'system');
    };
    
    websocket.onmessage = function(event) {
        addWebSocketMessage(event.data, 'received');
    };
    
    websocket.onclose = function(event) {
        isConnected = false;
        websocket = null;
        updateConnectionStatus(false);
        addWebSocketMessage(`Connection closed (code: ${event.code})`, 'system');
    };
    
    websocket.onerror = function(error) {
        addWebSocketMessage('WebSocket error occurred', 'system');
        console.error('WebSocket error:', error);
    };
}

function disconnectWebSocket() {
    if (websocket) {
        websocket.close();
        websocket = null;
        isConnected = false;
        updateConnectionStatus(false);
    }
}

function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (message && websocket && isConnected) {
        websocket.send(message);
        addWebSocketMessage(message, 'sent');
        messageInput.value = '';
    }
}

function updateConnectionStatus(connected) {
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    
    connectBtn.disabled = connected;
    disconnectBtn.disabled = !connected;
    messageInput.disabled = !connected;
    sendBtn.disabled = !connected;
    
    if (connected) {
        connectBtn.textContent = 'Connected';
        connectBtn.style.background = '#27ae60';
    } else {
        connectBtn.textContent = 'Connect';
        connectBtn.style.background = '#3498db';
    }
}

function addWebSocketMessage(message, type) {
    const messagesDiv = document.getElementById('websocketMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `ws-message ${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    const typeLabel = {
        'sent': '→ Sent',
        'received': '← Received',
        'system': '⚡ System'
    }[type] || type;
    
    messageDiv.innerHTML = `<strong>[${timestamp}] ${typeLabel}:</strong><br>${message}`;
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Utility Functions
function getCSRFToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Enable enter key for WebSocket message input
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    }
    
    // Auto-focus message input when modal opens
    const websocketModal = document.getElementById('websocketModal');
    if (websocketModal) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                    if (websocketModal.style.display === 'block') {
                        setTimeout(() => {
                            const input = document.getElementById('messageInput');
                            if (input && !input.disabled) {
                                input.focus();
                            }
                        }, 100);
                    }
                }
            });
        });
        
        observer.observe(websocketModal, { attributes: true });
    }
    
    console.log('🌪️ Tempest Framework Demo Loaded');
    console.log('Available features:');
    console.log('  - Interactive API testing');
    console.log('  - Background task management');
    console.log('  - WebSocket communication');
    console.log('  - Security feature demos');
});

// Notification system for demonstration
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 3000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;
    
    const colors = {
        'info': '#3498db',
        'success': '#27ae60',
        'warning': '#f39c12',
        'error': '#e74c3c'
    };
    
    notification.style.backgroundColor = colors[type] || colors.info;
    
    document.body.appendChild(notification);
    
    // Slide in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 3000);
}