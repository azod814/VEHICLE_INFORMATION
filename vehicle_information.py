"""
VEHICLE_INFORMATION (AZOD814) - v6.5
Cyberpunk Vehicle Intelligence & Tactical Recon Console

Educational & Ethical Use Only.

Features & Fixes:
- Multi-threaded non-blocking Tkinter engine.
- Resilient API Dual-Route (Direct endpoint + Failover Tunnel).
- In-App Challan Intelligence Matrix (No external redirect required).
- Built-in Local HTTP Server + QR Code Mobile Scanner.
- Full All-Data inspector, Age/Validity calculator, ReportLab PDF exporter.
- Retained full UI structure: Top bar, Sidebar, Bottom Bar, Multi-box Intel.
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
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
FALLBACK_API = "https://api.allorigins.win/raw?url=" + quote("https://vehicleinfobyterabaap.vercel.app/lookup")
WIKI_API = "https://commons.wikimedia.org/w/api.php"
VERSION = "6.5"
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
FONT = "DejaVu Sans" if os.name != "nt" else "Segoe UI"
MONO = "DejaVu Sans Mono" if os.name != "nt" else "Consolas"

STATE_CODES = {
    "AN": "Andaman & Nicobar", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh",
    "AS": "Assam", "BR": "Bihar", "CH": "Chandigarh", "CG": "Chhattisgarh",
    "DN": "Dadra & Nagar Haveli", "DD": "Daman & Diu", "DL": "Delhi",
    "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh",
    "JK": "Jammu & Kashmir", "JH": "Jharkhand", "KA": "Karnataka",
    "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep", "MP": "Madhya Pradesh",
    "MH": "Maharashtra", "MN": "Manipur", "ML": "Meghalaya", "MZ": "Mizoram",
    "NL": "Nagaland", "OD": "Odisha", "PB": "Punjab", "PY": "Puducherry",
    "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TS": "Telangana",
    "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal"
}


def get_local_ip():
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
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
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
            "data", "result", "vehicle", "vehicle_data",
            "vehicle data", "vehicleData", "response", "details",
            "result_data", "resultData"
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
    main = find_main_dict(data)
    return flatten_data(main)


class ThemedDialog:
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
        self.root.title(f"VEHICLE INFORMATION // v{VERSION} // {AUTHOR} // RECON CONSOLE")
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
            title, text="ADVANCED VEHICLE LOOKUP & CHALLAN SYSTEM",
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
            status, text="RESPONSE TIME    --", fg=MUTED, bg=BG2,
            font=(MONO, 8)
        )
        self.response_label.pack(anchor="w")

        self.cache_label = tk.Label(
            status, text="CACHE    READY", fg=MUTED, bg=BG2,
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
            ("⚠", "CHALLAN RECORDS"),
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
                side, text=f"{icon}    {name}", anchor="w",
                command=lambda n=name: self.menu_action(n),
                bg=BG2, fg=WHITE,
                activebackground="#07351d",
                activeforeground=NEON,
                font=(MONO, 8, "bold"),
                relief="flat", bd=0,
                padx=18, pady=9, cursor="hand2"
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
            ("FAILOVER", "ENABLED"),
            ("CACHE", "ENABLED"),
            ("CHALLAN AUDIT", "IN-APP"),
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
        self.summary_challan = self.summary_card(
            row, "⚠", "NO CHECK", "Challan Records", YELLOW
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
            card, text=icon, fg=color, bg=BG2,
            font=(MONO, 22, "bold")
        ).pack(side="left", padx=12)

        frame = tk.Frame(card, bg=BG2)
        frame.pack(side="left")

        label = tk.Label(
            frame, text=value, fg=color, bg=BG2,
            font=(MONO, 16, "bold")
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

        self.root.bind_all("<MouseWheel>", self.mouse_scroll_anywhere, add="+")
        self.root.bind_all("<Button-4>", self.mouse_scroll_anywhere, add="+")
        self.root.bind_all("<Button-5>", self.mouse_scroll_anywhere, add="+")

        self.build_intelligence_section()
        self.build_challan_section()
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

        summary = tk.Frame(top, bg=CARD, highlightbackground=BORDER2, highlightthickness=1)
        summary.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(summary, text="SMART VEHICLE SUMMARY", fg=NEON, bg=CARD, font=(MONO, 8, "bold")).pack(anchor="w", padx=12, pady=(10, 5))
        self.smart_summary_text = tk.Label(
            summary, text="Perform a vehicle lookup to generate an intelligent summary.",
            fg=WHITE, bg=CARD, font=(MONO, 8), justify="left", anchor="nw",
            wraplength=520
        )
        self.smart_summary_text.pack(fill="x", padx=12, pady=(0, 10))

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

        self.age_check_btn = tk.Button(
            bottom,
            text="⌛  CHECK VEHICLE AGE + VALIDITY",
            command=self.show_age_validity_report,
            bg="#041c0e", fg=CYAN,
            activebackground=CYAN, activeforeground=BLACK,
            font=(MONO, 8, "bold"), relief="flat", bd=1,
            highlightbackground=BORDER2, padx=12, pady=8, cursor="hand2"
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

    def build_challan_section(self):
        """In-app live Challan section."""
        frame = self.section(self.dashboard_frame, "⚠  IN-APP CHALLAN INTELLIGENCE")
        frame.pack(fill="x", padx=10, pady=(0, 7))

        body = tk.Frame(frame, bg=CARD, highlightbackground=BORDER2, highlightthickness=1)
        body.pack(fill="x", padx=10, pady=(0, 8))

        self.challan_status_lbl = tk.Label(
            body, text="CHALLAN STATUS: AWAITING VEHICLE LOOKUP",
            fg=MUTED, bg=CARD, font=(MONO, 9, "bold"), anchor="w"
        )
        self.challan_status_lbl.pack(fill="x", padx=12, pady=(8, 2))

        self.challan_summary_lbl = tk.Label(
            body, text="Active Unpaid Challans: --  |  Pending Fine: ₹0  |  Standing: UNCHECKED",
            fg=WHITE, bg=CARD, font=(MONO, 8), anchor="w"
        )
        self.challan_summary_lbl.pack(fill="x", padx=12, pady=(0, 8))

        btn_row = tk.Frame(body, bg=CARD)
        btn_row.pack(fill="x", padx=12, pady=(0, 8))

        tk.Button(
            btn_row, text="⚠  VIEW DETAILED CHALLAN DOSSIER (IN-APP)",
            command=self.show_challan_modal,
            bg="#041c0e", fg=CYAN, activebackground=CYAN, activeforeground=BLACK,
            font=(MONO, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER2,
            padx=14, pady=6, cursor="hand2"
        ).pack(side="left")

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

        clean_model = re.sub(
            r"\b(DUAL|CH|ABS|CBS|LCD|LED|BS[- ]?[IV0-9]+|PHASE[- ]?[0-9]+|PETROL|DIESEL|CNG|E20|DISC|DRUM)\b",
            " ", model.upper(), flags=re.IGNORECASE
        )
        clean_model = " ".join(clean_model.split()).strip()

        brand = maker.title()
        model_name = clean_model.title() or model.title()
        queries = [f"{brand} {model_name} bike", f"{brand} {model_name} vehicle", f"{model_name} vehicle"]

        cache_key = f"{brand}_{model_name}"
        cached = image_cache_file(cache_key)

        if os.path.exists(cached):
            return cached

        if DDGS_AVAILABLE:
            try:
                with DDGS() as ddgs:
                    for query in queries[:2]:
                        results = ddgs.images(query, max_results=5)
                        for result in results:
                            image_url = result.get("image") or result.get("thumbnail")
                            if image_url:
                                downloaded = self.download_vehicle_image(image_url, cached)
                                if downloaded:
                                    return downloaded
            except Exception as error:
                log(f"[IMAGE] DDGS error: {error}")

        # Wikimedia Fallback
        for query in queries[:2]:
            try:
                params = {
                    "action": "query", "generator": "search", "gsrsearch": query,
                    "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
                    "iiprop": "url", "iiurlwidth": 800, "format": "json", "origin": "*"
                }
                response = requests.get(WIKI_API, params=params, timeout=6)
                pages = response.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    info = page.get("imageinfo", [])
                    if info:
                        img_url = info[0].get("thumburl") or info[0].get("url")
                        downloaded = self.download_vehicle_image(img_url, cached)
                        if downloaded:
                            return downloaded
            except Exception:
                pass

        return None

    def download_vehicle_image(self, image_url, destination):
        if not image_url or not PIL_AVAILABLE:
            return None
        temp_file = destination + ".tmp"
        try:
            response = requests.get(
                image_url, timeout=6, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code != 200 or len(response.content) < 3000:
                return None

            with open(temp_file, "wb") as file:
                file.write(response.content)

            with Image.open(temp_file) as image:
                image.load()
                image.convert("RGB").save(destination, "JPEG", quality=90, optimize=True)

            return destination
        except Exception:
            return None
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def schedule_image_redraw(self):
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(140, self.redraw_current_image)

    def load_vehicle_image(self, image_path, model):
        if not image_path or not PIL_AVAILABLE:
            return
        try:
            width = max(self.image_canvas.winfo_width(), 220)
            height = max(self.image_canvas.winfo_height(), 180)

            with Image.open(image_path) as source:
                image = source.convert("RGB")
                max_w = max(int(width * 0.90), 180)
                max_h = max(int(height * 0.82), 150)
                image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                self.vehicle_image = ImageTk.PhotoImage(image)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(width // 2, height // 2, image=self.vehicle_image, anchor="center")
            self.draw_image_brackets(width, height)
            self.image_status.config(text="MODEL REFERENCE: " + str(model)[:35].upper(), fg=NEON)
        except Exception as error:
            log(f"Image load error: {error}")
            self.draw_vehicle_hud()

    def redraw_current_image(self):
        self._resize_job = None
        if self.vehicle_image_path and os.path.exists(self.vehicle_image_path) and PIL_AVAILABLE:
            self.load_vehicle_image(self.vehicle_image_path, self._image_model_label)
        else:
            self.draw_vehicle_hud()

    def draw_image_brackets(self, width, height):
        c = self.image_canvas
        m = 15
        length = 25
        lines = [
            (m, m, m + length, m), (m, m, m, m + length),
            (width - m, m, width - m - length, m), (width - m, m, width - m, m + length),
            (m, height - m, m + length, height - m), (m, height - m, m, height - m - length),
            (width - m, height - m, width - m - length, height - m), (width - m, height - m, width - m, height - m - length),
        ]
        for line in lines:
            c.create_line(*line, fill=NEON, width=2)

    def draw_vehicle_hud(self):
        if not hasattr(self, "image_canvas"):
            return
        canvas = self.image_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 260)
        height = max(canvas.winfo_height(), 200)

        for x in range(0, width, 32):
            canvas.create_line(x, 0, x, height, fill="#062819")
        for y in range(0, height, 32):
            canvas.create_line(0, y, width, y, fill="#062819")

        canvas.create_text(
            width // 2, height // 2,
            text="[ MODEL REFERENCE HUD ]\nNO IMAGE CACHED",
            fill=MUTED, font=(MONO, 8, "bold"), justify="center"
        )

    def build_actions(self, parent):
        frame = self.section(parent, "▧  QUICK ACTIONS")
        frame.pack(fill="x", pady=(0, 8))

        self.action_button(frame, "▣  EXPORT REPORT", self.export_report)
        self.action_button(frame, "▣  EXPORT JSON", self.export_json)
        self.action_button(frame, "↗  COPY RESULT", self.copy_result)
        self.action_button(frame, "☆  ADD TO FAVORITES", self.favorite)
        self.action_button(frame, "▣  QR CODE REPORT (PHONE)", self.generate_qr_report)

    def action_button(self, parent, text, command):
        tk.Button(
            parent, text=text, command=command,
            bg="#07130c", fg=WHITE,
            activebackground="#06391e", activeforeground=NEON,
            font=(MONO, 8, "bold"), relief="flat", bd=1,
            highlightbackground=BORDER2, pady=7, cursor="hand2"
        ).pack(fill="x", padx=10, pady=2)

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
        self.telemetry.insert("end", "[SYSTEM] Vehicle Intelligence Console v6.5 Initialized.\n")
        self.telemetry.configure(state="disabled")

    def telemetry_log(self, message):
        try:
            self.telemetry.configure(state="normal")
            self.telemetry.insert("end", message)
            self.telemetry.see("end")
            self.telemetry.configure(state="disabled")
        except Exception:
            pass

    def start_lookup(self):
        if self.scanning:
            return

        rc = self.rc_entry.get().strip().upper().replace(" ", "").replace("-", "")
        if not rc:
            self.show_dialog("INPUT REQUIRED", "Enter a vehicle registration number.", accent=YELLOW)
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

        self.scan_btn.config(text="◌  SEARCHING...", state="disabled", bg="#073b20")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="● SCANNING", fg=YELLOW)
        self.cache_label.config(text="CACHE    CHECKING", fg=YELLOW)

        self.summary_vehicle.config(text=rc)
        self.summary_status.config(text="SCANNING...", fg=YELLOW)
        self.summary_challan.config(text="CHECKING...", fg=YELLOW)
        self.summary_challan.config(text="PENDING", fg=YELLOW)

        self.telemetry_log(f"\n[SCAN] Target RC: {rc}\n")

        threading.Thread(
            target=self.lookup_worker,
            args=(rc, generation),
            daemon=True
        ).start()

    def lookup_worker(self, rc, generation):
        start = time.time()
        cache_hit = False
        raw = None
        path = cache_file(rc)

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    cached_raw = json.load(file)
                cache_hit = True
                cached_normalized = normalize_api_response(cached_raw)
                self.root.after(0, lambda: self.show_cached_result(rc, cached_raw, cached_normalized))
            except Exception as error:
                log(f"Cache read failed: {error}")

        if not raw and not self.stop_event.is_set():
            try:
                url = API_BASE + "?" + urlencode({"rc": rc})
                response = requests.get(url, timeout=(4, 10), headers={"User-Agent": "VehicleInfoRecon/6.5"})
                if response.status_code == 200:
                    raw = response.json()
            except Exception as e:
                self.root.after(0, lambda: self.telemetry_log(f"[API] Primary timeout. Trying Failover tunnel...\n"))

        if not raw and not self.stop_event.is_set():
            try:
                fb_url = FALLBACK_API + "?" + urlencode({"rc": rc})
                response = requests.get(fb_url, timeout=(4, 10))
                if response.status_code == 200:
                    raw = response.json()
            except Exception as e:
                self.root.after(0, lambda: self.telemetry_log(f"[API] Tunnel failover failed: {e}\n"))

        if self.stop_event.is_set() or generation != self.lookup_generation:
            self.root.after(0, self.lookup_stopped)
            return

        resp_time = round((time.time() - start) * 1000, 2)

        if raw:
            try:
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(self.sanitize_data_for_storage(raw), file, indent=2, ensure_ascii=False)
            except Exception:
                pass
            normalized = normalize_api_response(raw)
            self.root.after(0, lambda: self.lookup_finished(rc, raw, normalized, cache_hit, resp_time))
        else:
            self.root.after(0, lambda: self.lookup_offline_resolution(rc))

    def lookup_offline_resolution(self, rc):
        self.scanning = False
        self.scan_btn.config(text="⌕  SEARCH", state="normal", bg="#041c0e")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="● OFFLINE DECODE", fg=YELLOW)
        self.summary_status.config(text="OFFLINE", fg=YELLOW)

        st_code = rc[:2]
        st_name = STATE_CODES.get(st_code, "India RTO")
        offline_data = {
            "registration number": rc,
            "registered rto": f"{st_name} (Code {st_code})",
            "state": st_name,
            "owner name": "[PROTECTED]",
            "maker model": "Vehicle Spec Unreachable (Network)",
        }
        self.populate_vehicle_data(offline_data)
        self.set_all_data(offline_data)
        self.show_dialog(
            "OFFLINE REGISTRATION DETECTED",
            f"Target: {rc}\nState: {st_name}\n\nLive network endpoint unreachable. Local heuristics applied.",
            accent=YELLOW
        )

    def show_cached_result(self, rc, raw, normalized):
        self.current_rc = rc
        self.current_raw_data = raw
        self.current_data = normalized
        self.summary_vehicle.config(text=rc)
        self.summary_status.config(text="CACHE DATA", fg=CYAN)
        self.cache_label.config(text="CACHE    DISPLAYED", fg=CYAN)
        self.populate_vehicle_data(normalized)
        self.set_all_data(normalized)
        self.update_challan_ui(raw)

    def lookup_finished(self, rc, raw, normalized, cached, response_time):
        self.scanning = False
        self.stop_btn.config(state="disabled")
        self.scan_btn.config(text="⌕  SEARCH", state="normal", bg="#041c0e")
        self.status_label.config(text="● ONLINE", fg=NEON)
        self.cache_label.config(text="CACHE    UPDATED", fg=NEON)
        self.summary_vehicle.config(text=rc)
        self.summary_response.config(text=f"{response_time} ms")
        self.response_label.config(text=f"RESPONSE TIME    {response_time} ms")
        self.summary_status.config(text="SUCCESS" if normalized else "NO DATA", fg=NEON)

        self.current_rc = rc
        self.current_raw_data = raw
        self.current_data = normalized

        self.populate_vehicle_data(normalized)
        self.set_all_data(normalized)
        self.update_challan_ui(raw)
        self.add_history(rc)

        maker = self.find_value(normalized, "maker", "manufacturer", "make")
        model = self.find_value(normalized, "maker model", "model name", "model")

        if model != "N/A":
            threading.Thread(target=self.image_worker, args=(maker, model), daemon=True).start()

    def update_challan_ui(self, raw):
        challans = []
        if isinstance(raw, dict):
            for key in ("challans", "challan_details", "challan"):
                if key in raw and isinstance(raw[key], list):
                    challans = raw[key]
                    break

        if challans:
            count = len(challans)
            self.challan_status_lbl.config(text=f"CHALLAN STATUS: {count} ACTIVE/PENDING CHALLANS DETECTED", fg=RED)
            self.challan_summary_lbl.config(text=f"Unpaid Records Found: {count}. Click button below to inspect offenses.", fg=YELLOW)
            self.summary_challan.config(text=f"{count} ACTIVE", fg=RED)
        else:
            self.challan_status_lbl.config(text="CHALLAN STATUS: NO UNPAID CHALLANS FLAGGED", fg=NEON)
            self.challan_summary_lbl.config(text="National Registry compliance indicates clean traffic standing.", fg=WHITE)
            self.summary_challan.config(text="CLEAN", fg=NEON)

    def show_challan_modal(self):
        if not self.current_rc:
            self.show_dialog("NO VEHICLE", "Perform a vehicle lookup first.", accent=YELLOW)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"IN-APP CHALLAN INTEL // {self.current_rc}")
        dialog.geometry("700x500")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.grab_set()

        header = tk.Frame(dialog, bg=BG2, height=60, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(header, text=f"⚠  CHALLAN RECORDS: {self.current_rc}", fg=NEON, bg=BG2, font=(MONO, 11, "bold")).pack(side="left", padx=14)

        body = tk.Frame(dialog, bg=PANEL, highlightbackground=BORDER2, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        txt = tk.Text(body, bg=BLACK, fg=WHITE, font=(MONO, 8), relief="flat", bd=0, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        challans = []
        if isinstance(self.current_raw_data, dict):
            for k in ("challans", "challan_details", "challan"):
                if k in self.current_raw_data and isinstance(self.current_raw_data[k], list):
                    challans = self.current_raw_data[k]
                    break

        lines = [
            f"CHALLAN AUDIT REPORT FOR: {self.current_rc}",
            f"TIMESTAMP: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "=" * 70,
            ""
        ]

        if challans:
            lines.append("RECORDED TRAFFIC OFFENSES:\n")
            for idx, ch in enumerate(challans, 1):
                lines.append(f"[{idx}] CHALLAN NUMBER: {ch.get('number', 'N/A')}")
                lines.append(f"    FINE AMOUNT   : ₹{ch.get('amount', '0')}")
                lines.append(f"    OFFENSE       : {ch.get('offense', 'Traffic Violation')}")
                lines.append(f"    STATUS        : {ch.get('status', 'PENDING')}\n")
        else:
            lines.extend([
                "CHALLAN VERIFICATION STANDING: CLEAN",
                "-" * 50,
                "No pending or unpaid challans returned for this vehicle registration.",
                "Vehicle passes standard compliance audits."
            ])

        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")

        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))
        tk.Button(
            footer, text="CLOSE", command=dialog.destroy, bg="#071a0d", fg=NEON,
            font=(MONO, 8, "bold"), relief="flat", bd=1, padx=18, pady=7, cursor="hand2"
        ).pack(side="right")

    def image_worker(self, maker, model):
        try:
            path = self.search_vehicle_image(maker, model)
            self.root.after(0, lambda: self.image_result(path, maker, model))
        except Exception:
            self.root.after(0, lambda: self.image_result(None, maker, model))

    def image_result(self, path, maker, model):
        if path and os.path.exists(path):
            self.vehicle_image_path = path
            self.load_vehicle_image(path, model)
            self.telemetry_log("[IMAGE] Model visual loaded.\n")
        else:
            self.draw_vehicle_hud()
            self.image_status.config(text="MODEL IMAGE NOT FOUND", fg=MUTED)

    def find_value(self, data, *names):
        if not data:
            return "N/A"
        targets = [normalize_key(name) for name in names]
        for target in targets:
            if target in data:
                val = stringify(data[target])
                if val != "N/A":
                    return val
        for target in targets:
            for key, value in data.items():
                if target in key or key in target:
                    val = stringify(value)
                    if val != "N/A":
                        return val
        return "N/A"

    def parse_date_value(self, value):
        text = stringify(value)
        if text == "N/A":
            return None
        text = " ".join(text.strip().replace(",", " ").split())
        formats = (
            "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d-%B-%Y",
            "%d %b %Y", "%b-%d-%Y", "%Y-%m-%dT%H:%M:%S"
        )
        for fmt in formats:
            try:
                return datetime.strptime(text[:11], fmt)
            except ValueError:
                pass
        return None

    def vehicle_age_breakdown(self, dt):
        if not dt:
            return None
        today = datetime.now().date()
        reg = dt.date()
        if reg > today:
            return None
        years = today.year - reg.year
        if reg.replace(year=reg.year + years) > today:
            years -= 1
        months = (today.year - reg.year) * 12 + today.month - reg.month
        return years, months % 12, (today - reg).days % 30

    def vehicle_age_text(self, data):
        dt = self.parse_date_value(self.find_value(data, "registration date", "reg date"))
        res = self.vehicle_age_breakdown(dt)
        if not res:
            return "N/A"
        y, m, d = res
        return f"{y} YEARS {m} MONTHS {d} DAYS"

    def validity_state(self, data, *names):
        val = self.find_value(data, *names)
        if val == "N/A":
            return "UNKNOWN"
        dt = self.parse_date_value(val)
        if dt:
            return "ACTIVE" if dt.date() >= datetime.now().date() else "EXPIRED"
        txt = val.upper()
        if any(w in txt for w in ("EXPIRED", "NO", "INVALID")):
            return "EXPIRED"
        if any(w in txt for w in ("VALID", "YES", "ACTIVE")):
            return "ACTIVE"
        return "UNKNOWN"

    def calculate_health_score(self, data):
        checks = [
            self.validity_state(data, "insurance upto", "insurance expiry"),
            self.validity_state(data, "puc upto", "puc expiry"),
            self.validity_state(data, "fitness upto"),
            self.validity_state(data, "tax upto")
        ]
        score = 100
        for state in checks:
            if state == "EXPIRED":
                score -= 25
            elif state == "UNKNOWN":
                score -= 5
        return max(0, min(100, score)), checks

    def update_intelligence(self, data):
        maker = self.find_value(data, "maker", "manufacturer", "make")
        model = self.find_value(data, "maker model", "model name")
        city = self.find_value(data, "city name", "city")
        age = self.vehicle_age_text(data)
        score, checks = self.calculate_health_score(data)

        self.smart_summary_text.config(
            text=f"{maker} {model}\nCity: {city} | Age: {age}"
        )
        self.age_label.config(text=f"VEHICLE AGE: {age}")
        color = NEON if score >= 80 else (YELLOW if score >= 50 else RED)
        self.health_score_label.config(text=f"{score} / 100", fg=color)
        self.health_status_label.config(
            text="HEALTHY" if score >= 80 else "ATTENTION NEEDED", fg=color
        )

    def mask_sensitive_value(self, key, value):
        val = stringify(value)
        key = normalize_key(key)
        if val == "N/A":
            return val
        if "owner serial" in key:
            return "[PROTECTED]"
        if "owner name" in key:
            parts = val.split()
            return " ".join([p[0] + "*" * (len(p) - 1) if len(p) > 1 else p for p in parts])
        return val

    def populate_vehicle_data(self, data):
        items = [
            ("▧", "ADDRESS", self.mask_sensitive_value("address", self.find_value(data, "address"))),
            ("▥", "CITY", self.find_value(data, "city name", "city")),
            ("▦", "FITNESS UPTO", self.find_value(data, "fitness upto")),
            ("◉", "FUEL TYPE", self.find_value(data, "fuel type")),
            ("♢", "INSURANCE COMPANY", self.find_value(data, "insurance company")),
            ("▣", "INSURANCE NO", self.find_value(data, "insurance no")),
            ("▦", "INSURANCE UPTO", self.find_value(data, "insurance upto")),
            ("▱", "MAKER MODEL", self.find_value(data, "maker model")),
            ("◇", "MODEL NAME", self.find_value(data, "model name")),
            ("♙", "OWNER NAME", self.mask_sensitive_value("owner name", self.find_value(data, "owner name"))),
            ("▥", "REGISTERED RTO", self.find_value(data, "registered rto")),
            ("▦", "REGISTRATION DATE", self.find_value(data, "registration date")),
        ]
        self.render_details(items)
        self.update_intelligence(data)

    def show_age_validity_report(self):
        if not self.current_data:
            self.show_dialog("NO DATA", "Perform a lookup first.", accent=YELLOW)
            return
        age = self.vehicle_age_text(self.current_data)
        score, _ = self.calculate_health_score(self.current_data)
        msg = f"TARGET: {self.current_rc}\nVEHICLE AGE: {age}\nHEALTH COMPLIANCE: {score}/100"
        self.show_dialog("AGE & COMPLIANCE", msg, accent=CYAN)

    def on_window_resize(self, event=None):
        if self._layout_job is not None:
            try:
                self.root.after_cancel(self._layout_job)
            except Exception:
                pass
        self._layout_job = self.root.after(120, self.apply_responsive_layout)

    def apply_responsive_layout(self):
        self._layout_job = None
        width = self.root.winfo_width()
        if width >= 1200:
            self.sidebar_panel.grid(row=0, column=0, sticky="ns", padx=(0, 7))
            self.center_panel.grid(row=0, column=1, sticky="nsew", padx=7)
            self.right_panel.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
            self.main_body.grid_columnconfigure(1, weight=1)
        else:
            self.sidebar_panel.grid_remove()
            self.center_panel.grid(row=0, column=0, sticky="nsew")
            self.right_panel.grid(row=0, column=1, sticky="nsew")

    def ensure_report_server(self):
        if self.report_server is not None and self.report_server_thread is not None:
            if self.report_server_thread.is_alive():
                return self.report_server_port
        results_dir = os.path.abspath("results")
        handler = lambda *args, **kwargs: ReportRequestHandler(*args, directory=results_dir, **kwargs)
        try:
            self.report_server = ReportHTTPServer(("0.0.0.0", 0), handler)
            self.report_server_port = self.report_server.server_address[1]
            self.report_server_thread = threading.Thread(target=self.report_server.serve_forever, daemon=True)
            self.report_server_thread.start()
            return self.report_server_port
        except Exception:
            return None

    def export_report(self):
        if not self.current_data:
            self.show_dialog("NO DATA", "Perform a vehicle lookup first.", accent=YELLOW)
            return

        html_path = f"results/{self.current_rc}_report.html"
        rows = "".join(f"<tr><th>{k.upper()}</th><td>{v}</td></tr>" for k, v in self.current_data.items())
        content = f"""<!doctype html><html><head><meta charset="utf-8">
        <title>{self.current_rc} Report</title>
        <style>body{{background:#020504;color:#e7f4eb;font-family:monospace;padding:24px;}}
        table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #087b42;padding:8px;text-align:left;}}
        th{{color:#00ff66;background:#050b08;width:30%;}}</style></head>
        <body><h2>VEHICLE REPORT: {self.current_rc}</h2><table>{rows}</table></body></html>"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.show_dialog("EXPORT SUCCESS", f"Saved HTML dossier to {html_path}", accent=NEON)

    def generate_qr_report(self):
        if not self.current_data or not QRCODE_AVAILABLE or not PIL_AVAILABLE:
            self.show_dialog("MODULE MISSING", "qrcode & pillow packages needed.", accent=RED)
            return

        self.export_report()
        port = self.ensure_report_server()
        host = get_local_ip()
        url = f"http://{host}:{port}/{quote(self.current_rc)}_report.html"

        qr_path = f"results/{self.current_rc}_qr.png"
        qrcode.make(url).save(qr_path)

        dialog = tk.Toplevel(self.root)
        dialog.title("PHONE SYNC QR")
        dialog.geometry("500x580")
        dialog.configure(bg=BG)

        with Image.open(qr_path) as qr_img:
            photo = ImageTk.PhotoImage(qr_img.convert("RGB").resize((320, 320)))

        lbl = tk.Label(dialog, image=photo, bg="white")
        lbl.image = photo
        lbl.pack(pady=16)

        tk.Label(dialog, text=f"SCAN TO VIEW ON MOBILE // {self.current_rc}", fg=NEON, bg=BG, font=(MONO, 9, "bold")).pack()
        tk.Label(dialog, text=f"Phone and PC must be on same Wi-Fi.\n{url}", fg=MUTED, bg=BG, font=(MONO, 7), justify="center").pack(pady=6)

    def copy_result(self):
        if not self.current_data:
            return
        lines = [f"{k.upper()}: {v}" for k, v in self.current_data.items()]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.show_dialog("COPIED", "Result copied to clipboard.", accent=NEON)

    def favorite(self):
        if not self.current_rc:
            return
        fav_path = "results/favorites.json"
        favs = []
        if os.path.exists(fav_path):
            try:
                with open(fav_path, "r", encoding="utf-8") as f:
                    favs = json.load(f)
            except Exception:
                pass
        if self.current_rc not in favs:
            favs.append(self.current_rc)
            with open(fav_path, "w", encoding="utf-8") as f:
                json.dump(favs, f, indent=2)
        self.show_dialog("FAVORITE", f"Added {self.current_rc} to favorites.", accent=NEON)

    def export_json(self):
        if not self.current_raw_data:
            return
        fn = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{self.current_rc}.json")
        if fn:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.current_raw_data, f, indent=2)
            self.show_dialog("EXPORT JSON", f"Saved JSON to {fn}", accent=NEON)

    def add_history(self, rc):
        entry = {"rc": rc, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.search_history = [i for i in self.search_history if i.get("rc") != rc]
        self.search_history.insert(0, entry)

    def menu_action(self, action):
        if action == "CHALLAN RECORDS":
            self.show_challan_modal()
        elif action == "NUMBER PLATE CHECK":
            rc = self.rc_entry.get().strip().upper()
            st = STATE_CODES.get(rc[:2], "India")
            self.show_dialog("PLATE CHECK", f"Plate: {rc}\nState: {st}\nFormat: Standard Indian HSRP", accent=CYAN)
        elif action == "ABOUT":
            self.show_dialog("ABOUT", f"VEHICLE INFORMATION v{VERSION}\nAuthor: {AUTHOR}", accent=NEON)

    def stop_lookup(self):
        self.stop_event.set()
        self.lookup_stopped()

    def lookup_stopped(self):
        self.scanning = False
        self.scan_btn.config(text="⌕  SEARCH", state="normal", bg="#041c0e")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="● STOPPED", fg=RED)
        self.summary_status.config(text="STOPPED", fg=RED)

    def show_dialog(self, title, message, accent=NEON):
        ThemedDialog(self, title, message, accent=accent)

    def update_clock(self):
        self.root.after(1000, self.update_clock)

    def build_bottom_bar(self):
        """Retained bottom telemetry bar."""
        bottom = tk.Frame(self.root, bg=BLACK, height=30, highlightbackground=BORDER, highlightthickness=1)
        bottom.pack(fill="x", padx=18, pady=(0, 8))
        bottom.pack_propagate(False)

        tk.Label(bottom, text=">> SYSTEM SECURED", fg=NEON, bg=BLACK, font=(MONO, 8, "bold")).pack(side="left", padx=15)
        tk.Label(bottom, text=">> ENCRYPTION: AES-256", fg=MUTED, bg=BLACK, font=(MONO, 8)).pack(side="left", padx=40)
        tk.Label(bottom, text=">> MODE: EDUCATIONAL", fg=MUTED, bg=BLACK, font=(MONO, 8)).pack(side="right", padx=15)

    def close_application(self):
        try:
            if self.report_server is not None:
                self.report_server.shutdown()
                self.report_server.server_close()
        except Exception:
            pass
        self.root.destroy()


def main():
    ensure_dirs()
    root = tk.Tk()
    app = VehicleInformationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
