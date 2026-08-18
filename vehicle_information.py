"""
VEHICLE_INFORMATION (AZOD814) - v5.2
Cyberpunk Vehicle Intelligence Dashboard

Educational & Ethical Use Only.

Performance/responsive fixes:
- API/network work stays off the Tkinter main thread.
- Cached results are shown immediately; stale cache is refreshed in background.
- Responsive layout is breakpoint-based and debounced instead of reacting to every resize event.
- Vehicle images are resized only after resize settles, with a render cache.
- All returned fields are displayed, including nested fields.
- Custom themed dialogs replace native messagebox/file dialog info popups where possible.
- Sidebar actions open themed in-app panels instead of ugly native popups.
- Model image is explicitly marked as a reference image, not proof of the registered vehicle.
"""

import os
import json
import time
import hashlib
import threading
import socket
import mimetypes
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import tkinter as tk
import re
import html
import requests
from datetime import datetime
from urllib.parse import urlencode, quote
from tkinter import filedialog

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

try:
    from reportlab.lib import colors as pdf_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
WIKI_API = "https://commons.wikimedia.org/w/api.php"
VERSION = "5.2"
AUTHOR = "azod814"

BG = "#020504"
BG2 = "#050b08"
PANEL = "#06100b"
CARD = "#07130c"
BORDER = "#087b42"
BORDER2 = "#0d4e2e"
NEON = "#00ff66"
NEON2 = "#00d957"
WHITE = "#e7f4eb"
MUTED = "#789184"
CYAN = "#00e5ff"
YELLOW = "#ffd84d"
RED = "#ff3158"
BLACK = "#010302"
FONT = "DejaVu Sans"
MONO = "DejaVu Sans Mono"


