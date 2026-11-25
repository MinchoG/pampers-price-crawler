"""Interactive entry point for the desktop launchers."""
import subprocess
import sys


def main():
    product = input("Diaper brand and range [Pampers Premium Care]: ").strip() or "Pampers Premium Care"
    while True:
        size = input("Diaper size [1]: ").strip() or "1"
        if size in "012345678" and len(size) == 1:
            break
        print("Enter a size from 0 to 8.")
    print("Checking the stores. Prices will appear when the search finishes.", flush=True)
    return subprocess.call([
        sys.executable, "-c", "from pampers_prices.compare import main; main()",
        "--category", "diapers", "--query", product, "--size", size, "--sites", "all",
    ])


if __name__ == "__main__":
    sys.exit(main())
