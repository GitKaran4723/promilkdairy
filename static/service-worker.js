const CACHE="milk-diary-v1";
const ASSETS=[
  "/",
  "/static/css/app.css",
  "/static/js/pwa.js",
  "/static/manifest.webmanifest"
];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});
self.addEventListener("fetch", e => {
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
