"""
NTNU Browser-Based Client.

Uses headless browser (nodriver) to bypass anti-bot detection.
Extracts cookies after login for use with faster HTTP client.

✅ CONFIRMED from recorded API logs:
- Input field names: userid, password, validateCode, checkTW - CONFIRMED
- Login URL: LoginCheckCtrl?action=login&id={sessionId}

⚠️ UNVERIFIED PARTS:
- Success indicators (IndexCtrl, 登出, 選課) - GUESSED

✅ CONFIRMED Error Messages (2026-01-21 via Chrome DevTools MCP):
- "無此學號" - Invalid student ID
- Response format: {"success": false, "msg": "error message"}
"""

import asyncio
from typing import Any
from uuid import UUID

from app.anti_detection.human_behavior import (
    HumanBehaviorSimulator,
    simulate_reading,
    simulate_scroll_behavior,
)
from app.config import get_settings
from app.core.exceptions import NTNULoginError
from app.core.operation_logger import (
    OperationLogger,
    OperationStatus,
    OperationType,
)
from app.services.captcha_service import get_captcha_service
from app.services.session_manager import get_session_manager

settings = get_settings()


class NTNUBrowserClient:
    """
    Browser-based client for NTNU system.

    Uses real Chrome browser via nodriver to bypass anti-bot detection.
    After successful login, cookies can be extracted for use with
    the faster NTNUClient (curl_cffi based).
    """

    BASE_URL = settings.ntnu_base_url

    def __init__(
        self,
        ntnu_account_id: UUID,
        simulate_human: bool = True,
    ) -> None:
        """
        Initialize browser client.

        Args:
            ntnu_account_id: UUID of the NTNU account
            simulate_human: Whether to simulate human-like behavior (typing delays, mouse movement)
        """
        self.ntnu_account_id = ntnu_account_id
        self._browser = None
        self._page = None
        self._session_manager = get_session_manager()
        self._captcha_service = get_captcha_service()
        self._cookies: dict[str, str] = {}
        self._simulate_human = simulate_human
        self._human_simulator: HumanBehaviorSimulator | None = None
        self._logger = OperationLogger("browser_client", str(ntnu_account_id))

    async def _ensure_browser(self) -> None:
        """Ensure browser is started."""
        if self._browser is None:
            try:
                import nodriver as uc
            except ImportError:
                raise RuntimeError(
                    "nodriver is required for browser-based login. "
                    "Install with: pip install nodriver"
                )

            self._browser = await uc.start(
                headless=settings.browser_headless,  # False in dev to see browser
                browser_args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    # Required for running as root in Docker
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            self._page = await self._browser.get("about:blank")

            # Initialize human behavior simulator
            if self._simulate_human and self._page:
                self._human_simulator = HumanBehaviorSimulator(self._page)

    async def login(
        self,
        student_id: str,
        password: str,
        captcha_answer: str | None = None,
    ) -> dict[str, Any]:
        """
        Login to NTNU system using browser.

        If captcha_answer is not provided, will attempt OCR.

        Args:
            student_id: Student ID
            password: Password
            captcha_answer: Pre-solved captcha (optional)

        Returns:
            Dict with login result and cookies

        Raises:
            NTNULoginError: If login fails
        """
        await self._logger.log(
            OperationType.LOGIN, OperationStatus.STARTED,
            f"Starting browser login for student: {student_id[:4]}****"
        )

        await self._ensure_browser()

        if not self._page:
            raise NTNULoginError("Browser page not available")

        try:
            # Step 1: Navigate to login page
            await self._logger.log_step(1, 6, "Navigating to login page", OperationType.BROWSER)
            login_url = f"{self.BASE_URL}/LoginCheckCtrl?language=TW"
            await self._page.get(login_url)

            # Simulate human reading the page
            if self._simulate_human and self._human_simulator:
                await simulate_reading(min_seconds=1.5, max_seconds=3.0)
                # Simulate looking around the page with mouse movement
                await self._human_simulator.random_mouse_movement(movements=2)
                # Small scroll to view the form
                await simulate_scroll_behavior(self._page, scroll_count=1)
                await simulate_reading(min_seconds=0.5, max_seconds=1.0)
            else:
                await asyncio.sleep(2)

            # Step 2: Fill login form
            await self._logger.log_step(2, 6, "Locating form fields", OperationType.BROWSER)
            # ✅ CONFIRMED: Input field names from recorded API logs
            userid_input = await self._page.select("input[name='userid']")  # ✅ confirmed
            password_input = await self._page.select("input[name='password']")  # ✅ confirmed
            captcha_input = await self._page.select("input[name='validateCode']")  # ✅ confirmed

            if not all([userid_input, password_input, captcha_input]):
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Could not find login form fields"
                )
                raise NTNULoginError("Could not find login form fields")

            # Fill form with human-like behavior
            if self._simulate_human and self._human_simulator:
                # Hover over userid field before clicking
                await self._human_simulator.hover_element(userid_input)
                await simulate_reading(min_seconds=0.2, max_seconds=0.4)

                # Type student ID with natural delays and occasional typos
                await self._human_simulator.type_text(userid_input, student_id, make_typos=True)
                await simulate_reading(min_seconds=0.3, max_seconds=0.6)

                # Random mouse movement before next field (like looking around)
                await self._human_simulator.random_mouse_movement(movements=1)

                # Type password (no typos for security - use fill_form_field)
                await self._human_simulator.fill_form_field(password_input, password)
                await simulate_reading(min_seconds=0.2, max_seconds=0.5)
            else:
                # Fast mode: direct input
                await userid_input.clear_input()
                await userid_input.send_keys(student_id)
                await password_input.clear_input()
                await password_input.send_keys(password)

            # Step 3: Handle captcha
            await self._logger.log_step(3, 6, "Solving captcha", OperationType.CAPTCHA)
            if captcha_answer is None:
                # Simulate looking at captcha image before solving
                if self._simulate_human and self._human_simulator:
                    # Hover over captcha image to look at it
                    captcha_img_elem = await self._page.select("img[src*='RandImage']")
                    if captcha_img_elem:
                        await self._human_simulator.hover_element(captcha_img_elem)
                    await simulate_reading(min_seconds=1.0, max_seconds=2.0)

                # Get captcha image and solve with OCR
                captcha_image = await self._get_captcha_image()
                if captcha_image:
                    captcha_answer = self._captcha_service.solve(captcha_image)
                    await self._logger.log(
                        OperationType.CAPTCHA, OperationStatus.SUCCESS,
                        f"Captcha solved: {captcha_answer}"
                    )

            if not captcha_answer:
                await self._logger.log(
                    OperationType.CAPTCHA, OperationStatus.FAILED,
                    "Could not solve captcha"
                )
                raise NTNULoginError("Could not solve captcha")

            # Fill captcha with human-like behavior
            await self._logger.log_step(4, 6, "Filling form fields", OperationType.BROWSER)
            if self._simulate_human and self._human_simulator:
                # Type captcha slowly and carefully (no typos)
                await self._human_simulator.fill_form_field(captcha_input, captcha_answer)

                # Brief pause and random movement (like double-checking inputs)
                await simulate_reading(min_seconds=0.5, max_seconds=1.0)
                await self._human_simulator.random_mouse_movement(movements=1)
                await simulate_reading(min_seconds=0.3, max_seconds=0.6)
            else:
                await captcha_input.clear_input()
                await captcha_input.send_keys(captcha_answer)

            # Step 5: Submit form
            await self._logger.log_step(5, 6, "Submitting login form", OperationType.LOGIN)
            if self._simulate_human and self._human_simulator:
                # Find and click submit button naturally with mouse movement
                submit_btn = await self._page.select("input[type='submit'], button[type='submit']")
                if submit_btn:
                    # Hover before clicking (like aiming)
                    await self._human_simulator.hover_element(submit_btn)
                    await simulate_reading(min_seconds=0.2, max_seconds=0.4)
                    await self._human_simulator.click_element(submit_btn)
                else:
                    await self._page.evaluate("document.forms[0].submit()")
            else:
                await self._page.evaluate("document.forms[0].submit()")

            # Wait for page load
            if self._simulate_human:
                await simulate_reading(min_seconds=2.0, max_seconds=4.0)
            else:
                await asyncio.sleep(3)

            # Step 6: Check login result
            await self._logger.log_step(6, 6, "Checking login result", OperationType.LOGIN)
            current_url = self._page.url
            page_content = await self._page.get_content()

            # Check for errors
            # ✅ CONFIRMED via Chrome DevTools MCP (2026-01-21)
            if "無此學號" in page_content:  # ✅ CONFIRMED
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Invalid student ID (無此學號)"
                )
                raise NTNULoginError("Invalid student ID")
            if "驗證碼錯誤" in page_content:  # ⚠️ GUESSED
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Captcha incorrect (驗證碼錯誤)"
                )
                raise NTNULoginError("Captcha incorrect")
            if "帳號或密碼錯誤" in page_content:  # ⚠️ GUESSED
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Invalid credentials (帳號或密碼錯誤)"
                )
                raise NTNULoginError("Invalid credentials")
            if "不合法執行選課系統" in page_content:  # ✅ CONFIRMED
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Anti-bot detection triggered (不合法執行選課系統)"
                )
                raise NTNULoginError("Anti-bot detection triggered")

            # Check for success
            # ⚠️ Success indicators are GUESSED - need to verify from actual successful login
            login_success = False
            if "IndexCtrl" in current_url:  # ⚠️ GUESSED
                login_success = True
            elif "登出" in page_content or "選課" in page_content:  # ⚠️ GUESSED
                login_success = True

            if not login_success:
                await self._logger.log(
                    OperationType.LOGIN, OperationStatus.FAILED,
                    "Login failed - unknown error",
                    {"url": current_url}
                )
                raise NTNULoginError("Login failed - unknown error")

            # Simulate human browsing after successful login
            if self._simulate_human and self._human_simulator:
                await simulate_reading(min_seconds=1.0, max_seconds=2.0)
                await self._human_simulator.random_mouse_movement(movements=2)
                await simulate_scroll_behavior(self._page, scroll_count=2)
                await simulate_reading(min_seconds=0.5, max_seconds=1.0)

            # Extract cookies
            self._cookies = await self._extract_cookies()

            # Save session
            session_id = self._cookies.get("JSESSIONID", "")
            await self._session_manager.save_session(
                self.ntnu_account_id,
                self._cookies,
                session_id,
            )

            await self._logger.log(
                OperationType.LOGIN, OperationStatus.SUCCESS,
                "Login successful!",
                {"session_id": session_id[:8] + "..." if session_id else "N/A"}
            )

            return {
                "success": True,
                "message": "Login successful",
                "session_id": session_id,
                "cookies": self._cookies,
            }

        except NTNULoginError:
            raise
        except Exception as e:
            await self._logger.log(
                OperationType.LOGIN, OperationStatus.FAILED,
                f"Browser error: {e}"
            )
            raise NTNULoginError(f"Browser login error: {e}")

    async def _get_captcha_image(self) -> bytes | None:
        """Get captcha image from current page."""
        if not self._page:
            return None

        try:
            # Find captcha image element
            captcha_img = await self._page.select("img[src*='RandImage']")
            if captcha_img:
                # Get image source
                src = await self._page.evaluate(
                    "document.querySelector(\"img[src*='RandImage']\").src"
                )
                if src:
                    # Fetch image
                    response = await self._page.evaluate(f"""
                        fetch('{src}')
                            .then(r => r.arrayBuffer())
                            .then(b => Array.from(new Uint8Array(b)))
                    """)
                    if response:
                        return bytes(response)
        except Exception:
            pass

        return None

    async def _extract_cookies(self) -> dict[str, str]:
        """Extract cookies from browser."""
        if not self._page:
            return {}

        try:
            # Get cookies via CDP
            import nodriver as uc
            cookies_response = await self._page.send(
                uc.cdp.network.get_cookies()
            )
            cookies = {}
            for cookie in cookies_response:
                if "ntnu.edu.tw" in cookie.domain:
                    cookies[cookie.name] = cookie.value
            return cookies
        except Exception:
            return {}

    def get_cookies(self) -> dict[str, str]:
        """Get extracted cookies for use with HTTP client."""
        return self._cookies.copy()

    async def close(self) -> None:
        """Close browser."""
        if self._browser:
            try:
                self._browser.stop()
            except Exception:
                pass
            self._browser = None
            self._page = None


async def browser_login_and_get_cookies(
    ntnu_account_id: UUID,
    student_id: str,
    password: str,
    captcha_answer: str | None = None,
) -> dict[str, str]:
    """
    Convenience function to login via browser and get cookies.

    Args:
        ntnu_account_id: Account UUID
        student_id: Student ID
        password: Password
        captcha_answer: Pre-solved captcha (optional)

    Returns:
        Dict of cookies
    """
    client = NTNUBrowserClient(ntnu_account_id)
    try:
        result = await client.login(student_id, password, captcha_answer)
        return result.get("cookies", {})
    finally:
        await client.close()
