// Initial demo posts shown on first load.
// Replace with empty array `[]` to start with a clean feed.

export const initialPosts = [
  {
    id: 1,
    author: {
      name: '林阿宏',
      avatar: 'https://ui-avatars.com/api/?name=林阿宏&background=random',
      handle: '@ahong_lin',
    },
    time: '2 小時前',
    content:
      '剛剛收到一封簡訊說我抽中某某飆股的認購權，穩賺不賠，還要我加 LINE 老師的帳號，有人收到這個嗎？是不是詐騙啊？',
    aiResult: {
      risk_type: 'SCAM',
      category: '投資理財詐騙',
      confidence_score: 0.98,
      summary: '這是一則典型的高報酬投資詐騙訊息，誘導使用者加入不明 LINE 群組。',
      explanation:
        '系統比對 165 反詐騙資料庫，發現該內容特徵與多起報案紀錄高度吻合。詐騙集團常以「穩賺不賠」、「飆股」等話術吸引被害人。',
      sources: [{ title: '165 反詐騙專線', url: 'https://165.gov.tw/' }],
    },
    likes: 12,
    comments: 5,
    shares: 2,
  },
  {
    id: 2,
    author: {
      name: '陳美玲',
      avatar: 'https://ui-avatars.com/api/?name=陳美玲&background=random',
      handle: '@meiling_c',
    },
    time: '5 小時前',
    content:
      '分享一下，最近政府推出的節能家電退稅補助，只要在期限內購買符合標準的家電，就可以線上申請退款喔！網址在這：https://www.etax.nat.gov.tw/...',
    aiResult: {
      risk_type: 'SAFE',
      category: '官方資訊',
      confidence_score: 0.99,
      summary: '此為官方政府網站連結，發布的補助資訊屬實。',
      explanation: '網址網域為 gov.tw，確認為中華民國政府官方網站。該項節能家電補助計畫目前確實正在進行中。',
      sources: [],
    },
    likes: 45,
    comments: 8,
    shares: 15,
  },
];

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
