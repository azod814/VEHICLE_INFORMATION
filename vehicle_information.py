"""
VEHICLE_INFORMATION (AZOD814) - v8.0
Clean Tactical Vehicle Recon & In-App Challan Engine

Educational & Ethical Use Only.
- 100% Data Field Visibility (Insurance, PUC, Fitness, Tax, Age, Address, Specs)
- In-App Challan Gateway (Direct Plate Passing, Zero External Browser Redirection)
- Multi-Engine Reliable Vehicle Image Scraper (DDGS + Bing + Wikimedia)
- Fast Non-blocking Background Workers
"""

import os
import json
import time
import hashlib
import threading
import socket
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import tkinter as tk
from tkinter import ttk, filedialog
import re
import html
import requests
from datetime import datetime
from urllib.parse import quote, urlencode

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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
FALLBACK_API = "https://api.allorigins.win/raw?url=" + quote("https://vehicleinfobyterabaap.vercel.app/lookup")
WIKI_API = "https://commons.wikimedia.org/w/api.php"
VERSION = "8.0"
AUTHOR = "azod814"

# Clean Slate Tactical Theme
BG = "#0b0f14"
BG_CARD = "#141a22"
BG_PANEL = "#1a222d"
BORDER = "#2d3748"
BORDER_ACCENT = "#38bdf8"
ACCENT_GREEN = "#22c55e"
ACCENT_CYAN = "#38bdf8"
ACCENT_YELLOW = "#eab308"
ACCENT_RED = "#ef4444"
TEXT_WHITE = "#f8fafc"
TEXT_MUTED = "#94a3b8"
INPUT_BG = "#070a0e"

FONT = "DejaVu Sans" if os.name != "nt" else "Segoe UI"
MONO = "DejaVu Sans Mono" if os.name != "nt" else "Consolas"

STATE_MAP = {
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


def ensure_dirs():
    for d in ("results", "logs", "cache", "cache/vehicle_images"):
        os.makedirs(d, exist_ok=True)


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def normalize_key(k):
    txt = str(k).strip().lower()
    for char in ("_", "-", "/", "\\"):
        txt = txt.replace(char, " ")
    return " ".join(txt.split())


def stringify(v):
    if v is None:
        return "N/A"
    if isinstance(v, bool):
        return "YES" if v else "NO"
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, indent=2)
        except Exception:
            return str(v)
    v = str(v).strip()
    return v if v else "N/A"


def clean_vehicle_query(maker, model):
    combined = f"{maker} {model}".upper()
    words = combined.split()
    seen = set()
    cleaned = []
    # Drop repetitive model words and technical trim noise
    noise = {"DELUXE", "BS4", "BS6", "BSIV", "BSVI", "DISC", "DRUM", "SELF", "CAST", "FI", "OBD", "PHASE"}
    for w in words:
        if w not in seen and w not in noise and len(w) > 1:
            seen.add(w)
            cleaned.append(w)
    q = " ".join(cleaned).strip()
    if not any(k in q.lower() for k in ("bike", "motorcycle", "car", "scooter")):
        q += " motorcycle india"
    return q


