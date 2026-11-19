export function buildVideoShareUrl(origin: string, videoId: string): string {
  const url = new URL("/", origin);
  url.searchParams.set("video", videoId);
  return url.toString();
}
