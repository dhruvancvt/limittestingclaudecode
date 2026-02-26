// Minimal service worker – offline shell only (no API caching)
const CACHE_NAME = 'cc-remote-v1'
const PRECACHE = ['/', '/index.html']

self.addEventListener('install', (evt) => {
  self.skipWaiting()
  evt.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE))
  )
})

self.addEventListener('activate', (evt) => {
  evt.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (evt) => {
  const url = new URL(evt.request.url)
  // Never intercept API / WebSocket
  if (url.pathname.startsWith('/auth') ||
      url.pathname.startsWith('/sessions') ||
      url.pathname.startsWith('/ws') ||
      url.pathname.startsWith('/health')) {
    return
  }

  evt.respondWith(
    caches.match(evt.request).then((cached) =>
      cached || fetch(evt.request).catch(() => caches.match('/index.html'))
    )
  )
})
