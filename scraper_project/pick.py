"""
Freedom Wall Scraper — Interactive Launcher

Run this instead of typing command-line arguments.
Each researcher picks their assigned Freedom Wall from the menu.

Usage:
    python pick.py
"""

import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# All available Freedom Wall pages (must match config.py TARGETS)
# ---------------------------------------------------------------------------

PAGES = [
    {"code": "SLU",   "name": "Saint Louis University (Baguio)"},
    {"code": "FW-01", "name": "Ateneo de Manila University"},
    {"code": "FW-02", "name": "UP Diliman"},
    {"code": "FW-03", "name": "Far Eastern University"},
    {"code": "FW-04", "name": "UP Los Banos"},
    {"code": "FW-05", "name": "Lyceum of the Philippines"},
    {"code": "FW-06", "name": "Caraga State University"},
    {"code": "FW-07", "name": "University of the Philippines Baguio"},
    {"code": "FW-08", "name": "Benguet State University"},
    {"code": "FW-09", "name": "University of Baguio"},
]

COOKIES_FILE = "cookies.json"
DEFAULT_POSTS = 4000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    print()
    print("=" * 62)
    print("   FREEDOM WALL SCRAPER  --  Interactive Launcher")
    print("=" * 62)
    print()


def check_cookies() -> bool:
    """Return True if cookies.json exists next to this script."""
    path = os.path.join(os.path.dirname(__file__), COOKIES_FILE)
    return os.path.isfile(path)


def print_menu():
    print("  #    Code     Institution")
    print("  --   ------   " + "-" * 42)
    for i, page in enumerate(PAGES, start=1):
        print(f"  {i:<3}  {page['code']:<7}  {page['name']}")
    print()
    print("  Type one number, multiple numbers (e.g. 1 3 7),")
    print("  or 'all' to select every page.")
    print()


def parse_selection(raw: str) -> list[dict] | None:
    """
    Parse user input into a list of selected PAGES entries.
    Returns None on invalid input.
    """
    raw = raw.strip().lower()

    if raw in ("all", "a"):
        return PAGES[:]

    # Accept space- or comma-separated numbers
    tokens = raw.replace(",", " ").split()
    if not tokens:
        return None

    selected = []
    seen = set()
    for token in tokens:
        if not token.isdigit():
            return None
        idx = int(token) - 1  # 1-based -> 0-based
        if idx < 0 or idx >= len(PAGES):
            return None
        if idx not in seen:
            selected.append(PAGES[idx])
            seen.add(idx)

    return selected if selected else None


def ask_target_posts() -> int:
    """Prompt for target posts per page; default 4000."""
    while True:
        raw = input(f"  Target posts per page [{DEFAULT_POSTS}]: ").strip()
        if raw == "":
            return DEFAULT_POSTS
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("  Please enter a positive number (or press Enter for default).")


def confirm(selected: list[dict], target_posts: int) -> bool:
    """Show summary and ask Y/n."""
    print()
    print("  Selected pages:")
    for page in selected:
        print(f"    - {page['code']}  ({page['name']})")
    print()
    print(f"  Target posts per page : {target_posts}")
    print(f"  Cookie file           : {COOKIES_FILE}")
    print()

    raw = input("  Start scraping? [Y/n]: ").strip().lower()
    return raw in ("", "y", "yes")


def run_scraper(selected: list[dict], target_posts: int):
    """Build the command and hand off to main.py."""
    codes = [p["code"] for p in selected]
    cmd = [
        sys.executable, "main.py",
        "--cookies", COOKIES_FILE,
        "--targets", *codes,
        "--target-posts", str(target_posts),
    ]

    print()
    print("  Running: " + " ".join(cmd))
    print()
    print("=" * 62)
    print()

    # Replace current process — output goes straight to terminal
    if os.name == "nt":
        subprocess.run(cmd)
    else:
        os.execvp(sys.executable, cmd)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main():
    clear()
    header()

    # --- Cookie check ---
    if not check_cookies():
        print("  [!] cookies.json not found.")
        print()
        print("  You need to log in first. Run this once:")
        print("      python extract_cookies.py")
        print()
        input("  Press Enter to exit...")
        sys.exit(1)

    # --- Page selection ---
    print_menu()
    selected = None
    while selected is None:
        raw = input("  Your selection: ")
        selected = parse_selection(raw)
        if selected is None:
            print("  Invalid input. Enter numbers from the list above.\n")

    # --- Target posts ---
    print()
    target_posts = ask_target_posts()

    # --- Confirm ---
    if not confirm(selected, target_posts):
        print()
        print("  Cancelled. Run python pick.py again to start over.")
        sys.exit(0)

    # --- Go ---
    run_scraper(selected, target_posts)


if __name__ == "__main__":
    main()
