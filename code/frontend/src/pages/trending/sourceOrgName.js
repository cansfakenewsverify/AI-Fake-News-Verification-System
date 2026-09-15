import { displayHost, hostMatches, httpUrl } from "../../lib/httpUrl.js";
import { TRENDING_COPY } from "./copy.js";

// Trending card organisation name from source_url (S-09 step 3; spec 8.3 S3).
// mygopen.com -> MyGoPen, tfc-taiwan.org.tw -> the TFC name, cofacts.tw / cofacts.g0v.tw -> Cofacts
// (exact domain or subdomain); any other http(s) host -> that hostname without "www.".
// Google News redirect hosts never render (spec 8.3 S3, FR-06 acceptance 6): isBlockedSourceUrl() is
// true for them and sourceOrgName() returns null, the same as for missing or non-http(s) URLs.

const ORGS = [
  { domains: ["mygopen.com"], key: "org_mygopen" },
  { domains: ["tfc-taiwan.org.tw"], key: "org_tfc" },
  { domains: ["cofacts.tw", "cofacts.g0v.tw"], key: "org_cofacts" },
];

const BLOCKED_DOMAINS = ["news.google.com"];

export function isBlockedSourceUrl(value) {
  const url = httpUrl(value);
  if (!url) return false;
  const host = displayHost(url);
  return BLOCKED_DOMAINS.some((domain) => hostMatches(host, domain));
}

export function sourceOrgName(sourceUrl) {
  const url = httpUrl(sourceUrl);
  if (!url || isBlockedSourceUrl(sourceUrl)) return null;
  const host = displayHost(url);
  const org = ORGS.find((entry) => entry.domains.some((domain) => hostMatches(host, domain)));
  return org ? TRENDING_COPY[org.key] : host || null;
}
