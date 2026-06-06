// 初始貼文：留空，使用者送出查證後才會出現卡片。
export const initialPosts = [];

// Risk-type → UI styling map (single source of truth)
export const RISK_STYLES = {
  SCAM: {
    wrapper: 'bg-gradient-to-br from-red-50 to-rose-50 border-red-200',
    accent: 'bg-red-500',
    iconBg: 'bg-red-100 text-red-600',
    chip: 'bg-red-500 text-white',
    chipSmall: 'bg-red-100 text-red-700',
    title: 'text-red-700',
    icon: '🚨',
    label: '高風險詐騙',
    shortLabel: '詐騙',
  },
  MISINFO: {
    wrapper: 'bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200',
    accent: 'bg-amber-500',
    iconBg: 'bg-amber-100 text-amber-600',
    chip: 'bg-amber-500 text-white',
    chipSmall: 'bg-amber-100 text-amber-700',
    title: 'text-amber-700',
    icon: '⚠️',
    label: '假訊息提醒',
    shortLabel: '假訊息',
  },
  SAFE: {
    wrapper: 'bg-gradient-to-br from-emerald-50 to-teal-50 border-emerald-200',
    accent: 'bg-emerald-500',
    iconBg: 'bg-emerald-100 text-emerald-600',
    chip: 'bg-emerald-500 text-white',
    chipSmall: 'bg-emerald-100 text-emerald-700',
    title: 'text-emerald-700',
    icon: '✅',
    label: '安全資訊',
    shortLabel: '安全',
  },
  PENDING: {
    wrapper: 'bg-gradient-to-br from-slate-50 to-gray-50 border-slate-200',
    accent: 'bg-slate-400',
    iconBg: 'bg-slate-100 text-slate-600',
    chip: 'bg-slate-400 text-white',
    chipSmall: 'bg-slate-100 text-slate-500',
    title: 'text-slate-700',
    icon: '⏳',
    label: 'AI 分析中',
    shortLabel: 'AI 分析中',
  },
  UNKNOWN: {
    wrapper: 'bg-gradient-to-br from-slate-50 to-gray-50 border-slate-200',
    accent: 'bg-slate-400',
    iconBg: 'bg-slate-100 text-slate-600',
    chip: 'bg-slate-400 text-white',
    chipSmall: 'bg-slate-100 text-slate-500',
    title: 'text-slate-700',
    icon: 'ℹ️',
    label: 'AI 查證結果',
    shortLabel: '待分析',
  },
};

export const DEFAULT_RISK_STYLE = RISK_STYLES.UNKNOWN;
