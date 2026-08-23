# 🚀 Looney Market Intelligence Terminal

> **An institutional-grade, multi-asset quantitative intelligence bot and automated radar for Discord.**  
> Delivering real-time market snapshots, balance sheet & cash flow audits, adaptive DFOL options strategies, SEC Form 4 insider & Form 8-K corporate tracking, short squeeze metrics, head-to-head asset battles, Wall Street/Bay Street research, global macro economic calendars, 24/7 breaking news, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.

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
| **`!!health`** or `!health` | `!!health` or `!status` | **System Diagnostics & Gateway Monitor** | 24-hour daily volume bucket (**Auto-Resets 12:00 AM EST**), uptime duration, container RAM usage, WebSocket latency (ms), session resumes vs. logins, and live Discord 24h login quota. |

---

## 📖 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [Master Asset Universe (~225 Monitored Assets)](#-master-asset-universe-225-monitored-assets)
3. [Dual-Engine Volume Pacing (Equities & Crypto)](#-dual-engine-volume-pacing-equities--crypto)
4. [On-Demand Intelligence Suite](#-on-demand-intelligence-suite)
   * [1. Market Snapshot & Balance Sheet Audit (`!/$`)](#1-market-snapshot--balance-sheet-audit-)
   * [2. Adaptive DFOL Options Engine (`#`)](#2-adaptive-dfol-options-engine-)
   * [3. Institutional Research Radar (`%`)](#3-institutional-research-radar-)
   * [4. Insider Trading, Whales & 8-K Dispositions (`?`)](#4-insider-trading-whales--8-k-dispositions-)
   * [5. Short Squeeze & Borrow Risk Metrics (`^`)](#5-short-squeeze--borrow-risk-metrics-)
   * [6. Head-to-Head Comparative Battle (`!vs`)](#6-head-to-head-comparative-battle-vs)
   * [7. Global Macro Pulse & Economic Calendar (`!!macro`)](#7-global-macro-pulse--economic-calendar-macro)
   * [8. System Health & Gateway Diagnostics (`!!health`)](#8-system-health--gateway-diagnostics-health)
5. [Automated Scheduled Radars](#-automated-scheduled-radars)
   * [30-Minute Price & Breaking News Radar](#1-30-minute-price--breaking-news-radar-mainpy)
   * [30-Minute Top 100 Market Options Radar](#2-30-minute-top-100-market-options-radar-mainpy)
   * [Daily 6:00 AM Multi-Market Earnings Radar](#3-daily-600-am-multi-market-earnings-radar-earningspy)
6. [Hosting & Deployment Architecture](#-hosting--deployment-architecture)

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
│  (Render 24/7)   │                           │ (30-Min Cronjob) │                           │ (Daily 6:00 AM)  │
├──────────────────┤                           ├──────────────────┤                           ├──────────────────┤
│ • !/$ Snapshot   │                           │ • Price Alerts   │                           │ • Scorecard      │
│ • 🕒 Today's Path│                           │ • Breaking News  │                           │ • Watchlist 45D  │
│ • # Options Play │                           │ • Top 100 Options│                           │ • Mega & Mid-Cap │
│ • % Analyst Rprt │                           │  (10-Part Radar) │                           │   (US & TSX 🍁)  │
│ • ? Insider & 8-K│                           │                  │                           │                  │
│ • ^ Short Squeeze│                           │                  │                           │                  │
│ • !vs Battle     │                           │                  │                           │                  │
│ • !!macro Pulse  │                           │                  │                           │                  │
│ • !!health Check │                           │                  │                           │                  │
│ • 24/7 Web Server│                           │                  │                           │                  │
└──────────────────┘                           └──────────────────┘                           └──────────────────┘
🌐 Master Asset Universe (~225 Monitored Assets)
Every 30 minutes, main.py scans a comprehensive cross-asset universe:
🪙 24/7 Cryptocurrencies (5): BTC-USD, ETH-USD, XRP-USD, SOL-USD, LINK-USD.
🛢️ Commodity & Index Futures (9): Gold (GC=F), Silver (SI=F), Crude Oil (CL=F), Brent (BZ=F), Natural Gas (NG=F), Nasdaq (NQ=F), S&P 500 (ES=F), Dow (YM=F), Russell (RTY=F).
📊 Major ETFs (12): SPY, QQQ, IWM, DIA, VOO, VTI, GLD, SLV, USO, BNO, IBIT, ETHA.
🇺🇸 S&P 500 (SPY) Top 100 & Nasdaq 100 Leaders (~140): Mega-cap tech, semiconductors, financial giants, consumer leaders, and high-beta growth stocks (NVDA, AAPL, MSFT, TSLA, PLTR, MSTR, IREN, RKLB, SPCX, etc.).
🍁 S&P/TSX 60 Canadian Blue-Chips (60): Big 6 Banks (RY.TO, TD.TO, etc.), Energy Titans (ENB.TO, CNQ.TO), Mining & Gold (ABX.TO, AEM.TO), and Canadian Tech (SHOP.TO, CSU.TO).
📊 Dual-Engine Volume Pacing (Equities & Crypto)
Raw cumulative volume creates distorted readings when compared directly against full-day averages. Looney uses two specialized pacing engines to evaluate Relative Volume (RVOL) accurately:
1. Equities Institutional U-Curve Engine (Stocks & ETFs)
Market Hours (9:30 AM – 4:00 PM EST): Pacing factors scale dynamically along Wall Street's U-shaped intraday volume distribution curve down to the exact minute.
Pre-Market, After-Hours & Weekends: Automatically defaults to 1.0x (100% full-day baseline), ensuring finished prior-session bars do not trigger false pre-market surge alerts.
2. 24/7 Continuous Crypto Volume Surfing Engine
00:00 UTC (8:00 PM EST) Daily Reset: Tracks elapsed minutes across the continuous 1,440-minute crypto trading day.
Early-Session Noise Buffer: Applies a 15-minute smoothing floor immediately after 00:00 UTC rollover to prevent false volume alerts while catching genuine early-session volume surges.
🔍 On-Demand Intelligence Suite
1. Market Snapshot & Balance Sheet Audit (!/$)
🕒 Today's Path: Real-time intraday session trail fetched live over HTTP from GitHub via private REST API with 0.0s latency.
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
⚡ Play A (7–14 DTE): Fast scalp / weekly momentum (Target exit: +50% to +80%, Stop-loss: -35%).
🏛️ Play B (30–45 DTE): Institutional swing play (Target exit: +40% to +60%, Trailing stop at 50D SMA).
🛡️ Alternative Setup: Defensive spreads, iron condors, or protective married puts.
3. Institutional Research Radar (%)
Coverage: Wall Street 🇺🇸 & Bay Street 🍁 Tier-1 banks (Goldman Sachs, Morgan Stanley, JPM, RBC, TD, BMO, Scotia, etc.).
Smart Filtering: Verified analyst actions and price target adjustments from the last 90 days.
Chunked Embeds: Clean 4-per-card pagination with direct research hyperlinks.
4. Insider Trading, Whales & 8-K Dispositions (?)
Ownership Structure: Direct JSON extraction of Institutional Ownership %, Officer/Insider Ownership %, and Tradable Float.
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
5
%
<5%
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
8. System Health & Gateway Diagnostics (!!health)
24-Hour Daily Tracking: Counts messages processed, embeds dispatched, and command popularity. Automatically resets at 12:00:00 AM EST (Midnight).
Server Status: Continuous container uptime, RAM memory usage (MB), Port 8080 keep-alive state.
Gateway Health: Real-time ping (ms), Session resumes, and live remaining session start quota (e.g. 997 / 1,000 Remaining).
⏰ Automated Scheduled Radars
1. 30-Minute Price & Breaking News Radar (main.py)
Price Movement Alerts: Scans all ~225 watchlist equities, ETFs, commodities, and 24/7 crypto. Dispatches alerts when session change crosses thresholds (
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
Breaking News: Scans real-time financial RSS feeds and search APIs (< 45 minutes old) across all 225 tickers with zero caps and fingerprint deduplication.
2. 30-Minute Top 100 Market Options Radar (main.py)
Active Market Gate: Runs Monday through Friday, 9:32 AM to 4:00 PM EST.
9:32 AM Opening Bell Buffer: Automatically pauses until 9:32 AM EST at market open so the opening auction settles before computing options spreads.
Top 100 10-Part Paginated Delivery: Ranks the entire 200+ options universe by conviction score and dispatches the Top 100 setups across 10 separate Discord messages (10 setups per part):
Part 1/10: Top Picks 1 – 10
Part 2/10: Top Picks 11 – 20
Part 3/10: Top Picks 21 – 30
Part 4/10: Top Picks 31 – 40
Part 5/10: Top Picks 41 – 50
Part 6/10: Top Picks 51 – 60
Part 7/10: Top Picks 61 – 70
Part 8/10: Top Picks 71 – 80
Part 9/10: Top Picks 81 – 90
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
🛠️ Hosting & Deployment Architecture
code
Text
┌────────────────────────────────────────────────────────┐
│                   DEPLOYMENT MAP                       │
├───────────────────┬───────────────────┬────────────────┤
│ Service           │ Script            │ Hosting Model  │
├───────────────────┼───────────────────┼────────────────┤
│ On-Demand Bot     │ bot.py            │ Render (24/7)  │
│ 30-Min Alert/Opt  │ main.py           │ Cron Service   │
│ Daily Earnings    │ earnings.py       │ Cron (6:00 AM) │
└───────────────────┴───────────────────┴────────────────┘
