#!/usr/bin/env python3
"""
NTNU Log Analyzer

Analyzes recorded request logs and generates API documentation.
"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.tree import Tree

LOG_DIR = Path(__file__).parent / "request_logs"

console = Console()


def load_log(log_path: Path) -> dict:
    """Load a log file."""
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_endpoints(data: dict) -> dict:
    """Analyze endpoints from recorded requests."""
    endpoints = {}

    for req in data.get("requests", []):
        path = req.get("path", "")
        action = req.get("action")
        method = req.get("method", "GET")

        # Create endpoint key
        key = f"{method}:{path}:{action or ''}"

        if key not in endpoints:
            endpoints[key] = {
                "method": method,
                "path": path,
                "action": action,
                "params": set(),
                "post_params": set(),
                "count": 0,
                "sample_url": req.get("url"),
                "sample_post_data": req.get("post_data"),
            }

        endpoints[key]["count"] += 1

        # Collect params
        for k in req.get("params", {}).keys():
            if k != "action":
                endpoints[key]["params"].add(k)

        # Parse POST data params
        if req.get("post_data"):
            try:
                post_params = parse_qs(req["post_data"])
                for k in post_params.keys():
                    endpoints[key]["post_params"].add(k)
            except Exception:
                pass

    return endpoints


def display_analysis(endpoints: dict) -> None:
    """Display analysis results."""
    console.print("\n" + "=" * 70)
    console.print("[bold]API ENDPOINT ANALYSIS[/]")
    console.print("=" * 70)

    # Group by controller
    by_controller: dict[str, list] = {}
    for key, ep in endpoints.items():
        # Extract controller name from path
        path = ep["path"]
        if "Ctrl" in path:
            ctrl = path.split("/")[-1].split("?")[0]
        else:
            ctrl = "Other"
        by_controller.setdefault(ctrl, []).append(ep)

    # Display tree structure
    tree = Tree("[bold]NTNU Course System API[/]")

    for ctrl, eps in sorted(by_controller.items()):
        ctrl_branch = tree.add(f"[bold cyan]{ctrl}[/]")

        for ep in sorted(eps, key=lambda x: x["action"] or ""):
            action = ep["action"] or "(no action)"
            method = ep["method"]
            count = ep["count"]

            # Build param list
            params = list(ep["params"])
            post_params = list(ep["post_params"])

            action_node = ctrl_branch.add(
                f"[green]{method}[/] {action} [dim](called {count}x)[/]"
            )

            if params:
                action_node.add(f"[dim]Query params:[/] {', '.join(sorted(params))}")
            if post_params:
                action_node.add(f"[dim]POST params:[/] {', '.join(sorted(post_params))}")

    console.print(tree)

    # Detailed table
    console.print("\n[bold]Detailed Endpoint List:[/]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Controller", width=20)
    table.add_column("Action", width=25)
    table.add_column("Method", width=6)
    table.add_column("Query Params", width=25)
    table.add_column("POST Params", width=25)

    for key, ep in sorted(endpoints.items(), key=lambda x: x[1]["path"]):
        path = ep["path"]
        ctrl = path.split("/")[-1].split("?")[0] if "/" in path else path

        table.add_row(
            ctrl,
            ep["action"] or "-",
            ep["method"],
            ", ".join(sorted(ep["params"])) or "-",
            ", ".join(sorted(ep["post_params"])) or "-",
        )

    console.print(table)


def export_api_spec(endpoints: dict, output_path: Path) -> None:
    """Export API specification to JSON."""
    spec = {
        "title": "NTNU Course System API",
        "base_url": "https://cos2s.ntnu.edu.tw/AasEnrollStudent",
        "endpoints": []
    }

    for key, ep in endpoints.items():
        spec["endpoints"].append({
            "controller": ep["path"].split("/")[-1].split("?")[0],
            "action": ep["action"],
            "method": ep["method"],
            "path": ep["path"],
            "query_params": list(ep["params"]),
            "post_params": list(ep["post_params"]),
            "sample_url": ep["sample_url"],
            "sample_post_data": ep["sample_post_data"],
            "call_count": ep["count"],
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    console.print(f"\n[green]API spec exported to:[/] {output_path}")


def main():
    """Main entry point."""
    console.print(Panel(
        "[bold]NTNU Log Analyzer[/]\n\n"
        "Analyzes recorded request logs to extract API structure.",
        title="Log Analyzer",
        border_style="blue"
    ))

    # Find available logs
    log_files = sorted(LOG_DIR.glob("requests_*.json"), reverse=True)

    if not log_files:
        console.print("[red]No log files found![/]")
        console.print(f"[dim]Run ntnu_request_recorder.py first to create logs.[/]")
        return

    # List available logs
    console.print("\n[bold]Available log files:[/]")
    table = Table(show_header=True)
    table.add_column("#", width=4)
    table.add_column("File", width=40)
    table.add_column("Size", width=10)

    for idx, log_file in enumerate(log_files[:10], 1):
        size = log_file.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        table.add_row(str(idx), log_file.name, size_str)

    console.print(table)

    # Select log file
    choice = Prompt.ask(
        "Select log file number",
        default="1"
    )

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(log_files):
            log_path = log_files[idx]
        else:
            console.print("[red]Invalid selection[/]")
            return
    except ValueError:
        console.print("[red]Invalid input[/]")
        return

    # Load and analyze
    console.print(f"\n[dim]Loading {log_path.name}...[/]")
    data = load_log(log_path)

    console.print(f"[dim]Found {data.get('total_requests', 0)} requests[/]")

    endpoints = analyze_endpoints(data)
    display_analysis(endpoints)

    # Export option
    if Prompt.ask("\nExport API spec to JSON? (y/n)", default="y").lower() == "y":
        output_path = LOG_DIR / f"api_spec_{log_path.stem.replace('requests_', '')}.json"
        export_api_spec(endpoints, output_path)


if __name__ == "__main__":
    main()
