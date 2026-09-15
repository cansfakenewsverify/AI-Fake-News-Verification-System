import { test } from "node:test";
import assert from "node:assert/strict";
import {
  toneOf,
  listVerdict,
  showNoSourceBanner,
  showSources,
  canShare,
  cacheChipKey,
  labelSourceKey,
  tierCaption,
} from "./verdict.js";
import { t } from "../i18n.js";

const cases = [
  // toneOf
  ["toneOf red", () => toneOf("red"), { tone: "red", fg: "var(--c-red)", soft: "var(--c-red-soft)" }],
  ["toneOf yellow", () => toneOf("yellow").tone, "yellow"],
  ["toneOf green", () => toneOf("green").soft, "var(--c-green-soft)"],
  ["toneOf grey", () => toneOf("grey").fg, "var(--c-grey)"],
  ["toneOf banana -> grey", () => toneOf("banana").tone, "grey"],
  ["toneOf undefined -> grey", () => toneOf(undefined).tone, "grey"],

  // listVerdict
  ["list MISINFO unverified -> grey pending", () => pick(listVerdict({ risk_type: "MISINFO", verified: false })), { tone: "grey", labelKey: "chip_pending" }],
  ["list SAFE verified -> green safe", () => pick(listVerdict({ risk_type: "SAFE", verified: true })), { tone: "green", labelKey: "dot_safe" }],
  ["list SCAM -> red scam", () => pick(listVerdict({ risk_type: "SCAM", verified: true })), { tone: "red", labelKey: "dot_scam" }],
  ["list MISINFO -> red misinfo", () => pick(listVerdict({ risk_type: "MISINFO" })), { tone: "red", labelKey: "dot_misinfo" }],
  ["list PENDING -> grey", () => listVerdict({ risk_type: "PENDING" }).tone, "grey"],
  ["list UNVERIFIABLE -> grey", () => listVerdict({ risk_type: "UNVERIFIABLE", verified: true }).tone, "grey"],
  ["list UNKNOWN -> grey", () => listVerdict({ risk_type: "UNKNOWN" }).tone, "grey"],
  ["list missing risk -> grey", () => listVerdict({}).labelKey, "chip_pending"],
  ["list null item -> grey", () => listVerdict(null).tone, "grey"],
  ["list label text is i18n", () => listVerdict({ risk_type: "SAFE" }).label, t("dot_safe")],
  ["history frame_type wins over risk", () => listVerdict({ risk_type: "SAFE", frame_type: "yellow" }).tone, "yellow"],
  ["history frame_label used", () => listVerdict({ frame_type: "red", frame_label: "詐騙警告" }).label, "詐騙警告"],
  ["history unknown frame_type -> grey", () => listVerdict({ risk_type: "SCAM", frame_type: "banana" }).tone, "grey"],

  // banner / sources / share
  ["banner SAFE unverified -> true", () => showNoSourceBanner({ risk_type: "SAFE", verification_status: "unverified" }), true],
  ["banner UNVERIFIABLE -> false", () => showNoSourceBanner({ risk_type: "UNVERIFIABLE", verification_status: "unverified" }), false],
  ["banner ai_unavailable -> false", () => showNoSourceBanner({ risk_type: "SAFE", verification_status: "unverified", ai_unavailable: true }), false],
  ["banner missing status SCAM -> true", () => showNoSourceBanner({ risk_type: "SCAM" }), true],
  ["banner verified -> false", () => showNoSourceBanner({ risk_type: "SCAM", verification_status: "verified" }), false],
  ["sources normal -> true", () => showSources({ risk_type: "SCAM" }), true],
  ["sources UNVERIFIABLE -> false", () => showSources({ risk_type: "UNVERIFIABLE" }), false],
  ["sources ai_unavailable -> false", () => showSources({ risk_type: "SAFE", ai_unavailable: true }), false],
  ["canShare with share", () => canShare({ share: { text: "x" } }), true],
  ["canShare null share", () => canShare({ share: null }), false],
  ["canShare missing", () => canShare({}), false],

  // small helpers
  ["cache url", () => cacheChipKey("url"), "chip_cache_url"],
  ["cache hash", () => cacheChipKey("hash"), "chip_cache_hash"],
  ["cache vector", () => cacheChipKey("vector"), "chip_cache_vector"],
  ["cache null -> live", () => cacheChipKey(null), "chip_live"],
  ["label_source ai", () => labelSourceKey("ai"), "label_source_ai"],
  ["label_source admin", () => labelSourceKey("admin"), "label_source_admin"],
  ["label_source unknown", () => labelSourceKey("x"), null],
  ["tier 1", () => tierCaption(1), "tier_1_chip"],
  ["tier 2", () => tierCaption(2), "tier_2_chip"],
  ["tier 3 -> null", () => tierCaption(3), null],
  ["tier missing -> null", () => tierCaption(undefined), null],
];

function pick(v) {
  return { tone: v.tone, labelKey: v.labelKey };
}

for (const [name, fn, expected] of cases) {
  test(`verdict: ${name}`, () => {
    assert.deepEqual(fn(), expected);
  });
}

test("verdict: all i18n keys used exist", () => {
  const keys = [
    "chip_pending", "dot_scam", "dot_misinfo", "dot_safe", "frame_red_other", "frame_yellow",
    "frame_yellow_unverifiable", "frame_grey", "chip_live", "chip_cache_url", "chip_cache_hash",
    "chip_cache_vector", "label_source_ai", "label_source_rule", "label_source_gold",
    "label_source_admin", "tier_1_chip", "tier_2_chip",
  ];
  for (const k of keys) assert.notEqual(t(k), k, `missing i18n key ${k}`);
});
