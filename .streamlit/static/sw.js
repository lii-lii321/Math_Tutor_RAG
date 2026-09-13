/* MathMaster PWA 最小 Service Worker：仅支持安装，不做离线缓存 */
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
