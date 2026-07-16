"use client";

import { useEffect } from "react";

/**
 * ServiceWorkerRegistrar — registers sw.js on mount.
 * Must be a Client Component since it uses useEffect.
 * Rendered once in the root layout.
 */
export default function ServiceWorkerRegistrar() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then((reg) => {
          console.debug("[SW] registered, scope:", reg.scope);
        })
        .catch((err) => {
          console.warn("[SW] registration failed:", err);
        });
    }
  }, []);

  return null;
}
