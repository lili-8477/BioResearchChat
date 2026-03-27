"use client";

const STATIC_CONTROL_TOKEN = process.env.NEXT_PUBLIC_CONTROL_API_TOKEN || "";

export function getControlToken(): string {
  if (STATIC_CONTROL_TOKEN) {
    return STATIC_CONTROL_TOKEN;
  }
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem("bioChat_controlToken") || "";
}

export function withControlHeaders(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers || {});
  const token = getControlToken();
  if (token) {
    headers.set("x-control-token", token);
  }

  return {
    ...init,
    headers,
    credentials: "include",
  };
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return fetch(input, withControlHeaders(init));
}

export function withControlWebSocket(url: string): string {
  const token = getControlToken();
  if (!token) {
    return url;
  }

  const nextUrl = new URL(url);
  nextUrl.searchParams.set("control_token", token);
  return nextUrl.toString();
}
