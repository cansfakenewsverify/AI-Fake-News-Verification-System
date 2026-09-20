// Builds the two course forms — 學生自評表 and 評分表 — from ONE shared definition, so they come
// out in the same format as each other and as the originals.
//
// Usage:
//   node presentations/tools/build_course_forms.mjs
//   node code/frontend/tools/html_to_pdf.mjs "presentations/2026-09_進度報告/09_學生自評表_已填.html" "presentations/2026-09_進度報告/09_學生自評表_已填.pdf"
//   node code/frontend/tools/html_to_pdf.mjs "presentations/2026-09_進度報告/11_評分表_已填表頭.html" "presentations/2026-09_進度報告/11_評分表_已填表頭.pdf"
//
// The nine competencies, their four level descriptions, the score bands, the instruction lines and
// the SDG list are TRANSCRIBED VERBATIM from the blank forms the advisor issued
// (docs/course_forms/*.pdf, IEET 20230317). Do not paraphrase them — the wording is what the
// accreditation review reads. Only 團隊成員 / 指導教授 / 專題名稱, the chosen level and the
// 說明 text are ours.
//
// The 評分表 deliberately leaves 分數 and the level choice blank: those are the reviewing
// teacher's, not ours. We fill only the header and the SDG tick, which describe the project.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const DIR = path.join(REPO, "presentations", "2026-09_進度報告");

const HEAD = {
  team: "廖晢勛、石岱勳、姚睿、張宇宏、廖育翔",
  advisor: "黃崇源",
  title: "AI 為核心的假訊息驗證系統（系統名稱：全民查證公社）",
};

const BANDS = ["仍需加強(60 分以下)", "尚可(60-70 分)", "佳(71-85 分)", "優秀(86-100 分)"];

