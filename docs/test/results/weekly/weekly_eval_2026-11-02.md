# 每週新查核自動評測 2026-11-02

（`app/services/weekly_eval.py` 自動產生；方法見 `docs/test/上線後準確率驗證計畫.md` 的 M5。真值是查核機構已發布的結論；AI 不經快取、不帶 web_search，量的是 AI 判讀本身，不含快取與來源分級。）

- 模型：cgu `gpt-5.6-luna`，推理強度 medium，web_search 關
- 本週範圍：2026-10-26 起發布的查核結論（7 天）
- 額度：執行前本週已用 USD 4.6861，剩 USD 5.3139（額度 USD 10.00）；執行後本週已用 USD 4.6861，剩 USD 5.3139（額度 USD 10.00）；本次上限 USD 6.00、保留 USD 3.00 給網站使用者
- 本週可出題的查核結論 20 題
- 結束原因：超過 150 分鐘

## 本週新查核（主要數字）

模型訓練之後才出現的內容，最接近上線後的真實表現。

- 題數 20（SCAM 0、MISINFO 18、SAFE 2）；有效判讀 9，AI 服務不可用 11
- **風險判定一致率 88.9%**（95% 信賴區間 56.5%–98.0%）：真值有風險（SCAM／MISINFO）時 AI 也判有風險、真值 SAFE 時 AI 也判 SAFE；AI 判「無法查證」算不一致
- 三類完全一致率 22.2%（6.3%–54.7%）
- **偽陰性（真值有風險、AI 判 SAFE）0 筆**；偽陽性 0 筆；AI 判「無法查證」1 筆
- 估算花費 USD 0.0320

| 真值 ＼ AI 判定 | SCAM | MISINFO | SAFE | UNVERIFIABLE | 其他 |
|---|---:|---:|---:|---:|---:|
| SCAM | 0 | 0 | 0 | 0 | 0 |
| MISINFO | 6 | 2 | 0 | 1 | 0 |
| SAFE | 0 | 0 | 0 | 0 | 0 |

| 來源 | 有效題數 | 風險判定一致率 | 偽陰性 |
|---|---:|---:|---:|
| Cofacts | 5 | 100.0% | 0 |
| MyGoPen | 2 | 100.0% | 0 |
| TFC | 2 | 50.0% | 0 |

風險判定不一致的題目（原文請開查核網址；報告不存訊息原文）：

| 來源 | 真值 | AI 判定 | 查核網址 |
|---|---|---|---|
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/outdated-claim-kmt-blocked-military-pension-bill/ |

## 歷史抽樣（參考）

知識庫中查核機構已證實的訊息（風險題）與 Cofacts 認可為非謠言的訊息（安全題），2:1 抽樣；可能出現在模型訓練資料中，數字偏樂觀。

- 題數 660（SCAM 9、MISINFO 651、SAFE 0）；有效判讀 337，AI 服務不可用 323
- **風險判定一致率 88.4%**（95% 信賴區間 84.6%–91.4%）：真值有風險（SCAM／MISINFO）時 AI 也判有風險、真值 SAFE 時 AI 也判 SAFE；AI 判「無法查證」算不一致
- 三類完全一致率 68.8%（63.7%–73.6%）
- **偽陰性（真值有風險、AI 判 SAFE）16 筆**；偽陽性 0 筆；AI 判「無法查證」23 筆
- 估算花費 USD 1.4566

| 真值 ＼ AI 判定 | SCAM | MISINFO | SAFE | UNVERIFIABLE | 其他 |
|---|---:|---:|---:|---:|---:|
| SCAM | 2 | 0 | 0 | 1 | 0 |
| MISINFO | 66 | 230 | 16 | 22 | 0 |
| SAFE | 0 | 0 | 0 | 0 | 0 |

