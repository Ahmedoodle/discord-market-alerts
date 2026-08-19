import os
import time
import json
import re
import concurrent.futures
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import pandas as pd

# Webhook & Branding
DISCORD_EARNINGS_WEBHOOK_URL = os.getenv(
    "DISCORD_EARNINGS_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1539761350920642660/cDXOzG5Unsic7mcUrYS6KJK8evjolwQP0LSqs5ydvEFvnoXT-6djPpGj5VHM9czqRfrI"
)
BOT_NAME = "Looney"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

STATE_FILE = "earnings_state.json"
NY_TZ = ZoneInfo("America/New_York")

# Your Curated Watchlist
WATCHLIST = [
    "NVDA", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML", "CBRS", "SKHY", 
    "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META", "NBIS", "ORCL", "RBLX",
    "MSTR", "IREN", "BLSH", "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "SHOP.TO"
]

# Expanded Market Universes (US 🇺🇸 & Canada 🍁)
UNIVERSE_MEGA_US = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "CRM", 
    "ORCL", "AMD", "QCOM", "ADBE", "NFLX", "INTC", "CSCO", "TXN", "IBM", "NOW", "AMAT"
]
UNIVERSE_MEGA_CA = [
    "RY.TO", "TD.TO", "CNR.TO", "CP.TO", "BNS.TO", "BMO.TO", "ENB.TO", "TRP.TO", 
    "SHOP.TO", "CSU.TO", "BAM.TO", "MFC.TO", "SU.TO", "CNQ.TO", "ATD.TO"
]

UNIVERSE_MID_US = [
    "MDB", "CRWD", "AFRM", "ZS", "NET", "DDOG", "SNOW", "RBLX", "PLTR", "COIN", 
    "DASH", "RKLB", "IREN", "DUOL", "SMCI", "APP", "PINS", "PATH", "CELH", "SYM"
]
UNIVERSE_MID_CA = [
    "KXS.TO", "OTEX.TO", "WCN.TO", "GIB-A.TO", "LSPD.TO", "NVEI.TO", "TFII.TO", 
    "CAE.TO", "TOU.TO", "DOL.TO", "WPM.TO", "FM.TO"
]

UNIVERSE_SMALL_US = [
    "SOUN", "BBAI", "ASTS", "ACHR", "JOBY", "IONQ", "RGTI", "BLSH", "CBRS", 
    "NBIS", "HIMS", "CLOV", "PLUG", "MARA", "RIOT", "CLSK", "CIFR", "WULF"
]
UNIVERSE_SMALL_CA = [
    "HUT.TO", "BITF.TO", "HIVE.TO", "DMGI.TO", "NXT.TO", "GLXY.TO", "BB.TO", "WELL.TO"
]

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
})

def format_large_number(num):
    if num is None or pd.isna(num):
        return "N/A"
    try:
        num = float(num)
        if num >= 1e12:
            return f"${num / 1e12:.2f}T"
        elif num >= 1e9:
            return f"${num / 1e9:.2f}B"
        elif num >= 1e6:
            return f"${num / 1e6:.1f}M"
        return f"${num:,.0f}"
    except Exception:
        return "N/A"

def get_country_badge(ticker_symbol):
    return "🍁" if ".TO" in ticker_symbol or ".V" in ticker_symbol else "🇺🇸"

