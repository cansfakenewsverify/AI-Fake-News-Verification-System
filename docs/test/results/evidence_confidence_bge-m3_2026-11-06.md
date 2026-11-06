# 證據信心研究（bge-m3，2026-11-06）

由 `code/backend/scripts/evidence_confidence_study.py` 產生；語料來自 `scripts/ingest_factchecks.py`。
相似度為 cosine（bge-m3，1024 維），夾角 = arccos(相似度)。

## 語料

| 來源 | 標記 | 用途 | 筆數 |
|------|------|------|------|
| Cofacts | MISINFO | 可入庫 | 7,103 |
| Cofacts | SAFE | 只供分析 | 1,748 |
| MyGoPen | MISINFO | 可入庫 | 4,047 |
| MyGoPen | SAFE | 只供分析 | 61 |
| MyGoPen | SCAM | 可入庫 | 160 |
| TFC | MISINFO | 可入庫 | 7,159 |
| TFC | SAFE | 只供分析 | 4 |

## 1. 誤命中檢查：評測 150 題對可入庫列的最近相似度

語意快取門檻 0.75（夾角 41.4°）。可入庫列全是詐騙或假訊息，所以**安全題的最近鄰 ≥ 門檻，就代表入庫後這題會被語意快取誤判**。

| 正確答案 | 題數 | 最近鄰相似度 中位數 | ≥ 0.75 | 0.7～0.75 | 0.65～0.7 |
|----------|------|---------------------|--------|------------|------------|
| SCAM | 50 | 0.711 | 12 | 18 | 18 |
| MISINFO | 50 | 0.696 | 11 | 13 | 16 |
| SAFE | 50 | 0.644 | 1 | 5 | 17 |

≥ 門檻的題目共 24 題：

| 題號 | 正確答案 | 相似度 | 夾角 | 題目（前 40 字） | 最近鄰（前 60 字） | 最近鄰網址 |
|------|----------|--------|------|------------------|--------------------|------------|
| 62 | MISINFO | 0.865 | 30.1° | （不放原文） | （不放原文） | https://www.mygopen.com/2017/05/n.html |
| 27 | SCAM | 0.849 | 31.9° | （不放原文） | （不放原文） | https://cofacts.tw/article/1h8oygcqmrq9f |
| 24 | SCAM | 0.841 | 32.8° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-9161/ |
| 26 | SCAM | 0.836 | 33.3° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/fake-esun-bank-sms-phishing-scam/ |
| 21 | SCAM | 0.813 | 35.6° | （不放原文） | （不放原文） | https://cofacts.tw/article/1j7lr1320j2cc |
| 55 | MISINFO | 0.810 | 35.9° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-4016/ |
| 86 | MISINFO | 0.809 | 36.0° | （不放原文） | （不放原文） | https://www.mygopen.com/2020/06/cooking-with-aluminum.html |
| 17 | SCAM | 0.803 | 36.5° | （不放原文） | （不放原文） | https://cofacts.tw/article/28d8x1cb0flz1 |
| 1 | SCAM | 0.801 | 36.8° | （不放原文） | （不放原文） | https://cofacts.tw/article/5861y9oejsol |
| 6 | SCAM | 0.799 | 37.0° | （不放原文） | （不放原文） | https://cofacts.tw/article/AVxzfeBXyCdS-nWhuZ5n |
| 107 | SAFE | 0.787 | 38.1° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/165-hotline-did-not-cohost-anti-fraud-survey/ |
| 33 | SCAM | 0.785 | 38.3° | （不放原文） | （不放原文） | https://cofacts.tw/article/fcin9xjorkl9 |
| 9 | SCAM | 0.781 | 38.6° | （不放原文） | （不放原文） | https://www.mygopen.com/2021/01/fake-ebank.html |
| 73 | MISINFO | 0.777 | 39.0° | （不放原文） | （不放原文） | https://cofacts.tw/article/5483025407563-rumor |
| 57 | MISINFO | 0.773 | 39.3° | （不放原文） | （不放原文） | https://cofacts.tw/article/bjdjnlfnh404 |
| 7 | SCAM | 0.772 | 39.4° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-10406/ |
| 97 | MISINFO | 0.768 | 39.9° | （不放原文） | （不放原文） | https://www.mygopen.com/2020/05/instant-noodles-32.html |
| 51 | MISINFO | 0.766 | 40.0° | （不放原文） | （不放原文） | https://cofacts.tw/article/12v08cdgv9y84 |
| 23 | SCAM | 0.762 | 40.4° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-8229/ |
| 40 | SCAM | 0.760 | 40.6° | （不放原文） | （不放原文） | https://cofacts.tw/article/1kllzwi40lyat |
| 67 | MISINFO | 0.759 | 40.6° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-5161/ |
| 87 | MISINFO | 0.758 | 40.7° | （不放原文） | （不放原文） | https://www.mygopen.com/2024/04/Artificial.html |
| 68 | MISINFO | 0.757 | 40.8° | （不放原文） | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-5749/ |
| 99 | MISINFO | 0.754 | 41.0° | （不放原文） | （不放原文） | https://cofacts.tw/article/i4d2biaztm2i |

