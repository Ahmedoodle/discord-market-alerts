🚀 Looney Market Intelligence Terminal
An institutional-grade, multi-asset quantitative intelligence bot and automated radar for Discord.
Delivering real-time market snapshots, technical & balance sheet audits, DFOL options strategies, Wall Street/Bay Street research, 24/7 breaking news, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.
⚡ Quick Command Cheat Sheet
In any Discord channel where Looney is active, type one of the following triggers followed by any ticker symbol (e.g., NVDA, AAPL, TSLA, TD.TO, RY.TO, BTC-USD):
Trigger Prefix	Example	Command Name	What It Delivers
! or $	!NVDA or $TD.TO	Market & Financial Health Snapshot	Real-time technical indicators (RSI, MACD, SMAs, Pivots), time-paced institutional volume (RVOL), balance sheet & cash flow audit, valuation multiples (P/E & P/FCF), and dividend schedules.
#	#NVDA or #TSLA	Options Strategy Deep-Dive	Quant Confidence Score (0–100%), recommended DFOL options strategy, and dual 7–14 DTE (Weekly Momentum) vs. 30–45 DTE (Institutional Swing) trade setups with exact strikes and break-even math.
%	%NVDA or %RY.TO	Institutional Research Radar	Real-time research notes, price target revisions, and rating actions from Tier-1 Wall Street (Goldman, Morgan Stanley, JPM) and Bay Street (RBC, TD, BMO, Scotia, CIBC) banks with direct source links.
📖 Table of Contents
Core Features & Architecture
Dual-Engine Volume Pacing (Equities & Crypto)
Technical & Fundamental Indicator Guide
DFOL Options Strategy Engine Guide
Institutional Research Radar (%)
Automated Scheduled Radars
30-Minute Price & Breaking News Radar
30-Minute Top 50 Nasdaq 100 Options Radar
Daily 6:00 AM Multi-Market Earnings Radar
Hosting & Deployment Architecture
🧠 Core Features & Architecture
code
Text
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
│ • % Analyst Rprt │                           │ • Top 50 Options │                           │ • Mega & Mid-Cap │
│ • 24/7 Web Server│                           │   (5-Part Radar) │                           │   (US & TSX 🍁)  │
└──────────────────┘                           └──────────────────┘                           └──────────────────┘
📊 Dual-Engine Volume Pacing (Equities & Crypto)
Raw cumulative volume creates distorted readings when compared directly against full-day averages. Looney uses two specialized pacing engines to evaluate Relative Volume (RVOL) accurately:
1. Equities Institutional U-Curve Engine (Stocks & ETFs)
Market Hours (9:30 AM – 4:00 PM EST): Pacing factors scale along Wall Street's U-shaped intraday volume distribution curve.
Pre-Market, After-Hours & Weekends: Automatically defaults to 1.0x (100% full-day baseline), ensuring finished prior-session bars do not trigger false pre-market surge alerts.
2. 24/7 Continuous Crypto Volume Surfing Engine
00:00 UTC (8:00 PM EST) Daily Reset: Tracks elapsed minutes across the continuous 1,440-minute crypto day.
Early-Session Noise Buffer: Applies a 15-minute smoothing floor immediately after 00:00 UTC rollover to prevent false 100x alerts from initial trades while catching genuine early-session volume surges.
📈 Technical & Fundamental Indicator Guide
Every indicator in the !TICKER and $TICKER snapshot is calculated live:
1. Multi-Timeframe Volume Multipliers (RVOL)
What It Measures: Compares current time-paced volume against historical averages across 20-Day (1-Month), 50-Day (Quarterly), and 90-Day (Long-Term) benchmarks.
Benchmarks:
🔥 >= 2.0x (Unusual Surge): Heavy institutional accumulation or distribution.
⚡ >= 1.3x (Strong): Active institutional participation.
💤 < 0.6x (Low): Retail-only drift; low breakout conviction.
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
🟡 Counter-Trend Rebound: Price below 200D SMA but bouncing above 50D SMA.
4. MACD Momentum Verdict (12, 26, 9)
Evaluates MACD line versus signal line and tracks histogram expansion/contraction to determine whether directional momentum is expanding or slowing.
5. Floor Trader Pivot Points (S1 & R1)
Calculates key support (
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
) and resistance (
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
) levels based on previous session range, where 
P
=
H
+
L
+
C
3
P= 
3
H+L+C
​
 
