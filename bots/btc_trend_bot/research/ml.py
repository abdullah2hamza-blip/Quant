"""The paper does not validate a machine-learning trading policy."""
import sys

if __name__ == "__main__":
    print("The legacy ML search is retired. Use run_all.py for the frozen EMA family; new ML research requires a new protocol and evaluation.", file=sys.stderr)
    raise SystemExit(2)
