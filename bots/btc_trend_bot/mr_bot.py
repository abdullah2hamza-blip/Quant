"""Compatibility entry point; the unvalidated mean-reversion strategy is retired."""
import sys
from trend_bot import main

if __name__ == "__main__":
    print("mr_bot.py now runs the paper-aligned EMA bot. Use trend_bot.py for new commands.", file=sys.stderr)
    raise SystemExit(main())
