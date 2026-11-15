#!/usr/bin/env python3
"""Collectr portfolio tracker.

Reads your public Collectr showcase page once a day, saves a snapshot, and
sends you:
  * daily  - the 3 biggest gainers and 3 biggest losers
  * weekly - (Sundays) how much the whole portfolio went up or down this week

Usage:
  python3 tracker.py run            # daily report (+ weekly on Sundays)
  python3 tracker.py run --dry-run  # print the messages instead of sending
  python3 tracker.py weekly         # send the weekly report now
  python3 tracker.py telegram-setup # find your Telegram chat id
  python3 tracker.py test           # send a test message to every channel

Only uses the Python standard library.
"""
import datetime as dt
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
HISTORY_FILE = HERE / "history.json"
USER_AGENT = "collectr-portfolio-tracker/1.0 (personal use)"


def _ssl_context():
    # python.org builds of Python on macOS ship without CA certs; fall back to
    # certifi or the system bundle (verification stays on).
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


# ---------------------------------------------------------------- config ---

def load_config():
    if not CONFIG_FILE.exists():
        sys.exit("config.json not found - copy config.example.json to config.json and fill it in.")
    return json.loads(CONFIG_FILE.read_text())


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read().decode("utf-8", "replace")


# ------------------------------------------------------- fetch showcase ---

def fetch_showcase(profile):
    """Return (portfolio_total, items) from the public showcase page.

    The page is a Next.js app; its data is embedded as JSON strings inside
    self.__next_f.push([1,"..."]) script calls. We decode those strings and
    pull out the showcase profile object.
    """
    html = http_get(f"https://app.getcollectr.com/showcase/profile/{profile}")
    payload = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        payload.append(json.loads(m.group(1)))
    blob = "".join(payload) or html

    start = blob.find('"portfolio_value":')
    if start == -1:
        raise RuntimeError("Couldn't find portfolio data on the showcase page - "
                           "is the showcase still public? Collectr may have changed the page.")
    # Walk back to the opening brace of the profile object and decode it.
    obj_start = blob.rfind('{"user":', 0, start)
    if obj_start == -1:
        obj_start = blob.rfind("{", 0, start)
    profile_obj, _ = json.JSONDecoder().raw_decode(blob[obj_start:])

    total = float(profile_obj["portfolio_value"][0]["price"])
    items = {}
    for p in profile_obj.get("products", []):
        key = "|".join(str(p.get(k) or "") for k in
                       ("product_id", "grade_id", "card_condition", "product_sub_type"))
        price = float(p.get("price_override") or p["market_price"])
        qty = int(p.get("quantity") or 1)
        if key in items:  # same product listed twice: merge quantities
            items[key]["qty"] += qty
            continue
        items[key] = {
            "name": p["product_name"].strip(),
            "set": p.get("catalog_group", ""),
            "number": p.get("card_number", ""),
            "grade": grade_label(p),
            "price": price,
            "qty": qty,
            "collectr_pct": float(p.get("market_price_percentage_diff") or 0),
            "collectr_diff": float(p.get("market_price_diff") or 0),
        }
    return total, items


def grade_label(p):
    if p.get("grade_company"):
        return f'{p["grade_company"]} {p.get("grade", "")}'.strip()
    if not p.get("is_card", True):
        return "Sealed"
    return p.get("card_condition") or ""


# ---------------------------------------------------------- history ---

def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {}


def save_history(history):
    # keep ~1 year of snapshots
    keep = dict(sorted(history.items())[-400:])
    HISTORY_FILE.write_text(json.dumps(keep, indent=1))


def previous_snapshot(history, today, min_days=1, max_days=None):
    """Most recent snapshot at least `min_days` before today."""
    best = None
    for d in sorted(history):
        age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(d)).days
        if age >= min_days and (max_days is None or age <= max_days):
            best = d
    return best


# --------------------------------------------------------- reports ---

def money(x, sign=False):
    s = f"${abs(x):,.2f}"
    if sign:
        return ("+" if x >= 0 else "-") + s
    return s


def describe(item):
    bits = [item["name"]]
    extra = " · ".join(b for b in (item["set"], item["grade"]) if b)
    return f"{bits[0]} ({extra})" if extra else bits[0]


def item_changes(today_items, prev_items):
    changes = []
    for key, it in today_items.items():
        if prev_items is not None:
            old = prev_items.get(key)
            if not old or not old["price"]:
                continue
            diff = it["price"] - old["price"]
            pct = diff / old["price"] * 100
        else:  # no history yet: fall back to Collectr's own change figures
            diff, pct = it["collectr_diff"], it["collectr_pct"]
        changes.append((pct, diff, it))
    return changes


def daily_report(total, items, history, today):
    prev_day = previous_snapshot(history, today, min_days=1)
    prev_items = history[prev_day]["items"] if prev_day else None
    changes = item_changes(items, prev_items)

    gainers = sorted([c for c in changes if c[0] > 0], key=lambda c: -c[0])[:3]
    losers = sorted([c for c in changes if c[0] < 0], key=lambda c: c[0])[:3]

    lines = [f"📊 Collectr daily update — {today}",
             f"Portfolio value: {money(total)}"]
    if prev_day:
        d = total - history[prev_day]["total"]
        p = d / history[prev_day]["total"] * 100 if history[prev_day]["total"] else 0
        lines.append(f"Since {prev_day}: {money(d, True)} ({p:+.2f}%)")
    lines.append("")

    lines.append("🚀 Top 3 gainers")
    if gainers:
        for i, (pct, diff, it) in enumerate(gainers, 1):
            lines.append(f"{i}. {describe(it)}\n    {money(it['price'])}  {pct:+.2f}% ({money(diff, True)})")
    else:
        lines.append("No cards went up today.")
    lines.append("")
    lines.append("📉 Top 3 losers")
    if losers:
        for i, (pct, diff, it) in enumerate(losers, 1):
            lines.append(f"{i}. {describe(it)}\n    {money(it['price'])}  {pct:+.2f}% ({money(diff, True)})")
    else:
        lines.append("No cards went down today.")

    lines.append("")
    lines.append(f"(Movers are from your {len(items)} most valuable items on your showcase.)")
    return "\n".join(lines)


