import os
import time
import json
import logging
import concurrent.futures
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Webhook & Branding
DISCORD_EARNINGS_WEBHOOK_URL = os.getenv(
    "DISCORD_EARNINGS_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1539761350920642660/cDXOzG5Unsic7mcUrYS6KJK8evjolwQP0LSqs5ydvEFvnoXT-6djPpGj5VHM9czqRfrI"
)
BOT_NAME = "Looney"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

NY_TZ = ZoneInfo("America/New_York")
LOOKAHEAD_DAYS = 45
US_MIDCAP_CHUNK_SIZE = 15  # 15 entries per embed (100% safe within Discord character limits)

# Your Curated Watchlist
WATCHLIST = [
    "NVDA", "AMD", "MU", "INTC", "AVGO", "ASML", "IBM", "TSLA", 
    "RKLB", "PLTR", "META", "ORCL", "RBLX", "MSTR", "IREN", "SHOP.TO"
]

nasdaq_session = requests.Session()
nasdaq_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
})

yahoo_session = requests.Session()
yahoo_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*"
})

def clean_currency(val):
    if val is None or str(val).strip() in ["", "N/A", "None"]:
        return "N/A"
    s = str(val).replace("$", "").strip()
    try:
        f = float(s)
        return f"${f:.2f}"
    except Exception:
        return f"${s}"

def parse_market_cap_str(cap_str):
    if not cap_str or cap_str == "N/A":
        return 0
    try:
        clean = str(cap_str).replace("$", "").replace(",", "").strip()
        return float(clean)
    except Exception:
        return 0

# ====================================================================
# 1. DYNAMIC CANADIAN (TSX) SCREENER
# ====================================================================
def fetch_dynamic_tsx_universe():
    logging.info("Dynamically screening TSX for Canadian Mid & Mega-Caps (≥ $2B)...")
    tickers = set()
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener?formatted=false&lang=en-US&region=CA"
        payload = {
            "size": 150,
            "offset": 0,
            "sortField": "intradaymarketcap",
            "sortType": "DESC",
            "quoteType": "EQUITY",
            "topOperator": "AND",
            "query": {
                "operator": "AND",
                "operands": [
                    {"operator": "EQ", "operands": ["region", "ca"]},
                    {"operator": "GTE", "operands": ["intradaymarketcap", 2000000000]}
                ]
            }
        }
        res = yahoo_session.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            quotes = res.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
            for q in quotes:
                sym = q.get("symbol")
                if sym and (sym.endswith(".TO") or sym.endswith(".V")):
                    tickers.add(sym)
    except Exception as e:
        logging.warning(f"Yahoo dynamic TSX screener note: {e}")

    if len(tickers) < 20:
        tickers.update([
            "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "MFC.TO", "SLF.TO", "POW.TO", "IFC.TO",
            "ENB.TO", "CNQ.TO", "SU.TO", "TRP.TO", "CVE.TO", "IMO.TO", "TOU.TO", "ARX.TO", "PPL.TO", "KEY.TO",
            "SHOP.TO", "CSU.TO", "TRI.TO", "OTEX.TO", "GIB-A.TO", "BCE.TO", "T.TO", "RCI-B.TO",
            "CNR.TO", "CP.TO", "WCN.TO", "TFII.TO", "ABX.TO", "AEM.TO", "FNV.TO", "WPM.TO", "NTR.TO", "ATD.TO"
        ])
    return list(tickers)

