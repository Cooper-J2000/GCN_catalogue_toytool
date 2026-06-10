#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCN GRB Catalogue Tool
======================
Interactive tool for extracting observation records from GCN Circular JSON files
and saving them into structured data tables.

Layout:
  +------------------+--------------------------------+
  |                  |  GRB Info Management (top)     |
  |  GCN JSON        +--------------------------------+
  |  Browser         |  Observation Entry (bottom)    |
  |  (Left)          |                                |
  +------------------+--------------------------------+
  
This toolkit was entirely generated through Vibe Coding using Kimi.
"""

import os
import sys
import json
import csv
import re
import shutil
import tarfile
import tkinter as tk
import urllib.request
from tkinter import ttk, messagebox, scrolledtext, font as tkfont
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ============================================================================
# Configuration
# ============================================================================

PROJECT_DIR = Path(__file__).parent.resolve()
GCN_ARCHIVE_DIR = PROJECT_DIR / "archive.json"
CATA_OUTPUT_DIR = PROJECT_DIR / "Cata_output"
GRB_INFO_DIR = CATA_OUTPUT_DIR / "grb_info"
GRB_LC_DIR = CATA_OUTPUT_DIR / "grb_lc"
COLTITLE_FILE = PROJECT_DIR / "coltitle.txt"

# Colors and Styles
COLOR_BG = "#f5f5f5"
COLOR_LEFT_BG = "#fafafa"
COLOR_RIGHT_TOP_BG = "#f0f4f8"
COLOR_RIGHT_BOTTOM_BG = "#f8f6f0"
COLOR_HIGHLIGHT_NUM = "#d9534f"  # Red for numbers
COLOR_HIGHLIGHT_BG = "#fff3cd"   # Light yellow background
COLOR_BORDER = "#cccccc"
COLOR_BUTTON_BG = "#337ab7"
COLOR_BUTTON_FG = "white"
COLOR_BUTTON_ACTIVE = "#286090"
COLOR_READONLY_BG = "#e8e8e8"
COLOR_CURRENT_FILE = "#5cb85c"

# Font configuration
FONT_FAMILY = "Consolas" if os.name == "nt" else "DejaVu Sans Mono"
FONT_SIZE_NORMAL = 13
FONT_SIZE_SMALL = 11
FONT_SIZE_TITLE = 15


# ============================================================================
# Utility Functions
# ============================================================================

def ensure_directories():
    """Create necessary directories if they don't exist."""
    for d in [GCN_ARCHIVE_DIR, CATA_OUTPUT_DIR, GRB_INFO_DIR, GRB_LC_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_coltitles():
    """Load column titles from coltitle.txt."""
    titles = []
    if COLTITLE_FILE.exists():
        with open(COLTITLE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    titles.append(line)
    return titles


def get_gcn_files():
    """Get sorted list of JSON files in GCN archive directory (sorted numerically)."""
    if not GCN_ARCHIVE_DIR.exists():
        return []
    files = [f for f in GCN_ARCHIVE_DIR.iterdir() if f.suffix.lower() == ".json"]
    # Sort by numeric value of filename
    def sort_key(f):
        try:
            return int(f.stem)
        except ValueError:
            return float('inf')
    files.sort(key=sort_key)
    return files


def get_grb_info_files():
    """Get list of existing GRB info JSON files."""
    if not GRB_INFO_DIR.exists():
        return []
    files = [f for f in GRB_INFO_DIR.iterdir() if f.suffix.lower() == ".json"]
    files.sort(key=lambda f: f.stem)
    return files


def format_json_content(data):
    """Format JSON data for display with syntax highlighting preparation."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def extract_numbers(text):
    """Extract all numbers from text with their positions for highlighting."""
    # Match integers, decimals, scientific notation
    pattern = re.compile(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?')
    matches = []
    for m in pattern.finditer(text):
        matches.append((m.start(), m.end(), m.group()))
    return matches


# ============================================================================
# Left Panel: GCN JSON Browser
# ============================================================================

class GCNBrowserPanel(ttk.Frame):
    """Left panel for browsing GCN JSON files with number highlighting."""

    def __init__(self, parent, on_file_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_file_change = on_file_change
        self.current_files = []  # List of Path objects
        self.current_index = -1

        self._build_ui()
        self._load_file_list()

    def _build_ui(self):
        """Build the UI components."""
        self.configure(padding=5)

        # ===== Top control bar =====
        control_frame = ttk.Frame(self)
        control_frame.pack(fill=tk.X, pady=(0, 5))

        # File selector
        ttk.Label(control_frame, text="GCN:", font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold")).pack(side=tk.LEFT, padx=(0, 3))

        self.file_var = tk.StringVar()
        self.file_combo = ttk.Combobox(control_frame, textvariable=self.file_var, width=14, state="readonly")
        self.file_combo.pack(side=tk.LEFT, padx=(0, 3))
        self.file_combo.bind("<<ComboboxSelected>>", self._on_combo_select)

        # Quick jump to GCN ID
        ttk.Label(control_frame, text="Jump:", font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(side=tk.LEFT, padx=(5, 2))
        self.jump_var = tk.StringVar()
        self.jump_entry = ttk.Entry(control_frame, textvariable=self.jump_var, width=8, font=(FONT_FAMILY, FONT_SIZE_NORMAL))
        self.jump_entry.pack(side=tk.LEFT, padx=(0, 3))
        self.jump_entry.bind("<Return>", self._on_jump)
        ttk.Button(control_frame, text="Go", command=self._on_jump, width=4).pack(side=tk.LEFT, padx=(0, 5))

        # Navigation buttons
        self.btn_prev = ttk.Button(control_frame, text="<< Prev", command=self._go_prev, width=8)
        self.btn_prev.pack(side=tk.LEFT, padx=2)

        self.btn_next = ttk.Button(control_frame, text="Next >>", command=self._go_next, width=8)
        self.btn_next.pack(side=tk.LEFT, padx=2)

        # Separator
        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        # Download latest GCN archive
        self.btn_download = tk.Button(control_frame, text="Download Latest", command=self._download_latest,
                                       bg="#5cb85c", fg=COLOR_BUTTON_FG,
                                       activebackground="#449d44",
                                       font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                                       width=14, cursor="hand2", relief=tk.FLAT, padx=8, pady=3)
        self.btn_download.pack(side=tk.LEFT, padx=2)

        # Current file indicator
        self.lbl_current = ttk.Label(control_frame, text="No file", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                     foreground="#666666")
        self.lbl_current.pack(side=tk.RIGHT, padx=5)

        # ===== Separator =====
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        # ===== JSON text display =====
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar for text display
        toolbar = ttk.Frame(text_frame)
        toolbar.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(toolbar, text="JSON Content (numbers highlighted):",
                  font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold")).pack(side=tk.LEFT)

        # Scrollbars
        scroll_y = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        scroll_x = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        # Text widget for JSON display
        self.text_display = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=(FONT_FAMILY, FONT_SIZE_NORMAL),
            bg=COLOR_LEFT_BG,
            fg="#333333",
            padx=10,
            pady=10,
            spacing1=6,
            spacing3=2,
            undo=False,
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set
        )
        self.text_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.text_display.yview)
        scroll_x.config(command=self.text_display.xview)

        # Configure tags for highlighting
        self.text_display.tag_configure("number", foreground=COLOR_HIGHLIGHT_NUM, font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"))
        self.text_display.tag_configure("key", foreground="#2e6da4", font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"))
        self.text_display.tag_configure("string", foreground="#5cb85c")
        self.text_display.tag_configure("boolean", foreground="#f0ad4e")
        self.text_display.tag_configure("null", foreground="#f0ad4e")

        self.text_display.config(state=tk.DISABLED)

        # ===== Time Calculator (narrow strip below JSON viewer) =====
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 4))

        calc_outer = ttk.Frame(self)
        calc_outer.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(calc_outer, text="Time Calculator",
                  font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                  foreground=COLOR_BUTTON_BG).pack(anchor=tk.W, pady=(0, 4))

        calc_frame = ttk.Frame(calc_outer)
        calc_frame.pack(fill=tk.X)

        # --- Row 1: time_1 ---
        row1 = ttk.Frame(calc_frame)
        row1.pack(fill=tk.X, pady=1)

        ttk.Label(row1, text="time 1:", width=8,
                  font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(side=tk.LEFT)

        self.calc_t1_var = tk.StringVar()
        self.calc_t1_entry = ttk.Entry(row1, textvariable=self.calc_t1_var,
                                        width=22, font=(FONT_FAMILY, FONT_SIZE_SMALL))
        self.calc_t1_entry.pack(side=tk.LEFT, padx=(0, 4))

        self.calc_t1_fmt = tk.StringVar(value="UTC")
        ttk.Combobox(row1, textvariable=self.calc_t1_fmt,
                      values=["UTC", "MJD"], width=5, state="readonly",
                      font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(side=tk.LEFT)

        # --- Row 2: time_2 ---
        row2 = ttk.Frame(calc_frame)
        row2.pack(fill=tk.X, pady=1)

        ttk.Label(row2, text="time 2:", width=8,
                  font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(side=tk.LEFT)

        self.calc_t2_var = tk.StringVar()
        self.calc_t2_entry = ttk.Entry(row2, textvariable=self.calc_t2_var,
                                        width=22, font=(FONT_FAMILY, FONT_SIZE_SMALL))
        self.calc_t2_entry.pack(side=tk.LEFT, padx=(0, 4))

        self.calc_t2_fmt = tk.StringVar(value="UTC")
        ttk.Combobox(row2, textvariable=self.calc_t2_fmt,
                      values=["UTC", "MJD"], width=5, state="readonly",
                      font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(side=tk.LEFT)

        # --- Calculate button + Results ---
        row3 = ttk.Frame(calc_frame)
        row3.pack(fill=tk.X, pady=(4, 1))

        self.btn_calc = tk.Button(row3, text="Calculate Δt", command=self._calc_delta_t,
                                   bg=COLOR_BUTTON_BG, fg=COLOR_BUTTON_FG,
                                   activebackground=COLOR_BUTTON_ACTIVE,
                                   font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                                   width=12, cursor="hand2", relief=tk.FLAT, padx=8, pady=3)
        self.btn_calc.pack(side=tk.LEFT, padx=(0, 8))

        self.calc_result_var = tk.StringVar(value="Δt =")
        self.calc_result_entry = tk.Entry(row3, textvariable=self.calc_result_var,
                                           font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                           fg="#333333", bg=COLOR_LEFT_BG,
                                           state="readonly", readonlybackground=COLOR_LEFT_BG,
                                           highlightthickness=0, bd=1)
        self.calc_result_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # Bind Enter key to calculate
        self.calc_t1_entry.bind("<Return>", self._calc_delta_t)
        self.calc_t2_entry.bind("<Return>", self._calc_delta_t)

        # Status bar
        self.status_bar = ttk.Label(self, text="Ready", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                    foreground="#666666", anchor=tk.W)
        self.status_bar.pack(fill=tk.X, pady=(5, 0))

    # -----------------------------------------------------------------
    # Time Calculator helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_utc(utc_str):
        """Parse a UTC string into an aware datetime.

        Supported formats:
          - 2025-06-10T12:34:56.789
          - 2025-06-10T12:34:56
          - 2025-06-10 12:34:56.789
          - 2025-06-10 12:34:56
        Returns (datetime, None) on success, (None, error_msg) on failure.
        """
        s = utc_str.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                # Assume UTC if no tzinfo provided
                return dt.replace(tzinfo=timezone.utc), None
            except ValueError:
                continue
        return None, f"Cannot parse '{utc_str}' as UTC.\nExpected: YYYY-MM-DD[T or space]HH:MM:SS[.fff]"

    @staticmethod
    def _parse_mjd(mjd_str):
        """Parse an MJD string (float) into an aware datetime.

        MJD 0 = 1858-11-17 00:00:00 UTC
        Returns (datetime, None) on success, (None, error_msg) on failure.
        """
        try:
            mjd = float(mjd_str.strip())
        except ValueError:
            return None, f"Cannot parse '{mjd_str}' as MJD. Expected a float."

        # MJD 0 = 1858-11-17 00:00:00
        mjd_epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
        delta_days = timedelta(days=mjd)
        dt = mjd_epoch + delta_days
        return dt, None

    @staticmethod
    def _format_mjd(dt):
        """Convert a datetime to MJD float."""
        mjd_epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
        delta = dt - mjd_epoch
        return delta.total_seconds() / 86400.0

    @staticmethod
    def _format_utc(dt):
        """Format a datetime to UTC string."""
        if dt.microsecond:
            return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}".rstrip("0")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    def _calc_delta_t(self, event=None):
        """Calculate and display the time difference."""
        t1_str = self.calc_t1_var.get().strip()
        t2_str = self.calc_t2_var.get().strip()

        if not t1_str or not t2_str:
            self.calc_result_var.set("Δt = (enter both times)")
            return

        # Parse time 1
        if self.calc_t1_fmt.get() == "UTC":
            t1, err = self._parse_utc(t1_str)
        else:
            t1, err = self._parse_mjd(t1_str)
        if err:
            self.calc_result_var.set(f"time 1 error: {err}")
            return

        # Parse time 2
        if self.calc_t2_fmt.get() == "UTC":
            t2, err = self._parse_utc(t2_str)
        else:
            t2, err = self._parse_mjd(t2_str)
        if err:
            self.calc_result_var.set(f"time 2 error: {err}")
            return

        # Compute delta in seconds
        delta_seconds = (t2 - t1).total_seconds()
        delta_min = delta_seconds / 60.0
        delta_hr = delta_seconds / 3600.0
        delta_day = delta_seconds / 86400.0

        # Format output
        parts = []
        parts.append(f"{delta_seconds:,.6f} s")
        parts.append(f"{delta_min:,.6f} min")
        parts.append(f"{delta_hr:,.6f} h")
        parts.append(f"{delta_day:,.8f} day")

        self.calc_result_var.set("Δt = " + "  |  ".join(parts))

    def _load_file_list(self):
        """Load the list of GCN JSON files."""
        self.current_files = get_gcn_files()
        if not self.current_files:
            self.file_combo["values"] = ["No files found"]
            self.file_combo.set("No files found")
            self.status_bar.config(text=f"Directory: {GCN_ARCHIVE_DIR} (empty)")
            return

        file_names = [f.name for f in self.current_files]
        self.file_combo["values"] = file_names
        self.status_bar.config(text=f"Total: {len(file_names)} files in {GCN_ARCHIVE_DIR.name}")

    def _download_latest(self):
        """Download and extract the latest GCN archive from NASA GCN.

        Downloads archive.json.tar.gz, extracts it (produces archive.json/),
        removes the tar.gz, and refreshes the file list.
        """
        url = "https://gcn.nasa.gov/circulars/archive.json.tar.gz"
        tar_path = PROJECT_DIR / "archive.json.tar.gz"
        archive_dir = PROJECT_DIR / "archive.json"
        backup_dir = PROJECT_DIR / "archive.json.backup"

        # Confirm with user
        if not messagebox.askyesno(
            "Confirm Download",
            "This will download the latest GCN archive from:\n\n"
            f"{url}\n\n"
            "The existing archive.json folder will be temporarily backed up "
            "and replaced with the latest data.\n\n"
            "Proceed?"
        ):
            return

        try:
            self.btn_download.config(state=tk.DISABLED, text="Downloading...")
            self.status_bar.config(text="Downloading archive.json.tar.gz ...")
            self.update_idletasks()

            # Step 1: Download
            urllib.request.urlretrieve(url, tar_path)
            self.status_bar.config(text="Download complete. Extracting...")
            self.update_idletasks()

            # Step 2: Backup existing archive.json if it exists
            if archive_dir.exists():
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.move(str(archive_dir), str(backup_dir))

            # Step 3: Extract tar.gz
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=PROJECT_DIR)

            # Step 4: Remove tar.gz
            tar_path.unlink()

            # Step 5: Clean up backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

            # Step 6: Refresh file list
            self._load_file_list()
            file_count = len(self.current_files)
            self.status_bar.config(
                text=f"GCN archive updated: {file_count} files in {archive_dir.name}"
            )
            messagebox.showinfo(
                "Success",
                f"Downloaded and extracted successfully.\n\n"
                f"{file_count} GCN JSON files now available."
            )

        except Exception as e:
            # Rollback: restore from backup if extraction failed
            if backup_dir.exists() and not archive_dir.exists():
                shutil.move(str(backup_dir), str(archive_dir))
            messagebox.showerror("Download Error", f"Failed to download/extract:\n\n{e}")
            self.status_bar.config(text="Download failed.")

        finally:
            # Clean up tar file if it still exists
            if tar_path.exists():
                tar_path.unlink()
            # Clean up backup if it still exists
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            self.btn_download.config(state=tk.NORMAL, text="Download Latest")

    def _on_combo_select(self, event=None):
        """Handle file selection from combobox."""
        selected = self.file_var.get()
        if not selected or selected == "No files found":
            return

        # Find index
        for i, f in enumerate(self.current_files):
            if f.name == selected:
                self.current_index = i
                break

        self._load_current_file()

    def _on_jump(self, event=None):
        """Jump to a specific GCN file by ID."""
        jump_id = self.jump_var.get().strip()
        if not jump_id:
            return
        # Try to find file with matching name (e.g., "40689" -> "40689.json")
        target_name = f"{jump_id}.json"
        for i, f in enumerate(self.current_files):
            if f.name == target_name:
                self.current_index = i
                self.file_var.set(target_name)
                self._load_current_file()
                self.jump_var.set("")
                return
        # Not found
        messagebox.showinfo("Not Found", f"GCN file #{jump_id} not found in archive.")

    def _go_prev(self):
        """Go to previous file."""
        if not self.current_files or self.current_index <= 0:
            return
        self.current_index -= 1
        self.file_var.set(self.current_files[self.current_index].name)
        self._load_current_file()

    def _go_next(self):
        """Go to next file."""
        if not self.current_files or self.current_index >= len(self.current_files) - 1:
            return
        self.current_index += 1
        self.file_var.set(self.current_files[self.current_index].name)
        self._load_current_file()

    def _load_current_file(self):
        """Load and display the current JSON file."""
        if self.current_index < 0 or self.current_index >= len(self.current_files):
            return

        file_path = self.current_files[self.current_index]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            messagebox.showerror("Error", f"Failed to load {file_path.name}:\n{e}")
            return

        # Update current file label
        self.lbl_current.config(text=f"#{file_path.stem}")

        # Format and display JSON
        formatted = format_json_content(data)

        self.text_display.config(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)

        # Insert text with syntax highlighting
        self._insert_with_highlighting(formatted)

        self.text_display.config(state=tk.DISABLED)

        # Update status
        self.status_bar.config(text=f"Loaded: {file_path.name} ({len(formatted)} chars)")

        # Notify parent
        if self.on_file_change:
            self.on_file_change(data, file_path)

    def _insert_with_highlighting(self, text):
        """Insert text with syntax highlighting for numbers, keys, and JSON values.
        
        Also converts escaped \\n inside string values into real line breaks
        with proper indentation so multi-line fields (especially "body")
        are readable.
        """
        # Replace escaped \n (two chars: backslash + n) with real newlines.
        # In json.dumps() output, string newlines appear as \n; structural
        # newlines are already real \n characters, so this only affects
        # text inside JSON string values.
        processed = self._expand_escaped_newlines(text)

        # Insert the processed text
        self.text_display.insert("1.0", processed)

        # Apply number highlighting on the processed text
        self._highlight_numbers(processed)
        # Apply syntax highlighting for booleans and null
        self._highlight_json_syntax(processed)

    def _expand_escaped_newlines(self, text):
        """Expand escaped \\n sequences inside JSON string values into real newlines.
        
        Adds indentation so wrapped lines align nicely beneath the opening
        quote of the string value.
        """
        result_lines = []
        for line in text.split('\n'):
            # Find the content part (after leading spaces)
            stripped = line.lstrip(' ')
            leading = line[:len(line) - len(stripped)]

            if '\\n' in stripped:
                # This line contains escaped newlines inside a string value.
                # We add extra indentation (4 spaces beyond current level)
                # for continuation lines so they align under the opening quote.
                indent = leading + '    '
                # Split on escaped \n and reassemble with real newlines + indent
                parts = stripped.split('\\n')
                new_line = parts[0]
                for part in parts[1:]:
                    new_line += '\n' + indent + part
                result_lines.append(new_line)
            else:
                result_lines.append(line)
        return '\n'.join(result_lines)

    def _highlight_numbers(self, text):
        """Highlight all numbers in the text widget."""
        # Remove existing number tags
        self.text_display.tag_remove("number", "1.0", tk.END)

        # Find and tag all numbers
        pattern = re.compile(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?')
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line_num = i + 1
            for m in pattern.finditer(line):
                start_idx = f"{line_num}.{m.start()}"
                end_idx = f"{line_num}.{m.end()}"
                self.text_display.tag_add("number", start_idx, end_idx)

    def _highlight_json_syntax(self, text):
        """Highlight JSON keys and string values."""
        # Highlight boolean and null values
        for token, tag in [("true", "boolean"), ("false", "boolean"), ("null", "null")]:
            start = "1.0"
            while True:
                pos = self.text_display.search(token, start, tk.END, regexp=False)
                if not pos:
                    break
                # Check if it's a standalone token (not part of another word)
                end = f"{pos}+{len(token)}c"
                # Simple check: make sure it's surrounded by non-word chars
                line, col = map(int, pos.split('.'))
                line_text = self.text_display.get(f"{line}.0", f"{line}.end")
                actual_col = int(col)
                before = line_text[actual_col-1] if actual_col > 0 else ' '
                after = line_text[actual_col+len(token)] if actual_col + len(token) < len(line_text) else ' '
                if not (before.isalnum() or before == '_') and not (after.isalnum() or after == '_'):
                    self.text_display.tag_add(tag, pos, end)
                start = end

    def get_current_gcn_data(self):
        """Get the currently loaded GCN data."""
        if self.current_index < 0 or self.current_index >= len(self.current_files):
            return None, None
        file_path = self.current_files[self.current_index]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data, file_path
        except:
            return None, None

    def get_current_circular_id(self):
        """Get the circular ID of the current file."""
        if self.current_index < 0:
            return ""
        return self.current_files[self.current_index].stem


# ============================================================================
# Top-Right Panel: GRB Info Management
# ============================================================================

class GRBInfoPanel(ttk.Frame):
    """Top-right panel for managing GRB basic information."""

    GRB_FIELDS = [
        ("grb_id", "GRB ID *", True),           # Required
        ("alias", "Alias", False),
        ("ra", "RA (deg)", False),
        ("dec", "Dec (deg)", False),
        ("T0", "T0 (UTC)", False),
        ("Trigger_Instrument", "Trigger Instrument", False),
        ("redshift", "Redshift", False),
    ]

    def __init__(self, parent, on_grb_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_grb_change = on_grb_change
        self.current_grb_id = None
        self.entries = {}

        self._build_ui()
        self._refresh_grb_list()

    def _build_ui(self):
        """Build the UI components."""
        self.configure(padding=10)

        # Title
        title_frame = ttk.Frame(self)
        title_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(title_frame, text="GRB Information Management",
                  font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                  foreground=COLOR_BUTTON_BG).pack(side=tk.LEFT)

        # GRB selector
        select_frame = ttk.Frame(self)
        select_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(select_frame, text="Select Existing GRB:",
                  font=(FONT_FAMILY, FONT_SIZE_NORMAL)).pack(side=tk.LEFT, padx=(0, 5))

        self.grb_select_var = tk.StringVar()
        self.grb_combo = ttk.Combobox(select_frame, textvariable=self.grb_select_var,
                                       width=20, state="readonly")
        self.grb_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.grb_combo.bind("<<ComboboxSelected>>", self._on_grb_select)

        ttk.Button(select_frame, text="Refresh List", command=self._refresh_grb_list,
                   width=10).pack(side=tk.LEFT, padx=5)

        # Separator
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Form fields
        form_frame = ttk.Frame(self)
        form_frame.pack(fill=tk.X, expand=True)

        for i, (field_id, label, required) in enumerate(self.GRB_FIELDS):
            row = ttk.Frame(form_frame)
            row.pack(fill=tk.X, pady=2)

            label_text = label
            ttk.Label(row, text=label_text + ":", width=22,
                      font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                      anchor=tk.E).pack(side=tk.LEFT, padx=(0, 5))

            entry = ttk.Entry(row, font=(FONT_FAMILY, FONT_SIZE_NORMAL))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            if field_id == "grb_id":
                entry.bind("<KeyRelease>", self._on_grb_id_change)

            self.entries[field_id] = entry

        # Separator
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.btn_create = tk.Button(btn_frame, text="Create New GRB", command=self._create_grb,
                                     bg=COLOR_BUTTON_BG, fg=COLOR_BUTTON_FG,
                                     activebackground=COLOR_BUTTON_ACTIVE,
                                     font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                     width=15, cursor="hand2", relief=tk.FLAT, padx=10, pady=5)
        self.btn_create.pack(side=tk.LEFT, padx=5)

        self.btn_save = tk.Button(btn_frame, text="Save Changes", command=self._save_grb,
                                   bg="#5cb85c", fg=COLOR_BUTTON_FG,
                                   activebackground="#449d44",
                                   font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                   width=15, cursor="hand2", relief=tk.FLAT, padx=10, pady=5)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        self.btn_clear = tk.Button(btn_frame, text="Clear Form", command=self._clear_form,
                                    bg="#f0ad4e", fg=COLOR_BUTTON_FG,
                                    activebackground="#ec971f",
                                    font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                    width=12, cursor="hand2", relief=tk.FLAT, padx=10, pady=5)
        self.btn_clear.pack(side=tk.LEFT, padx=5)

        # Status
        self.status_label = ttk.Label(self, text="", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                      foreground="#666666", anchor=tk.W)
        self.status_label.pack(fill=tk.X, pady=(8, 0))

    def _on_grb_id_change(self, event=None):
        """Handle GRB ID field changes."""
        grb_id = self.entries["grb_id"].get().strip()
        if grb_id != self.current_grb_id:
            self.current_grb_id = grb_id
            if self.on_grb_change:
                self.on_grb_change(grb_id)

    def _refresh_grb_list(self):
        """Refresh the list of existing GRB entries."""
        files = get_grb_info_files()
        grb_ids = [f.stem for f in files]
        self.grb_combo["values"] = ["-- Select GRB --"] + grb_ids
        if not grb_ids:
            self.grb_combo.set("No existing GRBs")
        else:
            self.grb_combo.set("-- Select GRB --")

    def _on_grb_select(self, event=None):
        """Handle selection of an existing GRB."""
        selected = self.grb_select_var.get()
        if not selected or selected == "-- Select GRB --" or selected == "No existing GRBs":
            return

        file_path = GRB_INFO_DIR / f"{selected}.json"
        if not file_path.exists():
            messagebox.showerror("Error", f"GRB info file not found: {file_path}")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            messagebox.showerror("Error", f"Failed to load GRB info:\n{e}")
            return

        # Populate form
        for field_id, _, _ in self.GRB_FIELDS:
            value = data.get(field_id, "")
            self.entries[field_id].delete(0, tk.END)
            self.entries[field_id].insert(0, str(value) if value is not None else "")

        self.current_grb_id = selected
        self.status_label.config(text=f"Loaded: {file_path.name}", foreground="#5cb85c")

        # Notify
        if self.on_grb_change:
            self.on_grb_change(selected)

    def _validate_grb_id(self, grb_id):
        """Validate GRB ID format."""
        if not grb_id:
            return False, "GRB ID is required"
        # Format: GRB + YYYYMMDD + optional letter, no spaces
        if not re.match(r'^GRB\d{6}[A-Z]?$', grb_id):
            return False, "Invalid format. Expected: GRBYYYMMDD or GRBYYYMMDDA (no spaces)"
        return True, ""

    def _create_grb(self):
        """Create a new GRB entry."""
        grb_id = self.entries["grb_id"].get().strip()
        valid, msg = self._validate_grb_id(grb_id)
        if not valid:
            messagebox.showwarning("Validation Error", msg)
            return

        file_path = GRB_INFO_DIR / f"{grb_id}.json"
        if file_path.exists():
            if not messagebox.askyesno("Confirm", f"GRB {grb_id} already exists. Overwrite?"):
                return

        data = self._collect_form_data()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.current_grb_id = grb_id
            self.status_label.config(text=f"Created: {file_path.name}", foreground="#5cb85c")
            self._refresh_grb_list()
            self.grb_select_var.set(grb_id)

            # Notify
            if self.on_grb_change:
                self.on_grb_change(grb_id)

            messagebox.showinfo("Success", f"GRB {grb_id} created successfully!")
        except IOError as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _save_grb(self):
        """Save changes to existing GRB entry."""
        grb_id = self.entries["grb_id"].get().strip()
        valid, msg = self._validate_grb_id(grb_id)
        if not valid:
            messagebox.showwarning("Validation Error", msg)
            return

        file_path = GRB_INFO_DIR / f"{grb_id}.json"
        data = self._collect_form_data()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.current_grb_id = grb_id
            self.status_label.config(text=f"Saved: {file_path.name}", foreground="#5cb85c")
            self._refresh_grb_list()
            self.grb_select_var.set(grb_id)

            # Notify
            if self.on_grb_change:
                self.on_grb_change(grb_id)

            messagebox.showinfo("Success", f"GRB {grb_id} saved successfully!")
        except IOError as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _collect_form_data(self):
        """Collect data from form fields."""
        data = {}
        for field_id, _, _ in self.GRB_FIELDS:
            value = self.entries[field_id].get().strip()
            # Convert numeric fields
            if field_id in ("ra", "dec", "redshift") and value:
                try:
                    value = float(value)
                except ValueError:
                    pass
            data[field_id] = value if value else None
        return data

    def _clear_form(self):
        """Clear all form fields."""
        for field_id, _, _ in self.GRB_FIELDS:
            self.entries[field_id].delete(0, tk.END)
        self.current_grb_id = None
        self.grb_select_var.set("-- Select GRB --")
        self.status_label.config(text="Form cleared", foreground="#666666")
        if self.on_grb_change:
            self.on_grb_change("")

    def get_current_grb_id(self):
        """Get the current GRB ID."""
        return self.entries["grb_id"].get().strip()


# ============================================================================
# Bottom-Right Panel: Observation Record Entry
# ============================================================================

class ObservationPanel(ttk.Frame):
    """Bottom-right panel for entering observation records."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.coltitles = load_coltitles()
        self.current_grb_id = ""
        self.current_csv_path = None
        self.entries = {}

        self._build_ui()

    def _build_ui(self):
        """Build the UI components."""
        self.configure(padding=10)

        # Title and CSV file indicator
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(header_frame, text="Observation Record Entry",
                  font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
                  foreground=COLOR_BUTTON_BG).pack(side=tk.LEFT)

        self.lbl_csv_file = ttk.Label(header_frame, text="CSV: (no GRB selected)",
                                       font=(FONT_FAMILY, FONT_SIZE_SMALL, "bold"),
                                       foreground=COLOR_CURRENT_FILE)
        self.lbl_csv_file.pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Scrollable form area
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=COLOR_RIGHT_BOTTOM_BG, highlightthickness=0)
        scroll_y = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        scroll_x = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.form_frame = ttk.Frame(self.canvas, padding=5)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.form_frame, anchor=tk.NW)

        self.form_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Build form fields based on coltitles
        self._build_form_fields()

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.btn_save_obs = tk.Button(btn_frame, text="Save Observation", command=self._save_observation,
                                       bg=COLOR_BUTTON_BG, fg=COLOR_BUTTON_FG,
                                       activebackground=COLOR_BUTTON_ACTIVE,
                                       font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                       width=18, cursor="hand2", relief=tk.FLAT, padx=10, pady=6)
        self.btn_save_obs.pack(side=tk.LEFT, padx=5)

        self.btn_clear_obs = tk.Button(btn_frame, text="Clear Fields", command=self._clear_fields,
                                        bg="#f0ad4e", fg=COLOR_BUTTON_FG,
                                        activebackground="#ec971f",
                                        font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                        width=12, cursor="hand2", relief=tk.FLAT, padx=10, pady=6)
        self.btn_clear_obs.pack(side=tk.LEFT, padx=5)

        self.btn_view_csv = tk.Button(btn_frame, text="View CSV", command=self._view_csv,
                                       bg="#5cb85c", fg=COLOR_BUTTON_FG,
                                       activebackground="#449d44",
                                       font=(FONT_FAMILY, FONT_SIZE_NORMAL, "bold"),
                                       width=10, cursor="hand2", relief=tk.FLAT, padx=10, pady=6)
        self.btn_view_csv.pack(side=tk.LEFT, padx=5)

        # Status
        self.status_label = ttk.Label(self, text="", font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                      foreground="#666666", anchor=tk.W)
        self.status_label.pack(fill=tk.X, pady=(8, 0))

    def _on_frame_configure(self, event=None):
        """Reset the scroll region to encompass the inner frame."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        """When canvas is resized, resize the inner window width."""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)

    def _build_form_fields(self):
        """Build form fields dynamically based on coltitles."""
        for col in self.coltitles:
            row = ttk.Frame(self.form_frame)
            row.pack(fill=tk.X, pady=2)

            label_text = col.replace("_", " ").title()
            readonly = (col == "grb_id")

            ttk.Label(row, text=label_text + ":", width=26,
                      font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                      anchor=tk.E).pack(side=tk.LEFT, padx=(0, 5))

            if readonly:
                entry = tk.Entry(row, font=(FONT_FAMILY, FONT_SIZE_NORMAL),
                                 state="readonly", readonlybackground=COLOR_READONLY_BG,
                                 fg="#666666")
            else:
                entry = ttk.Entry(row, font=(FONT_FAMILY, FONT_SIZE_NORMAL))

            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[col] = entry

    def _count_csv_rows(self):
        """Count data rows in current CSV file."""
        if not self.current_csv_path or not self.current_csv_path.exists():
            return 0
        try:
            with open(self.current_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                return sum(1 for _ in reader)
        except:
            return 0

    def set_gcn_id(self, gcn_id):
        """Set the GCN ID field (auto-filled from left panel, user can edit)."""
        gcn_entry = self.entries.get("gcn_id")
        if gcn_entry:
            gcn_entry.delete(0, tk.END)
            gcn_entry.insert(0, str(gcn_id))

    def set_grb_id(self, grb_id):
        """Set the GRB ID and update the CSV file path."""
        self.current_grb_id = grb_id.strip()

        # Update grb_id field
        grb_entry = self.entries.get("grb_id")
        if grb_entry:
            grb_entry.config(state="normal")
            grb_entry.delete(0, tk.END)
            grb_entry.insert(0, self.current_grb_id)
            grb_entry.config(state="readonly")

        # Update CSV file path and show row count
        if self.current_grb_id:
            self.current_csv_path = GRB_LC_DIR / f"{self.current_grb_id}.csv"
            row_count = self._count_csv_rows()
            row_info = f" ({row_count} records)" if row_count > 0 else " (new)"
            self.lbl_csv_file.config(text=f"CSV: {self.current_grb_id}.csv{row_info}")
            self.status_label.config(text=f"Ready to add observations for {self.current_grb_id}",
                                      foreground="#666666")
        else:
            self.current_csv_path = None
            self.lbl_csv_file.config(text="CSV: (no GRB selected)")
            self.status_label.config(text="Please select or create a GRB first", foreground="#999999")

    def _save_observation(self):
        """Save the current observation to the CSV file."""
        if not self.current_grb_id:
            messagebox.showwarning("Warning", "Please enter a GRB ID in the GRB Info panel first.")
            return

        if not self.current_csv_path:
            messagebox.showerror("Error", "CSV file path is not set.")
            return

        # Collect data
        row_data = []
        for col in self.coltitles:
            entry = self.entries.get(col)
            if entry:
                if col == "grb_id":
                    value = self.current_grb_id
                else:
                    value = entry.get().strip()
                row_data.append(value)
            else:
                row_data.append("")

        # Ensure directory exists
        self.current_csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists to determine if we need headers
        file_exists = self.current_csv_path.exists()

        try:
            with open(self.current_csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(self.coltitles)
                writer.writerow(row_data)

            row_count = self._count_csv_rows()
            self.status_label.config(
                text=f"Saved! {self.current_csv_path.name} now has {row_count} records",
                foreground="#5cb85c"
            )
            # Update CSV label with new count
            self.lbl_csv_file.config(text=f"CSV: {self.current_grb_id}.csv ({row_count} records)")

            # Clear all fields except grb_id
            self._clear_fields(keep_grb_id=True)

        except IOError as e:
            messagebox.showerror("Error", f"Failed to save observation:\n{e}")

    def _clear_fields(self, keep_grb_id=False):
        """Clear all entry fields."""
        for col, entry in self.entries.items():
            if col == "grb_id" and keep_grb_id:
                continue
            entry.delete(0, tk.END) if entry.cget('state') != 'readonly' else None
            if col == "grb_id" and keep_grb_id:
                pass  # Keep the value
            else:
                entry.delete(0, tk.END) if entry.cget('state') != 'readonly' else None

        if not keep_grb_id:
            self.status_label.config(text="Fields cleared", foreground="#666666")
        else:
            self.status_label.config(text="Fields cleared (GRB ID kept)", foreground="#666666")

    def _view_csv(self):
        """Open the current CSV file for viewing."""
        if not self.current_csv_path or not self.current_csv_path.exists():
            messagebox.showinfo("Info", "No CSV file exists yet for this GRB.")
            return

        # Create a popup window to show CSV content
        popup = tk.Toplevel(self)
        popup.title(f"CSV: {self.current_csv_path.name}")
        popup.geometry("900x500")
        popup.configure(bg=COLOR_BG)

        # Read CSV
        tree = ttk.Treeview(popup, show="headings")
        scroll_y = ttk.Scrollbar(popup, orient=tk.VERTICAL, command=tree.yview)
        scroll_x = ttk.Scrollbar(popup, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        try:
            with open(self.current_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)
                tree["columns"] = headers
                for h in headers:
                    tree.heading(h, text=h)
                    tree.column(h, width=100, anchor=tk.CENTER)

                for row in reader:
                    tree.insert("", tk.END, values=row)

            ttk.Label(popup, text=f"File: {self.current_csv_path} | Rows: {len(tree.get_children())}",
                      font=(FONT_FAMILY, FONT_SIZE_SMALL)).pack(pady=5)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read CSV:\n{e}")
            popup.destroy()


# ============================================================================
# Main Application
# ============================================================================

class GCNCatalogueApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("GCN GRB Catalogue Tool")
        self.geometry("1600x1000")
        self.configure(bg=COLOR_BG)

        # Ensure directories exist
        ensure_directories()

        # Check if GCN archive directory has files
        gcn_files = get_gcn_files()
        if not gcn_files:
            messagebox.showwarning("Warning",
                f"No JSON files found in:\n{GCN_ARCHIVE_DIR}\n\n"
                f"Please place GCN JSON files in this directory and restart.")

        self._build_ui()

    def _build_ui(self):
        """Build the main UI layout."""
        # Main container with padding
        main_container = ttk.Frame(self, padding=5)
        main_container.pack(fill=tk.BOTH, expand=True)

        # PanedWindow for left-right split
        paned_lr = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned_lr.pack(fill=tk.BOTH, expand=True)

        # ===== Left Panel (GCN Browser) =====
        left_frame = ttk.Frame(paned_lr, padding=5)
        paned_lr.add(left_frame, weight=1)

        self.gcn_browser = GCNBrowserPanel(left_frame, on_file_change=self._on_gcn_file_change)
        self.gcn_browser.pack(fill=tk.BOTH, expand=True)

        # ===== Right Panel =====
        right_frame = ttk.Frame(paned_lr, padding=5)
        paned_lr.add(right_frame, weight=1)

        # PanedWindow for top-bottom split within right panel
        paned_tb = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        paned_tb.pack(fill=tk.BOTH, expand=True)

        # Top-right: GRB Info
        top_right_frame = ttk.Frame(paned_tb, padding=5)
        paned_tb.add(top_right_frame, weight=1)

        self.grb_info = GRBInfoPanel(top_right_frame, on_grb_change=self._on_grb_change)
        self.grb_info.pack(fill=tk.BOTH, expand=True)

        # Bottom-right: Observation Entry
        bottom_right_frame = ttk.Frame(paned_tb, padding=5)
        paned_tb.add(bottom_right_frame, weight=1)

        self.obs_panel = ObservationPanel(bottom_right_frame)
        self.obs_panel.pack(fill=tk.BOTH, expand=True)

        # Status bar at the bottom
        self.status_bar = ttk.Label(main_container,
                                     text="Ready | Directories: " + str(CATA_OUTPUT_DIR),
                                     font=(FONT_FAMILY, FONT_SIZE_SMALL),
                                     foreground="#666666", anchor=tk.W, relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, pady=(5, 0))

        # Set initial sash positions
        self.after(100, lambda: self._set_sash_positions(paned_lr, paned_tb))

        # Bind keyboard shortcuts
        self._bind_shortcuts()

    def _set_sash_positions(self, paned_lr, paned_tb):
        """Set initial sash positions after window is rendered."""
        total_width = self.winfo_width()
        total_height = self.winfo_height()
        if total_width > 1:
            paned_lr.sashpos(0, int(total_width * 0.45))
        if total_height > 1:
            # Approximate: top-right gets about 40% of right panel height
            right_height = int(total_height * 0.55)
            paned_tb.sashpos(0, int(right_height * 0.55))

    def _on_gcn_file_change(self, data, file_path):
        """Handle GCN file change."""
        # Update status bar
        circular_id = data.get("circularId", file_path.stem)
        self.status_bar.config(text=f"GCN Circular #{circular_id} loaded")
        # Auto-fill gcn_id in the observation panel (user can still edit it)
        self.obs_panel.set_gcn_id(str(circular_id))

    def _on_grb_change(self, grb_id):
        """Handle GRB change - sync observation panel."""
        self.obs_panel.set_grb_id(grb_id)

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        self.bind("<Control-Left>", lambda e: self.gcn_browser._go_prev())
        self.bind("<Control-Right>", lambda e: self.gcn_browser._go_next())
        self.bind("<Control-n>", lambda e: self.gcn_browser._go_next())
        self.bind("<Control-p>", lambda e: self.gcn_browser._go_prev())
        self.bind("<Control-s>", lambda e: self.obs_panel._save_observation())


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point."""
    app = GCNCatalogueApp()
    app.mainloop()


if __name__ == "__main__":
    main()