## 2. 同一則謠言的改寫句夾角（PF-2 題組）

| 題組 | 句數 | 相似度 中位數 | 最小 | 最大 | ≥ 0.75 |
|------|------|------|------|------|------|
| pf2_paraphrases | 20 | 0.887 | 0.803 | 0.962 | 20 |
| pf2_rerun_2026-09-21 | 20 | 0.919 | 0.606 | 1.000 | 18 |

## 3. 夾角分段校準：最近鄰相似度 → 題目真的有風險的比例

評測題庫三類各 50 題，基準比例為 66.7%（100／150）。

| 相似度區間 | 夾角 | 題數 | 真的有風險 | 比例 |
|------------|------|------|------------|------|
| 0.50～0.55 | 57°～60° | 1 | 0 | 0% |
| 0.55～0.60 | 53°～57° | 6 | 2 | 33% |
| 0.60～0.65 | 49°～53° | 32 | 10 | 31% |
| 0.65～0.70 | 46°～49° | 51 | 34 | 67% |
| 0.70～0.75 | 41°～46° | 36 | 31 | 86% |
| 0.75～0.80 | 37°～41° | 15 | 14 | 93% |
| 0.80～0.85 | 32°～37° | 8 | 8 | 100% |
| 0.85～0.90 | 26°～32° | 1 | 1 | 100% |

## 4. 話術類型（規定集）：40 個風險原型、12 個正常訊息原型

判斷規則：離最近的風險原型比離最近的正常原型更近（差距 > 0）就判為有風險。

| 正確答案 | 題數 | 判為有風險 | 判對 |
|----------|------|------------|------|
| SCAM | 50 | 42 | 42／50 |
| MISINFO | 50 | 49 | 49／50 |
| SAFE | 50 | 24 | 26／50 |
| 全部 | 150 | 115 | 78.0% |

差距分段（差距越大越像已知話術）：

| 差距區間 | 題數 | 真的有風險 | 比例 |
|----------|------|------------|------|
| -1.00～-0.05 | 4 | 1 | 25% |
| -0.05～+0.00 | 31 | 8 | 26% |
| +0.00～+0.05 | 79 | 55 | 70% |
| +0.05～+0.10 | 36 | 36 | 100% |

對照：kNN 投票（最近 10 筆，含已證實為真的列，以相似度加權，風險權重 > 0.5 判為有風險）

| 正確答案 | 題數 | 判為有風險 | 判對 |
|----------|------|------------|------|
| SCAM | 50 | 47 | 47／50 |
| MISINFO | 50 | 50 | 50／50 |
| SAFE | 50 | 38 | 12／50 |
| 全部 | 150 | 135 | 72.7% |

