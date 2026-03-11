#!/usr/bin/env python3
"""
NTNU Request Recorder

Simple script that:
1. Opens browser
2. Records all network requests while you manually operate the system
3. Saves the log for later analysis
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import nodriver as uc
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

# Configuration
BASE_URL = "https://cos2s.ntnu.edu.tw/AasEnrollStudent"
LOG_DIR = Path(__file__).parent / "request_logs"
LOG_DIR.mkdir(exist_ok=True)

console = Console()


@dataclass
class RequestRecord:
    """A single network request record."""
    timestamp: str
    method: str
    url: str
    path: str
    action: str | None
    params: dict
    post_data: str | None
    headers: dict
    response_status: int | None = None
    response_body: str | None = None


class RequestRecorder:
    """Records all network requests during manual browser operation."""

    def __init__(self):
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None
        self.requests: list[RequestRecord] = []
        self.request_count = 0
        self._pending_requests: dict[str, RequestRecord] = {}

    async def start(self) -> None:
        """Start browser and begin recording."""
        console.print("[bold]Starting browser...[/]")

        self.browser = await uc.start(
            headless=False,
            browser_args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )

        self.page = await self.browser.get(f"{BASE_URL}/LoginCheckCtrl?language=TW")

        # Setup network interception
        await self._setup_network_listener()

        console.print("[green]Browser started![/]")
        console.print(f"[green]Recording requests to NTNU system...[/]\n")

    async def _setup_network_listener(self) -> None:
        """Setup CDP network listeners."""
        if not self.page:
            return

        await self.page.send(uc.cdp.network.enable())

        self.page.add_handler(
            uc.cdp.network.RequestWillBeSent,
            self._on_request
        )
        self.page.add_handler(
            uc.cdp.network.ResponseReceived,
            self._on_response
        )

    def _on_request(self, event: uc.cdp.network.RequestWillBeSent) -> None:
        """Handle outgoing requests."""
        request = event.request
        url = request.url

        # Only record NTNU requests
        if "ntnu.edu.tw" not in url:
            return

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        action = query_params.get("action", [None])[0]

        # Get POST data if available
        post_data = None
        if hasattr(request, "post_data") and request.post_data:
            post_data = request.post_data

        record = RequestRecord(
            timestamp=datetime.now().isoformat(),
            method=request.method,
            url=url,
            path=parsed.path,
            action=action,
            params={k: v[0] if len(v) == 1 else v for k, v in query_params.items()},
            post_data=post_data,
            headers=dict(request.headers) if request.headers else {},
        )

        # Store for response matching
        self._pending_requests[str(event.request_id)] = record
        self.requests.append(record)
        self.request_count += 1

        # Print to console
        action_str = f"?action={action}" if action else ""
        console.print(f"[cyan]{self.request_count:3d}[/] {request.method:4s} {parsed.path}{action_str}")

    def _on_response(self, event: uc.cdp.network.ResponseReceived) -> None:
        """Handle response to update request record."""
        request_id = str(event.request_id)
        if request_id in self._pending_requests:
            self._pending_requests[request_id].response_status = event.response.status

    def save_log(self) -> Path:
        """Save recorded requests to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"requests_{timestamp}.json"

        data = {
            "recorded_at": datetime.now().isoformat(),
            "total_requests": len(self.requests),
            "requests": [
                {
                    "timestamp": r.timestamp,
                    "method": r.method,
                    "url": r.url,
                    "path": r.path,
                    "action": r.action,
                    "params": r.params,
                    "post_data": r.post_data,
                    "response_status": r.response_status,
                }
                for r in self.requests
            ]
        }

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return log_path

    def generate_summary(self) -> None:
        """Generate and display summary of recorded requests."""
        console.print("\n" + "=" * 60)
        console.print("[bold]REQUEST RECORDING SUMMARY[/]")
        console.print("=" * 60)

        # Group by endpoint
        endpoints: dict[str, list[RequestRecord]] = {}
        for req in self.requests:
            key = f"{req.method} {req.path}"
            if req.action:
                key += f"?action={req.action}"
            endpoints.setdefault(key, []).append(req)

        # Display table
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", width=4)
        table.add_column("Method", width=6)
        table.add_column("Endpoint", width=40)
        table.add_column("Count", width=6)
        table.add_column("Params", width=30)

        for idx, (endpoint, reqs) in enumerate(sorted(endpoints.items()), 1):
            # Get unique params
            all_params = set()
            for req in reqs:
                for k in req.params.keys():
                    if k != "action":
                        all_params.add(k)

            method = reqs[0].method
            params_str = ", ".join(sorted(all_params)) if all_params else "-"

            table.add_row(
                str(idx),
                method,
                endpoint.replace(f"{method} ", ""),
                str(len(reqs)),
                params_str[:30]
            )

        console.print(table)
        console.print(f"\n[bold]Total unique endpoints:[/] {len(endpoints)}")
        console.print(f"[bold]Total requests recorded:[/] {len(self.requests)}")

    async def close(self) -> None:
        """Close browser."""
        if self.browser:
            try:
                await asyncio.sleep(0.5)
                self.browser.stop()
                await asyncio.sleep(0.5)
            except Exception:
                pass


async def main():
    """Main entry point."""
    console.print(Panel(
        "[bold]NTNU Request Recorder[/]\n\n"
        "This tool records all network requests while you:\n"
        "1. Login to the course system\n"
        "2. Navigate through menus\n"
        "3. Perform course operations\n\n"
        "[yellow]Press Enter when you're done to save the log.[/]",
        title="Request Recorder",
        border_style="blue"
    ))

    recorder = RequestRecorder()

    try:
        await recorder.start()

        console.print("[bold yellow]>>> Now manually operate the browser <<<[/]")
        console.print("[dim]Login, browse courses, try selecting/dropping courses, etc.[/]")
        console.print("[dim]All requests will be recorded below:[/]\n")

        # Wait for user to finish
        await asyncio.get_event_loop().run_in_executor(
            None,
            input,
            "\n[Press Enter when done recording...]\n"
        )

        # Save and summarize
        log_path = recorder.save_log()
        recorder.generate_summary()

        console.print(f"\n[green]Log saved to:[/] {log_path}")
        console.print("\n[dim]You can now analyze this log file to understand the API structure.[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Recording stopped.[/]")
        if recorder.requests:
            log_path = recorder.save_log()
            recorder.generate_summary()
            console.print(f"\n[green]Log saved to:[/] {log_path}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        import traceback
        traceback.print_exc()
    finally:
        await recorder.close()


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=ResourceWarning)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())
