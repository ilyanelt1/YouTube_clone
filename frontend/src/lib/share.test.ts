import { describe, expect, it } from "vitest";

import { buildVideoShareUrl } from "./share";

describe("buildVideoShareUrl", () => {
  it("preserves the frontend port on localhost", () => {
    expect(
      buildVideoShareUrl("http://localhost:8083", "c059ba60-8bad-4ceb-bc99-e93ec2de2e12"),
    ).toBe("http://localhost:8083/?video=c059ba60-8bad-4ceb-bc99-e93ec2de2e12");
  });

  it("uses the current HTTPS origin in production", () => {
    expect(buildVideoShareUrl("https://videos.example.com", "video-id")).toBe(
      "https://videos.example.com/?video=video-id",
    );
  });
});