.
6. Capital Efficiency, Cash Flow & Valuation Multiples
ROE (Return on Equity): Capital efficiency metric (💎 >= 20% denotes elite return).
Net Margin: Percentage of top-line revenue converted to net profit.
Solvency & Liquidity: Debt-to-Equity and Current Ratio.
Free Cash Flow (FCF) & Quality Ratio: Operating Cash Flow minus CapEx, verified by FCF / Net Income cash backing.
Valuation Multiples: Dual display of Trailing P/E and P/FCF (Price to Free Cash Flow) with clean growth and pre-profit status tags.
🎯 DFOL Options Strategy Engine Guide
When typing #TICKER or reviewing the scheduled Top 50 Options Radar, Looney applies official DFOL (Derivatives Fundamentals & Options Licensing) principles:
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
2. 30-Minute Top 50 Nasdaq 100 Options Radar (main.py)
Active Market Gate: Runs Monday through Friday, 9:32 AM to 4:00 PM EST.
9:32 AM Opening Bell Buffer: Automatically pauses until 9:32 AM EST at market open so the opening auction settles before computing options spreads.
Top 50 5-Part Paginated Delivery: Ranks the entire Nasdaq 100 by conviction score and automatically dispatches the Top 50 setups across 5 separate Discord messages (10 setups per part):
Part 1/5: Top Picks 1 – 10
Part 2/5: Top Picks 11 – 20
Part 3/5: Top Picks 21 – 30
Part 4/5: Top Picks 31 – 40
Part 5/5: Top Picks 41 – 50
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
Model 5:06 PM
ThinkingThoughts
Expand to view model thoughts

chevron_right
Here is the updated and corrected README.md reflecting all the latest features, the Top 100 Options Radar (10-Part Pagination), the Adaptive IPO & Fresh Listing Engine, the expanded S&P 100 & TSX 60 Master Universe, and the on-demand Today's Path intraday trails:
code
Markdown
# 🚀 Looney Market Intelligence Terminal

> **An institutional-grade, multi-asset quantitative intelligence bot and automated radar for Discord.**  
> Delivering real-time market snapshots, technical & balance sheet audits, adaptive DFOL options strategies, Wall Street/Bay Street research, 24/7 breaking news, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.

---

## ⚡ Quick Command Cheat Sheet

In any Discord channel where Looney is active, type one of the following triggers followed by any ticker symbol (e.g., `NVDA`, `AAPL`, `TSLA`, `TD.TO`, `RY.TO`, `SPCX`, `BTC-USD`):

| Trigger Prefix | Example | Command Name | What It Delivers |
| :--- | :--- | :--- | :--- |
| **`!`** or **`$`** | `!NVDA` or `$TD.TO` | **Market & Financial Health Snapshot** | Real-time technical indicators (RSI, MACD, SMAs, Pivots), time-paced institutional volume (RVOL), **🕒 Today's Path** intraday trail, balance sheet & cash flow audit, valuation multiples (P/E & P/FCF), and dividend schedules. |
| **`#`** | `#NVDA` or `#SPCX` | **Adaptive Options Deep-Dive** | Quant Confidence Score (0–100%), recommended DFOL options strategy, **Adaptive IPO/SPAC Engine** for fresh listings, and dual **7–14 DTE (Weekly Momentum)** vs. **30–45 DTE (Institutional Swing)** setups with exact strikes and break-even math. |
| **`%`** | `%NVDA` or `%RY.TO` | **Institutional Research Radar** | Real-time research notes, price target revisions, and rating actions from Tier-1 Wall Street (Goldman, Morgan Stanley, JPM) and Bay Street (RBC, TD, BMO, Scotia, CIBC) banks with direct source links. |

---