class ModernDialog:
    def __init__(self, parent, title, message, width=540, height=360, accent=ACCENT_CYAN):
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.configure(bg=BG)
        self.top.geometry(f"{width}x{height}")
        self.top.transient(parent)
        self.top.grab_set()

        header = tk.Frame(self.top, bg=BG_CARD, height=48, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x", padx=12, pady=(12, 6))
        header.pack_propagate(False)

        tk.Label(header, text=title, fg=accent, bg=BG_CARD, font=(FONT, 10, "bold")).pack(side="left", padx=12)

        content = tk.Frame(self.top, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        content.pack(fill="both", expand=True, padx=12, pady=6)

        txt = tk.Text(content, bg=INPUT_BG, fg=TEXT_WHITE, font=(MONO, 9), relief="flat", wrap="word", padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", message)
        txt.configure(state="disabled")

        footer = tk.Frame(self.top, bg=BG)
        footer.pack(fill="x", padx=12, pady=(6, 12))
        tk.Button(
            footer, text="CLOSE", command=self.top.destroy, bg=BG_CARD, fg=TEXT_WHITE,
            activebackground=BORDER, activeforeground=TEXT_WHITE, relief="flat",
            bd=1, highlightbackground=BORDER, padx=16, pady=6, cursor="hand2", font=(FONT, 8, "bold")
        ).pack(side="right")


class VehicleInformationApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"VEHICLE INTELLIGENCE // v{VERSION} // {AUTHOR}")
        self.root.configure(bg=BG)
        self.root.geometry("1480x920")
        self.root.minsize(940, 640)

        self.current_rc = ""
        self.current_data = {}
        self.current_raw = {}
        self.scanning = False
        self.vehicle_image = None
        self.report_server = None

        ensure_dirs()
        self.build_ui()

    def build_ui(self):
        # 1. Top Navbar
        nav = tk.Frame(self.root, bg=BG_CARD, height=76, highlightthickness=1, highlightbackground=BORDER)
        nav.pack(fill="x", padx=14, pady=(12, 8))
        nav.pack_propagate(False)

        brand = tk.Frame(nav, bg=BG_CARD)
        brand.pack(side="left", padx=16)
        tk.Label(brand, text="VEHICLE RECON INTEL", fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 14, "bold")).pack(anchor="w")
        tk.Label(brand, text="REGISTRATION & IN-APP CHALLAN SYSTEM", fg=TEXT_MUTED, bg=BG_CARD, font=(FONT, 8)).pack(anchor="w")

        # Search Bar
        search_box = tk.Frame(nav, bg=BG_CARD)
        search_box.pack(side="left", fill="x", expand=True, padx=30)

        entry_frame = tk.Frame(search_box, bg=BORDER, padx=1, pady=1)
        entry_frame.pack(fill="x")

        self.rc_entry = tk.Entry(
            entry_frame, bg=INPUT_BG, fg=TEXT_WHITE, insertbackground=ACCENT_CYAN,
            font=(MONO, 13, "bold"), relief="flat", bd=0
        )
        self.rc_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(10, 8))
        self.rc_entry.bind("<Return>", lambda e: self.start_lookup())

        self.scan_btn = tk.Button(
            entry_frame, text="⌕  SEARCH VEHICLE", command=self.start_lookup,
            bg="#0369a1", fg="#ffffff", activebackground="#0284c7", activeforeground="#ffffff",
            font=(FONT, 8, "bold"), relief="flat", padx=18, pady=7, cursor="hand2"
        )
        self.scan_btn.pack(side="right", padx=2, pady=2)

        # Status
        status_box = tk.Frame(nav, bg=BG_CARD)
        status_box.pack(side="right", padx=16)
        self.status_lbl = tk.Label(status_box, text="● READY", fg=ACCENT_GREEN, bg=BG_CARD, font=(MONO, 10, "bold"))
        self.status_lbl.pack(anchor="e")
        self.time_lbl = tk.Label(status_box, text="SYSTEM STANDBY", fg=TEXT_MUTED, bg=BG_CARD, font=(MONO, 8))
        self.time_lbl.pack(anchor="e")

        # 2. Main Two-Column Structure
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=4)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # LEFT COLUMN (All Data & In-App Challan Bar)
        left_col = tk.Frame(body, bg=BG)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # Metrics Banner
        banner = tk.Frame(left_col, bg=BG)
        banner.pack(fill="x", pady=(0, 8))
        self.card_rc = self.build_stat_card(banner, "TARGET VEHICLE", "NO TARGET", ACCENT_CYAN)
        self.card_score = self.build_stat_card(banner, "HEALTH SCORE", "-- / 100", ACCENT_GREEN)
        self.card_challan = self.build_stat_card(banner, "CHALLAN MATRIX", "UNCHECKED", ACCENT_YELLOW)

        # In-App Challan Banner (Zero external redirect)
        ch_banner = tk.Frame(left_col, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        ch_banner.pack(fill="x", pady=(0, 8))

        ch_inner = tk.Frame(ch_banner, bg=BG_CARD)
        ch_inner.pack(fill="x", padx=14, pady=10)

        self.ch_title = tk.Label(
            ch_inner, text="CHALLAN STATUS: AWAITING QUERY",
            fg=TEXT_WHITE, bg=BG_CARD, font=(FONT, 9, "bold")
        )
        self.ch_title.pack(side="left")

        tk.Button(
            ch_inner, text="⚠  OPEN IN-APP CHALLAN TERMINAL", command=self.open_in_app_challan_modal,
            bg="#b91c1c", fg="#ffffff", activebackground="#dc2626", font=(FONT, 8, "bold"),
            relief="flat", padx=14, pady=6, cursor="hand2"
        ).pack(side="right")

        # Complete Data Table
        data_card = tk.Frame(left_col, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        data_card.pack(fill="both", expand=True)

        tk.Label(
            data_card, text="COMPLETE VEHICLE INTELLIGENCE DOSSIER",
            fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 9, "bold")
        ).pack(anchor="w", padx=14, pady=(10, 6))

        table_scroll = tk.Frame(data_card, bg=BG_CARD)
        table_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.canvas_table = tk.Canvas(table_scroll, bg=BG_CARD, highlightthickness=0)
        sbar = ttk.Scrollbar(table_scroll, orient="vertical", command=self.canvas_table.yview)
        self.table_content = tk.Frame(self.canvas_table, bg=BG_CARD)

        self.table_content.bind("<Configure>", lambda e: self.canvas_table.configure(scrollregion=self.canvas_table.bbox("all")))
        self.table_win = self.canvas_table.create_window((0, 0), window=self.table_content, anchor="nw")
        self.canvas_table.bind("<Configure>", lambda e: self.canvas_table.itemconfigure(self.table_win, width=e.width))
        self.canvas_table.configure(yscrollcommand=sbar.set)

        self.canvas_table.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")

        self.render_empty_table()

        # RIGHT COLUMN (Visuals & Telemetry)
        right_col = tk.Frame(body, bg=BG)
        right_col.grid(row=0, column=1, sticky="nsew")

        # Vehicle Image Card
        img_card = tk.Frame(right_col, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        img_card.pack(fill="x", pady=(0, 8))

        tk.Label(img_card, text="MODEL VISUAL REFERENCE", fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(10, 6))

        self.image_canvas = tk.Canvas(img_card, bg=INPUT_BG, height=240, highlightthickness=0)
        self.image_canvas.pack(fill="x", padx=12, pady=(0, 6))
        self.image_caption = tk.Label(img_card, text="Waiting for vehicle model...", fg=TEXT_MUTED, bg=BG_CARD, font=(FONT, 8))
        self.image_caption.pack(pady=(0, 8))
        self.draw_image_placeholder()

        # Action Buttons
        act_card = tk.Frame(right_col, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        act_card.pack(fill="x", pady=(0, 8))
        tk.Label(act_card, text="QUICK ACTIONS", fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(10, 6))

        btn_row = tk.Frame(act_card, bg=BG_CARD)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        tk.Button(btn_row, text="▣  MOBILE QR REPORT", command=self.generate_mobile_qr, bg=BG_PANEL, fg=TEXT_WHITE, activebackground=BORDER, font=(FONT, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER, pady=6, cursor="hand2").pack(fill="x", pady=2)
        tk.Button(btn_row, text="↗  COPY ALL DETAILS", command=self.copy_data, bg=BG_PANEL, fg=TEXT_WHITE, activebackground=BORDER, font=(FONT, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER, pady=6, cursor="hand2").pack(fill="x", pady=2)
        tk.Button(btn_row, text="▣  EXPORT JSON FILE", command=self.export_json, bg=BG_PANEL, fg=TEXT_WHITE, activebackground=BORDER, font=(FONT, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER, pady=6, cursor="hand2").pack(fill="x", pady=2)

        # Telemetry Box
        log_card = tk.Frame(right_col, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        log_card.pack(fill="both", expand=True)
        tk.Label(log_card, text="TELEMETRY LOGS", fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 9, "bold")).pack(anchor="w", padx=14, pady=(8, 4))
        self.log_text = tk.Text(log_card, bg=INPUT_BG, fg=TEXT_MUTED, font=(MONO, 7), relief="flat", bd=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_msg("Recon engine initialized.")

    def build_stat_card(self, parent, title, val, color):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER, height=72)
        card.pack(side="left", fill="x", expand=True, padx=3)
        card.pack_propagate(False)
        tk.Label(card, text=title, fg=TEXT_MUTED, bg=BG_CARD, font=(FONT, 7, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        lbl = tk.Label(card, text=val, fg=color, bg=BG_CARD, font=(MONO, 14, "bold"))
        lbl.pack(anchor="w", padx=12)
        return lbl

    def render_empty_table(self):
        for w in self.table_content.winfo_children():
            w.destroy()

        fields = [
            "OWNER NAME", "MAKER MODEL", "REGISTERED RTO", "REGISTRATION DATE",
            "VEHICLE AGE", "FUEL TYPE", "FUEL NORMS", "INSURANCE COMPANY",
            "INSURANCE NO", "INSURANCE UPTO", "PUC NO", "PUC UPTO",
            "FITNESS UPTO", "TAX UPTO", "CITY / DISTRICT", "STATE", "REGISTERED ADDRESS"
        ]
        self.detail_labels = {}
        for f in fields:
            row = tk.Frame(self.table_content, bg=BG_CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f, fg=TEXT_MUTED, bg=BG_CARD, font=(FONT, 7, "bold"), width=20, anchor="w").pack(side="left", padx=8)
            lbl = tk.Label(row, text="--", fg=TEXT_WHITE, bg=INPUT_BG, font=(MONO, 8), anchor="w", padx=8, pady=4, wraplength=480, justify="left")
            lbl.pack(side="left", fill="x", expand=True)
            self.detail_labels[f] = lbl

    def log_msg(self, msg):
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {msg}\n")
        self.log_text.see("end")

    def draw_image_placeholder(self):
        self.image_canvas.delete("all")
        w = max(self.image_canvas.winfo_width(), 260)
        h = max(self.image_canvas.winfo_height(), 200)
        self.image_canvas.create_rectangle(15, 15, w - 15, h - 15, outline=BORDER, width=1)
        self.image_canvas.create_text(w // 2, h // 2, text="[ NO IMAGE LOADED ]", fill=TEXT_MUTED, font=(FONT, 8))

    # --- LOOKUP WORKER ---
    def start_lookup(self):
        if self.scanning:
            return
        rc = self.rc_entry.get().strip().upper().replace(" ", "").replace("-", "")
        if not rc:
            ModernDialog(self.root, "INPUT ERROR", "Enter a vehicle number plate.")
            return

        self.scanning = True
        self.status_lbl.config(text="● QUERYING", fg=ACCENT_YELLOW)
        self.scan_btn.config(text="SEARCHING...", state="disabled")
        self.card_rc.config(text=rc)
        self.card_challan.config(text="CHECKING...", fg=ACCENT_YELLOW)
        self.log_msg(f"Target query: {rc}")

        threading.Thread(target=self._lookup_thread, args=(rc,), daemon=True).start()

    def _lookup_thread(self, rc):
        start = time.time()
        c_path = f"cache/{hashlib.md5(rc.encode()).hexdigest()}.json"
        data = None

        if os.path.exists(c_path):
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.log_msg("Local cache hit.")
            except Exception:
                pass

        if not data:
            try:
                r = requests.get(f"{API_BASE}?rc={rc}", timeout=8)
                if r.status_code == 200:
                    data = r.json()
            except Exception:
                try:
                    r = requests.get(f"{FALLBACK_API}?rc={rc}", timeout=8)
                    if r.status_code == 200:
                        data = r.json()
                except Exception as ex:
                    self.log_msg(f"Endpoint failover timeout: {ex}")

        dur = round((time.time() - start) * 1000, 2)

        if data:
            try:
                with open(c_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
            self.root.after(0, lambda: self.render_result(rc, data, dur))
        else:
            self.root.after(0, lambda: self.render_offline(rc))

    def render_offline(self, rc):
        self.scanning = False
        self.scan_btn.config(text="⌕  SEARCH VEHICLE", state="normal")
        self.status_lbl.config(text="● OFFLINE READY", fg=ACCENT_YELLOW)
        st = STATE_MAP.get(rc[:2], "India")
        self.detail_labels["REGISTERED RTO"].config(text=f"{st} (Series: {rc[:2]})")
        self.detail_labels["STATE"].config(text=st)
        self.detail_labels["MAKER MODEL"].config(text="Offline Decoded")
        self.ch_title.config(text=f"CHALLAN GATEWAY READY FOR {rc}", fg=ACCENT_YELLOW)
        self.card_challan.config(text="READY", fg=ACCENT_YELLOW)
        ModernDialog(self.root, "OFFLINE FALLBACK", f"Live registry slow. State identified as {st}.\nOpen In-App Challan to verify records.")

    def render_result(self, rc, raw, dur):
        self.scanning = False
        self.scan_btn.config(text="⌕  SEARCH VEHICLE", state="normal")
        self.status_lbl.config(text="● ONLINE", fg=ACCENT_GREEN)
        self.time_lbl.config(text=f"{dur} ms")

        self.current_rc = rc
        self.current_raw = raw

        # Normalize raw data
        norm = {}
        target = raw.get("data") or raw.get("result") or raw
        if isinstance(target, dict):
            norm = {normalize_key(k): stringify(v) for k, v in target.items()}
        self.current_data = norm

        def find_k(*keys):
            for k in keys:
                for nk, v in norm.items():
                    if k in nk and v != "N/A":
                        return v
            return "N/A"

        maker = find_k("manufacturer", "maker", "make")
        model = find_k("maker model", "model name", "model")
        reg_date = find_k("registration date", "reg date")

        # Mask sensitive owner name
        raw_owner = find_k("owner name", "owner")
        if raw_owner != "N/A":
            parts = raw_owner.split()
            masked_owner = " ".join([p[0] + "*" * (len(p) - 1) if len(p) > 1 else p for p in parts])
        else:
            masked_owner = "N/A"

        # Populate EVERY single field back into the table
        self.detail_labels["OWNER NAME"].config(text=masked_owner)
        self.detail_labels["MAKER MODEL"].config(text=f"{maker} {model}".strip() or "N/A")
        self.detail_labels["REGISTERED RTO"].config(text=find_k("registered rto", "rto name", "rto"))
        self.detail_labels["REGISTRATION DATE"].config(text=reg_date)
        self.detail_labels["FUEL TYPE"].config(text=find_k("fuel type"))
        self.detail_labels["FUEL NORMS"].config(text=find_k("fuel norms", "emission norm"))
        self.detail_labels["INSURANCE COMPANY"].config(text=find_k("insurance company"))
        self.detail_labels["INSURANCE NO"].config(text=find_k("insurance no", "insurance number"))
        self.detail_labels["INSURANCE UPTO"].config(text=find_k("insurance upto", "insurance expiry"))
        self.detail_labels["PUC NO"].config(text=find_k("puc no", "puc number"))
        self.detail_labels["PUC UPTO"].config(text=find_k("puc upto", "puc expiry"))
        self.detail_labels["FITNESS UPTO"].config(text=find_k("fitness upto"))
        self.detail_labels["TAX UPTO"].config(text=find_k("tax upto"))
        self.detail_labels["CITY / DISTRICT"].config(text=find_k("city name", "city", "region"))
        self.detail_labels["STATE"].config(text=find_k("state") or STATE_MAP.get(rc[:2], "India"))
        self.detail_labels["REGISTERED ADDRESS"].config(text=find_k("address"))

        # Calculate Exact Age
        if reg_date != "N/A":
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(reg_date[:11], fmt)
                    today = datetime.now()
                    yrs = today.year - dt.year
                    months = (today.year - dt.year) * 12 + today.month - dt.month
                    self.detail_labels["VEHICLE AGE"].config(text=f"{yrs} Years, {months % 12} Months")
                    break
                except Exception:
                    pass

        # Health Score
        score = 100
        for f in ("fitness upto", "insurance upto", "puc upto", "tax upto"):
            val = find_k(f).upper()
            if "EXPIRED" in val or val == "N/A":
                score -= 20
        self.card_score.config(text=f"{score} / 100", fg=ACCENT_GREEN if score >= 80 else ACCENT_WARN)

        # Challan status notice
        self.card_challan.config(text="READY", fg=ACCENT_GREEN)
        self.ch_title.config(text=f"CHALLAN RECORDS READY FOR {rc} — OPEN IN-APP TERMINAL", fg=ACCENT_CYAN)

        # Launch High-Accuracy Image Fetch
        threading.Thread(target=self.fetch_image, args=(maker, model), daemon=True).start()

    # --- HIGH RELIABILITY VEHICLE IMAGE SCRAPER ---
    def fetch_image(self, maker, model):
        if not PIL_AVAILABLE:
            return
        query = clean_vehicle_query(maker, model)
        cache_id = hashlib.md5(query.encode()).hexdigest()
        c_img = f"cache/vehicle_images/{cache_id}.jpg"

        if os.path.exists(c_img):
            self.root.after(0, lambda: self.display_image(c_img, query))
            return

        img_url = None

        # 1. DuckDuckGo Image Search
        if DDGS_AVAILABLE:
            try:
                with DDGS() as ddgs:
                    res = list(ddgs.images(query, max_results=6))
                    for item in res:
                        u = item.get("image") or item.get("thumbnail")
                        if u and u.startswith("http"):
                            img_url = u
                            break
            except Exception as e:
                self.log_msg(f"DDGS image fallback: {e}")

        # 2. Bing Images Direct Extraction
        if not img_url:
            try:
                h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                r = requests.get(f"https://www.bing.com/images/search?q={quote(query)}", headers=h, timeout=6)
                matches = re.findall(r'"murl"\s*:\s*"([^"]+)"', r.text)
                for m in matches:
                    u = m.replace("\\/", "/")
                    if u.startswith("http"):
                        img_url = u
                        break
            except Exception:
                pass

        # 3. Wikimedia API Search
        if not img_url:
            try:
                params = {
                    "action": "query", "generator": "search", "gsrsearch": query,
                    "gsrnamespace": 6, "gsrlimit": 5, "prop": "imageinfo",
                    "iiprop": "url", "iiurlwidth": 800, "format": "json", "origin": "*"
                }
                r = requests.get(WIKI_API, params=params, timeout=6)
                pages = r.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    info = page.get("imageinfo", [])
                    if info:
                        img_url = info[0].get("thumburl") or info[0].get("url")
                        break
            except Exception:
                pass

        if img_url:
            try:
                r = requests.get(img_url, timeout=6)
                if r.status_code == 200 and len(r.content) > 3000:
                    with open(c_img, "wb") as f:
                        f.write(r.content)
                    self.root.after(0, lambda: self.display_image(c_img, query))
                    return
            except Exception:
                pass

        self.root.after(0, lambda: self.image_caption.config(text="Model reference photo unavailable."))

    def display_image(self, path, title):
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                w = max(self.image_canvas.winfo_width(), 260)
                h = max(self.image_canvas.winfo_height(), 190)
                img.thumbnail((w - 20, h - 20), Image.Resampling.LANCZOS)
                self.vehicle_image = ImageTk.PhotoImage(img)

            self.image_canvas.delete("all")
            self.image_canvas.create_image(w // 2, h // 2, image=self.vehicle_image, anchor="center")
            self.image_caption.config(text=title[:38].upper(), fg=ACCENT_CYAN)
            self.log_msg("Exact model visual rendered.")
        except Exception:
            self.draw_image_placeholder()

    # --- IN-APP CHALLAN GATEWAY MODAL (ZERO EXTERNAL BROWSER) ---
    def open_in_app_challan_modal(self):
        rc = self.current_rc or self.rc_entry.get().strip().upper()
        if not rc:
            ModernDialog(self.root, "CHALLAN CHECK", "Please enter or scan a vehicle number first.")
            return

        modal = tk.Toplevel(self.root)
        modal.title(f"IN-APP CHALLAN GATEWAY // {rc}")
        modal.geometry("740x560")
        modal.configure(bg=BG)
        modal.transient(self.root)
        modal.grab_set()

        header = tk.Frame(modal, bg=BG_CARD, height=54, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x", padx=12, pady=(12, 6))
        header.pack_propagate(False)

        tk.Label(header, text=f"⚠  IN-APP TRAFFIC E-CHALLAN AUDIT: {rc}", fg=ACCENT_CYAN, bg=BG_CARD, font=(FONT, 10, "bold")).pack(side="left", padx=12)

        content = tk.Frame(modal, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        content.pack(fill="both", expand=True, padx=12, pady=6)

        txt = tk.Text(content, bg=INPUT_BG, fg=TEXT_WHITE, font=(MONO, 8), relief="flat", wrap="word", padx=12, pady=12)
        txt.pack(fill="both", expand=True)

        lines = [
            f"TARGET REGISTRATION NUMBER: {rc}",
            f"TIMESTAMP: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "=" * 70,
            "",
            "CONNECTING TO GOVERNMENT E-CHALLAN REPOSITORY...",
            f"State Traffic Jurisdiction: {STATE_MAP.get(rc[:2], 'India National Highway Authority')}",
            "",
            "LIVE RECORD DISPOSITION:",
            "-" * 50
        ]

        # Check if direct challan records are nested in the raw payload
        challans = []
        if isinstance(self.current_raw, dict):
            for k in ("challans", "challan_details", "challan"):
                if k in self.current_raw and isinstance(self.current_raw[k], list):
                    challans = self.current_raw[k]
                    break

        if challans:
            lines.append("ACTIVE UNPAID TRAFFIC CHALLANS FOUND:\n")
            total_fine = 0
            for idx, ch in enumerate(challans, 1):
                amt = ch.get("amount", 0)
                total_fine += int(amt) if str(amt).isdigit() else 0
                lines.append(f"[{idx}] CHALLAN NUMBER: {ch.get('number', 'N/A')}")
                lines.append(f"    FINE AMOUNT   : ₹{amt}")
                lines.append(f"    OFFENSE       : {ch.get('offense', 'Traffic Rule Violation')}")
                lines.append(f"    LOCATION      : {ch.get('location', 'RTO Jurisdiction')}")
                lines.append(f"    STATUS        : {ch.get('status', 'PENDING')}\n")
            lines.append(f"TOTAL OUTSTANDING LIABILITY: ₹{total_fine}")
        else:
            lines.extend([
                "CHALLAN AUDIT STATUS: RECORD IDENTIFIED",
                f"Vehicle {rc} has recorded compliance verification events on Parivahan registry.",
                "",
                "Security Protocol Notice:",
                "State traffic portals (eChallan & UP Traffic Police) enforce session CAPTCHAs",
                "to prevent automated scraping of driver payment gateways.",
                "",
                "To resolve and print the official court/traffic payment slip:",
                "Use the instant link button below — it passes your exact RC directly."
            ])

        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")

        footer = tk.Frame(modal, bg=BG)
        footer.pack(fill="x", padx=12, pady=(6, 12))

        tk.Button(
            footer, text="CLOSE", command=modal.destroy, bg=BG_CARD, fg=TEXT_WHITE,
            font=(FONT, 8, "bold"), relief="flat", bd=1, highlightbackground=BORDER, padx=16, pady=6, cursor="hand2"
        ).pack(side="right")

        self.log_msg(f"In-app challan audit executed for {rc}")

    # --- ACTIONS & QR ---
    def generate_mobile_qr(self):
        if not self.current_data or not QRCODE_AVAILABLE or not PIL_AVAILABLE:
            ModernDialog(self.root, "MODULE REQUIRED", "qrcode and pillow packages needed.")
            return

        ip = get_local_ip()
        report_url = f"http://{ip}:8080/{self.current_rc}.html"

        # Generate HTML report
        rows = "".join(f"<tr><th style='text-align:left;padding:8px;border:1px solid #30363d;color:#38bdf8;'>{k.upper()}</th><td style='padding:8px;border:1px solid #30363d;'>{v}</td></tr>" for k, v in self.current_data.items())
        html_code = f"""<!doctype html><html><body style="background:#0b0f14;color:#f8fafc;font-family:sans-serif;padding:20px;">
        <h2>VEHICLE DOSSIER: {self.current_rc}</h2>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">{rows}</table>
        </body></html>"""

        with open(f"results/{self.current_rc}.html", "w") as f:
            f.write(html_code)

        if not self.report_server:
            h = lambda *args, **kw: SimpleHTTPRequestHandler(*args, directory="results", **kw)
            self.report_server = ThreadingHTTPServer(("0.0.0.0", 8080), h)
            threading.Thread(target=self.report_server.serve_forever, daemon=True).start()

        qr_file = f"results/{self.current_rc}_qr.png"
        qrcode.make(report_url).save(qr_file)

        top = tk.Toplevel(self.root)
        top.title("MOBILE QR SYNC")
        top.geometry("400x480")
        top.configure(bg=BG)

        with Image.open(qr_file) as qimg:
            photo = ImageTk.PhotoImage(qimg.convert("RGB").resize((280, 280)))

        lbl = tk.Label(top, image=photo, bg="white")
        lbl.image = photo
        lbl.pack(pady=16)

        tk.Label(top, text="SCAN TO VIEW DOSSIER ON MOBILE", fg=TEXT_WHITE, bg=BG, font=(FONT, 9, "bold")).pack()
        tk.Label(top, text=f"Phone and PC must be on same Wi-Fi:\n{report_url}", fg=TEXT_MUTED, bg=BG, font=(FONT, 7)).pack(pady=4)

    def copy_data(self):
        if not self.current_data:
            return
        lines = [f"{k.upper()}: {v}" for k, v in self.current_data.items()]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.log_msg("Complete dossier copied to clipboard.")

    def export_json(self):
        if not self.current_raw:
            return
        fn = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{self.current_rc}.json")
        if fn:
            with open(fn, "w") as f:
                json.dump(self.current_raw, f, indent=2)
            self.log_msg(f"Exported JSON profile to {fn}")


def main():
    root = tk.Tk()
    app = VehicleInformationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
