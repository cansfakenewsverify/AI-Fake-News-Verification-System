# 02 · Mockup 設計簡報（第 3 站）

> 上游：`00_consensus.md` §5（前端決策）、`01_spec.md` §8（UX 規格，含 8.3 畫面、8.4 狀態表、8.7 文案）。
> 產出：`docs/rebuild/mockup/*.dc.html` + `canvas.json`（設計畫布工作檔），發佈成可點選、可匯出 PNG 的設計畫布給負責人 grill。
> 靜態 mockup（不是可點的 prototype）；每個畫面一個 artboard，狀態另開 artboard 疊放。

## 1. 方向（負責人已選：a）

**淺色、乾淨、黑白為底 + 單一強調色；紅黃綠只出現在判定。手機優先，像 Threads 一樣安靜。**
- 情緒：可信、冷靜、不像政府公文也不像新創 landing page。留白多、線條細、字級大。
- 反面清單（不要）：漸層背景、彩色裝飾圖示、emoji 當圖示、左側彩色邊條卡片、環形儀表盤、深色青綠（舊版）、Inter/Roboto。
- 紅黃綠：只用在「燈號區塊、判定 chip、熱門／知識庫的燈號點」。導覽、按鈕、連結、裝飾一律黑／灰／強調色。

## 2. Token（mockup 定案值；實作時進 `index.css`）

| token | 值 | 用途 |
|---|---|---|
| `--c-bg` | `#FFFFFF` | 頁面底 |
| `--c-surface` | `#F7F7F8` | 卡片／輸入區底（極淡暖灰） |
| `--c-ink` | `#111111` | 主文字、主按鈕底 |
| `--c-ink-2` | `#4B5563` | 次文字（白底對比 7:1） |
| `--c-ink-3` | `#6B7280` | 提示、時間（白底對比 4.8:1；審查後從 #9CA3AF 加深，原值只有 2.5:1） |
| `--c-line` | `#E5E7EB` | 分隔線、卡片邊 |
| `--c-accent` | `#2F4BFF` | 連結、當前分頁、焦點環、次按鈕文字 |
| `--c-accent-soft` | `#EEF1FF` | 選中分頁底、資訊框底 |
| `--c-red` / `--c-red-soft` | `#D92D20` / `#FEF3F2` | 🔴 判定 |
| `--c-yellow` / `--c-yellow-soft` | `#B54708` / `#FEF0C7` | 🟡 判定（文字用深琥珀確保對比） |
| `--c-green` / `--c-green-soft` | `#067647` / `#ECFDF3` | 🟢 判定 |
| `--c-grey` / `--c-grey-soft` | `#6B7280` / `#F2F4F7` | AI 不可用／未查證 chip |
| `--radius-card` | `12px` | 卡片 |
| `--radius-btn` | `10px` | 按鈕、輸入框 |
| `--radius-chip` | `999px` | chip |
| `--shadow-card` | `0 1px 2px rgba(17,17,17,.04)` | 卡片（幾乎看不見） |

字型：`"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif`（mockup 可從 Google Fonts 載 Noto Sans TC 400/500/700 以求顯示一致）。
字級（px／行高）：h1 24/32 700；h2 18/26 700；正文 16/24 400；次文 14/20 400；chip 13/16 500；細字 13/16 400（最小 13px，依 spec 8.6）。
觸控目標：chip 視覺高 28px 可以，但實作時外層 hit area 必須 ≥44px（Main 的範例 chip 已示範外包 44px button）。
間距：頁面左右 16；卡片內距 16；卡片間 12；區塊間 24；觸控目標高 ≥44。

## 3. 元件解剖（所有畫面共用，`Primitives.dc.html` 先做出來，其他 artboard 複製同樣 markup）

