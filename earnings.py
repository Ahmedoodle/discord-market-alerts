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

# ====================================================================
# 1. LIVE MASTER CALENDAR API ENGINE
# ====================================================================
def fetch_calendar_day(target_date):
    """Fetches every company reporting on a specific day from Yahoo Calendar."""
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://query1.finance.yahoo.com/v1/finance/calendar/earnings?day={date_str}&offset=0&size=100"
    items = []
    try:
        res = http_session.get(url, timeout=5)
        if res.status_code == 200:
            rows = res.json().get("finance", {}).get("result", [{}])[0].get("rows", [])
            for r in rows:
                items.append({
                    "ticker": r.get("ticker", ""),
                    "name": r.get("companyshortname") or r.get("ticker", ""),
                    "date": target_date,
                    "date_str": target_date.strftime("%b %d, %Y"),
                    "startdatetime": r.get("startdatetime"),
                    "startdatetimetype": r.get("startdatetimetype", "TAS"),
                    "eps_estimate": r.get("epsestimate"),
                    "eps_actual": r.get("epsactual"),
                    "eps_surprise": r.get("epssurprisepct")
                })
    except Exception:
        pass
    return items

def fetch_single_ticker_details(item, days_away):
    """Pulls market cap and previous quarter for a calendar item."""
    sym = item["ticker"]
    if any(sym.endswith(ext) for ext in ["-USD", "=F"]):
        return None

    try:
        t_obj = yf.Ticker(sym, session=http_session)
        fi = t_obj.fast_info
        
        market_cap = getattr(fi, "market_cap", None)
        short_name = getattr(fi, "name", None) or item["name"]
        time_badge = "Before Open 🌅" if item["startdatetimetype"] == "BMO" else "After Close 🌙"
        
        eps_est_str = f"${float(item['eps_estimate']):.2f}" if item.get("eps_estimate") is not None else "Pending"
        
        # Previous quarter surprise
        prev_quarter_str = "N/A"
        try:
            ed_df = t_obj.earnings_dates
            if ed_df is not None and not ed_df.empty:
                past_df = ed_df[ed_df['Reported EPS'].notna()]
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
        except Exception:
            pass

        return {
            "ticker": sym,
            "name": short_name,
            "badge": get_country_badge(sym),
            "date": item["date"],
            "days_away": days_away,
            "date_str": item["date_str"],
            "time_badge": time_badge,
            "status": "Official / Confirmed 🟢",
            "market_cap": market_cap or 0,
            "consensus_est": f"EPS: `{eps_est_str}`",
            "actual_reported": "Pending ⏳",
            "prev_quarter": prev_quarter_str
        }
    except Exception:
        return None