# ====================================================================
# 2. LIVE US MASTER CALENDAR API (NASDAQ)
# ====================================================================
def fetch_nasdaq_calendar_day(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    items = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                if not sym or "^" in sym or "/" in sym or "." in sym:
                    continue
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                if mcap < 2e9:
                    continue

                time_code = r.get("time", "time-not-supplied").lower()
                time_badge = "Before Open 🌅" if "pre" in time_code or "bmo" in time_code else "After Close 🌙"
                eps_forecast = clean_currency(r.get("epsForecast"))

                items.append({
                    "ticker": sym,
                    "name": r.get("name", sym),
                    "badge": "🇺🇸",
                    "date": target_date,
                    "days_away": (target_date - datetime.now(NY_TZ).date()).days,
                    "date_str": target_date.strftime("%b %d, %Y"),
                    "time_badge": time_badge,
                    "status": "Official / Confirmed 🟢",
                    "market_cap": mcap,
                    "consensus_est": f"EPS: `{eps_forecast}`",
                    "actual_reported": "Pending ⏳"
                })
    except Exception:
        pass
    return items

def fetch_us_yesterday_actuals(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    scorecard = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                eps_actual_raw = r.get("eps")
                if not sym or eps_actual_raw is None or str(eps_actual_raw).strip() in ["", "N/A"]:
                    continue
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                if mcap < 2e9:
                    continue

                eps_forecast_raw = r.get("epsForecast")
                act_str = clean_currency(eps_actual_raw)
                est_str = clean_currency(eps_forecast_raw)
                
                surp_str = ""
                try:
                    act_f = float(str(eps_actual_raw).replace("$", ""))
                    est_f = float(str(eps_forecast_raw).replace("$", ""))
                    diff = act_f - est_f
                    tag = "🎯" if diff >= 0 else "⚠️"
                    surp_str = f" (**{'Beat' if diff >= 0 else 'Missed'} by `${abs(diff):.2f}` {tag}**)"
                except Exception:
                    pass

                scorecard.append({
                    "ticker": sym,
                    "name": r.get("name", sym),
                    "badge": "🇺🇸",
                    "reported_date": target_date.strftime("%b %d, %Y"),
                    "market_cap": mcap,
                    "eps_line": f"Actual: `{act_str}` | Estimate: `{est_str}`{surp_str}"
                })
    except Exception:
        pass
    return scorecard

# ====================================================================
# 3. CANADIAN (TSX) TICKER PROCESSOR
# ====================================================================
def scan_single_tsx_ticker(sym, check_dates):
    upcoming_item = None
    scorecard_item = None
    try:
        t_obj = yf.Ticker(sym, session=yahoo_session)
        today = datetime.now(NY_TZ).date()
        m_cap = getattr(t_obj.fast_info, "market_cap", 0) or 0
        
        if m_cap < 2e9:
            return None, None

        name = getattr(t_obj.fast_info, "name", None) or sym

        # Upcoming Calendar
        cal = t_obj.calendar
        nxt_d = None
        eps_est = "Pending"
        if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    target = ed[0] if isinstance(ed, list) else ed
                    nxt_d = target.date() if isinstance(target, datetime) else target
                avg_val = cal.get("Earnings Average")
                if avg_val is not None:
                    eps_est = clean_currency(avg_val)
            elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                nxt_d = ed.date() if isinstance(ed, datetime) else ed

        if nxt_d and nxt_d >= today:
            days_away = (nxt_d - today).days
            if days_away <= LOOKAHEAD_DAYS:
                upcoming_item = {
                    "ticker": sym,
                    "name": name,
                    "badge": "🍁",
                    "date": nxt_d,
                    "days_away": days_away,
                    "date_str": nxt_d.strftime("%b %d, %Y"),
                    "time_badge": "After Close 🌙",
                    "status": "Official / Confirmed 🟢",
                    "market_cap": m_cap,
                    "consensus_est": f"EPS: `{eps_est}`",
                    "actual_reported": "Pending ⏳"
                }

        # Scorecard
        ed_df = t_obj.get_earnings_dates(limit=4)
        if ed_df is not None and not ed_df.empty:
            past_df = ed_df[ed_df['Reported EPS'].notna()]
            if not past_df.empty:
                last_dt = past_df.index[0]
                last_date = last_dt.date() if isinstance(last_dt, datetime) else last_dt
                if last_date in check_dates:
                    actual_eps = past_df['Reported EPS'].iloc[0]
                    est_eps = past_df['EPS Estimate'].iloc[0] if 'EPS Estimate' in past_df.columns else None
                    surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None

                    surp_str = ""
                    if pd.notna(surp):
                        raw_s = float(surp)
                        surp_val = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                        tag = "🎯" if surp_val >= 0 else "⚠️"
                        surp_str = f" (**Beat by `{surp_val:+.1f}%` {tag}**)" if surp_val >= 0 else f" (**Missed by `{surp_val:+.1f}%` {tag}**)"

                    act_str = clean_currency(actual_eps)
                    est_str = clean_currency(est_eps)
                    eps_line = f"Actual: `{act_str}`" + (f" | Estimate: `{est_str}`{surp_str}" if est_eps is not None else "")

                    scorecard_item = {
                        "ticker": sym,
                        "name": name,
                        "badge": "🍁",
                        "reported_date": last_date.strftime("%b %d, %Y"),
                        "market_cap": m_cap,
                        "eps_line": eps_line
                    }
    except Exception:
        pass
    return upcoming_item, scorecard_item

def deduplicate_dual_listings(us_items, ca_items):
    ca_base_symbols = {item["ticker"].replace(".TO", "").replace(".V", "").upper(): item for item in ca_items}
    filtered_us_items = [us_item for us_item in us_items if us_item["ticker"].upper() not in ca_base_symbols]
    return filtered_us_items, ca_items

def format_earnings_entry(idx, item):
    return (
        f"**{idx}. {item['ticker']} — {item['name']}** {item['badge']}\n"
        f"• **Date & Time:** `{item['date_str']} (In {item['days_away']} Days)` • **{item['time_badge']}**\n"
        f"• **Status:** `{item['status']}`\n"
        f"• **Consensus Estimate:** {item['consensus_est']}\n"
        f"• **Actual Reported:** `{item['actual_reported']}`\n"
    )

def dispatch_discord_earnings_embed(title, description, entries_text, color=3447003, footer_text=None):
    if not DISCORD_EARNINGS_WEBHOOK_URL:
        return

    footer = footer_text or f"Looney • Daily 6:00 AM Earnings Radar (Next {LOOKAHEAD_DAYS} Days)"
    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": title,
            "description": f"{description}\n\n{entries_text}"[:4000],
            "color": color,
            "footer": {"text": footer}
        }]
    }
    try:
        res = requests.post(DISCORD_EARNINGS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        time.sleep(0.6)  # Safe spacing to respect Discord rate limits
    except Exception as e:
        logging.error(f"Error sending embed: {e}")

# ====================================================================
# MAIN RUNNER
# ====================================================================
def run_earnings_daily():
    now_ny = datetime.now(NY_TZ)
    today = now_ny.date()
    today_str = now_ny.strftime("%A, %B %d, %Y")
    logging.info(f"Starting Live {LOOKAHEAD_DAYS}-Day Multi-Market Earnings Radar for {today_str}...")

    prev_dates = [today - timedelta(days=i) for i in (range(1, 4) if today.weekday() == 0 else range(1, 2))]

    # 1. FETCH US SCORECARD
    logging.info("Pulling US reported earnings scorecard...")
    scorecard_items = []
    for d in prev_dates:
        scorecard_items.extend(fetch_us_yesterday_actuals(d))

    # 2. FETCH US UPCOMING CALENDAR (Parallel 45-Day Fetch)
    logging.info(f"Pulling {LOOKAHEAD_DAYS}-day US market calendar in parallel...")
    upcoming_us_items = []
    dates_to_scan = [today + timedelta(days=i) for i in range(1, LOOKAHEAD_DAYS + 1)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        for day_res in executor.map(fetch_nasdaq_calendar_day, dates_to_scan):
            upcoming_us_items.extend(day_res)

    # 3. DYNAMICALLY SCAN TSX CANADIAN UNIVERSE
    dynamic_tsx_list = fetch_dynamic_tsx_universe()
    upcoming_ca_items = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(scan_single_tsx_ticker, sym, prev_dates) for sym in dynamic_tsx_list]
        for f in concurrent.futures.as_completed(futures):
            up, sc = f.result()
            if up:
                upcoming_ca_items.append(up)
            if sc:
                scorecard_items.append(sc)

    # 4. DUAL-LISTING RESOLUTION & SORTING
    filtered_us_upcoming, upcoming_ca_items = deduplicate_dual_listings(upcoming_us_items, upcoming_ca_items)
    scorecard_items.sort(key=lambda x: x["market_cap"], reverse=True)

    # 5. WATCHLIST PROCESSING
    all_upcoming = filtered_us_upcoming + upcoming_ca_items
    watchlist_set = set(WATCHLIST)
    watchlist_results = [item for item in all_upcoming if item["ticker"] in watchlist_set and item["days_away"] <= LOOKAHEAD_DAYS]
    watchlist_results.sort(key=lambda x: x["date"])

    # 6. SEGMENT MEGA AND MID CAPS
    mega_us, mega_ca = [], []
    mid_us, mid_ca = [], []

    for item in all_upcoming:
        m_cap = item["market_cap"]
        is_ca = item["badge"] == "🍁"
        days = item["days_away"]

        # Mega-Cap: >= $200B (Next 45 Days)
        if m_cap >= 2e11 and days <= LOOKAHEAD_DAYS:
            (mega_ca if is_ca else mega_us).append(item)
        # Mid-Cap: $2B to $200B (Next 45 Days)
        elif 2e9 <= m_cap < 2e11 and days <= LOOKAHEAD_DAYS:
            (mid_ca if is_ca else mid_us).append(item)

    # Sort each tier chronologically
    mega_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mega_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))

    # =================================================================
    # DISPATCH ALL CARDS TO DISCORD
    # =================================================================
    # CARD 1: Unified Scorecard (US + TSX)
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items[:12], 1):
            scorecard_txt += (
                f"**{i}. {sc['ticker']} — {sc['name']}** {sc['badge']}\n"
                f"• **Reported Date:** `{sc['reported_date']}`\n"
                f"• **EPS Result:** {sc['eps_line']}\n\n"
            )
        dispatch_discord_earnings_embed(
            title="📢 Yesterday's Reported Earnings Scorecard [ACTUALS & SURPRISES]",
            description="*Official results reported in previous session across US and Canadian (TSX) markets.*",
            entries_text=scorecard_txt,
            color=15844367  # Gold
        )

    # CARD 2: Watchlist (Next 45 Days)
    if watchlist_results:
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results[:12], 1)])
        dispatch_discord_earnings_embed(
            title=f"🗓️ Watchlist Earnings Calendar [NEXT {LOOKAHEAD_DAYS} DAYS]",
            description=f"*Sorted by nearest report date across your watchlist as of {today_str}.*",
            entries_text=wl_txt,
            color=3066993  # Green
        )

    # CARD 3: Mega-Caps (Next 45 Days — ≥ $200B)
    mega_combined = mega_us + mega_ca
    if mega_combined:
        mega_txt = ""
        if mega_us:
            mega_txt += "**🇺🇸 UNITED STATES MEGA-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_us[:8], 1)]) + "\n\n"
        if mega_ca:
            mega_txt += "**🇨🇦 CANADIAN MEGA-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_ca[:8], 1)])
        dispatch_discord_earnings_embed(
            title=f"👑 Mega-Cap Earnings Calendar [NEXT {LOOKAHEAD_DAYS} DAYS — ≥ $200B]",
            description="*Major market-moving corporate reports over the next 45 days.*",
            entries_text=mega_txt,
            color=10181046  # Purple
        )

    # CARD 4A: Canadian Mid-Caps (Next 45 Days — $2B to $200B)
    if mid_ca:
        mid_ca_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca, 1)])
        dispatch_discord_earnings_embed(
            title=f"🍁 Canadian Mid-Cap Earnings Calendar [NEXT {LOOKAHEAD_DAYS} DAYS — $2B to $200B]",
            description=f"*All {len(mid_ca)} Canadian institutional & momentum leaders reporting in the next 45 days.*",
            entries_text=mid_ca_txt,
            color=15158332,  # Crimson/Maple Red
            footer_text=f"Looney • TSX Mid-Cap Calendar ({len(mid_ca)} Total)"
        )

    # CARD 4B: US Mid-Caps (Paginated Sequentially to deliver 100% of reports)
    if mid_us:
        total_us = len(mid_us)
        # Split into chunks of US_MIDCAP_CHUNK_SIZE
        chunks = [mid_us[i:i + US_MIDCAP_CHUNK_SIZE] for i in range(0, total_us, US_MIDCAP_CHUNK_SIZE)]
        total_chunks = len(chunks)

        for chunk_idx, chunk in enumerate(chunks, 1):
            start_num = (chunk_idx - 1) * US_MIDCAP_CHUNK_SIZE + 1
            chunk_txt = "\n".join([format_earnings_entry(start_num + j, item) for j, item in enumerate(chunk)])
            
            part_title = f"📈 US Mid-Cap Earnings Calendar [NEXT {LOOKAHEAD_DAYS} DAYS — Part {chunk_idx}/{total_chunks}]" if total_chunks > 1 else f"📈 US Mid-Cap Earnings Calendar [NEXT {LOOKAHEAD_DAYS} DAYS]"
            part_desc = f"*Showing entries {start_num} to {start_num + len(chunk) - 1} of {total_us} total upcoming US Mid-Caps ($2B–$200B).*"
            
            dispatch_discord_earnings_embed(
                title=part_title,
                description=part_desc,
                entries_text=chunk_txt,
                color=3447003,  # Blue
                footer_text=f"Looney • US Mid-Caps (Part {chunk_idx} of {total_chunks} • {total_us} Total)"
            )

    logging.info("Earnings Intelligence 45-day flow completed successfully.")

if __name__ == "__main__":
    run_earnings_daily()