/** level: 1–4, the level this team selects on the self-evaluation. */
const ITEMS = [
  {
    n: 1,
    name: "運用資工領域、數學、科學及工程知識之能力",
    levels: [
      "未能運用資訊技術於專題實作",
      "已能運用資訊技術於專題實作，但使用之資訊技術過於簡單",
      "能充分運用資訊技術於專題實作，且專題具有創新性，但專題內容仍有可改進之處",
      "能充分運用資訊技術於專題實作，且專題具創新性，並能完整實作",
    ],
    level: 4,
    note:
      "整合 React、FastAPI、PostgreSQL 與 pgvector 向量檢索及大型語言模型，完成可公開使用的查證網站"
      + "（https://fakenewsverify.vercel.app，2026-09-19 起上線運作，不需要任何人開著電腦）。"
      + "創新處在於「三層快取」判讀流程：內容雜湊比對 → 語意向量比對 → 才呼叫 AI；"
      + "相似度門檻 0.75 由實測校準（同一謠言的改寫版 0.79–0.82、不同謠言 ≤ 0.68），"
      + "使重複出現的謠言不必重複呼叫模型。系統已完整實作並對外運作。",
  },
  {
    n: 2,
    name: "發掘、分析及處理資訊系統運作問題的能力",
    levels: [
      "專題議題缺乏重要性",
      "專題議題之重要性不足",
      "專題議題具重要性，但專題實作內容仍有可持續改進之處",
      "專題議題具重要性，且專題內容具有優秀的成果",
    ],
    level: 3,
    note:
      "假訊息與詐騙查證具社會重要性。我們把「怎樣才算可信」當成需求來分析，訂出只採計已做出判定的"
      + "查核來源、找不到就標示「尚無查核機構證實」而且不給綠燈的規則。仍有可持續改進之處："
      + "語意快取命中率 65%，未達自訂的 70% 準則；雲端知識庫 128 筆中有 24 筆的來源標記需重新檢視。"
      + "兩項都已列入下一期工作，不以調低準則的方式掩蓋。",
  },
  {
    n: 3,
    name: "設計與執行資訊系統實驗，與分析實驗數據之能力",
    levels: [
      "無法使用資訊系統進行實驗或不具有分析實驗數據的能力",
      "能使用資訊系統進行實驗，但不具有分析實驗數據的能力",
      "能使用資訊系統進行實驗，且具有分析實驗數據的能力，但不夠精熟",
      "能精熟使用資訊系統進行實驗，且具有優秀分析實驗數據的能力",
    ],
    level: 3,
    note:
      "自建 150 筆標註資料集（詐騙、假訊息、安全各 50，並刻意放入「看起來像詐騙的合法官方訊息」"
      + "作為難題）進行評測：前一版模型準確率 96.0%（誤報 5、漏判 0），現行模型 100%（誤報 0、漏判 0），"
      + "並以精確 McNemar 檢定比較兩版差異（p = 0.031）。另量測三層快取的延遲："
      + "雜湊命中 213 ms、向量命中 3.06 秒、AI 判讀 9–27 秒。分析上仍不夠精熟：150 筆對現行模型已飽和"
      + "（準確率 95% 信賴區間下限 0.976），無法再區分模型或設定之間的差異，需擴充資料集並做信心校準。",
  },
  {
    n: 4,
    name: "運用適當工具、儀器與現存模組執行資訊系統軟硬體開發之能力",
    levels: [
      "未使用任何工具、儀器與現存模組進行資訊系統軟硬體開發",
      "能使用工具、儀器與現存模組進行資訊系統軟硬體開發，但未能選擇適當的工具、儀器與現存模組",
      "能使用正確的工具、儀器與現存模組進行資訊系統軟硬體開發，但使用技巧可持續加強",
      "能使用正確的工具、儀器與現存模組進行資訊系統軟硬體開發，且使用技巧精熟",
    ],
    level: 4,
    note:
      "使用 Git 與 GitHub Actions（每次提交自動執行後端 700 項、前端 385 項測試）、Vercel、Render、"
      + "Supabase 與 pgvector、長庚 CGU AIR 模型閘道；並以無頭瀏覽器自動擷取介面測試截圖與錄製簡報影片，"
      + "使測試與展示素材都能重現。開發過程使用 AI 程式開發助理協助，並在測試計畫書中具名揭露其分工"
      + "與人工判斷的界線。",
  },
  {
    n: 5,
    name: "規劃、建立資訊系統測試環境，及執行測試與結果分析之專案管理能力",
    levels: [
      "無法規劃系統測試項目",
      "能規劃系統測試，但無法順利執行測試內容或呈現結果",
      "能規劃系統測試，亦可順利執行測試內容或呈現結果，但測試面向仍有不足待修正之處",
      "能規劃系統測試，測試面向完整，亦可順利執行測試內容並呈現結果",
    ],
    level: 3,
    note:
      "依課程格式撰寫測試計畫書 TP-FNV-2026-01（5 類 46 項，含通過準則、中止與再繼續規則），"
      + "並將實作拆成 109 張票管理。已執行兩輪：第一輪 P0 通過 23／30，修正缺陷後重測 27／30，"
      + "缺陷 DEF-01～DEF-09 逐項記錄原因與修正。測試面向仍有不足："
      + "PF-2 語意快取命中率未達準則，UI-6、PF-1、OP-1 三項因需另外安裝的工具或另備環境尚未執行，"
      + "均已列出原因與補做時程。",
  },
  {
    n: 6,
    name: "具備撰寫與運用資訊系統設計文件之能力",
    levels: [
      "未繳交口頭報告投影片或期末專題報告",
      "有繳交口頭報告投影片與期末專題報告，但內容空乏",
      "有繳交口頭報告投影片與期末專題報告，內容完整但仍有可改進之處",
      "有繳交口頭報告投影片與期末專題報告，內容完整且清楚詳實",
    ],
    level: 4,
    note:
      "文件鏈完整且可回溯：共識文件 → 功能與 UX 規格書 v1.3（19 條功能需求與測試通過準則）→ "
      + "介面設計稿 → 實作票 109 張 → 測試計畫書 → 雲端部署手冊，全部放在版本庫的 docs/ 之下，"
      + "每一項實作與測試都能對應到文件條目。本次繳交書面報告與 4 分 38 秒的簡報影片"
      + "（附字幕與逐段旁白稿）；README 與專案說明隨程式同步維護。",
  },
  {
    n: 7,
    name: "具備有效溝通與合作之能力",
    levels: [
      "單一組員且缺乏與指導教授溝通專題進度",
      "單一組員但能夠與專題教授溝通專題進度，並完成各項專題工作;多組員但缺少分工合作，無法完成各項專題工作",
      "多組員且能分工合作完成各項專題工作，但相處不融洽",
      "多組員且能分工合作完成各項專題工作，且相處融洽",
    ],
    level: 4,
    note:
      "五人分工明確：廖晢勛（測試負責人、系統實作與部署）、石岱勳（介面測試）、姚睿（績效與品質數據）、"
      + "張宇宏（文件與審查）、廖育翔（影片與簡報）。以 GitHub 與共用報告資料夾協作，"
      + "介面檢核由非實作組員勾核、另一位組員覆核，避免自己檢查自己。"
      + "與指導教授持續溝通進度，各項工作均如期完成，合作過程順利融洽。",
  },
  {
    n: 8,
    name: "理解資訊倫理與社會責任",
    levels: [
      "缺乏資訊倫理(如隱私權、網路倫理、資訊精確性等)與資訊安全的相關知識",
      "能具有基本資訊倫理(如隱私權、網路倫理、資訊精確性等)與資訊安全的基本知識",
      "能具有基本資訊倫理(如隱私權、網路倫理、資訊精確性等)與資訊安全的基本知識，專題內容也能考量到資訊倫理與資訊安全的影響",
      "能具有基本資訊倫理((如隱私權、網路倫理、資訊精確性等))與資訊安全的基本知識，專題內容亦加入資訊倫理與資訊安全的相關實作",
    ],
    level: 4,
    note:
      "倫理面已落實為功能：不引用未經查核的來源，沒有來源就標示「尚無查核機構證實」且不給綠燈；"
      + "每一頁都標示判讀由 AI 自動產生、僅供參考；提供隱私政策與資料刪除說明；不需登入，"
      + "查詢紀錄只留在使用者自己的瀏覽器，也不把使用者輸入送到搜尋引擎。"
      + "資訊安全面則有實作：對使用者提供的網址一律經 SSRF 防護後才連線、每個 IP 的頻率限制、"
      + "請求與上傳大小上限、圖片檔頭檢查、每日 AI 呼叫上限，管理端點需權杖；"
      + "金鑰只存在本機設定檔與雲端後台，不進公開的版本庫。",
  },
  {
    n: 9,
    name: "瞭解資訊工程技術對環境永續、社會共好及全球發展的影響，並培養持續學習的習慣與能力",
    levels: [
      "專題內容與任一 SDG 均無關",
      "專題內容能夠考量到與 SDG 間的關聯性",
      "專題內容與一項 SDG 有關",
      "專題內容涵蓋多項 SDG",
    ],
    level: 3,
    note:
      "對應 SDG 16「和平、正義及健全制度」：以可查證的判定與明確的來源揭露，"
      + "減少詐騙與假訊息對民眾造成的傷害，建立具公信力的資訊查證管道。"
      + "另以三層快取減少重複的 AI 運算；團隊於過程中自學雲端部署、向量資料庫與大型語言模型評測方法。",
  },
];

