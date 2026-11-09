import json
import re
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from core.config import EXPORTS_DIR
from core.database import get_metadata, set_metadata

SETTINGS_FILE = EXPORTS_DIR / "export_settings.json"


def parse_export_datetime(folder_path: Path):
    """Attempt to parse date from Letterboxd export folder name.
    Pattern: ...-YYYY-MM-DD-HH-MM-utc
    """
    if not folder_path:
        return None
    name = folder_path.name
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", name)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
            )
        except ValueError:
            pass
    # Fallback to filesystem modification time
    try:
        return datetime.fromtimestamp(folder_path.stat().st_mtime)
    except Exception:
        return None


def get_stored_export_folder(conn=None):
    """Retrieve previously stored export folder from app_metadata or json file."""
    # 1. Try DB app_metadata
    if conn:
        try:
            val = get_metadata(conn, "last_export_folder")
            if val:
                path = EXPORTS_DIR / val
                if path.exists():
                    return path
        except Exception:
            pass

    # 2. Try JSON settings in data_exports
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                folder_name = data.get("last_export_folder")
                if folder_name:
                    path = EXPORTS_DIR / folder_name
                    if path.exists():
                        return path
        except Exception:
            pass

    return None


def save_stored_export_folder(conn, folder_path: Path):
    """Store the chosen folder in app_metadata table and export_settings.json."""
    folder_name = folder_path.name
    now_iso = datetime.now().isoformat()

    # 1. Save in app_metadata
    if conn:
        try:
            set_metadata(conn, "last_export_folder", folder_name)
            set_metadata(conn, "last_export_folder_path", str(folder_path.resolve()))
        except Exception as e:
            print(f"Warning: could not save export folder to DB metadata: {e}")

    # 2. Save in export_settings.json in data_exports directory
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_export_folder": folder_name,
                "path": str(folder_path.resolve()),
                "saved_at": now_iso
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: could not save export_settings.json: {e}")


def get_latest_export_folder():
    """Find the most recent export folder in EXPORTS_DIR."""
    if not EXPORTS_DIR.exists():
        return None

    folders = [f for f in EXPORTS_DIR.iterdir() if f.is_dir() and (f / "ratings.csv").exists()]
    if not folders:
        folders = [f for f in EXPORTS_DIR.iterdir() if f.is_dir()]
    if not folders:
        return None

    def sort_key(p):
        dt = parse_export_datetime(p)
        return dt or datetime.min

    return sorted(folders, key=sort_key, reverse=True)[0]


def select_export_folder(conn=None, interactive=True):
    """Ask user whether to use the latest export or choose another folder using Tkinter.
    Warns if the selected folder is newer than stored folder.
    Saves the choice to app_metadata and export_settings.json.
    """
    latest_folder = get_latest_export_folder()
    stored_folder = get_stored_export_folder(conn)

    if not interactive:
        chosen = latest_folder or stored_folder
        if chosen and conn:
            save_stored_export_folder(conn, chosen)
        return chosen

    # Initialize Tkinter GUI
    root = tk.Tk()
    root.title("Letterboxd Export Selector")
    root.geometry("540x300")
    root.resizable(False, False)

    # Bring to front
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)

    chosen_folder = {"path": None}

    def on_use_latest():
        chosen_folder["path"] = latest_folder
        root.destroy()

    def on_choose_other():
        root.withdraw()
        selected = filedialog.askdirectory(
            initialdir=str(EXPORTS_DIR),
            title="Select Letterboxd Export Folder"
        )
        if selected:
            selected_path = Path(selected)
            if not (selected_path / "ratings.csv").exists():
                messagebox.showerror(
                    "Invalid Export Folder",
                    f"Selected folder does not contain 'ratings.csv':\n\n{selected_path}\n\nPlease choose a valid Letterboxd export folder."
                )
                root.deiconify()
                return
            chosen_folder["path"] = selected_path
            root.destroy()
        else:
            root.deiconify()

    def on_cancel():
        root.destroy()
        print("Export selection cancelled by user.")
        sys.exit(0)

    # UI Widgets
    title_label = tk.Label(
        root,
        text="Letterboxd Data Analyzer",
        font=("Segoe UI", 14, "bold")
    )
    title_label.pack(pady=(15, 4))

    sub_label = tk.Label(
        root,
        text="Select the Letterboxd export folder to process into your database:",
        font=("Segoe UI", 10)
    )
    sub_label.pack(pady=(0, 14))

    # Info display frame
    info_frame = tk.Frame(root, padx=16, pady=10, relief=tk.GROOVE, borderwidth=1)
    info_frame.pack(fill=tk.X, padx=24)

    latest_name = latest_folder.name if latest_folder else "None found"
    stored_name = stored_folder.name if stored_folder else "None previously stored"

    lbl_latest = tk.Label(
        info_frame,
        text=f"Latest Detected Export:\n  {latest_name}",
        font=("Segoe UI", 9, "bold"),
        fg="#008037",
        justify=tk.LEFT
    )
    lbl_latest.pack(anchor="w", pady=2)

    lbl_stored = tk.Label(
        info_frame,
        text=f"Previously Stored Export:\n  {stored_name}",
        font=("Segoe UI", 8),
        fg="#555555",
        justify=tk.LEFT
    )
    lbl_stored.pack(anchor="w", pady=2)

    # Action buttons
    btn_frame = tk.Frame(root, pady=16)
    btn_frame.pack()

    btn_latest = tk.Button(
        btn_frame,
        text="Use Latest Export",
        command=on_use_latest,
        width=18,
        bg="#00d75a",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        cursor="hand2"
    )
    btn_latest.pack(side=tk.LEFT, padx=6)

    btn_other = tk.Button(
        btn_frame,
        text="Choose Other Folder...",
        command=on_choose_other,
        width=20,
        font=("Segoe UI", 9),
        cursor="hand2"
    )
    btn_other.pack(side=tk.LEFT, padx=6)

    btn_cancel = tk.Button(
        btn_frame,
        text="Cancel",
        command=on_cancel,
        width=10,
        font=("Segoe UI", 9),
        cursor="hand2"
    )
    btn_cancel.pack(side=tk.LEFT, padx=6)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()

    selected_folder = chosen_folder["path"]
    if not selected_folder:
        print("No folder selected. Exiting.")
        sys.exit(0)

    # Check if selected folder is newer than stored folder -> warn user
    if stored_folder and selected_folder != stored_folder:
        selected_dt = parse_export_datetime(selected_folder)
        stored_dt = parse_export_datetime(stored_folder)

        is_newer = False
        if selected_dt and stored_dt:
            is_newer = selected_dt > stored_dt
        else:
            is_newer = selected_folder.name > stored_folder.name

        if is_newer:
            warn_msg = (
                f"Warning: The selected export folder:\n\n"
                f"  '{selected_folder.name}'\n\n"
                f"is NEWER than the previously stored folder:\n\n"
                f"  '{stored_folder.name}'.\n\n"
                f"Importing will update your database with newer ratings and active films."
            )
            print(f"\n[WARNING] {warn_msg}\n")
            warn_root = tk.Tk()
            warn_root.withdraw()
            warn_root.attributes("-topmost", True)
            messagebox.showwarning("Newer Export Selected", warn_msg, parent=warn_root)
            warn_root.destroy()

    # Save selection to app_metadata and export_settings.json
    save_stored_export_folder(conn, selected_folder)

    print(f"Selected export folder: {selected_folder.name}\n")
    return selected_folder
