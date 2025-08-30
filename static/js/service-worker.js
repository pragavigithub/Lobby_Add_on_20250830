// Service Worker for PWA functionality
const CACHE_NAME = 'wms-cache-v1';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/barcode-scanner.js',
    '/static/manifest.json',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
    // Bootstrap CSS and JS
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    // jQuery
    'https://code.jquery.com/jquery-3.6.0.min.js',
    // QuaggaJS for barcode scanning
    'https://cdn.jsdelivr.net/npm/quagga@0.12.1/dist/quagga.min.js',
    // QR Scanner
    'https://cdn.jsdelivr.net/npm/qr-scanner@1.4.2/qr-scanner.min.js',
    // Feather Icons
    'https://cdn.jsdelivr.net/npm/feather-icons@4.28.0/dist/feather.min.js'
];

// Install event - cache resources
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
    );
});

// Fetch event - serve from cache when offline
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Return cached version or fetch from network
                if (response) {
                    return response;
                }
                
                // Clone the request because it's a stream
                const fetchRequest = event.request.clone();
                
                return fetch(fetchRequest).then(response => {
                    // Check if we received a valid response
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }
                    
                    // Clone the response because it's a stream
                    const responseToCache = response.clone();
                    
                    caches.open(CACHE_NAME)
                        .then(cache => {
                            cache.put(event.request, responseToCache);
                        });
                    
                    return response;
                });
            })
            .catch(() => {
                // If both cache and network fail, return offline page
                if (event.request.destination === 'document') {
                    return caches.match('/offline.html');
                }
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// Background sync for offline data
self.addEventListener('sync', event => {
    if (event.tag === 'background-sync') {
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    try {
        // Get offline data from IndexedDB or localStorage
        const offlineData = await getOfflineData();
        
        if (offlineData && offlineData.length > 0) {
            // Sync data to server
            for (const item of offlineData) {
                await syncDataToServer(item);
            }
            
            // Clear offline data after successful sync
            await clearOfflineData();
        }
    } catch (error) {
        console.error('Background sync failed:', error);
    }
}

async function getOfflineData() {
    // This would typically use IndexedDB
    // For now, using localStorage as fallback
    const data = [];
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('wms_offline_')) {
            const value = JSON.parse(localStorage.getItem(key));
            data.push({ key, value });
        }
    }
    return data;
}

async function syncDataToServer(item) {
    try {
        const response = await fetch('/api/sync_offline', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(item)
        });
        
        if (response.ok) {
            console.log('Data synced successfully:', item.key);
        } else {
            throw new Error('Sync failed');
        }
    } catch (error) {
        console.error('Error syncing data:', error);
        throw error;
    }
}

async function clearOfflineData() {
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('wms_offline_')) {
            keys.push(key);
        }
    }
    
    keys.forEach(key => localStorage.removeItem(key));
}

// Push notifications
self.addEventListener('push', event => {
    if (event.data) {
        const data = event.data.json();
        const options = {
            body: data.body,
            icon: '/static/icons/icon-192x192.png',
            badge: '/static/icons/icon-192x192.png',
            vibrate: [100, 50, 100],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: 1
            },
            actions: [
                {
                    action: 'explore',
                    title: 'View Details',
                    icon: '/static/icons/icon-192x192.png'
                },
                {
                    action: 'close',
                    title: 'Close',
                    icon: '/static/icons/icon-192x192.png'
                }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    }
});

// Notification click handler
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'explore') {
        // Open the app
        event.waitUntil(
            clients.openWindow('/')
        );
    } else if (event.action === 'close') {
        // Just close the notification
        event.notification.close();
    } else {
        // Default action - open app
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Handle messages from the main thread
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// Periodic background sync (when supported)
self.addEventListener('periodicsync', event => {
    if (event.tag === 'wms-sync') {
        event.waitUntil(doPeriodicSync());
    }
});

async function doPeriodicSync() {
    try {
        // Sync critical data in the background
        await syncCriticalData();
    } catch (error) {
        console.error('Periodic sync failed:', error);
    }
}

async function syncCriticalData() {
    // Sync inventory levels, pending approvals, etc.
    try {
        const response = await fetch('/api/sync_critical_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (response.ok) {
            console.log('Critical data synced successfully');
        }
    } catch (error) {
        console.error('Error syncing critical data:', error);
    }
}
