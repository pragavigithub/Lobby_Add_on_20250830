// Main application JavaScript
class WMSApp {
    constructor() {
        this.initializeApp();
        this.setupEventListeners();
        this.registerServiceWorker();
    }

    initializeApp() {
        // Initialize tooltips
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });

        // Initialize modals
        var modalTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="modal"]'));
        var modalList = modalTriggerList.map(function (modalTriggerEl) {
            return new bootstrap.Modal(modalTriggerEl);
        });

        // Setup CSRF token for AJAX requests
        const csrfToken = document.querySelector('meta[name="csrf-token"]');
        if (csrfToken) {
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken.getAttribute('content'));
                    }
                }
            });
        }
    }

    setupEventListeners() {
        // Dashboard card clicks
        document.querySelectorAll('.dashboard-card').forEach(card => {
            card.addEventListener('click', (e) => {
                const url = card.dataset.url;
                if (url) {
                    window.location.href = url;
                }
            });
        });

        // Form submissions with loading states
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (e) => {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    const originalText = submitBtn.textContent;
                    submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
                    
                    // Re-enable button after 5 seconds as fallback
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                    }, 5000);
                }
            });
        });

        // Auto-hide alerts
        document.querySelectorAll('.alert').forEach(alert => {
            setTimeout(() => {
                alert.classList.add('fade');
                setTimeout(() => {
                    alert.remove();
                }, 150);
            }, 5000);
        });
    }

    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/js/service-worker.js')
                .then(registration => {
                    console.log('Service Worker registered successfully:', registration);
                })
                .catch(error => {
                    console.log('Service Worker registration failed:', error);
                });
        }
    }

    // Utility methods
    showLoading(element) {
        element.innerHTML = '<span class="spinner"></span> Loading...';
        element.disabled = true;
    }

    hideLoading(element, originalText) {
        element.innerHTML = originalText;
        element.disabled = false;
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.main-content .container');
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // API methods
    async apiRequest(url, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const mergedOptions = { ...defaultOptions, ...options };

        try {
            const response = await fetch(url, mergedOptions);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Request failed');
            }
            
            return data;
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    }

    async validatePO(poNumber) {
        try {
            const data = await this.apiRequest('/api/validate_po', {
                method: 'POST',
                body: JSON.stringify({ po_number: poNumber })
            });
            return data;
        } catch (error) {
            this.showAlert('Error validating PO: ' + error.message, 'danger');
            return null;
        }
    }

    async validateItem(itemCode) {
        try {
            const data = await this.apiRequest('/api/validate_item', {
                method: 'POST',
                body: JSON.stringify({ item_code: itemCode })
            });
            return data;
        } catch (error) {
            this.showAlert('Error validating item: ' + error.message, 'danger');
            return null;
        }
    }

    async getBins(warehouse) {
        try {
            const data = await this.apiRequest(`/api/get_bins?warehouse=${warehouse}`);
            return data.bins || [];
        } catch (error) {
            this.showAlert('Error fetching bins: ' + error.message, 'danger');
            return [];
        }
    }

    async scanBin(binCode) {
        try {
            const data = await this.apiRequest('/api/scan_bin', {
                method: 'POST',
                body: JSON.stringify({ bin_code: binCode })
            });
            return data.items || [];
        } catch (error) {
            this.showAlert('Error scanning bin: ' + error.message, 'danger');
            return [];
        }
    }

    async printLabel(itemCode, labelFormat = 'standard') {
        try {
            const data = await this.apiRequest('/api/print_label', {
                method: 'POST',
                body: JSON.stringify({ item_code: itemCode, label_format: labelFormat })
            });
            
            if (data.success) {
                this.showAlert('Label printed successfully!', 'success');
                return data.barcode;
            } else {
                throw new Error('Print failed');
            }
        } catch (error) {
            this.showAlert('Error printing label: ' + error.message, 'danger');
            return null;
        }
    }

    async reprintLabel(labelId) {
        try {
            const data = await this.apiRequest('/api/reprint_label', {
                method: 'POST',
                body: JSON.stringify({ label_id: labelId })
            });
            
            if (data.success) {
                this.showAlert('Label reprinted successfully!', 'success');
                return data.barcode;
            } else {
                throw new Error('Reprint failed');
            }
        } catch (error) {
            this.showAlert('Error reprinting label: ' + error.message, 'danger');
            return null;
        }
    }

    // Offline functionality
    isOnline() {
        return navigator.onLine;
    }

    saveOfflineData(key, data) {
        localStorage.setItem(`wms_offline_${key}`, JSON.stringify(data));
    }

    getOfflineData(key) {
        const data = localStorage.getItem(`wms_offline_${key}`);
        return data ? JSON.parse(data) : null;
    }

    clearOfflineData(key) {
        localStorage.removeItem(`wms_offline_${key}`);
    }

    // Sync offline data when online
    async syncOfflineData() {
        if (!this.isOnline()) return;

        const offlineKeys = Object.keys(localStorage).filter(key => 
            key.startsWith('wms_offline_')
        );

        for (const key of offlineKeys) {
            try {
                const data = this.getOfflineData(key.replace('wms_offline_', ''));
                if (data) {
                    // Sync data to server
                    await this.apiRequest('/api/sync_offline', {
                        method: 'POST',
                        body: JSON.stringify({ key: key.replace('wms_offline_', ''), data })
                    });
                    
                    this.clearOfflineData(key.replace('wms_offline_', ''));
                }
            } catch (error) {
                console.error('Error syncing offline data:', error);
            }
        }
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.wmsApp = new WMSApp();
    
    // Check for offline data sync when online
    window.addEventListener('online', () => {
        window.wmsApp.syncOfflineData();
    });
});

// Global utility functions
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function formatNumber(number, decimals = 2) {
    return Number(number).toFixed(decimals);
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0;
        var v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl+Alt+S for scan
    if (e.ctrlKey && e.altKey && e.key === 's') {
        e.preventDefault();
        if (window.barcodeScanner) {
            window.barcodeScanner.startScan();
        }
    }
    
    // Ctrl+Alt+P for print
    if (e.ctrlKey && e.altKey && e.key === 'p') {
        e.preventDefault();
        window.print();
    }
});
