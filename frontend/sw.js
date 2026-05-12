/* PO Diary — cache da interface e fallback offline básico */
const CACHE = "po-diary-shell-v10";
const PRECACHE = [
  "/",
  "/index.html",
  "/login.html",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/imagens/logo_daily.png",
  "/imagens/logo_empresarial_daily.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) =>
        Promise.all(
          PRECACHE.map((url) =>
            cache.add(new Request(url, { cache: "reload" })).catch(() => {})
          )
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(
          JSON.stringify({
            erro: "Sem conexão",
            offline: true,
          }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }
        )
      )
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          try {
            if (res.ok) {
              const a = res.clone();
              const b = res.clone();
              caches.open(CACHE).then((c) => {
                c.put("/index.html", a);
                c.put("/", b);
              });
            }
          } catch (_) {}
          return res;
        })
        .catch(() =>
          caches.match("/index.html").then((r) => r || caches.match("/"))
        )
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const net = fetch(request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || net;
    })
  );
});
