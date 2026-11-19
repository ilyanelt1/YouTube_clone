import {
  createRefreshCoordinator,
  type RefreshLockManager,
} from "./refreshCoordinator";

const API = "/api/v1";
const AUTH_ENDPOINTS_WITHOUT_RETRY = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/logout",
]);

export type AuthResponse<TUser = unknown> = {
  access_token: string;
  expires_in?: number;
  user: TUser;
};

type ErrorPayload = {
  detail?: unknown;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let accessToken: string | null = null;
const accessTokenListeners = new Set<() => void>();

const authChannel =
  typeof window !== "undefined" && typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel("youtube-clone-auth")
    : null;

authChannel?.addEventListener("message", (event: MessageEvent<unknown>) => {
  if (
    typeof event.data === "object" &&
    event.data !== null &&
    "type" in event.data &&
    event.data.type === "logout"
  ) {
    setAccessToken(null);
  }
});

export function getAccessToken(): string | null {
  return accessToken;
}

export function subscribeAccessToken(listener: () => void): () => void {
  accessTokenListeners.add(listener);
  return () => accessTokenListeners.delete(listener);
}

export function setAccessToken(value: string | null): void {
  if (accessToken === value) {
    return;
  }

  accessToken = value;
  accessTokenListeners.forEach((listener) => listener());
}

export function clearAccessToken(broadcast = false): void {
  setAccessToken(null);
  if (broadcast) {
    authChannel?.postMessage({ type: "logout" });
  }
}

function getBrowserLockManager(): RefreshLockManager | null {
  if (typeof navigator === "undefined") {
    return null;
  }

  return (
    navigator as Navigator & { locks?: RefreshLockManager }
  ).locks ?? null;
}

async function responseError(response: Response): Promise<ApiError> {
  const payload = (await response.json().catch(() => null)) as ErrorPayload | null;
  const detail = payload?.detail;
  const message =
    typeof detail === "string"
      ? detail
      : `Request failed: ${response.status}`;
  return new ApiError(message, response.status);
}

async function performRefresh(): Promise<AuthResponse> {
  const response = await fetch(`${API}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw await responseError(response);
  }

  const result = (await response.json()) as AuthResponse;
  if (!result.access_token) {
    throw new Error("Сервер не вернул access-токен.");
  }

  setAccessToken(result.access_token);
  return result;
}

const coordinateRefresh = createRefreshCoordinator(
  performRefresh,
  getBrowserLockManager,
);

/**
 * Restores a session on app startup. The shared promise prevents React
 * StrictMode's development effect replay from rotating the cookie twice.
 */
export async function refreshSession(): Promise<AuthResponse> {
  try {
    return await coordinateRefresh();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      clearAccessToken(true);
    }
    throw error;
  }
}

async function refreshAccessToken(rejectedToken: string): Promise<string> {
  // Another request in this tab may already have refreshed the rejected token.
  if (accessToken && accessToken !== rejectedToken) {
    return accessToken;
  }

  const result = await refreshSession();
  return result.access_token;
}

async function sendRequest(
  path: string,
  options: RequestInit,
  token: string | null,
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else {
    headers.delete("Authorization");
  }

  return fetch(`${API}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
}

function isAuthEndpoint(path: string): boolean {
  return AUTH_ENDPOINTS_WITHOUT_RETRY.has(path.split("?")[0]);
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const requestToken = accessToken ?? token ?? null;
  let response = await sendRequest(path, options, requestToken);

  if (response.status === 401 && requestToken && !isAuthEndpoint(path)) {
    let freshToken: string;
    try {
      freshToken = await refreshAccessToken(requestToken);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAccessToken(true);
        throw new ApiError("Сессия истекла. Войдите снова.", 401);
      }
      throw error;
    }

    response = await sendRequest(path, options, freshToken);
    if (response.status === 401) {
      clearAccessToken(true);
      throw new ApiError("Сессия истекла. Войдите снова.", 401);
    }
  }

  if (!response.ok) {
    throw await responseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

type UploadResult = {
  status: number;
  payload: Record<string, unknown>;
};

function uploadOnce(
  form: FormData,
  token: string,
  onProgress: (value: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${API}/videos/upload`);
    request.withCredentials = true;
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    request.onload = () => {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(request.responseText || "{}") as Record<string, unknown>;
      } catch {
        payload = {};
      }
      resolve({ status: request.status, payload });
    };
    request.onerror = () => reject(new Error("Network error while uploading video"));
    request.onabort = () => reject(new Error("Upload cancelled"));
    request.send(form);
  });
}

export async function uploadWithProgress<T>(
  form: FormData,
  token: string,
  onProgress: (value: number) => void,
): Promise<T> {
  let requestToken = accessToken ?? token;
  let result = await uploadOnce(form, requestToken, onProgress);

  if (result.status === 401) {
    try {
      requestToken = await refreshAccessToken(requestToken);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAccessToken(true);
        throw new ApiError("Сессия истекла. Войдите снова.", 401);
      }
      throw error;
    }

    onProgress(0);
    result = await uploadOnce(form, requestToken, onProgress);
    if (result.status === 401) {
      clearAccessToken(true);
      throw new ApiError("Сессия истекла. Войдите снова.", 401);
    }
  }

  if (result.status < 200 || result.status >= 300) {
    const detail = result.payload.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Upload failed: ${result.status}`,
    );
  }

  return result.payload as T;
}
