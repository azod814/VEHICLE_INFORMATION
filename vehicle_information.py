#!/usr/bin/env python3
"""
VEHICLE_INFORMATION (AZOD08)
Author : azod08
License : MIT
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

# ---------------- BASIC ----------------

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

# ---------------- UI ----------------

def banner():
    clear()
    console.print(
        Align.center(
            Panel(
                f"VEHICLE INFORMATION SYSTEM\n"
                f"Educational & Ethical Use Only\n\n"
                f"Author : azod08 | Version : {VERSION}",
                border_style="green",
                box=box.DOUBLE
            )
        )
    )

# ---------------- CORE ----------------

def fetch_data(rc):
    cached = cache_file(rc)
    if os.path.exists(cached):
        with open(cached) as f:
            return json.load(f), True

    url = f"{API_BASE}?{urlencode({'rc': rc})}"
    start = time.time()
    r = requests.get(url, timeout=15)
    data = r.json()
    data["_response_time_ms"] = round((time.time() - start) * 1000, 2)

    with open(cached, "w") as f:
        json.dump(data, f, indent=4)

    return data, False

# ---------------- DISPLAY ----------------

def display(rc, data, cached):

    # RC INPUT RESULT (NUMBER PLATE)
    console.print(
        Align.center(
            Panel(
                rc.upper(),
                title="VEHICLE NUMBER",
                border_style="green",
                box=box.DOUBLE
            )
        )
    )

    # LEFT SIDE BOXES
    address_box = Panel(
        f"{data.get('address','N/A')}\n"
        f"City : {data.get('city_name','N/A')}\n"
        f"District : {data.get('district','N/A')}",
        title="ADDRESS INFO",
        border_style="green",
        box=box.HEAVY
    )

    personal_box = Panel(
        f"Name : {data.get('owner_name','N/A')}\n"
        f"Father : {data.get('father_name','N/A')}\n"
        f"Mobile : {data.get('mobile_no','N/A')}",
        title="PERSONAL INFO",
        border_style="green",
        box=box.HEAVY
    )

    # CENTER BOXES
    detail_box_1 = Panel(
        f"Reg Date : {data.get('reg_date','N/A')}\n"
        f"RTO : {data.get('rto','N/A')}\n"
        f"State : {data.get('state','N/A')}",
        title="DETAIL",
        border_style="green"
    )

    detail_box_2 = Panel(
        f"Owner Type : {data.get('owner_type','N/A')}\n"
        f"Class : {data.get('vehicle_class','N/A')}\n"
        f"Status : {data.get('status','N/A')}",
        title="DETAIL",
        border_style="green"
    )

    # RIGHT SIDE BOXES
    vehicle_box = Panel(
        f"Type : {data.get('vehicle_type','N/A')}\n"
        f"Fuel : {data.get('fuel_type','N/A')}\n"
        f"Norms : {data.get('fuel_norms','N/A')}\n"
        f"Fitness : {data.get('fitness_upto','N/A')}",
        title="VEHICLE INFO",
        border_style="green"
    )

    engine_box = Panel(
        f"Engine : {data.get('engine_no','N/A')}\n"
        f"Chassis : {data.get('chassis_no','N/A')}",
        title="ENGINE / CHASSIS",
        border_style="green"
    )

    # FINAL LAYOUT (DRAWING MATCH)
    console.print(
        Columns(
            [
                Columns([address_box, personal_box]),
                Columns([detail_box_1, detail_box_2]),
                Columns([vehicle_box, engine_box]),
            ],
            expand=True
        )
    )

    with open(f"results/{rc}.json", "w") as f:
        json.dump(data, f, indent=4)

# ---------------- MAIN ----------------

def main():
    ensure_dirs()
    banner()

    rc = console.input("\nEnter Vehicle RC Number : ").strip()
    if not rc:
        return

    log(f"Lookup started : {rc}")
    data, cached = fetch_data(rc)
    display(rc, data, cached)
    log(f"Lookup finished : {rc}")

if __name__ == "__main__":
    main()
