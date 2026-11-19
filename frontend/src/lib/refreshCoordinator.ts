export interface RefreshLockManager {
  request<T>(
    name: string,
    options: { mode: "exclusive" },
    callback: () => Promise<T>,
  ): Promise<T>;
}

const REFRESH_LOCK_NAME = "youtube-clone-auth-refresh";

/**
 * Coalesces refreshes in the current tab and serializes refreshes across tabs
 * through the browser's origin-wide Web Locks API.
 */
export function createRefreshCoordinator<T>(
  refresh: () => Promise<T>,
  getLockManager: () => RefreshLockManager | null,
): () => Promise<T> {
  let inFlight: Promise<T> | null = null;

  return () => {
    if (inFlight) {
      return inFlight;
    }

    const lockManager = getLockManager();
    if (!lockManager) {
      return Promise.reject(
        new Error(
          "Безопасное обновление сессии требует современного браузера с поддержкой Web Locks API.",
        ),
      );
    }

    const pending = lockManager.request(
      REFRESH_LOCK_NAME,
      { mode: "exclusive" },
      refresh,
    );

    const shared = pending.finally(() => {
      if (inFlight === shared) {
        inFlight = null;
      }
    });

    inFlight = shared;
    return shared;
  };
}
