import { describe, expect, it } from "vitest";
import { buildVideoShareUrl } from "./shareUrl";

describe("buildVideoShareUrl", () => {
  it("preserves the frontend port in shared links", () => {
    expect(
      buildVideoShareUrl(
        "http://localhost:8083",
        "c059ba60-8bad-4ceb-bc99-e93ec2de2e12",
      ),
    ).toBe(
      "http://localhost:8083/?video=c059ba60-8bad-4ceb-bc99-e93ec2de2e12",
    );
  });

  it("encodes the video identifier as a query parameter", () => {
    expect(buildVideoShareUrl("https://youtube.example", "video id")).toBe(
      "https://youtube.example/?video=video+id",
    );
  });
});
