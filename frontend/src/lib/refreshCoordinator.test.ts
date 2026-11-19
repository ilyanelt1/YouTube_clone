import { describe, expect, it, vi } from "vitest";
import {
  createRefreshCoordinator,
  type RefreshLockManager,
} from "./refreshCoordinator";

function createSharedLockManager(): RefreshLockManager {
  let previousRelease: Promise<void> = Promise.resolve();

  return {
    request<T>(
      _name: string,
      _options: { mode: "exclusive" },
      callback: () => Promise<T>,
    ): Promise<T> {
      const previous = previousRelease;
      let release: () => void = () => undefined;
      previousRelease = new Promise<void>((resolve) => {
        release = resolve;
      });

      return previous.then(callback).finally(release);
    },
  };
}

describe("createRefreshCoordinator", () => {
  it("shares one refresh promise inside a tab", async () => {
    let finishRefresh: (value: string) => void = () => undefined;
    const refresh = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          finishRefresh = resolve;
        }),
    );
    const coordinator = createRefreshCoordinator(
      refresh,
      () => createSharedLockManager(),
    );

    const first = coordinator();
    const second = coordinator();

    expect(refresh).toHaveBeenCalledTimes(1);
    finishRefresh("fresh-access-token");

    await expect(Promise.all([first, second])).resolves.toEqual([
      "fresh-access-token",
      "fresh-access-token",
    ]);
  });

  it("serializes refreshes from separate tabs with the same origin lock", async () => {
    const sharedLockManager = createSharedLockManager();
    let activeRefreshes = 0;
    let maxActiveRefreshes = 0;
    let refreshCount = 0;

    const makeTabCoordinator = () =>
      createRefreshCoordinator(
        async () => {
          activeRefreshes += 1;
          maxActiveRefreshes = Math.max(maxActiveRefreshes, activeRefreshes);
          refreshCount += 1;
          await new Promise((resolve) => setTimeout(resolve, 10));
          activeRefreshes -= 1;
          return `token-${refreshCount}`;
        },
        () => sharedLockManager,
      );

    const tabOne = makeTabCoordinator();
    const tabTwo = makeTabCoordinator();

    await Promise.all([tabOne(), tabTwo()]);

    expect(refreshCount).toBe(2);
    expect(maxActiveRefreshes).toBe(1);
  });

  it("fails closed when the browser has no cross-tab lock support", async () => {
    const coordinator = createRefreshCoordinator(
      vi.fn(async () => "token"),
      () => null,
    );

    await expect(coordinator()).rejects.toThrow("Web Locks API");
  });
});
