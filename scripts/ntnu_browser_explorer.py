"""
NTNU Course Enrollment System Browser-based Explorer

Uses nodriver (undetected Chrome) to bypass anti-bot detection.

Usage:
    python scripts/ntnu_browser_explorer.py

Requirements:
    - pip install nodriver rich
    - Google Chrome installed
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

# Constants
BASE_URL = "https://cos2s.ntnu.edu.tw/AasEnrollStudent"
LOG_DIR = Path(__file__).parent / "api_logs"
LOG_DIR.mkdir(exist_ok=True)


async def main() -> None:
    console.print(Panel.fit(
        "[bold cyan]NTNU Course Enrollment Browser Explorer[/]\n"
        "Uses undetected Chrome to bypass anti-bot detection.",
        border_style="cyan"
    ))

    try:
        import nodriver as uc
    except ImportError:
        console.print("[red]Please install nodriver: pip install nodriver[/]")
        return

    # Get credentials
    console.print("\n[bold]Enter your NTNU credentials:[/]")
    student_id = Prompt.ask("Student ID")
    password = Prompt.ask("Password", password=True)

    console.print("\n[yellow]Starting Chrome browser...[/]")

    # Start browser
    browser = await uc.start(headless=False)  # Set to True for headless mode

    try:
        # Navigate to login page
        console.print("[bold]Step 1: Loading login page...[/]")
        page = await browser.get(f"{BASE_URL}/LoginCheckCtrl?language=TW")

        # Wait for ExtJS to load
        await asyncio.sleep(2)

        console.print("[bold]Step 2: Filling login form...[/]")

        # Find and fill the form fields
        # ExtJS creates input fields dynamically, we need to find them
        try:
            # Try to find userid field
            userid_field = await page.select('input[name="userid"]')
            if userid_field:
                await userid_field.clear_input()
                await userid_field.send_keys(student_id)
                console.print("[green]✓ Filled student ID[/]")
            else:
                # Try alternative selector
                userid_field = await page.select('#userid')
                if userid_field:
                    await userid_field.clear_input()
                    await userid_field.send_keys(student_id)
                    console.print("[green]✓ Filled student ID (alt)[/]")
                else:
                    console.print("[yellow]Could not find userid field, trying JavaScript...[/]")
                    await page.evaluate(f'document.querySelector("input[name=userid]").value = "{student_id}"')
        except Exception as e:
            console.print(f"[red]Error filling userid: {e}[/]")

        await asyncio.sleep(0.5)

        try:
            # Find and fill password field
            password_field = await page.select('input[name="password"]')
            if password_field:
                await password_field.clear_input()
                await password_field.send_keys(password)
                console.print("[green]✓ Filled password[/]")
            else:
                password_field = await page.select('#password')
                if password_field:
                    await password_field.clear_input()
                    await password_field.send_keys(password)
                    console.print("[green]✓ Filled password (alt)[/]")
                else:
                    console.print("[yellow]Could not find password field, trying JavaScript...[/]")
                    await page.evaluate(f'document.querySelector("input[name=password]").value = "{password}"')
        except Exception as e:
            console.print(f"[red]Error filling password: {e}[/]")

        # Handle captcha
        console.print("\n[bold]Step 3: Captcha handling...[/]")
        console.print("[yellow]Please solve the captcha manually in the browser window.[/]")

        # Wait for user to solve captcha and click login
        captcha_answer = Prompt.ask("Enter the captcha code you see")

        try:
            captcha_field = await page.select('input[name="validateCode"]')
            if captcha_field:
                await captcha_field.clear_input()
                await captcha_field.send_keys(captcha_answer)
                console.print("[green]✓ Filled captcha[/]")
            else:
                await page.evaluate(f'document.querySelector("input[name=validateCode]").value = "{captcha_answer}"')
        except Exception as e:
            console.print(f"[red]Error filling captcha: {e}[/]")

        # Click login button
        console.print("\n[bold]Step 4: Clicking login button...[/]")

        try:
            # Try to find and click the login button
            # ExtJS buttons might have specific classes or text content
            login_btn = await page.select('a.x-btn')  # ExtJS button
            if login_btn:
                await login_btn.click()
                console.print("[green]✓ Clicked login button[/]")
            else:
                # Try to submit the form via JavaScript
                console.print("[yellow]Trying JavaScript form submission...[/]")
                await page.evaluate('''
                    // Find the ExtJS form and submit it
                    var forms = Ext.ComponentQuery.query('form');
                    if (forms.length > 0) {
                        forms[0].submit();
                    }
                ''')
        except Exception as e:
            console.print(f"[yellow]Button click failed: {e}[/]")
            console.print("[yellow]Please click the login button manually in the browser.[/]")

        # Wait for login to complete
        console.print("\n[yellow]Waiting for login to complete...[/]")
        await asyncio.sleep(3)

        # Check current URL and page content
        current_url = page.url
        console.print(f"[dim]Current URL:[/] {current_url}")

        # Get page content
        html_content = await page.get_content()

        # Check if login was successful
        if "IndexCtrl" in current_url or "選課" in html_content:
            console.print("[bold green]Login appears successful![/]")

            # Save cookies for later use
            cookies = await browser.cookies.get_all()
            cookie_data = {c.name: c.value for c in cookies}
            console.print(f"[dim]Cookies:[/] {cookie_data}")

            # Save session data
            session_file = LOG_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "cookies": cookie_data,
                    "url": current_url,
                }, f, ensure_ascii=False, indent=2)
            console.print(f"[green]Session saved to:[/] {session_file}")

            # Now explore the system
            await explore_system(page, browser)
        else:
            console.print("[red]Login may have failed.[/]")
            console.print(f"[dim]Page content snippet:[/] {html_content[:1000]}")

            # Check for error messages
            if "錯誤" in html_content or "失敗" in html_content:
                console.print("[red]Error detected in page content[/]")

        # Keep browser open for manual exploration
        console.print("\n[yellow]Browser will stay open for manual exploration.[/]")
        console.print("[yellow]Press Enter to close...[/]")
        input()

    finally:
        browser.stop()


async def explore_system(page, browser) -> None:
    """Explore the course enrollment system after login."""
    console.print("\n[bold cyan]═══ System Exploration ═══[/]")

    endpoints_to_try = [
        ("EnrollCtrl", "Enrollment page"),
        ("CourseQueryCtrl", "Course query"),
        ("StageCtrl", "Stage controller"),
        ("MyEnrollCtrl", "My enrollments"),
        ("ResultCtrl", "Results"),
    ]

    request_log = []

    for endpoint, desc in endpoints_to_try:
        console.print(f"\n[bold]Trying {endpoint}...[/]")

        try:
            url = f"{BASE_URL}/{endpoint}"
            await page.get(url)
            await asyncio.sleep(1)

            html = await page.get_content()
            current_url = page.url

            # Log the request
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": endpoint,
                "url": current_url,
                "description": desc,
                "response_length": len(html),
                "contains_error": "錯誤" in html or "不合法" in html,
                "snippet": html[:1000],
            }
            request_log.append(log_entry)

            if "錯誤" in html or "不合法" in html:
                console.print(f"[red]✗ {endpoint}: Error page[/]")
            elif len(html) > 500:
                console.print(f"[green]✓ {endpoint}: Got response ({len(html)} bytes)[/]")
            else:
                console.print(f"[yellow]? {endpoint}: Short response ({len(html)} bytes)[/]")

        except Exception as e:
            console.print(f"[red]✗ {endpoint}: {e}[/]")
            request_log.append({
                "timestamp": datetime.now().isoformat(),
                "endpoint": endpoint,
                "error": str(e),
            })

    # Save exploration log
    log_file = LOG_DIR / f"browser_exploration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(request_log, f, ensure_ascii=False, indent=2)
    console.print(f"\n[green]Exploration log saved to:[/] {log_file}")


if __name__ == "__main__":
    asyncio.run(main())
