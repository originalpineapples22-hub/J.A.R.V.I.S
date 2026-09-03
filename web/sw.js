self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {title: 'J.A.R.V.I.S.', body: 'Sir?', url: '/'};
  try { d = Object.assign(d, e.data.json()); } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.title, {body: d.body, icon: '/static/icons/icon-192.png', badge: '/static/icons/icon-192.png', data: {url: d.url}}));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(cs => {
    for (const c of cs) { if ('focus' in c) return c.focus(); }
    return clients.openWindow(e.notification.data?.url || '/');
  }));
});