def weekly_report(total, items, history, today):
    week_ago = previous_snapshot(history, today, min_days=6, max_days=10)
    lines = [f"🗓️ Collectr weekly update — week ending {today}",
             f"Portfolio value: {money(total)}"]
    if not week_ago:
        lines.append("No snapshot from a week ago yet — tracking started recently. "
                     "Your first full weekly comparison comes next week.")
        return "\n".join(lines)

    old_total = history[week_ago]["total"]
    diff = total - old_total
    pct = diff / old_total * 100 if old_total else 0
    arrow = "📈" if diff >= 0 else "📉"
    lines.append(f"{arrow} This week: {money(diff, True)} ({pct:+.2f}%)")
    lines.append(f"A week ago ({week_ago}): {money(old_total)}")

    changes = item_changes(items, history[week_ago]["items"])
    by_dollars = sorted(changes, key=lambda c: c[1])
    if changes:
        best, worst = by_dollars[-1], by_dollars[0]
        lines.append("")
        if best[1] > 0:
            lines.append(f"Best of the week: {describe(best[2])} {best[0]:+.2f}% ({money(best[1], True)})")
        if worst[1] < 0:
            lines.append(f"Worst of the week: {describe(worst[2])} {worst[0]:+.2f}% ({money(worst[1], True)})")
    return "\n".join(lines)


# ---------------------------------------------------------- senders ---

def send_telegram(cfg, text):
    tg = cfg.get("telegram") or {}
    if not tg.get("enabled") or not tg.get("bot_token") or not tg.get("chat_id"):
        return None
    url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": tg["chat_id"], "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.loads(r.read()).get("ok")


def send_whatsapp(cfg, text):
    """WhatsApp via CallMeBot (free, for messages to your own number)."""
    wa = cfg.get("whatsapp") or {}
    if not wa.get("enabled") or not wa.get("phone") or not wa.get("apikey"):
        return None
    qs = urllib.parse.urlencode({"phone": wa["phone"], "text": text, "apikey": wa["apikey"]})
    body = http_get(f"https://api.callmebot.com/whatsapp.php?{qs}", timeout=60)
    return "queued" in body.lower() or "sent" in body.lower()


def deliver(cfg, text, dry_run=False):
    if dry_run:
        print(text, "\n" + "-" * 40)
        return
    results = {}
    for name, fn in (("Telegram", send_telegram), ("WhatsApp", send_whatsapp)):
        try:
            results[name] = fn(cfg, text)
        except Exception as e:  # keep going if one channel fails
            results[name] = f"error: {e}"
    sent = {k: v for k, v in results.items() if v is not None}
    if not sent:
        print("No channel is enabled in config.json - printing instead:\n")
        print(text)
    else:
        print("Delivery:", sent)


# ------------------------------------------------------------- main ---

def snapshot(cfg):
    total, items = fetch_showcase(cfg["profile"])
    today = dt.date.today().isoformat()
    history = load_history()
    return total, items, history, today


def cmd_run(cfg, dry_run=False, force_weekly=False):
    total, items, history, today = snapshot(cfg)
    deliver(cfg, daily_report(total, items, history, today), dry_run)
    weekday = int(cfg.get("weekly_day", 6))  # 0=Mon ... 6=Sun
    if force_weekly or dt.date.today().weekday() == weekday:
        deliver(cfg, weekly_report(total, items, history, today), dry_run)
    history[today] = {"total": total, "items": items}
    save_history(history)


def cmd_weekly(cfg, dry_run=False):
    total, items, history, today = snapshot(cfg)
    deliver(cfg, weekly_report(total, items, history, today), dry_run)
    history[today] = {"total": total, "items": items}
    save_history(history)


def cmd_telegram_setup(cfg):
    token = (cfg.get("telegram") or {}).get("bot_token")
    if not token:
        sys.exit("Put your bot token in config.json first (telegram.bot_token).")
    data = json.loads(http_get(f"https://api.telegram.org/bot{token}/getUpdates"))
    chats = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        c = msg.get("chat")
        if c:
            chats[c["id"]] = c.get("username") or c.get("title") or c.get("first_name")
    if not chats:
        sys.exit("No messages found. Open your bot in Telegram, press Start / send it 'hi', then rerun.")
    for cid, who in chats.items():
        print(f"chat_id {cid}  ({who})")
    if len(chats) == 1:
        cid = next(iter(chats))
        cfg["telegram"]["chat_id"] = cid
        cfg["telegram"]["enabled"] = True
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        print("Saved to config.json and enabled Telegram.")


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    cmd = next((a for a in args if not a.startswith("--")), "run")
    cfg = load_config()
    if cmd == "run":
        cmd_run(cfg, dry, force_weekly="--weekly" in args)
    elif cmd == "weekly":
        cmd_weekly(cfg, dry)
    elif cmd == "telegram-setup":
        cmd_telegram_setup(cfg)
    elif cmd == "test":
        deliver(cfg, "✅ Collectr tracker test message — notifications are working.", dry)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