const SDGS = [
  "無相關",
  "SDG 1 終結貧窮：消除各地一切形式的貧窮",
  "SDG 2 消除飢餓：確保糧食安全，消除飢餓，促進永續農業",
  "SDG 3 健康與福祉：確保及促進各年齡層健康生活與福祉",
  "SDG 4 優質教育：確保有教無類、公平以及高品質的教育，及提倡終身學習",
  "SDG 5 性別平權：實現性別平等，並賦予婦女權力",
  "SDG 6 淨水及衛生：確保所有人都能享有水、衛生及其永續管理",
  "SDG 7 可負擔的潔淨能源：確保所有的人都可取得負擔得起、可靠、永續及現代的能源",
  "SDG 8 合適的工作及經濟成長：促進包容且永續的經濟成長，讓每個人都有一份好工作",
  "SDG 9 工業化、創新及基礎建設：建立具有韌性的基礎建設，促進包容且永續的工業，並加速創新",
  "SDG 10 減少不平等：減少國內及國家間的不平等",
  "SDG 11 永續城鄉：建構具包容、安全、韌性及永續特質的城市與鄉村",
  "SDG 12 責任消費及生產：促進綠色經濟，確保永續消費及生產模式",
  "SDG 13 氣候行動：完備減緩調適行動，以因應氣候變遷及其影響",
  "SDG 14 保育海洋生態：保育及永續利用海洋生態系，以確保生物多樣性並防止海洋環境劣化",
  "SDG 15 保育陸域生態：保育及永續利用陸域生態系，確保生物多樣性並防止土地劣化",
  "SDG 16 和平、正義及健全制度：促進和平多元的社會，確保司法平等，建立具公信力且廣納民意的體系",
  "SDG 17 多元夥伴關係：建立多元夥伴關係，協力促進永續願景",
];
const SDG_TICKED = 17; // index into SDGS — SDG 16

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const CSS = `
  @page { size: A4; margin: 14mm 13mm 13mm 13mm; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif;
         color: #000; font-size: 10pt; line-height: 1.45; }
  h1 { font-size: 15pt; text-align: center; margin: 0 0 3mm; letter-spacing: 0.04em; }
  table { width: 100%; border-collapse: collapse; }
  .hd td { border: 0.35mm solid #000; padding: 1.6mm 2mm; font-size: 10pt; }
  .hd .k { width: 22mm; font-weight: 700; background: #f0f0f0; text-align: center; }
  .lead { margin: 3mm 0 2mm; font-size: 10pt; }
  .item { margin-top: 3.5mm; }
  .item > table { border: 0.35mm solid #000; }
  .qh td { border: 0.35mm solid #000; padding: 1.5mm 2mm; font-weight: 700; font-size: 10.5pt; background: #ededed; }
  .band td { border: 0.35mm solid #000; padding: 1.2mm 1.6mm; text-align: center;
             font-size: 9pt; font-weight: 700; background: #f7f7f7; }
  .lv td { border: 0.35mm solid #000; padding: 1.8mm 1.8mm; width: 25%; vertical-align: top;
           font-size: 8.8pt; line-height: 1.4; }
  .lv td.on { box-shadow: inset 0 0 0 0.7mm #000; background: #f2f2f2; font-weight: 700; }
  .pick { display: block; font-size: 8pt; font-weight: 700; margin-bottom: 1mm; letter-spacing: 0.04em; }
  .act td { border: 0.35mm solid #000; padding: 1.5mm 2mm; font-size: 9.5pt; }
  .note td { border: 0.35mm solid #000; padding: 2mm; font-size: 9pt; line-height: 1.5; vertical-align: top; }
  .note b { font-weight: 700; }
  .sdg { margin-top: 4mm; }
  .sdg .t { font-weight: 700; margin-bottom: 1.5mm; font-size: 10pt; }
  .sdg ul { list-style: none; margin: 0; padding: 0; }
  .sdg li { font-size: 8.8pt; line-height: 1.55; }
  .sdg li .box { display: inline-block; width: 3.2mm; height: 3.2mm; border: 0.3mm solid #000;
                 margin-right: 1.6mm; vertical-align: -0.3mm; text-align: center; line-height: 3mm; font-size: 7pt; }
  .sdg li.on { font-weight: 700; }
  .sdg li.on .box { background: #000; color: #fff; }
  .adv { margin-top: 4mm; }
  .adv td { border: 0.35mm solid #000; padding: 2mm; font-size: 10pt; }
  .adv .tall { height: 62mm; vertical-align: top; }
  .brk { page-break-before: always; }
  .item, .sdg li { break-inside: avoid; }
`;

