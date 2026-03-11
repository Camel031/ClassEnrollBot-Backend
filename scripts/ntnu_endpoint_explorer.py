#!/usr/bin/env python3
"""
NTNU Course System API Endpoint Explorer

This script automatically discovers API endpoints by:
1. Intercepting all network requests during browsing
2. Extracting API patterns from JavaScript files
3. Automatically navigating through menu items
4. Generating a comprehensive endpoint report
"""

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import nodriver as uc
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

# Configuration
BASE_URL = "https://cos2s.ntnu.edu.tw/AasEnrollStudent"
LOG_DIR = Path(__file__).parent / "explorer_logs"
LOG_DIR.mkdir(exist_ok=True)

console = Console()


@dataclass
class APIEndpoint:
    """Represents a discovered API endpoint."""
    url: str
    method: str
    action: str | None = None
    params: dict = field(default_factory=dict)
    request_body: dict | None = None
    response_sample: str | None = None
    source: str = "network"  # network, js_analysis, manual
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EndpointRegistry:
    """Registry of all discovered endpoints."""
    endpoints: dict[str, APIEndpoint] = field(default_factory=dict)
    js_files: list[str] = field(default_factory=list)
    raw_requests: list[dict] = field(default_factory=list)

    def add_endpoint(self, endpoint: APIEndpoint) -> bool:
        """Add endpoint if not already exists. Returns True if new."""
        key = f"{endpoint.method}:{endpoint.url}:{endpoint.action or ''}"
        if key not in self.endpoints:
            self.endpoints[key] = endpoint
            return True
        return False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "endpoints": [
                {
                    "url": ep.url,
                    "method": ep.method,
                    "action": ep.action,
                    "params": ep.params,
                    "request_body": ep.request_body,
                    "response_sample": ep.response_sample[:500] if ep.response_sample else None,
                    "source": ep.source,
                }
                for ep in self.endpoints.values()
            ],
            "js_files": self.js_files,
            "total_requests_captured": len(self.raw_requests),
        }


