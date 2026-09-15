import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { THREADS_INTENT_URL, buildThreadsIntent } from "./buildThreadsIntent.js";

// S-08 Threads Web Intent (FR-05 acceptance 1, 2, 5). Kept free of Han characters like the rest of the folder.

test("intent URL targets threads.com/intent/post with text and url only", () => {
  const href = buildThreadsIntent({ text: "hello", url: "https://example.com/r/1" });
  const u = new URL(href);
  assert.equal(u.origin + u.pathname, THREADS_INTENT_URL);
  assert.equal(THREADS_INTENT_URL, "https://www.threads.com/intent/post");
  assert.deepEqual([...u.searchParams.keys()], ["text", "url"]);
  assert.equal(u.searchParams.has("tag"), false);
  assert.equal(u.searchParams.has("reply_control"), false);
});

test("special characters round-trip verbatim", () => {
  const share = {
    text: "\u{1F534} A&B #tag 100% + x=y? a b\nline https://x.example/?a=1&b=2#frag",
    url: "https://fcc.example/r/abc?x=1&y=2#top",
  };
  const href = buildThreadsIntent(share);
  const u = new URL(href);
  assert.equal(u.searchParams.get("text"), share.text);
  assert.equal(u.searchParams.get("url"), share.url);
  // the raw query keeps exactly one separator between the two parameters
  assert.equal(href.split("&").length, 2);
  assert.equal(href.includes("#"), false);
});

test("missing or incomplete share -> null (no button)", () => {
  assert.equal(buildThreadsIntent(null), null);
  assert.equal(buildThreadsIntent(undefined), null);
  assert.equal(buildThreadsIntent({ text: "x" }), null);
  assert.equal(buildThreadsIntent({ url: "https://example.com" }), null);
  assert.equal(buildThreadsIntent({ text: "", url: "https://example.com" }), null);
  assert.equal(buildThreadsIntent({ text: "\uD800", url: "https://example.com" }), null);
});

test("fixture fx-share-special-chars keeps & and # through the intent URL", async () => {
  const fixture = JSON.parse(
    await readFile(new URL("../../dev/fixtures/result_fx-share-special-chars.json", import.meta.url), "utf8"),
  );
  assert.ok(fixture.share.text.includes("&") && fixture.share.text.includes("#"));
  const u = new URL(buildThreadsIntent(fixture.share));
  assert.equal(u.searchParams.get("text"), fixture.share.text);
  assert.equal(u.searchParams.get("url"), fixture.share.url);
});
