import { test } from "node:test";
import assert from "node:assert/strict";
import { displayHost, hostMatches, httpUrl } from "./httpUrl.js";

test("httpUrl accepts only http(s) strings", () => {
  assert.equal(httpUrl("https://www.mygopen.com/a")?.hostname, "www.mygopen.com");
  assert.equal(httpUrl("  http://tfc-taiwan.org.tw/x  ")?.protocol, "http:");
  for (const bad of ["javascript:alert(1)", "mailto:a@b.c", "/r/abc", "mygopen.com", "", "   ", null, undefined, 42, {}]) {
    assert.equal(httpUrl(bad), null, String(bad));
  }
});

test("displayHost lower-cases and drops www. and a trailing dot", () => {
  assert.equal(displayHost(httpUrl("https://WWW.MyGoPen.com./2026/x.html")), "mygopen.com");
  assert.equal(displayHost(httpUrl("https://news.cts.com.tw/a")), "news.cts.com.tw");
  assert.equal(displayHost(null), "");
});

test("hostMatches is an exact or dot-boundary suffix match", () => {
  assert.equal(hostMatches("mygopen.com", "mygopen.com"), true);
  assert.equal(hostMatches("m.mygopen.com", "mygopen.com"), true);
  assert.equal(hostMatches("evilmygopen.com", "mygopen.com"), false);
  assert.equal(hostMatches("gov.tw.evil.com", "gov.tw"), false);
  assert.equal(hostMatches("", "gov.tw"), false);
  assert.equal(hostMatches("gov.tw", ""), false);
});
