import { useState } from 'react';

// === 假貼文資料 (Mock Data) ===
const initialPosts = [
  {
    id: 1,
    author: {
      name: '林阿宏',
      avatar: 'https://ui-avatars.com/api/?name=林阿宏&background=random',
      handle: '@ahong_lin'
    },
    time: '2 小時前',
    content: '剛剛收到一封簡訊說我抽中某某飆股的認購權，穩賺不賠，還要我加 LINE 老師的帳號，有人收到這個嗎？是不是詐騙啊？',
    aiResult: {
      risk_type: 'SCAM',
      category: '投資理財詐騙',
      confidence_score: 0.98,
      summary: '這是一則典型的高報酬投資詐騙訊息，誘導使用者加入不明 LINE 群組。',
      explanation: '系統比對 165 反詐騙資料庫，發現該內容特徵與多起報案紀錄高度吻合。詐騙集團常以「穩賺不賠」、「飆股」等話術吸引被害人。',
      sources: ['https://165.gov.tw/']
    },
    likes: 12,
    comments: 5,
    shares: 2
  },
  {
    id: 2,
    author: {
      name: '陳美玲',
      avatar: 'https://ui-avatars.com/api/?name=陳美玲&background=random',
      handle: '@meiling_c'
    },
    time: '5 小時前',
    content: '分享一下，最近政府推出的節能家電退稅補助，只要在期限內購買符合標準的家電，就可以線上申請退款喔！網址在這：https://www.etax.nat.gov.tw/...',
    aiResult: {
      risk_type: 'SAFE',
      category: '官方資訊',
      confidence_score: 0.99,
      summary: '此為官方政府網站連結，發布的補助資訊屬實。',
      explanation: '網址網域為 gov.tw，確認為中華民國政府官方網站。該項節能家電補助計畫目前確實正在進行中。',
      sources: []
    },
    likes: 45,
    comments: 8,
    shares: 15
  }
];

