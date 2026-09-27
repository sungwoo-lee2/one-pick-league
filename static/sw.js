
const CACHE = "one-pick-v6";
const CORE = [
  "/",
  "/static/app.css",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;

  if (req.url.includes("/api/")) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(JSON.stringify({error:"오프라인 상태입니다."}), {
          status: 503,
          headers: {"Content-Type":"application/json"}
        })
      )
    );
    return;
  }

  event.respondWith(
    fetch(req)
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(cache => cache.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req).then(r => r || caches.match("/")))
  );
});
