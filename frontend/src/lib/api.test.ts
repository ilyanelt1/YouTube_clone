import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  getAccessToken,
  setAccessToken,
} from "./api";
import type { RefreshLockManager } from "./refreshCoordinator";

function createLockManager(): RefreshLockManager {
  return {
    request<T>(
      _name: string,
      _options: { mode: "exclusive" },
      callback: () => Promise<T>,
    ): Promise<T> {
      return callback();
    },
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("navigator", { locks: createLockManager() });
  vi.unstubAllGlobals();
  vi.stubGlobal("navigator", { locks: createLockManager() });
});

describe("api authentication retry", () => {
  it("refreshes an expired access token and retries the original request once", async () => {
    setAccessToken("expired-token");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return jsonResponse({ access_token: "fresh-token", user: {} });
      }

      const authorization = new Headers(init?.headers).get("Authorization");
      if (authorization === "Bearer expired-token") {
        return jsonResponse({ detail: "Invalid credentials" }, 401);
      }
      return jsonResponse({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await api<{ ok: boolean }>("/videos/mine", {}, "expired-token");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({
      headers: expect.any(Headers),
    });
    expect(
      new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get("Authorization"),
    ).toBe("Bearer fresh-token");
    expect(getAccessToken()).toBe("fresh-token");
  });

  it("shares one refresh when several requests receive 401 together", async () => {
    setAccessToken("expired-token");
    let refreshCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        refreshCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 0));
        return jsonResponse({ access_token: "fresh-token", user: {} });
      }

      const authorization = new Headers(init?.headers).get("Authorization");
      if (authorization === "Bearer expired-token") {
        return jsonResponse({ detail: "Invalid credentials" }, 401);
      }
      return jsonResponse({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    const [first, second] = await Promise.all([
      api<{ ok: boolean }>("/videos/mine", {}, "expired-token"),
      api<{ ok: boolean }>("/notifications", {}, "expired-token"),
    ]);

    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: true });
    expect(refreshCount).toBe(1);
    expect(getAccessToken()).toBe("fresh-token");
  });

  it("ends the local session after the retried request is still unauthorized", async () => {
    setAccessToken("expired-token");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/auth/refresh")) {
        return jsonResponse({ access_token: "fresh-token", user: {} });
      }
      return jsonResponse({ detail: "Invalid credentials" }, 401);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api("/videos/mine", {}, "expired-token"),
    ).rejects.toThrow("Сессия истекла. Войдите снова.");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBeNull();
  });

  it("does not attempt refresh for login and registration failures", async () => {
    setAccessToken(null);
    const fetchMock = vi.fn(async () =>
      jsonResponse({ detail: "Invalid credentials" }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api("/auth/login", { method: "POST" }),
    ).rejects.toThrow("Invalid credentials");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
