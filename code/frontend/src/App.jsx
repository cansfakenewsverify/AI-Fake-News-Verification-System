import { useState, useEffect, useRef, useCallback } from 'react';
import { initialPosts, RISK_STYLES, DEFAULT_RISK_STYLE } from './mockData';

const getAiCardStyle = (riskType) => RISK_STYLES[riskType] || DEFAULT_RISK_STYLE;

// === AI 分析中骨架卡片 ===
function AnalyzingCard() {
  return (
    <div className="mt-3 mb-4 rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm fade-in">
      <div className="h-1 bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 analyzing-pulse" />
      <div className="p-4 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-indigo-50 flex items-center justify-center text-xl analyzing-pulse">
          🤖
        </div>
        <div className="flex-1 flex flex-col gap-2">
          <div className="h-3 w-2/3 rounded shimmer" />
          <div className="h-3 w-1/2 rounded shimmer" />
        </div>
      </div>
      <div className="px-4 pb-4 flex flex-col gap-2">
        <div className="h-3 w-full rounded shimmer" />
        <div className="h-3 w-5/6 rounded shimmer" />
      </div>
      <div className="px-4 pb-4">
        <div className="text-[12px] text-slate-500 flex items-center gap-1.5">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping" />
          AI 正在進行雙重事實查核...
        </div>
      </div>
    </div>
  );
}