1. **頂欄**（56 高）：左「← 返回」或品牌名（16/500）；右主題切換文字鈕「深色」（14，`--c-ink-2`）。底線 1px `--c-line`。
2. **底部分頁列**（手機；56 高 + 安全區 16）：3 格「查證／熱門／知識庫」，圖示 20px 線性 SVG + 12px 文字；當前格 `--c-accent` 文字 + 上緣 2px 線；其餘 `--c-ink-2`。
3. **卡片**：`--c-surface` 底、1px `--c-line` 邊、12px 圓角、16 內距。
4. **主按鈕**：全寬 48 高、`--c-ink` 底白字 16/500、10px 圓角。**次按鈕**：白底 1px `--c-line` 邊、`--c-ink` 文字。**文字鈕**：`--c-accent` 文字。
5. **輸入卡**：頂部模式 tab（3 格分段控制，選中白底黑字有陰影、未選 `--c-ink-2`）；textarea 白底 1px `--c-line`、內距 12、最小 4 行；右下 `0/20000` 細字。
6. **chip**：高 28、內距 0 10、13/500、圓角 999。變體：快取（`--c-accent-soft` 底 `--c-accent` 字）、信心（白底線框）、未查證（`--c-grey-soft` 底 `--c-grey` 字）。
7. **燈號區塊**（結果頁首屏）：全寬區塊、`--c-red-soft`／`-yellow-soft`／`-green-soft`／`-grey-soft` 底、無邊框、上下內距 24；內容：實心圓點 12px（`--c-red` 等）+ `frame_label` 24/700 同色 + 次行 `category_label` 14 `--c-ink-2`；右上 chip 列（信心、快取／即時）。
8. **燈號點列**（熱門、知識庫、最近查證）：8px 實心圓點 + 標題文字；不靠色：圓點旁一律有判定文字（詐騙／假訊息／安全／未查證）。
9. **來源列**：標題 16 `--c-ink` + 網域 13 `--c-ink-3` + 右側外連圖示 16px；每列 ≥44 高、底線 1px。Tier 1／2 來源前加小標「查核機構」或「媒體查核報導」（13，`--c-ink-2`）。
10. **骨架**：`--c-line` 底 8px 圓角條，寬度錯落。
11. **橫幅**（後端不可用）：頂部全寬 `--c-yellow-soft` 底、14 字 `--c-yellow`。
12. **圖示**（線性 SVG，stroke 1.75，20px；不用 emoji）：返回箭頭、外連、複製、分享、搜尋、展開 chevron、資訊 i、清除 ✕、勾 ✓、驚嘆 !。

## 4. 畫面與 artboard 清單（手機框 390 寬；高度依內容，內容底部留 88px 給 sticky 動作列 + 分頁列）

| 檔名 | 內容 | 資料範例 |
|---|---|---|
| `Main.dc.html` | S1 首頁（預設狀態 + 最近查證 3 筆） | 範例 chip 3 個（8.7 `example_1..3`）；最近查證：紅「健保卡停用」、綠「165 專線提醒」、黃「香蕉配優格」 |
| `Result.dc.html` | S2 結果頁・成功（未快取）・🔴 假訊息 | 輸入：「網傳吃香蕉配優格會中毒」；summary 一句；explanation 折疊；來源 2 筆：MyGoPen（查核機構）+ 華視查核報導（媒體）；相似查證 2 筆；動作列 sticky |
| `ResultStates.dc.html` | S2 其他狀態，由上而下疊放 5 張卡：載入骨架＋三步指示／快取命中（🟢 查無異常 + chip 語意相似）／🟡 尚無查核機構證實（SAFE 但 sources=[]）／AI 不可用（灰卡 + 重新查證）／🟡 無法查證（threads 網址提示） | 依 8.3 S2 狀態 1、4、（FR-16）、5、7 |
| `Trending.dc.html` | S3 熱門牆（載入完成，6 張卡，篩選 chip「全部」選中） | 來源只有 MyGoPen／TFC／Cofacts；含 1 張「未查證」灰 chip；`label_source` 小字 |
| `Knowledge.dc.html` | S4 知識庫（搜尋列 + 統計列 + 4 張結果卡 + 載入更多） | 統計：共 184 筆・詐騙 59・假訊息 92・安全 33（示意） |
| `Bot.dc.html` | S6 機器人狀態（最小只讀版，開發模式徽章、狀態卡、dev_mode_notice、最近回覆 2 筆） | 回覆全文照 7.7 模板 |
| `Primitives.dc.html` | 元件表（900 寬桌面框）：token 色票、字級、按鈕三態、chip 四種、燈號區塊四色、來源列、骨架、分頁列、頂欄 | — |
| `DirectionB.dc.html` | 低保真替代方向 B「編輯感」：結果頁一屏，serif 標題（Noto Serif TC）、純黑白、細線分隔、燈號只用文字＋圓點 | 同 Result 資料 |
| `DirectionC.dc.html` | 低保真替代方向 C「親切感」：結果頁一屏，20px 大圓角、柔和 `--c-surface` 大面積、燈號區塊做成大色塊卡 | 同 Result 資料 |

