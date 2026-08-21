# 🚀 Looney Market Intelligence Terminal

> **An institutional-grade, multi-asset quantitative intelligence bot and automated radar for Discord.**  
> Delivering real-time market snapshots, technical & balance sheet audits, DFOL options strategies, Wall Street/Bay Street research, 24/7 breaking news, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.

---

## ⚡ Quick Command Cheat Sheet

In any Discord channel where Looney is active, type one of the following triggers followed by any ticker symbol (e.g., `NVDA`, `AAPL`, `TSLA`, `TD.TO`, `RY.TO`, `BTC-USD`):

| Trigger Prefix | Example | Command Name | What It Delivers |
| :--- | :--- | :--- | :--- |
| **`!`** or **`$`** | `!NVDA` or `$TD.TO` | **Market & Financial Health Snapshot** | Real-time technical indicators (RSI, MACD, SMAs, Pivots), time-paced institutional volume (RVOL), balance sheet & cash flow audit, valuation multiples (P/E & P/FCF), and dividend schedules. |
| **`#`** | `#NVDA` or `#TSLA` | **Options Strategy Deep-Dive** | Quant Confidence Score (0–100%), recommended DFOL options strategy, and dual **7–14 DTE (Weekly Momentum)** vs. **30–45 DTE (Institutional Swing)** trade setups with exact strikes and break-even math. |
| **`%`** | `%NVDA` or `%RY.TO` | **Institutional Research Radar** | Real-time research notes, price target revisions, and rating actions from Tier-1 Wall Street (Goldman, Morgan Stanley, JPM) and Bay Street (RBC, TD, BMO, Scotia, CIBC) banks with direct source links. |

---