def fetch_single_ticker_earnings(ticker_symbol):
    """Pulls next earnings date, estimates, and previous beat %."""
    if any(ticker_symbol.endswith(ext) for ext in ["-USD", "=F"]):
        return None

    try:
        t_obj = yf.Ticker(ticker_symbol, session=http_session)
        country_badge = get_country_badge(ticker_symbol)
        
        short_name = ticker_symbol
        try:
            short_name = t_obj.fast_info.name or ticker_symbol
        except Exception:
            pass

        ed_df = None
        try:
            ed_df = t_obj.earnings_dates
        except Exception:
            pass

        upcoming_date = None
        days_away = None
        is_confirmed = False
        time_badge = "After Close 🌙"
        eps_est = None
        prev_quarter_str = "N/A"
        today = datetime.now(NY_TZ).date()

        if ed_df is not None and not ed_df.empty:
            future_mask = ed_df['Reported EPS'].isna() if 'Reported EPS' in ed_df.columns else pd.Series([True]*len(ed_df), index=ed_df.index)
            future_df = ed_df[future_mask]

            if not future_df.empty:
                nxt_idx = future_df.index[0]
                nxt_dt = nxt_idx.tz_convert(NY_TZ) if hasattr(nxt_idx, "tz_convert") and nxt_idx.tz else (nxt_idx.to_pydatetime() if hasattr(nxt_idx, "to_pydatetime") else nxt_idx)
                nxt_d = nxt_dt.date() if isinstance(nxt_dt, datetime) else nxt_dt
                
                if nxt_d >= today:
                    upcoming_date = nxt_d
                    days_away = (nxt_d - today).days
                    is_confirmed = True
                    time_badge = "Before Open 🌅" if getattr(nxt_dt, "hour", 16) < 12 else "After Close 🌙"
                    
                    if "EPS Estimate" in future_df.columns:
                        val = future_df["EPS Estimate"].iloc[0]
                        eps_est = f"${float(val):.2f}" if pd.notna(val) else None

            past_mask = ed_df['Reported EPS'].notna() if 'Reported EPS' in ed_df.columns else pd.Series([False]*len(ed_df), index=ed_df.index)
            past_df = ed_df[past_mask]
            if not past_df.empty:
                p_dt = past_df.index[0]
                p_eps = past_df['Reported EPS'].iloc[0]
                p_surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None
                
                p_dt_str = p_dt.strftime("%b %Y") if hasattr(p_dt, "strftime") else "Prev Q"
                surp_str = ""
                if pd.notna(p_surp):
                    raw_s = float(p_surp)
                    surp_val = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                    tag = "🎯" if surp_val >= 0 else "⚠️"
                    surp_str = f" • Beat by `{surp_val:+.1f}% {tag}`"
                
                prev_quarter_str = f"`{p_dt_str}` (EPS: `${float(p_eps):.2f}`{surp_str})"

        # Fallback to calendar
        if upcoming_date is None:
            try:
                cal = t_obj.calendar
                if cal is not None:
                    ed_val = cal.get("Earnings Date") if isinstance(cal, dict) else (cal.loc["Earnings Date"].values if hasattr(cal, "loc") and "Earnings Date" in cal.index else None)
                    if ed_val is not None and len(ed_val) > 0:
                        t_ed = ed_val[0]
                        nxt_d = t_ed.date() if isinstance(t_ed, datetime) else t_ed
                        if nxt_d >= today:
                            upcoming_date = nxt_d
                            days_away = (nxt_d - today).days
                            is_confirmed = False
            except Exception:
                pass

        if upcoming_date is None:
            return None

        est_parts = []
        est_parts.append(f"EPS: `{eps_est}`" if eps_est else "EPS: `Est. Pending`")
        
        try:
            rev_raw = t_obj.fast_info.revenue or None
            if rev_raw:
                est_parts.append(f"Revenue: `{format_large_number(rev_raw / 4)}`")
        except Exception:
            pass

        consensus_est_str = " | ".join(est_parts)
        status_badge = "Official / Confirmed 🟢" if is_confirmed else "Projected Estimate 🟡"

        return {
            "ticker": ticker_symbol,
            "name": short_name,
            "badge": country_badge,
            "date": upcoming_date,
            "days_away": days_away,
            "date_str": upcoming_date.strftime("%b %d, %Y"),
            "time_badge": time_badge,
            "status": status_badge,
            "consensus_est": consensus_est_str,
            "actual_reported": "Pending ⏳",
            "prev_quarter": prev_quarter_str
        }

    except Exception:
        return None

