/**
 * middleware.ts — Next.js Edge Middleware for route protection.
 *
 * Redirects unauthenticated users to /login for all routes except /login itself.
 * The authentication check is simple: verify that the httpOnly cookie exists.
 * The JWT signature is validated by the backend on every API call — we just need
 * to gate the UI here to avoid rendering authenticated pages before the 401.
 *
 * Note: The cookie is httpOnly, so it's not readable from JS, but the middleware
 * runs on the Edge Runtime and CAN read request cookies.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login"];
const COOKIE_NAME = "access_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths through
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow Next.js internal paths and static files
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".") // static files (favicon, sw.js, etc.)
  ) {
    return NextResponse.next();
  }

  // Check for auth cookie
  const token = request.cookies.get(COOKIE_NAME);
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    // Pass the original destination so we can redirect back after login
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Run on all paths except Next.js internals
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
