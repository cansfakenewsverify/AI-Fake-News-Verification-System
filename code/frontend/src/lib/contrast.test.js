import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// 讀 index.css 解析兩個主題的 token，計算 WCAG 2.x 對比（spec §8.6、測試 UI-4）。
const css = readFileSync(new URL("../index.css", import.meta.url), "utf8");

function block(selectorRe) {
  const m = css.match(selectorRe);
  assert.ok(m, `找不到 token 區塊 ${selectorRe}`);
  const tokens = {};
  for (const [, name, value] of m[1].matchAll(/--(c-[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    tokens[name] = value;
  }
  return tokens;
}

const light = block(/(?:^|\n):root\s*\{([^}]*)\}/);
const dark = { ...light, ...block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/) };

function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// 紅字 on red-soft 只要求 3.0：僅限 24px 粗體大字（燈號區塊 frame_label）；
// 紅色小字不得放在 red-soft 上。
const PAIRS = [
  ["c-ink", "c-bg", 4.5],
  ["c-ink", "c-surface", 4.5],
  ["c-ink-2", "c-bg", 4.5],
  ["c-ink-2", "c-surface", 4.5],
  ["c-ink-3", "c-bg", 4.5],
  ["c-ink-3", "c-surface", 4.5],
  ["c-yellow", "c-yellow-soft", 4.5],
  ["c-grey", "c-grey-soft", 4.5],
  ["c-green", "c-green-soft", 4.5],
  ["c-red", "c-red-soft", 3.0],
  // 元件實際使用的組合（P-14～P-17）：
  // DotRow 13px 判定文字與 InputCard inline 錯誤字（在頁面底或卡片底上）
  ["c-red", "c-bg", 4.5],
  ["c-red", "c-surface", 4.5],
  ["c-yellow", "c-bg", 4.5],
  ["c-yellow", "c-surface", 4.5],
  ["c-green", "c-bg", 4.5],
  ["c-green", "c-surface", 4.5],
  ["c-grey", "c-bg", 4.5],
  ["c-grey", "c-surface", 4.5],
  // VerdictBlock category_label（14px --c-ink-2 在各 -soft 底上）
  ["c-ink-2", "c-red-soft", 4.5],
  ["c-ink-2", "c-yellow-soft", 4.5],
  ["c-ink-2", "c-green-soft", 4.5],
  ["c-ink-2", "c-grey-soft", 4.5],
  // Chip cache／neutral、篩選選中與 Toast（反白）、分段 tab 未選、分頁列當前格
  ["c-accent", "c-accent-soft", 4.5],
  ["c-ink-2", "c-accent-soft", 4.5],
  ["c-ink-inverse", "c-ink", 4.5],
  ["c-ink-2", "c-line", 4.5],
  ["c-accent", "c-bg", 4.5],
];

test("contrast helper matches known values", () => {
  assert.ok(Math.abs(contrast("#FFFFFF", "#000000") - 21) < 0.01);
  assert.ok(Math.abs(contrast("#777777", "#FFFFFF") - 4.48) < 0.01);
});

for (const [themeName, tokens] of [["light", light], ["dark", dark]]) {
  for (const [fg, bg, min] of PAIRS) {
    test(`${themeName}: ${fg} on ${bg} >= ${min}`, () => {
      assert.ok(tokens[fg] && tokens[bg], `missing token ${fg} or ${bg}`);
      const ratio = contrast(tokens[fg], tokens[bg]);
      assert.ok(ratio >= min, `${fg} ${tokens[fg]} on ${bg} ${tokens[bg]} = ${ratio.toFixed(2)} < ${min}`);
    });
  }
}

test("accent token defined exactly once per theme; #111111 accent only in light", () => {
  const lines = css.split("\n").filter((l) => /--c-accent:/.test(l));
  assert.equal(lines.length, 2);
  assert.equal(light["c-accent"].toUpperCase(), "#111111");
  assert.notEqual(dark["c-accent"].toUpperCase(), "#111111");
});
