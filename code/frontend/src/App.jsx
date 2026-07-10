import { useState, useEffect, useRef, useCallback } from 'react';
import { initialPosts, RISK_STYLES, DEFAULT_RISK_STYLE } from './mockData';

const getAiCardStyle = (riskType) => RISK_STYLES[riskType] || DEFAULT_RISK_STYLE;

const AVATAR = 'https://ui-avatars.com/api/?name=Me&background=18212f&color=34dcc4';

// === AI 分析中骨架卡片 ===
function AnalyzingCard() {
  return (
    <div className="mt-3 mb-1 rounded-2xl border border-[var(--c-border)] bg-[var(--c-bg-surface)] overflow-hidden shadow-sm fade-in">
      <div className="h-1 bg-[var(--c-accent)] analyzing-pulse" />
      <div className="p-4 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-[var(--c-accent-soft)] flex items-center justify-center text-xl analyzing-pulse">🤖</div>
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
        <div className="text-[12px] text-[var(--c-text-secondary)] flex items-center gap-1.5">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--c-accent)] animate-ping" />
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
  const confLevel =
    result.confidence_level ||
    (conf == null ? null : conf >= 0.8 ? '高' : conf >= 0.5 ? '中' : '低');
  const confNote = result.confidence_note || '模型自評信心，未經機率校準';

  return (
    <div className={`mt-3 mb-1 rounded-2xl border ${s.wrapper} overflow-hidden shadow-sm fade-in relative`}>
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${s.accent}`} />
      <div className="px-4 pt-3.5 pb-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-xl ${s.iconBg} flex items-center justify-center text-lg shadow-sm`}>{s.icon}</div>
          <div className="flex flex-col">
            <span className={`text-[11px] font-semibold uppercase tracking-wider ${s.title} opacity-70`}>AI 查證結果</span>
            <span className={`font-bold text-[15px] ${s.title}`}>{s.label}：{result.category || '—'}</span>
          </div>
        </div>
        {confLevel != null && (
          <div className={`${s.chip} text-xs font-bold px-3 py-1.5 rounded-full shadow-sm cursor-help`} title={confNote}>
            信心：{confLevel}
          </div>
        )}
      </div>
      <div className="px-4 pb-4 flex flex-col gap-3">
        <div className="bg-[var(--c-bg-input)] rounded-xl p-3 border border-[var(--c-border)]">
          <h4 className="text-[10px] font-bold text-[var(--c-text-muted)] uppercase tracking-widest mb-1">查證摘要</h4>
          <p className="text-[14px] font-medium text-[var(--c-text-primary)] leading-relaxed">{result.summary}</p>
        </div>
        <div>
          <h4 className="text-[10px] font-bold text-[var(--c-text-muted)] uppercase tracking-widest mb-1.5">詳細解釋</h4>
          <p className="text-[13.5px] text-[var(--c-text-secondary)] leading-relaxed">{result.explanation}</p>
        </div>
        {result.sources && result.sources.length > 0 && (
          <div className="pt-2 border-t border-[var(--c-border)]">
            <h4 className="text-[10px] font-bold text-[var(--c-text-muted)] uppercase tracking-widest mb-2">參考來源</h4>
            <div className="flex flex-wrap gap-2">
              {result.sources.map((src, idx) => {
                const isString = typeof src === 'string';
                let url = isString ? src : src.url;
                const title = isString ? '查看來源' : (src.title || '查看來源');
                if (!url) return null;
                if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
                return (
                  <a key={idx} href={url} target="_blank" rel="noopener noreferrer"
                    className="text-[12px] text-[var(--c-accent)] hover:text-[var(--c-accent-strong)] bg-[var(--c-bg-elevated)] hover:bg-[var(--c-accent-soft)] px-2.5 py-1.5 rounded-lg border border-[var(--c-border)] transition-colors shadow-sm flex items-center gap-1.5 max-w-[220px]"
                    title={title}>
                    <span>🔗</span><span className="truncate">{title}</span>
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

// === 共用資訊卡片（資料庫 / 今日熱門共用同一風格）===
function InfoCard({ riskType, title, subtitle, category, metaRight, href, rank }) {
  const s = getAiCardStyle(riskType);
  const inner = (
    <div className={`rounded-2xl border ${s.wrapper} shadow-sm overflow-hidden relative fade-in ${href ? 'hover:shadow-md transition-shadow' : ''}`}>
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${s.accent}`} />
      <div className="p-4 pl-5">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          {rank != null && <span className="text-[var(--c-text-muted)] font-extrabold text-sm">{rank}</span>}
          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md ${s.chip}`}>{s.icon} {s.shortLabel}</span>
          {category && <span className="text-[11px] text-[var(--c-text-secondary)]">{category}</span>}
          {metaRight && <span className="text-[10px] text-[var(--c-text-muted)] ml-auto">{metaRight}</span>}
        </div>
        <p className="text-[14px] text-[var(--c-text-primary)] leading-relaxed line-clamp-3">{title}</p>
        {subtitle && subtitle !== title && (
          <p className="text-[12.5px] text-[var(--c-text-secondary)] leading-snug mt-2 border-t border-[var(--c-border)] pt-2 line-clamp-2">{subtitle}</p>
        )}
        {href && <span className="inline-flex items-center gap-1 text-[12px] text-[var(--c-accent)] mt-2">🔗 查看來源</span>}
      </div>
    </div>
  );
  return href
    ? <a href={href} target="_blank" rel="noopener noreferrer" className="block">{inner}</a>
    : inner;
}

const confLabel = (v) => v == null ? null : (v >= 0.8 ? '高' : v >= 0.5 ? '中' : '低');

// === 今日熱門趨勢 ===
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
    } catch (e) { console.error('Trending fetch error', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchTrending();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchTrending]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch('/api/trending/refresh', { method: 'POST' });
      let attempts = 0;
      const maxAttempts = 50;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        attempts += 1;
        try {
          const res = await fetch('/api/trending?limit=6');
          if (res.ok) setRecords((await res.json()).records || []);
        } catch {}
        if (attempts >= maxAttempts) {
          setRefreshing(false);
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 3000);
    } catch (e) { setRefreshing(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="bg-[var(--c-bg-surface)] rounded-2xl border border-[var(--c-border)] shadow-sm px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔥</span>
          <span className="font-bold text-[var(--c-text-primary)]">今日熱門趨勢</span>
          <span className="text-[11px] text-[var(--c-text-muted)] bg-[var(--c-bg-elevated)] px-2 py-0.5 rounded-full">AI 每 6 小時更新</span>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}
          className="text-xs text-[var(--c-accent)] hover:text-[var(--c-accent-strong)] flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-[var(--c-accent-soft)] transition-colors disabled:opacity-50 font-medium">
          {refreshing
            ? <span className="inline-block w-3 h-3 border-2 border-[var(--c-accent-line)] border-t-[var(--c-accent)] rounded-full animate-spin" />
            : '↻'} 立即更新
        </button>
      </div>
      {/* Items（與資料庫同款卡片）*/}
      {loading ? (
        <div className="flex flex-col gap-3">{[1,2,3].map(i => <div key={i} className="h-20 rounded-2xl shimmer" />)}</div>
      ) : records.length === 0 ? (
        <div className="bg-[var(--c-bg-surface)] rounded-2xl border border-[var(--c-border)] shadow-sm px-4 py-8 text-center text-[var(--c-text-muted)] text-sm">
          <div className="text-3xl mb-2">📭</div>
          <div>尚無趨勢資料</div>
          <div className="text-xs mt-1">點「立即更新」觸發 AI 抓取熱門新聞</div>
        </div>
      ) : (
        records.map((rec, i) => (
          <InfoCard
            key={rec.id}
            rank={i + 1}
            riskType={rec.risk_type}
            title={rec.news_title || rec.ai_summary || rec.source_url}
            subtitle={rec.ai_summary && rec.ai_summary !== rec.news_title ? rec.ai_summary : null}
            category={rec.category}
            metaRight={rec.ai_score != null ? `信心：${confLabel(rec.ai_score)}` : null}
            href={rec.source_url || null}
          />
        ))
      )}
    </div>
  );
}

// === 資料庫內容檢視 / 查找 ===
const RISK_FILTERS = [
  { key: '', label: '全部' },
  { key: 'SCAM', label: '詐騙' },
  { key: 'MISINFO', label: '假訊息' },
  { key: 'SAFE', label: '安全' },
];

function KnowledgeSection() {
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState({ total: 0, by_risk: {} });
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async (q = '', rt = '') => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (q) params.set('q', q);
      if (rt) params.set('risk_type', rt);
      const [listRes, statsRes] = await Promise.all([
        fetch('/api/knowledge?' + params.toString()),
        fetch('/api/knowledge/stats'),
      ]);
      if (listRes.ok) setRecords((await listRes.json()).records || []);
      if (statsRes.ok) setStats(await statsRes.json());
    } catch (e) { console.error('knowledge fetch error', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const onSearch = (e) => { e.preventDefault(); fetchData(query.trim(), filter); };
  const onFilter = (rt) => { const nf = filter === rt ? '' : rt; setFilter(nf); fetchData(query.trim(), nf); };

  return (
    <div className="flex flex-col gap-4">
      {/* 標題 + 統計 */}
      <div className="bg-[var(--c-bg-surface)] rounded-2xl border border-[var(--c-border)] shadow-sm p-4 sm:p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">🗂️</span>
          <span className="font-bold text-[var(--c-text-primary)]">查證資料庫</span>
          <span className="text-[11px] text-[var(--c-text-muted)] bg-[var(--c-bg-elevated)] px-2 py-0.5 rounded-full">已快取 {stats.total} 筆</span>
        </div>
        {/* 統計小卡 */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          {['SCAM','MISINFO','SAFE'].map(rt => {
            const st = getAiCardStyle(rt);
            return (
              <div key={rt} className={`rounded-xl px-3 py-2 border ${st.wrapper} flex flex-col`}>
                <span className={`text-[11px] font-semibold ${st.title} opacity-80`}>{st.icon} {st.shortLabel}</span>
                <span className={`text-xl font-extrabold ${st.title}`}>{stats.by_risk?.[rt] || 0}</span>
              </div>
            );
          })}
        </div>
        {/* 搜尋 */}
        <form onSubmit={onSearch} className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜尋已查證的內容或摘要..."
            className="flex-1 bg-[var(--c-bg-input)] border border-[var(--c-border)] rounded-xl px-3.5 py-2.5 text-sm text-[var(--c-text-primary)] placeholder-[var(--c-text-muted)] outline-none focus:border-[var(--c-accent)] transition-colors"
          />
          <button type="submit" className="btn-primary px-4 py-2 rounded-xl font-semibold text-sm">搜尋</button>
        </form>
        {/* 篩選 */}
        <div className="flex gap-2 mt-3">
          {RISK_FILTERS.map(f => (
            <button key={f.key} onClick={() => onFilter(f.key)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                filter === f.key
                  ? 'bg-[var(--c-accent)] text-[var(--c-accent-ink)] border-[var(--c-accent)]'
                  : 'bg-[var(--c-bg-elevated)] text-[var(--c-text-secondary)] border-[var(--c-border)] hover:border-[var(--c-accent-line)]'
              }`}>{f.label}</button>
          ))}
        </div>
      </div>

      {/* 結果列表 */}
      {loading ? (
        <div className="flex flex-col gap-3">{[1,2,3,4].map(i => <div key={i} className="h-24 rounded-2xl shimmer" />)}</div>
      ) : records.length === 0 ? (
        <div className="bg-[var(--c-bg-surface)] rounded-2xl border border-[var(--c-border)] shadow-sm px-4 py-12 text-center text-[var(--c-text-muted)]">
          <div className="text-4xl mb-2">🔍</div>
          <div className="text-sm">找不到符合的資料</div>
          <div className="text-xs mt-1">換個關鍵字，或先送出幾筆查證</div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {records.map((rec, i) => {
            return (
              <InfoCard key={i}
                riskType={rec.risk_type}
                title={rec.raw_content}
                subtitle={rec.summary}
                category={rec.category}
                metaRight={rec.hit_count > 0 ? `命中 ${rec.hit_count} 次` : null}
                href={rec.source_url || null}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// === 主應用 ===
export default function App() {
  const [view, setView] = useState('feed');  // 'feed' | 'db'
  const [posts, setPosts] = useState(initialPosts);
  const [inputText, setInputText] = useState('');
  const [inputMode, setInputMode] = useState('text');  // 'text' | 'url' | 'image'
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const pollIntervalsRef = useRef(new Set());
  const [isDragActive, setIsDragActive] = useState(false);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('factscan_theme') || 'dark'; } catch { return 'dark'; }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('factscan_theme', theme); } catch {}
  }, [theme]);

  useEffect(() => () => {
    pollIntervalsRef.current.forEach(clearInterval);
    pollIntervalsRef.current.clear();
  }, []);

  const handleImageSelect = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) { alert('請選擇圖片檔案'); return; }
    if (file.size > 10 * 1024 * 1024) { alert('圖片大於 10MB，請選小一點'); return; }
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target.result);
    reader.readAsDataURL(file);
  };

  const handlePostSubmit = async () => {
    setIsLoading(true);
    try {
      let apiResult, displayContent;
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
        author: { name: '我', avatar: AVATAR, handle: '@me' },
        time: '剛剛',
        content: displayContent,
        imagePreview: inputMode === 'image' ? imagePreview : null,
        aiResult: apiResult.task_id ? null : apiResult,
        analyzing: !!apiResult.task_id,
      };

      setPosts(prev => [newPost, ...prev]);
      setInputText('');
      setImageFile(null);
      setImagePreview(null);

      if (apiResult.task_id) {
        let attempts = 0;
        const maxAttempts = 60;
        const stop = (id) => { clearInterval(id); pollIntervalsRef.current.delete(id); };
        const pollInterval = setInterval(async () => {
          attempts += 1;
          if (attempts > maxAttempts) { stop(pollInterval); return; }
          try {
            const statusRes = await fetch(`/api/analyze/task/${apiResult.task_id}/status`);
            if (!statusRes.ok) return;
            const statusData = await statusRes.json();
            if (statusData.status === 'completed') {
              stop(pollInterval);
              const finalData = await (await fetch(`/api/analyze/task/${apiResult.task_id}`)).json();
              setPosts(prev => prev.map(p => p.id === newPostId ? { ...p, aiResult: finalData, analyzing: false } : p));
            } else if (statusData.status === 'failed') {
              stop(pollInterval);
              setPosts(prev => prev.map(p => p.id === newPostId ? {
                ...p, analyzing: false,
                aiResult: { risk_type: 'UNKNOWN', category: '分析失敗', confidence_score: null,
                  summary: 'AI 處理失敗或憑證無效。', explanation: '請檢查後端日誌與 API Key。', sources: [] }
              } : p));
            }
          } catch (err) { console.error('Polling error', err); }
        }, 2000);
        pollIntervalsRef.current.add(pollInterval);
      }
    } catch (error) {
      console.error('API Error:', error);
      alert('連線失敗或伺服器錯誤: ' + error.message);
    } finally { setIsLoading(false); }
  };

  return (
    <div className="min-h-screen app-bg text-[var(--c-text-primary)]">
      {/* 頂部導覽 */}
      <nav className="sticky top-0 z-50 bg-[var(--c-topbar-bg)] backdrop-blur-xl border-b border-[var(--c-border)] px-4">
        <div className="w-full max-w-2xl mx-auto">
          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[var(--c-accent-soft)] flex items-center justify-center text-[var(--c-accent)] font-black shadow-sm ring-1 ring-[var(--c-accent-line)]">查</div>
              <div className="text-[19px] font-extrabold text-[var(--c-text-primary)] tracking-tight">全民查證公社</div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
                className="w-9 h-9 rounded-xl bg-[var(--c-bg-surface)] border border-[var(--c-border)] flex items-center justify-center text-[15px] text-[var(--c-text-secondary)] hover:border-[var(--c-accent-line)] hover:text-[var(--c-text-primary)] transition-colors"
                aria-label="切換深色／淺色主題" title="切換主題">
                {theme === 'light' ? '☀️' : '🌙'}
              </button>
              <div className="w-9 h-9 rounded-full bg-[var(--c-accent-soft)] flex items-center justify-center text-[var(--c-accent)] font-bold shadow-sm cursor-pointer hover:scale-105 transition-transform ring-1 ring-[var(--c-border)]">我</div>
            </div>
          </div>
          {/* 視圖切換 */}
          <div className="flex gap-1">
            {[
              { key: 'feed', label: '查證', icon: '🔎' },
              { key: 'db', label: '資料庫', icon: '🗂️' },
            ].map(t => (
              <button key={t.key} onClick={() => setView(t.key)}
                className={`relative px-4 py-2.5 text-sm font-semibold transition-colors ${
                  view === t.key ? 'text-[var(--c-accent)]' : 'text-[var(--c-text-muted)] hover:text-[var(--c-text-secondary)]'
                }`}>
                <span className="mr-1">{t.icon}</span>{t.label}
                {view === t.key && <span className="absolute left-2 right-2 -bottom-px h-0.5 rounded-full bg-[var(--c-accent)]" />}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <main className="w-full max-w-2xl mx-auto flex flex-col pt-5 pb-24 px-4 sm:px-0 gap-5">
        {view === 'db' ? (
          <KnowledgeSection />
        ) : (
          <>
            <TrendingSection />

            {/* 查證輸入框 */}
            <div className="bg-[var(--c-bg-surface)] rounded-2xl p-4 sm:p-5 shadow-sm border border-[var(--c-border)] hover:shadow-md transition-shadow">
              <div className="flex gap-1 mb-3 bg-[var(--c-bg-input)] p-1 rounded-xl">
                {[
                  { key: 'text', label: '文字', icon: '📝' },
                  { key: 'url', label: '網址', icon: '🔗' },
                  { key: 'image', label: '圖片', icon: '🖼️' },
                ].map(t => (
                  <button key={t.key} onClick={() => setInputMode(t.key)} disabled={isLoading}
                    className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      inputMode === t.key ? 'bg-[var(--c-bg-elevated)] text-[var(--c-accent)] shadow-sm' : 'text-[var(--c-text-muted)] hover:text-[var(--c-text-secondary)]'
                    }`}>
                    <span className="mr-1">{t.icon}</span>{t.label}
                  </button>
                ))}
              </div>

              <div className="flex gap-3">
                <img src={AVATAR} alt="me"
                  className="w-10 h-10 rounded-full flex-shrink-0 ring-1 ring-[var(--c-border)] shadow-sm" />
                <div className="flex-1">
                  {inputMode === 'text' && (
                    <textarea
                      className="w-full bg-transparent resize-none outline-none text-[15px] text-[var(--c-text-primary)] placeholder-[var(--c-text-muted)] min-h-[60px] leading-relaxed"
                      placeholder="貼上可疑的訊息、新聞，讓 AI 幫你查證..."
                      value={inputText} onChange={(e) => setInputText(e.target.value)} disabled={isLoading} />
                  )}
                  {inputMode === 'url' && (
                    <input type="url"
                      className="w-full bg-transparent outline-none text-[15px] text-[var(--c-text-primary)] placeholder-[var(--c-text-muted)] py-3 border-b border-[var(--c-border)] focus:border-[var(--c-accent)] transition-colors"
                      placeholder="貼上文章網址 https://..."
                      value={inputText} onChange={(e) => setInputText(e.target.value)} disabled={isLoading} />
                  )}
                  {inputMode === 'image' && (
                    <div>
                      {imagePreview ? (
                        <div className="relative inline-block">
                          <img src={imagePreview} alt="preview" className="max-h-48 rounded-lg shadow-sm border border-[var(--c-border)]" />
                          <button onClick={() => { setImageFile(null); setImagePreview(null); }} disabled={isLoading}
                            className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-[var(--c-bg-elevated)] text-[var(--c-text-primary)] text-sm hover:bg-[var(--c-border-strong)] shadow-md border border-[var(--c-border)]">×</button>
                          <div className="text-[11px] text-[var(--c-text-muted)] mt-1.5">{imageFile?.name}</div>
                        </div>
                      ) : (
                        <label htmlFor="img-upload"
                          onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
                          onDragLeave={() => setIsDragActive(false)}
                          onDrop={(e) => { e.preventDefault(); setIsDragActive(false); if (e.dataTransfer.files[0]) handleImageSelect(e.dataTransfer.files[0]); }}
                          className={`block border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                            isDragActive ? 'border-[var(--c-accent)] bg-[var(--c-accent-soft)]' : 'border-[var(--c-border)] hover:border-[var(--c-accent-line)] hover:bg-[var(--c-bg-input)]'
                          }`}>
                          <div className="text-3xl mb-2">📷</div>
                          <div className="text-sm font-medium text-[var(--c-text-secondary)]">點擊或拖曳上傳圖片</div>
                          <div className="text-[11px] text-[var(--c-text-muted)] mt-1">支援 PNG / JPG / WEBP，最大 10MB</div>
                          <input id="img-upload" type="file" accept="image/*" className="hidden"
                            onChange={(e) => handleImageSelect(e.target.files[0])} disabled={isLoading} />
                        </label>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-between items-center border-t border-[var(--c-border)] pt-3 mt-3">
                <div className="text-[12px] text-[var(--c-text-muted)] flex items-center gap-1.5">
                  <span>✨</span>
                  {inputMode === 'image' ? 'AI 將進行 OCR 與圖片內容分析' : 'AI 將進行雙重事實查核'}
                </div>
                <button onClick={handlePostSubmit}
                  disabled={isLoading || (inputMode === 'image' ? !imageFile : !inputText.trim())}
                  className="btn-primary px-5 py-2 rounded-full font-semibold text-sm flex items-center gap-2">
                  {isLoading
                    ? (<><span className="inline-block w-3 h-3 border-2 border-[var(--c-accent-ink)]/30 border-t-[var(--c-accent-ink)] rounded-full animate-spin" />分析中</>)
                    : (<>發布查證</>)}
                </button>
              </div>
            </div>

            {/* 結果列表 */}
            {posts.length === 0 ? (
              <div className="bg-[var(--c-bg-surface)] rounded-2xl border border-[var(--c-border)] shadow-sm px-4 py-12 text-center text-[var(--c-text-muted)]">
                <div className="text-4xl mb-2">📝</div>
                <div className="text-sm font-medium text-[var(--c-text-secondary)]">還沒有查證紀錄</div>
                <div className="text-xs mt-1">在上方貼上可疑訊息、網址或圖片，AI 會幫你判斷真偽</div>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {posts.map((post) => (
                  <article key={post.id}
                    className="bg-[var(--c-bg-surface)] rounded-2xl p-4 sm:p-5 shadow-sm border border-[var(--c-border)] transition-all hover:shadow-md hover:border-[var(--c-border-strong)] fade-in">
                    <div className="flex items-center gap-3 mb-3">
                      <img src={post.author.avatar} alt={post.author.name} className="w-10 h-10 rounded-full flex-shrink-0 ring-1 ring-[var(--c-border)] shadow-sm" />
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-bold text-[var(--c-text-primary)]">{post.author.name}</span>
                        <span className="text-[var(--c-text-muted)] text-sm">{post.author.handle}</span>
                        <span className="text-[var(--c-text-muted)] text-sm">·</span>
                        <span className="text-[var(--c-text-muted)] text-sm">{post.time}</span>
                      </div>
                    </div>
                    <div className="text-[var(--c-text-primary)] text-[15px] leading-relaxed mb-2 whitespace-pre-wrap">{post.content}</div>
                    {post.imagePreview && <img src={post.imagePreview} alt="upload" className="max-h-64 rounded-lg border border-[var(--c-border)] mb-3" />}
                    {post.analyzing && <AnalyzingCard />}
                    {post.aiResult && !post.analyzing && <AiResultCard result={post.aiResult} />}
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
