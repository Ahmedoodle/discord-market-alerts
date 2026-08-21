# 🚀 Looney Market Intelligence Terminal

> **An institutional-grade, multi-asset quantitative intelligence bot and automated radar for Discord.**  
> Delivering real-time market snapshots, technical & balance sheet audits, DFOL options strategies, Wall Street/Bay Street research, 24/7 breaking news, and multi-tier earnings intelligence across US 🇺🇸 and Canadian 🍁 markets.

---

## ⚡ Quick Command Cheat Sheet

In any Discord channel where Looney is active, simply type one of the following triggers followed by any ticker symbol (e.g., `NVDA`, `AAPL`, `TSLA`, `TD.TO`, `RY.TO`, `BTC-USD`):

| Trigger Prefix | Example | Command Name | What It Delivers |
| :--- | :--- | :--- | :--- |
| **`!`** or **`$`** | `!NVDA` or `$TD.TO` | **Market & Financial Health Snapshot** | Complete technical analysis (RSI, MACD, SMAs, Pivots), institutional volume (RVOL), balance sheet & cash flow audit, and dividend schedule (Ex-Date & Pay Date). |
| **`#`** | `#NVDA` or `#TSLA` | **Options Strategy Deep-Dive** | Quant Confidence Score (0–100%), recommended DFOL options strategy, and dual **7–14 DTE (Weekly)** vs. **30–45 DTE (Monthly)** trade setups with exact strikes and break-even math. |
| **`%`** | `%NVDA` or `%RY.TO` | **Institutional Research Radar** | Real-time research notes, price target revisions, and rating actions from Tier-1 Wall Street (Goldman, Morgan Stanley, JPM) and Bay Street (RBC, TD, BMO, Scotia, CIBC) banks with direct article links. |

---

