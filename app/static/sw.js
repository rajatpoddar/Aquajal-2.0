// File: app/static/sw.js
// This is the service worker that handles PWA functionality like offline caching and push notifications.

const CACHE_NAME = 'aquajal-cache-v1';
const urlsToCache = [
  '/',
  '/index',
  '/offline',
  '/static/manifest.json',
  '/static/images/logo-192.png',
  '/static/images/logo-512.png'
];

// Install event: Fires when the service worker is first installed.
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Activate event: Fires when the service worker is activated.
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

// Fetch event: Intercepts network requests to serve cached content when offline.
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Cache hit - return response
        if (response) {
          return response;
        }
        // Not in cache - fetch from network
        return fetch(event.request).catch(() => {
          // If network fails, return the offline page for navigation requests
          if (event.request.mode === 'navigate') {
            return caches.match('/offline');
          }
        });
      })
  );
});


// --- PUSH EVENT LISTENER (THE CRITICAL FIX) ---
// This is the code that was missing. It listens for a push event from the server.
self.addEventListener('push', event => {
  // Check if there is data in the push event
  if (event.data) {
    const data = event.data.json();
    const title = data.title || "Aquajal Notification";
    const options = {
      body: data.body || "You have a new update.",
      icon: '/static/images/logo-192.png', // Icon for the notification
      badge: '/static/images/logo-192.png' // A smaller icon for the status bar
    };

    // Use waitUntil to ensure the service worker doesn't terminate before the notification is shown.
    event.waitUntil(
      self.registration.showNotification(title, options)
    );
  } else {
    console.log('Push event but no data');
  }
});