// === AI 結果卡片 ===
function AiResultCard({ result }) {
  const s = getAiCardStyle(result.risk_type);
  const conf = result.confidence_score;
  const confPct = conf != null ? Math.round(conf * 100) : null;

  return (
    <div className={`mt-3 mb-4 rounded-2xl border ${s.wrapper} overflow-hidden shadow-sm fade-in relative`}>
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${s.accent}`} />

      <div className="px-4 pt-3.5 pb-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-xl ${s.iconBg} flex items-center justify-center text-lg shadow-sm`}>
            {s.icon}
          </div>
          <div className="flex flex-col">
            <span className={`text-[11px] font-semibold uppercase tracking-wider ${s.title} opacity-70`}>
              AI 查證結果
            </span>
            <span className={`font-bold text-[15px] ${s.title}`}>
              {s.label}：{result.category || '—'}
            </span>
          </div>
        </div>
        {confPct != null && (
          <div className={`${s.chip} text-xs font-bold px-3 py-1.5 rounded-full shadow-sm`}>
            信心 {confPct}%
          </div>
        )}
      </div>

      <div className="px-4 pb-4 flex flex-col gap-3">
        <div className="bg-white/60 rounded-xl p-3 border border-white/80">
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">查證摘要</h4>
          <p className="text-[14px] font-medium text-slate-800 leading-relaxed">{result.summary}</p>
        </div>

        <div>
          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">詳細解釋</h4>
          <p className="text-[13.5px] text-slate-600 leading-relaxed">{result.explanation}</p>
        </div>

        {result.sources && result.sources.length > 0 && (
          <div className="pt-2 border-t border-black/5">
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">參考來源</h4>
            <div className="flex flex-wrap gap-2">
              {result.sources.map((src, idx) => {
                const isString = typeof src === 'string';
                let url = isString ? src : src.url;
                const title = isString ? '查看來源' : (src.title || '查看來源');
                if (!url) return null;
                if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
                return (
                  <a
                    key={idx}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] text-indigo-700 hover:text-indigo-900 bg-white hover:bg-indigo-50 px-2.5 py-1.5 rounded-lg border border-indigo-100 transition-colors shadow-sm flex items-center gap-1.5 max-w-[220px]"
                    title={title}
                  >
                    <span>🔗</span>
                    <span className="truncate">{title}</span>
                  </a>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TrendingSection() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const pollRef = useRef(null);

  const fetchTrending = useCallback(async () => {
    try {
      const res = await fetch('/api/trending?limit=6');
      if (!res.ok) return;
      const data = await res.json();
      setRecords(data.records || []);
    } catch (e) {
      console.error('Trending fetch error', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrending();
    // Cleanup any active poll on unmount
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchTrending]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch('/api/trending/refresh', { method: 'POST' });
      // Phase 1 saves titles within 2-3s; Phase 2 (AI) updates over 1-2 min.
      let attempts = 0;
      const maxAttempts = 50;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        attempts += 1;
        try {
          const res = await fetch('/api/trending?limit=6');
          if (res.ok) {
            const data = await res.json();
            setRecords(data.records || []);
          }
        } catch {}
        if (attempts >= maxAttempts) {
          setRefreshing(false);
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 3000);
    } catch (e) {
      setRefreshing(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔥</span>
          <span className="font-bold text-slate-800">今日熱門趨勢</span>
          <span className="text-[11px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">AI 每 6 小時更新</span>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-indigo-50 transition-colors disabled:opacity-50"
        >
          {refreshing ? (
            <span className="inline-block w-3 h-3 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
          ) : '↻'} 立即更新
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="p-4 flex flex-col gap-3">
          {[1,2,3].map(i => (
            <div key={i} className="h-14 rounded-xl shimmer" />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="px-4 py-8 text-center text-slate-400 text-sm">
          <div className="text-3xl mb-2">📭</div>
          <div>尚無趨勢資料</div>
          <div className="text-xs mt-1">點「立即更新」觸發 AI 抓取熱門新聞</div>
        </div>
      ) : (
        <div className="divide-y divide-slate-50">
          {records.map((rec, i) => {
            const style = getAiCardStyle(rec.risk_type);
            return (
              <a
                key={rec.id}
                href={rec.source_url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50 transition-colors group"
              >
                <span className="text-slate-300 font-bold text-sm w-5 flex-shrink-0 mt-0.5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] text-slate-800 leading-snug line-clamp-2 group-hover:text-indigo-700 transition-colors">
                    {rec.news_title || rec.ai_summary || rec.source_url}
                  </p>
                  {rec.ai_summary && rec.news_title && rec.ai_summary !== rec.news_title && (
                    <p className="text-[11px] text-slate-500 leading-snug line-clamp-1 mt-0.5">
                      {rec.ai_summary}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${style.chipSmall}`}>
                      {style.shortLabel}
                    </span>
                    {rec.category && (
                      <span className="text-[10px] text-slate-400">{rec.category}</span>
                    )}
                    {rec.ai_score != null && (
                      <span className="text-[10px] text-slate-400">信心 {Math.round(rec.ai_score * 100)}%</span>
                    )}
                  </div>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [posts, setPosts] = useState(initialPosts);
  const [inputText, setInputText] = useState('');
  const [inputMode, setInputMode] = useState('text');  // 'text' | 'url' | 'image'
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Track active poll intervals so we can clean them up on unmount.
  const pollIntervalsRef = useRef(new Set());
  const [isDragActive, setIsDragActive] = useState(false);

  useEffect(() => () => {
    pollIntervalsRef.current.forEach(clearInterval);
    pollIntervalsRef.current.clear();
  }, []);

  const handleImageSelect = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      alert('請選擇圖片檔案');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('圖片大於 10MB，請選小一點');
      return;
    }
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target.result);
    reader.readAsDataURL(file);
  };

  const handlePostSubmit = async () => {
    setIsLoading(true);

    try {
      let apiResult;
      let displayContent;

      if (inputMode === 'image') {
        if (!imageFile) { setIsLoading(false); return; }
        const fd = new FormData();
        fd.append('file', imageFile);
        const response = await fetch('/api/analyze/image', { method: 'POST', body: fd });
        apiResult = await response.json();
        if (!response.ok) throw new Error(apiResult.detail || 'API 請求失敗');
        displayContent = `[已上傳圖片：${imageFile.name}]`;
      } else {
        if (!inputText.trim()) { setIsLoading(false); return; }
        const endpoint = inputMode === 'url' ? '/api/analyze/url' : '/api/analyze/text';
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: inputText })
        });
        apiResult = await response.json();
        if (!response.ok) throw new Error(apiResult.detail || 'API 請求失敗');
        displayContent = inputText;
      }

      const newPostId = Date.now();
      const newPost = {
        id: newPostId,
        author: {
          name: '目前使用者',
          avatar: 'https://ui-avatars.com/api/?name=User&background=E0E7FF&color=4F46E5',
          handle: '@current_user'
        },
        time: '剛剛',
        content: displayContent,
        imagePreview: inputMode === 'image' ? imagePreview : null,
        aiResult: apiResult.task_id ? null : apiResult,
        analyzing: !!apiResult.task_id,
        likes: 0, comments: 0, shares: 0
      };

      setPosts(prev => [newPost, ...prev]);
      setInputText('');
      setImageFile(null);
      setImagePreview(null);

      if (apiResult.task_id) {
        let attempts = 0;
        const maxAttempts = 60;  // 2 minutes total
        const stop = (intervalId) => {
          clearInterval(intervalId);
          pollIntervalsRef.current.delete(intervalId);
        };
        const pollInterval = setInterval(async () => {
          attempts += 1;
          if (attempts > maxAttempts) {
            stop(pollInterval);
            return;
          }
          try {
            const statusRes = await fetch(`/api/analyze/task/${apiResult.task_id}/status`);
            if (!statusRes.ok) return;
            const statusData = await statusRes.json();

            if (statusData.status === 'completed') {
              stop(pollInterval);
              const finalRes = await fetch(`/api/analyze/task/${apiResult.task_id}`);
              const finalData = await finalRes.json();
              setPosts(prev => prev.map(p => p.id === newPostId
                ? { ...p, aiResult: finalData, analyzing: false }
                : p));
            } else if (statusData.status === 'failed') {
              stop(pollInterval);
              setPosts(prev => prev.map(p => p.id === newPostId ? {
                ...p,
                analyzing: false,
                aiResult: {
                  risk_type: 'UNKNOWN', category: '分析失敗',
                  confidence_score: null,
                  summary: 'AI 處理失敗或憑證無效。',
                  explanation: '請檢查後端日誌與 API Key。',
                  sources: []
                }
              } : p));
            }
          } catch (err) {
            console.error('Polling error', err);
          }
        }, 2000);
        pollIntervalsRef.current.add(pollInterval);
      }
    } catch (error) {
      console.error('API Error:', error);
      alert('連線失敗或伺服器錯誤: ' + error.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white text-gray-900">
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200/70 px-4 py-3 flex justify-center">
        <div className="w-full max-w-2xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-black text-sm shadow-sm">
              查
            </div>
            <div className="text-xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-purple-600 tracking-tight">
              全民查證公社
            </div>
          </div>
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center text-indigo-700 font-bold shadow-sm cursor-pointer hover:scale-105 transition-transform border border-white">
            我
          </div>
        </div>
      </nav>

      <main className="w-full max-w-2xl mx-auto flex flex-col pt-6 pb-20 px-4 sm:px-0 gap-5">
        {/* Trending */}
        <TrendingSection />

        {/* Composer */}
        <div className="bg-white rounded-2xl p-4 sm:p-5 shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
          {/* Mode Tabs */}
          <div className="flex gap-1 mb-3 bg-slate-50 p-1 rounded-xl">
            {[
              { key: 'text', label: '文字', icon: '📝' },
              { key: 'url',  label: '網址', icon: '🔗' },
              { key: 'image', label: '圖片', icon: '🖼️' },
            ].map(t => (
              <button
                key={t.key}
                onClick={() => setInputMode(t.key)}
                disabled={isLoading}
                className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  inputMode === t.key
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <span className="mr-1">{t.icon}</span>{t.label}
              </button>
            ))}
          </div>

          <div className="flex gap-3">
            <img
              src="https://ui-avatars.com/api/?name=User&background=E0E7FF&color=4F46E5"
              alt="My Avatar"
              className="w-10 h-10 rounded-full flex-shrink-0 ring-2 ring-white shadow-sm"
            />

            <div className="flex-1">
              {inputMode === 'text' && (
                <textarea
                  className="w-full bg-transparent resize-none outline-none text-[15px] placeholder-slate-400 min-h-[60px] leading-relaxed"
                  placeholder="貼上可疑的訊息、新聞，讓 AI 幫你查證..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  disabled={isLoading}
                />
              )}

              {inputMode === 'url' && (
                <input
                  type="url"
                  className="w-full bg-transparent outline-none text-[15px] placeholder-slate-400 py-3 border-b border-slate-100 focus:border-indigo-300 transition-colors"
                  placeholder="貼上文章網址 https://..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  disabled={isLoading}
                />
              )}

              {inputMode === 'image' && (
                <div>
                  {imagePreview ? (
                    <div className="relative inline-block">
                      <img
                        src={imagePreview}
                        alt="preview"
                        className="max-h-48 rounded-lg shadow-sm border border-slate-200"
                      />
                      <button
                        onClick={() => { setImageFile(null); setImagePreview(null); }}
                        disabled={isLoading}
                        className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-slate-700 text-white text-sm hover:bg-slate-800 shadow-md"
                      >×</button>
                      <div className="text-[11px] text-slate-400 mt-1.5">{imageFile?.name}</div>
                    </div>
                  ) : (
                    <label
                      htmlFor="img-upload"
                      onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
                      onDragLeave={() => setIsDragActive(false)}
                      onDrop={(e) => {
                        e.preventDefault();
                        setIsDragActive(false);
                        if (e.dataTransfer.files[0]) handleImageSelect(e.dataTransfer.files[0]);
                      }}
                      className={`block border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                        isDragActive
                          ? 'border-indigo-400 bg-indigo-50'
                          : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30'
                      }`}
                    >
                      <div className="text-3xl mb-2">📷</div>
                      <div className="text-sm font-medium text-slate-600">點擊或拖曳上傳圖片</div>
                      <div className="text-[11px] text-slate-400 mt-1">支援 PNG / JPG / WEBP，最大 10MB</div>
                      <input
                        id="img-upload"
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => handleImageSelect(e.target.files[0])}
                        disabled={isLoading}
                      />
                    </label>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-between items-center border-t border-slate-100 pt-3 mt-3">
            <div className="text-[12px] text-slate-400 flex items-center gap-1.5">
              <span>✨</span>
              {inputMode === 'image' ? 'AI 將進行 OCR 與圖片內容分析' : 'AI 將進行雙重事實查核'}
            </div>
            <button
              onClick={handlePostSubmit}
              disabled={isLoading ||
                (inputMode === 'image' ? !imageFile : !inputText.trim())}
              className="btn-primary text-white px-5 py-2 rounded-full font-semibold text-sm flex items-center gap-2"
            >
              {isLoading ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  分析中
                </>
              ) : (
                <>發布查證</>
              )}
            </button>
          </div>
        </div>

        {/* Feed */}
        <div className="flex flex-col gap-4">
          {posts.map((post) => (
            <article
              key={post.id}
              className="bg-white rounded-2xl p-4 sm:p-5 shadow-sm border border-slate-100 transition-all hover:shadow-md hover:border-slate-200 fade-in"
            >
              <div className="flex items-center gap-3 mb-3">
                <img
                  src={post.author.avatar}
                  alt={post.author.name}
                  className="w-10 h-10 rounded-full flex-shrink-0 ring-2 ring-white shadow-sm"
                />
                <div className="flex flex-col flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-bold text-slate-900">{post.author.name}</span>
                    <span className="text-slate-400 text-sm">{post.author.handle}</span>
                    <span className="text-slate-300 text-sm hidden sm:inline">·</span>
                    <span className="text-slate-400 text-sm">{post.time}</span>
                  </div>
                </div>
              </div>

              <div className="text-slate-800 text-[15px] leading-relaxed mb-2 whitespace-pre-wrap">
                {post.content}
              </div>

              {post.imagePreview && (
                <img
                  src={post.imagePreview}
                  alt="user upload"
                  className="max-h-64 rounded-lg border border-slate-200 mb-3"
                />
              )}

              {post.analyzing && <AnalyzingCard />}
              {post.aiResult && !post.analyzing && <AiResultCard result={post.aiResult} />}

              <div className="flex items-center justify-between text-slate-400 pt-3 border-t border-slate-100 px-2 sm:px-6">
                <button className="flex items-center gap-2 hover:text-rose-500 transition-colors group p-2 rounded-full hover:bg-rose-50">
                  <span className="text-[16px] group-hover:scale-110 transition-transform">❤️</span>
                  <span className="text-sm font-medium">{post.likes}</span>
                </button>
                <button className="flex items-center gap-2 hover:text-blue-500 transition-colors group p-2 rounded-full hover:bg-blue-50">
                  <span className="text-[16px] group-hover:scale-110 transition-transform">💬</span>
                  <span className="text-sm font-medium">{post.comments}</span>
                </button>
                <button className="flex items-center gap-2 hover:text-emerald-500 transition-colors group p-2 rounded-full hover:bg-emerald-50">
                  <span className="text-[16px] group-hover:scale-110 transition-transform">🔗</span>
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