## 📖 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [Dual-Engine Volume Pacing (Equities & Crypto)](#-dual-engine-volume-pacing-equities--crypto)
3. [Technical & Fundamental Indicator Guide](#-technical--fundamental-indicator-guide)
4. [DFOL Options Strategy Engine Guide](#-dfol-options-strategy-engine-guide)
5. [Institutional Research Radar (`%`)](#-institutional-research-radar-)
6. [Automated Scheduled Radars](#-automated-scheduled-radars)
   * [30-Minute Price & Breaking News Radar](#1-30-minute-price--breaking-news-radar)
   * [30-Minute Top 10 Nasdaq 100 Options Radar](#2-30-minute-top-10-nasdaq-100-options-radar)
   * [Daily 6:00 AM Multi-Market Earnings Radar](#3-daily-600-am-multi-market-earnings-radar)
7. [Hosting & Deployment Architecture](#-hosting--deployment-architecture)

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
│ • # Options Play │                           │ • Breaking News  │                           │ • Watchlist 45D  │
│ • % Analyst Rprt │                           │ • Top 10 Options │                           │ • Mega & Mid-Cap │
│ • 24/7 Web Server│                           │   (9:32am-4:00pm)│                           │   (US & TSX 🍁)  │
└──────────────────┘                           └──────────────────┘                           └──────────────────┘
📊 Dual-Engine Volume Pacing (Equities & Crypto)
Raw cumulative volume creates false readings when compared directly against full-day averages. Looney uses two specialized pacing engines to evaluate Relative Volume (RVOL) accurately:

1. Equities Institutional U-Curve Engine (Stocks & ETFs)
Market Hours (9:30 AM – 4:00 PM EST): Pacing factors scale along Wall Street's U-shaped intraday volume distribution curve.

Pre-Market, After-Hours & Weekends: Automatically defaults to 1.0x (100% full-day baseline), preventing previous-session finished bars from triggering false pre-market surge alerts.

2. 24/7 Continuous Crypto Volume Surfing Engine
00:00 UTC (8:00 PM EST) Daily Reset: Tracks elapsed minutes across the 1,440-minute crypto day.

Early-Session Noise Buffer: Applies a 15-minute smoothing floor immediately after 00:00 UTC rollover to prevent false 100x alerts from initial trades while catching early-session institutional breakouts.

📈 Technical & Fundamental Indicator Guide
Every indicator in the !TICKER and $TICKER snapshot is calculated live:

1. Multi-Timeframe Volume Multipliers (RVOL)
What It Measures: Compares current time-paced volume against historical averages across 20-Day (1-Month), 50-Day (Quarterly), and 90-Day (Long-Term) benchmarks.

Benchmarks:

🔥 >= 2.0x (Unusual Surge): Heavy institutional accumulation/distribution.

⚡ >= 1.3x (Strong): Active institutional participation.

💤 < 0.6x (Low): Low-liquidity retail drift.

2. Multi-Timeframe RSI (Relative Strength Index)
Horizons: 7D (Fast/Scalp Momentum), 14D (Standard), 30D (Macro Trend).

Zones:

🟢 50.0 – 68.0 (Bullish Trend): Momentum expanding with room to run.

🔴 32.0 – 48.0 (Bearish Trend): Downward momentum dominant.

⚠️ >= 70.0 (Overbought): Near-term pullback risk.

🟢 <= 30.0 (Oversold): High probability relief bounce zone.

3. Moving Averages & Structural Trend (50D & 200D SMA)
🟢 Strong Bullish Uptrend: Price above both 50D & 200D SMA (Institutional Support).

🔴 Strong Bearish Downtrend: Price below both 50D & 200D SMA (Institutional Selling).

🟡 Pullback in Macro Uptrend: Price above 200D SMA but testing 50D SMA.

🟡 Counter-Trend Rebound: Price below 200D SMA but bouncing over 50D SMA.

4. MACD Momentum Verdict (12, 26, 9)
Evaluates MACD line versus signal line and tracks histogram expansion/contraction to determine whether directional momentum is accelerating or exhausting.

5. Floor Trader Pivot Points (S1 & R1)
Calculates key support (
S
1
=
2
P
−
H
S1=2P−H
) and resistance (
R
1
=
2
P
−
L
R1=2P−L
) levels based on previous session range.

6. Capital Efficiency, Cash Flow & Valuation Multiples
ROE (Return on Equity): Capital efficiency metric (💎 >= 20% denotes elite return).

Net Margin: Percentage of top-line revenue converted to net profit.

Solvency & Liquidity: Debt-to-Equity and Current Ratio.

Free Cash Flow (FCF) & Quality Ratio: Operating Cash Flow minus CapEx, verified by FCF / Net Income cash backing.

Valuation Multiples: Dual display of Trailing P/E and P/FCF (Price to Free Cash Flow) with clean growth/pre-profit status tags.

🎯 DFOL Options Strategy Engine Guide
When typing #TICKER or reviewing the scheduled Top 10 Options Radar, Looney applies official DFOL (Derivatives Fundamentals & Options Licensing) principles:

1. 100-Point Quantitative Conviction Matrix
code
Text
[ 100-Point Scoring Algorithm ]
 ├── 25 pts: Trend Alignment (Price vs. 50D & 200D SMA)
 ├── 20 pts: RSI Momentum Sweet Spot (52–68 Bullish / 32–48 Bearish)
 ├── 20 pts: MACD Directional Momentum & Histogram Expansion
 ├── 15 pts: Time-Paced RVOL (Volume Confirmation >= 1.3x)
 └── 20 pts: Implied Volatility Match (DFOL Strategy Selection)
🟢 >= 80% (High Conviction): High technical and volatility alignment.

🟠 60% – 79% (Developing / Watchlist): Solid setup pending confirmation.

🔴 < 60% (Low Conviction / Avoid): Conflicting signals or poor risk/reward.

2. Strategy Selection Matrix
Directional Bias	IV Environment	Selected DFOL Strategy	Execution Setup
Outright Bullish	Low IV (< 40%)	Long Call	Buy 30–45 DTE Call (Delta ~ 0.65–0.70)
Moderately Bullish	Moderate IV (30–50%)	Bull Call Debit Spread	Buy ATM Call / Sell OTM Call
Neutral to Bullish	High IV (> 50%)	Bull Put Credit Spread	Sell OTM Put at S1 / Buy Lower Put
Outright Bearish	Low IV (< 40%)	Long Put	Buy 30–45 DTE Put (Delta ~ -0.65–0.70)
Moderately Bearish	Moderate IV (30–50%)	Bear Put Debit Spread	Buy ATM Put / Sell OTM Put
Neutral to Bearish	High IV (> 50%)	Bear Call Credit Spread	Sell OTM Call at R1 / Buy Higher Call
3. Dual Timeframe Trade Plans
⚡ Play A (7–14 DTE): Fast scalp / weekly momentum (Target exit: +50% to +80%, Stop-loss: -35%).

🏛️ Play B (30–45 DTE): Institutional swing play (Target exit: +40% to +60%, Trailing stop at 50D SMA).

🛡️ Alternative Setup: Defensive spread or married hedge for risk mitigation.

🏛️ Institutional Research Radar (%)
Typing %TICKER performs a multi-source scan across major financial news wires and research desks:

Wall Street 🇺🇸: Goldman Sachs, Morgan Stanley, JPMorgan Chase, Bank of America, Wells Fargo, Citigroup, Barclays, UBS, Deutsche Bank, Jefferies, Piper Sandler, Wedbush, Evercore ISI, Baird, Stifel, Wolfe Research.

Bay Street 🍁: RBC Capital Markets, TD Cowen / TD Securities, BMO Capital Markets, Scotiabank Global, CIBC World Markets, National Bank Financial, Desjardins.

Smart Disambiguation: Differentiates between subject company tickers and research notes authored by bank analysts.

Automatic Multi-Part Pagination: Splits large research sets into clean batches of 4 per Discord embed card with source hyperlinks.

⏰ Automated Scheduled Radars

1. 30-Minute Price & Breaking News Radar (main.py)
Price Movement Alerts: Scans watchlist equities, commodities, and 24/7 crypto. Dispatches alerts when session change crosses thresholds (±2.0% regular, ±1.0% pre/after-hours) with full technical blocks and intraday path trail history.

Breaking News: Scans real-time financial RSS feeds and search APIs (< 45 minutes old) with fingerprint deduplication.

2. 30-Minute Top 10 Nasdaq 100 Options Radar (main.py)
Active Market Gate: Runs Monday through Friday, 9:32 AM to 4:00 PM EST.

9:32 AM Opening Bell Buffer: Automatically pauses until 9:32 AM EST at market open so the opening auction settles before computing options spreads.

Ranked Output: Ranks the entire Nasdaq 100 by conviction score and posts the Top 10 actionable options setups.

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
