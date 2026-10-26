"""Evaluation: 20 GeM bids x 3 configurations (Lightning only, Super only, routed).

Writes eval/results.csv and a chart. Metrics: disqualifier recall, precision, citation
validity, cost per tender, latency per tender (docs/PLAN.md "Evaluation and limitations").
"""

import sys


def main() -> int:
    raise NotImplementedError("TODO(lane-A): run configs over eval/tenders + labels.jsonl")


if __name__ == "__main__":
    sys.exit(main())