def fetch_yesterday_reported_scorecard(all_symbols):
    """Pulls reported actuals, beats/misses, and stock moves from the last 1-2 trading days."""
    scorecard_items = []
    today = datetime.now(NY_TZ).date()
    
    # Check yesterday (or Friday & Thursday if running on Monday)
    target_dates = [today - timedelta(days=i) for i in (range(1, 4) if today.weekday() == 0 else range(1, 2))]

    for ticker_symbol in all_symbols:
        if any(ticker_symbol.endswith(ext) for ext in ["-USD", "=F"]):
            continue
        try:
            t_obj = yf.Ticker(ticker_symbol, session=http_session)
            ed_df = t_obj.earnings_dates
            if ed_df is not None and not ed_df.empty:
                past_df = ed_df[ed_df['Reported EPS'].notna()]
                if not past_df.empty:
                    rep_idx = past_df.index[0]
                    rep_dt = rep_idx.tz_convert(NY_TZ) if hasattr(rep_idx, "tz_convert") and rep_idx.tz else (rep_idx.to_pydatetime() if hasattr(rep_idx, "to_pydatetime") else rep_idx)
                    rep_d = rep_dt.date() if isinstance(rep_dt, datetime) else rep_dt
                    
                    if rep_d in target_dates:
                        actual_eps = past_df['Reported EPS'].iloc[0]
                        est_eps = past_df['EPS Estimate'].iloc[0] if 'EPS Estimate' in past_df.columns else None
                        surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None
                        
                        move_str = "N/A"
                        try:
                            hist = t_obj.history(period="2d")
                            if len(hist) >= 2:
                                p0 = hist['Close'].iloc[-2]
                                p1 = hist['Close'].iloc[-1]
                                chg = ((p1 - p0) / p0) * 100
                                move_str = f"`{chg:+.2f}%` {'🚀' if chg >= 0 else '🔻'}"
                        except Exception:
                            pass

                        surp_str = ""
                        if pd.notna(surp):
                            raw_s = float(surp)
                            surp_v = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                            tag = "🎯" if surp_v >= 0 else "⚠️"
                            surp_str = f" (**Beat by `{surp_v:+.1f}%` {tag}**)" if surp_v >= 0 else f" (**Missed by `{surp_v:+.1f}%` {tag}**)"

                        scorecard_items.append({
                            "ticker": ticker_symbol,
                            "name": t_obj.fast_info.name or ticker_symbol,
                            "badge": get_country_badge(ticker_symbol),
                            "reported_date": rep_d.strftime("%b %d, %Y"),
                            "time_badge": "After Close 🌙" if getattr(rep_dt, "hour", 16) >= 12 else "Before Open 🌅",
                            "eps_line": f"Actual: `${float(actual_eps):.2f}` | Estimate: `${float(est_eps):.2f}`{surp_str}" if pd.notna(est_eps) else f"Actual: `${float(actual_eps):.2f}`",
                            "move_str": move_str
                        })
        except Exception:
            pass

    return scorecard_items

def format_earnings_entry(idx, item):
    return (
        f"**{idx}. {item['ticker']} — {item['name']}** {item['badge']}\n"
        f"• **Date & Time:** `{item['date_str']} (In {item['days_away']} Days)` • **{item['time_badge']}**\n"
        f"• **Status:** `{item['status']}`\n"
        f"• **Consensus Estimate:** {item['consensus_est']}\n"
        f"• **Actual Reported:** `{item['actual_reported']}`\n"
        f"• **Previous Quarter:** {item['prev_quarter']}\n"
    )

