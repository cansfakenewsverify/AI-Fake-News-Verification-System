# 2026-10 專題介紹海報

長庚大學資訊工程學系 軟硬體專題「AI 為核心的假訊息驗證系統」（系統名稱：全民查證公社）的兩張介紹海報。
課程規定每組兩張、A1、300 dpi 以上，由學校影印店以油性墨水霧面紙輸出。

## 交給影印店的檔案

| 檔案 | 內容 |
|------|------|
| `海報1_系統介紹.pdf` | 第 1 張，給一般觀眾：摘要、研究動機與目的、使用流程（手機畫面）、Threads 查核機器人、QR code |
| `海報2_技術與成果.pdf` | 第 2 張：系統架構、研究方法、實驗結果、研究限制、結論與未來展望 |
| `海報1_系統介紹_300dpi.png`、`海報2_技術與成果_300dpi.png` | 同內容的點陣圖（7017 × 9933 px、300 dpi），影印店讀不了 PDF 時使用 |
| `preview/` | 低解析度預覽圖 |

列印設定：A1 直式（594 × 841 mm）、原尺寸、不另加邊框。PDF 的文字是向量，放大不會模糊；
手機截圖印在海報上約 300 dpi。

## 內容與數字的出處

| 海報上的內容 | 出處 |
|---|---|
| 150 題評測（漏判 0、誤報 0、無法查證 32） | 2026-10-15，`docs/test/results/prompt_calibration_2026-10-12.md` 第 6 節 |
| 每週新查核自動評測（三週對照） | `docs/test/results/weekly/weekly_eval_2026-10-05.md`、`weekly_eval_2026-10-12.md`、`weekly_eval_2026-10-19.md` |
| 判定校準的 306 題開發組 | `docs/test/results/prompt_calibration_2026-10-12.md` 第 2、6 節 |
| 知識庫 18,745 筆 | 2026-10-21 正式站 `/api/knowledge/stats`（假訊息 18,552＋詐騙 193） |
| 0.2 秒／約 3 秒／4.8 秒 | 測試計畫書 6.4（快取命中）與 2026-10-15 評測（AI 判讀中位數） |
| 自動化測試 1,262 項 | 後端 pytest 853＋前端單元測試 409 |
| 手機畫面 | 2026-10-18 正式站（淺色模式）；三則範例訊息都是快取命中，結果固定 |

QR code 連到：網站首頁、簡報影片、Threads 機器人帳號、GitHub repo。

依負責人 2026-10-18 的決定，不放校徽、不放組別。課程若要求標示組別，加在標頭右上角的標籤（`src/poster.css` 的 `.tag`）。

## 修改與重新輸出

原始檔在 `src/`：`poster1.html`、`poster2.html` 共用 `poster.css`；字型是 Google Fonts 的 Noto Sans TC 與 Noto Serif TC，
輸出時要連網。改完在專案根目錄執行（需要 Python 套件 playwright 與 pymupdf，使用電腦上已安裝的 Microsoft Edge）：

```powershell
python presentations\tools\build_posters.py
python presentations\tools\build_posters.py --preview
```

第一行輸出 PDF、300 dpi PNG 與預覽；加 `--preview` 只輸出 PDF 與預覽，比較快。
腳本會檢查每個區塊放不放得下，內容被切掉時印出 WARNING 與超出的毫米數。
