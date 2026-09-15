import { test } from "node:test";
import assert from "node:assert/strict";
import { THEME_KEY, getInitialTheme, applyTheme, toggleTheme, getSystemTheme } from "./theme.js";

const throwingStorage = {
  getItem() { throw new Error("SecurityError"); },
  setItem() { throw new Error("SecurityError"); },
};
const mm = (dark) => () => ({ matches: dark });

function memStorage(init = {}) {
  const data = { ...init };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
}

function fakeRoot() {
  const attrs = {};
  return {
    attrs,
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    setAttribute: (k, v) => { attrs[k] = v; },
  };
}

test("storage throwing falls back to system preference without throwing", () => {
  assert.equal(getInitialTheme({ storage: throwingStorage, matchMedia: mm(true) }), "dark");
  assert.equal(getInitialTheme({ storage: throwingStorage, matchMedia: mm(false) }), "light");
});

test("stored value wins over system preference", () => {
  assert.equal(getInitialTheme({ storage: memStorage({ [THEME_KEY]: "light" }), matchMedia: mm(true) }), "light");
});

test("invalid stored value is ignored", () => {
  assert.equal(getInitialTheme({ storage: memStorage({ [THEME_KEY]: "blue" }), matchMedia: mm(true) }), "dark");
});

test("no storage / no matchMedia / matchMedia throwing -> light", () => {
  assert.equal(getInitialTheme({ storage: undefined, matchMedia: undefined }), "light");
  assert.equal(getSystemTheme(() => { throw new Error("x"); }), "light");
});

test("applyTheme sets data-theme", () => {
  const root = fakeRoot();
  applyTheme("dark", root);
  assert.equal(root.attrs["data-theme"], "dark");
  applyTheme("garbage", root);
  assert.equal(root.attrs["data-theme"], "light");
});

test("toggleTheme flips and persists", () => {
  const root = fakeRoot();
  const storage = memStorage();
  root.setAttribute("data-theme", "dark");
  assert.equal(toggleTheme({ root, storage }), "light");
  assert.equal(storage.data[THEME_KEY], "light");
  assert.equal(root.attrs["data-theme"], "light");
  assert.equal(toggleTheme({ root, storage }), "dark");
});

test("toggleTheme with throwing storage does not throw", () => {
  const root = fakeRoot();
  root.setAttribute("data-theme", "light");
  assert.equal(toggleTheme({ root, storage: throwingStorage, matchMedia: mm(false) }), "dark");
});