## 風險原型一覽（每群筆數與代表句）

| 群 | 筆數 | 詐騙 | 代表句（離中心最近，前 50 字） | 代表句網址 |
|----|------|------|------------------------------|------------|
| 0 | 505 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-7578/ |
| 1 | 791 | 0 | （不放原文） | https://cofacts.tw/article/10c9xxens5beb |
| 2 | 468 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-10716/ |
| 3 | 444 | 0 | （不放原文） | https://cofacts.tw/article/f6w11w2y4v05 |
| 4 | 731 | 0 | （不放原文） | https://cofacts.tw/article/6g1bptibb0xm |
| 5 | 372 | 1 | （不放原文） | https://cofacts.tw/article/3kpov2gzso30d |
| 6 | 295 | 2 | （不放原文） | https://www.mygopen.com/2016/12/100150.html |
| 7 | 265 | 0 | （不放原文） | https://www.mygopen.com/2024/04/arma3.html |
| 8 | 184 | 0 | （不放原文） | https://cofacts.tw/article/2rud6roo6u583 |
| 9 | 442 | 40 | （不放原文） | https://cofacts.tw/article/3vqof2y2rutym |
| 10 | 331 | 1 | （不放原文） | https://cofacts.tw/article/2zt6p2hdfy9qj |
| 11 | 620 | 2 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-10111/ |
| 12 | 359 | 0 | （不放原文） | https://cofacts.tw/article/3j0nc8kvng8ww |
| 13 | 222 | 7 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-5136/ |
| 14 | 204 | 3 | （不放原文） | https://cofacts.tw/article/16v3w5awakzh5 |
| 15 | 357 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-4348/ |
| 16 | 489 | 0 | （不放原文） | https://www.mygopen.com/2025/07/trump357.html |
| 17 | 882 | 0 | （不放原文） | https://cofacts.tw/article/30735trkxio7b |
| 18 | 395 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-2189/ |
| 19 | 437 | 0 | （不放原文） | https://cofacts.tw/article/2om5rnziokhbv |
| 20 | 416 | 19 | （不放原文） | https://www.mygopen.com/2016/02/20.html |
| 21 | 594 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-4706/ |
| 22 | 491 | 0 | （不放原文） | https://www.mygopen.com/2018/10/94.html |
| 23 | 384 | 0 | （不放原文） | https://cofacts.tw/article/5618991709228-rumor |
| 24 | 473 | 23 | （不放原文） | https://cofacts.tw/article/AVr1HOz9tKp96s659C1F |
| 25 | 541 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-6534/ |
| 26 | 424 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-6434/ |
| 27 | 585 | 7 | （不放原文） | https://cofacts.tw/article/1zikhwcphgfxl |
| 28 | 587 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-9848/ |
| 29 | 471 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-10850/ |
| 30 | 353 | 2 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/migration-8494/ |
| 31 | 458 | 1 | （不放原文） | https://cofacts.tw/article/uffvy8nlsl53 |
| 32 | 398 | 0 | （不放原文） | https://cofacts.tw/article/29z12ittbjom1 |
| 33 | 423 | 29 | （不放原文） | https://cofacts.tw/article/AV-MlymQyCdS-nWhuioK |
| 34 | 571 | 0 | （不放原文） | https://cofacts.tw/article/2q3d9qakdadcg |
| 35 | 326 | 0 | （不放原文） | https://tfc-taiwan.org.tw/fact-check-reports/costco-taiwan-not-selling-returned-us-beef-from-korea/ |
| 36 | 602 | 14 | （不放原文） | https://www.mygopen.com/2025/03/20w.html |
| 37 | 699 | 2 | （不放原文） | https://cofacts.tw/article/3aqnam3y5zabu |
| 38 | 403 | 0 | （不放原文） | https://cofacts.tw/article/17lfjnks28aug |
| 39 | 477 | 7 | （不放原文） | https://www.mygopen.com/2021/10/water.html |
