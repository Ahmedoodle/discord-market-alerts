# 🚀 Looney Market Intelligence Terminal

> **An institutional-grade, multi-asset quantitative intelligence bot and automated market radar for Discord.**  
> Delivering real-time market snapshots, balance sheet & cash flow audits, adaptive DFOL options strategies, SEC Form 4 insider & Form 8-K corporate tracking, short squeeze metrics, head-to-head asset battles, Wall Street/Bay Street research, global macro economic calendars, 24/7 breaking news, Top 100 options radars, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.

---

## ⚡ Quick Command Cheat Sheet

In any Discord channel where Looney is active, type one of the following triggers followed by any ticker symbol (e.g., `NVDA`, `AAPL`, `TSLA`, `TD.TO`, `RY.TO`, `SPCX`, `BTC-USD`):

| Trigger / Command | Example | Command Name | What It Delivers |
| :--- | :--- | :--- | :--- |
| **`!`** or **`$`** | `!NVDA` or `$TD.TO` | **Market & Financial Health Snapshot** | Real-time technical indicators (RSI, MACD, SMAs, Pivots), time-paced institutional volume (RVOL), **🕒 Today's Path** intraday trail, balance sheet & cash flow audit, valuation multiples (P/E & P/FCF), and dividend schedules. |
| **`#`** | `#NVDA` or `#SPCX` | **Adaptive Options Deep-Dive** | Quant Confidence Score (0–100%), recommended DFOL options strategy, **Adaptive IPO/SPAC Engine** for fresh listings ($\ge 3$ days), and dual **7–14 DTE (Weekly Momentum)** vs. **30–45 DTE (Institutional Swing)** setups with exact strikes and break-even math. |
| **`%`** | `%NVDA` or `%RY.TO` | **Institutional Research Radar** | Real-time research notes, price target revisions, and rating actions from Tier-1 Wall Street (Goldman, Morgan Stanley, JPM) and Bay Street (RBC, TD, BMO, Scotia, CIBC) banks with direct source links. |
| **`?`** or `!insider` | `?NVDA` or `?AMD` | **Insider Trading & Corporate Dispositions** | Direct SEC Form 4 filings with **Dollar Cash Value** ($\text{Shares} \times \text{Price}$), **Top 10 Institutional Whales (Funds)**, **Top 10 Individual Insider Owners (People)**, and **Form 8-K Material Corporate Asset Sales / Divestitures**. |
| **`^`** or `!short` | `^AMD` or `^KUST` | **Short Squeeze & Borrow Risk Metrics** | Short Interest % of Float (with risk badges), **Days to Cover (Short Ratio)**, Month-over-Month short trend %, and accurate **Tradable Float** share counts. |
| **`!vs`** | `!vs NVDA AMD` | **Head-to-Head Comparative Battle** | Side-by-side comparative showdown across 1D Return, 14D RSI, ROE, Net Margin, Market Cap, and P/E Valuation with automatic **🏆 Crown Badges** for winning metrics. |
| **`!!macro`** or `!macro` | `!!macro` or `!econ` | **Global Macro Pulse & Fed Watch** | Real-time price matrix for Major Indices (`SPY`, `QQQ`, `DIA`, `IWM`), 10Y Yield (`^TNX`), VIX (`^VIX`), US Dollar (`DX-Y.NYB`), Gold, Oil, Bitcoin, and High-Impact Weekly Economic Releases (FOMC, CPI, NFP Jobs). |
| **`!crypto`** or `!cryptos` | `!crypto` | **13-Asset Crypto Radar** | Sequential paced audit across top global cryptocurrencies (`BTC`, `ETH`, `XRP`, `SOL`, `LINK`, `BNB`, `ADA`, `DOGE`, etc.) with 24/7 volume surfing. |
| **`!!health`** or `!health` | `!!health` or `!status` | **Operational Diagnostics & State Monitor** | Real-time live execution counters (**Today vs. Lifetime 💾**), container RAM usage, WebSocket latency (ms), session resumes vs. logins, and automatic 3-way GitHub state backup. |

---

