// http(s) URL helpers shared by the list pages (S-09 trending cards, S-10 knowledge cards).
// - httpUrl(value): URL object only for http: / https: strings; anything else (javascript:, mailto:,
//   relative paths, garbage) returns null, so it can never become a link.
// - displayHost(url): lower-case hostname without a leading "www." or a trailing dot.
// - hostMatches(host, domain): exact domain or a subdomain of it (suffix on a dot boundary, never a
//   substring match, so "gov.tw.evil.com" does not match "gov.tw").

export function httpUrl(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

export function displayHost(url) {
  const host = String(url?.hostname || "")
    .toLowerCase()
    .replace(/\.$/, "");
  return host.replace(/^www\./, "");
}

export function hostMatches(host, domain) {
  const h = String(host || "").toLowerCase();
  const d = String(domain || "").toLowerCase();
  if (!h || !d) return false;
  return h === d || h.endsWith(`.${d}`);
}
