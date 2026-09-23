import { test } from "node:test";
import assert from "node:assert/strict";
import { t } from "../../i18n.js";
import {
  CONFIDENCE_BASES,
  angleOf,
  SIMILAR_NEWS_MAX,
  confidenceNoteLines,
  similarNewsItems,
  similarityText,
} from "./similarNews.js";

// Evidence-based confidence note (FR-22) and "similar checks in the knowledge base" (FR-02 similar_news).
// Expected texts come from t() so this folder stays free of Han characters.

const CASE = {
  title: "claim text",
  url: "https://www.mygopen.com/2026/09/salt.html",
  source: "MyGoPen",
  risk_type: "MISINFO",
  frame_type: "red",
  similarity: 0.7234,
  degrees: 43.6,
  kb_id: "kb-1",
};

test("similarityText shows two decimals and a rounded angle", () => {
  assert.equal(similarityText(0.7234, 43.6), t("similar_item", { similarity: "0.72", degrees: 44 }));
  assert.equal(similarityText(0.75, null), t("similar_item", { similarity: "0.75", degrees: 41 }));
  assert.equal(similarityText(null, 40), "");
});

test("angleOf is the arccos angle in degrees", () => {
  assert.equal(Math.round(angleOf(0.75) * 10) / 10, 41.4);
  assert.equal(angleOf(1), 0);
  assert.equal(angleOf(2), 0);
});

test("similarNewsItems maps rows for DotRow and keeps colour from frame_type", () => {
  const [row] = similarNewsItems({ cached: false, similar_news: [CASE] });
  assert.equal(row.title, "claim text");
  assert.equal(row.href, CASE.url);
  assert.deepEqual(row.item, { frame_type: "red", risk_type: "MISINFO" });
  assert.deepEqual(row.meta, ["MyGoPen", similarityText(0.7234, 43.6)]);
});

test("similarNewsItems is empty on cache hits and when nothing was sent", () => {
  assert.deepEqual(similarNewsItems({ cached: true, similar_news: [CASE] }), []);
  assert.deepEqual(similarNewsItems({ cached: false }), []);
  assert.deepEqual(similarNewsItems(null), []);
});

test("similarNewsItems keeps at most three rows, drops blank titles and never links non-http urls", () => {
  const rows = similarNewsItems({
    similar_news: [
      { ...CASE, title: "  " },
      { ...CASE, url: "javascript:alert(1)" },
      { ...CASE, url: null },
      CASE,
      CASE,
    ],
  });
  assert.equal(rows.length, SIMILAR_NEWS_MAX);
  assert.equal(rows[0].href, null);
  assert.equal(rows[1].href, null);
  assert.equal(rows[2].href, CASE.url);
  assert.equal(new Set(rows.map((row) => row.key)).size, rows.length);
});

test("confidenceNoteLines explains the basis, the nearest case and the method", () => {
  const lines = confidenceNoteLines({
    confidence_basis: "similar_case",
    evidence: { nearest_similarity: 0.7012, nearest_degrees: 45.47 },
  });
  assert.deepEqual(lines, [
    t("confidence_basis_similar_case"),
    t("confidence_evidence", { similarity: "0.70", degrees: 45 }),
    t("confidence_method"),
  ]);
});

test("confidenceNoteLines shows the nearest case only when it is the reason", () => {
  const evidence = { nearest_similarity: 0.61, nearest_degrees: 52.4 };
  assert.deepEqual(confidenceNoteLines({ confidence_basis: "ai_only", evidence }), [
    t("confidence_basis_ai_only"),
    t("confidence_method"),
  ]);
  assert.equal(confidenceNoteLines({ confidence_basis: "conflict", evidence }).length, 3);
  assert.equal(confidenceNoteLines({ confidence_basis: "similar_case", evidence: { nearest_similarity: null } }).length, 2);
});

test("results stored before the evidence change keep the old note", () => {
  assert.deepEqual(confidenceNoteLines({ confidence_level: "high" }), [t("confidence_note")]);
  assert.deepEqual(confidenceNoteLines({ confidence_basis: "unknown" }), [t("confidence_note")]);
});

test("every confidence basis has its own sentence", () => {
  for (const basis of CONFIDENCE_BASES) {
    const text = t(`confidence_basis_${basis}`);
    assert.notEqual(text, `confidence_basis_${basis}`, basis);
  }
});
