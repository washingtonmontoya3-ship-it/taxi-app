self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());

self.addEventListener('push', event => {
  let titulo = 'Taxi App';
  let cuerpo = 'Tienes una nueva notificacion';
  try {
    const data = event.data ? event.data.json() : {};
    titulo = data.title || titulo;
    cuerpo = data.body || cuerpo;
  } catch (e) {}

  event.waitUntil(
    self.registration.showNotification(titulo, {
      body: cuerpo,
      icon: '/icon-chofer.svg',
      badge: '/icon-chofer.svg',
      vibrate: [300, 100, 300],
      tag: 'solicitud-taxi',
      renotify: true,
      requireInteraction: true,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(lista => {
      for (const c of lista) {
        if (c.url.includes('chofer.html') && 'focus' in c) return c.focus();
      }
      return clients.openWindow('/chofer.html');
    })
  );
});