| 來源 | 有效題數 | 風險判定一致率 | 偽陰性 |
|---|---:|---:|---:|
| Cofacts | 144 | 95.1% | 3 |
| MyGoPen | 76 | 77.6% | 6 |
| TFC | 117 | 87.2% | 7 |

風險判定不一致的題目（原文請開查核網址；報告不存訊息原文）：

| 來源 | 真值 | AI 判定 | 查核網址 |
|---|---|---|---|
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/migration-11205/ |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/garlic-kills-parasites-misconception/ |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/migration-5041/ |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2018/12/line311.html |
| Cofacts | MISINFO | SAFE | https://cofacts.tw/article/x2xff8oolqmx |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2025/12/mobile.html |
| Cofacts | MISINFO | UNVERIFIABLE | https://cofacts.tw/article/wqrxy83lnxqj |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2023/06/ai-optimus.html |
| Cofacts | MISINFO | UNVERIFIABLE | https://cofacts.tw/article/3iywa8b2pf6sy |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2023/02/fire-Chicago.html |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2020/06/US-police-shoot-homeless-man.html |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/india-landslide-video-misrepresented-tibet/ |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/migration-7116/ |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2021/08/Hang.html |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/migration-7032/ |
| Cofacts | MISINFO | UNVERIFIABLE | https://cofacts.tw/article/3uxpz579mhtcr |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/no-solar-panels-found-in-pingtung-floating-debris/ |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2025/07/Alice-Weidel.html |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2025/09/Uttarakhand.html |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/migration-7225/ |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2025/10/trip.html |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2023/04/hpv-vaccine.html |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2020/03/Kitchen-alcohol-fire.html |
| MyGoPen | SCAM | UNVERIFIABLE | https://www.mygopen.com/2021/01/FamilyMart.html |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2025/02/mRNA.html |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/migration-5254/ |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2026/02/infect.html |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/migration-10189/ |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/flooding-leptospira-risk-not-transmitted-through-clothes/ |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2026/05/mocs.html |
| TFC | MISINFO | UNVERIFIABLE | https://tfc-taiwan.org.tw/fact-check-reports/beware-avocado-oversupply-scam-social-media/ |
| Cofacts | MISINFO | SAFE | https://cofacts.tw/article/1en8thk9rlnvx |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/ai-generated-image-not-real-skeleton-flower/ |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/migration-11171/ |
| MyGoPen | MISINFO | UNVERIFIABLE | https://www.mygopen.com/2019/03/3d5g.html |
| Cofacts | MISINFO | SAFE | https://cofacts.tw/article/1p0zr9ewmeu2b |
| TFC | MISINFO | SAFE | https://tfc-taiwan.org.tw/fact-check-reports/japan-three-way-cash-scam/ |
| Cofacts | MISINFO | UNVERIFIABLE | https://cofacts.tw/article/312et1oj7856z |
| MyGoPen | MISINFO | SAFE | https://www.mygopen.com/2017/09/line_58.html |

## 解讀注意

1. Cofacts 的 RUMOR 一律記為 MISINFO，其中的詐騙訊息被 AI 判為 SCAM 算風險判定正確、三類不一致；所以以「風險判定一致率」為主要數字。
2. Cofacts 的題目是使用者回報的原始訊息，常是詐騙對話中的一句（例如「你今天有時間去辦理一下預付卡嗎」），單看一句本來就難以判斷；MyGoPen 與台灣事實查核中心的題目是查核機構整理過的主張。兩者請分開看上面的來源表。
3. 偽陰性是本系統唯一的絕對禁止項：每一筆都要打開查核網址確認。查核機構文章的偽陰性依準確率驗證計畫第 5 節做錯誤分析；Cofacts 的對話片段若單看該句確實無法判斷，在覆核紀錄註明後不列為缺陷。
4. 網站上的燈號另外要求查核來源（沒有 Tier 1／2 來源不給綠燈），所以使用者實際看到的綠燈比這裡的 SAFE 判定更保守。
