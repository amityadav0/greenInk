"""Pre-warm a deployment: run the suggestion searches and open reports for the best bids, so
judges get instant, cached results.

    uv run python scripts/prewarm.py https://your-app.up.railway.app --reports 20

Set RATE_LIMIT_EXEMPT_TOKEN (same value as on the API) to skip the per-IP report limit.
Costs Token Factory credits (about $0.04-0.11 per new report; searches are a fraction of a
cent). Reports that already exist are free. Asks before spending unless --yes is given.
"""

import argparse
import os
import sys
import time

import httpx

SUGGESTIONS = [
    "current transformer",
    "potential transformer",
    "energy meter",
    "LED street light",
    "distribution transformer",
    "LT panel",
    "cable",
    "office chair",
]
BADGE_RANK = {"green": 0, "amber": 1, "red": 2}
EST_PER_REPORT_USD = 0.08


def wait_for_badges(client: httpx.Client, query: str, timeout_s: float = 60) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_s
    while True:
        results: list[dict[str, object]] = client.get("/v1/search", params={"q": query}).json()["results"]
        if all(r.get("badge") for r in results) or time.monotonic() > deadline:
            return results
        time.sleep(3)


def wait_for_report(client: httpx.Client, status_url: str, timeout_s: float = 240) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    while True:
        analysis: dict[str, object] = client.get(status_url).json()["analysis"]
        if analysis["status"] in ("done", "partial", "failed") or time.monotonic() > deadline:
            return analysis
        time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("base_url", help="the deployed web app (it proxies /v1 to the API)")
    parser.add_argument("--reports", type=int, default=20, help="reports to open in total")
    parser.add_argument("--yes", action="store_true", help="don't ask before spending credits")
    parser.add_argument(
        "--report-queries",
        default="current transformer,potential transformer",
        help="comma list: only these searches get reports (the demo company's own products)",
    )
    args = parser.parse_args()

    if not args.yes:
        estimate = args.reports * EST_PER_REPORT_USD
        answer = input(f"Open up to {args.reports} reports (about ${estimate:.2f} of credits)? [y/N] ")
        if answer.strip().lower() != "y":
            return 1

    token = os.environ.get("RATE_LIMIT_EXEMPT_TOKEN")
    headers = {"X-Greenink-Admin": token} if token else {}
    with httpx.Client(
        base_url=args.base_url.rstrip("/"), timeout=120, follow_redirects=True, headers=headers
    ) as client:
        demo = client.get("/v1/companies").json()[0]
        report_queries = {q.strip().lower() for q in args.report_queries.split(",") if q.strip()}
        candidates: list[tuple[int, dict[str, object]]] = []
        for query in SUGGESTIONS:
            results = wait_for_badges(client, query)
            badges = [r["badge"]["level"] for r in results if r.get("badge")]  # type: ignore[index]
            print(f"search {query!r}: {len(results)} bids, {badges.count('green')} green")
            if query.lower() not in report_queries:
                continue
            for bid in results:
                badge = bid.get("badge") or {"level": "red"}
                level = badge["level"]  # type: ignore[index]
                # Only bids that are really for this product and not judged out of reach:
                # anything else spends credits on reports nobody will open.
                if level == "red" or query.lower() not in " ".join(str(bid["title"]).lower().split()):
                    continue
                candidates.append((BADGE_RANK[level], bid))

        candidates.sort(key=lambda c: c[0])
        opened = 0
        seen: set[object] = set()
        for _, bid in candidates:
            if opened >= args.reports:
                break
            if bid["tender_id"] in seen:
                continue
            seen.add(bid["tender_id"])
            accepted = client.post(
                "/v1/analyses", json={"tender_id": bid["tender_id"], "company_id": demo["id"]}
            )
            if accepted.status_code == 429:
                print("rate limited; stopping (the API allows 10 new reports per hour per IP)")
                break
            body = accepted.json()
            analysis = wait_for_report(client, body["status_url"])
            opened += 1
            print(
                f"report {opened:2}: {analysis['status']:8} {analysis.get('verdict') or '-':13} "
                f"{'cached' if body['cached'] else 'new':6} {str(bid['title'])[:60]}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
