"""Cloudflare free-tier usage check for the whole account (all projects).

Reads wrangler's OAuth token from ~/.config/.wrangler/config/default.toml
(never printed). Run `npx wrangler whoami` first so wrangler refreshes it.
"""

import datetime as dt
import json
import os
import sys
import tomllib
import urllib.request

ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "e4a32e315e6b457ffc89087f65bb0645")
LIMITS = {"worker_requests": 100_000, "do_requests": 100_000, "do_gbs": 13_000}
WARN = float(os.environ.get("CF_WARN", "0.5"))


def token() -> str:
    path = os.path.expanduser("~/.config/.wrangler/config/default.toml")
    with open(path, "rb") as f:
        return tomllib.load(f)["oauth_token"]


def call(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rest(path: str) -> list:
    out = call(f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/{path}")
    return out.get("result") or []


GQL = """query($a: String!, $s: Time!, $e: Time!, $d: Date!) {
  viewer { accounts(filter: {accountTag: $a}) {
    w: workersInvocationsAdaptive(limit: 100, filter: {datetime_geq: $s, datetime_lt: $e}) {
      sum { requests errors subrequests } dimensions { scriptName } }
    di: durableObjectsInvocationsAdaptiveGroups(limit: 100, filter: {date_geq: $d, date_leq: $d}) {
      sum { requests } dimensions { scriptName } }
    dp: durableObjectsPeriodicGroups(limit: 100, filter: {date_geq: $d, date_leq: $d}) {
      sum { activeTime inboundWebsocketMsgCount } dimensions { namespaceId } }
  } } }"""


def main() -> int:
    now = dt.datetime.now(dt.UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"Cloudflare account usage, UTC day {start:%Y-%m-%d} (resets 00:00 UTC), now {now:%H:%M}")
    scripts = rest("workers/scripts")
    print("Workers:", ", ".join(s["id"] for s in scripts) or "none")
    ns = rest("workers/durable_objects/namespaces")
    print("DO namespaces:", ", ".join(f"{n.get('script')}/{n.get('class')}" for n in ns) or "none")

    data = call(
        "https://api.cloudflare.com/client/v4/graphql",
        {
            "query": GQL,
            "variables": {
                "a": ACCOUNT,
                "s": start.isoformat(),
                "e": now.isoformat(),
                "d": f"{start:%Y-%m-%d}",
            },
        },
    )
    if data.get("errors"):
        print("GraphQL errors:", [e.get("message") for e in data["errors"]])
        return 2
    acc = data["data"]["viewer"]["accounts"][0]
    wreq = sum(r["sum"]["requests"] for r in acc["w"])
    dreq = sum(r["sum"]["requests"] for r in acc["di"])
    # activeTime is in microseconds; free plan bills duration at 128 MB per object.
    gbs = sum(r["sum"]["activeTime"] for r in acc["dp"]) / 1e6 * 0.128
    for r in acc["w"]:
        print(
            f"  worker {r['dimensions']['scriptName']}: {r['sum']['requests']} req, "
            f"{r['sum']['errors']} errors"
        )
    for r in acc["di"]:
        print(f"  DO in {r['dimensions']['scriptName']}: {r['sum']['requests']} req")

    worst = 0.0
    for name, used in (("worker_requests", wreq), ("do_requests", dreq), ("do_gbs", gbs)):
        frac = used / LIMITS[name]
        worst = max(worst, frac)
        print(f"{name}: {used:,.0f} / {LIMITS[name]:,} ({frac:.1%})")
    if worst >= WARN:
        print(f"WARNING: usage at {worst:.0%} of a free-tier daily limit")
        return 1
    print("OK: all within free tier")
    return 0


if __name__ == "__main__":
    sys.exit(main())