export default function App() {
  const [posts] = useState(initialPosts);

  // 根據 risk_type 決定 AI 查證卡片的樣式
  const getAiCardStyle = (riskType) => {
    switch (riskType) {
      case 'SCAM':
        return { bg: 'bg-red-50', text: 'text-red-800', border: 'border-red-200', icon: '🚨', title: 'AI 高風險詐騙' };
      case 'SAFE':
        return { bg: 'bg-green-50', text: 'text-green-800', border: 'border-green-200', icon: '✅', title: 'AI 安全資訊' };
      case 'MISINFO':
        return { bg: 'bg-orange-50', text: 'text-orange-800', border: 'border-orange-200', icon: '⚠️', title: 'AI 假訊息提醒' };
      default:
        return { bg: 'bg-gray-50', text: 'text-gray-800', border: 'border-gray-200', icon: 'ℹ️', title: 'AI 查證結果' };
    }
  };

  return (
    // 整體佈局：淺灰背景，滿版高度
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
      
      {/* 頂部導覽列 (Navbar) */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200 px-4 py-3 flex justify-center">
        <div className="w-full max-w-2xl flex items-center justify-between">
          <div className="text-xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-blue-500 tracking-tight">
            全民查證公社
          </div>
          <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold shadow-sm cursor-pointer hover:bg-indigo-200 transition-colors">
            我
          </div>
        </div>
      </nav>

      {/* 內容區塊：置中且最大寬度為 max-w-2xl */}
      <main className="w-full max-w-2xl mx-auto flex flex-col pt-6 pb-20 px-4 sm:px-0 gap-6">
        
        {/* === 發文區塊 (Create Post) === */}
        <div className="bg-white rounded-2xl p-4 sm:p-5 shadow-sm border border-gray-100 flex gap-4">
          <img 
            src="https://ui-avatars.com/api/?name=User&background=E0E7FF&color=4F46E5" 
            alt="My Avatar" 
            className="w-10 h-10 rounded-full flex-shrink-0"
          />
          <div className="flex-1 flex flex-col gap-3">
            <textarea 
              className="w-full bg-transparent resize-none outline-none text-[16px] placeholder-gray-400 min-h-[60px]"
              placeholder="分享可疑的新聞、連結或截圖..."
            ></textarea>
            <div className="flex justify-end border-t border-gray-50 pt-3">
              <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-full font-medium transition-colors text-sm shadow-sm flex items-center gap-2">
                <span>✨</span> 發布並讓 AI 查證
              </button>
            </div>
          </div>
        </div>

        {/* === 貼文列表 (News Feed) === */}
        <div className="flex flex-col gap-5">
          {posts.map((post) => (
            <article key={post.id} className="bg-white rounded-2xl p-4 sm:p-5 shadow-sm border border-gray-100 transition-shadow hover:shadow-md">
              
              {/* 發文者資訊區塊 */}
              <div className="flex items-center gap-3 mb-3">
                <img 
                  src={post.author.avatar} 
                  alt={post.author.name} 
                  className="w-10 h-10 rounded-full flex-shrink-0"
                />
                <div className="flex flex-col flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-bold text-gray-900">{post.author.name}</span>
                    <span className="text-gray-500 text-sm">{post.author.handle}</span>
                    <span className="text-gray-400 text-sm hidden sm:inline">·</span>
                    <span className="text-gray-500 text-sm hover:underline cursor-pointer">{post.time}</span>
                  </div>
                </div>
              </div>

              {/* 使用者原本的內文 */}
              <div className="text-gray-800 text-[15px] sm:text-[16px] leading-relaxed mb-4 whitespace-pre-wrap">
                {post.content}
              </div>

              {/* AI 查證結果卡片 (嵌入於發文下方) */}
              {post.aiResult && (() => {
                const style = getAiCardStyle(post.aiResult.risk_type);
                return (
                  <div className={`mt-2 mb-4 rounded-xl border ${style.border} ${style.bg} overflow-hidden shadow-sm`}>
                    
                    {/* 卡片標頭 (顯示判斷與信心分數) */}
                    <div className={`px-4 py-2.5 border-b ${style.border} bg-white/40 flex items-center justify-between flex-wrap gap-2`}>
                      <h3 className={`font-bold flex items-center gap-1.5 text-sm sm:text-base ${style.text}`}>
                        <span>{style.icon}</span>
                        {style.title}：{post.aiResult.category}
                      </h3>
                      <div className="text-xs font-medium text-gray-600 bg-white/60 px-2.5 py-1 rounded-md shadow-sm border border-white/80">
                        AI 準確度 <span className={`font-bold ${style.text}`}>{post.aiResult.confidence_score ? `${(post.aiResult.confidence_score * 100).toFixed(0)}%` : 'N/A'}</span>
                      </div>
                    </div>

                    {/* 卡片內容 (摘要與解釋) */}
                    <div className="p-4 flex flex-col gap-3">
                      <div>
                        <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1">AI 查證摘要</h4>
                        <p className="text-[14px] font-medium text-gray-800 leading-relaxed">{post.aiResult.summary}</p>
                      </div>
                      
                      <div>
                        <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1">風險詳細解釋</h4>
                        <p className="text-[14px] text-gray-600 leading-relaxed">{post.aiResult.explanation}</p>
                      </div>

                      {post.aiResult.sources && post.aiResult.sources.length > 0 && (
                        <div className="pt-3 mt-1 border-t border-black/5">
                          <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-1">相關參考來源</h4>
                          <div className="flex flex-wrap gap-2 mt-2">
                            {post.aiResult.sources.map((source, idx) => (
                              <a 
                                key={idx} 
                                href={source} 
                                target="_blank" 
                                rel="noopener noreferrer" 
                                className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline inline-flex items-center gap-1 bg-white px-2 py-1 rounded border border-indigo-100 transition-colors shadow-sm"
                              >
                                🔗 點此查看來源
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* 底部互動區 (讚、留言、分享) */}
              <div className="flex items-center justify-between text-gray-500 pt-3 border-t border-gray-100 px-2 sm:px-8">
                <button className="flex items-center gap-2 hover:text-red-500 transition-colors group p-2 rounded-full hover:bg-red-50">
                  <span className="text-[18px] group-hover:scale-110 transition-transform grayscale group-hover:grayscale-0">❤️</span>
                  <span className="text-sm font-medium">{post.likes}</span>
                </button>
                <button className="flex items-center gap-2 hover:text-blue-500 transition-colors group p-2 rounded-full hover:bg-blue-50">
                  <span className="text-[18px] group-hover:scale-110 transition-transform grayscale group-hover:grayscale-0">💬</span>
                  <span className="text-sm font-medium">{post.comments}</span>
                </button>
                <button className="flex items-center gap-2 hover:text-green-500 transition-colors group p-2 rounded-full hover:bg-green-50">
                  <span className="text-[18px] group-hover:scale-110 transition-transform grayscale group-hover:grayscale-0">🔗</span>
                  <span className="text-sm font-medium">{post.shares}</span>
                </button>
              </div>

            </article>
          ))}
        </div>

      </main>
    </div>
  );
}