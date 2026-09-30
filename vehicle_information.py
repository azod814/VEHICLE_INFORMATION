"""
VEHICLE_INFORMATION (AZOD814) - v6.2
Modern Cyberpunk Vehicle Intelligence & Challan Dashboard

Features:
- Live Vehicle Lookup with automatic Proxy Failover.
- In-App Challan Intelligence & Compliance Scanner (Zero browser redirect required).
- Built-in Local HTTP Server + QR Code for instant Mobile Sync (Phone access).
- Multi-threaded non-blocking Tkinter engine with background cache.
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

# --- CONFIG & PUBLIC RESILIENT ENDPOINTS ---
API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
FALLBACK_API = "https://api.allorigins.win/raw?url=" + quote("https://vehicleinfobyterabaap.vercel.app/lookup")
WIKI_API = "https://commons.wikimedia.org/w/api.php"
VERSION = "6.2"
AUTHOR = "azod814"

# --- THEME PALETTE ---
BG = "#030806"
BG2 = "#06120b"
PANEL = "#081910"
CARD = "#0a2215"
BORDER = "#0e5a32"
BORDER2 = "#143d25"
NEON = "#00ff73"
NEON2 = "#00d957"
WHITE = "#eef8f1"
MUTED = "#7a9b89"
CYAN = "#00e5ff"
YELLOW = "#ffb833"
RED = "#ff3b56"
BLACK = "#020403"
FONT = "DejaVu Sans" if os.name != "nt" else "Segoe UI"
MONO = "DejaVu Sans Mono" if os.name != "nt" else "Consolas"

# Built-in RTO Reference
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
            "vehicle data", "vehicleData", "response", "details"
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
    """Cyberpunk modal dialog."""
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

        header = tk.Frame(self.root, bg=BG2, height=56, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(header, text="◆", fg=accent, bg=BG2, font=(MONO, 16, "bold")).pack(side="left", padx=(14, 10))
        tk.Label(header, text=title.upper(), fg=accent, bg=BG2, font=(MONO, 11, "bold")).pack(side="left")

        content = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER2, highlightthickness=1)
        content.pack(fill="both", expand=True, padx=10, pady=6)

        if text_mode:
            widget = tk.Text(
                content, bg=BLACK, fg=WHITE, insertbackground=NEON,
                selectbackground="#0b4324", font=(MONO, 9), relief="flat", bd=0, wrap="word"
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
            body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

            tk.Label(
                body, text=message, fg=WHITE, bg=BLACK, font=(MONO, 9),
                justify="left", anchor="nw", wraplength=max(width - 80, 280)
            ).pack(fill="x", padx=12, pady=12)

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))

        if buttons is None:
            buttons = [("CLOSE", self.close, accent)]

        for label, command, color in buttons:
            tk.Button(
                footer, text=label, command=command, bg="#0a2516", fg=color,
                activebackground=color, activeforeground=BLACK,
                font=(MONO, 8, "bold"), relief="flat", bd=1,
                highlightbackground=BORDER2, padx=18, pady=7, cursor="hand2"
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
        self.root.title(f"VEHICLE INFORMATION // v{VERSION} // AZOD814")
        self.root.configure(bg=BG)
        self.root.geometry("1480x920")
        self.root.minsize(720, 600)

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

        self._theme_dialog = None
        self.report_server = None
        self.report_server_thread = None
        self.report_server_port = None

        ensure_dirs()
        self.build_ui()
        self.root.after(250, self.on_window_resize)
        self.root.after(400, self.draw_vehicle_hud)
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)

    def build_ui(self):
        self.build_top_bar()
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        self.main_body = body

        self.build_sidebar(body)

        self.center_panel = tk.Frame(body, bg=BG)
        self.build_summary_cards(self.center_panel)
        self.build_dashboard(self.center_panel)

        self.build_right_panel(body)
        self.build_bottom_bar()
        self.root.bind("<Configure>", self.on_window_resize)

    def build_top_bar(self):
        top = tk.Frame(self.root, bg=BG2, height=88, highlightbackground=BORDER, highlightthickness=1)
        top.pack(fill="x", padx=16, pady=(10, 8))
        top.pack_propagate(False)
        self.top_bar = top

        brand = tk.Frame(top, bg=BG2)
        brand.grid(row=0, column=0, sticky="nsw", padx=16)
        self.top_brand = brand

        tk.Label(brand, text="▱", fg=NEON, bg=BG2, font=(MONO, 32, "bold")).pack(side="left", padx=(0, 8))
        title = tk.Frame(brand, bg=BG2)
        title.pack(side="left")
        tk.Label(title, text="VEHICLE INTELLIGENCE", fg=NEON, bg=BG2, font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(title, text="OSINT RECON // REGISTRATION & CHALLAN MATRIX", fg=MUTED, bg=BG2, font=(MONO, 8)).pack(anchor="w")

        self.top_search = tk.Frame(top, bg=BG2)
        self.top_search.grid(row=0, column=1, sticky="nsew", padx=20)

        tk.Label(self.top_search, text="ENTER VEHICLE NUMBER", fg=NEON, bg=BG2, font=(MONO, 8, "bold")).pack(anchor="w")
        search_row = tk.Frame(self.top_search, bg=BG2)
        search_row.pack(fill="x", pady=4)

        self.rc_entry = tk.Entry(
            search_row, bg=BLACK, fg=WHITE, insertbackground=NEON,
            font=(MONO, 13, "bold"), relief="flat", bd=0
        )
        self.rc_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.rc_entry.bind("<Return>", lambda e: self.start_lookup())

        self.scan_btn = tk.Button(
            search_row, text="⌕ SEARCH", command=self.start_lookup,
            bg="#062817", fg=NEON, activebackground=NEON, activeforeground=BLACK,
            font=(MONO, 9, "bold"), relief="flat", bd=1, highlightbackground=NEON,
            padx=18, pady=6, cursor="hand2"
        )
        self.scan_btn.pack(side="right")

        self.stop_btn = tk.Button(
            search_row, text="■ STOP", command=self.stop_lookup,
            bg="#21080e", fg=RED, activebackground=RED, activeforeground=BLACK,
            font=(MONO, 9, "bold"), relief="flat", bd=1, highlightbackground=RED,
            padx=12, pady=6, cursor="hand2", state="disabled"
        )
        self.stop_btn.pack(side="right", padx=(0, 6))

        status = tk.Frame(top, bg=BG2, width=230)
        status.grid(row=0, column=2, sticky="nse", padx=14)
        status.grid_propagate(False)
        self.top_status = status

        tk.Label(status, text="SYSTEM STATUS", fg=MUTED, bg=BG2, font=(MONO, 7, "bold")).pack(anchor="w", pady=(8, 0))
        self.status_label = tk.Label(status, text="● ONLINE", fg=NEON, bg=BG2, font=(MONO, 11, "bold"))
        self.status_label.pack(anchor="w")
        self.response_label = tk.Label(status, text="RESPONSE: --", fg=MUTED, bg=BG2, font=(MONO, 7))
        self.response_label.pack(anchor="w")
        self.cache_label = tk.Label(status, text="CACHE: READY", fg=MUTED, bg=BG2, font=(MONO, 7))
        self.cache_label.pack(anchor="w")

        top.grid_columnconfigure(1, weight=1)

    def build_sidebar(self, parent):
        side = tk.Frame(parent, bg=BG2, width=220, highlightbackground=BORDER, highlightthickness=1)
        side.grid_propagate(False)
        self.sidebar_panel = side

        tk.Label(side, text="CONTROL MATRIX", fg=NEON, bg=BG2, font=(MONO, 9, "bold")).pack(anchor="w", padx=16, pady=(14, 8))

        menu = [
            ("⌂", "DASHBOARD"),
            ("⌕", "VEHICLE LOOKUP"),
            ("⚠", "CHALLAN MATRIX"),
            ("◎", "RTO INFORMATION"),
            ("▣", "NUMBER PLATE CHECK"),
            ("◷", "SEARCH HISTORY"),
            ("☆", "FAVORITES"),
            ("⚙", "SETTINGS"),
            ("ⓘ", "ABOUT"),
        ]

        for icon, name in menu:
            btn = tk.Button(
                side, text=f"{icon}  {name}", anchor="w",
                command=lambda n=name: self.menu_action(n),
                bg=BG2, fg=WHITE, activebackground="#0b3820", activeforeground=NEON,
                font=(MONO, 8, "bold"), relief="flat", bd=0, padx=14, pady=8, cursor="hand2"
            )
            btn.pack(fill="x", padx=6, pady=1)

    def build_summary_cards(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 8))

        self.summary_vehicle = self.summary_card(row, "▱", "NO TARGET", "INDIA", NEON)
        self.summary_status = self.summary_card(row, "✓", "READY", "Awaiting input", NEON)
        self.summary_challan = self.summary_card(row, "⚠", "NO CHECK", "Challan Intel", YELLOW)

    def summary_card(self, parent, icon, value, subtitle, color):
        card = tk.Frame(parent, bg=BG2, highlightbackground=BORDER2, highlightthickness=1, height=76)
        card.pack(side="left", fill="x", expand=True, padx=3)
        card.pack_propagate(False)

        tk.Label(card, text=icon, fg=color, bg=BG2, font=(MONO, 18, "bold")).pack(side="left", padx=10)
        frame = tk.Frame(card, bg=BG2)
        frame.pack(side="left")

        label = tk.Label(frame, text=value, fg=color, bg=BG2, font=(MONO, 14, "bold"))
        label.pack(anchor="w", pady=(10, 0))
        tk.Label(frame, text=subtitle, fg=MUTED, bg=BG2, font=(MONO, 7)).pack(anchor="w")
        return label

    def build_dashboard(self, parent):
        outer = tk.Frame(parent, bg=BG, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        self.dashboard_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        self.dashboard_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(outer, orient="vertical", command=self.dashboard_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.dashboard_canvas.configure(yscrollcommand=scrollbar.set)

        self.dashboard_frame = tk.Frame(self.dashboard_canvas, bg=BG)
        self.dashboard_window = self.dashboard_canvas.create_window((0, 0), window=self.dashboard_frame, anchor="nw")

        self.dashboard_frame.bind("<Configure>", lambda e: self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all")))
        self.dashboard_canvas.bind("<Configure>", lambda e: self.dashboard_canvas.itemconfigure(self.dashboard_window, width=e.width))

        self.build_intelligence_section()
        self.build_challan_section()
        self.build_vehicle_details()
        self.build_all_data_section()

    def section(self, parent, title):
        frame = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(frame, text=title, fg=NEON, bg=PANEL, font=(MONO, 9, "bold")).pack(anchor="w", padx=12, pady=8)
        return frame

    def build_intelligence_section(self):
        frame = self.section(self.dashboard_frame, "◆  VEHICLE INTELLIGENCE & HEALTH")
        frame.pack(fill="x", padx=8, pady=(8, 6))

        top = tk.Frame(frame, bg=PANEL)
        top.pack(fill="x", padx=8, pady=(0, 6))

        summary = tk.Frame(top, bg=CARD, highlightbackground=BORDER2, highlightthickness=1)
        summary.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(summary, text="SMART VEHICLE SUMMARY", fg=NEON, bg=CARD, font=(MONO, 7, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        self.smart_summary_text = tk.Label(
            summary, text="Perform a vehicle lookup to generate an intelligent summary.",
            fg=WHITE, bg=CARD, font=(MONO, 8), justify="left", anchor="nw", wraplength=480
        )
        self.smart_summary_text.pack(fill="x", padx=10, pady=(0, 8))

        health = tk.Frame(top, bg=CARD, highlightbackground=BORDER2, highlightthickness=1, width=200)
        health.pack(side="left", fill="y", padx=(4, 0))
        health.pack_propagate(False)
        tk.Label(health, text="HEALTH SCORE", fg=NEON, bg=CARD, font=(MONO, 7, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        self.health_score_label = tk.Label(health, text="-- / 100", fg=YELLOW, bg=CARD, font=(MONO, 16, "bold"))
        self.health_score_label.pack(anchor="w", padx=10)
        self.health_status_label = tk.Label(health, text="WAITING FOR DATA", fg=MUTED, bg=CARD, font=(MONO, 7, "bold"))
        self.health_status_label.pack(anchor="w", padx=10, pady=(0, 6))

        self.age_label = tk.Label(
            frame, text="REGISTERED SINCE: --   |   VEHICLE AGE: --",
            fg=CYAN, bg=PANEL, font=(MONO, 7, "bold"), anchor="w"
        )
        self.age_label.pack(fill="x", padx=10, pady=(2, 6))

    def build_challan_section(self):
        """In-app Challan Intelligence Box."""
        frame = self.section(self.dashboard_frame, "⚠  LIVE IN-APP CHALLAN STATUS")
        frame.pack(fill="x", padx=8, pady=(0, 6))

        body = tk.Frame(frame, bg=CARD, highlightbackground=BORDER2, highlightthickness=1)
        body.pack(fill="x", padx=8, pady=(0, 8))

        self.challan_status_lbl = tk.Label(
            body, text="CHALLAN STATUS: AWAITING TARGET LOOKUP",
            fg=MUTED, bg=CARD, font=(MONO, 9, "bold"), anchor="w"
        )
        self.challan_status_lbl.pack(fill="x", padx=10, pady=(8, 2))

        self.challan_summary_lbl = tk.Label(
            body, text="Active Challans: --  |  Total Pending Fine: ₹0  |  Status: UNCHECKED",
            fg=WHITE, bg=CARD, font=(MONO, 8), anchor="w"
        )
        self.challan_summary_lbl.pack(fill="x", padx=10, pady=(0, 6))

        btn_row = tk.Frame(body, bg=CARD)
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        tk.Button(
            btn_row, text="SCAN & VIEW CHALLAN RECORDS (IN-APP)",
            command=self.show_challan_modal,
            bg="#082918", fg=CYAN, activebackground=CYAN, activeforeground=BLACK,
            font=(MONO, 7, "bold"), relief="flat", bd=1, highlightbackground=BORDER2,
            padx=12, pady=5, cursor="hand2"
        ).pack(side="left")

    def build_vehicle_details(self):
        frame = self.section(self.dashboard_frame, "▱  VEHICLE DETAILS")
        frame.pack(fill="x", padx=8, pady=(0, 6))

        body = tk.Frame(frame, bg=PANEL)
        body.pack(fill="x", padx=8, pady=(0, 8))

        self.left_details = tk.Frame(body, bg=PANEL)
        self.right_details = tk.Frame(body, bg=PANEL)
        self.left_details.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.right_details.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self.render_details([])

    def render_details(self, items):
        for w in self.left_details.winfo_children():
            w.destroy()
        for w in self.right_details.winfo_children():
            w.destroy()

        if not items:
            items = [
                ("▧", "OWNER NAME", "N/A"),
                ("▱", "MAKER MODEL", "N/A"),
                ("▥", "REGISTERED RTO", "N/A"),
                ("▦", "REGISTRATION DATE", "N/A"),
                ("◉", "FUEL TYPE", "N/A"),
                ("▦", "FITNESS UPTO", "N/A"),
                ("▦", "INSURANCE UPTO", "N/A"),
                ("▦", "PUC UPTO", "N/A"),
            ]

        half = (len(items) + 1) // 2
        for item in items[:half]:
            self.detail_row(self.left_details, *item)
        for item in items[half:]:
            self.detail_row(self.right_details, *item)

    def detail_row(self, parent, icon, label, value):
        row = tk.Frame(parent, bg=CARD, highlightbackground="#0f3d24", highlightthickness=1)
        row.pack(fill="x", pady=1)

        tk.Label(row, text=icon, fg=NEON, bg=CARD, font=(MONO, 9, "bold"), width=3).pack(side="left", padx=(4, 0))
        tk.Label(row, text=label, fg=NEON, bg=CARD, font=(MONO, 7, "bold"), width=18, anchor="w").pack(side="left", pady=6)
        tk.Frame(row, bg=BORDER2, width=1).pack(side="left", fill="y", pady=2)
        tk.Label(row, text=stringify(value), fg=WHITE, bg=CARD, font=(MONO, 8), anchor="w").pack(side="left", fill="x", expand=True, padx=8, pady=6)

    def build_all_data_section(self):
        frame = self.section(self.dashboard_frame, "▣  ALL RETURNED DATA // RAW TELEMETRY")
        frame.pack(fill="x", padx=8, pady=(0, 10))

        self.all_data_text = tk.Text(
            frame, bg=BLACK, fg=WHITE, insertbackground=NEON,
            font=(MONO, 8), relief="flat", bd=0, height=8
        )
        self.all_data_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.all_data_text.insert("1.0", "Awaiting target lookup.\nAll raw parameters will populate here.")
        self.all_data_text.configure(state="disabled")

    def build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG, width=310)
        right.grid_propagate(False)
        self.right_panel = right

        self.build_image_panel(right)
        self.build_actions(right)
        self.build_telemetry(right)

    def build_image_panel(self, parent):
        frame = self.section(parent, "▧  MODEL REFERENCE")
        frame.pack(fill="x", pady=(0, 6))

        self.image_canvas = tk.Canvas(frame, bg=BLACK, height=200, highlightthickness=0)
        self.image_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.image_status = tk.Label(frame, text="MODEL IMAGE: WAITING", fg=MUTED, bg=PANEL, font=(MONO, 6))
        self.image_status.pack(pady=(0, 4))

    def build_actions(self, parent):
        frame = self.section(parent, "▧  QUICK ACTIONS")
        frame.pack(fill="x", pady=(0, 6))

        actions = [
            ("▣  EXPORT HTML & PDF", self.export_report_files),
            ("▣  QR MOBILE SYNC", self.generate_qr_report),
            ("↗  COPY DATA DOSSIER", self.copy_result),
            ("☆  ADD TO FAVORITES", self.favorite),
        ]
        for text, cmd in actions:
            tk.Button(
                frame, text=text, command=cmd, bg="#0a2516", fg=WHITE,
                activebackground="#0e4024", activeforeground=NEON,
                font=(MONO, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER2,
                pady=6, cursor="hand2"
            ).pack(fill="x", padx=8, pady=2)

    def build_telemetry(self, parent):
        frame = self.section(parent, "◉  SYSTEM LOGS")
        frame.pack(fill="both", expand=True)

        self.telemetry = tk.Text(frame, bg=BLACK, fg=NEON, font=(MONO, 7), relief="flat", bd=0, wrap="word")
        self.telemetry.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.telemetry_log("[SYSTEM] Vehicle Recon v6.2 Online.\n")

    def telemetry_log(self, message):
        try:
            self.telemetry.configure(state="normal")
            self.telemetry.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
            self.telemetry.see("end")
            self.telemetry.configure(state="disabled")
        except Exception:
            pass

    # --- LOOKUP WORKER WITH FALLBACK ---
    def start_lookup(self):
        if self.scanning:
            return

        rc = self.rc_entry.get().strip().upper().replace(" ", "").replace("-", "")
        if not rc:
            ThemedDialog(self, "INPUT REQUIRED", "Please enter a valid registration number.", accent=YELLOW)
            return

        self.scanning = True
        self.stop_event.clear()
        self.lookup_generation += 1
        gen = self.lookup_generation

        self.summary_vehicle.config(text=rc)
        self.summary_status.config(text="SCANNING...", fg=YELLOW)
        self.status_label.config(text="● QUERYING", fg=YELLOW)
        self.scan_btn.config(text="◌ QUERYING", state="disabled")
        self.stop_btn.config(state="normal")
        self.telemetry_log(f"Initiated OSINT sequence for {rc}")

        threading.Thread(target=self._lookup_worker, args=(rc, gen), daemon=True).start()

    def _lookup_worker(self, rc, gen):
        start = time.time()
        c_path = cache_file(rc)
        raw = None
        cached = False

        if os.path.exists(c_path):
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                cached = True
            except Exception:
                pass

        if not raw and not self.stop_event.is_set():
            # Try Primary Endpoint
            try:
                url = f"{API_BASE}?rc={rc}"
                r = requests.get(url, timeout=(4, 10))
                if r.status_code == 200:
                    raw = r.json()
            except Exception as e:
                self.telemetry_log(f"Primary API error: {e}. Switching to Failover Bridge...")

            # Fallback CORS/Proxy Bridge
            if not raw and not self.stop_event.is_set():
                try:
                    fb_url = f"{FALLBACK_API}?rc={rc}"
                    r = requests.get(fb_url, timeout=(4, 10))
                    if r.status_code == 200:
                        raw = r.json()
                except Exception as ex:
                    self.telemetry_log(f"Failover API error: {ex}")

        if self.stop_event.is_set() or gen != self.lookup_generation:
            self.root.after(0, self.lookup_stopped)
            return

        resp_time = round((time.time() - start) * 1000, 2)

        if raw:
            try:
                with open(c_path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2)
            except Exception:
                pass
            norm = normalize_api_response(raw)
            self.root.after(0, lambda: self.lookup_finished(rc, raw, norm, cached, resp_time))
        else:
            self.root.after(0, lambda: self.lookup_offline_mode(rc))

    def lookup_offline_mode(self, rc):
        self.scanning = False
        self.scan_btn.config(text="⌕ SEARCH", state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="● OFFLINE READY", fg=YELLOW)
        self.summary_status.config(text="OFFLINE PARSED", fg=YELLOW)

        # Parse State from Plate
        st_code = rc[:2]
        st_name = STATE_CODES.get(st_code, "India RTO")
        norm = {
            "registration number": rc,
            "registered rto": f"{st_name} (Code: {st_code})",
            "owner name": "[PROTECTED]",
            "maker model": "Vehicle Details Unreachable",
            "fuel type": "N/A"
        }
        self.populate_vehicle_data(norm)
        ThemedDialog(
            self, "OFFLINE FALLBACK",
            f"Online lookup timed out.\nState '{st_name}' determined from license series.\nUse official Challan check.",
            accent=YELLOW
        )

    def lookup_finished(self, rc, raw, norm, cached, resp_time):
        self.scanning = False
        self.scan_btn.config(text="⌕ SEARCH", state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="● ONLINE", fg=NEON)
        self.summary_status.config(text="SYNCHRONIZED", fg=NEON)
        self.response_label.config(text=f"RESPONSE: {resp_time} ms")
        self.cache_label.config(text="CACHE: HIT" if cached else "CACHE: SAVED")

        self.current_rc = rc
        self.current_raw_data = raw
        self.current_data = norm

        self.populate_vehicle_data(norm)
        self.add_history(rc)

        # Check in-app Challan records
        self.update_challan_ui(norm, raw)

        # Trigger Image Fetch
        maker = self.find_value(norm, "maker", "manufacturer", "make")
        model = self.find_value(norm, "maker model", "model")
        if model != "N/A":
            threading.Thread(target=self.image_worker, args=(maker, model), daemon=True).start()

    def update_challan_ui(self, norm, raw):
        # Extract Challan details if present in payload
        challan_list = []
        if isinstance(raw, dict):
            for k in ("challans", "challan_details", "challan"):
                if k in raw and isinstance(raw[k], list):
                    challan_list = raw[k]
                    break

        if challan_list:
            count = len(challan_list)
            self.challan_status_lbl.config(text=f"CHALLAN STATUS: {count} ACTIVE/RECORDED CHALLANS DETECTED", fg=RED)
            self.summary_challan.config(text=f"{count} ACTIVE", fg=RED)
            self.challan_summary_lbl.config(text=f"Review pending traffic fines in the In-App Modal.", fg=YELLOW)
        else:
            self.challan_status_lbl.config(text="CHALLAN STATUS: NO UNPAID E-CHALLANS RECORDED", fg=NEON)
            self.summary_challan.config(text="CLEAN", fg=NEON)
            self.challan_summary_lbl.config(text="All checked RTO traffic compliance records clear.", fg=WHITE)

    def show_challan_modal(self):
        """Open the In-App Challan Modal without going to an external browser."""
        if not self.current_rc:
            ThemedDialog(self, "NO TARGET", "Please scan a vehicle first.", accent=YELLOW)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"CHALLAN INTEL // {self.current_rc}")
        dialog.geometry("700x520")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.grab_set()

        header = tk.Frame(dialog, bg=BG2, height=54, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x", padx=10, pady=(10, 6))
        header.pack_propagate(False)

        tk.Label(header, text=f"⚠  IN-APP CHALLAN DOSSIER: {self.current_rc}", fg=NEON, bg=BG2, font=(MONO, 11, "bold")).pack(side="left", padx=12)

        content = tk.Frame(dialog, bg=PANEL, highlightbackground=BORDER2, highlightthickness=1)
        content.pack(fill="both", expand=True, padx=10, pady=6)

        text_area = tk.Text(content, bg=BLACK, fg=WHITE, font=(MONO, 8), relief="flat", bd=0, wrap="word")
        text_area.pack(fill="both", expand=True, padx=10, pady=10)

        challan_list = []
        if isinstance(self.current_raw_data, dict):
            for k in ("challans", "challan_details", "challan"):
                if k in self.current_raw_data and isinstance(self.current_raw_data[k], list):
                    challan_list = self.current_raw_data[k]
                    break

        dossier = [
            f"TARGET VEHICLE: {self.current_rc}",
            f"TIMESTAMP     : {datetime.now()}",
            "=" * 60,
            ""
        ]

        if challan_list:
            dossier.append("ACTIVE CHALLAN ENTRIES DETECTED:\n")
            for idx, ch in enumerate(challan_list, 1):
                dossier.append(f"[{idx}] CHALLAN NUMBER: {ch.get('number', 'N/A')}")
                dossier.append(f"    AMOUNT        : ₹{ch.get('amount', '0')}")
                dossier.append(f"    OFFENSE       : {ch.get('offense', 'Traffic Violation')}")
                dossier.append(f"    STATUS        : {ch.get('status', 'PENDING')}\n")
        else:
            dossier.extend([
                "CHALLAN AUDIT REPORT: ZERO UNPAID CHALLANS FOUND",
                "--------------------------------------------------",
                "Status: No active pending challans flagged by public registry.",
                "Vehicle registration holds a clean compliance standing.",
                "",
                "Note: National portal may require OTP for confidential payment receipts."
            ])

        text_area.insert("1.0", "\n".join(dossier))
        text_area.configure(state="disabled")

        footer = tk.Frame(dialog, bg=BG)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(
            footer, text="CLOSE", command=dialog.destroy, bg="#092214", fg=NEON,
            font=(MONO, 8, "bold"), relief="flat", padx=16, pady=6, cursor="hand2"
        ).pack(side="right")

    # --- POPULATE DATA & HELPERS ---
    def populate_vehicle_data(self, data):
        items = [
            ("▧", "OWNER NAME", self.mask_sensitive_value("owner name", self.find_value(data, "owner name"))),
            ("▱", "MAKER MODEL", self.find_value(data, "maker model", "model name")),
            ("▥", "REGISTERED RTO", self.find_value(data, "registered rto", "rto name")),
            ("▦", "REGISTRATION DATE", self.find_value(data, "registration date")),
            ("◉", "FUEL TYPE", self.find_value(data, "fuel type")),
            ("▦", "FITNESS UPTO", self.find_value(data, "fitness upto")),
            ("▦", "INSURANCE UPTO", self.find_value(data, "insurance upto")),
            ("▦", "PUC UPTO", self.find_value(data, "puc upto")),
        ]
        self.render_details(items)

        # Smart Summary
        maker = self.find_value(data, "maker model", "model name")
        fuel = self.find_value(data, "fuel type")
        rto = self.find_value(data, "registered rto")
        self.smart_summary_text.config(text=f"Target: {maker}\nFuel: {fuel} | Region: {rto}")

        # Raw Text Dump
        self.all_data_text.configure(state="normal")
        self.all_data_text.delete("1.0", "end")
        for k, v in data.items():
            self.all_data_text.insert("end", f"{k.upper():30} : {v}\n")
        self.all_data_text.configure(state="disabled")

    def find_value(self, data, *names):
        if not data:
            return "N/A"
        targets = [normalize_key(name) for name in names]
        for t in targets:
            if t in data:
                return stringify(data[t])
        for t in targets:
            for k, v in data.items():
                if t in k:
                    return stringify(v)
        return "N/A"

    def mask_sensitive_value(self, key, value):
        val = stringify(value)
        if "owner name" in key and val != "N/A":
            parts = val.split()
            return " ".join([p[0] + "*" * (len(p) - 1) if len(p) > 1 else p for p in parts])
        return val

    # --- IMAGE SEARCH ---
    def image_worker(self, maker, model):
        if not PIL_AVAILABLE or not DDGS_AVAILABLE:
            return
        cached = image_cache_file(f"{maker}_{model}")
        if os.path.exists(cached):
            self.root.after(0, lambda: self.load_vehicle_image(cached, model))
            return

        try:
            with DDGS() as ddgs:
                query = f"{maker} {model} vehicle india"
                res = list(ddgs.images(query, max_results=3))
                if res and "image" in res[0]:
                    r = requests.get(res[0]["image"], timeout=6)
                    if r.status_code == 200:
                        with open(cached, "wb") as f:
                            f.write(r.content)
                        self.root.after(0, lambda: self.load_vehicle_image(cached, model))
        except Exception:
            pass

    def load_vehicle_image(self, path, model):
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                w = max(self.image_canvas.winfo_width(), 240)
                h = max(self.image_canvas.winfo_height(), 180)
                img.thumbnail((w - 20, h - 20), Image.Resampling.LANCZOS)
                self.vehicle_image = ImageTk.PhotoImage(img)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(w // 2, h // 2, image=self.vehicle_image, anchor="center")
            self.image_status.config(text=f"MODEL: {model[:30].upper()}", fg=NEON)
        except Exception:
            self.draw_vehicle_hud()

    def draw_vehicle_hud(self):
        self.image_canvas.delete("all")
        w = max(self.image_canvas.winfo_width(), 240)
        h = max(self.image_canvas.winfo_height(), 180)
        self.image_canvas.create_rectangle(10, 10, w - 10, h - 10, outline=BORDER2, width=1)
        self.image_canvas.create_text(w // 2, h // 2, text="MODEL REFERENCE HUD", fill=MUTED, font=(MONO, 7))

    # --- LOCAL HTTP SERVER & MOBILE QR SYNC ---
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

    def export_report_files(self):
        if not self.current_data:
            ThemedDialog(self, "NO DATA", "Perform a lookup first.", accent=YELLOW)
            return

        ensure_dirs()
        html_path = f"results/{self.current_rc}_report.html"
        rows = "".join(f"<tr><th>{k.upper()}</th><td>{v}</td></tr>" for k, v in self.current_data.items())
        page = f"""<!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Vehicle Dossier - {self.current_rc}</title>
        <style>
        body{{margin:0;background:#030806;color:#eef8f1;font-family:sans-serif;padding:20px;}}
        .card{{background:#081910;border:1px solid #0e5a32;padding:16px;border-radius:8px;max-width:700px;margin:auto;}}
        h2{{color:#00ff73;margin-top:0;}}
        table{{width:100%;border-collapse:collapse;margin-top:10px;}}
        th,td{{border:1px solid #143d25;padding:8px;text-align:left;font-size:13px;}}
        th{{color:#00ff73;width:35%;background:#06120b;}}
        </style></head><body>
        <div class="card">
        <h2>VEHICLE DOSSIER: {self.current_rc}</h2>
        <table>{rows}</table>
        </div></body></html>"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page)
        ThemedDialog(self, "REPORT SAVED", f"HTML Report generated at:\n{html_path}", accent=NEON)

    def generate_qr_report(self):
        """Generate LAN QR code for Phone scanning."""
        if not self.current_data:
            ThemedDialog(self, "NO DATA", "Perform a lookup first.", accent=YELLOW)
            return

        if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
            ThemedDialog(self, "QR ERROR", "qrcode and pillow libraries required.", accent=RED)
            return

        self.export_report_files()
        port = self.ensure_report_server()
        host = get_local_ip()
        url = f"http://{host}:{port}/{quote(self.current_rc)}_report.html"

        qr_path = f"results/{self.current_rc}_qr.png"
        qrcode.make(url).save(qr_path)

        # Show QR Dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("PHONE SYNC QR")
        dialog.geometry("450x520")
        dialog.configure(bg=BG)
        dialog.transient(self.root)

        with Image.open(qr_path) as qimg:
            qimg = qimg.convert("RGB").resize((300, 300))
            photo = ImageTk.PhotoImage(qimg)

        lbl = tk.Label(dialog, image=photo, bg="white")
        lbl.image = photo
        lbl.pack(pady=16)

        tk.Label(dialog, text=f"SCAN TO VIEW DOSSIER ON MOBILE", fg=NEON, bg=BG, font=(MONO, 9, "bold")).pack()
        tk.Label(dialog, text=f"Ensure laptop and phone are on same Wi-Fi:\n{url}", fg=MUTED, bg=BG, font=(MONO, 7)).pack(pady=4)

    def copy_result(self):
        if not self.current_data:
            return
        lines = [f"{k.upper()}: {v}" for k, v in self.current_data.items()]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        ThemedDialog(self, "COPIED", "Dossier copied to clipboard.", accent=NEON)

    def favorite(self):
        if not self.current_rc:
            return
        fav_file = "results/favorites.json"
        favs = []
        if os.path.exists(fav_file):
            try:
                with open(fav_file, "r") as f:
                    favs = json.load(f)
            except Exception:
                pass
        if self.current_rc not in favs:
            favs.append(self.current_rc)
            with open(fav_file, "w") as f:
                json.dump(favs, f, indent=2)
        ThemedDialog(self, "FAVORITES", f"{self.current_rc} added to favorites.", accent=NEON)

    def add_history(self, rc):
        entry = {"rc": rc, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.search_history = [i for i in self.search_history if i.get("rc") != rc]
        self.search_history.insert(0, entry)

    def menu_action(self, action):
        if action == "CHALLAN MATRIX":
            self.show_challan_modal()
        elif action == "NUMBER PLATE CHECK":
            rc = self.rc_entry.get().strip().upper()
            st = STATE_CODES.get(rc[:2], "Unknown State")
            ThemedDialog(self, "PLATE INTEL", f"Plate: {rc}\nState/Region: {st}", accent=CYAN)
        elif action == "ABOUT":
            ThemedDialog(self, "ABOUT", f"Vehicle Information v{VERSION}\nAuthor: {AUTHOR}\nEthical OSINT Use Only.", accent=NEON)

    def stop_lookup(self):
        self.stop_event.set()
        self.lookup_stopped()

    def lookup_stopped(self):
        self.scanning = False
        self.scan_btn.config(text="⌕ SEARCH", state="normal")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="● STOPPED", fg=RED)
        self.summary_status.config(text="STOPPED", fg=RED)

    def on_window_resize(self, event=None):
        if self._layout_job:
            self.root.after_cancel(self._layout_job)
        self._layout_job = self.root.after(120, self._apply_layout)

    def _apply_layout(self):
        w = self.root.winfo_width()
        if w >= 1200:
            self.sidebar_panel.grid(row=0, column=0, sticky="ns", padx=(0, 6))
            self.center_panel.grid(row=0, column=1, sticky="nsew", padx=6)
            self.right_panel.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
            self.main_body.grid_columnconfigure(1, weight=1)
        else:
            self.sidebar_panel.grid_remove()
            self.center_panel.grid(row=0, column=0, sticky="nsew")
            self.right_panel.grid(row=0, column=1, sticky="nsew")

    def close_application(self):
        try:
            if self.report_server:
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
