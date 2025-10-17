// File: app/static/notifications.js

// This variable will hold the VAPID public key passed from the template.
let vapidPublicKey = null;

/**
 * Converts a VAPID public key string into a Uint8Array.
 * This is a necessary step for the browser's push subscription API.
 */
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

/**
 * Sends the push subscription object to the backend server to be saved.
 * @param {PushSubscription} subscription The subscription object from the browser.
 */
function sendSubscriptionToBackEnd(subscription) {
    return fetch('/notifications/subscribe', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(subscription)
    }).then(response => {
        if (!response.ok) {
            throw new Error('Failed to send subscription to backend. Server responded with an error.');
        }
        console.log('Successfully sent subscription to backend.');
        return response.json();
    }).catch(error => {
        console.error('Error sending subscription to backend:', error);
    });
}

/**
 * Subscribes the user to push notifications.
 * It first checks if a subscription already exists. If not, it creates a new one.
 */
function subscribeUser() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.warn('Push messaging is not supported by this browser.');
        alert('Sorry, push notifications are not supported by your browser.');
        return;
    }

    navigator.serviceWorker.ready.then(function(registration) {
        registration.pushManager.getSubscription().then(function(existedSubscription) {
            if (existedSubscription === null) {
                // No subscription exists, so create a new one.
                console.log('No subscription detected, creating a new one.');
                const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);
                registration.pushManager.subscribe({
                    applicationServerKey: applicationServerKey,
                    userVisibleOnly: true, // This is required for web push.
                }).then(function(newSubscription) {
                    console.log('New push subscription created.');
                    sendSubscriptionToBackEnd(newSubscription);
                    alert('You have been successfully subscribed to notifications!');
                }).catch(function(e) {
                    console.error('Failed to subscribe the user: ', e);
                    alert('Failed to subscribe to notifications. You may have blocked them for this site.');
                });
            } else {
                // A subscription already exists.
                console.log('Existing subscription detected.');
                sendSubscriptionToBackEnd(existedSubscription);
                // We don't need to alert the user if they are already subscribed.
            }
        });
    }).catch(function(e) {
        console.error('Service Worker is not ready yet.', e);
    });
}

/**
 * The main function to start the push notification process.
 * It checks for permissions and then triggers the subscription.
 * @param {string} publicKey The VAPID public key from the server.
 */
function initializePushNotifications(publicKey) {
    if (!publicKey) {
        console.error('VAPID public key is missing.');
        return;
    }
    vapidPublicKey = publicKey;

    // If permission is already granted, subscribe automatically on page load.
    if ("Notification" in window && Notification.permission === "granted") {
        console.log("Permission already granted. Subscribing user.");
        subscribeUser();
    }
}

/**
 * This function is triggered by the "Enable Notifications" button click.
 */
function requestNotificationPermission() {
    if (!("Notification" in window)) {
        alert("Sorry, your browser does not support notifications.");
        return;
    }

    if (Notification.permission === 'denied') {
        alert("You have blocked notifications. To enable them, you must change the settings for this site in your browser.");
        return;
    }
    
    // If not denied, request permission. This will trigger the subscription if granted.
    Notification.requestPermission().then(function(permission) {
        if (permission === "granted") {
            console.log("Permission was granted on click.");
            subscribeUser();
        } else {
            console.log("Permission was denied on click.");
            alert("You have denied notification permissions. To enable them, please go to your browser settings.");
        }
    });
}

