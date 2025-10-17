// File: app/static/sw.js

const CACHE_NAME = 'aquajal-cache-v2'; // Increment cache version to force update
const urlsToCache = [
  '/',
  '/index',
  '/offline', // An offline fallback page
  '/static/manifest.json',
  '/static/images/logo-192.png',
  '/static/images/logo-512.png'
];

// Install event: Caches core assets when the service worker is installed.
self.addEventListener('install', event => {
  self.skipWaiting(); // Force the new service worker to activate immediately
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache and caching core assets.');
        return cache.addAll(urlsToCache);
      })
  );
});

// Activate event: Cleans up old caches.
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Fetch event: Serves cached content when offline.
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached response if found, otherwise fetch from network.
        return response || fetch(event.request).catch(() => {
          // If network fails for a page navigation, show the offline page.
          if (event.request.mode === 'navigate') {
            return caches.match('/offline');
          }
        });
      })
  );
});

// --- PUSH EVENT LISTENER (THE FIX) ---
// This code listens for a push notification arriving from your server.
self.addEventListener('push', event => {
  console.log('[Service Worker] Push Received.');
  
  if (!event.data) {
    console.error('[Service Worker] Push event but no data');
    return;
  }
  
  const data = event.data.json();
  const title = data.title || "Aquajal Notification";
  const options = {
    body: data.body,
    icon: '/static/images/logo-192.png', // Main icon
    badge: '/static/images/logo-192.png' // Small icon for status bar
  };

  // Tell the browser to show the notification.
  event.waitUntil(self.registration.showNotification(title, options));
});
