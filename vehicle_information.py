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
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box

API_BASE = "https://vehicleinfobyterabaap.vercel.app/lookup"
VERSION = "1.0"

# Dark green theme color
THEME_COLOR = "#0f9d58"

console = Console()

# ------------------ BASIC UTILS ------------------

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
            Panel.fit(
                f"[bold {THEME_COLOR}]VEHICLE INFORMATION SYSTEM[/bold {THEME_COLOR}]\n"
                f"[{THEME_COLOR}]Educational & Ethical Use Only[/]\n\n"
                f"[bold {THEME_COLOR}]Author:[/] azod08   |   "
                f"[bold {THEME_COLOR}]Version:[/] {VERSION}",
                border_style=THEME_COLOR,
                box=box.DOUBLE
            )
        )
    )

    console.print(
        Align.center(
            Panel(
                "[bold red]                     ⚠ DISCLAIMER ⚠[/bold red]\n"
                f"[{THEME_COLOR}]This tool is strictly for lawful & educational purposes only.[/]",
                border_style="red",
                box=box.HEAVY
            )
        )
    )

# ------------------ CORE LOGIC ------------------

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

def display(rc, data, cached):
    if "error" in data:
        console.print(
            Panel(
                data["error"],
                title="ERROR",
                border_style="red",
                box=box.HEAVY
            )
        )
        return

    # NUMBER PLATE
    console.print(
        Align.center(
            Panel.fit(
                f"🚘  {rc.upper()}",
                border_style=THEME_COLOR,
                box=box.DOUBLE
            )
        )
    )

    status = (
        f"Cached : {'YES' if cached else 'NO'}\n"
        f"Response Time : {data.pop('_response_time_ms')} ms"
    )

    console.print(
        Panel(
            status,
            title="SYSTEM STATUS",
            border_style=THEME_COLOR,
            box=box.SQUARE
        )
    )

    table = Table(
        title="VEHICLE DATA OUTPUT",
        box=box.HEAVY,
        show_lines=True,
        border_style=THEME_COLOR
    )

    table.add_column("FIELD", style=f"bold {THEME_COLOR}", no_wrap=True)
    table.add_column("VALUE", style="white")

    for k, v in data.items():
        table.add_row(
            k.replace("_", " ").upper(),
            str(v)
        )

    console.print(table)

    with open(f"results/{rc}.json", "w") as f:
        json.dump(data, f, indent=4)

# ------------------ MAIN ------------------

def main():
    ensure_dirs()
    banner()

    # CLEAN INPUT (NO RAW MARKUP TEXT)
    rc = console.input(
        f"\n[{THEME_COLOR}]Enter Vehicle RC Number: ➜ [/]"
    ).strip()

    if not rc:
        console.print("[red]RC number is required.[/red]")
        return

    log(f"Lookup started for RC: {rc}")
    data, cached = fetch_data(rc)
    display(rc, data, cached)
    log(f"Lookup finished for RC: {rc}")

    console.print(f"\n[bold {THEME_COLOR}]✔ DONE[/bold {THEME_COLOR}]")

if __name__ == "__main__":
    main()