function header() {
  return `    <table class="hd">
      <tr>
        <td class="k">團隊成員</td><td style="width:44%">${esc(HEAD.team)}</td>
        <td class="k">指導教授</td><td>${esc(HEAD.advisor)}</td>
      </tr>
      <tr><td class="k">專題名稱</td><td colspan="3">${esc(HEAD.title)}</td></tr>
    </table>`;
}

function sdgBlock() {
  return `    <div class="sdg">
      <div class="t">請勾選與專題內容相關之 SDG</div>
      <ul>
${SDGS.map((s, i) => `        <li class="${i === SDG_TICKED ? "on" : ""}"><span class="box">${i === SDG_TICKED ? "✔" : ""}</span>${esc(s)}</li>`).join("\n")}
      </ul>
    </div>`;
}

/** kind: "self" (自評表) or "score" (評分表) */
function build(kind) {
  const self = kind === "self";
  const items = ITEMS.map((it) => {
    const band = self ? "" : `        <tr class="band">${BANDS.map((b) => `<td>${esc(b)}</td>`).join("")}</tr>\n`;
    const cells = it.levels.map((t, i) => {
      const on = self && it.level === i + 1;
      return `<td class="${on ? "on" : ""}">${on ? '<span class="pick">✔ 本組自評</span>' : ""}${esc(t)}</td>`;
    }).join("");
    const action = self
      ? `        <tr class="act"><td colspan="4">(圈選上述四個等級)　　本組自評：<b>第 ${it.level} 級</b>（由左至右為第 1～4 級）</td></tr>`
      : `        <tr class="act"><td colspan="4">分數＿＿＿＿＿ (請從上述四個等級圈選一個等級，並給予對應分數)</td></tr>`;
    const note = self
      ? `        <tr class="note"><td colspan="4"><b>說明：</b>${esc(it.note)}</td></tr>`
      : "";
    return `    <div class="item">
      <table>
        <tr class="qh"><td colspan="4">${it.n}. ${esc(it.name)}</td></tr>
${band}        <tr class="lv">${cells}</tr>
${action}
${note}      </table>
    </div>`;
  }).join("\n");

  const advisory = self ? "" : `
    <div class="brk"></div>
${header()}
    <table class="adv">
      <tr><td>建議事項：(請評審老師摘要說明須修正之建議事項)</td></tr>
      <tr><td class="tall"></td></tr>
      <tr><td>審查委員：</td></tr>
    </table>`;

  return `<!doctype html>
<!--
  GENERATED by presentations/tools/build_course_forms.mjs — 不要直接編輯這個檔。
  九項核心能力、四個等級的描述、分數級距、說明文字與 SDG 清單，全部逐字照錄自指導教授發的空白表
  （docs/course_forms/，IEET 20230317 版）。我們只填：團隊成員／指導教授／專題名稱、自評等級與說明、
  以及與專題相關的 SDG。${self ? "" : "\n  評分表的分數與等級留空——那是評審老師要填的。"}
-->
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
    <title>長庚大學資工系軟硬體專題${self ? "學生自評表" : "評分表"}</title>
    <style>${CSS}</style>
  </head>
  <body>
    <h1>長庚大學資工系軟硬體專題${self ? "學生自評表" : "評分表"}</h1>
${header()}
    <p class="lead">請就下列各項核心能力逐一檢視，${self ? "自評專題等級並提出證據說明理由" : "並給予適當分數"}</p>
${items}
${sdgBlock()}${advisory}
  </body>
</html>
`;
}

const outputs = [
  ["09_學生自評表_已填.html", build("self")],
  ["11_評分表_已填表頭.html", build("score")],
];
for (const [name, html] of outputs) {
  fs.writeFileSync(path.join(DIR, name), html, "utf8");
  console.log(`${name}  ${(Buffer.byteLength(html) / 1024).toFixed(0)} KB`);
}
