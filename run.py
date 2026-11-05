import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable
MAIN_SCRIPT = PROJECT_ROOT / "core" / "main.py"
DASHBOARD_SCRIPT = PROJECT_ROOT / "dashboard" / "app.py"


def run_ingestion(extra_args=None):
    """Run core/main.py data ingestion pipeline."""
    cmd = [PYTHON_EXE, str(MAIN_SCRIPT)]
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n[Launcher] Running ingestion pipeline: {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return proc.returncode == 0


def run_dashboard():
    """Launch the interactive Streamlit dashboard."""
    cmd = [PYTHON_EXE, "-m", "streamlit", "run", str(DASHBOARD_SCRIPT)]
    print(f"\n[Launcher] Starting Streamlit dashboard: {' '.join(cmd)}\n")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT))


def interactive_menu():
    """Show interactive selection menu when launched without arguments."""
    print("\n" + "=" * 58)
    print("        🎬 LETTERBOXD DATA ANALYZER LAUNCHER")
    print("=" * 58)
    print("  [1] Ingest Data & Open Dashboard (Default)")
    print("  [2] Open Dashboard Directly (View Previous Data)")
    print("  [3] Ingest Data Only (Run main.py without Dashboard)")
    print("  [4] Exit")
    print("=" * 58)

    try:
        choice = input("Enter your choice [1-4] (default: 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(0)

    if choice in ("", "1"):
        success = run_ingestion()
        if success:
            run_dashboard()
    elif choice == "2":
        run_dashboard()
    elif choice == "3":
        run_ingestion()
    elif choice == "4":
        print("Goodbye!")
        sys.exit(0)
    else:
        print(f"Invalid choice '{choice}'. Running default option (1)...")
        if run_ingestion():
            run_dashboard()


def main():
    parser = argparse.ArgumentParser(
        description="Letterboxd Data Analyzer - Unified Launcher"
    )
    parser.add_argument(
        "-d", "--dashboard",
        action="store_true",
        help="Launch the Streamlit dashboard directly using previous database data"
    )
    parser.add_argument(
        "-i", "--ingest",
        action="store_true",
        help="Run data ingestion pipeline (main.py) only without opening dashboard"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Run data ingestion pipeline and automatically open dashboard"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Automatically use latest export without GUI prompt when running ingestion"
    )
    args = parser.parse_args()

    if args.dashboard:
        run_dashboard()
    elif args.ingest:
        extra = ["--latest"] if args.latest else []
        run_ingestion(extra)
    elif args.all:
        extra = ["--latest"] if args.latest else []
        if run_ingestion(extra):
            run_dashboard()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
