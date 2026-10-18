// Keeps the page usable offline: the app shell is cached, and news and weather
// are fetched fresh when online, falling back to the last copy when not.
const CACHE = 'morning-brief-v2';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'zh/', 'zh/index.html', 'zh/manifest.webmanifest',
               'icons/icon-192.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: false });
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  const sameOrigin = url.origin === self.location.origin;
  // News, the page itself, and live weather: always try the network first.
  if (sameOrigin || url.hostname === 'api.open-meteo.com') {
    e.respondWith(networkFirst(e.request));
  }
});
