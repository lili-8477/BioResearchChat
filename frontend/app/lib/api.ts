"use client";

export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("biochat_token") || "";
}

export function getUser(): { id: number; username: string; display_name: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem("biochat_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return !!getAuthToken();
}

export function logout() {
  localStorage.removeItem("biochat_token");
  localStorage.removeItem("biochat_user");
  localStorage.removeItem("bioChat_sessionId");
  window.location.href = "/login";
}

export function withControlHeaders(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers || {});
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return {
    ...init,
    headers,
    credentials: "include",
  };
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(input, withControlHeaders(init));
  if (res.status === 401) {
    logout();
  }
  return res;
}

export function wsUrl(baseUrl: string): string {
  const token = getAuthToken();
  if (!token) return baseUrl;
  const url = new URL(baseUrl);
  url.searchParams.set("token", token);
  return url.toString();
}
