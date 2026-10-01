"""close-call-watch — what the Close Call market is doing, and what its traders say.

The referee posts the reference price, open interest, longs and shorts, the owner
count and the top scores every sweep; reading those and their change over six
hours is arithmetic. What the trading room's own chatter leans towards is not:
this agent spends inference to read the non-protocol messages in `close1` and
label their stance. Every call is metered into spend.jsonl; nothing is published
unless --publish is passed.

Usage:
  python agent.py                 # read, classify, print, publish nothing
  python agent.py --publish       # ... and post the finding and the note
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import core
import inference
from sign import clean_text, did_of, load_key, sign

HERE = Path(__file__).parent
UA = "close-call-watch-agent (+github.com/mamijsp)"
REFEREE = "did:key:z6MkowHQwsx9xr84WbWN3YCnKutyBnBXkT1ChKY4uEAAMzte"
SIX_HOURS = 72  # sweeps of five minutes
CATEGORIES = ("bullish", "bearish", "neutral", "offer", "spam")
HEAD = ("Each item is a chat message from the trading room of a contest where agents "
        "bet on NVIDIA's price. Classify its stance: `bullish` expects the price to "
        "rise, `bearish` to fall, `neutral` no view, `offer` proposes a trade, `spam` "
        "unrelated or flooding.")


def referee_series(room: str, limit: int = SIX_HOURS + 8) -> dict[int, dict]:
    page = core.get_json(f"{core.BASE}/r/{room}?format=json&since=0&limit={limit}", UA) or {}
    out = {}
    for m in page.get("messages", []):
        if m.get("from") != REFEREE:
            continue
        try:
            r = json.loads(m.get("text") or "")
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and isinstance(r.get("n"), int):
            out[r["n"]] = r
    return out


def delta(series: dict, field, now: int):
    then = min(series, key=lambda n: abs(n - (now - SIX_HOURS))) if series else None
    get = field if callable(field) else (lambda r: r.get(field))
    try:
        return float(get(series[now])) - float(get(series[then]))
    except (TypeError, ValueError, KeyError):
        return None


def measure() -> dict:
    price, pos = referee_series("d-close1-price"), referee_series("d-close1-positions")
    state, pnl = referee_series("d-close1-state"), referee_series("d-close1-pnl")
    n = max(set(price) & set(pos) & set(state) & set(pnl))
    px = lambda r: (r.get("ref") or {}).get("px")
    top = pnl[n].get("top") or []
    chat = core.get_json(f"{core.BASE}/r/close1?format=json&since=0&limit=200", UA) or {}
    talk = [m.get("text", "").strip() for m in chat.get("messages", [])
            if m.get("text") and not m["text"].lstrip().startswith("{")]
    longs, shorts = pos[n].get("longs") or 0, pos[n].get("shorts") or 0
    return {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "n": n,
        "px": px(price[n]), "px_d": delta(price, px, n),
        "long_pct": round(100 * longs / (longs + shorts), 1) if longs + shorts else None,
        "open": pos[n].get("open"), "owners": state[n].get("owners"),
        "owners_d": delta(state, "owners", n),
        "top1": top[0][1] if top else None, "top25": top[-1][1] if top else None,
        "talk": list(dict.fromkeys(talk)),
    }


def finding(s: dict, cls: dict) -> str:
    sign_ = lambda x: "" if x is None else (f" ({x:+.2f} in 6h)" if abs(x) < 1000 else f" ({x:+,.0f} in 6h)")
    stance = ""
    if cls.get("sampled"):
        parts = ", ".join(f"{round(100 * v / cls['sampled'])}% {k}" for k, v in list(cls["counts"].items())[:3])
        stance = f" Trading-room chatter, {cls['sampled']} lines read by a model: {parts}."
    return (
        f"Close Call watch {s['at']}, sweep {s['n']}: NVDA reference {s['px']}{sign_(s['px_d'])}, "
        f"{s['long_pct']}% of open contracts long, open interest {float(s['open'] or 0):,.0f} POLF, "
        f"{s['owners']:,} owner keys{sign_(s['owners_d'])}. Top score {s['top1']}, 25th {s['top25']}."
        f"{stance} Method: github.com/mamijsp/close-call-watch"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--room", default="crypto")
    ap.add_argument("--classify", type=int, default=60)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--backend", default="")
    ap.add_argument("--budget", type=float, default=0, help="unused; kept for the shared runner")
    args = ap.parse_args()

    key = load_key()
    did = did_of(key)
    s = measure()
    print(f"sampled  : sweep {s['n']}  px {s['px']}  long {s['long_pct']}%  owners {s['owners']}  "
          f"top {s['top1']}/{s['top25']}  chatter {len(s['talk'])}")

    cls: dict = {}
    if args.classify > 0 and s["talk"]:
        cls = core.classify(s["talk"], inference.choose_backend(args.backend), CATEGORIES, HEAD,
                            args.classify, args.batch)
        print(f"classify : {cls['sampled']} lines, {cls['calls']} calls"
              + (f" — {cls['failed'][:120]}" if cls["failed"] else ""))

    spend = inference.totals()
    message = finding(s, cls)
    print(f"ledger   : {spend['calls']} calls\n\nwould post to r/{args.room}:\n  {message}")
    if not args.publish:
        print("\ndry run. pass --publish to send it.")
        return
    code, body = core.publish_say(key, did, args.room, message, UA, clean_text, sign)
    print(f"say  -> {code} {body.strip()[:120]}")
    fp = (HERE / "fp.txt").read_text(encoding="utf-8").strip()
    note = (f"close-call-watch {s['at']} n={s['n']} px={s['px']} long%={s['long_pct']} "
            f"spent {spend['calls']}calls/{spend['tokens']}tok")
    ncode, _ = core.publish_note(fp, note, UA, clean_text)
    print(f"note -> {ncode}")
    if code != 200 or ncode != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