def dispatch_discord_earnings_embed(title, description, entries_text, color=3447003):
    if not DISCORD_EARNINGS_WEBHOOK_URL:
        return

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": title,
            "description": f"{description}\n\n{entries_text}",
            "color": color,
            "footer": {"text": "Looney • Daily 6:00 AM Earnings Intelligence"}
        }]
    }
    try:
        res = requests.post(DISCORD_EARNINGS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        time.sleep(0.5)
    except Exception as e:
        print(f"Error sending earnings embed: {e}")

# ====================================================================
# MAIN RUNNER (Executes Daily at 6:00 AM EST)
# ====================================================================
def run_earnings_daily():
    now_ny = datetime.now(NY_TZ)
    today_str = now_ny.strftime("%A, %B %d, %Y")
    print(f"[{now_ny.strftime('%I:%M:%S %p %Z')}] Starting Daily 6:00 AM Earnings Radar for {today_str}...\n")

    # Step 1: Scan Watchlist (Next 30 Days)
    print("1. Scanning Watchlist Earnings (Next 30 Days)...")
    watchlist_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for r in executor.map(fetch_single_ticker_earnings, WATCHLIST):
            if r and r["days_away"] <= 30:
                watchlist_results.append(r)
    watchlist_results.sort(key=lambda x: x["date"])

    # Step 2: Scan Mega-Caps (Next 30 Days)
    print("2. Scanning Mega-Cap Universe (Next 30 Days)...")
    mega_us, mega_ca = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_MEGA_US):
            if r and r["days_away"] <= 30:
                mega_us.append(r)
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_MEGA_CA):
            if r and r["days_away"] <= 30:
                mega_ca.append(r)
    mega_us.sort(key=lambda x: x["date"])
    mega_ca.sort(key=lambda x: x["date"])

    # Step 3: Scan Mid-Caps (Next 14 Days)
    print("3. Scanning Mid-Cap Universe (Next 14 Days)...")
    mid_us, mid_ca = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_MID_US):
            if r and r["days_away"] <= 14:
                mid_us.append(r)
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_MID_CA):
            if r and r["days_away"] <= 14:
                mid_ca.append(r)
    mid_us.sort(key=lambda x: x["date"])
    mid_ca.sort(key=lambda x: x["date"])

    # Step 4: Scan Small-Caps (Next 14 Days)
    print("4. Scanning Small-Cap Universe (Next 14 Days)...")
    small_us, small_ca = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_SMALL_US):
            if r and r["days_away"] <= 14:
                small_us.append(r)
        for r in executor.map(fetch_single_ticker_earnings, UNIVERSE_SMALL_CA):
            if r and r["days_away"] <= 14:
                small_ca.append(r)
    small_us.sort(key=lambda x: x["date"])
    small_ca.sort(key=lambda x: x["date"])

    # Step 5: Master Scorecard Lookback across 120+ companies
    print("5. Generating Yesterday's Reported Actuals Scorecard across 120+ tickers...")
    all_symbols_master = list(set(WATCHLIST + UNIVERSE_MEGA_US + UNIVERSE_MEGA_CA + UNIVERSE_MID_US + UNIVERSE_MID_CA + UNIVERSE_SMALL_US + UNIVERSE_SMALL_CA))
    scorecard_items = fetch_yesterday_reported_scorecard(all_symbols_master)

    # =================================================================
    # DISPATCH ALL CARDS TO DISCORD
    # =================================================================
    print("\nDispatching formatted cards to Earnings Channel...")

    # CARD 1: Yesterday's Scorecard
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items, 1):
            scorecard_txt += (
                f"**{i}. {sc['ticker']} — {sc['name']}** {sc['badge']}\n"
                f"• **Reported Time:** `{sc['reported_date']} ({sc['time_badge']})`\n"
                f"• **EPS Result:** {sc['eps_line']}\n"
                f"• **Market Reaction:** Stock Move: {sc['move_str']}\n"
                f"• **Status:** `Official SEC/TSX Filing 🟢`\n\n"
            )
        dispatch_discord_earnings_embed(
            title="📢 Yesterday's Reported Earnings Scorecard [ACTUALS & BEATS/MISSES]",
            description="*Official results and price reactions from the previous business day (Auto-clears on Day 2).* ",
            entries_text=scorecard_txt,
            color=15844367  # Gold
        )

    # CARD 2: Watchlist (Next 30 Days)
    if watchlist_results:
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results, 1)])
        dispatch_discord_earnings_embed(
            title="🗓️ Watchlist Earnings Calendar [NEXT 30 DAYS]",
            description=f"*Sorted by nearest report date across your personal watchlist as of {today_str}.*",
            entries_text=wl_txt,
            color=3066993  # Green
        )

    # CARD 3: Mega-Caps (Next 30 Days)
    mega_combined = mega_us + mega_ca
    if mega_combined:
        mega_txt = ""
        if mega_us:
            mega_txt += "**🇺🇸 UNITED STATES MEGA-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_us, 1)]) + "\n\n"
        if mega_ca:
            mega_txt += "**🇨🇦 CANADIAN MEGA-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_ca, 1)])
        dispatch_discord_earnings_embed(
            title="👑 Mega-Cap Earnings Calendar [NEXT 30 DAYS — ≥ $200B]",
            description="*Major market-moving corporate reports over the next month.*",
            entries_text=mega_txt,
            color=10181046  # Purple
        )

    # CARD 4: Mid-Caps (Next 14 Days)
    mid_combined = mid_us + mid_ca
    if mid_combined:
        mid_txt = ""
        if mid_us:
            mid_txt += "**🇺🇸 UNITED STATES MID-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_us, 1)]) + "\n\n"
        if mid_ca:
            mid_txt += "**🇨🇦 CANADIAN MID-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca, 1)])
        dispatch_discord_earnings_embed(
            title="📈 Mid-Cap Earnings Calendar [NEXT 14 DAYS — $2B - $10B]",
            description="*High-growth momentum leaders reporting in the next two weeks.*",
            entries_text=mid_txt,
            color=3447003  # Blue
        )

    # CARD 5: Small-Caps (Next 14 Days)
    small_combined = small_us + small_ca
    if small_combined:
        small_txt = ""
        if small_us:
            small_txt += "**🇺🇸 UNITED STATES SMALL-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_us, 1)]) + "\n\n"
        if small_ca:
            small_txt += "**🇨🇦 CANADIAN SMALL-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_ca, 1)])
        dispatch_discord_earnings_embed(
            title="🌱 Small-Cap Earnings Calendar [NEXT 14 DAYS — High Volatility]",
            description="*Active small-cap runners and potential earnings squeeze movers.*",
            entries_text=small_txt,
            color=15105570  # Orange
        )

    print("\n=======================================================")
    print(f"Earnings Intelligence Report Dispatched Successfully for {today_str}!")

if __name__ == "__main__":
    run_earnings_daily()
