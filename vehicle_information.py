"""
VEHICLE_INFORMATION (AZOD814) - v4.0
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
import tkinter as tk
import re
import html
import requests
from datetime import datetime
from urllib.parse import urlencode
from tkinter import filedialog

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


API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
WIKI_API = "https://commons.wikimedia.org/w/api.php"
VERSION = "4.0"
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

        ensure_dirs()
        self.build_ui()
        self.update_clock()

        self.root.after(250, self.on_window_resize)
        self.root.after(400, self.draw_vehicle_hud)

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

        self.build_vehicle_details()
        self.build_additional_information()
        self.build_all_data_section()

    def mouse_scroll(self, event):
        try:
            delta = -3 if event.delta < 0 else 3
            self.dashboard_canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return "break"

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
                    f"{key.upper():34} : {stringify(value)}\n"
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
            args=(rc,),
            daemon=True
        ).start()

    def lookup_worker(self, rc):
        start = time.time()
        cache_hit = False
        raw = None

        try:
            path = cache_file(rc)

            # CACHE-FIRST: show old result instantly if available,
            # then refresh API in the same worker.
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        cached_raw = json.load(file)

                    cache_hit = True

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

            url = API_BASE + "?" + urlencode({"rc": rc})

            response = requests.get(
                url,
                timeout=(4, 12),
                headers={
                    "User-Agent":
                        "VehicleInformationAZOD814/4.0"
                }
            )

            response.raise_for_status()
            raw = response.json()

            try:
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(
                        raw,
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
                    lambda: self.lookup_error(
                        f"API request timed out.\n\n{error}"
                    )
                )

        except requests.exceptions.RequestException as error:
            log(f"API request error for {rc}: {error}")

            if cache_hit:
                self.root.after(
                    0,
                    lambda: self.live_refresh_notice(
                        "LIVE API REFRESH FAILED",
                        "Cached data remains visible. "
                        f"\n\n{error}"
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda: self.lookup_error(
                        f"Network/API error.\n\n{error}"
                    )
                )

        except ValueError as error:
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
                    lambda: self.lookup_error(
                        f"API returned invalid JSON.\n\n{error}"
                    )
                )

        except Exception as error:
            log(f"Unexpected lookup error for {rc}: {error}")

            if cache_hit:
                self.root.after(
                    0,
                    lambda: self.live_refresh_notice(
                        "LIVE REFRESH ERROR",
                        str(error)
                    )
                )
            else:
                self.root.after(
                    0,
                    lambda: self.lookup_error(
                        f"Unexpected lookup error.\n\n"
                        f"{type(error).__name__}: {error}"
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
        self.scanning = False

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

    def populate_vehicle_data(self, data):
        items = [
            ("▧", "ADDRESS", self.find_value(data, "address")),
            ("▥", "CITY", self.find_value(data, "city name", "city")),
            ("▦", "FITNESS UPTO", self.find_value(data, "fitness upto")),
            ("◉", "FUEL TYPE", self.find_value(data, "fuel type")),
            ("♢", "INSURANCE COMPANY", self.find_value(data, "insurance company")),
            ("▣", "INSURANCE NO", self.find_value(data, "insurance no", "insurance number")),
            ("▦", "INSURANCE UPTO", self.find_value(data, "insurance upto")),
            ("▱", "MAKER MODEL", self.find_value(data, "maker model")),
            ("◇", "MODEL NAME", self.find_value(data, "model name")),
            ("♙", "OWNER NAME", self.find_value(data, "owner name")),
            ("▣", "OWNER SERIAL NO", self.find_value(data, "owner serial no", "owner serial number")),
            ("❧", "FUEL NORMS", self.find_value(data, "fuel norms")),
            ("▦", "INSURANCE EXPIRY", self.find_value(data, "insurance expiry")),
            ("⚙", "PUC NO", self.find_value(data, "puc no", "puc number")),
            ("▦", "PUC UPTO", self.find_value(data, "puc upto")),
            ("⌕", "PHONE", self.find_value(data, "phone", "mobile")),
            ("▥", "REGISTERED RTO", self.find_value(data, "registered rto", "rto name")),
            ("▦", "REGISTRATION DATE", self.find_value(data, "registration date")),
            ("₹", "TAX UPTO", self.find_value(data, "tax upto")),
        ]

        # Do not hide any other returned field.
        known = {normalize_key(label) for _, label, _ in items}

        for key, value in data.items():
            if normalize_key(key) not in known:
                items.append(("◇", key.upper(), value))

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

        pattern = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$"

        if re.match(pattern, rc):
            self.show_dialog(
                "NUMBER PLATE CHECK",
                f"TARGET\n{rc}\n\n"
                "FORMAT\nVALID / RECOGNIZED",
                accent=NEON
            )
        else:
            self.show_dialog(
                "NUMBER PLATE CHECK",
                f"TARGET\n{rc or 'EMPTY'}\n\n"
                "FORMAT\nINVALID / UNRECOGNIZED",
                accent=YELLOW
            )

    # ---------------------------- export ----------------------------

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
                    f"{key.upper()}: {stringify(value)}"
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
                        f"{stringify(value)}\n"
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

    def lookup_error(self, error):
        self.scanning = False

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
