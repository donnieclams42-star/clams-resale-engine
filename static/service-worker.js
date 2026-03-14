const CACHE_NAME = "clams-cache-v3";

self.addEventListener("install", event => {
  self.skipWaiting();   // force new worker immediately
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim(); // take control of open pages
});

self.addEventListener("fetch", event => {

  // Never cache HTML
  if (event.request.headers.get("accept")?.includes("text/html")) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});