canvas.json：兩頁。`page-1`「畫面」放 Main／Result／Trending／Knowledge／Bot 一列（x 每 470）、ResultStates 第二列；`page-2`「元件與替代方向」放 Primitives、DirectionB、DirectionC。`launch: {view:"canvas", page:"page-1"}`。

## 5. 文案

全部逐字取自 `01_spec.md` 8.7（key 對應）；Threads 回覆文案取 7.7。範例資料可用真實查核標題（MyGoPen／TFC 公開報導標題），來源網域必須是 Tier 1／2（`mygopen.com`、`tfc-taiwan.org.tw`、`cofacts.tw`、`*.gov.tw`、主流媒體查核報導）。不要 lorem ipsum、不要「歡迎使用」。

## 7. grill with mockup 結論（2026-09-15，負責人看過畫布後）

畫布：https://claude.ai/artifact/A4UtUPgSwRCfHAmAKM6TKh

1. **方向定案：A**（淺色、黑白為底、單一強調色、紅黃綠只用在判定）。B／C 不採用。
2. 「結果頁 3 秒看懂燈號＋摘要」：負責人暫不判斷，**移到實作後的 visual review（介面測試 3.3）驗收**，屆時用真手機測。
3. **強調色定案：(a) 墨黑無彩 `#111111`**（2026-09-15 負責人選定；連結加底線辨識）。不用 `#2F4BFF`。mockup 畫布上的藍色僅為舊稿，實作以此為準；值只存在 `--c-accent` 一個 token。
4. 審查留下的兩項由 Claude 依規格定案：
   - chip 視覺高 28px，但可點的 chip（信心、快取、篩選）外層 hit area 必須 ≥44px。
   - `label_source` 在熱門牆與知識庫**一律用 13px 次文字**顯示（不用 chip），兩頁一致。
5. 下一站：ticket（primitives → screens），產出 `docs/rebuild/03_tickets.md`。

## 6. 驗收（reviewer 逐條勾）

1. §4 清單指定的狀態都有對應畫面或疊放卡（mockup 只做「決定方向」所需的主要狀態；8.4 狀態表的每一格由實作階段的 visual review＝介面測試 3.3 逐格驗收，不在 mockup 補齊）。
2. 紅黃綠只出現在 §1 允許的位置；導覽／按鈕沒有紅黃綠。
3. 每個互動元素 ≥44px；正文 ≥15px；chip ≥13px。
4. 不畫假 iOS 狀態列、不畫鍵盤；沒有 emoji 圖示（🔴🟡🟢 只出現在 Bot 畫面的回覆全文與分享文案內）。
5. 所有 artboard 的 token、字級、元件尺寸與 `Primitives.dc.html` 一致（同一份 CSS 變數）。
6. 手機框內無橫向溢出；長網址 `word-break: break-all`。