## 📖 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [Master Asset Universe (~225 Monitored Assets)](#-master-asset-universe-225-monitored-assets)
3. [Dual-Engine Volume Pacing (Equities & Crypto)](#-dual-engine-volume-pacing-equities--crypto)
4. [Technical & Fundamental Indicator Guide](#-technical--fundamental-indicator-guide)
5. [Adaptive DFOL Options Strategy Engine](#-adaptive-dfol-options-strategy-engine)
6. [Institutional Research Radar (`%`)](#-institutional-research-radar-)
7. [Automated Scheduled Radars](#-automated-scheduled-radars)
   * [30-Minute Price & Breaking News Radar](#1-30-minute-price--breaking-news-radar-mainpy)
   * [30-Minute Top 100 Market Options Radar](#2-30-minute-top-100-market-options-radar-mainpy)
   * [Daily 6:00 AM Multi-Market Earnings Radar](#3-daily-600-am-multi-market-earnings-radar-earningspy)
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
│  (Render 24/7)   │                           │ (30-Min Cronjob) │                           │ (Daily 6:00 AM)  │
├──────────────────┤                           ├──────────────────┤                           ├──────────────────┤
│ • !/$ Snapshot   │                           │ • Price Alerts   │                           │ • Scorecard      │
│ • 🕒 Today's Path│                           │ • Breaking News  │                           │ • Watchlist 45D  │
│ • # Options Play │                           │ • Top 100 Options│                           │ • Mega & Mid-Cap │
│ • % Analyst Rprt │                           │  (10-Part Radar) │                           │   (US & TSX 🍁)  │
│ • 24/7 Web Server│                           │                  │                           │                  │
└──────────────────┘                           └──────────────────┘                           └──────────────────┘
🌐 Master Asset Universe (~225 Monitored Assets)
Every 30 minutes, main.py scans a comprehensive cross-asset universe:
🪙 24/7 Cryptocurrencies (5): BTC-USD, ETH-USD, XRP-USD, SOL-USD, LINK-USD.
🛢️ Commodity & Index Futures (9): Gold (GC=F), Silver (SI=F), Crude Oil (CL=F), Brent (BZ=F), Natural Gas (NG=F), Nasdaq (NQ=F), S&P 500 (ES=F), Dow (YM=F), Russell (RTY=F).
📊 Major ETFs (12): SPY, QQQ, IWM, DIA, VOO, VTI, GLD, SLV, USO, BNO, IBIT, ETHA.
🇺🇸 S&P 500 (SPY) Top 100 & Nasdaq 100 Leaders (~140): All mega-cap tech, semiconductors, financial giants, consumer leaders, and high-beta growth stocks (NVDA, AAPL, MSFT, TSLA, PLTR, MSTR, IREN, RKLB, SPCX, etc.).
🍁 S&P/TSX 60 Canadian Blue-Chips (60): Big 6 Banks (RY.TO, TD.TO, etc.), Energy Titans (ENB.TO, CNQ.TO), Mining & Gold (ABX.TO, AEM.TO), and Canadian Tech (SHOP.TO, CSU.TO).
📊 Dual-Engine Volume Pacing (Equities & Crypto)
Raw cumulative volume creates distorted readings when compared directly against full-day averages. Looney uses two specialized pacing engines to evaluate Relative Volume (RVOL) accurately:
1. Equities Institutional U-Curve Engine (Stocks & ETFs)
Market Hours (9:30 AM – 4:00 PM EST): Pacing factors scale dynamically along Wall Street's U-shaped intraday volume distribution curve.
Pre-Market, After-Hours & Weekends: Automatically defaults to 1.0x (100% full-day baseline), ensuring finished prior-session bars do not trigger false pre-market surge alerts.
2. 24/7 Continuous Crypto Volume Surfing Engine
00:00 UTC (8:00 PM EST) Daily Reset: Tracks elapsed minutes across the continuous 1,440-minute crypto trading day.
Early-Session Noise Buffer: Applies a 15-minute smoothing floor immediately after 00:00 UTC rollover to prevent false volume alerts while catching genuine early-session volume surges.
📈 Technical & Fundamental Indicator Guide
Every indicator in the !TICKER and $TICKER snapshot is calculated live:
1. 🕒 Today's Path (Session Trails)
Pulls real-time step history recorded in alerts_state.json by automated market scans.
Formats step-by-step price action trails (e.g. `+2.15% ➔ +4.30%` ➔ **+5.10%**).
2. Multi-Timeframe Volume Multipliers (RVOL)
Compares current time-paced volume against historical averages across 20-Day (1-Month), 50-Day (Quarterly), and 90-Day (Long-Term) benchmarks.
🔥 
≥
≥
 2.0x (Unusual Surge): Heavy institutional accumulation or distribution.
⚡ 
≥
≥
 1.3x (Strong): Active institutional participation.
💤 < 0.6x (Low): Retail-only drift; low breakout conviction.
3. Multi-Timeframe RSI (Relative Strength Index)
Horizons: 7D (Fast/Scalp Momentum), 14D (Standard), 30D (Macro Trend).
🟢 50.0 – 68.0 (Bullish Trend): Momentum expanding with room to run.
🔴 32.0 – 48.0 (Bearish Trend): Downward momentum dominant.
⚠️ 
≥
≥
 70.0 (Overbought): Near-term pullback risk.
🟢 
≤
≤
 30.0 (Oversold): High probability relief bounce zone.
4. Moving Averages & Structural Trend (50D & 200D SMA)
🟢 Strong Bullish Uptrend: Price above both 50D & 200D SMA (Institutional Support).
🔴 Strong Bearish Downtrend: Price below both 50D & 200D SMA (Institutional Selling).
🟡 Pullback in Macro Uptrend: Price above 200D SMA but testing 50D SMA.
🟡 Counter-Trend Rebound: Price below 200D SMA but bouncing above 50D SMA.
Young / IPO Listings: Automatically displays Listing Average ($X.XX) over available days.
5. Floor Trader Pivot Points (S1 & R1)
Calculates key support (
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
) and resistance (
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
) levels based on previous session range, where 
P
=
H
+
L
+
C
3
P= 
3
H+L+C
​
 
.
6. Capital Efficiency, Cash Flow & Valuation Multiples
ROE (Return on Equity): Capital efficiency metric (💎 
≥
20
%
≥20%
 denotes elite return).
Net Margin: Percentage of top-line revenue converted to net profit.
Solvency & Liquidity: Debt-to-Equity and Current Ratio.
Free Cash Flow (FCF) & Quality Ratio: Operating Cash Flow minus CapEx, verified by FCF / Net Income cash backing.
Valuation Multiples: Dual display of Trailing P/E and P/FCF (Price to Free Cash Flow).
🎯 Adaptive DFOL Options Strategy Engine
When typing #TICKER or reviewing the scheduled Top 100 Options Radar, Looney applies official DFOL (Derivatives Fundamentals & Options Licensing) principles:
1. 100-Point Quantitative Conviction Matrix
code
Text
[ 100-Point Scoring Algorithm ]
 ├── 25 pts: Trend Alignment (Price vs. 50D & 200D SMA or Listing Baseline)
 ├── 20 pts: RSI Momentum Sweet Spot (52–68 Bullish / 32–48 Bearish)
 ├── 20 pts: MACD Directional Momentum & Histogram Expansion
 ├── 15 pts: Time-Paced RVOL (Volume Confirmation >= 1.3x)
 └── 20 pts: Implied Volatility Match (DFOL Strategy Selection)
🟢 
≥
≥
 80% (High Conviction): High technical and volatility alignment.
🟠 60% – 79% (Developing / Watchlist): Solid setup pending confirmation.
🔴 < 60% (Low Conviction / Avoid): Conflicting signals or poor risk/reward.
2. Adaptive IPO & Fresh Listing Engine
No Historical Data Rejections: Analyzes listings with as few as 3 trading days of history.
Synchronized Candle Scrubbing: Eliminates null candle gaps to prevent array index errors on illiquid or newly-listed tickers (SPCX, fresh SPACs, IPOs).
Elastic Volatility & ATR: Dynamically sizes strike intervals based on actual trading range.
3. Strategy Selection Matrix
Directional Bias	IV Environment	Selected DFOL Strategy	Execution Setup
Outright Bullish	Low IV (< 40%)	Long Call	Buy 30–45 DTE Call (Delta ~ 0.65–0.70)
Moderately Bullish	Moderate IV (30–50%)	Bull Call Debit Spread	Buy ATM Call / Sell OTM Call
Neutral to Bullish	High IV (> 50%)	Bull Put Credit Spread	Sell OTM Put at S1 / Buy Lower Put
Outright Bearish	Low IV (< 40%)	Long Put	Buy 30–45 DTE Put (Delta ~ -0.65–0.70)
Moderately Bearish	Moderate IV (30–50%)	Bear Put Debit Spread	Buy ATM Put / Sell OTM Put
Neutral to Bearish	High IV (> 50%)	Bear Call Credit Spread	Sell OTM Call at R1 / Buy Higher Call
🏛️ Institutional Research Radar (%)
Typing %TICKER performs a multi-source scan across major financial news wires and research desks:
Wall Street 🇺🇸: Goldman Sachs, Morgan Stanley, JPMorgan Chase, Bank of America, Wells Fargo, Citigroup, Barclays, UBS, Deutsche Bank, Jefferies, Piper Sandler, Wedbush, Evercore ISI, Baird, Stifel, Wolfe Research.
Bay Street 🍁: RBC Capital Markets, TD Cowen / TD Securities, BMO Capital Markets, Scotiabank Global, CIBC World Markets, National Bank Financial, Desjardins.
Smart Disambiguation: Differentiates between subject company tickers and research notes authored by bank analysts.
Automatic Multi-Part Pagination: Splits large research sets into clean batches of 4 per Discord embed card with source hyperlinks.
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
