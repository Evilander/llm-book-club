import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

function apiOrigin(): string {
  try {
    return new URL(
      process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
    ).origin;
  } catch {
    return "http://localhost:8000";
  }
}

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const isDevelopment = process.env.NODE_ENV === "development";
  const backend = apiOrigin();
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' blob: https://fonts.googleapis.com",
    `img-src 'self' blob: data: ${backend}`,
    "font-src 'self' blob: data: https://fonts.gstatic.com",
    `connect-src 'self' blob: ${backend}`,
    `frame-src 'self' blob: ${backend}`,
    `media-src 'self' blob: ${backend}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Permissions-Policy", "camera=(), geolocation=(), payment=()");
  return response;
}

export const config = {
  matcher: "/read/:path*",
};
