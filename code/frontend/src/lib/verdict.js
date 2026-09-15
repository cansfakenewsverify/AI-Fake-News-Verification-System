// 前端判定映射 util（spec §7.8、brief §3.7／§3.8／§7-4）。
// 規則：結果頁燈色「只讀」後端 frame_type／frame_label，絕不由風險類別欄位重算。
// 風險類別欄位只允許在 listVerdict（熱門／知識庫／最近查證：這些資料沒有 frame_type）
// 與 showNoSourceBanner／showSources（spec §5.3 verification_status 例外）內讀取。
import { t } from "../i18n.js";

const TONES = ["red", "yellow", "green", "grey"];

/** frame_type → 色調與 token；未知值一律 grey。 */
export function toneOf(frame_type) {
  const tone = TONES.includes(frame_type) ? frame_type : "grey";
  return { tone, fg: `var(--c-${tone})`, soft: `var(--c-${tone}-soft)` };
}

function withLabel(tone, labelKey) {
  return { ...toneOf(tone), labelKey, label: t(labelKey) };
}

/**
 * 列表項目（熱門牆、知識庫、最近查證）的判定 chip。
 * 回傳 {tone, fg, soft, labelKey, label}。
 */
export function listVerdict(item) {
  const it = item || {};
  const risk = it.risk_type;

  // 最近查證：若已回寫 frame_type，燈色以後端 frame_type 為準。
  if (it.frame_type != null) {
    const { tone } = toneOf(it.frame_type);
    let labelKey;
    if (tone === "red") {
      labelKey = risk === "SCAM" ? "dot_scam" : risk === "MISINFO" ? "dot_misinfo" : "frame_red_other";
    } else if (tone === "yellow") {
      labelKey = risk === "UNVERIFIABLE" ? "frame_yellow_unverifiable" : "frame_yellow";
    } else if (tone === "green") {
      labelKey = "dot_safe";
    } else {
      labelKey = "frame_grey";
    }
    const out = withLabel(tone, labelKey);
    if (typeof it.frame_label === "string" && it.frame_label) out.label = it.frame_label;
    return out;
  }

  if (it.verified === false || risk == null || ["PENDING", "UNVERIFIABLE", "UNKNOWN"].includes(risk)) {
    return withLabel("grey", "chip_pending");
  }
  if (risk === "SCAM") return withLabel("red", "dot_scam");
  if (risk === "MISINFO") return withLabel("red", "dot_misinfo");
  if (risk === "SAFE") return withLabel("green", "dot_safe");
  return withLabel("grey", "chip_pending");
}

function isAiUnavailable(result) {
  return result?.ai_unavailable === true;
}

/** 「尚無查核機構證實」橫幅：unverified（缺鍵視同）且非 UNVERIFIABLE、非 AI 不可用。 */
export function showNoSourceBanner(result) {
  if (!result) return false;
  const status = result.verification_status ?? "unverified";
  return status === "unverified" && result.risk_type !== "UNVERIFIABLE" && !isAiUnavailable(result);
}

/** 來源區塊：UNVERIFIABLE 或 AI 不可用時不顯示。 */
export function showSources(result) {
  if (!result) return false;
  return result.risk_type !== "UNVERIFIABLE" && !isAiUnavailable(result);
}

/** 可否分享：後端有給 share 物件才顯示分享按鈕。 */
export function canShare(res) {
  return res?.share != null;
}

/** cache_layer → i18n key。 */
export function cacheChipKey(cache_layer) {
  return ["url", "hash", "vector"].includes(cache_layer) ? `chip_cache_${cache_layer}` : "chip_live";
}

/** confidence_level（後端 高／中／低，spec §5.3）→ confidence_chip_* key；缺值或未知回 null（不渲染信心 chip）。 */
export function confidenceChipKey(confidence_level) {
  const keys = { 高: "confidence_chip_high", 中: "confidence_chip_mid", 低: "confidence_chip_low" };
  return Object.prototype.hasOwnProperty.call(keys, confidence_level) ? keys[confidence_level] : null;
}

/** label_source → i18n key；未知值回 null（呼叫端不渲染）。 */
export function labelSourceKey(label_source) {
  return ["ai", "rule", "gold", "admin"].includes(label_source) ? `label_source_${label_source}` : null;
}

/** 來源 tier → i18n key；tier 3 或缺值回 null（呼叫端不渲染）。 */
export function tierCaption(tier) {
  const n = Number(tier);
  if (n === 1) return "tier_1_chip";
  if (n === 2) return "tier_2_chip";
  return null;
}