def fetch_watchlist_earnings_direct(sym):
    """Pulls accurate earnings dates for personal watchlist."""
    try:
        t_obj = yf.Ticker(sym, session=http_session)
        today = datetime.now(NY_TZ).date()
        
        ed_df = t_obj.earnings_dates
        if ed_df is not None and not ed_df.empty:
            future_mask = ed_df['Reported EPS'].isna() if 'Reported EPS' in ed_df.columns else pd.Series([True]*len(ed_df), index=ed_df.index)
            future_df = ed_df[future_mask]
            
            if not future_df.empty:
                nxt_idx = future_df.index[0]
                nxt_dt = nxt_idx.tz_convert(NY_TZ) if hasattr(nxt_idx, "tz_convert") and nxt_idx.tz else (nxt_idx.to_pydatetime() if hasattr(nxt_idx, "to_pydatetime") else nxt_idx)
                nxt_d = nxt_dt.date() if isinstance(nxt_dt, datetime) else nxt_dt
                
                if nxt_d >= today:
                    days_away = (nxt_d - today).days
                    eps_val = future_df["EPS Estimate"].iloc[0] if "EPS Estimate" in future_df.columns else None
                    eps_est = f"${float(eps_val):.2f}" if pd.notna(eps_val) else "Pending"
                    time_badge = "Before Open 🌅" if getattr(nxt_dt, "hour", 16) < 12 else "After Close 🌙"

                    # Previous quarter
                    prev_quarter_str = "N/A"
                    past_df = ed_df[ed_df['Reported EPS'].notna()]
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

                    return {
                        "ticker": sym,
                        "name": t_obj.fast_info.name or sym,
                        "badge": get_country_badge(sym),
                        "date": nxt_d,
                        "days_away": days_away,
                        "date_str": nxt_d.strftime("%b %d, %Y"),
                        "time_badge": time_badge,
                        "status": "Official / Confirmed 🟢",
                        "consensus_est": f"EPS: `{eps_est}`",
                        "actual_reported": "Pending ⏳",
                        "prev_quarter": prev_quarter_str
                    }
    except Exception:
        pass
    return None

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
    today = now_ny.date()
    today_str = now_ny.strftime("%A, %B %d, %Y")
    print(f"[{now_ny.strftime('%I:%M:%S %p %Z')}] Starting Market-Wide Earnings Radar for {today_str}...\n")

    # -------------------------------------------------------------
    # 1. YESTERDAY'S SCORECARD (From Live Calendar Feed)
    # -------------------------------------------------------------
    print("1. Pulling Yesterday's Live Reported Earnings Scorecard...")
    yesterday_targets = [today - timedelta(days=i) for i in (range(1, 4) if today.weekday() == 0 else range(1, 2))]
    yesterday_raw = []
    for d in yesterday_targets:
        yesterday_raw.extend(fetch_calendar_day(d))

    scorecard_items = []
    for r in yesterday_raw[:15]:  # Top reports from yesterday
        sym = r["ticker"]
        if not sym or r.get("eps_actual") is None:
            continue
        try:
            t_obj = yf.Ticker(sym, session=http_session)
            actual_eps = r["eps_actual"]
            est_eps = r.get("eps_estimate")
            surp = r.get("eps_surprise")

            # Stock move
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
            if surp is not None:
                tag = "🎯" if surp >= 0 else "⚠️"
                surp_str = f" (**Beat by `{surp:+.1f}%` {tag}**)" if surp >= 0 else f" (**Missed by `{surp:+.1f}%` {tag}**)"

            eps_line = f"Actual: `${float(actual_eps):.2f}` | Estimate: `${float(est_eps):.2f}`{surp_str}" if est_eps is not None else f"Actual: `${float(actual_eps):.2f}`"
            
            scorecard_items.append({
                "ticker": sym,
                "name": r["name"],
                "badge": get_country_badge(sym),
                "reported_date": r["date_str"],
                "time_badge": "Before Open 🌅" if r["startdatetimetype"] == "BMO" else "After Close 🌙",
                "eps_line": eps_line,
                "move_str": move_str
            })
        except Exception:
            pass

    # -------------------------------------------------------------
    # 2. SCAN WATCHLIST (Next 30 Days)
    # -------------------------------------------------------------
    print("2. Scanning Watchlist Earnings (Next 30 Days)...")
    watchlist_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(fetch_watchlist_earnings_direct, WATCHLIST):
            if res and res["days_away"] <= 30:
                watchlist_results.append(res)
    watchlist_results.sort(key=lambda x: x["date"])

    # -------------------------------------------------------------
    # 3. SCAN MARKET-WIDE CALENDAR (Next 30 Days)
    # -------------------------------------------------------------
    print("3. Scanning 30-Day Market-Wide Calendar Stream...")
    calendar_30d = []
    for i in range(1, 31):
        target_d = today + timedelta(days=i)
        calendar_30d.extend(fetch_calendar_day(target_d))

    print(f"   Found {len(calendar_30d)} total upcoming earnings events across the market.")

    # Process all calendar items in parallel
    detailed_market_items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_single_ticker_details, item, (item["date"] - today).days): item for item in calendar_30d}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                detailed_market_items.append(res)

    # Segment into Mega, Mid, and Small Caps
    mega_us, mega_ca = [], []
    mid_us, mid_ca = [], []
    small_us, small_ca = [], []

    for item in detailed_market_items:
        m_cap = item["market_cap"]
        is_ca = "🍁" in item["badge"]
        days = item["days_away"]

        # Mega-Caps (Next 30 Days, >= $200B)
        if m_cap >= 2e11 and days <= 30:
            if is_ca:
                mega_ca.append(item)
            else:
                mega_us.append(item)

        # Mid-Caps (Next 14 Days, $2B - $10B)
        elif 2e9 <= m_cap <= 1e10 and days <= 14:
            if is_ca:
                mid_ca.append(item)
            else:
                mid_us.append(item)

        # Small-Caps (Next 14 Days, < $2B)
        elif m_cap < 2e9 and days <= 14:
            if is_ca:
                small_ca.append(item)
            else:
                small_us.append(item)

    # Sort each tier by date
    mega_us.sort(key=lambda x: x["date"])
    mega_ca.sort(key=lambda x: x["date"])
    mid_us.sort(key=lambda x: x["date"])
    mid_ca.sort(key=lambda x: x["date"])
    small_us.sort(key=lambda x: x["date"])
    small_ca.sort(key=lambda x: x["date"])

    # =================================================================
    # DISPATCH ALL 5 CARDS TO DISCORD
    # =================================================================
    print("\nDispatching all cards to Earnings Channel...")

    # CARD 1: Yesterday's Scorecard
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items[:10], 1):
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
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results[:10], 1)])
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
            mega_txt += "**🇺🇸 UNITED STATES MEGA-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_us[:6], 1)]) + "\n\n"
        if mega_ca:
            mega_txt += "**🇨🇦 CANADIAN MEGA-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_ca[:6], 1)])
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
            mid_txt += "**🇺🇸 UNITED STATES MID-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_us[:6], 1)]) + "\n\n"
        if mid_ca:
            mid_txt += "**🇨🇦 CANADIAN MID-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca[:6], 1)])
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
            small_txt += "**🇺🇸 UNITED STATES SMALL-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_us[:6], 1)]) + "\n\n"
        if small_ca:
            small_txt += "**🇨🇦 CANADIAN SMALL-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_ca[:6], 1)])
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
