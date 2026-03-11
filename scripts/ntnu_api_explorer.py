"""
NTNU Course Enrollment System API Explorer

This script helps you explore and capture the actual API endpoints
of the NTNU course enrollment system.

Usage:
    python scripts/ntnu_api_explorer.py

Requirements:
    - pip install curl_cffi ddddocr rich
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import RequestException, Timeout
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

console = Console()

# Constants
BASE_URL = "https://cos2s.ntnu.edu.tw/AasEnrollStudent"
LOG_DIR = Path(__file__).parent / "api_logs"
LOG_DIR.mkdir(exist_ok=True)
REQUEST_TIMEOUT = 30  # seconds


class NTNUApiExplorer:
    """Interactive explorer for NTNU course enrollment API."""

    def __init__(self) -> None:
        self.session = cffi_requests.Session(impersonate="chrome120")
        self.request_log: list[dict[str, Any]] = []
        self.is_logged_in = False

    def _log_request(
        self,
        method: str,
        url: str,
        params: dict | None,
        data: dict | None,
        response: cffi_requests.Response,
    ) -> None:
        """Log request and response details."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "url": url,
            "params": params,
            "data": data,
            "status_code": response.status_code,
            "response_headers": dict(response.headers),
            "response_text": response.text[:5000] if len(response.text) > 5000 else response.text,
            "cookies": dict(self.session.cookies),
        }
        self.request_log.append(log_entry)

        # Print summary
        console.print(f"\n[bold cyan]Request:[/] {method} {url}")
        if params:
            console.print(f"[dim]Params:[/] {params}")
        if data:
            console.print(f"[dim]Data:[/] {data}")
        console.print(f"[bold {'green' if response.status_code == 200 else 'red'}]Status:[/] {response.status_code}")

    def get_captcha(self) -> bytes | None:
        """Fetch captcha image."""
        url = f"{BASE_URL}/RandImage"
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            self._log_request("GET", url, None, None, response)
            return response.content
        except Timeout:
            console.print(f"[red]Request timeout while fetching captcha (>{REQUEST_TIMEOUT}s)[/]")
            return None
        except RequestException as e:
            console.print(f"[red]Connection error while fetching captcha: {e}[/]")
            return None

    def solve_captcha_manual(self, image_bytes: bytes) -> str:
        """Save captcha and ask user to solve it."""
        captcha_path = LOG_DIR / "current_captcha.png"
        captcha_path.write_bytes(image_bytes)
        console.print(f"\n[yellow]Captcha saved to:[/] {captcha_path}")
        console.print("[yellow]Please open the image and enter the captcha code.[/]")
        return Prompt.ask("Enter captcha")

    def solve_captcha_ocr(self, image_bytes: bytes) -> str:
        """Solve captcha using OCR."""
        try:
            import ddddocr
            ocr = ddddocr.DdddOcr(show_ad=False)
            result = ocr.classification(image_bytes)
            console.print(f"[green]OCR Result:[/] {result}")
            return result
        except Exception as e:
            console.print(f"[red]OCR failed:[/] {e}")
            return self.solve_captcha_manual(image_bytes)

    def login(self, student_id: str, password: str, use_ocr: bool = True) -> bool:
        """Login to NTNU system."""
        console.print("\n[bold]Step 1: Loading login page...[/]")

        # Load login page first to get cookies
        login_page_url = f"{BASE_URL}/LoginCheckCtrl?language=TW"
        try:
            response = self.session.get(login_page_url, timeout=REQUEST_TIMEOUT)
            self._log_request("GET", login_page_url, None, None, response)
        except Timeout:
            console.print(f"[red]Request timeout while loading login page (>{REQUEST_TIMEOUT}s)[/]")
            return False
        except RequestException as e:
            console.print(f"[red]Connection error while loading login page: {e}[/]")
            return False

        if response.status_code != 200:
            console.print("[red]Failed to load login page[/]")
            return False

        # Get and solve captcha
        console.print("\n[bold]Step 2: Getting captcha...[/]")
        max_attempts = 3
        for attempt in range(max_attempts):
            captcha_image = self.get_captcha()

            if captcha_image is None:
                console.print("[red]Failed to fetch captcha image[/]")
                if attempt < max_attempts - 1:
                    retry = Prompt.ask("Retry? (y/n)", default="y")
                    if retry.lower() == "y":
                        continue
                return False

            if use_ocr:
                captcha_answer = self.solve_captcha_ocr(captcha_image)
                confirm = Prompt.ask(f"Use OCR result '{captcha_answer}'? (y/n)", default="y")
                if confirm.lower() != "y":
                    captcha_answer = Prompt.ask("Enter captcha manually")
            else:
                captcha_answer = self.solve_captcha_manual(captcha_image)

            # Submit login
            console.print("\n[bold]Step 3: Submitting login...[/]")
            login_url = f"{BASE_URL}/LoginCheckCtrl?action=login"
            login_data = {
                "userid": student_id,
                "password": password,
                "validateCode": captcha_answer,
            }

            # ExtJS typically sends these headers
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": login_page_url,
                "Origin": "https://cos2s.ntnu.edu.tw",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            try:
                response = self.session.post(
                    login_url, data=login_data, headers=headers,
                    allow_redirects=True, timeout=REQUEST_TIMEOUT
                )
                self._log_request("POST", login_url, None, {"userid": student_id, "validateCode": captcha_answer}, response)
            except Timeout:
                console.print(f"[red]Request timeout while submitting login (>{REQUEST_TIMEOUT}s)[/]")
                if attempt < max_attempts - 1:
                    retry = Prompt.ask("Retry? (y/n)", default="y")
                    if retry.lower() == "y":
                        continue
                return False
            except RequestException as e:
                console.print(f"[red]Connection error while submitting login: {e}[/]")
                if attempt < max_attempts - 1:
                    retry = Prompt.ask("Retry? (y/n)", default="y")
                    if retry.lower() == "y":
                        continue
                return False

            console.print(f"[dim]Response URL:[/] {response.url}")
            console.print(f"[dim]Response length:[/] {len(response.text)} bytes")
            console.print(f"[dim]Cookies:[/] {dict(self.session.cookies)}")

            # Check login result - multiple methods
            login_success = False

            # Method 1: Check JSON response
            try:
                if response.text.strip():
                    result = response.json()
                    console.print(f"[dim]Response JSON:[/] {json.dumps(result, ensure_ascii=False, indent=2)}")

                    if result.get("success") is True:
                        login_success = True
                    elif "msg" in result:
                        error_msg = result.get("msg", "Unknown error")
                        console.print(f"[red]Login failed:[/] {error_msg}")
                        if "驗證碼" in error_msg and attempt < max_attempts - 1:
                            console.print("[yellow]Retrying with new captcha...[/]")
                            continue
            except json.JSONDecodeError:
                pass

            # Method 2: Check if redirected to index page
            if not login_success and "IndexCtrl" in response.url:
                login_success = True

            # Method 3: Try to access a protected page to verify login
            if not login_success and response.text == "":
                console.print("[yellow]Empty response, verifying login by accessing IndexCtrl...[/]")
                verify_url = f"{BASE_URL}/IndexCtrl"
                try:
                    verify_response = self.session.get(
                        verify_url, headers={"Referer": login_url}, timeout=REQUEST_TIMEOUT
                    )
                    self._log_request("GET", verify_url, None, None, verify_response)
                except Timeout:
                    console.print(f"[red]Request timeout while verifying login (>{REQUEST_TIMEOUT}s)[/]")
                    continue
                except RequestException as e:
                    console.print(f"[red]Connection error while verifying login: {e}[/]")
                    continue

                console.print(f"[dim]Verify URL:[/] {verify_response.url}")
                console.print(f"[dim]Verify response length:[/] {len(verify_response.text)} bytes")

                # If we can access IndexCtrl without being redirected to login, we're logged in
                if "LoginCheckCtrl" not in verify_response.url and len(verify_response.text) > 100:
                    # Check if response contains logged-in user content
                    if "登出" in verify_response.text or "logout" in verify_response.text.lower() or student_id in verify_response.text:
                        login_success = True
                    elif "選課" in verify_response.text or "課程" in verify_response.text:
                        login_success = True
                    else:
                        # Show a snippet of the response for debugging
                        console.print(f"[dim]Verify response snippet:[/] {verify_response.text[:1000]}")
                        manual_check = Prompt.ask("Does this look like a logged-in page? (y/n)", default="n")
                        if manual_check.lower() == "y":
                            login_success = True

            if login_success:
                console.print("[bold green]Login successful![/]")
                self.is_logged_in = True
                return True
            else:
                console.print(f"[dim]Response text:[/] {response.text[:500] if response.text else '(empty)'}")

            if attempt < max_attempts - 1:
                retry = Prompt.ask("Retry login? (y/n)", default="y")
                if retry.lower() != "y":
                    break

        return False

    def explore_endpoints(self) -> None:
        """Interactive endpoint exploration."""
        if not self.is_logged_in:
            console.print("[red]Please login first![/]")
            return

        known_endpoints = [
            ("IndexCtrl", "Main index page after login"),
            ("EnrollCtrl", "Course enrollment controller"),
            ("CourseQueryCtrl", "Course query controller"),
            ("StageCtrl", "Enrollment stage controller"),
            ("Wakeup.do", "Session keepalive"),
        ]

        while True:
            console.print("\n[bold cyan]═══ Endpoint Explorer ═══[/]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("Endpoint", style="cyan")
            table.add_column("Description")

            for i, (endpoint, desc) in enumerate(known_endpoints, 1):
                table.add_row(str(i), endpoint, desc)
            table.add_row("c", "Custom URL", "Enter custom endpoint")
            table.add_row("q", "Quit", "Exit explorer")

            console.print(table)

            choice = Prompt.ask("Select endpoint")

            if choice.lower() == "q":
                break
            elif choice.lower() == "c":
                custom_url = Prompt.ask("Enter full URL or endpoint path")
                if not custom_url.startswith("http"):
                    custom_url = f"{BASE_URL}/{custom_url}"
                self._explore_url(custom_url)
            elif choice.isdigit() and 1 <= int(choice) <= len(known_endpoints):
                endpoint = known_endpoints[int(choice) - 1][0]
                self._explore_url(f"{BASE_URL}/{endpoint}")

    def _explore_url(self, url: str) -> None:
        """Explore a specific URL."""
        console.print(f"\n[bold]Exploring:[/] {url}")

        method = Prompt.ask("HTTP Method", choices=["GET", "POST"], default="GET")

        params = {}
        if Prompt.ask("Add query parameters? (y/n)", default="n").lower() == "y":
            while True:
                key = Prompt.ask("Parameter name (empty to finish)")
                if not key:
                    break
                value = Prompt.ask(f"Value for '{key}'")
                params[key] = value

        data = {}
        if method == "POST":
            if Prompt.ask("Add form data? (y/n)", default="n").lower() == "y":
                while True:
                    key = Prompt.ask("Field name (empty to finish)")
                    if not key:
                        break
                    value = Prompt.ask(f"Value for '{key}'")
                    data[key] = value

        # Make request
        headers = {
            "Referer": f"{BASE_URL}/IndexCtrl",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            if method == "GET":
                response = self.session.get(
                    url, params=params or None, headers=headers, timeout=REQUEST_TIMEOUT
                )
            else:
                response = self.session.post(
                    url, params=params or None, data=data or None,
                    headers=headers, timeout=REQUEST_TIMEOUT
                )
            self._log_request(method, url, params or None, data or None, response)
        except Timeout:
            console.print(f"[red]Request timeout (>{REQUEST_TIMEOUT}s)[/]")
            return
        except RequestException as e:
            console.print(f"[red]Connection error: {e}[/]")
            return

        # Display response
        console.print(f"\n[bold]Response ({len(response.text)} bytes):[/]")

        try:
            json_response = response.json()
            console.print(Panel(
                json.dumps(json_response, ensure_ascii=False, indent=2)[:3000],
                title="JSON Response",
                border_style="green"
            ))
        except json.JSONDecodeError:
            # Try to extract useful info from HTML
            if "<html" in response.text.lower():
                # Extract ExtJS store data or JavaScript variables
                store_matches = re.findall(r'Ext\.create\(["\']Ext\.data\.Store["\'],\s*(\{.*?\})\)', response.text, re.DOTALL)
                if store_matches:
                    console.print("[yellow]Found ExtJS Store definitions:[/]")
                    for match in store_matches[:3]:
                        console.print(match[:500])

                # Extract any JSON-like data
                json_matches = re.findall(r'\{["\']success["\']:\s*(true|false).*?\}', response.text)
                if json_matches:
                    console.print("[yellow]Found JSON-like responses:[/]")
                    for match in json_matches[:3]:
                        console.print(match)

            console.print(Panel(
                response.text[:2000] + ("..." if len(response.text) > 2000 else ""),
                title="Raw Response",
                border_style="yellow"
            ))

    def save_logs(self) -> None:
        """Save all request logs to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOG_DIR / f"api_log_{timestamp}.json"

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self.request_log, f, ensure_ascii=False, indent=2)

        console.print(f"\n[green]Logs saved to:[/] {log_file}")

    def show_summary(self) -> None:
        """Show summary of discovered endpoints."""
        console.print("\n[bold cyan]═══ Session Summary ═══[/]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=3)
        table.add_column("Method", width=6)
        table.add_column("URL")
        table.add_column("Status", width=6)

        for i, log in enumerate(self.request_log, 1):
            status_style = "green" if log["status_code"] == 200 else "red"
            table.add_row(
                str(i),
                log["method"],
                log["url"][:60] + ("..." if len(log["url"]) > 60 else ""),
                f"[{status_style}]{log['status_code']}[/]"
            )

        console.print(table)


def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]NTNU Course Enrollment API Explorer[/]\n"
        "This tool helps you discover and test API endpoints.",
        border_style="cyan"
    ))

    explorer = NTNUApiExplorer()

    # Get credentials
    console.print("\n[bold]Enter your NTNU credentials:[/]")
    student_id = Prompt.ask("Student ID")
    password = Prompt.ask("Password", password=True)

    use_ocr = Prompt.ask("Use OCR for captcha? (y/n)", default="y").lower() == "y"

    # Login
    if explorer.login(student_id, password, use_ocr):
        # Explore endpoints
        explorer.explore_endpoints()

    # Save and show summary
    explorer.save_logs()
    explorer.show_summary()

    console.print("\n[bold green]Done![/] Check the logs directory for captured API data.")


if __name__ == "__main__":
    main()
