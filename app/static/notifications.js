// app/static/notifications.js

// This key will be passed from the template
let VAPID_PUBLIC_KEY = ''; 

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

function sendSubscriptionToBackEnd(subscription) {
    return fetch('/notifications/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription)
    }).then(response => {
        if (!response.ok) {
            throw new Error('Failed to send subscription to backend.');
        }
        return response.json();
    });
}

function subscribeUser() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.ready.then(function(registration) {
            if (!registration.pushManager) {
                console.log('Push manager unavailable.');
                return;
            }

            registration.pushManager.getSubscription().then(function(existedSubscription) {
                if (existedSubscription === null) {
                    console.log('No subscription detected, make a new one.');
                    registration.pushManager.subscribe({
                        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
                        userVisibleOnly: true,
                    }).then(function(newSubscription) {
                        console.log('New subscription added.');
                        sendSubscriptionToBackEnd(newSubscription);
                    }).catch(function(e) {
                        if (Notification.permission !== 'granted') {
                            console.log('Permission was not granted.');
                        } else {
                            console.error('An error ocurred during the subscription process.', e);
                        }
                    });
                } else {
                    console.log('Existed subscription detected.');
                    sendSubscriptionToBackEnd(existedSubscription);
                }
            });
        }).catch(function(e) {
            console.error('An error ocurred during Service Worker registration.', e);
        });
    }
}

function initializePushNotifications(publicKey) {
    VAPID_PUBLIC_KEY = publicKey;
    if (!("Notification" in window)) {
        console.log("This browser does not support desktop notification");
    } else if (Notification.permission === "granted") {
        console.log("Permission to receive notifications has been granted");
        subscribeUser();
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(function (permission) {
            if (permission === "granted") {
                subscribeUser();
            }
        });
    }
}