## 📖 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [Master Asset Universe (~235 Monitored Assets)](#-master-asset-universe-235-monitored-assets)
3. [Session-Relative Price Engine & Isolation](#-session-relative-price-engine--isolation)
4. [Dual-Engine Volume Pacing (Equities & Crypto)](#-dual-engine-volume-pacing-equities--crypto)
5. [On-Demand Intelligence Suite](#-on-demand-intelligence-suite)
6. [Automated Scheduled Radars](#-automated-scheduled-radars)
7. [Persistent Analytics & 3-Way GitHub State Sync](#-persistent-analytics--3-way-github-state-sync)
8. [Hosting & Deployment Architecture](#-hosting--deployment-architecture)

---

## 🧠 Core Features & Architecture

```text
                                  ┌───────────────────────────────────────────────┐
                                  │      LOONEY MARKET TERMINAL ECOSYSTEM         │
                                  └──────────────────────┬────────────────────────┘
                                                         │
         ┌───────────────────────────────────────────────┼───────────────────────────────────────────────┐
         ▼                                               ▼                                               ▼
┌──────────────────┐                           ┌──────────────────┐                           ┌──────────────────┐
│      bot.py      │                           │     main.py      │                           │   earnings.py    │
│  (Render 24/7)   │                           │ (30-Min Actions) │                           │ (Daily 6:00 AM)  │
├──────────────────┤                           ├──────────────────┤                           ├──────────────────┤
│ • !/$ Snapshot   │                           │ • Session Alerts │                           │ • Scorecard      │
│ • 🕒 Today's Path│                           │   (Pre/Reg/AH)   │                           │ • Watchlist 45D  │
│ • # Options Play │                           │ • Breaking News  │                           │ • Mega & Mid-Cap │
│ • % Analyst Rprt │                           │ • Top 100 Options│                           │   (US & TSX 🍁)  │
│ • ? Insider & 8-K│                           │   (10-Part Radar)│                           │ • State Sync     │
│ • ^ Short Squeeze│                           │ • State Sync     │                           │                  │
│ • !vs Battle     │                           └──────────────────┘                           └──────────────────┘
│ • !!macro Pulse  │                                     │                                              │
│ • !crypto Radar  │                                     └──────────────────────┬───────────────────────┘
│ • !!health Check │                                                            ▼
│ • Port 8080 Web  │                                              ┌──────────────────────────┐
└──────────────────┘                                              │    alerts_state.json     │
         │                                                        │   (GitHub Remote Hub)    │
         └───────────────────────────────────────────────────────►│  • stats_today           │
                                                                  │  • stats_lifetime        │
                                                                  │  • persistent_analytics  │
                                                                  └──────────────────────────┘
🌐 Master Asset Universe (~235 Monitored Assets)
Every 30 minutes, main.py scans a comprehensive cross-asset universe:
🪙 24/7 Cryptocurrencies (5): BTC-USD, ETH-USD, XRP-USD, SOL-USD, LINK-USD.
🛢️ Commodity & Index Futures (9): Gold (GC=F), Silver (SI=F), Crude Oil (CL=F), Brent (BZ=F), Natural Gas (NG=F), Nasdaq (NQ=F), S&P 500 (ES=F), Dow (YM=F), Russell (RTY=F).
📊 Major ETFs (12): SPY, QQQ, IWM, DIA, VOO, VTI, GLD, SLV, USO, BNO, IBIT, ETHA.
🇺🇸 S&P 500 (SPY) Top 100 & Nasdaq 100 Leaders (~140): Mega-cap tech, semiconductors, financial giants, consumer leaders, and high-beta growth stocks (NVDA, AAPL, MSFT, TSLA, PLTR, MSTR, IREN, RKLB, SPCX, etc.).
🍁 S&P/TSX 60 Canadian Blue-Chips (60): Big 6 Banks (RY.TO, TD.TO, etc.), Energy Titans (ENB.TO, CNQ.TO), Mining & Gold (ABX.TO, AEM.TO), and Canadian Tech (SHOP.TO, CSU.TO).
🕒 Session-Relative Price Engine & Isolation
Rather than blending previous day closes across sessions, Looney uses strict session-relative math to eliminate false triggers:
code
Text
┌─────────────────┬──────────────────────┬────────────────────────────────┬───────────────────────────┐
│ Session         │ Active Hours (EST)   │ Baseline Price Used            │ Alert Trigger Threshold   │
├─────────────────┼──────────────────────┼────────────────────────────────┼───────────────────────────┤
│ [PRE-MARKET]    │ 4:00 AM – 9:30 AM    │ Yesterday's 4:00 PM Close      │ ±1.0% (Pure morning move) │
│ [REGULAR]       │ 9:30 AM – 4:00 PM    │ Yesterday's Official Close     │ ±2.0% (Standard day move) │
│ [AFTER-HOURS]   │ 4:00 PM – 8:00 PM    │ Today's 4:00 PM Regular Close  │ ±1.0% (Pure post-bell)    │
│ [CRYPTO]        │ 24/7/365 Continuous  │ 24h Rolling Baseline           │ ±2.0% (Continuous move)   │
└─────────────────┴──────────────────────┴────────────────────────────────┴───────────────────────────┘
Session Memory Isolation: Alerts are tracked across 4 independent dictionaries (premarket_tickers, regular_tickers, afterhours_tickers, crypto_tickers). When the session rolls (e.g. at the 9:30 AM opening bell), the new session starts with a completely clean slate.
Stale-Print Filter: In Pre-Market, the engine filters 1-minute trades executed specifically since 4:00 AM EST today. If a stock hasn't traded yet this morning, it sets 0.00% change and cleanly skips.
📊 Dual-Engine Volume Pacing (Equities & Crypto)
Raw cumulative volume creates distorted readings when compared directly against full-day averages. Looney uses two specialized pacing engines to evaluate Relative Volume (RVOL) accurately:
1. Equities Institutional U-Curve Engine (Stocks & ETFs)
Market Hours (9:30 AM – 4:00 PM EST): Pacing factors scale dynamically along Wall Street's U-shaped intraday volume distribution curve down to the exact minute.
Pre-Market, After-Hours & Weekends: Automatically defaults to 
1.0
×
1.0×
 (
100
%
100%
 full-day baseline), ensuring finished prior-session bars do not trigger false surge alerts.
2. 24/7 Continuous Crypto Volume Surfing Engine
00:00 UTC (8:00 PM EST) Daily Reset: Tracks elapsed minutes across the continuous 1,440-minute crypto trading day.
Early-Session Noise Buffer: Applies a 15-minute smoothing floor immediately after 00:00 UTC rollover to prevent false volume alerts while catching genuine early-session volume surges.
🔍 On-Demand Intelligence Suite
1. Market Snapshot & Balance Sheet Audit (!/$)
🕒 Today's Path: Real-time intraday session trail fetched live over HTTP from GitHub via private REST API with 
0.0
s
0.0s
 latency.
Multi-Timeframe RVOL: 20D (1-Month), 50D (Quarterly), and 90D (Long-Term) volume pacing tags.
Multi-Timeframe RSI: 7D (Fast/Scalp), 14D (Standard), and 30D (Macro Trend).
Moving Averages: 50D and 200D SMAs (or Listing Average for young IPOs).
Floor Trader Pivots: Key Support (
S
1
=
2
P
−
H
S 
1
​
 =2P−H
) and Resistance (
R
1
=
2
P
−
L
R 
1
​
 =2P−L
).
Fundamental Audit: Return on Equity (ROE), Net Profit Margin, Debt/Equity, Current Ratio, Free Cash Flow (FCF), and Trailing P/E vs. P/FCF valuation multiples.
2. Adaptive DFOL Options Engine (#)
100-Point Conviction Matrix: Evaluates Trend Alignment (25 pts), RSI Sweet Spot (20 pts), MACD Momentum (20 pts), Time-Paced RVOL (15 pts), and Implied Volatility Match (20 pts).
Adaptive IPO / SPAC Floor: Computes options analytics for fresh listings with as few as 3 trading days (SPCX, fresh IPOs).
Dual Timeframe Trade Plans:
⚡ Play A (7–14 DTE): Fast scalp / weekly momentum (Target exit: 
+
50
%
+50%
 to 
+
80
%
+80%
, Stop-loss: 
−
35
%
−35%
).
🏛️ Play B (30–45 DTE): Institutional swing play (Target exit: 
+
40
%
+40%
 to 
+
60
%
+60%
, Trailing stop at 50D SMA).
🛡️ Alternative Setup: Defensive spreads, iron condors, or protective married puts.
3. Institutional Research Radar (%)
Coverage: Wall Street 🇺🇸 & Bay Street 🍁 Tier-1 banks (Goldman Sachs, Morgan Stanley, JPM, RBC, TD, BMO, Scotia, etc.).
Smart Filtering: Verified analyst actions and price target adjustments from the last 90 days.
Chunked Embeds: Clean 4-per-card pagination with direct research hyperlinks.
4. Insider Trading, Whales & 8-K Dispositions (?)
Ownership Structure: Direct extraction of Institutional Ownership %, Officer/Insider Ownership %, and Tradable Float.
Whale Registries:
🏢 Top 10 Institutional Whales (Funds): Top asset managers and % stake of float.
👤 Top 10 Individual Insider Owners (People): Founders, CEO, Directors, and Officers with direct share counts.
Dollar-Calculated Form 4 Trades: Formats executed insider transactions with share counts, prices, and Total Dollar Cash Value ($) (e.g. 600 shares @ $1,162.16 ➔ $697.3K Total Value).
Material Corporate Dispositions (Form 8-K): Tracks when the company itself sells a business unit, subsidiary, or material asset (SEC Items 1.01 & 2.01).
5. Short Squeeze & Borrow Risk Metrics (^)
Short Interest % of Float: With institutional risk badges:
🔥 Extreme Squeeze Risk (
≥
20
%
≥20%
)
⚡ Elevated Short Interest (
≥
10
%
≥10%
)
🟢 Normal / Low Short Interest (
<
10
%
<10%
)
Days to Cover (Short Ratio): Measures how many trading days shorts need to buy back shares.
Month-over-Month Trend: Tracks whether short sellers are piling in or covering.
6. Head-to-Head Comparative Battle (!vs)
Direct Rivalry Showdown: Compares two assets side-by-side (!vs NVDA AMD or !vs SPY QQQ).
Visual 🏆 Crown Badges: Automatically awards crowns to the winner for 1D Change, RSI Momentum, ROE, Net Margin, and Valuation (P/E).
7. Global Macro Pulse & Economic Calendar (!!macro)
Multi-Asset Dashboard: Live prices and 1D returns across:
Indices: SPY, QQQ, DIA, IWM
Yields & Fear: 10Y Treasury Yield (^TNX), VIX Volatility (^VIX)
Commodities & Dollar: US Dollar Index (DX-Y.NYB), Gold (GC=F), Oil (CL=F)
Crypto: Bitcoin (BTC-USD)
Fed Watch & High-Impact Events: Upcoming FOMC rate policies, CPI/PPI inflation releases, Non-Farm Payrolls jobs data, and Fed Chair speeches.
⏰ Automated Scheduled Radars
1. 30-Minute Price & Breaking News Radar (main.py)
Price Movement Alerts: Scans all ~235 watchlist assets. Dispatches alerts when session change crosses thresholds (
±
2.0
%
±2.0%
 regular, 
±
1.0
%
±1.0%
 pre/after-hours) with full technical blocks and intraday path trail history.
Breaking News: Scans real-time financial RSS feeds and search APIs (
<
45
<45
 minutes old) across all tickers with zero duplicate spam and fingerprint deduplication.
2. 30-Minute Top 100 Market Options Radar (main.py)
Active Market Gate: Runs Monday through Friday, 9:32 AM to 4:00 PM EST.
9:32 AM Opening Bell Buffer: Automatically pauses until 9:32 AM EST at market open so the opening auction settles before computing options spreads.
Top 100 10-Part Paginated Delivery: Ranks the entire 200+ options universe by conviction score and dispatches the Top 100 setups across 10 separate Discord messages (10 setups per part):
Part 1/10: Top Picks 1 – 10
Part 2/10: Top Picks 11 – 20
Part 3/10: Top Picks 21 – 30
...
Part 10/10: Top Picks 91 – 100
3. Daily 6:00 AM Multi-Market Earnings Radar (earnings.py)
Card 1: 📢 Yesterday's Scorecard: Official reported actuals, estimates, and beat/miss data across US and TSX listings (Hierarchically ordered: 🍁 CAD Mega ➔ 🇺🇸 US Mega ➔ 🍁 CAD Mid ➔ 🇺🇸 US Mid).
Card 2: 🗓️ Watchlist Calendar (Next 45 Days): Upcoming reports across personal watchlist.
Card 3A & 3B: 👑 Mega-Caps (Next 45 Days — 
≥
$
200
B
≥$200B
): Dedicated Canadian TSX and US Mega-Cap calendars.
Card 4A: 🍁 Canadian Mid-Caps (Next 45 Days — 
$
1.5
B
−
$
200
B
$1.5B−$200B
): Complete TSX mid-cap coverage.
Card 4B: 📈 US Mid-Caps (Next 7 Days — 
$
1.5
B
−
$
200
B
$1.5B−$200B
): Paginated in clean batches of 15 per card.
