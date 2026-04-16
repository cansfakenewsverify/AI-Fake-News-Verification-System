// src/mockData.js
// 這是模擬後端 API 最終會回傳給前端的 JSON 格式

export const MOCK_SCAM_RESULT = {
  status: "scam",
  score: 98,
  summary: "⚠️ 高風險！這是一則常見的投資詐騙訊息，連結導向偽造的假網站。",
  sources: [
    { title: "165 反詐騙網域公告", url: "https://165.gov.tw/" },
    { title: "Cofacts 相似回報紀錄", url: "https://cofacts.tw/" }
  ]
};

export const MOCK_SAFE_RESULT = {
  status: "safe",
  score: 12,
  summary: "✅ 安全！未發現詐騙風險，連結為正常的官方網站。",
  sources: []
};