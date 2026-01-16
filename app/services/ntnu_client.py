"""NTNU Course Enrollment System API Client."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from curl_cffi import requests as cffi_requests
from tenacity import retry, stop_after_attempt, wait_exponential

from app.anti_detection.fingerprint import get_fingerprint_config
from app.anti_detection.headers import get_ajax_headers, get_browser_headers
from app.anti_detection.rate_limiter import RequestType, get_rate_limiter
from app.config import get_settings
from app.core.exceptions import (
    NTNUClientError,
    NTNULoginError,
    NTNUSessionExpiredError,
)
from app.services.captcha_service import get_captcha_service
from app.services.session_manager import get_session_manager

settings = get_settings()


class NTNUClient:
    """
    Client for interacting with NTNU Course Enrollment System.
    Uses curl_cffi for TLS fingerprint impersonation.
    """

    BASE_URL = settings.ntnu_base_url

    # API endpoints
    ENDPOINTS = {
        "login_page": "/LoginCheckCtrl?language=TW",
        "login": "/LoginCheckCtrl?action=login",
        "captcha": "/RandImage",
        "wakeup": "/Wakeup.do",
        "index": "/IndexCtrl",
        "course_list": "/CourseListCtrl",
        "enroll": "/EnrollCtrl",
    }

    def __init__(self, ntnu_account_id: UUID) -> None:
        """
        Initialize NTNU client for a specific account.

        Args:
            ntnu_account_id: UUID of the NTNU account
        """
        self.ntnu_account_id = ntnu_account_id
        self._session: cffi_requests.Session | None = None
        self._fingerprint = get_fingerprint_config()
        self._rate_limiter = get_rate_limiter()
        self._session_manager = get_session_manager()
        self._captcha_service = get_captcha_service()

    def _get_session(self) -> cffi_requests.Session:
        """Get or create HTTP session with browser impersonation."""
        if self._session is None:
            self._session = cffi_requests.Session(
                impersonate=self._fingerprint.get_browser()
            )
        return self._session

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint."""
        return f"{self.BASE_URL}{endpoint}"

    async def _restore_session(self) -> bool:
        """
        Restore session from Redis if available.

        Returns:
            True if session was restored
        """
        session_data = await self._session_manager.get_session(self.ntnu_account_id)
        if not session_data:
            return False

        # Restore cookies to HTTP session
        http_session = self._get_session()
        for name, value in session_data.cookies.items():
            http_session.cookies.set(name, value)

        return True

    async def get_captcha_image(self) -> bytes:
        """
        Fetch captcha image from NTNU system.

        Returns:
            Raw image bytes
        """
        await self._rate_limiter.wait_for_slot(RequestType.GENERAL)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["captcha"])
        headers = get_browser_headers(referer=self._build_url(self.ENDPOINTS["login_page"]))

        response = session.get(url, headers=headers)

        if response.status_code != 200:
            raise NTNUClientError(f"Failed to fetch captcha: {response.status_code}")

        self._rate_limiter.record_request()
        return response.content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def login(self, student_id: str, password: str) -> Dict[str, Any]:
        """
        Login to NTNU system.

        Args:
            student_id: Student ID
            password: Password

        Returns:
            Dict with login result

        Raises:
            NTNULoginError: If login fails
        """
        await self._rate_limiter.wait_for_slot(RequestType.LOGIN)

        # First, visit login page to get initial cookies
        session = self._get_session()
        login_page_url = self._build_url(self.ENDPOINTS["login_page"])
        headers = get_browser_headers()

        response = session.get(login_page_url, headers=headers)
        if response.status_code != 200:
            raise NTNULoginError("Failed to load login page")

        # Small delay to simulate reading
        await asyncio.sleep(1.0)

        # Solve captcha
        captcha_answer, _ = await self._captcha_service.solve_with_retry(
            self.get_captcha_image,
            max_attempts=3,
        )

        # Prepare login data
        login_data = {
            "userid": student_id,
            "password": password,
            "validateCode": captcha_answer,
        }

        # Submit login
        login_url = self._build_url(self.ENDPOINTS["login"])
        headers = get_ajax_headers(referer=login_page_url)

        response = session.post(login_url, data=login_data, headers=headers)
        self._rate_limiter.record_request()

        if response.status_code != 200:
            raise NTNULoginError(f"Login request failed: {response.status_code}")

        # Parse response
        try:
            result = response.json()
        except Exception:
            # Some responses are not JSON
            result = {"raw": response.text}

        # Check for success indicators
        if self._is_login_successful(result, response):
            # Save session to Redis
            cookies = {k: v for k, v in session.cookies.items()}
            session_id = cookies.get("JSESSIONID", "")

            await self._session_manager.save_session(
                self.ntnu_account_id,
                cookies,
                session_id,
            )

            self._fingerprint.on_success()

            return {
                "success": True,
                "message": "Login successful",
                "session_id": session_id,
            }
        else:
            self._fingerprint.on_error()
            error_msg = result.get("msg", result.get("raw", "Unknown error"))
            raise NTNULoginError(f"Login failed: {error_msg}")

    def _is_login_successful(self, result: Dict, response: cffi_requests.Response) -> bool:
        """Check if login was successful based on response."""
        # Check for success in JSON response
        if isinstance(result, dict):
            if result.get("success") is True:
                return True
            if result.get("status") == "success":
                return True

        # Check for redirect to index page
        if "IndexCtrl" in response.url:
            return True

        # Check for session cookie
        if "JSESSIONID" in response.cookies:
            return True

        return False

    async def keepalive(self) -> bool:
        """
        Send keepalive request to maintain session.

        Returns:
            True if session is still valid
        """
        if not await self._restore_session():
            return False

        await self._rate_limiter.wait_for_slot(RequestType.HEARTBEAT)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["wakeup"])
        headers = get_ajax_headers(referer=self._build_url(self.ENDPOINTS["index"]))

        try:
            response = session.get(url, headers=headers)
            self._rate_limiter.record_request()

            if response.status_code == 200:
                await self._session_manager.update_activity(self.ntnu_account_id)
                return True
            else:
                return False

        except Exception:
            return False

    async def check_course_availability(
        self,
        course_code: str,
        class_code: str | None = None,
    ) -> Dict[str, Any]:
        """
        Check course availability (enrollment status).

        Args:
            course_code: Course code
            class_code: Class code (optional)

        Returns:
            Dict with course availability info

        Raises:
            NTNUSessionExpiredError: If session is expired
            NTNUClientError: If request fails
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.CHECK_AVAILABILITY)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["course_list"])
        headers = get_ajax_headers(referer=self._build_url(self.ENDPOINTS["index"]))

        # Build query parameters
        params = {"courseCode": course_code}
        if class_code:
            params["classCode"] = class_code

        try:
            response = session.get(url, params=params, headers=headers)
            self._rate_limiter.record_request()

            if response.status_code == 200:
                await self._session_manager.update_activity(self.ntnu_account_id)
                self._fingerprint.on_success()

                # Parse response
                try:
                    data = response.json()
                    return self._parse_course_data(data)
                except Exception:
                    return {"raw": response.text}
            elif response.status_code in [401, 403]:
                raise NTNUSessionExpiredError("Session expired")
            else:
                self._fingerprint.on_error()
                raise NTNUClientError(f"Request failed: {response.status_code}")

        except (NTNUSessionExpiredError, NTNUClientError):
            raise
        except Exception as e:
            self._fingerprint.on_error()
            raise NTNUClientError(f"Request error: {str(e)}")

    def _parse_course_data(self, data: Any) -> Dict[str, Any]:
        """Parse course data from API response."""
        # This will need to be adjusted based on actual API response format
        if isinstance(data, dict):
            return {
                "course_code": data.get("courseCode", ""),
                "course_name": data.get("courseName", ""),
                "current_enrolled": data.get("currentEnrolled", 0),
                "max_capacity": data.get("maxCapacity", 0),
                "has_vacancy": data.get("currentEnrolled", 0) < data.get("maxCapacity", 0),
            }
        return {"raw": data}

    async def enroll_course(
        self,
        course_code: str,
        class_code: str | None = None,
    ) -> Dict[str, Any]:
        """
        Attempt to enroll in a course.

        Args:
            course_code: Course code
            class_code: Class code (optional)

        Returns:
            Dict with enrollment result

        Raises:
            NTNUSessionExpiredError: If session is expired
            NTNUClientError: If request fails
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.ENROLL)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["enroll"])
        headers = get_ajax_headers(referer=self._build_url(self.ENDPOINTS["index"]))

        # Build enrollment data
        data = {
            "action": "add",
            "courseCode": course_code,
        }
        if class_code:
            data["classCode"] = class_code

        try:
            response = session.post(url, data=data, headers=headers)
            self._rate_limiter.record_request()

            if response.status_code == 200:
                await self._session_manager.update_activity(self.ntnu_account_id)
                self._fingerprint.on_success()

                try:
                    result = response.json()
                except Exception:
                    result = {"raw": response.text}

                return {
                    "success": self._is_enrollment_successful(result),
                    "message": result.get("msg", result.get("raw", "")),
                    "data": result,
                }
            elif response.status_code in [401, 403]:
                raise NTNUSessionExpiredError("Session expired")
            else:
                self._fingerprint.on_error()
                raise NTNUClientError(f"Enrollment failed: {response.status_code}")

        except (NTNUSessionExpiredError, NTNUClientError):
            raise
        except Exception as e:
            self._fingerprint.on_error()
            raise NTNUClientError(f"Enrollment error: {str(e)}")

    def _is_enrollment_successful(self, result: Dict) -> bool:
        """Check if enrollment was successful."""
        if isinstance(result, dict):
            if result.get("success") is True:
                return True
            if result.get("status") == "success":
                return True
        return False

    async def logout(self) -> None:
        """Logout and invalidate session."""
        await self._session_manager.invalidate_session(self.ntnu_account_id)
        if self._session:
            self._session.close()
            self._session = None

    def close(self) -> None:
        """Close HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
