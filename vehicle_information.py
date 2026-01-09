#!/usr/bin/env python3
"""
VEHICLE_INFORMATION (AZOD08)
Author : azod08
License: MIT
Educational & Ethical Use Only
"""

import os
import json
import time
import hashlib
import requests
from datetime import datetime
from urllib.parse import urlencode
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.columns import Columns
from rich import box

API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
VERSION = "1.0"

console = Console()

# ------------------ UTILS ------------------

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def ensure_dirs():
    for d in ["results", "logs", "cache"]:
        os.makedirs(d, exist_ok=True)

def log(msg):
    with open("logs/activity.log", "a") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def cache_file(rc):
    return f"cache/{hashlib.md5(rc.encode()).hexdigest()}.json"

# ------------------ UI ------------------

def banner():
    clear()

    console.print(
        Align.center(
            Panel(
                f"VEHICLE INFORMATION SYSTEM\n"
                f"Educational & Ethical Use Only\n\n"
                f"Author : azod08   |   Version : {VERSION}",
                border_style="green",
                box=box.DOUBLE
            )
        )
    )

    console.print(
        Align.center(
            Panel(
                "This tool is strictly for lawful & educational purposes only.",
                border_style="red",
                box=box.HEAVY
            )
        )
    )

# ------------------ CORE ------------------

def fetch_data(rc):
    cached = cache_file(rc)

    if os.path.exists(cached):
        with open(cached) as f:
            return json.load(f), True

    url = f"{API_BASE}?{urlencode({'rc': rc})}"
    start = time.time()

    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except Exception as e:
        return {"error": str(e)}, False

    data["_response_time_ms"] = round((time.time() - start) * 1000, 2)

    with open(cached, "w") as f:
        json.dump(data, f, indent=4)

    return data, False

# ------------------ DISPLAY ------------------

def display(rc, data, cached):

    if "error" in data:
        console.print(
            Align.center(
                Panel(str(data["error"]), border_style="red", box=box.HEAVY)
            )
        )
        return

    # RC NUMBER PLATE
    console.print("\n")
    console.print(
        Align.center(
            Panel(
                f"🚘  {rc.upper()}",
                border_style="green",
                box=box.DOUBLE
            )
        )
    )

    # STATUS BOX
    console.print(
        Align.center(
            Panel(
                f"Cached : {'YES' if cached else 'NO'}\n"
                f"Response Time : {data.pop('_response_time_ms')} ms",
                border_style="green"
            )
        )
    )

    # PERSONAL INFO (RIGHT SIDE)
    personal_keys = [
        "owner_name",
        "father_name",
        "mobile_no",
        "address"
    ]

    personal_text = ""
    for key in personal_keys:
        if key in data:
            personal_text += f"{key.replace('_',' ').upper()} : {data.pop(key)}\n"

    personal_box = Panel(
        personal_text.strip() if personal_text else "N/A",
        title="PERSONAL INFORMATION",
        border_style="green",
        box=box.HEAVY
    )

    # OTHER DATA (LEFT SIDE, MULTIPLE BOXES)
    other_boxes = []
    for k, v in data.items():
        other_boxes.append(
            Panel(
                str(v),
                title=k.replace("_", " ").upper(),
                border_style="green"
            )
        )

    left_column = Columns(other_boxes, expand=True, equal=True)

    # FINAL DASHBOARD LAYOUT
    console.print(
        Columns(
            [left_column, personal_box],
            expand=True
        )
    )

    # SAVE RESULT
    with open(f"results/{rc}.json", "w") as f:
        json.dump(data, f, indent=4)

# ------------------ MAIN ------------------

def main():
    ensure_dirs()
    banner()

    rc = console.input("\n➜ Enter Vehicle RC Number : ").strip()
    if not rc:
        return

    log(f"Lookup started for RC: {rc}")
    data, cached = fetch_data(rc)
    display(rc, data, cached)
    log(f"Lookup finished for RC: {rc}")

    console.print("\n")
    console.print(
        Align.center(
            Panel("DONE", border_style="green")
        )
    )

if __name__ == "__main__":
    main()
