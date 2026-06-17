"""Score a trace read from stdin and print the result as JSON.

Usage:
    python tools/generate_pyautogui_trace.py | python server/score_cli.py
    cat tests/fixtures/human_sample.json | python server/score_cli.py
"""

import json
import sys

from scorer import score


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("no input on stdin", file=sys.stderr)
        return 1
    trace = json.loads(raw)
    result = score(trace)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
