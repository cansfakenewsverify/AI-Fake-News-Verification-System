import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_CHARS, countChars, isHttpUrl, validateInput } from "./validateInput.js";
import { STRINGS } from "../i18n.js";

test("empty and whitespace-only input -> err_empty", () => {
  assert.equal(validateInput("text", ""), "err_empty");
  assert.equal(validateInput("text", "   \n\t "), "err_empty");
  assert.equal(validateInput("url", ""), "err_empty");
  assert.equal(validateInput("text", undefined), "err_empty");
});

test("20000 chars ok, 20001 chars -> err_too_long", () => {
  assert.equal(MAX_CHARS, 20000);
  assert.equal(validateInput("text", "字".repeat(20000)), null);
  assert.equal(validateInput("text", "字".repeat(20001)), "err_too_long");
});

test("length counts code points like the backend (emoji = 1)", () => {
  assert.equal(countChars("a😀字"), 3);
  assert.equal(validateInput("text", "😀".repeat(20000)), null);
  assert.equal(validateInput("text", "😀".repeat(20001)), "err_too_long");
});

test("url mode: ftp://x -> err_invalid_url", () => {
  assert.equal(validateInput("url", "ftp://x"), "err_invalid_url");
});

test("url mode: https:// without host -> err_invalid_url", () => {
  assert.equal(validateInput("url", "https://"), "err_invalid_url");
});

test("url mode: https://example.com -> null", () => {
  assert.equal(validateInput("url", "https://example.com"), null);
  assert.equal(validateInput("url", "  HTTP://Example.com/path?q=1  "), null);
});

test("url mode rejects non-url text; text mode accepts it", () => {
  assert.equal(validateInput("url", "abc"), "err_invalid_url");
  assert.equal(validateInput("url", "example.com"), "err_invalid_url");
  assert.equal(validateInput("url", "https:// example.com"), "err_invalid_url");
  assert.equal(validateInput("text", "abc"), null);
  assert.equal(isHttpUrl("javascript:void(0)"), false);
});

test("returned keys exist in the spec 8.7 copy table", () => {
  for (const key of ["err_empty", "err_too_long", "err_invalid_url"]) {
    assert.equal(typeof STRINGS[key], "string", key);
  }
});