class NTNUEndpointExplorer:
    """Automated endpoint explorer for NTNU course system."""

    def __init__(self):
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None
        self.registry = EndpointRegistry()
        self.is_logged_in = False

    async def start_browser(self) -> None:
        """Start browser with network interception enabled."""
        console.print("[bold]Starting browser...[/]")

        self.browser = await uc.start(
            headless=False,  # Need visible browser for manual captcha
            browser_args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )

        self.page = await self.browser.get("about:blank")

        # Enable CDP for network interception
        await self._setup_network_interception()

        console.print("[green]Browser started with network interception enabled[/]")

    async def _setup_network_interception(self) -> None:
        """Setup CDP network interception to capture all requests."""
        if not self.page:
            return

        # Enable network domain
        await self.page.send(uc.cdp.network.enable())

        # Add event listeners for network events
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

        # Only capture requests to NTNU system
        if "ntnu.edu.tw" not in url:
            return

        # Parse URL
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Extract action parameter if present
        action = query_params.get("action", [None])[0]

        # Store raw request
        self.registry.raw_requests.append({
            "url": url,
            "method": request.method,
            "headers": dict(request.headers) if request.headers else {},
            "post_data": request.post_data if hasattr(request, "post_data") else None,
            "timestamp": datetime.now().isoformat(),
        })

        # Create endpoint record for API calls
        if "Ctrl" in url or "action=" in url:
            endpoint = APIEndpoint(
                url=f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
                method=request.method,
                action=action,
                params={k: v[0] if len(v) == 1 else v for k, v in query_params.items()},
                source="network",
            )

            if self.registry.add_endpoint(endpoint):
                console.print(f"[cyan]NEW[/] {request.method} {parsed.path}?action={action or 'N/A'}")

    def _on_response(self, event: uc.cdp.network.ResponseReceived) -> None:
        """Handle responses (for capturing response samples)."""
        # Response handling is limited in CDP without additional setup
        pass

    async def login(self, student_id: str, password: str) -> bool:
        """Login to NTNU system with manual captcha input."""
        if not self.page:
            return False

        console.print("\n[bold]Step 1: Loading login page...[/]")

        # Navigate to login page
        await self.page.get(f"{BASE_URL}/LoginCheckCtrl?language=TW")
        await asyncio.sleep(2)

        # Find and fill login form
        console.print("[bold]Step 2: Filling login form...[/]")

        try:
            # Find input fields
            userid_input = await self.page.select("input[name='userid']")
            password_input = await self.page.select("input[name='password']")
            captcha_input = await self.page.select("input[name='validateCode']")

            if not all([userid_input, password_input, captcha_input]):
                console.print("[red]Could not find login form fields[/]")
                return False

            # Fill credentials
            await userid_input.clear_input()
            await userid_input.send_keys(student_id)

            await password_input.clear_input()
            await password_input.send_keys(password)

            # Wait for user to solve captcha
            console.print("\n[yellow]Please solve the captcha in the browser window[/]")
            captcha_code = Prompt.ask("Enter the captcha code you see")

            await captcha_input.clear_input()
            await captcha_input.send_keys(captcha_code)

            # Click login button
            console.print("[bold]Step 3: Submitting login...[/]")

            # Try multiple methods to submit
            submitted = False

            # Method 1: Try various button selectors
            button_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "input[type='button']",
                ".x-btn",
                "a.x-btn",
                "#loginBtn",
                "[onclick*='login']",
                "button",
            ]

            for selector in button_selectors:
                try:
                    login_btn = await self.page.select(selector)
                    if login_btn:
                        # Get button info via JavaScript
                        try:
                            btn_info = await self.page.evaluate(f"""
                                (() => {{
                                    const btn = document.querySelector('{selector}');
                                    return btn ? (btn.textContent || btn.value || '{selector}') : null;
                                }})()
                            """)
                            console.print(f"[dim]Found button: {selector} - {btn_info}[/]")
                        except Exception:
                            console.print(f"[dim]Found button: {selector}[/]")
                        await login_btn.click()
                        submitted = True
                        break
                except Exception:
                    pass

            # Method 2: Submit form via JavaScript
            if not submitted:
                console.print("[yellow]Trying JavaScript form submission...[/]")
                try:
                    await self.page.evaluate("document.forms[0].submit()")
                    submitted = True
                except Exception:
                    pass

            # Method 3: Press Enter on captcha field
            if not submitted:
                console.print("[yellow]Trying Enter key...[/]")
                await captcha_input.send_keys("\n")

            await asyncio.sleep(3)

            # Check current URL
            current_url = self.page.url
            console.print(f"[dim]Current URL: {current_url}[/]")

            # Check if login successful
            if "IndexCtrl" in current_url or "index" in current_url.lower():
                console.print("[bold green]Login successful![/]")
                self.is_logged_in = True
                return True

            # Check page content
            page_text = await self.page.get_content()

            # Check for success indicators
            if "登出" in page_text or "選課" in page_text or "課程" in page_text:
                console.print("[bold green]Login successful (detected menu content)![/]")
                self.is_logged_in = True
                return True

            # Check for error messages
            if "驗證碼錯誤" in page_text:
                console.print("[red]Captcha incorrect[/]")
                return False
            if "帳號或密碼錯誤" in page_text or "密碼錯誤" in page_text:
                console.print("[red]Invalid credentials[/]")
                return False

            # Manual confirmation
            console.print("\n[yellow]Could not auto-detect login status.[/]")
            console.print("Please check the browser window.")
            confirm = Prompt.ask("Is login successful? (y/n)", default="y")
            if confirm.lower() == "y":
                self.is_logged_in = True
                return True

            # Allow retry
            retry = Prompt.ask("Retry login? (y/n)", default="y")
            if retry.lower() == "y":
                return await self.login(student_id, password)

            return False

        except Exception as e:
            console.print(f"[red]Login error: {e}[/]")
            return False

    async def explore_menus(self) -> None:
        """Automatically click through menu items to discover endpoints."""
        if not self.page or not self.is_logged_in:
            console.print("[red]Must be logged in to explore menus[/]")
            return

        console.print("\n[bold]Exploring menu items...[/]")

        # Wait for page to fully load
        await asyncio.sleep(2)

        # ExtJS typically uses these selectors for menu items
        menu_selectors = [
            ".x-menu-item",
            ".x-tree-node",
            ".x-panel-header",
            "[class*='menu']",
            "a[href*='Ctrl']",
            "button[onclick*='Ctrl']",
        ]

        discovered_items = set()

        # Use JavaScript to find menu items more reliably
        for selector in menu_selectors:
            try:
                items = await self.page.evaluate(f"""
                    Array.from(document.querySelectorAll('{selector}'))
                        .slice(0, 20)
                        .map(el => el.textContent.trim())
                        .filter(t => t && t.length < 50)
                """)
                if items:
                    console.print(f"[dim]Found {len(items)} elements with selector: {selector}[/]")
                    for text in items:
                        if text and text not in discovered_items:
                            discovered_items.add(text)
                            console.print(f"[dim]  Menu item: {text}[/]")
            except Exception:
                pass

        console.print(f"\n[green]Found {len(discovered_items)} menu items[/]")

        # Interactive exploration
        console.print("\n[yellow]Starting interactive exploration...[/]")
        console.print("Instructions:")
        console.print("  - Click through the system manually in the browser")
        console.print("  - All network requests are being captured")
        console.print("  - Press Enter here when done exploring")

        await asyncio.get_event_loop().run_in_executor(None, input, "")

    async def analyze_js_files(self) -> None:
        """Extract API endpoints from loaded JavaScript files."""
        if not self.page:
            return

        console.print("\n[bold]Analyzing JavaScript files...[/]")

        # Get all script sources using JavaScript evaluation
        try:
            js_urls_result = await self.page.evaluate("""
                Array.from(document.querySelectorAll('script[src]'))
                    .map(s => s.src)
                    .filter(src => src.includes('ntnu.edu.tw'))
            """)
            js_urls = js_urls_result if js_urls_result else []
            self.registry.js_files.extend(js_urls)
        except Exception as e:
            console.print(f"[yellow]Could not get JS file list: {e}[/]")
            js_urls = []

        console.print(f"[dim]Found {len(js_urls)} JavaScript files[/]")

        # Patterns to find API endpoints in JS code
        api_patterns = [
            r"url\s*:\s*['\"]([^'\"]*Ctrl[^'\"]*)['\"]",
            r"action\s*:\s*['\"](\w+)['\"]",
            r"['\"]([^'\"]*\?action=\w+)['\"]",
            r"ajax\(['\"]([^'\"]+)['\"]",
            r"\.load\(['\"]([^'\"]+)['\"]",
            r"proxy\s*:\s*\{[^}]*url\s*:\s*['\"]([^'\"]+)['\"]",
        ]

        # Get inline scripts content using JavaScript
        try:
            all_js_content = await self.page.evaluate("""
                Array.from(document.querySelectorAll('script:not([src])'))
                    .map(s => s.textContent)
                    .join('\\n')
            """)
            all_js_content = all_js_content or ""
        except Exception as e:
            console.print(f"[yellow]Could not get inline scripts: {e}[/]")
            all_js_content = ""

        # Extract patterns
        found_patterns = set()
        for pattern in api_patterns:
            matches = re.findall(pattern, all_js_content, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 3:
                    found_patterns.add(match)

        console.print(f"[green]Found {len(found_patterns)} potential endpoints in inline JS[/]")

        for pattern in sorted(found_patterns):
            # Determine if it's an action or full URL
            if pattern.startswith("http") or pattern.startswith("/"):
                url = pattern
                action = None
                if "action=" in pattern:
                    action = re.search(r"action=(\w+)", pattern)
                    action = action.group(1) if action else None
            else:
                url = f"{BASE_URL}/AjaxCtrl"
                action = pattern

            endpoint = APIEndpoint(
                url=url,
                method="GET/POST",
                action=action,
                source="js_analysis",
            )

            if self.registry.add_endpoint(endpoint):
                console.print(f"[cyan]JS[/] Found: {action or url}")

    async def explore_known_endpoints(self) -> None:
        """Try accessing known/common NTNU endpoints."""
        if not self.page or not self.is_logged_in:
            return

        console.print("\n[bold]Probing known endpoint patterns...[/]")

        # Common NTNU endpoint patterns based on ExtJS conventions
        known_patterns = [
            # Course operations
            ("CourseCtrl", "getCourseList", "GET"),
            ("CourseCtrl", "getCourseDetail", "GET"),
            ("CourseCtrl", "searchCourse", "GET"),
            # Enrollment operations
            ("EnrollCtrl", "getEnrollList", "GET"),
            ("EnrollCtrl", "addCourse", "POST"),
            ("EnrollCtrl", "dropCourse", "POST"),
            ("EnrollCtrl", "getSelectedCourses", "GET"),
            # Student info
            ("StudentCtrl", "getStudentInfo", "GET"),
            ("StudentCtrl", "getEnrollStatus", "GET"),
            # General
            ("AjaxCtrl", "getCourseList", "GET"),
            ("AjaxCtrl", "getAnnouncement", "GET"),
            ("IndexCtrl", None, "GET"),
            ("MainCtrl", None, "GET"),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Probing endpoints...", total=len(known_patterns))

            for ctrl, action, method in known_patterns:
                if action:
                    url = f"{BASE_URL}/{ctrl}?action={action}"
                else:
                    url = f"{BASE_URL}/{ctrl}"

                try:
                    # Navigate to trigger request capture
                    if method == "GET":
                        # Use JavaScript to make request without navigation
                        js_code = f"""
                        fetch('{url}', {{
                            method: 'GET',
                            credentials: 'include'
                        }}).then(r => r.text()).then(t => console.log('Response length:', t.length));
                        """
                        await self.page.evaluate(js_code)
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                progress.advance(task)

    def generate_report(self) -> str:
        """Generate a comprehensive endpoint report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = LOG_DIR / f"endpoint_report_{timestamp}.json"

        # Save JSON report
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.registry.to_dict(), f, ensure_ascii=False, indent=2)

        # Save raw requests log
        raw_log_path = LOG_DIR / f"raw_requests_{timestamp}.json"
        with open(raw_log_path, "w", encoding="utf-8") as f:
            json.dump(self.registry.raw_requests, f, ensure_ascii=False, indent=2)

        # Display summary
        console.print("\n" + "=" * 60)
        console.print("[bold]ENDPOINT DISCOVERY REPORT[/]")
        console.print("=" * 60)

        # Group by source
        by_source: dict[str, list] = {}
        for ep in self.registry.endpoints.values():
            by_source.setdefault(ep.source, []).append(ep)

        for source, endpoints in by_source.items():
            console.print(f"\n[bold]{source.upper()}[/] ({len(endpoints)} endpoints)")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Method", width=8)
            table.add_column("Controller", width=20)
            table.add_column("Action", width=25)
            table.add_column("Params", width=30)

            for ep in sorted(endpoints, key=lambda x: x.action or ""):
                # Extract controller from URL
                ctrl_match = re.search(r"/(\w+Ctrl)", ep.url)
                ctrl = ctrl_match.group(1) if ctrl_match else ep.url[-30:]

                params = ", ".join(f"{k}={v}" for k, v in ep.params.items() if k != "action")
                params = params[:30] + "..." if len(params) > 30 else params

                table.add_row(
                    ep.method,
                    ctrl,
                    ep.action or "-",
                    params or "-"
                )

            console.print(table)

        console.print(f"\n[bold]Summary:[/]")
        console.print(f"  Total endpoints discovered: {len(self.registry.endpoints)}")
        console.print(f"  Total requests captured: {len(self.registry.raw_requests)}")
        console.print(f"  JS files analyzed: {len(self.registry.js_files)}")
        console.print(f"\n[green]Reports saved to:[/]")
        console.print(f"  {report_path}")
        console.print(f"  {raw_log_path}")

        return str(report_path)

    async def close(self) -> None:
        """Close browser."""
        if self.browser:
            try:
                await asyncio.sleep(0.5)  # Allow pending operations to complete
                self.browser.stop()
                await asyncio.sleep(0.5)  # Allow cleanup
            except Exception:
                pass  # Ignore cleanup errors


async def main():
    """Main entry point."""
    console.print(Panel(
        "[bold]NTNU Course System Endpoint Explorer[/]\n\n"
        "This tool automatically discovers API endpoints by:\n"
        "• Intercepting network requests\n"
        "• Analyzing JavaScript code\n"
        "• Probing known endpoint patterns",
        title="Endpoint Explorer",
        border_style="blue"
    ))

    explorer = NTNUEndpointExplorer()

    try:
        # Start browser
        await explorer.start_browser()

        # Get credentials
        console.print("\n[bold]Login Credentials[/]")
        student_id = Prompt.ask("Student ID")
        password = Prompt.ask("Password", password=True)

        # Login
        if not await explorer.login(student_id, password):
            console.print("[red]Login failed. Exiting.[/]")
            return

        # Exploration phase
        console.print("\n[bold]Starting exploration...[/]")

        # Analyze JS files first
        await explorer.analyze_js_files()

        # Probe known endpoints
        await explorer.explore_known_endpoints()

        # Interactive menu exploration
        await explorer.explore_menus()

        # Generate report
        explorer.generate_report()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/]")
        explorer.generate_report()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        import traceback
        traceback.print_exc()
    finally:
        await explorer.close()


if __name__ == "__main__":
    import warnings
    # Suppress asyncio cleanup warnings on Windows
    warnings.filterwarnings("ignore", category=ResourceWarning)

    if sys.platform == "win32":
        # Use ProactorEventLoop for subprocess support on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())
