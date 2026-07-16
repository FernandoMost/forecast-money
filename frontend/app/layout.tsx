import type { Metadata, Viewport } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import ServiceWorkerRegistrar from "@/components/ServiceWorkerRegistrar";
import Providers from "@/components/Providers";
import { themeScript } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Forecast Money",
  description: "Privacy-first personal finance analyzer",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Forecast Money",
  },
};

export const viewport: Viewport = {
  themeColor: "#4f46e5",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // lang is updated dynamically by I18nProvider via document.documentElement.lang
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* Anti-flash-of-wrong-theme: runs before first paint, reads localStorage */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link rel="manifest" href="/manifest.json" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="Forecast Money" />
      </head>
      <body className="bg-gray-50 dark:bg-gray-950 min-h-screen font-sans transition-colors duration-200">
        <Providers>
          <Nav />
          <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
          <ServiceWorkerRegistrar />
        </Providers>
      </body>
    </html>
  );
}
