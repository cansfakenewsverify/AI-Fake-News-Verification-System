// 初始貼文：留空，使用者送出查證後才會出現卡片。
export const initialPosts = [];

// Risk-type → UI styling map（單一來源）。
// 深色查核儀風格：統一深色卡片 + 語意色左條／徽章（青綠基調的語意紅/黃/綠/灰）。
const CARD = 'bg-[var(--c-bg-surface)] border-[var(--c-border)]';

export const RISK_STYLES = {
  SCAM: {
    wrapper: `${CARD}`,
    accent: 'bg-[var(--c-risk-high)]',
    iconBg: 'bg-[var(--c-risk-high-soft)] text-[var(--c-risk-high)]',
    chip: 'bg-[var(--c-risk-high-soft)] text-[var(--c-risk-high)]',
    chipSmall: 'bg-[var(--c-risk-high-soft)] text-[var(--c-risk-high)]',
    title: 'text-[var(--c-risk-high)]',
    icon: '✕',
    label: '高風險詐騙',
    shortLabel: '詐騙',
  },
  MISINFO: {
    wrapper: `${CARD}`,
    accent: 'bg-[var(--c-risk-mid)]',
    iconBg: 'bg-[var(--c-risk-mid-soft)] text-[var(--c-risk-mid)]',
    chip: 'bg-[var(--c-risk-mid-soft)] text-[var(--c-risk-mid)]',
    chipSmall: 'bg-[var(--c-risk-mid-soft)] text-[var(--c-risk-mid)]',
    title: 'text-[var(--c-risk-mid)]',
    icon: '!',
    label: '假訊息提醒',
    shortLabel: '假訊息',
  },
  SAFE: {
    wrapper: `${CARD}`,
    accent: 'bg-[var(--c-risk-low)]',
    iconBg: 'bg-[var(--c-risk-low-soft)] text-[var(--c-risk-low)]',
    chip: 'bg-[var(--c-risk-low-soft)] text-[var(--c-risk-low)]',
    chipSmall: 'bg-[var(--c-risk-low-soft)] text-[var(--c-risk-low)]',
    title: 'text-[var(--c-risk-low)]',
    icon: '✓',
    label: '安全資訊',
    shortLabel: '安全',
  },
  PENDING: {
    wrapper: `${CARD}`,
    accent: 'bg-[var(--c-text-muted)]',
    iconBg: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    chip: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    chipSmall: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    title: 'text-[var(--c-text-secondary)]',
    icon: '?',
    label: '尚未查證',
    shortLabel: '未查證',
  },
  UNKNOWN: {
    wrapper: `${CARD}`,
    accent: 'bg-[var(--c-text-muted)]',
    iconBg: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    chip: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    chipSmall: 'bg-[var(--c-muted-soft)] text-[var(--c-text-secondary)]',
    title: 'text-[var(--c-text-secondary)]',
    icon: 'i',
    label: 'AI 查證結果',
    shortLabel: '待分析',
  },
};

export const DEFAULT_RISK_STYLE = RISK_STYLES.UNKNOWN;
