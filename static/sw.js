/* IAS Machine — Full Offline Service Worker */
const VERSION = 'ias-v7';
const STATIC_CACHE = 'ias-static-' + VERSION;
const PAGES_CACHE  = 'ias-pages-'  + VERSION;
const BOOKS_CACHE  = 'ias-books-v4';   // keep version stable for books
const API_CACHE    = 'ias-api-'    + VERSION;

const PRECACHE = [
  '/', '/toolkit', '/library', '/bookzone', '/epaper/lazy', '/news',
  '/static/style.css',
  '/static/manifest.json',
  '/static/offline.js',
  '/static/offline-fallback.html',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/pdfjs/pdf.min.js',
  '/static/pdfjs/pdf.worker.min.js',
];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(PAGES_CACHE).then(c =>
      Promise.all(PRECACHE.map(u =>
        fetch(u, {credentials:'same-origin'})
          .then(r => r.ok && c.put(u, r.clone()))
          .catch(() => null)
      ))
    )
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => {
        // Delete only OLD versioned caches (keep books cache version stable)
        if (k.startsWith('ias-') && !k.includes(VERSION) && k !== BOOKS_CACHE) {
          return caches.delete(k);
        }
      }))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const same = url.origin === location.origin;

  // Skip external (jina, google news, BBC, etc.)
  if (!same) return;

  const path = url.pathname;

  // 1) Saved books — cache-first forever
  if (path.startsWith('/read/') || path.startsWith('/book/') || path.startsWith('/download/')) {
    e.respondWith(
      caches.open(BOOKS_CACHE).then(c =>
        c.match(req).then(hit => hit || fetch(req).then(res => {
          // don't cache errors
          if (res.ok) c.put(req, res.clone());
          return res;
        }).catch(() => c.match('/static/offline-fallback.html')))
      )
    );
    return;
  }

  // 2) Static assets — cache-first
  if (path.startsWith('/static/')) {
    e.respondWith(
      caches.open(STATIC_CACHE).then(c =>
        c.match(req).then(hit => hit || fetch(req).then(res => {
          if (res.ok) c.put(req, res.clone());
          return res;
        }).catch(() => caches.match('/static/offline-fallback.html')))
      )
    );
    return;
  }

  // 3) HTML pages — network-first, cache fallback
  if (req.headers.get('accept')?.includes('text/html') || path === '/') {
    e.respondWith(
      fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(PAGES_CACHE).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() =>
        caches.open(PAGES_CACHE).then(c =>
          c.match(req).then(hit =>
            hit || c.match('/static/offline-fallback.html')
          )
        )
      )
    );
    return;
  }

  // 4) API JSON — network-first, then cache
  if (path.startsWith('/api') || path.endsWith('.json') ||
      req.headers.get('accept')?.includes('application/json')) {
    e.respondWith(
      fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(API_CACHE).then(c => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.open(API_CACHE).then(c => c.match(req)))
    );
    return;
  }

  // 5) Everything else — try network, fall back to cache
  e.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});

// Handle messages from the page
self.addEventListener('message', e => {
  if (e.data === 'skipWaiting') self.skipWaiting();
  if (e.data === 'getCacheSize') {
    navigator.storage && navigator.storage.estimate().then(est => {
      e.source.postMessage({
        type: 'cacheSize',
        usage: est.usage,
        quota: est.quota
      });
    });
  }
});
