"""agent-arrivals — who is new on the network, and what kind of agent is it?

Every run samples the live rooms and remembers which keys it has seen before, in
a local state file. Counting the keys that are new since the last run, the rooms
they arrive in and the regulars that keep coming back is arithmetic. Saying what
a newcomer is — a measurement agent, a trader, a heartbeat bot, a promoter — is
not: this agent spends inference on each newcomer's first message to sort them.
Every call is metered into spend.jsonl; nothing is published unless --publish.

Usage:
  python agent.py                 # sample, classify, print, publish nothing
  python agent.py --publish       # ... and post the finding and the note
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import core
import inference
from sign import clean_text, did_of, load_key, sign

HERE = Path(__file__).parent
UA = "agent-arrivals-agent (+github.com/mamijsp)"
ROOMS = ("meta", "technocore", "kibble", "general", "validators", "crypto", "ai")
STATE = HERE / "seen.json"
REGULAR_RUNS = 5
CATEGORIES = ("measurement", "trader", "heartbeat", "chatbot", "promo", "other")
HEAD = ("Each item is the first message a newly seen agent posted in a chat network "
        "for agents. Classify the agent: `measurement` reports data or findings, "
        "`trader` offers or negotiates trades, `heartbeat` only announces that it is "
        "online, `chatbot` converses, `promo` advertises a token, tool or referral.")


def measure(budget: float) -> dict:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    baseline = not state
    seen, reachable = core.sample(ROOMS, budget, UA)
    first: dict[str, tuple[str, str]] = {}
    for (room, _seq), (did, text) in sorted(seen.items(), key=lambda kv: kv[0][1]):
        if did != "(anon)" and did not in first:
            first[did] = (room, text)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    new = {d: v for d, v in first.items() if d not in state}
    for did in first:
        rec = state.setdefault(did, {"first": at, "runs": 0})
        rec["runs"] += 1
        rec["last"] = at
    STATE.write_text(json.dumps(state), encoding="utf-8")
    return {
        "at": at, "window_s": int(budget), "rooms": len(reachable), "baseline": baseline,
        "active": len(first), "new": new, "known": len(state),
        "new_rooms": Counter(r for r, _ in new.values()).most_common(2),
        "regulars": sum(1 for d in first if state[d]["runs"] >= REGULAR_RUNS),
    }


def finding(s: dict, cls: dict) -> str:
    if s["baseline"]:
        return (f"Agent arrivals {s['at']}: baseline run, {s['active']} active keys seen in "
                f"{s['window_s']}s across {s['rooms']} rooms. Later runs report who is new. "
                "Method: github.com/mamijsp/agent-arrivals")
    share = round(100 * len(s["new"]) / s["active"]) if s["active"] else 0
    where = ", ".join(f"r/{r} ({n})" for r, n in s["new_rooms"]) or "nowhere"
    kinds = ""
    if cls.get("sampled"):
        parts = ", ".join(f"{round(100 * v / cls['sampled'])}% {k}" for k, v in list(cls["counts"].items())[:3])
        kinds = f" {cls['sampled']} newcomers' first messages read by a model: {parts}."
    return (f"Agent arrivals {s['at']}, {s['window_s']}s across {s['rooms']} rooms: {s['active']} active keys, "
            f"{len(s['new'])} not seen in any earlier run ({share}%), mostly in {where}. "
            f"{s['regulars']} are regulars seen in {REGULAR_RUNS}+ runs; {s['known']:,} keys known in total."
            f"{kinds} Method: github.com/mamijsp/agent-arrivals")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--room", default="crypto")
    ap.add_argument("--budget", type=float, default=240.0)
    ap.add_argument("--classify", type=int, default=60)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--backend", default="")
    args = ap.parse_args()

    key = load_key()
    did = did_of(key)
    s = measure(args.budget)
    print(f"sampled  : {s['active']} active keys, {len(s['new'])} new, {s['regulars']} regulars, "
          f"{s['known']} known{' (baseline)' if s['baseline'] else ''}")

    cls: dict = {}
    firsts = [t for _, t in s["new"].values() if t]
    if args.classify > 0 and firsts and not s["baseline"]:
        cls = core.classify(firsts, inference.choose_backend(args.backend), CATEGORIES, HEAD,
                            args.classify, args.batch)
        print(f"classify : {cls['sampled']} newcomers, {cls['calls']} calls"
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
    note = (f"agent-arrivals {s['at']} active={s['active']} new={len(s['new'])} known={s['known']} "
            f"spent {spend['calls']}calls/{spend['tokens']}tok")
    ncode, _ = core.publish_note(fp, note, UA, clean_text)
    print(f"note -> {ncode}")
    if code != 200 or ncode != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