## 📖 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [Technical & Fundamental Indicator Guide](#-technical--fundamental-indicator-guide)
3. [DFOL Options Strategy Engine Guide](#-dfol-options-strategy-engine-guide)
4. [Institutional Research Radar (`%`)](#-institutional-research-radar-)
5. [Automated Scheduled Radars](#-automated-scheduled-radars)
   * [30-Minute Price & Breaking News Radar](#1-30-minute-price--breaking-news-radar)
   * [30-Minute Top 10 Nasdaq 100 Options Radar](#2-30-minute-top-10-nasdaq-100-options-radar)
   * [Daily 6:00 AM Multi-Market Earnings Radar](#3-daily-600-am-multi-market-earnings-radar)
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
│ • # Options Play │                           │ • Breaking News  │                           │ • Watchlist 45D  │
│ • % Analyst Rprt │                           │ • Top 10 Options │                           │ • Mega & Mid-Cap │
│ • 24/7 Web Server│                           │   (9:32am-4:00pm)│                           │   (US & TSX 🍁)  │
└──────────────────┘                           └──────────────────┘                           └──────────────────┘
📊 Technical & Fundamental Indicator Guide
Every indicator in the !SYMBOL and $SYMBOL snapshot is calculated in real-time from raw market prints and SEC/SEDAR filings:
1. Volume Multipliers (RVOL)
What It Measures: Compares current trading volume against historical benchmarks to detect institutional accumulation or distribution.
How It's Calculated: RVOL = Today's Volume / Average Volume over Period across 20-Day (1-Month), 50-Day (Quarterly), and 90-Day (Long-Term) windows.
What to Watch For:
🔥 >= 2.0x (Unusual Surge): Heavy institutional block trading / catalyst in play.
⚡ >= 1.3x (Strong): Active institutional participation.
💤 < 0.6x (Low): Retail-only drift; low breakout reliability.
2. Multi-Timeframe RSI (Relative Strength Index)
What It Measures: Internal momentum and velocity of price changes across 3 separate horizons (7D Fast/Scalp, 14D Standard, 30D Macro).
How It's Calculated: RSI = 100 - (100 / (1 + RS)) where RS = Average Gain / Average Loss.
What to Watch For:
🟢 50 to 68 (Bullish Acceleration Zone): Strong upward momentum with room to run before hitting exhaustion.
🔴 32 to 48 (Bearish Breakdown Zone): Downward momentum expanding.
⚠️ >= 70 (Overbought): High risk of near-term mean reversion/pullback.
🟢 <= 30 (Oversold): High probability of bounce/relief rally.
3. Moving Averages & Trend Verdict (50D & 200D SMA)
What It Measures: The health of the intermediate trend (50-Day Simple Moving Average) and macro structural trend (200-Day Simple Moving Average).
Trend Classifications:
🟢 Strong Bullish Uptrend: Price above both 50D & 200D SMA (Institutional Buying).
🔴 Strong Bearish Downtrend: Price below both 50D & 200D SMA (Institutional Selling).
🟡 Pullback in Macro Uptrend: Price above 200D SMA but below 50D SMA (Support Test).
🟡 Counter-Trend Rebound: Price below 200D SMA but above 50D SMA (Bear Market Bounce).
4. MACD (12, 26, 9)
What It Measures: Exponential moving average convergence/divergence and momentum histogram expansion.
What to Watch For:
Bullish Momentum Expanding 🟢: MACD line above Signal line with growing positive histogram bars (increasing buying velocity).
Bullish Momentum Slowing 🟡: MACD line above Signal line but histogram bars shrinking (momentum peaking).
Bearish Momentum Expanding 🔴: MACD line below Signal line with growing negative histogram bars (accelerating downside).
5. Key Pivot Levels (S1 & R1)
How It's Calculated: Classic Floor Trader Pivot Points from previous day's High (H), Low (L), and Close (C):
Pivot Point (P) = (H + L + C) / 3
Resistance 1 (R1) = (2 * P) - L
Support 1 (S1) = (2 * P) - H
What to Watch For: Key intraday bounce zones (S1) and profit-taking/rejection zones (R1).
6. Smart Money & Risk Metrics (Beta & ATR)
Beta vs. SPY: Measures volatility relative to the broader S&P 500 benchmark.
Beta >= 1.5x: High volatility asset (large swings; high reward/risk).
Beta < 0.8x: Defensive asset (lower volatility than index).
14D ATR (Average True Range): Calculates the average expected daily dollar move (+/- $ and +/- %).
7. Multi-Market Dividend Engine
What It Delivers:
Yield & Payout: Current annual dividend yield %, dollar amount per payout, and annualized payout.
Frequency: Monthly (12x/yr), Quarterly (4x/yr), Semi-Annual (2x/yr), or Annual (1x/yr).
Key Dates: Official Ex-Dividend Date (date you must own shares by) and Pay Date (distribution date).
Sustainability Payout Ratio:
🟢 <= 50%: Highly Secure (Strong cash flow backing).
🟡 51% - 75%: Moderate payout.
⚠️ > 75%: Elevated payout / high-yield risk.
8. Balance Sheet & Cash Flow Audit (YoY Aligned)
ROE (Return on Equity): (TTM Net Income / Stockholders' Equity) * 100. (💎 >= 20% denotes elite capital efficiency).
Net Profit Margin: (TTM Net Income / TTM Total Revenue) * 100.
Debt-to-Equity: Total Debt / Stockholders' Equity. (< 0.6x is low debt; > 1.5x is high leverage).
Current Ratio: Current Assets / Current Liabilities. (> 1.5x indicates strong short-term liquidity).
Free Cash Flow (FCF): Operating Cash Flow - Capital Expenditures (CapEx).
Earnings Quality Ratio: TTM Free Cash Flow / TTM Net Income.
🟢 >= 1.0x: High quality (real cash profits exceed accounting net income).
⚠️ < 0.6x: Accrual/paper-heavy earnings.
🎯 DFOL Options Strategy Engine Guide
When typing #SYMBOL or reviewing the Top 10 Options Radar, the bot acts as a licensed Derivatives Specialist applying official DFOL (Derivatives Fundamentals & Options Licensing) principles:
1. The Quant Confidence Scoring Matrix (0–100 Points)
code
Text
[ 100-Point Scoring Algorithm ]
 ├── 25 pts: Trend Alignment (Price vs. 50D & 200D SMA)
 ├── 20 pts: RSI Momentum Sweet Spot (52–68 Bullish / 32–48 Bearish)
 ├── 20 pts: MACD Histogram Expansion in Trade Direction
 ├── 15 pts: Institutional Volume Multiplier (RVOL >= 1.3x)
 └── 20 pts: Implied Volatility Match (DFOL Strategy Selection)
🟢 >= 80% (High Conviction): Pristine multi-indicator and volatility alignment.
🟠 60% - 79% (Developing / Watchlist): Solid setup pending a key breakout or confirmation.
🔴 < 60% (Low Conviction / Avoid): Choppy, conflicting indicators, or unfavorable risk/reward.
2. Strategy Decision Matrix
The bot checks Directional Bias and Implied Volatility (IV Rank) to select the mathematical optimal strategy:
Market Bias	IV Environment	Selected DFOL Strategy	Target Setup
Outright Bullish	Low IV (< 40%)	Long Call	Buy 30–45 DTE Call (Delta ~ 0.65–0.70)
Moderately Bullish	Moderate IV (30–50%)	Bull Call Debit Spread	Buy ATM Call (Delta ~ 0.60) / Sell OTM Call (Delta ~ 0.30)
Neutral to Bullish	High IV (> 50%)	Bull Put Credit Spread	Sell OTM Put at S1 (Delta ~ 0.25) / Buy OTM Put (Delta ~ 0.15)
Outright Bearish	Low IV (< 40%)	Long Put	Buy 30–45 DTE Put (Delta ~ -0.65–0.70)
Moderately Bearish	Moderate IV (30–50%)	Bear Put Debit Spread	Buy ATM Put (Delta ~ -0.60) / Sell OTM Put (Delta ~ -0.30)
Neutral to Bearish	High IV (> 50%)	Bear Call Credit Spread	Sell OTM Call at R1 (Delta ~ 0.25) / Buy OTM Call (Delta ~ 0.15)
Neutral / Rangebound	High IV (> 60%)	Iron Condor / Short Strangle	Sell OTM Put below S1 + Sell OTM Call above R1
Breakout Expected	Low IV (< 20%)	Long Straddle / Strangle	Buy ATM Call + Buy ATM Put (Vol expansion)
3. DFOL Break-Even Golden Rules
All break-evens are calculated using official DFOL rules:
Bullish Debit (Call): Break-Even = Strike + Net Premium Paid
Bearish Debit (Put): Break-Even = Strike - Net Premium Paid
Bullish Credit (Bull Put Spread): Break-Even = Short Put Strike - Net Credit Received (RRR Rule)
Bearish Credit (Bear Call Spread): Break-Even = Short Call Strike + Net Credit Received (RRR Rule)
4. Dual Timeframe Execution
Every #SYMBOL query delivers two distinct plans:
⚡ Play A (7–14 DTE): Fast scalp / weekly momentum play. (Target exit: +50% to +80%; Stop-loss: -35%).
🏛️ Play B (30–45 DTE): Standard institutional swing play. (Target exit: +40% to +60%; Trailing stop at 50D SMA).
🏛️ Institutional Research Radar (%)
Typing %SYMBOL triggers a live search across major financial news wires and research desks:
Tier-1 Coverage Filter: Automatically searches for and extracts rating actions from:
🇺🇸 Wall Street: Goldman Sachs, Morgan Stanley, JPMorgan, Bank of America, Wells Fargo, Citigroup, Barclays, UBS, Deutsche Bank, Jefferies, Piper Sandler, Wedbush, Rosenblatt, Wolfe Research.
🍁 Bay Street: RBC Capital Markets, TD Cowen / TD Securities, BMO Capital Markets, Scotiabank Global Banking, CIBC World Markets, National Bank Financial.
Automated Categorization:
🟢 Bullish / High Target Reports: Price target raises, Outperform, Conviction Buys.
🟡 Neutral / Reiteration Reports: Hold, Equal-Weight, Market Perform, valuation re-evaluations.
🔴 Cautious / Downgrade Reports: Underperform, Sell, price target cuts.
Direct Hyperlinks: Includes direct links to the source research notes.
⏰ Automated Scheduled Radars
1. 30-Minute Price & Breaking News Radar
Script: main.py (Runs every 30 minutes via Cron).
Price Action Alerts: Scans all watchlist equities, commodities, and 24/7 crypto. Dispatches embed if price moves exceed threshold (+/- 2.0% regular, +/- 1.0% pre/after-market) with full institutional indicators and intraday path trail (1.50% -> 3.20%).
Breaking News: Scans RSS and search feeds; dispatches articles < 45 minutes old with deduplication memory.
2. 30-Minute Top 10 Nasdaq 100 Options Radar
Script: main.py
Operating Hours: Monday through Friday, 9:32 AM to 4:00 PM EST (Strictly during live options market trading).
9:32 AM Opening Bell Buffer: Automatically pauses until 9:32 AM EST at market open so the opening auction settles before calculating options spreads.
Output: Ranks the entire Nasdaq 100 and sends the Top 10 highest-conviction option setups with dual 7–14 DTE and 30–45 DTE plans.
3. Daily 6:00 AM Multi-Market Earnings Radar
Script: earnings.py (Runs Monday–Friday at 6:00 AM EST).
Card 1: 📢 Yesterday's Scorecard: Official reported actuals, estimates, beats/misses, and stock moves across US and TSX listings. (Hierarchically ordered: 🍁 CAD Mega -> 🇺🇸 US Mega -> 🍁 CAD Mid -> 🇺🇸 US Mid).
Card 2: 🗓️ Watchlist Calendar (Next 45 Days): Upcoming reports across personal watchlist.
Card 3A & 3B: 👑 Mega-Caps (Next 45 Days — >= $200B): Dedicated Canadian TSX and US Mega-Cap cards.
Card 4A: 🍁 Canadian Mid-Caps (Next 45 Days — $1.5B - $200B): 100% complete coverage of Canadian mid-caps.
Card 4B: 📈 US Mid-Caps (Next 7 Days — $1.5B - $200B): Paginated in clean batches of 15 (Part 1/X, Part 2/X).