def get_local_ip():
    """Best-effort LAN address used by QR report links."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


class ReportHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReportRequestHandler(SimpleHTTPRequestHandler):
    """Serve generated HTML/PDF reports from the local results directory."""
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        # Keep HTTP request noise out of the terminal.
        log("[REPORT SERVER] " + (format % args))


def ensure_dirs():
    for directory in ("results", "logs", "cache", "cache/vehicle_images"):
        os.makedirs(directory, exist_ok=True)


def log(message):
    ensure_dirs()
    try:
        with open("logs/activity.log", "a", encoding="utf-8") as file:
            file.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except Exception:
        pass


def cache_file(rc):
    return f"cache/{hashlib.md5(rc.encode('utf-8')).hexdigest()}.json"


def image_cache_file(model):
    return f"cache/vehicle_images/{hashlib.md5(model.encode('utf-8')).hexdigest()}.jpg"


def normalize_key(key):
    text = str(key).strip().lower()
    for char in ("_", "-", "/", "\\"):
        text = text.replace(char, " ")
    return " ".join(text.split())


def stringify(value):
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    value = str(value).strip()
    return value if value else "N/A"


def flatten_data(data):
    """
    Flatten the complete API object without dropping underscore-prefixed
    fields. This intentionally keeps every returned field visible.
    """
    output = {}

    def walk(value, prefix=""):
        if isinstance(value, dict):
            if not value and prefix:
                output[normalize_key(prefix)] = "N/A"
                return

            for key, child in value.items():
                new_key = f"{prefix} {key}" if prefix else str(key)
                walk(child, new_key)

        elif isinstance(value, list):
            if not value:
                output[normalize_key(prefix)] = "N/A"
                return

            if all(not isinstance(item, (dict, list)) for item in value):
                output[normalize_key(prefix)] = ", ".join(stringify(item) for item in value)
            else:
                for index, child in enumerate(value, 1):
                    walk(child, f"{prefix} {index}")

        else:
            output[normalize_key(prefix)] = stringify(value)

    walk(data)
    return output


def find_main_dict(data):
    if isinstance(data, dict):
        preferred = (
            "data",
            "result",
            "vehicle",
            "vehicle_data",
            "vehicle data",
            "vehicleData",
            "response",
            "details",
            "result_data",
            "resultData",
        )

        normalized = {normalize_key(key): value for key, value in data.items()}

        for key in preferred:
            target = normalize_key(key)
            if target in normalized and isinstance(normalized[target], dict):
                return normalized[target]

        return data

    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]

    return {}


def normalize_api_response(data):
    # Keep the whole raw response available while using the most useful
    # vehicle object for the primary dashboard.
    main = find_main_dict(data)
    return flatten_data(main)


class ThemedDialog:
    """Small cyberpunk modal Toplevel used instead of native message boxes."""

    def __init__(self, app, title, message, width=650, height=420,
                 buttons=None, accent=NEON, text_mode=False):
        self.app = app
        self.root = tk.Toplevel(app.root)
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(360, 240)
        self.root.transient(app.root)
        self.root.grab_set()

        try:
            self.root.resizable(True, True)
        except Exception:
            pass

        header = tk.Frame(
            self.root, bg=BG2, height=62,
            highlightbackground=BORDER, highlightthickness=1
        )
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(
            header, text="◆", fg=accent, bg=BG2,
            font=(MONO, 20, "bold")
        ).pack(side="left", padx=(14, 10))

        tk.Label(
            header, text=title.upper(), fg=accent, bg=BG2,
            font=(MONO, 12, "bold")
        ).pack(side="left")

        content = tk.Frame(
            self.root, bg=PANEL,
            highlightbackground=BORDER2, highlightthickness=1
        )
        content.pack(fill="both", expand=True, padx=10, pady=6)

        if text_mode:
            widget = tk.Text(
                content, bg=BLACK, fg=WHITE,
                insertbackground=NEON, selectbackground="#075f31",
                font=(MONO, 9), relief="flat", bd=0, wrap="word"
            )
            widget.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            widget.insert("1.0", message)
            widget.configure(state="disabled")

            scroll = tk.Scrollbar(content, command=widget.yview)
            scroll.pack(side="right", fill="y", pady=10)
            widget.configure(yscrollcommand=scroll.set)
        else:
            canvas = tk.Canvas(content, bg=BLACK, highlightthickness=0)
            canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)

            scrollbar = tk.Scrollbar(content, command=canvas.yview)
            scrollbar.pack(side="right", fill="y", pady=10)
            canvas.configure(yscrollcommand=scrollbar.set)

            body = tk.Frame(canvas, bg=BLACK)
            window = canvas.create_window((0, 0), window=body, anchor="nw")

            body.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            canvas.bind(
                "<Configure>",
                lambda e: canvas.itemconfigure(window, width=e.width)
            )

            tk.Label(
                body, text=message, fg=WHITE, bg=BLACK,
                font=(MONO, 9), justify="left",
                anchor="nw", wraplength=max(width - 80, 280)
            ).pack(fill="x", padx=12, pady=12)

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))

        if buttons is None:
            buttons = [("CLOSE", self.close, accent)]

        for label, command, color in buttons:
            tk.Button(
                footer, text=label, command=command,
                bg="#071a0d", fg=color,
                activebackground=color,
                activeforeground=BLACK,
                font=(MONO, 8, "bold"),
                relief="flat", bd=1,
                highlightbackground=BORDER2,
                padx=18, pady=8, cursor="hand2"
            ).pack(side="right", padx=4)

        self.root.bind("<Escape>", lambda e: self.close())

        self.root.update_idletasks()
        self._center()

    def _center(self):
        try:
            parent = self.app.root
            parent.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - self.root.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.root.winfo_height()) // 2
            self.root.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def close(self):
        try:
            self.root.grab_release()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


class VehicleInformationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VEHICLE INFORMATION // AZOD814 // RECON CONSOLE")
        self.root.configure(bg=BG)
        self.root.geometry("1500x920")
        self.root.minsize(520, 600)

        try:
            self.root.state("zoomed")
        except Exception:
            pass

        self.current_rc = ""
        self.current_data = {}
        self.current_raw_data = {}
        self.search_history = []
        self.scanning = False
        self.stop_event = threading.Event()
        self.lookup_generation = 0

        self.vehicle_image = None
        self.vehicle_image_path = None
        self._image_model_label = "MODEL"
        self._image_render_key = None
        self._resize_job = None
        self._layout_job = None
        self._last_layout = None
        self._details_layout = None
        self._last_window_size = (0, 0)

        self._theme_dialog = None
        self.report_server = None
        self.report_server_thread = None
        self.report_server_port = None

        ensure_dirs()
        self.build_ui()
        self.update_clock()

        self.root.after(250, self.on_window_resize)
        self.root.after(400, self.draw_vehicle_hud)
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)

    # ---------------------------- UI ----------------------------

    def build_ui(self):
        self.build_top_bar()

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.main_body = body

        self.build_sidebar(body)

        self.center_panel = tk.Frame(body, bg=BG)
        self.build_summary_cards(self.center_panel)
        self.build_dashboard(self.center_panel)

        self.build_right_panel(body)

        self.build_bottom_bar()

        self.root.bind("<Configure>", self.on_window_resize)

    def build_top_bar(self):
        top = tk.Frame(
            self.root, bg=BG2, height=92,
            highlightbackground=BORDER, highlightthickness=1
        )
        top.pack(fill="x", padx=18, pady=(12, 8))
        top.pack_propagate(False)
        self.top_bar = top

        brand = tk.Frame(top, bg=BG2)
        brand.grid(row=0, column=0, sticky="nsw", padx=20)
        self.top_brand = brand

        tk.Label(
            brand, text="▱", fg=NEON, bg=BG2,
            font=(MONO, 38, "bold")
        ).pack(side="left", padx=(0, 10))

        title = tk.Frame(brand, bg=BG2)
        title.pack(side="left")

        tk.Label(
            title, text="VEHICLE INFORMATION",
            fg=NEON, bg=BG2, font=(FONT, 21, "bold")
        ).pack(anchor="w")

        tk.Label(
            title, text="ADVANCED VEHICLE LOOKUP SYSTEM",
            fg=MUTED, bg=BG2, font=(MONO, 9)
        ).pack(anchor="w")

        self.top_search = tk.Frame(top, bg=BG2)
        self.top_search.grid(row=0, column=1, sticky="nsew", padx=25)

        tk.Label(
            self.top_search, text="ENTER VEHICLE NUMBER",
            fg=NEON, bg=BG2, font=(MONO, 8, "bold")
        ).pack(anchor="w")

        search_row = tk.Frame(self.top_search, bg=BG2)
        search_row.pack(fill="x", pady=5)

        self.rc_entry = tk.Entry(
            search_row, bg=BLACK, fg=WHITE,
            insertbackground=NEON, font=(MONO, 14, "bold"),
            relief="flat", bd=0
        )
        self.rc_entry.pack(
            side="left", fill="x", expand=True,
            ipady=8, padx=(0, 10)
        )
        self.rc_entry.bind("<Return>", lambda e: self.start_lookup())

        self.scan_btn = tk.Button(
            search_row, text="⌕  SEARCH",
            command=self.start_lookup,
            bg="#041c0e", fg=NEON,
            activebackground=NEON, activeforeground=BLACK,
            font=(MONO, 10, "bold"), relief="flat",
            bd=1, highlightbackground=NEON,
            padx=22, pady=8, cursor="hand2"
        )
        self.scan_btn.pack(side="right")

        self.stop_btn = tk.Button(
            search_row, text="■  STOP", command=self.stop_lookup,
            bg="#16070b", fg=RED, activebackground=RED, activeforeground=BLACK,
            font=(MONO, 9, "bold"), relief="flat", bd=1,
            highlightbackground=RED, padx=12, pady=8, cursor="hand2", state="disabled"
        )
        self.stop_btn.pack(side="right", padx=(0, 8))

        status = tk.Frame(top, bg=BG2, width=255)
        status.grid(row=0, column=2, sticky="nse", padx=18)
        status.grid_propagate(False)
        self.top_status = status

        tk.Label(
            status, text="SYSTEM STATUS", fg=MUTED, bg=BG2,
            font=(MONO, 8, "bold")
        ).pack(anchor="w", pady=(12, 0))

        self.status_label = tk.Label(
            status, text="● ONLINE", fg=NEON, bg=BG2,
            font=(MONO, 13, "bold")
        )
        self.status_label.pack(anchor="w")

        self.response_label = tk.Label(
            status, text="RESPONSE TIME   --", fg=MUTED, bg=BG2,
            font=(MONO, 8)
        )
        self.response_label.pack(anchor="w")

        self.cache_label = tk.Label(
            status, text="CACHE   READY", fg=MUTED, bg=BG2,
            font=(MONO, 8)
        )
        self.cache_label.pack(anchor="w")

        top.grid_columnconfigure(1, weight=1)

    def build_sidebar(self, parent):
        side = tk.Frame(
            parent, bg=BG2, width=235,
            highlightbackground=BORDER, highlightthickness=1
        )
        side.grid_propagate(False)
        self.sidebar_panel = side

        tk.Label(
            side, text="CONTROL MATRIX", fg=NEON, bg=BG2,
            font=(MONO, 10, "bold")
        ).pack(anchor="w", padx=18, pady=(18, 10))

        menu = [
            ("⌂", "DASHBOARD"),
            ("⌕", "VEHICLE LOOKUP"),
            ("◎", "RTO INFORMATION"),
            ("◇", "VIN DECODER"),
            ("▣", "NUMBER PLATE CHECK"),
            ("◷", "SEARCH HISTORY"),
            ("☆", "FAVORITES"),
            ("⚙", "SETTINGS"),
            ("⌘", "API CONSOLE"),
            ("ⓘ", "ABOUT"),
        ]

        for icon, name in menu:
            button = tk.Button(
                side, text=f"{icon}   {name}", anchor="w",
                command=lambda n=name: self.menu_action(n),
                bg=BG2, fg=WHITE,
                activebackground="#07351d",
                activeforeground=NEON,
                font=(MONO, 8, "bold"),
                relief="flat", bd=0,
                padx=18, pady=10, cursor="hand2"
            )
            button.pack(fill="x", padx=9, pady=1)

        info = tk.Frame(
            side, bg=PANEL,
            highlightbackground=BORDER2, highlightthickness=1
        )
        info.pack(side="bottom", fill="x", padx=10, pady=12)

        tk.Label(
            info, text="SYSTEM INFO", fg=NEON, bg=PANEL,
            font=(MONO, 9, "bold")
        ).pack(anchor="w", padx=12, pady=(10, 6))

        rows = [
            ("VERSION", VERSION),
            ("DATABASE", "CONNECTED"),
            ("API STATUS", "ACTIVE"),
            ("CACHE", "ENABLED"),
            ("IMAGE SEARCH", "ENABLED"),
            ("MODE", "EDUCATIONAL"),
        ]

        for key, value in rows:
            r = tk.Frame(info, bg=PANEL)
            r.pack(fill="x", padx=12, pady=2)

            tk.Label(
                r, text=key, fg=MUTED, bg=PANEL,
                font=(MONO, 6)
            ).pack(side="left")

            tk.Label(
                r, text=value, fg=NEON, bg=PANEL,
                font=(MONO, 6, "bold")
            ).pack(side="right")

    def build_summary_cards(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 9))

        self.summary_vehicle = self.summary_card(
            row, "▱", "NO TARGET", "INDIA", NEON
        )
        self.summary_status = self.summary_card(
            row, "✓", "READY", "Awaiting vehicle lookup", NEON
        )
        self.summary_response = self.summary_card(
            row, "◷", "-- ms", "Data Fetch", YELLOW
        )

    def summary_card(self, parent, icon, value, subtitle, color):
        card = tk.Frame(
            parent, bg=BG2,
            highlightbackground=BORDER2, highlightthickness=1,
            height=82
        )
        card.pack(side="left", fill="x", expand=True, padx=4)
        card.pack_propagate(False)

        tk.Label(
            card, text=icon, fg=NEON, bg=BG2,
            font=(MONO, 22, "bold")
        ).pack(side="left", padx=12)

        frame = tk.Frame(card, bg=BG2)
        frame.pack(side="left")

        label = tk.Label(
            frame, text=value, fg=color, bg=BG2,
            font=(MONO, 17, "bold")
        )
        label.pack(anchor="w", pady=(13, 0))

        tk.Label(
            frame, text=subtitle, fg=MUTED, bg=BG2,
            font=(MONO, 7)
        ).pack(anchor="w")

        return label

    def build_dashboard(self, parent):
        outer = tk.Frame(
            parent, bg=BG,
            highlightbackground=BORDER, highlightthickness=1
        )
        outer.pack(fill="both", expand=True)

        self.dashboard_canvas = tk.Canvas(
            outer, bg=BG, highlightthickness=0
        )
        self.dashboard_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            outer, orient="vertical",
            command=self.dashboard_canvas.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.dashboard_canvas.configure(yscrollcommand=scrollbar.set)

        self.dashboard_frame = tk.Frame(
            self.dashboard_canvas, bg=BG
        )

        self.dashboard_window = self.dashboard_canvas.create_window(
            (0, 0), window=self.dashboard_frame, anchor="nw"
        )

        self.dashboard_frame.bind(
            "<Configure>",
            lambda e: self.dashboard_canvas.configure(
                scrollregion=self.dashboard_canvas.bbox("all")
            )
        )

        self.dashboard_canvas.bind(
            "<Configure>",
            lambda e: self.dashboard_canvas.itemconfigure(
                self.dashboard_window, width=e.width
            )
        )

        self.dashboard_canvas.bind("<MouseWheel>", self.mouse_scroll)
        self.dashboard_canvas.bind("<Button-4>", lambda e: self.dashboard_canvas.yview_scroll(-3, "units"))
        self.dashboard_canvas.bind("<Button-5>", lambda e: self.dashboard_canvas.yview_scroll(3, "units"))

        # Normal mouse-wheel scrolling anywhere inside the dashboard.
        # Child labels/frames do not automatically pass wheel events to the
        # canvas, so use a global handler that only reacts while the pointer
        # is physically over this dashboard canvas.
        self.root.bind_all("<MouseWheel>", self.mouse_scroll_anywhere, add="+")
        self.root.bind_all("<Button-4>", self.mouse_scroll_anywhere, add="+")
        self.root.bind_all("<Button-5>", self.mouse_scroll_anywhere, add="+")

        self.build_intelligence_section()
        self.build_vehicle_details()
        self.build_additional_information()
        self.build_all_data_section()

    def mouse_scroll(self, event):
        try:
            if hasattr(event, "delta"):
                delta = -3 if event.delta < 0 else 3
            else:
                delta = -3 if getattr(event, "num", 5) == 4 else 3
            self.dashboard_canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return "break"

    def mouse_scroll_anywhere(self, event):
        """Scroll the main dashboard when the pointer is over any child widget."""
        try:
            canvas = self.dashboard_canvas
            x0 = canvas.winfo_rootx()
            y0 = canvas.winfo_rooty()
            x1 = x0 + canvas.winfo_width()
            y1 = y0 + canvas.winfo_height()
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()

            if x0 <= px <= x1 and y0 <= py <= y1:
                if hasattr(event, "delta"):
                    delta = -3 if event.delta < 0 else 3
                else:
                    delta = -3 if getattr(event, "num", 5) == 4 else 3
                canvas.yview_scroll(delta, "units")
                return "break"
        except Exception:
            pass
        return None

    def section(self, parent, title):
        frame = tk.Frame(
            parent, bg=PANEL,
            highlightbackground=BORDER, highlightthickness=1
        )

        tk.Label(
            frame, text=title, fg=NEON, bg=PANEL,
            font=(MONO, 10, "bold")
        ).pack(anchor="w", padx=14, pady=10)

        return frame

    def build_intelligence_section(self):
        frame = self.section(self.dashboard_frame, "◆  VEHICLE INTELLIGENCE")
        frame.pack(fill="x", padx=10, pady=(10, 7))

        top = tk.Frame(frame, bg=PANEL)
        top.pack(fill="x", padx=10, pady=(0, 8))

        # Smart summary
        summary = tk.Frame(top, bg=CARD, highlightbackground=BORDER2, highlightthickness=1)
        summary.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(summary, text="SMART VEHICLE SUMMARY", fg=NEON, bg=CARD, font=(MONO, 8, "bold")).pack(anchor="w", padx=12, pady=(10, 5))
        self.smart_summary_text = tk.Label(
            summary, text="Perform a vehicle lookup to generate an intelligent summary.",
            fg=WHITE, bg=CARD, font=(MONO, 8), justify="left", anchor="nw",
            wraplength=520
        )
        self.smart_summary_text.pack(fill="x", padx=12, pady=(0, 10))

        # Health score
        health = tk.Frame(top, bg=CARD, highlightbackground=BORDER2, highlightthickness=1, width=230)
        health.pack(side="left", fill="y", padx=(4, 0))
        health.pack_propagate(False)
        tk.Label(health, text="VEHICLE HEALTH SCORE", fg=NEON, bg=CARD, font=(MONO, 8, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self.health_score_label = tk.Label(health, text="-- / 100", fg=YELLOW, bg=CARD, font=(MONO, 20, "bold"))
        self.health_score_label.pack(anchor="w", padx=12)
        self.health_status_label = tk.Label(health, text="WAITING FOR DATA", fg=MUTED, bg=CARD, font=(MONO, 7, "bold"))
        self.health_status_label.pack(anchor="w", padx=12, pady=(0, 8))

        bottom = tk.Frame(frame, bg=PANEL)
        bottom.pack(fill="x", padx=10, pady=(0, 6))

        # Dedicated, highly visible age/validity control.
        self.age_check_btn = tk.Button(
            bottom,
            text="⌛  CHECK VEHICLE AGE + VALIDITY",
            command=self.show_age_validity_report,
            bg="#041c0e",
            fg=CYAN,
            activebackground=CYAN,
            activeforeground=BLACK,
            font=(MONO, 8, "bold"),
            relief="flat",
            bd=1,
            highlightbackground=BORDER2,
            padx=12,
            pady=8,
            cursor="hand2"
        )
        self.age_check_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.rto_intel_label = tk.Label(
            bottom,
            text="RTO INTELLIGENCE  --",
            fg=WHITE, bg=CARD, font=(MONO, 8, "bold"),
            anchor="w", padx=12, pady=9,
            highlightbackground=BORDER2, highlightthickness=1
        )
        self.rto_intel_label.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.age_label = tk.Label(
            frame,
            text="AGE CHECK: PRESS BUTTON ABOVE",
            fg=CYAN, bg=PANEL, font=(MONO, 7, "bold"),
            anchor="w"
        )
        self.age_label.pack(fill="x", padx=12, pady=(0, 3))

        self.health_details_label = tk.Label(
            frame, text="Insurance: --   |   PUC: --   |   Fitness: --   |   Tax: --",
            fg=MUTED, bg=PANEL, font=(MONO, 7), anchor="w"
        )
        self.health_details_label.pack(fill="x", padx=12, pady=(0, 9))

    def build_vehicle_details(self):
        frame = self.section(
            self.dashboard_frame, "▱  VEHICLE DETAILS"
        )
        frame.pack(fill="x", padx=10, pady=(10, 7))

        body = tk.Frame(frame, bg=PANEL)
        body.pack(fill="x", padx=10, pady=(0, 10))

        self.left_details = tk.Frame(body, bg=PANEL)
        self.right_details = tk.Frame(body, bg=PANEL)

        self.left_details.pack(
            side="left", fill="both", expand=True, padx=(0, 4)
        )
        self.right_details.pack(
            side="left", fill="both", expand=True, padx=(4, 0)
        )

        self.render_details([])

    def render_details(self, items):
        for widget in self.left_details.winfo_children():
            widget.destroy()
        for widget in self.right_details.winfo_children():
            widget.destroy()

        if not items:
            items = [
                ("▧", "ADDRESS", "N/A"),
                ("▥", "CITY", "N/A"),
                ("▦", "FITNESS UPTO", "N/A"),
                ("◉", "FUEL TYPE", "N/A"),
                ("♢", "INSURANCE COMPANY", "N/A"),
                ("▣", "INSURANCE NO", "N/A"),
                ("▦", "INSURANCE UPTO", "N/A"),
                ("▱", "MAKER MODEL", "N/A"),
                ("◇", "MODEL NAME", "N/A"),
                ("♙", "OWNER NAME", "N/A"),
                ("▣", "OWNER SERIAL NO", "N/A"),
                ("❧", "FUEL NORMS", "N/A"),
                ("▦", "INSURANCE EXPIRY", "N/A"),
                ("⚙", "PUC NO", "N/A"),
                ("▦", "PUC UPTO", "N/A"),
                ("⌕", "PHONE", "N/A"),
                ("▥", "REGISTERED RTO", "N/A"),
                ("▦", "REGISTRATION DATE", "N/A"),
                ("₹", "TAX UPTO", "N/A"),
            ]

        half = (len(items) + 1) // 2

        for item in items[:half]:
            self.detail_row(self.left_details, *item)

        for item in items[half:]:
            self.detail_row(self.right_details, *item)

    def detail_row(self, parent, icon, label, value):
        row = tk.Frame(
            parent, bg=CARD,
            highlightbackground="#0b4026",
            highlightthickness=1
        )
        row.pack(fill="x", pady=1)

        tk.Label(
            row, text=icon, fg=NEON, bg=CARD,
            font=(MONO, 10, "bold"), width=3
        ).pack(side="left", padx=(6, 0))

        tk.Label(
            row, text=label, fg=NEON, bg=CARD,
            font=(MONO, 7, "bold"), anchor="w",
            width=20
        ).pack(side="left", padx=(0, 4), pady=8)

        tk.Frame(
            row, bg=BORDER2, width=1
        ).pack(side="left", fill="y", pady=3)

        value_label = tk.Label(
            row, text=stringify(value),
            fg=WHITE, bg=CARD,
            font=(MONO, 8), anchor="w",
            justify="left", wraplength=420
        )
        value_label.pack(
            side="left", fill="x", expand=True,
            padx=10, pady=8
        )

    def build_additional_information(self):
        frame = self.section(
            self.dashboard_frame, "▱  ADDITIONAL INFORMATION"
        )
        frame.pack(fill="x", padx=10, pady=(7, 7))

        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x", padx=10, pady=(0, 10))

        self.rto_box = self.info_box(row, "▧  RTO DETAILS")
        self.spec_box = self.info_box(row, "♧  VEHICLE SPECIFICATIONS")
        self.env_box = self.info_box(row, "♙  ENVIRONMENT")

        self.fill_info(
            self.rto_box,
            [
                ("RTO Code", "N/A"),
                ("RTO Name", "N/A"),
                ("State", "N/A"),
                ("Region", "N/A"),
            ],
        )

        self.fill_info(
            self.spec_box,
            [
                ("Engine Type", "N/A"),
                ("Displacement", "N/A"),
                ("Max Power", "N/A"),
                ("Max Torque", "N/A"),
            ],
        )

        self.fill_info(
            self.env_box,
            [
                ("Emission Norm", "N/A"),
                ("Fuel Type", "N/A"),
                ("PUC Status", "N/A"),
                ("Vehicle Age", "N/A"),
            ],
        )

    def info_box(self, parent, title):
        box = tk.Frame(
            parent, bg=CARD,
            highlightbackground=BORDER2, highlightthickness=1
        )
        box.pack(side="left", fill="both", expand=True, padx=4)

        tk.Label(
            box, text=title, fg=NEON, bg=CARD,
            font=(MONO, 8, "bold")
        ).pack(anchor="w", padx=12, pady=10)

        body = tk.Frame(box, bg=CARD)
        body.pack(fill="x", padx=12, pady=(0, 10))
        return body

    def fill_info(self, parent, rows):
        for widget in parent.winfo_children():
            widget.destroy()

        for key, value in rows:
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)

            tk.Label(
                row, text=key, fg=MUTED, bg=CARD,
                font=(MONO, 7), width=17, anchor="w"
            ).pack(side="left")

            tk.Label(
                row, text=stringify(value),
                fg=WHITE, bg=CARD,
                font=(MONO, 7), anchor="w",
                justify="left", wraplength=240
            ).pack(side="left", fill="x", expand=True)

    def build_all_data_section(self):
        frame = self.section(
            self.dashboard_frame,
            "▣  ALL RETURNED DATA // NOTHING HIDDEN"
        )
        frame.pack(fill="x", padx=10, pady=(7, 12))

        self.all_data_text = tk.Text(
            frame, bg=BLACK, fg=WHITE,
            insertbackground=NEON,
            selectbackground="#075f31",
            font=(MONO, 8),
            relief="flat", bd=0,
            wrap="word",
            height=12
        )
        self.all_data_text.pack(
            fill="both", expand=True,
            padx=10, pady=(0, 10)
        )

        self.all_data_text.insert(
            "1.0",
            "No lookup performed yet.\n"
            "Every field returned by the API will be shown here."
        )
        self.all_data_text.configure(state="disabled")

    def set_all_data(self, data):
        self.all_data_text.configure(state="normal")
        self.all_data_text.delete("1.0", "end")

        if not data:
            self.all_data_text.insert(
                "end",
                "NO DATA RETURNED BY API."
            )
        else:
            for key, value in data.items():
                self.all_data_text.insert(
                    "end",
                    f"{key.upper():34} : {self.mask_sensitive_value(key, value)}\n"
                )

        self.all_data_text.configure(state="disabled")

    # ---------------------------- right panel ----------------------------

    def build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG, width=330)
        right.grid_propagate(False)
        self.right_panel = right

        self.build_image_panel(right)
        self.build_actions(right)
        self.build_telemetry(right)

    def build_image_panel(self, parent):
        frame = self.section(parent, "▧  VEHICLE IMAGE")
        frame.pack(fill="both", expand=True, pady=(0, 8))

        self.image_canvas = tk.Canvas(
            frame, bg=BLACK, height=285,
            highlightthickness=0
        )
        self.image_canvas.pack(
            fill="both", expand=True,
            padx=10, pady=(0, 6)
        )

        self.image_canvas.bind(
            "<Configure>",
            lambda e: self.schedule_image_redraw()
        )

        self.image_status = tk.Label(
            frame,
            text="MODEL REFERENCE: WAITING",
            fg=MUTED, bg=PANEL,
            font=(MONO, 6)
        )
        self.image_status.pack(pady=(0, 2))

        self.image_note = tk.Label(
            frame,
            text="Reference image only • not proof of exact registered vehicle",
            fg=MUTED, bg=PANEL,
            font=(MONO, 5),
            wraplength=300
        )
        self.image_note.pack(pady=(0, 6))

    # ---------------------------- image search ----------------------------

    def search_vehicle_image(self, maker, model):
        if not PIL_AVAILABLE:
            log("[IMAGE] Pillow is not installed.")
            return None

        maker = str(maker or "").strip()
        model = str(model or "").strip()

        if maker == "N/A":
            maker = ""
        if model == "N/A":
            model = ""

        if not maker and not model:
            return None

        maker_upper = maker.upper()
        model_upper = model.upper()

        brand_map = [
            ("HERO", "Hero"),
            ("HONDA", "Honda"),
            ("YAMAHA", "Yamaha"),
            ("BAJAJ", "Bajaj"),
            ("TVS", "TVS"),
            ("ROYAL ENFIELD", "Royal Enfield"),
            ("SUZUKI", "Suzuki"),
            ("KTM", "KTM"),
            ("OLA", "Ola"),
            ("ATHER", "Ather"),
            ("JAWA", "Jawa"),
            ("TRIUMPH", "Triumph"),
            ("BMW", "BMW"),
            ("KAWASAKI", "Kawasaki"),
            ("HARLEY", "Harley-Davidson"),
        ]

        brand = maker.title()
        for token, public_name in brand_map:
            if token in maker_upper:
                brand = public_name
                break

        clean_model = model_upper
        clean_model = re.sub(
            r"\b(DUAL|CH|ABS|CBS|LCD|LED|BS[- ]?[IV0-9]+|"
            r"PHASE[- ]?[0-9]+|PETROL|DIESEL|CNG|E20|DISC|"
            r"DRUM|SELF|START|FI|DELUXE)\b",
            " ",
            clean_model,
            flags=re.IGNORECASE,
        )
        clean_model = re.sub(r"\s+", " ", clean_model).strip()

        known_models = [
            ("XTREME 125R", "Xtreme 125R"),
            ("XTREME", "Xtreme"),
            ("SPLENDOR PLUS", "Splendor Plus"),
            ("SPLENDOR", "Splendor"),
            ("PASSION", "Passion"),
            ("HF DELUXE", "HF Deluxe"),
            ("PULSAR", "Pulsar"),
            ("APACHE", "Apache"),
            ("ACTIVA", "Activa"),
            ("SHINE", "Shine"),
            ("SP 125", "SP 125"),
            ("ACCESS", "Access"),
            ("FZ", "FZ"),
            ("MT 15", "MT-15"),
            ("R15", "R15"),
            ("CLASSIC 350", "Classic 350"),
            ("HUNTER 350", "Hunter 350"),
            ("METEOR 350", "Meteor 350"),
        ]

        model_name = clean_model.title() or model.title()
        for key, value in known_models:
            if key in model_upper:
                model_name = value
                break

        queries = []
        candidates = [
            f"{brand} {model_name} motorcycle",
            f"{brand} {model_name} bike",
            f"{brand} {model_name}",
            f"{model_name} motorcycle",
            f"{model_name} bike",
        ]

        for query in candidates:
            query = " ".join(query.split()).strip()
            if query and query.lower() not in [x.lower() for x in queries]:
                queries.append(query)

        cache_key = f"{brand}_{model_name}"
        cached = image_cache_file(cache_key)

        if os.path.exists(cached):
            try:
                with Image.open(cached) as test:
                    test.verify()
                log(f"[IMAGE] Cache HIT: {cache_key}")
                return cached
            except Exception:
                try:
                    os.remove(cached)
                except Exception:
                    pass

        log(f"[IMAGE] Target model: {brand} {model_name}")

        # Fastest path first.
        if DDGS_AVAILABLE:
            try:
                with DDGS() as ddgs:
                    for query in queries[:3]:
                        self._ui_telemetry(f"[IMAGE] Search: {query}\n")
                        results = ddgs.images(query, max_results=8)

                        for result in results:
                            image_url = result.get("image") or result.get("thumbnail")
                            if not image_url:
                                continue

                            downloaded = self.download_vehicle_image(
                                image_url, cached
                            )
                            if downloaded:
                                log(f"[IMAGE] DDGS SUCCESS: {query}")
                                return downloaded
            except Exception as error:
                log(f"[IMAGE] DDGS error: {error}")

        # Wikimedia fallback.
        for query in queries[:3]:
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrnamespace": 6,
                    "gsrlimit": 20,
                    "prop": "imageinfo",
                    "iiprop": "url|mime|size",
                    "iiurlwidth": 1000,
                    "format": "json",
                    "origin": "*",
                }

                response = requests.get(
                    WIKI_API,
                    params=params,
                    timeout=8,
                    headers={
                        "User-Agent": "VEHICLE_INFORMATION_AZOD814/4.0"
                    },
                )
                payload = response.json()
                pages = payload.get("query", {}).get("pages", {})

                candidates = []

                for page in pages.values():
                    title = str(page.get("title", ""))
                    info = page.get("imageinfo", [])
                    if not info:
                        continue

                    ii = info[0]
                    image_url = ii.get("thumburl") or ii.get("url")
                    if not image_url:
                        continue

                    title_lower = title.lower()
                    score = 0

                    if model_name.lower() in title_lower:
                        score += 100
                    if brand.lower() in title_lower:
                        score += 50
                    if "motorcycle" in title_lower:
                        score += 20
                    if "bike" in title_lower:
                        score += 10

                    candidates.append((score, image_url))

                candidates.sort(key=lambda x: x[0], reverse=True)

                for score, image_url in candidates[:10]:
                    downloaded = self.download_vehicle_image(
                        image_url, cached
                    )
                    if downloaded:
                        log(f"[IMAGE] Wikimedia SUCCESS score={score}")
                        return downloaded

            except Exception as error:
                log(f"[IMAGE] Wikimedia error: {error}")

        # Bing fallback.
        for query in queries[:2]:
            try:
                url = (
                    "https://www.bing.com/images/search?q="
                    + requests.utils.quote(query)
                )

                response = requests.get(
                    url,
                    timeout=8,
                    headers={
                        "User-Agent":
                            "Mozilla/5.0 "
                            "(Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 "
                            "(KHTML, like Gecko) "
                            "Chrome/151.0 Safari/537.36"
                    },
                )

                if response.status_code != 200:
                    continue

                matches = re.findall(
                    r'"murl"\s*:\s*"([^"]+)"',
                    response.text
                )

                for image_url in matches[:15]:
                    image_url = (
                        html.unescape(image_url)
                        .replace("\\/", "/")
                        .replace("\\u0026", "&")
                    )

                    if not image_url.startswith("http"):
                        continue

                    downloaded = self.download_vehicle_image(
                        image_url, cached
                    )
                    if downloaded:
                        log(f"[IMAGE] Bing SUCCESS: {query}")
                        return downloaded

            except Exception as error:
                log(f"[IMAGE] Bing error: {error}")

        log(f"[IMAGE] No usable image for {brand} {model_name}")
        return None

    def download_vehicle_image(self, image_url, destination):
        if not image_url or not PIL_AVAILABLE:
            return None

        temp_file = destination + ".tmp"

        try:
            response = requests.get(
                image_url,
                timeout=7,
                allow_redirects=True,
                headers={
                    "User-Agent":
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/151.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,"
                              "image/svg+xml,image/*,*/*;q=0.8",
                },
            )

            if response.status_code != 200:
                return None

            if len(response.content) < 3000:
                return None

            if len(response.content) > 20 * 1024 * 1024:
                return None

            with open(temp_file, "wb") as file:
                file.write(response.content)

            with Image.open(temp_file) as image:
                image.load()
                width, height = image.size

                if width < 180 or height < 120:
                    return None

                image.convert("RGB").save(
                    destination,
                    "JPEG",
                    quality=90,
                    optimize=True
                )

            return destination

        except Exception as error:
            log(f"[IMAGE] Download failed: {error}")
            return None

        finally:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

    def _ui_telemetry(self, message):
        try:
            self.root.after(
                0, lambda msg=message: self.telemetry_log(msg)
            )
        except Exception:
            pass

    # ---------------------------- image rendering ----------------------------

    def schedule_image_redraw(self):
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass

        self._resize_job = self.root.after(
            140, self.redraw_current_image
        )

    def load_vehicle_image(self, image_path, model):
        if not image_path or not PIL_AVAILABLE:
            return

        try:
            width = max(self.image_canvas.winfo_width(), 220)
            height = max(self.image_canvas.winfo_height(), 180)

            # Avoid reprocessing the same image at almost identical size.
            key = (
                image_path,
                int(width / 20),
                int(height / 20)
            )

            if self._image_render_key == key and self.vehicle_image is not None:
                return

            self._image_render_key = key

            with Image.open(image_path) as source:
                image = source.convert("RGB")

                max_w = max(int(width * 0.90), 180)
                max_h = max(int(height * 0.82), 150)

                image.thumbnail(
                    (max_w, max_h),
                    Image.Resampling.LANCZOS
                )

                self.vehicle_image = ImageTk.PhotoImage(image)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                width // 2,
                height // 2,
                image=self.vehicle_image,
                anchor="center"
            )
            self.draw_image_brackets(width, height)

            self.image_status.config(
                text="MODEL REFERENCE: " + str(model)[:42].upper(),
                fg=NEON
            )

        except Exception as error:
            log(f"Image rendering error: {error}")
            self.vehicle_image = None
            self._image_render_key = None
            self.draw_vehicle_hud()
            self.image_status.config(
                text="MODEL IMAGE LOAD ERROR",
                fg=MUTED
            )

    def redraw_current_image(self):
        self._resize_job = None

        if (
            self.vehicle_image_path
            and os.path.exists(self.vehicle_image_path)
            and PIL_AVAILABLE
        ):
            self.load_vehicle_image(
                self.vehicle_image_path,
                self._image_model_label
            )
        else:
            self.draw_vehicle_hud()

    def draw_image_brackets(self, width, height):
        c = self.image_canvas
        m = 15
        length = 30

        lines = [
            (m, m, m + length, m),
            (m, m, m, m + length),
            (width - m, m, width - m - length, m),
            (width - m, m, width - m, m + length),
            (m, height - m, m + length, height - m),
            (m, height - m, m, height - m - length),
            (width - m, height - m, width - m - length, height - m),
            (width - m, height - m, width - m, height - m - length),
        ]

        for line in lines:
            c.create_line(*line, fill=NEON, width=2)

    def draw_vehicle_hud(self):
        if not hasattr(self, "image_canvas"):
            return

        if self.vehicle_image is not None:
            return

        canvas = self.image_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 280)
        height = max(canvas.winfo_height(), 240)

        # Lightweight grid; do not redraw this on every Configure event.
        for x in range(0, width, 32):
            canvas.create_line(
                x, 0, x, height, fill="#062819"
            )
        for y in range(0, height, 32):
            canvas.create_line(
                0, y, width, y, fill="#062819"
            )

        m = 16
        l = 32

        for line in [
            (m, m, m + l, m),
            (m, m, m, m + l),
            (width - m, m, width - m - l, m),
            (width - m, m, width - m, m + l),
            (m, height - m, m + l, height - m),
            (m, height - m, m, height - m - l),
            (width - m, height - m, width - m - l, height - m),
            (width - m, height - m, width - m, height - m - l),
        ]:
            canvas.create_line(*line, fill=NEON, width=2)

        cx = width / 2
        cy = height / 2

        canvas.create_oval(
            cx - 82, cy + 3, cx - 28, cy + 57,
            outline=BORDER, width=2
        )
        canvas.create_oval(
            cx + 28, cy + 3, cx + 82, cy + 57,
            outline=BORDER, width=2
        )

        canvas.create_line(
            cx - 58, cy + 15,
            cx - 18, cy - 32,
            cx + 20, cy - 24,
            cx + 58, cy + 15,
            fill=NEON, width=3
        )

        canvas.create_line(
            cx - 18, cy - 32,
            cx - 42, cy - 43,
            fill=NEON2, width=4
        )

        canvas.create_line(
            cx + 20, cy - 24,
            cx + 39, cy - 52,
            fill=NEON, width=3
        )

        canvas.create_line(
            cx + 39, cy - 52,
            cx + 65, cy - 52,
            fill=NEON, width=3
        )

        canvas.create_line(
            cx - 45, cy + 15,
            cx + 35, cy + 18,
            fill=NEON2, width=3
        )

        canvas.create_text(
            cx, height - 22,
            text="MODEL IMAGE NOT FOUND",
            fill=MUTED,
            font=(MONO, 7, "bold")
        )

    # ---------------------------- actions / telemetry ----------------------------

    def build_actions(self, parent):
        frame = self.section(parent, "▧  QUICK ACTIONS")
        frame.pack(fill="x", pady=(0, 8))

        self.action_button(
            frame, "▣  EXPORT REPORT", self.export_report
        )
        self.action_button(
            frame, "▣  EXPORT JSON", self.export_json
        )
        self.action_button(
            frame, "↗  COPY RESULT", self.copy_result
        )
        self.action_button(
            frame, "☆  ADD TO FAVORITES", self.favorite
        )
        self.action_button(
            frame, "▣  QR CODE REPORT", self.generate_qr_report
        )

    def action_button(self, parent, text, command):
        tk.Button(
            parent, text=text, command=command,
            bg="#07130c", fg=WHITE,
            activebackground="#06391e",
            activeforeground=NEON,
            font=(MONO, 8, "bold"),
            relief="flat", bd=1,
            highlightbackground=BORDER2,
            pady=8, cursor="hand2"
        ).pack(fill="x", padx=10, pady=3)

    def build_telemetry(self, parent):
        frame = self.section(parent, "◉  SYSTEM TELEMETRY")
        frame.pack(fill="both", expand=True)

        self.telemetry = tk.Text(
            frame, bg=BLACK, fg=NEON,
            font=(MONO, 7), relief="flat",
            bd=0, wrap="word"
        )
        self.telemetry.pack(
            fill="both", expand=True,
            padx=10, pady=(0, 10)
        )

        for line in (
            "[SYSTEM] Vehicle Intelligence Dashboard\n",
            "[SYSTEM] API channel initialized\n",
            "[SYSTEM] Cache enabled\n",
            "[SYSTEM] Responsive engine v4 enabled\n",
            "[SYSTEM] All-field data view enabled\n",
            "[SYSTEM] Model image search enabled\n",
        ):
            self.telemetry.insert("end", line)

        self.telemetry.configure(state="disabled")

    def telemetry_log(self, message):
        try:
            self.telemetry.configure(state="normal")
            self.telemetry.insert("end", message)
            self.telemetry.see("end")

            # Prevent the telemetry widget from growing forever.
            line_count = int(self.telemetry.index("end-1c").split(".")[0])
            if line_count > 600:
                self.telemetry.delete("1.0", "100.0")

            self.telemetry.configure(state="disabled")
        except Exception:
            pass

    # ---------------------------- lookup ----------------------------

    def start_lookup(self):
        if self.scanning:
            return

        rc = self.rc_entry.get().strip().upper()

        if not rc:
            self.show_dialog(
                "INPUT REQUIRED",
                "Enter a vehicle registration number.",
                accent=YELLOW
            )
            return

        self.scanning = True
        self.stop_event.clear()
        self.lookup_generation += 1
        generation = self.lookup_generation

        self.vehicle_image = None
        self.vehicle_image_path = None
        self._image_render_key = None
        self._image_model_label = "MODEL"

        self.draw_vehicle_hud()

        self.image_status.config(
            text="MODEL REFERENCE: WAITING",
            fg=MUTED
        )

        self.scan_btn.config(
            text="◌  SEARCHING...",
            state="disabled",
            bg="#073b20"
        )
        self.stop_btn.config(state="normal")

        self.status_label.config(
            text="● SCANNING",
            fg=YELLOW
        )

        self.cache_label.config(
            text="CACHE   CHECKING",
            fg=YELLOW
        )

        self.summary_vehicle.config(text=rc)
        self.summary_status.config(
            text="SCANNING...",
            fg=YELLOW
        )
        self.summary_response.config(text="-- ms")

        self.telemetry_log(
            f"\n[SCAN] Target: {rc}\n"
        )

        threading.Thread(
            target=self.lookup_worker,
            args=(rc, generation),
            daemon=True
        ).start()

    def lookup_worker(self, rc, generation):
        start = time.time()
        cache_hit = False
        raw = None

        try:
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return

            path = cache_file(rc)

            # CACHE-FIRST: show old result instantly if available,
            # then refresh API in the same worker.
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        cached_raw = json.load(file)

                    cache_hit = True

                    if self.stop_event.is_set() or generation != self.lookup_generation:
                        self.root.after(0, self.lookup_stopped)
                        return

                    try:
                        cached_normalized = normalize_api_response(cached_raw)
                    except Exception:
                        cached_normalized = {}

                    self.root.after(
                        0,
                        lambda:
                        self.show_cached_result(
                            rc,
                            cached_raw,
                            cached_normalized
                        )
                    )

                except Exception as error:
                    log(f"Cache read failed for {rc}: {error}")

            self.root.after(
                0,
                lambda: self.telemetry_log(
                    "[API] Live request started...\n"
                )
            )

            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return

            url = API_BASE + "?" + urlencode({"rc": rc})

            response = requests.get(
                url,
                timeout=(4, 12),
                headers={
                    "User-Agent":
                        "VehicleInformationAZOD814/5.0"
                }
            )

            response.raise_for_status()
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return
            raw = response.json()

            try:
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(
                        self.sanitize_data_for_storage(raw),
                        file,
                        indent=2,
                        ensure_ascii=False
                    )
            except OSError as error:
                log(f"Cache write failed: {error}")

            response_time = round(
                (time.time() - start) * 1000,
                2
            )

            normalized = normalize_api_response(raw)

            self.root.after(
                0,
                lambda:
                self.lookup_finished(
                    rc,
                    raw,
                    normalized,
                    cache_hit,
                    response_time
                )
            )

        except requests.exceptions.Timeout as error:
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return
            log(f"API timeout for {rc}: {error}")

            # If cached result was already shown, keep it and simply
            # mark live refresh as timed out.
            if cache_hit:
                self.root.after(
                    0,
                    lambda: self.live_refresh_notice(
                        "LIVE API REFRESH TIMED OUT",
                        "Cached data is still available above. "
                        "The window is responsive and you can continue using it."
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda error_text=str(error): self.lookup_error(
                        f"API request timed out.\n\n{error_text}"
                    )
                )

        except requests.exceptions.RequestException as error:
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return
            log(f"API request error for {rc}: {error}")

            if cache_hit:
                self.root.after(
                    0,
                    lambda error_text=str(error): self.live_refresh_notice(
                        "LIVE API REFRESH FAILED",
                        "Cached data remains visible. "
                        f"\n\n{error_text}"
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda error_text=str(error): self.lookup_error(
                        f"Network/API error.\n\n{error_text}"
                    )
                )

        except ValueError as error:
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return
            log(f"API JSON error for {rc}: {error}")

            if cache_hit:
                self.root.after(
                    0,
                    lambda: self.live_refresh_notice(
                        "INVALID LIVE RESPONSE",
                        "Cached data remains visible."
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda error_text=str(error): self.lookup_error(
                        f"API returned invalid JSON.\n\n{error_text}"
                    )
                )

        except Exception as error:
            if self.stop_event.is_set() or generation != self.lookup_generation:
                self.root.after(0, self.lookup_stopped)
                return
            log(f"Unexpected lookup error for {rc}: {error}")

            if cache_hit:
                self.root.after(
                    0,
                    lambda error_text=str(error): self.live_refresh_notice(
                        "LIVE REFRESH ERROR",
                        error_text
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda error_type=type(error).__name__, error_text=str(error): self.lookup_error(
                        f"Unexpected lookup error.\n\n"
                        f"{error_type}: {error_text}"
                    )
                )

    def show_cached_result(self, rc, raw, normalized):
        self.current_rc = rc
        self.current_raw_data = raw
        self.current_data = normalized

        self.summary_vehicle.config(text=rc)
        self.summary_status.config(
            text="CACHE DATA",
            fg=CYAN
        )
        self.cache_label.config(
            text="CACHE   DISPLAYED",
            fg=CYAN
        )

        self.populate_vehicle_data(normalized)
        self.set_all_data(normalized)

        self.telemetry_log(
            "[CACHE] Previous result displayed immediately.\n"
        )

    def live_refresh_notice(self, title, message):
        self.scanning = False
        self.stop_btn.config(state="disabled")
        self.scan_btn.config(
            text="⌕  SEARCH",
            state="normal",
            bg="#041c0e"
        )
        self.status_label.config(
            text="● ONLINE",
            fg=NEON
        )
        self.cache_label.config(
            text="CACHE   AVAILABLE",
            fg=CYAN
        )
        self.telemetry_log(
            f"[API] {title}\n"
        )
        self.show_dialog(
            title,
            message,
            accent=YELLOW
        )

    def lookup_finished(
        self,
        rc,
        raw,
        normalized,
        cached,
        response_time
    ):
        if self.stop_event.is_set():
            self.lookup_stopped()
            return

        self.scanning = False
        self.stop_btn.config(state="disabled")

        self.scan_btn.config(
            text="⌕  SEARCH",
            state="normal",
            bg="#041c0e"
        )

        self.status_label.config(
            text="● ONLINE",
            fg=NEON
        )

        self.cache_label.config(
            text="CACHE   UPDATED",
            fg=NEON
        )

        self.current_rc = rc
        self.current_raw_data = raw
        self.current_data = normalized

        self.summary_vehicle.config(text=rc)
        self.summary_response.config(
            text=f"{response_time} ms"
        )
        self.response_label.config(
            text=f"RESPONSE TIME   {response_time} ms"
        )

        self.summary_status.config(
            text="SUCCESS" if normalized else "NO DATA",
            fg=NEON if normalized else YELLOW
        )

        self.populate_vehicle_data(normalized)
        self.set_all_data(normalized)

        self.telemetry_log(
            f"[SCAN] Fields: {len(normalized)}\n"
        )
        self.telemetry_log(
            f"[SCAN] Cache used: {'YES' if cached else 'NO'}\n"
        )
        self.telemetry_log(
            f"[SCAN] Live response: {response_time} ms\n"
        )

        self.add_history(rc)
        self.save_result()

        maker = self.find_value(
            normalized,
            "model name",
            "manufacturer",
            "maker",
            "make"
        )

        model = self.find_value(
            normalized,
            "maker model",
            "model",
            "vehicle model"
        )

        self.vehicle_image = None
        self.vehicle_image_path = None
        self._image_render_key = None
        self._image_model_label = (
            model if model != "N/A" else maker
        )

        if model != "N/A" or maker != "N/A":
            self.image_status.config(
                text="SEARCHING MODEL IMAGE...",
                fg=YELLOW
            )
            self.telemetry_log(
                "[IMAGE] Searching model reference image...\n"
            )

            threading.Thread(
                target=self.image_worker,
                args=(maker, model),
                daemon=True
            ).start()
        else:
            self.draw_vehicle_hud()
            self.image_status.config(
                text="MODEL REFERENCE: UNAVAILABLE",
                fg=MUTED
            )

    def image_worker(self, maker, model):
        try:
            path = self.search_vehicle_image(maker, model)

            self.root.after(
                0,
                lambda:
                self.image_result(path, maker, model)
            )

        except Exception as error:
            log(f"Image worker error: {error}")

            self.root.after(
                0,
                lambda:
                self.image_result(None, maker, model)
            )

    def image_result(self, path, maker, model):
        if path and os.path.exists(path):
            self.vehicle_image_path = path
            self._image_render_key = None

            self.load_vehicle_image(
                path,
                model
            )

            self.telemetry_log(
                "[IMAGE] Model reference loaded.\n"
            )
        else:
            self.vehicle_image = None
            self._image_render_key = None

            self.draw_vehicle_hud()

            self.image_status.config(
                text="MODEL IMAGE NOT FOUND",
                fg=MUTED
            )

            self.telemetry_log(
                "[IMAGE] No suitable model image found.\n"
            )

    # ---------------------------- data ----------------------------

    def find_value(self, data, *names):
        if not data:
            return "N/A"

        targets = [normalize_key(name) for name in names]

        # Exact first.
        for target in targets:
            if target in data:
                value = stringify(data[target])
                if value != "N/A":
                    return value

        # Then partial.
        for target in targets:
            for key, value in data.items():
                if target in key or key in target:
                    value = stringify(value)
                    if value != "N/A":
                        return value

        return "N/A"

    def parse_date_value(self, value):
        """
        Parse the date formats commonly returned by vehicle APIs.

        Important: this API returns dates such as:
            23-Aug-2010
            18-Aug-2011
            22-Aug-2025

        The previous parser did not include %d-%b-%Y, so those dates
        were displayed correctly but could not be used for age/validity
        calculations.
        """
        text = stringify(value)
        if text == "N/A":
            return None

        text = text.strip().replace(",", " ")
        text = re.sub(r"\s+", " ", text)

        # Most-specific formats first.
        formats = (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d.%m.%Y",

            # API format used by this vehicle service.
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d/%b/%Y",
            "%d/%B/%Y",
            "%d %b %Y",
            "%d %B %Y",

            "%b-%d-%Y",
            "%B-%d-%Y",
            "%b %d %Y",
            "%B %d %Y",
        )

        for fmt in formats:
            try:
                return datetime.strptime(text[:26], fmt)
            except ValueError:
                pass

        # Numeric date fallback.
        match = re.search(
            r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
            text
        )
        if match:
            try:
                return datetime(
                    int(match.group(3)),
                    int(match.group(2)),
                    int(match.group(1))
                )
            except ValueError:
                pass

        return None

    def vehicle_age_breakdown(self, registration_date):
        """Return exact completed vehicle age as years, months and days."""
        if not registration_date:
            return None

        today = datetime.now().date()
        registered = registration_date.date()

        if registered > today:
            return None

        years = today.year - registered.year
        anniversary = registered.replace(year=registered.year + years)

        if anniversary > today:
            years -= 1
            anniversary = registered.replace(year=registered.year + years)

        months = 0
        cursor = anniversary

        while True:
            next_month = cursor.month + 1
            next_year = cursor.year
            if next_month == 13:
                next_month = 1
                next_year += 1

            # Safe end-of-month handling.
            import calendar
            next_day = min(
                cursor.day,
                calendar.monthrange(next_year, next_month)[1]
            )
            candidate = cursor.replace(
                year=next_year,
                month=next_month,
                day=next_day
            )

            if candidate <= today:
                cursor = candidate
                months += 1
            else:
                break

        days = (today - cursor).days
        return years, months, days

    def vehicle_age_text(self, data):
        registration = self.find_value(data, "registration date", "reg date")
        dt = self.parse_date_value(registration)
        breakdown = self.vehicle_age_breakdown(dt)

        if not breakdown:
            return "N/A"

        years, months, days = breakdown
        parts = []

        if years:
            parts.append(f"{years} YEARS")
        if months:
            parts.append(f"{months} MONTHS")
        if days or not parts:
            parts.append(f"{days} DAYS")

        return " ".join(parts)

    def vehicle_age_short_text(self, data):
        """Compact age for the main dashboard."""
        registration = self.find_value(data, "registration date", "reg date")
        dt = self.parse_date_value(registration)
        breakdown = self.vehicle_age_breakdown(dt)

        if not breakdown:
            return "N/A"

        years, months, days = breakdown
        return f"{years}Y {months}M {days}D"

    def validity_state(self, data, *names):
        raw = self.find_value(data, *names)
        if raw == "N/A":
            return "UNKNOWN"
        dt = self.parse_date_value(raw)
        if dt:
            return "ACTIVE" if dt.date() >= datetime.now().date() else "EXPIRED"
        text = raw.upper()
        if any(word in text for word in ("EXPIRED", "INVALID", "NO", "INACTIVE")):
            return "EXPIRED"
        if any(word in text for word in ("VALID", "ACTIVE", "YES")):
            return "ACTIVE"
        return "UNKNOWN"

    def calculate_health_score(self, data):
        checks = [
            self.validity_state(data, "insurance upto", "insurance expiry"),
            self.validity_state(data, "puc upto", "puc expiry"),
            self.validity_state(data, "fitness upto", "fitness expiry"),
            self.validity_state(data, "tax upto", "tax expiry"),
        ]
        known = [x for x in checks if x != "UNKNOWN"]
        if not known:
            return None, checks
        score = 100
        for state in checks:
            if state == "EXPIRED":
                score -= 25
            elif state == "UNKNOWN":
                score -= 5
        return max(0, min(100, score)), checks

    def update_intelligence(self, data):
        if not data:
            return
        maker = self.find_value(data, "manufacturer", "maker", "make", "model name")
        model = self.find_value(data, "maker model", "model", "vehicle model")
        fuel = self.find_value(data, "fuel type")
        city = self.find_value(data, "city name", "city")
        rto = self.find_value(data, "rto code")
        rto_name = self.find_value(data, "rto name", "registered rto")
        rto_state = self.find_value(data, "state")
        rto_region = self.find_value(data, "region", "city")
        age = self.vehicle_age_text(data)
        score, checks = self.calculate_health_score(data)

        vehicle_name = " ".join(x for x in (maker, model) if x != "N/A").strip() or "Vehicle"
        parts = [vehicle_name]
        if fuel != "N/A":
            parts.append(f"Fuel: {fuel}")
        if city != "N/A":
            parts.append(f"Registered: {city}")
        if age != "N/A":
            parts.append(f"Age: {age.title()}")
        self.smart_summary_text.config(text="\n".join(parts))

        registration = self.find_value(data, "registration date", "reg date")
        age_short = self.vehicle_age_short_text(data)

        if registration != "N/A" and age_short != "N/A":
            self.age_label.config(
                text=f"REGISTERED SINCE  {registration}    |    VEHICLE AGE  {age_short}",
                fg=CYAN
            )
        elif registration != "N/A":
            self.age_label.config(
                text=f"REGISTERED SINCE  {registration}    |    VEHICLE AGE  CALCULATION UNAVAILABLE",
                fg=YELLOW
            )
        else:
            self.age_label.config(
                text="REGISTERED SINCE  N/A    |    VEHICLE AGE  N/A",
                fg=YELLOW
            )
        rto_text = " / ".join(x for x in (rto, rto_name, rto_state, rto_region) if x != "N/A") or "N/A"
        self.rto_intel_label.config(text=f"RTO INTELLIGENCE  {rto_text}")

        if score is None:
            self.health_score_label.config(text="-- / 100", fg=YELLOW)
            self.health_status_label.config(text="INSUFFICIENT VALIDITY DATA", fg=MUTED)
        else:
            color = NEON if score >= 80 else (YELLOW if score >= 50 else RED)
            status = "HEALTHY" if score >= 80 else ("REVIEW REQUIRED" if score >= 50 else "ATTENTION REQUIRED")
            self.health_score_label.config(text=f"{score} / 100", fg=color)
            self.health_status_label.config(text=status, fg=color)

        labels = ("Insurance", "PUC", "Fitness", "Tax")
        self.health_details_label.config(
            text="   |   ".join(f"{name}: {state}" for name, state in zip(labels, checks)),
            fg=WHITE
        )

    def age_validity_details(self, data):
        """Build the one-click age/validity report from the current API data."""
        registration_raw = self.find_value(data, "registration date", "reg date")
        registration_dt = self.parse_date_value(registration_raw)
        age = self.vehicle_age_text(data)

        if registration_dt:
            breakdown = self.vehicle_age_breakdown(registration_dt)

            if breakdown:
                age_years, age_months, age_days = breakdown

                if age_years >= 15:
                    age_review = (
                        f"OVER 15 YEARS — {age_years} YEARS {age_months} MONTHS {age_days} DAYS OLD. "
                        "CHECK APPLICABLE RENEWAL / FITNESS RULES."
                    )
                else:
                    age_review = (
                        f"VEHICLE AGE {age_years} YEARS {age_months} MONTHS {age_days} DAYS — "
                        "NO 15-YEAR INFORMATIONAL FLAG"
                    )
            else:
                age_review = "AGE UNKNOWN — INVALID REGISTRATION DATE"
        else:
            age_review = "AGE UNKNOWN — REGISTRATION DATE NOT AVAILABLE"

        fields = [
            ("INSURANCE", self.validity_state(data, "insurance upto", "insurance expiry")),
            ("PUC", self.validity_state(data, "puc upto", "puc expiry")),
            ("FITNESS", self.validity_state(data, "fitness upto", "fitness expiry")),
            ("TAX", self.validity_state(data, "tax upto", "tax expiry")),
        ]

        score, checks = self.calculate_health_score(data)
        expired = [name for (name, state) in fields if state == "EXPIRED"]
        unknown = [name for (name, state) in fields if state == "UNKNOWN"]

        if expired:
            overall = "NOT CURRENTLY VALID — " + ", ".join(expired) + " EXPIRED"
            overall_color = RED
        elif unknown:
            overall = "PARTIAL CHECK — SOME VALIDITY DATA UNAVAILABLE"
            overall_color = YELLOW
        else:
            overall = "CURRENTLY VALID — ALL CHECKED VALIDITY DATES ACTIVE"
            overall_color = NEON

        return {
            "registration": registration_raw,
            "purchase": self.find_value(
                data,
                "purchase date",
                "date of purchase",
                "purchase",
                "delivery date",
                "delivery"
            ),
            "age": age,
            "age_review": age_review,
            "fields": fields,
            "score": score,
            "checks": checks,
            "overall": overall,
            "overall_color": overall_color,
        }

    def show_age_validity_report(self):
        if not self.current_data:
            self.show_dialog(
                "NO VEHICLE DATA",
                "Perform a vehicle lookup first.",
                accent=YELLOW
            )
            return

        report = self.age_validity_details(self.current_data)

        dialog = tk.Toplevel(self.root)
        dialog.title("VEHICLE AGE + VALIDITY")
        dialog.configure(bg=BG)
        dialog.geometry("820x680")
        dialog.minsize(620, 500)
        dialog.transient(self.root)
        dialog.grab_set()

        header = tk.Frame(
            dialog, bg=BG2, height=62,
            highlightbackground=BORDER, highlightthickness=1
        )
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(
            header, text="⌛  VEHICLE AGE + VALIDITY",
            fg=CYAN, bg=BG2, font=(MONO, 12, "bold")
        ).pack(side="left", padx=14)

        tk.Label(
            header, text=self.current_rc,
            fg=NEON, bg=BG2, font=(MONO, 10, "bold")
        ).pack(side="right", padx=14)

        body = tk.Frame(
            dialog, bg=PANEL,
            highlightbackground=BORDER2, highlightthickness=1
        )
        body.pack(fill="both", expand=True, padx=10, pady=6)

        canvas = tk.Canvas(body, bg=BLACK, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar = tk.Scrollbar(body, command=canvas.yview)
        scrollbar.pack(side="right", fill="y", pady=8)
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg=BLACK)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window, width=e.width)
        )
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(
                -3 if e.delta > 0 else 3, "units"
            )
        )
        canvas.bind(
            "<Button-4>",
            lambda e: canvas.yview_scroll(-3, "units")
        )
        canvas.bind(
            "<Button-5>",
            lambda e: canvas.yview_scroll(3, "units")
        )

        def row(label, value, color=WHITE):
            r = tk.Frame(
                inner, bg=CARD,
                highlightbackground=BORDER2, highlightthickness=1
            )
            r.pack(fill="x", padx=12, pady=3)
            tk.Label(
                r, text=label, fg=NEON, bg=CARD,
                font=(MONO, 8, "bold"), width=23, anchor="w"
            ).pack(side="left", padx=10, pady=9)
            tk.Label(
                r, text=stringify(value), fg=color, bg=CARD,
                font=(MONO, 9, "bold"), anchor="w",
                justify="left", wraplength=500
            ).pack(side="left", fill="x", expand=True, padx=8, pady=9)

        row("VEHICLE NUMBER", self.current_rc, NEON)
        row("REGISTERED SINCE", report["registration"])
        row("PURCHASE / DELIVERY", report["purchase"])
        row("VEHICLE AGE", report["age"], CYAN)
        row("AGE REVIEW", report["age_review"], YELLOW if "OVER 15" in report["age_review"] else NEON)

        tk.Label(
            inner, text="CURRENT VALIDITY",
            fg=NEON, bg=BLACK, font=(MONO, 9, "bold")
        ).pack(anchor="w", padx=14, pady=(14, 6))

        for label, state in report["fields"]:
            color = NEON if state == "ACTIVE" else (RED if state == "EXPIRED" else YELLOW)
            row(label, state, color)

        row(
            "HEALTH SCORE",
            f"{report['score']} / 100" if report["score"] is not None else "N/A",
            NEON if report["score"] is not None and report["score"] >= 80 else YELLOW
        )
        row("OVERALL STATUS", report["overall"], report["overall_color"])

        tk.Label(
            inner,
            text=(
                "AGE IS AN INFORMATIONAL CALCULATION. "
                "LEGAL RENEWAL / FITNESS LIMITS DEPEND ON VEHICLE CATEGORY "
                "AND APPLICABLE RTO RULES."
            ),
            fg=MUTED, bg=BLACK, font=(MONO, 7),
            justify="left", wraplength=700
        ).pack(fill="x", padx=14, pady=(12, 14))

        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))
        tk.Button(
            footer, text="CLOSE", command=dialog.destroy,
            bg="#071a0d", fg=NEON,
            activebackground=NEON, activeforeground=BLACK,
            font=(MONO, 8, "bold"), relief="flat", bd=1,
            padx=18, pady=7, cursor="hand2"
        ).pack(side="right")

        self.center_toplevel(dialog)

    def plate_intelligence(self, rc):
        rc = re.sub(r"[\s-]+", "", rc.upper())
        pattern = r"^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$"
        match = re.match(pattern, rc)
        if not match:
            return None
        state, rto, series, number = match.groups()
        return {"state": state, "rto": rto, "series": series or "--", "number": number, "normalized": rc}

    def mask_sensitive_value(self, key, value):
        key = normalize_key(key)
        value = stringify(value)
        sensitive = ("owner name", "phone", "mobile", "address", "owner serial")
        if any(token in key for token in sensitive) and value != "N/A":
            if "phone" in key or "mobile" in key:
                digits = re.sub(r"\D", "", value)
                return ("*" * max(0, len(digits) - 4)) + digits[-4:] if digits else "[PROTECTED]"
            if "address" in key:
                return "[PROTECTED PERSONAL ADDRESS]"
            if "owner serial" in key:
                return "[PROTECTED]"
            parts = value.split()
            return (parts[0][0] + "***") if parts else "[PROTECTED]"
        return value

    def populate_vehicle_data(self, data):
        items = [
            ("▧", "ADDRESS", self.mask_sensitive_value("address", self.find_value(data, "address"))),
            ("▥", "CITY", self.find_value(data, "city name", "city")),
            ("▦", "FITNESS UPTO", self.find_value(data, "fitness upto")),
            ("◉", "FUEL TYPE", self.find_value(data, "fuel type")),
            ("♢", "INSURANCE COMPANY", self.find_value(data, "insurance company")),
            ("▣", "INSURANCE NO", self.find_value(data, "insurance no", "insurance number")),
            ("▦", "INSURANCE UPTO", self.find_value(data, "insurance upto")),
            ("▱", "MAKER MODEL", self.find_value(data, "maker model")),
            ("◇", "MODEL NAME", self.find_value(data, "model name")),
            ("♙", "OWNER NAME", self.mask_sensitive_value("owner name", self.find_value(data, "owner name"))),
            ("▣", "OWNER SERIAL NO", self.mask_sensitive_value("owner serial no", self.find_value(data, "owner serial no", "owner serial number"))),
            ("❧", "FUEL NORMS", self.find_value(data, "fuel norms")),
            ("▦", "INSURANCE EXPIRY", self.find_value(data, "insurance expiry")),
            ("⚙", "PUC NO", self.find_value(data, "puc no", "puc number")),
            ("▦", "PUC UPTO", self.find_value(data, "puc upto")),
            ("⌕", "PHONE", self.mask_sensitive_value("phone", self.find_value(data, "phone", "mobile"))),
            ("▥", "REGISTERED RTO", self.find_value(data, "registered rto", "rto name")),
            ("▦", "REGISTRATION DATE", self.find_value(data, "registration date")),
            ("₹", "TAX UPTO", self.find_value(data, "tax upto")),
        ]

        # Do not hide any other returned field.
        known = {normalize_key(label) for _, label, _ in items}

        for key, value in data.items():
            if normalize_key(key) not in known:
                items.append(("◇", key.upper(), self.mask_sensitive_value(key, value)))

        self.render_details(items)

        self.fill_info(
            self.rto_box,
            [
                ("RTO Code", self.find_value(data, "rto code")),
                ("RTO Name", self.find_value(data, "rto name", "registered rto")),
                ("State", self.find_value(data, "state")),
                ("Region", self.find_value(data, "region", "city")),
            ],
        )

        self.fill_info(
            self.spec_box,
            [
                ("Engine Type", self.find_value(data, "engine type")),
                ("Displacement", self.find_value(data, "displacement")),
                ("Max Power", self.find_value(data, "max power")),
                ("Max Torque", self.find_value(data, "max torque")),
            ],
        )

        self.fill_info(
            self.env_box,
            [
                ("Emission Norm", self.find_value(data, "emission norm", "fuel norms")),
                ("Fuel Type", self.find_value(data, "fuel type")),
                ("PUC Status", self.find_value(data, "puc status")),
                ("Vehicle Age", self.find_value(data, "vehicle age")),
            ],
        )

        self.update_intelligence(data)
        self.root.after_idle(self.reflow_detail_rows)

    # ---------------------------- responsive ----------------------------

    def on_window_resize(self, event=None):
        # Configure fires for almost every pixel while dragging.
        # Debounce it so we do not rebuild/repaint continuously.
        if self._layout_job is not None:
            try:
                self.root.after_cancel(self._layout_job)
            except Exception:
                pass

        self._layout_job = self.root.after(
            120, self.apply_responsive_layout
        )

    def apply_responsive_layout(self):
        self._layout_job = None

        try:
            width = self.root.winfo_width()
            if width <= 1:
                return

            if width >= 1280:
                layout = "large"
            elif width >= 930:
                layout = "medium"
            else:
                layout = "small"

            if layout == self._last_layout:
                # Do not touch widget geometry during normal resizing.
                self.schedule_image_redraw()
                return

            self._last_layout = layout

            if layout == "large":
                self.sidebar_panel.grid(
                    row=0, column=0, sticky="ns", padx=(0, 7)
                )
                self.center_panel.grid(
                    row=0, column=1, sticky="nsew", padx=7
                )
                self.right_panel.grid(
                    row=0, column=2, sticky="nsew", padx=(7, 0)
                )

                self.sidebar_panel.configure(width=235)
                self.right_panel.configure(width=330)

                self.main_body.grid_columnconfigure(0, weight=0)
                self.main_body.grid_columnconfigure(1, weight=1)
                self.main_body.grid_columnconfigure(2, weight=0)
                self.main_body.grid_rowconfigure(0, weight=1)
                self.main_body.grid_rowconfigure(1, weight=0)

                self.top_brand.grid(
                    row=0, column=0, sticky="nsw", padx=20
                )
                self.top_status.grid(
                    row=0, column=2, sticky="nse", padx=18
                )
                self.top_search.grid(
                    row=0, column=1, sticky="nsew", padx=25
                )

            elif layout == "medium":
                self.sidebar_panel.grid(
                    row=0, column=0, sticky="ns", padx=(0, 4)
                )
                self.center_panel.grid(
                    row=0, column=1, sticky="nsew", padx=4
                )
                self.right_panel.grid(
                    row=0, column=2, sticky="nsew", padx=(4, 0)
                )

                self.sidebar_panel.configure(width=180)
                self.right_panel.configure(width=260)

                self.main_body.grid_columnconfigure(0, weight=0)
                self.main_body.grid_columnconfigure(1, weight=1)
                self.main_body.grid_columnconfigure(2, weight=0)
                self.main_body.grid_rowconfigure(0, weight=1)
                self.main_body.grid_rowconfigure(1, weight=0)

                self.top_brand.grid(
                    row=0, column=0, sticky="nsw", padx=12
                )
                self.top_status.grid(
                    row=0, column=2, sticky="nse", padx=10
                )
                self.top_search.grid(
                    row=0, column=1, sticky="nsew", padx=10
                )

            else:
                self.sidebar_panel.grid_remove()

                self.center_panel.grid(
                    row=0, column=0, sticky="nsew",
                    padx=0, pady=(0, 6)
                )
                self.right_panel.grid(
                    row=1, column=0, sticky="nsew",
                    padx=0, pady=(6, 0)
                )

                self.main_body.grid_columnconfigure(0, weight=1)
                self.main_body.grid_columnconfigure(1, weight=0)
                self.main_body.grid_columnconfigure(2, weight=0)
                self.main_body.grid_rowconfigure(0, weight=1)
                self.main_body.grid_rowconfigure(1, weight=1)

                self.right_panel.configure(
                    width=max(self.root.winfo_width() - 40, 400)
                )

                self.top_brand.grid_remove()
                self.top_status.grid_remove()
                self.top_search.grid(
                    row=0, column=0, sticky="nsew", padx=10
                )

                self.top_bar.grid_columnconfigure(0, weight=1)
                self.top_bar.grid_columnconfigure(1, weight=0)
                self.top_bar.grid_columnconfigure(2, weight=0)

            detail_mode = (
                "stacked" if layout == "small"
                else "columns"
            )

            if detail_mode != self._details_layout:
                self._details_layout = detail_mode

                self.left_details.pack_forget()
                self.right_details.pack_forget()

                if detail_mode == "stacked":
                    self.left_details.pack(
                        fill="x", expand=False,
                        padx=0, pady=(0, 3)
                    )
                    self.right_details.pack(
                        fill="x", expand=False,
                        padx=0, pady=(3, 0)
                    )
                else:
                    self.left_details.pack(
                        side="left",
                        fill="both", expand=True,
                        padx=(0, 4)
                    )
                    self.right_details.pack(
                        side="left",
                        fill="both", expand=True,
                        padx=(4, 0)
                    )

            self.main_body.update_idletasks()
            self.dashboard_frame.update_idletasks()

            self.reflow_detail_rows()
            self.schedule_image_redraw()

        except Exception as error:
            log(f"Responsive layout error: {error}")

    def reflow_detail_rows(self):
        try:
            width = max(self.center_panel.winfo_width(), 360)

            if self._details_layout == "stacked":
                wrap = max(240, width - 250)
            else:
                wrap = max(
                    180,
                    min(520, int(width / 2) - 125)
                )

            for parent in (
                self.left_details,
                self.right_details,
            ):
                for row in parent.winfo_children():
                    labels = [
                        widget
                        for widget in row.winfo_children()
                        if isinstance(widget, tk.Label)
                    ]
                    if labels:
                        labels[-1].configure(
                            wraplength=wrap
                        )

        except Exception as error:
            log(f"Detail reflow error: {error}")

    # ---------------------------- history/favorites/sidebar ----------------------------

    def add_history(self, rc):
        entry = {
            "rc": rc,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.search_history = [
            item for item in self.search_history
            if item.get("rc") != rc
        ]

        self.search_history.insert(0, entry)
        self.search_history = self.search_history[:50]
        self.save_history()

    def history_file(self):
        return "results/search_history.json"

    def save_history(self):
        try:
            with open(
                self.history_file(),
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    self.search_history,
                    file,
                    indent=2,
                    ensure_ascii=False
                )
        except Exception as error:
            log(f"History save error: {error}")

    def load_history(self):
        try:
            path = self.history_file()
            if os.path.exists(path):
                with open(
                    path,
                    "r",
                    encoding="utf-8"
                ) as file:
                    data = json.load(file)

                if isinstance(data, list):
                    self.search_history = data[:50]
        except Exception as error:
            log(f"History load error: {error}")

    def favorites_file(self):
        return "results/favorites.json"

    def load_favorites(self):
        try:
            if os.path.exists(self.favorites_file()):
                with open(
                    self.favorites_file(),
                    "r",
                    encoding="utf-8"
                ) as file:
                    data = json.load(file)

                if isinstance(data, list):
                    return data
        except Exception as error:
            log(f"Favorites read error: {error}")

        return []

    def favorite(self):
        if not self.current_rc:
            self.show_dialog(
                "NO VEHICLE",
                "Perform a vehicle lookup first.",
                accent=YELLOW
            )
            return

        favorites = self.load_favorites()

        if self.current_rc not in favorites:
            favorites.append(self.current_rc)

        try:
            with open(
                self.favorites_file(),
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    favorites,
                    file,
                    indent=2,
                    ensure_ascii=False
                )

            self.telemetry_log(
                f"[FAVORITE] Added {self.current_rc}\n"
            )

            self.show_dialog(
                "FAVORITES",
                f"{self.current_rc}\n\nAdded to favorites.",
                accent=NEON
            )

        except Exception as error:
            self.show_dialog(
                "FAVORITES ERROR",
                str(error),
                accent=RED
            )

    def show_history(self):
        self.load_history()

        dialog = tk.Toplevel(self.root)
        dialog.title("SEARCH HISTORY")
        dialog.configure(bg=BG)
        dialog.geometry("760x520")
        dialog.minsize(520, 360)
        dialog.transient(self.root)
        dialog.grab_set()

        header = tk.Frame(
            dialog, bg=BG2, height=60,
            highlightbackground=BORDER, highlightthickness=1
        )
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(
            header, text="◷  SEARCH HISTORY",
            fg=NEON, bg=BG2,
            font=(MONO, 12, "bold")
        ).pack(side="left", padx=14)

        tk.Label(
            header, text=f"{len(self.search_history)} RECORDS",
            fg=MUTED, bg=BG2,
            font=(MONO, 8)
        ).pack(side="right", padx=14)

        body = tk.Frame(
            dialog, bg=PANEL,
            highlightbackground=BORDER2,
            highlightthickness=1
        )
        body.pack(fill="both", expand=True, padx=10, pady=6)

        canvas = tk.Canvas(body, bg=BLACK, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        scrollbar = tk.Scrollbar(body, command=canvas.yview)
        scrollbar.pack(side="right", fill="y", pady=8)

        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg=BLACK)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(
                window, width=e.width
            )
        )

        if not self.search_history:
            tk.Label(
                inner,
                text="NO SEARCH HISTORY",
                fg=MUTED, bg=BLACK,
                font=(MONO, 10, "bold")
            ).pack(pady=30)
        else:
            for index, item in enumerate(self.search_history, 1):
                rc = item.get("rc", "N/A")
                timestamp = item.get("time", "N/A")

                row = tk.Frame(
                    inner, bg=CARD,
                    highlightbackground=BORDER2,
                    highlightthickness=1
                )
                row.pack(
                    fill="x", padx=4, pady=3
                )

                tk.Label(
                    row, text=f"{index:02}",
                    fg=MUTED, bg=CARD,
                    font=(MONO, 8, "bold"),
                    width=4
                ).pack(side="left", padx=5)

                tk.Label(
                    row, text=rc,
                    fg=NEON, bg=CARD,
                    font=(MONO, 10, "bold"),
                    width=16, anchor="w"
                ).pack(side="left", padx=5)

                tk.Label(
                    row, text=timestamp,
                    fg=WHITE, bg=CARD,
                    font=(MONO, 8),
                    anchor="w"
                ).pack(
                    side="left", fill="x", expand=True
                )

                tk.Button(
                    row, text="LOAD",
                    command=lambda plate=rc: (
                        dialog.destroy(),
                        self.load_from_history(plate)
                    ),
                    bg="#071a0d", fg=NEON,
                    activebackground=NEON,
                    activeforeground=BLACK,
                    font=(MONO, 7, "bold"),
                    relief="flat", bd=1,
                    padx=12, pady=5,
                    cursor="hand2"
                ).pack(side="right", padx=7)

        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))

        tk.Button(
            footer, text="CLEAR HISTORY",
            command=lambda: (
                self.clear_history(),
                dialog.destroy()
            ),
            bg="#16070b", fg=RED,
            activebackground=RED,
            activeforeground=BLACK,
            font=(MONO, 8, "bold"),
            relief="flat", bd=1,
            padx=14, pady=7
        ).pack(side="left")

        tk.Button(
            footer, text="CLOSE",
            command=dialog.destroy,
            bg="#071a0d", fg=NEON,
            activebackground=NEON,
            activeforeground=BLACK,
            font=(MONO, 8, "bold"),
            relief="flat", bd=1,
            padx=18, pady=7
        ).pack(side="right")

        self.center_toplevel(dialog)

    def load_from_history(self, rc):
        self.rc_entry.delete(0, "end")
        self.rc_entry.insert(0, rc)
        self.start_lookup()

    def clear_history(self):
        self.search_history = []

        try:
            if os.path.exists(self.history_file()):
                os.remove(self.history_file())
        except Exception as error:
            log(f"History clear error: {error}")

        self.show_dialog(
            "HISTORY",
            "Search history cleared.",
            accent=NEON
        )

    def show_favorites(self):
        favorites = self.load_favorites()

        dialog = tk.Toplevel(self.root)
        dialog.title("FAVORITES")
        dialog.configure(bg=BG)
        dialog.geometry("620x460")
        dialog.minsize(480, 320)
        dialog.transient(self.root)
        dialog.grab_set()

        header = tk.Frame(
            dialog, bg=BG2, height=60,
            highlightbackground=BORDER, highlightthickness=1
        )
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(
            header, text="☆  FAVORITES",
            fg=NEON, bg=BG2,
            font=(MONO, 12, "bold")
        ).pack(side="left", padx=14)

        body = tk.Frame(
            dialog, bg=PANEL,
            highlightbackground=BORDER2,
            highlightthickness=1
        )
        body.pack(fill="both", expand=True, padx=10, pady=6)

        if not favorites:
            tk.Label(
                body,
                text="NO FAVORITES SAVED",
                fg=MUTED, bg=PANEL,
                font=(MONO, 10, "bold")
            ).pack(expand=True)
        else:
            for plate in favorites:
                row = tk.Frame(
                    body, bg=CARD,
                    highlightbackground=BORDER2,
                    highlightthickness=1
                )
                row.pack(
                    fill="x", padx=10, pady=4
                )

                tk.Label(
                    row, text=plate,
                    fg=NEON, bg=CARD,
                    font=(MONO, 10, "bold")
                ).pack(
                    side="left", padx=12, pady=8
                )

                tk.Button(
                    row, text="LOAD",
                    command=lambda p=plate: (
                        dialog.destroy(),
                        self.load_from_history(p)
                    ),
                    bg="#071a0d", fg=NEON,
                    activebackground=NEON,
                    activeforeground=BLACK,
                    font=(MONO, 7, "bold"),
                    relief="flat", bd=1,
                    padx=12, pady=5
                ).pack(side="right", padx=8)

        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))

        tk.Button(
            footer, text="CLOSE",
            command=dialog.destroy,
            bg="#071a0d", fg=NEON,
            activebackground=NEON,
            activeforeground=BLACK,
            font=(MONO, 8, "bold"),
            relief="flat", bd=1,
            padx=18, pady=7
        ).pack(side="right")

        self.center_toplevel(dialog)

    def center_toplevel(self, dialog):
        try:
            self.root.update_idletasks()
            dialog.update_idletasks()

            x = (
                self.root.winfo_rootx()
                + (self.root.winfo_width() - dialog.winfo_width()) // 2
            )
            y = (
                self.root.winfo_rooty()
                + (self.root.winfo_height() - dialog.winfo_height()) // 2
            )

            dialog.geometry(
                f"+{max(0, x)}+{max(0, y)}"
            )
        except Exception:
            pass

    # ---------------------------- sidebar ----------------------------

    def menu_action(self, action):
        if action == "DASHBOARD":
            self.dashboard_canvas.yview_moveto(0)
            self.telemetry_log("[NAV] Dashboard opened.\n")

        elif action == "VEHICLE LOOKUP":
            self.rc_entry.focus_set()
            self.rc_entry.selection_range(0, "end")

        elif action == "RTO INFORMATION":
            self.dashboard_canvas.yview_moveto(0.62)
            self.telemetry_log("[NAV] RTO information focused.\n")

        elif action == "VIN DECODER":
            self.show_dialog(
                "VIN DECODER",
                "VIN decoder module is not connected to the current vehicle API.\n\n"
                "The dashboard is ready for a future VIN module.",
                accent=CYAN
            )

        elif action == "NUMBER PLATE CHECK":
            self.validate_plate()

        elif action == "SEARCH HISTORY":
            self.show_history()

        elif action == "FAVORITES":
            self.show_favorites()

        elif action == "SETTINGS":
            self.show_dialog(
                "SETTINGS",
                f"API ENDPOINT\n{API_BASE}\n\n"
                f"VERSION\n{VERSION}\n\n"
                "CACHE\nENABLED\n\n"
                "LIVE REFRESH\nENABLED\n\n"
                "RESPONSIVE ENGINE\nENABLED\n\n"
                "ALL RETURNED DATA\nVISIBLE",
                accent=NEON
            )

        elif action == "API CONSOLE":
            api_text = (
                f"API BASE\n{API_BASE}\n\n"
                f"CURRENT TARGET\n{self.current_rc or 'NONE'}\n\n"
                f"CURRENT FIELDS\n{len(self.current_data)}\n\n"
                "NETWORK WORKER\nBACKGROUND THREAD\n\n"
                "UI THREAD\nNON-BLOCKING"
            )
            self.show_dialog(
                "API CONSOLE",
                api_text,
                accent=CYAN
            )

        elif action == "ABOUT":
            self.show_dialog(
                "ABOUT",
                f"VEHICLE INFORMATION\n\n"
                f"VERSION: {VERSION}\n"
                f"AUTHOR: {AUTHOR}\n\n"
                "PERFORMANCE ENGINE: ENABLED\n"
                "RESPONSIVE UI: ENABLED\n"
                "CACHE-FIRST LOOKUP: ENABLED\n"
                "ALL-FIELD VIEW: ENABLED\n"
                "MODEL IMAGE SEARCH: ENABLED\n\n"
                "Educational & Ethical Use Only.\n"
                "The vehicle image is a model reference image.",
                accent=NEON
            )

    def validate_plate(self):
        rc = self.rc_entry.get().strip().upper()
        info = self.plate_intelligence(rc)

        if info:
            self.show_dialog(
                "NUMBER PLATE CHECK",
                f"TARGET\n{info['normalized']}\n\n"
                f"STATE / REGION\n{info['state']}\n\n"
                f"RTO CODE\n{info['rto']}\n\n"
                f"SERIES\n{info['series']}\n\n"
                f"REGISTRATION NUMBER\n{info['number']}\n\n"
                "FORMAT\nVALID / RECOGNIZED",
                accent=NEON
            )
        else:
            self.show_dialog(
                "NUMBER PLATE CHECK",
                f"TARGET\n{rc or 'EMPTY'}\n\n"
                "FORMAT\nINVALID / UNRECOGNIZED\n\n"
                "EXPECTED EXAMPLE\nUP14AB1234",
                accent=YELLOW
            )

    def ensure_report_server(self):
        """Start a tiny local HTTP server once so phones can open QR reports."""
        if self.report_server is not None and self.report_server_thread is not None:
            if self.report_server_thread.is_alive():
                return self.report_server_port

        results_dir = os.path.abspath("results")
        handler = lambda *args, **kwargs: ReportRequestHandler(
            *args, directory=results_dir, **kwargs
        )

        try:
            self.report_server = ReportHTTPServer(("0.0.0.0", 0), handler)
            self.report_server_port = self.report_server.server_address[1]
            self.report_server_thread = threading.Thread(
                target=self.report_server.serve_forever,
                daemon=True
            )
            self.report_server_thread.start()
            log(
                f"[REPORT SERVER] Started on "
                f"0.0.0.0:{self.report_server_port}"
            )
            return self.report_server_port
        except Exception as error:
            self.report_server = None
            self.report_server_thread = None
            self.report_server_port = None
            log(f"[REPORT SERVER] Start failed: {error}")
            return None

    def report_rows(self):
        """Return exactly the data representation shown by the dashboard."""
        rows = [
            ("VEHICLE NUMBER", self.current_rc),
            ("MAKER MODEL", self.find_value(self.current_data, "maker model")),
            ("MODEL NAME", self.find_value(self.current_data, "model name")),
            ("FUEL TYPE", self.find_value(self.current_data, "fuel type")),
            ("FUEL NORMS", self.find_value(self.current_data, "fuel norms")),
            ("ADDRESS", self.mask_sensitive_value(
                "address", self.find_value(self.current_data, "address")
            )),
            ("CITY", self.find_value(self.current_data, "city name", "city")),
            ("REGISTERED RTO", self.find_value(
                self.current_data, "registered rto", "rto name"
            )),
            ("RTO CODE", self.find_value(self.current_data, "rto code")),
            ("STATE", self.find_value(self.current_data, "state")),
            ("REGISTRATION DATE", self.find_value(
                self.current_data, "registration date"
            )),
            ("PURCHASE / DELIVERY", self.find_value(
                self.current_data,
                "purchase date", "date of purchase", "purchase",
                "delivery date", "delivery"
            )),
            ("INSURANCE COMPANY", self.find_value(
                self.current_data, "insurance company"
            )),
            ("INSURANCE NO", self.find_value(
                self.current_data, "insurance no", "insurance number"
            )),
            ("INSURANCE UPTO", self.find_value(
                self.current_data, "insurance upto", "insurance expiry"
            )),
            ("PUC NO", self.find_value(
                self.current_data, "puc no", "puc number"
            )),
            ("PUC UPTO", self.find_value(self.current_data, "puc upto")),
            ("FITNESS UPTO", self.find_value(
                self.current_data, "fitness upto"
            )),
            ("TAX UPTO", self.find_value(self.current_data, "tax upto")),
            ("OWNER NAME", self.mask_sensitive_value(
                "owner name", self.find_value(self.current_data, "owner name")
            )),
            ("OWNER SERIAL NO", self.mask_sensitive_value(
                "owner serial no",
                self.find_value(
                    self.current_data,
                    "owner serial no", "owner serial number"
                )
            )),
            ("PHONE", self.mask_sensitive_value(
                "phone", self.find_value(
                    self.current_data, "phone", "mobile"
                )
            )),
        ]

        known = {normalize_key(label) for label, _ in rows}
        for key, value in self.current_data.items():
            if normalize_key(key) not in known:
                rows.append(
                    (key.upper(), self.mask_sensitive_value(key, value))
                )
        return rows

    def build_html_report(self, html_path):
        rows = self.report_rows()
        report = self.age_validity_details(self.current_data)
        score = report["score"]
        score_text = f"{score} / 100" if score is not None else "N/A"

        table_rows = []
        for label, value in rows:
            table_rows.append(
                "<tr><th>{}</th><td>{}</td></tr>".format(
                    html.escape(str(label)),
                    html.escape(stringify(value)).replace("\n", "<br>")
                )
            )

        validity_rows = []
        for label, state in report["fields"]:
            validity_rows.append(
                "<tr><th>{}</th><td class='{}'>{}</td></tr>".format(
                    html.escape(label),
                    "good" if state == "ACTIVE"
                    else "bad" if state == "EXPIRED"
                    else "warn",
                    html.escape(state)
                )
            )

        css = """
        :root { color-scheme: dark; }
        body {
            margin:0; background:#020504; color:#e7f4eb;
            font-family:Arial, sans-serif;
        }
        .wrap { max-width:1000px; margin:auto; padding:24px; }
        .header {
            border:1px solid #087b42; background:#050b08;
            padding:18px; margin-bottom:14px;
        }
        h1 { color:#00ff66; margin:0 0 6px; font-size:24px; }
        h2 { color:#00ff66; font-size:15px; }
        .sub { color:#789184; }
        .card {
            border:1px solid #0d4e2e; background:#06100b;
            padding:14px; margin:12px 0;
        }
        table { width:100%; border-collapse:collapse; }
        th,td {
            border:1px solid #0d4e2e; padding:9px;
            text-align:left; vertical-align:top;
        }
        th { width:30%; color:#00ff66; background:#07130c; }
        .good { color:#00ff66; font-weight:bold; }
        .bad { color:#ff3158; font-weight:bold; }
        .warn { color:#ffd84d; font-weight:bold; }
        a.button {
            display:inline-block; padding:10px 15px; margin:4px 6px 4px 0;
            border:1px solid #00ff66; color:#00ff66;
            text-decoration:none; background:#041c0e;
        }
        .note { color:#789184; font-size:12px; }
        """
        body = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vehicle Report - {html.escape(self.current_rc)}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>VEHICLE INFORMATION REPORT</h1>
    <div class="sub">VEHICLE: {html.escape(self.current_rc)}</div>
    <div class="sub">GENERATED: {html.escape(str(datetime.now()))}</div>
  </div>

  <div class="card">
    <h2>VEHICLE AGE + VALIDITY</h2>
    <table>
      <tr><th>REGISTERED SINCE</th><td>{html.escape(report["registration"])}</td></tr>
      <tr><th>PURCHASE / DELIVERY</th><td>{html.escape(report["purchase"])}</td></tr>
      <tr><th>VEHICLE AGE</th><td>{html.escape(report["age"])}</td></tr>
      <tr><th>AGE REVIEW</th><td class="warn">{html.escape(report["age_review"])}</td></tr>
      <tr><th>HEALTH SCORE</th><td>{html.escape(score_text)}</td></tr>
      <tr><th>OVERALL STATUS</th><td class="{ 'good' if report['overall_color'] == NEON else 'bad' if report['overall_color'] == RED else 'warn' }">{html.escape(report["overall"])}</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>CURRENT VALIDITY</h2>
    <table>{''.join(validity_rows)}</table>
  </div>

  <div class="card">
    <h2>ALL DISPLAYED VEHICLE DATA</h2>
    <table>{''.join(table_rows)}</table>
  </div>

  <div class="card">
    <a class="button" href="{html.escape(self.current_rc)}_report.pdf">OPEN / DOWNLOAD PDF</a>
  </div>

  <div class="note">
    Educational &amp; Ethical Use Only. Vehicle image is a model reference.
    Age is informational; legal renewal/fitness rules depend on vehicle category
    and applicable RTO rules.
  </div>
</div>
</body>
</html>"""
        with open(html_path, "w", encoding="utf-8") as file:
            file.write(body)

    def build_pdf_report(self, pdf_path):
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError(
                "ReportLab is not installed. Run: pip install reportlab"
            )

        rows = self.report_rows()
        report = self.age_validity_details(self.current_data)
        score_text = f"{report['score']} / 100" if report["score"] is not None else "N/A"

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CyberTitle", parent=styles["Title"],
            fontName="Helvetica-Bold", fontSize=18,
            textColor=pdf_colors.HexColor("#00aa55"),
            spaceAfter=12
        )
        heading_style = ParagraphStyle(
            "CyberHeading", parent=styles["Heading2"],
            fontName="Helvetica-Bold", fontSize=11,
            textColor=pdf_colors.HexColor("#007a3d"),
            spaceBefore=10, spaceAfter=7
        )
        normal_style = ParagraphStyle(
            "CyberNormal", parent=styles["BodyText"],
            fontName="Helvetica", fontSize=8.5,
            leading=11
        )

        doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
        )
        story = [
            Paragraph("VEHICLE INFORMATION REPORT", title_style),
            Paragraph(
                f"<b>VEHICLE:</b> {html.escape(self.current_rc)}<br/>"
                f"<b>GENERATED:</b> {html.escape(str(datetime.now()))}",
                normal_style
            ),
            Spacer(1, 10),
            Paragraph("VEHICLE AGE + VALIDITY", heading_style)
        ]

        age_table = [
            ["REGISTERED SINCE", report["registration"]],
            ["PURCHASE / DELIVERY", report["purchase"]],
            ["VEHICLE AGE", report["age"]],
            ["AGE REVIEW", report["age_review"]],
            ["HEALTH SCORE", score_text],
            ["OVERALL STATUS", report["overall"]],
        ]
        table = Table(age_table, colWidths=[145, 385])
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, pdf_colors.HexColor("#5c8f70")),
            ("BACKGROUND", (0,0), (0,-1), pdf_colors.HexColor("#e8f5ec")),
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ]))
        story.extend([table, Spacer(1, 10), Paragraph("CURRENT VALIDITY", heading_style)])

        validity_table = [["CHECK", "STATUS"]] + [
            [label, state] for label, state in report["fields"]
        ]
        table = Table(validity_table, colWidths=[145, 385])
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, pdf_colors.HexColor("#5c8f70")),
            ("BACKGROUND", (0,0), (-1,0), pdf_colors.HexColor("#dcefe3")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.extend([table, Spacer(1, 10), Paragraph("ALL DISPLAYED VEHICLE DATA", heading_style)])

        data_table = [["FIELD", "VALUE"]]
        for label, value in rows:
            data_table.append([str(label), stringify(value)])
        table = Table(data_table, colWidths=[145, 385], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.4, pdf_colors.HexColor("#8aa895")),
            ("BACKGROUND", (0,0), (-1,0), pdf_colors.HexColor("#dcefe3")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.5),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("WORDWRAP", (0,0), (-1,-1), True),
        ]))
        story.extend([
            table, Spacer(1, 12),
            Paragraph(
                "Educational & Ethical Use Only. Vehicle image is a model reference. "
                "Age is informational; legal renewal/fitness rules depend on vehicle "
                "category and applicable RTO rules.",
                normal_style
            )
        ])
        doc.build(story)

    def generate_qr_report(self):
        if not self.current_data:
            self.show_dialog(
                "NO DATA", "Perform a vehicle lookup first.", accent=YELLOW
            )
            return
        if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
            self.show_dialog(
                "QR MODULE NOT INSTALLED",
                "Install the free QR dependencies with:\n\n"
                "pip install qrcode[pil] pillow",
                accent=YELLOW
            )
            return

        ensure_dirs()

        try:
            html_path = os.path.abspath(
                f"results/{self.current_rc}_report.html"
            )
            pdf_path = os.path.abspath(
                f"results/{self.current_rc}_report.pdf"
            )

            self.build_pdf_report(pdf_path)
            self.build_html_report(html_path)

            port = self.ensure_report_server()
            if not port:
                raise RuntimeError(
                    "Could not start the local report server."
                )

            host = get_local_ip()
            report_url = (
                f"http://{host}:{port}/"
                f"{quote(os.path.basename(html_path))}"
            )

            qr_path = f"results/{self.current_rc}_qr.png"
            qrcode.make(report_url).save(qr_path)

            dialog = tk.Toplevel(self.root)
            dialog.title("QR CODE REPORT")
            dialog.configure(bg=BG)
            dialog.geometry("620x720")
            dialog.minsize(520, 620)
            dialog.transient(self.root)
            dialog.grab_set()

            header = tk.Frame(
                dialog, bg=BG2, height=60,
                highlightbackground=BORDER, highlightthickness=1
            )
            header.pack(fill="x", padx=10, pady=(10, 6))
            header.pack_propagate(False)

            tk.Label(
                header, text="▣  QR CODE REPORT",
                fg=NEON, bg=BG2, font=(MONO, 12, "bold")
            ).pack(side="left", padx=14)

            body = tk.Frame(
                dialog, bg=PANEL,
                highlightbackground=BORDER2, highlightthickness=1
            )
            body.pack(fill="both", expand=True, padx=10, pady=6)

            with Image.open(qr_path) as qr_img:
                qr_img = qr_img.convert("RGB")
                qr_img.thumbnail((430, 430), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(qr_img)

            label = tk.Label(body, image=photo, bg="white")
            label.image = photo
            label.pack(pady=14)

            tk.Label(
                body,
                text=f"SCAN → FULL DATA REPORT  //  {self.current_rc}",
                fg=NEON, bg=PANEL, font=(MONO, 8, "bold")
            ).pack()

            tk.Label(
                body,
                text=(
                    "Phone and laptop must be on the same Wi-Fi/network.\n"
                    "Scan opens the full report page + PDF download."
                ),
                fg=MUTED, bg=PANEL, font=(MONO, 7),
                justify="center"
            ).pack(pady=(5, 8))

            url_label = tk.Label(
                body,
                text=report_url,
                fg=CYAN, bg=PANEL,
                font=(MONO, 7),
                wraplength=540,
                justify="center"
            )
            url_label.pack(pady=(0, 8))

            footer = tk.Frame(dialog, bg=BG)
            footer.pack(fill="x", padx=10, pady=(6, 10))

            tk.Button(
                footer, text="CLOSE", command=dialog.destroy,
                bg="#071a0d", fg=NEON,
                activebackground=NEON, activeforeground=BLACK,
                font=(MONO, 8, "bold"), relief="flat", bd=1,
                padx=18, pady=7, cursor="hand2"
            ).pack(side="right")

            self.center_toplevel(dialog)
            self.telemetry_log(
                f"[QR] Full report generated.\n"
                f"[QR] HTML: {html_path}\n"
                f"[QR] PDF: {pdf_path}\n"
                f"[QR] URL: {report_url}\n"
            )

        except Exception as error:
            log(f"QR generation error: {error}")
            self.show_dialog("QR ERROR", str(error), accent=RED)

    # ---------------------------- export ----------------------------

    def sanitize_data_for_storage(self, value, key=""):
        if isinstance(value, dict):
            return {k: self.sanitize_data_for_storage(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.sanitize_data_for_storage(v, key) for v in value]
        return self.mask_sensitive_value(key, value)

    def save_result(self):
        if not self.current_rc:
            return

        try:
            filename = f"results/{self.current_rc}.json"

            with open(
                filename,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    self.current_raw_data,
                    file,
                    indent=2,
                    ensure_ascii=False
                )
        except Exception as error:
            log(f"Result save error: {error}")

    def export_json(self):
        if not self.current_data:
            self.show_dialog(
                "NO DATA",
                "Perform a vehicle lookup first.",
                accent=YELLOW
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Export Vehicle JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=f"{self.current_rc}_vehicle.json"
        )

        if not filename:
            return

        try:
            with open(
                filename,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    self.current_raw_data,
                    file,
                    indent=2,
                    ensure_ascii=False
                )

            self.show_dialog(
                "EXPORT COMPLETE",
                f"JSON exported successfully.\n\n{filename}",
                accent=NEON
            )

        except Exception as error:
            self.show_dialog(
                "EXPORT ERROR",
                str(error),
                accent=RED
            )

    def copy_result(self):
        if not self.current_data:
            self.show_dialog(
                "NO DATA",
                "Perform a vehicle lookup first.",
                accent=YELLOW
            )
            return

        try:
            lines = [
                f"VEHICLE: {self.current_rc}",
                "-" * 70,
            ]

            for key, value in self.current_data.items():
                lines.append(
                    f"{key.upper()}: {self.mask_sensitive_value(key, value)}"
                )

            text = "\n".join(lines)

            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()

            self.show_dialog(
                "COPIED",
                "Complete vehicle result copied to clipboard.",
                accent=NEON
            )

        except Exception as error:
            self.show_dialog(
                "COPY ERROR",
                str(error),
                accent=RED
            )

    def export_report(self):
        if not self.current_data:
            self.show_dialog(
                "NO DATA",
                "Perform a vehicle lookup first.",
                accent=YELLOW
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Export Vehicle Report",
            defaultextension=".txt",
            filetypes=[("Text Report", "*.txt")],
            initialfile=f"{self.current_rc}_report.txt"
        )

        if not filename:
            return

        try:
            with open(
                filename,
                "w",
                encoding="utf-8"
            ) as file:
                file.write("VEHICLE INFORMATION\n")
                file.write("=" * 80 + "\n\n")
                file.write(
                    f"VEHICLE NUMBER: {self.current_rc}\n"
                )
                file.write(
                    f"GENERATED: {datetime.now()}\n\n"
                )

                for key, value in self.current_data.items():
                    file.write(
                        f"{key.upper():35} "
                        f"{self.mask_sensitive_value(key, value)}\n"
                    )

            self.show_dialog(
                "EXPORT COMPLETE",
                f"Vehicle report exported successfully.\n\n{filename}",
                accent=NEON
            )

        except Exception as error:
            self.show_dialog(
                "EXPORT ERROR",
                str(error),
                accent=RED
            )

    # ---------------------------- misc ----------------------------

    def show_dialog(self, title, message, width=650, height=420, accent=NEON):
        # Keep only one generic dialog reference.
        try:
            if self._theme_dialog is not None:
                if self._theme_dialog.root.winfo_exists():
                    self._theme_dialog.close()
        except Exception:
            pass

        self._theme_dialog = ThemedDialog(
            self,
            title,
            message,
            width=width,
            height=height,
            accent=accent,
            text_mode=False
        )

    def stop_lookup(self):
        if not self.scanning:
            return

        self.stop_event.set()
        self.lookup_generation += 1
        self.scanning = False
        self.stop_btn.config(state="disabled")
        self.scan_btn.config(text="⌕  SEARCH", state="normal", bg="#041c0e")
        self.status_label.config(text="● STOPPED", fg=RED)
        self.cache_label.config(text="CACHE   READY", fg=MUTED)
        self.summary_status.config(text="STOPPED", fg=RED)
        self.telemetry_log("[SCAN] Lookup stopped by user.\n")

    def lookup_stopped(self):
        self.scanning = False
        self.stop_btn.config(state="disabled")
        self.scan_btn.config(text="⌕  SEARCH", state="normal", bg="#041c0e")
        self.status_label.config(text="● STOPPED", fg=RED)
        self.cache_label.config(text="CACHE   READY", fg=MUTED)
        self.summary_status.config(text="STOPPED", fg=RED)
        self.telemetry_log("[SCAN] Lookup cancelled.\n")

    def lookup_error(self, error):
        self.scanning = False
        self.stop_btn.config(state="disabled")

        self.scan_btn.config(
            text="⌕  SEARCH",
            state="normal",
            bg="#041c0e"
        )

        self.status_label.config(
            text="● ONLINE",
            fg=NEON
        )

        self.cache_label.config(
            text="CACHE   READY",
            fg=MUTED
        )

        self.summary_status.config(
            text="ERROR",
            fg=RED
        )

        self.telemetry_log(
            f"[ERROR] {error}\n"
        )

        self.show_dialog(
            "LOOKUP FAILED",
            error,
            accent=RED
        )

    def close_application(self):
        try:
            if self.report_server is not None:
                self.report_server.shutdown()
                self.report_server.server_close()
        except Exception as error:
            log(f"Report server shutdown error: {error}")
        try:
            self.root.destroy()
        except Exception:
            pass

    def update_clock(self):
        # Kept as a lightweight 1-second timer.
        # No widget currently needs a clock label.
        self.root.after(1000, self.update_clock)

    def build_bottom_bar(self):
        bottom = tk.Frame(
            self.root, bg=BLACK, height=30,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        bottom.pack(
            fill="x", padx=18, pady=(0, 8)
        )
        bottom.pack_propagate(False)

        tk.Label(
            bottom, text=">> SYSTEM SECURED",
            fg=NEON, bg=BLACK,
            font=(MONO, 8, "bold")
        ).pack(side="left", padx=15)

        tk.Label(
            bottom, text=">> ENCRYPTION: AES-256",
            fg=MUTED, bg=BLACK,
            font=(MONO, 8)
        ).pack(side="left", padx=40)

        tk.Label(
            bottom, text=">> MODE: EDUCATIONAL",
            fg=MUTED, bg=BLACK,
            font=(MONO, 8)
        ).pack(side="right", padx=15)


def main():
    ensure_dirs()

    root = tk.Tk()

    app = VehicleInformationApp(root)
    app.load_history()

    root.mainloop()


if __name__ == "__main__":
    main()
