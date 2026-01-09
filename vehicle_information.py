#!/usr/bin/env python3
"""
VEHICLE_INFORMATION (AZOD08)
Author : azod08
License: MIT

Educational & Ethical Use Only
"""

import os
import sys
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

# ------------------ HACKER UI ------------------

def banner():
    clear()
    console.print(
        Panel.fit(
            "[bold green]VEHICLE INFORMATION SYSTEM[/bold green]\n"
            "[green]Educational & Ethical Use Only[/green]\n\n"
            f"[bold]Author:[/bold] azod08   |   [bold]Version:[/bold] {VERSION}",
            border_style="green",
            box=box.DOUBLE
        )
    )

    console.print(
        Panel(
            "[bold red]⚠ DISCLAIMER ⚠[/bold red]\n"
            "[green]This tool is strictly for lawful & educational purposes only.[/green]",
            border_style="red",
            box=box.HEAVY
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
                f"[bold red]{data['error']}[/bold red]",
                title="[red]ERROR[/red]",
                border_style="red",
                box=box.HEAVY
            )
        )
        return

    # NUMBER PLATE STYLE RC DISPLAY
    console.print(
        Align.center(
            Panel.fit(
                f"[bold black on green]  🚘  {rc.upper()}  [/bold black on green]",
                border_style="green",
                box=box.DOUBLE
            )
        )
    )

    status = (
        f"[green]Cached:[/green] {'YES' if cached else 'NO'}\n"
        f"[green]Response Time:[/green] {data.pop('_response_time_ms')} ms"
    )

    console.print(
        Panel(
            status,
            title="[bold green]SYSTEM STATUS[/bold green]",
            border_style="green",
            box=box.SQUARE
        )
    )

    table = Table(
        title="[bold green]VEHICLE DATA OUTPUT[/bold green]",
        box=box.HEAVY,
        show_lines=True,
        border_style="green"
    )

    table.add_column("FIELD", style="bold green", no_wrap=True)
    table.add_column("VALUE", style="bold white")

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

    rc = input("\n[bold green]➜ Enter Vehicle RC Number:[/bold green] ").strip()
    if not rc:
        console.print("[bold red]RC number is required.[/bold red]")
        return

    log(f"Lookup started for RC: {rc}")
    data, cached = fetch_data(rc)
    display(rc, data, cached)
    log(f"Lookup finished for RC: {rc}")

    console.print("\n[bold green]✔ DONE[/bold green]")

if __name__ == "__main__":
    main()
