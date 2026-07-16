/**
 * sw.js — Minimal Service Worker for Forecast Money PWA.
 *
 * Main responsibilities:
 *   1. Register the app as a Web Share Target (defined in manifest.json).
 *   2. When a file is shared to the app, store it in Cache API and redirect
 *      the user to /upload?shared=1. The upload page reads the file from Cache.
 *
 * We deliberately avoid any aggressive caching strategy here — the app makes
 * API calls to a backend that must always be fresh. The SW only handles
 * the share target flow.
 */

const SHARE_CACHE = "share-target";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// ---------------------------------------------------------------------------
// Web Share Target — intercept the POST from the OS share sheet
// ---------------------------------------------------------------------------

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Only intercept POST to /upload (triggered by the share_target in manifest)
  if (event.request.method !== "POST" || url.pathname !== "/upload") {
    return; // let all other requests pass through normally
  }

  event.respondWith(handleShareTarget(event.request));
});

async function handleShareTarget(request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (file && file instanceof File) {
      // Store the file in Cache so the upload page can retrieve it
      const cache = await caches.open(SHARE_CACHE);
      const headers = new Headers({
        "Content-Type": file.type || "application/octet-stream",
        "X-Filename": file.name,
      });
      const response = new Response(file, { headers });
      await cache.put("/shared-file", response);
    }
  } catch (err) {
    console.error("[SW] share target error:", err);
  }

  // Redirect to the upload page with a flag so it knows to read from Cache
  return Response.redirect("/upload?shared=1", 303);
}
