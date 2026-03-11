"""
NTNU Course Enrollment System API Client.

Based on API discovery from actual system (2026-01).
Note: NTNU system has anti-bot protection that rejects non-browser requests.
Browser-based login is required to establish a valid session.

API Verification Status:
========================
✅ CONFIRMED (verified with actual response/HTML source):
   - LoginCheckCtrl?action=login&id={sessionId} - login step 1
     POST: userid, password, validateCode, checkTW
   - LoginCtrl - login step 2
     POST: userid, stdName, checkTW
   - CourseQueryCtrl?action=showGrid - course search
   - StfseldListCtrl?action=showGrid - enrolled courses list
   - StfseldListCtrl?action=remove1Stfseld - drop course
   - StfseldListCtrl?action=remove2Stfseld - confirm drop
   - Wakeup.do?something=111 - session keepalive
   - RandImage - captcha image

⚠️ UNVERIFIED (guessed based on common patterns):
   - LogoutCtrl - logout

✅ CONFIRMED Login Response Format (2026-01-21):
   - JSON: {"success": true/false, "msg": "error message"}
   - Error examples: "無此學號", "驗證碼錯誤", "帳號或密碼錯誤"

🔴 NOT IMPLEMENTED:
   - enroll_course() - add course API not yet discovered
   - Authorization code enrollment
"""

import asyncio
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import RequestException, Timeout
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

# Request timeout in seconds
REQUEST_TIMEOUT = 30


class NTNUClient:
    """
    Client for interacting with NTNU Course Enrollment System.

    IMPORTANT: NTNU system has anti-bot detection that returns
    "不合法執行選課系統" for non-browser requests. Production use
    requires browser-based login (see NTNUBrowserClient).

    This client can be used with cookies extracted from browser session.
    """

    BASE_URL = settings.ntnu_base_url

    # API endpoints discovered from actual system
    # Status: ✅=confirmed, ⚠️=unverified/guessed, 🔴=not implemented
    ENDPOINTS = {
        # Authentication - ✅ CONFIRMED from recorded logs
        "login_page": "/LoginCheckCtrl?language=TW",  # ✅ confirmed
        "login": "/LoginCheckCtrl",  # ✅ action=login&id={sessionId}, POST: userid,password,validateCode,checkTW
        "login_confirm": "/LoginCtrl",  # ✅ POST: userid, stdName, checkTW
        "captcha": "/RandImage",  # ✅ confirmed
        "index": "/IndexCtrl",  # ⚠️ unverified
        "logout": "/LogoutCtrl",  # ⚠️ action=logout - GUESSED

        # Session keepalive - ✅ CONFIRMED from HTML
        "wakeup": "/Wakeup.do",  # ✅ params: something=111

        # Enrollment - ✅ CONFIRMED from HTML
        "enroll_page": "/EnrollCtrl",  # ✅ action=go
        "enrolled_list": "/StfseldListCtrl",  # ✅ action=showGrid, remove1Stfseld, remove2Stfseld
        "general_list": "/GeneralListCtrl",  # ✅ confirmed from HTML (通識志願)
        "education_list": "/EducationListCtrl",  # ✅ confirmed from HTML (教育學程)
        "sport_list": "/SportListCtrl",  # ✅ confirmed from HTML (體育志願)
        "summer_list": "/StfseldSummerListCtrl",  # ✅ confirmed from HTML (暑修)
        "phase4_list": "/Phase4AsnListCtrl",  # ✅ confirmed from HTML (加退選階段)
        "phase6_list": "/Phase6AsnListCtrl",  # ✅ confirmed from HTML (新生選課階段)

        # Course Query - ✅ CONFIRMED from actual response
        "course_query_page": "/CourseQueryCtrl",  # ✅ action=query
        "course_search": "/CourseQueryCtrl",  # ✅ action=showGrid (POST) - response verified
        "course_domains": "/CourseQueryCtrl",  # ⚠️ action=getGuDomain - unverified
        "course_names": "/CofnameCtrl",  # ⚠️ unverified
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
        self._login_session_id: str | None = None

    def _get_session(self) -> cffi_requests.Session:
        """Get or create HTTP session with browser impersonation."""
        if self._session is None:
            self._session = cffi_requests.Session(
                impersonate=self._fingerprint.get_browser()
            )
        return self._session

    def _build_url(self, endpoint: str, params: dict | None = None) -> str:
        """Build full URL for an endpoint with optional query params."""
        url = f"{self.BASE_URL}{endpoint}"
        if params:
            url += ("&" if "?" in endpoint else "?") + urlencode(params)
        return url

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

    def set_cookies_from_browser(self, cookies: dict[str, str]) -> None:
        """
        Set cookies extracted from browser session.

        This allows using curl_cffi for faster requests after
        browser-based login.

        Args:
            cookies: Dict of cookie name -> value
        """
        session = self._get_session()
        for name, value in cookies.items():
            session.cookies.set(name, value)

    async def get_captcha_image(self) -> bytes:
        """
        Fetch captcha image from NTNU system.

        Returns:
            Raw image bytes
        """
        await self._rate_limiter.wait_for_slot(RequestType.GENERAL)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["captcha"])
        headers = get_browser_headers(
            referer=self._build_url(self.ENDPOINTS["login_page"])
        )

        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        except Timeout:
            raise NTNUClientError("Captcha request timed out")
        except RequestException as e:
            raise NTNUClientError(f"Captcha request failed: {e}")

        if response.status_code != 200:
            raise NTNUClientError(f"Failed to fetch captcha: {response.status_code}")

        self._rate_limiter.record_request()
        return response.content

    def _generate_session_id(self) -> str:
        """Generate a random session ID for login request."""
        import random
        import string
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=15))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def login(self, student_id: str, password: str) -> dict[str, Any]:
        """
        Login to NTNU system via HTTP client.

        ⚠️ WARNING: HTTP login likely to fail due to anti-bot detection.
        Use NTNUBrowserClient for production.

        ✅ CONFIRMED from recorded logs:
        - Login URL: LoginCheckCtrl?action=login&id={sessionId}
        - POST params: userid, password, validateCode, checkTW
        - Session ID format: 15 alphanumeric chars (e.g., "56994tcnkii775")

        ⚠️ UNVERIFIED (need to check actual responses):
        - Response format: JSON with success/status/msg
        - Success/error detection logic

        Args:
            student_id: Student ID
            password: Password

        Returns:
            Dict with login result

        Raises:
            NTNULoginError: If login fails
        """
        await self._rate_limiter.wait_for_slot(RequestType.LOGIN)

        session = self._get_session()

        # Step 1: Visit login page to get initial cookies
        login_page_url = self._build_url(self.ENDPOINTS["login_page"])
        headers = get_browser_headers()

        try:
            response = session.get(
                login_page_url, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except Timeout:
            raise NTNULoginError("Login page request timed out")
        except RequestException as e:
            raise NTNULoginError(f"Failed to load login page: {e}")

        if response.status_code != 200:
            raise NTNULoginError("Failed to load login page")

        # Small delay to simulate human behavior
        await asyncio.sleep(1.0)

        # Step 2: Solve captcha
        captcha_answer, _ = await self._captcha_service.solve_with_retry(
            self.get_captcha_image,
            max_attempts=3,
        )

        # Step 3: Generate session ID and submit login
        # ✅ CONFIRMED: URL format LoginCheckCtrl?action=login&id={sessionId}
        self._login_session_id = self._generate_session_id()
        login_url = self._build_url(
            self.ENDPOINTS["login"],
            {"action": "login", "id": self._login_session_id}
        )

        # ✅ CONFIRMED: POST parameter names from recorded logs
        # Sample: userid=41143203S&password=xxx&validateCode=vndm&checkTW=1
        login_data = {
            "userid": student_id,  # ✅ confirmed
            "password": password,  # ✅ confirmed
            "validateCode": captcha_answer,  # ✅ confirmed
            "checkTW": "1",  # ✅ confirmed (always "1")
        }

        headers = get_ajax_headers(referer=login_page_url)

        try:
            response = session.post(
                login_url, data=login_data, headers=headers,
                timeout=REQUEST_TIMEOUT, allow_redirects=True
            )
        except Timeout:
            raise NTNULoginError("Login request timed out")
        except RequestException as e:
            raise NTNULoginError(f"Login request failed: {e}")

        self._rate_limiter.record_request()

        if response.status_code != 200:
            raise NTNULoginError(f"Login request failed: {response.status_code}")

        # Check for anti-bot detection - ✅ CONFIRMED error message
        if "不合法執行選課系統" in response.text:
            raise NTNULoginError(
                "Anti-bot detection triggered. Use browser-based login."
            )

        # ⚠️ GUESSED: Response might be JSON or HTML redirect
        try:
            result = response.json()
        except Exception:
            result = {"raw": response.text}

        # ⚠️ GUESSED: Success indicators
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

    def _is_login_successful(
        self, result: dict, response: cffi_requests.Response
    ) -> bool:
        """
        Check if login was successful based on response.

        ✅ CONFIRMED (2026-01-21): Response format is JSON with:
        - success: true/false
        - msg: error message (when success=false)
        """
        # ✅ CONFIRMED: JSON response format {"success": true/false, "msg": "..."}
        if isinstance(result, dict):
            if result.get("success") is True:
                return True
            # If success is explicitly false, login failed
            if result.get("success") is False:
                return False

        # Fallback: Redirect to index page indicates success
        if "IndexCtrl" in response.url:
            return True

        return False

    async def search_courses(
        self,
        serial_no: str | None = None,
        course_name: str | None = None,
        teacher: str | None = None,
        dept_code: str | None = None,
        not_full_only: bool = False,
        course_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Search for courses.

        Args:
            serial_no: Course serial number (e.g., "0001", "6024")
            course_name: Course name (Chinese)
            teacher: Teacher name
            dept_code: Department code
            not_full_only: Only show courses with available seats
            course_code: Course code

        Returns:
            Dict with search results

        Raises:
            NTNUSessionExpiredError: If session is expired
            NTNUClientError: If request fails
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.CHECK_AVAILABILITY)

        session = self._get_session()

        # Build search URL with timestamp
        timestamp = int(datetime.now().timestamp() * 1000)
        url = self._build_url(
            self.ENDPOINTS["course_search"],
            {"action": "showGrid", "_dc": str(timestamp)}
        )

        # Build POST data
        # Initialize all time slot checkboxes to 0
        post_data: dict[str, Any] = {}
        for day in range(1, 7):  # Days 1-6 (Mon-Sat)
            for period in range(0, 15):  # Periods 0-14
                post_data[f"checkWkSection{day}{period}"] = "0"

        # Add search parameters
        post_data.update({
            "serialNo": serial_no or "",
            "chnName": course_name or "",
            "teacher": teacher or "",
            "deptCode": dept_code or "",
            "notFull": "1" if not_full_only else "0",
            "courseCode": course_code or "",
            "formS": "",
            "class1": "",
            "generalCore": "",
            "validQuery": "",
            "action": "showGrid",
            "actionButton": "query",
            "page": "1",
            "start": "0",
            "limit": "999999",
        })

        headers = get_ajax_headers(
            referer=self._build_url(self.ENDPOINTS["course_query_page"])
        )

        try:
            response = session.post(
                url, data=post_data, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except Timeout:
            raise NTNUClientError("Course search request timed out")
        except RequestException as e:
            raise NTNUClientError(f"Course search request failed: {e}")

        self._rate_limiter.record_request()

        if response.status_code == 200:
            await self._session_manager.update_activity(self.ntnu_account_id)
            self._fingerprint.on_success()

            try:
                data = response.json()
                return self._parse_course_search_results(data)
            except Exception:
                return {"raw": response.text, "success": False}

        elif response.status_code in [401, 403]:
            raise NTNUSessionExpiredError("Session expired")
        else:
            self._fingerprint.on_error()
            raise NTNUClientError(f"Course search failed: {response.status_code}")

    def _parse_course_search_results(self, data: Any) -> dict[str, Any]:
        """
        Parse course search results from API response.

        Actual response format:
        {
            "Count": 1,
            "List": [{
                "serialNo": "0001",
                "courseCode": "A0U0004",
                "chnName": "生涯規劃與就業輔導",
                "engName": "Career Planning...",
                "teacher": "李加耀",
                "credit": "2.0",
                "limitCountH": 50,       # Max capacity
                "v_stfseld": 0,          # Current enrolled (選課人數)
                "timeInfo": "三 6-7 和平 體002",
                "optionCode": "選修",
                "v_deptChiabbr": "運休學院",
                ...
            }]
        }
        """
        if not isinstance(data, dict):
            return {"raw": data, "success": False}

        courses = []
        # Response uses "List" not "rows"
        rows = data.get("List", data.get("rows", data.get("data", [])))

        for row in rows:
            if isinstance(row, dict):
                # Parse credit as float
                credit_str = row.get("credit", "0")
                try:
                    credits = float(credit_str)
                except (ValueError, TypeError):
                    credits = 0.0

                courses.append({
                    "serial_no": row.get("serialNo", ""),
                    "course_code": row.get("courseCode", ""),
                    "course_name": row.get("chnName", ""),
                    "course_name_eng": row.get("engName", ""),
                    "teacher": row.get("teacher", ""),
                    "credits": credits,
                    "current_enrolled": row.get("v_stfseld", 0),  # 選課人數
                    "max_capacity": row.get("limitCountH", 0),    # 人數上限
                    "time_info": row.get("timeInfo", ""),
                    "time_info_eng": row.get("engTimeInfo", ""),
                    "option_code": row.get("optionCode", ""),     # 選修/必修
                    "dept_code": row.get("deptCode", ""),
                    "dept_name": row.get("v_deptChiabbr", ""),
                    "course_kind": row.get("courseKind", ""),     # 半/全
                    "acadm_year": row.get("acadmYear", ""),       # 學年
                    "acadm_term": row.get("acadmTerm", ""),       # 學期
                    "is_full": row.get("v_is_Full", "") == "Y",
                    "emi": row.get("emi", ""),                    # EMI課程
                    "memo": row.get("v_comment", ""),
                })

        return {
            "success": True,
            "total": data.get("Count", len(courses)),
            "courses": courses,
        }

    async def get_enrolled_courses(self) -> dict[str, Any]:
        """
        Get list of currently enrolled courses.

        Returns:
            Dict with enrolled courses

        Raises:
            NTNUSessionExpiredError: If session is expired
            NTNUClientError: If request fails
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.CHECK_AVAILABILITY)

        session = self._get_session()

        # Build URL with timestamp
        timestamp = int(datetime.now().timestamp() * 1000)
        url = self._build_url(
            self.ENDPOINTS["enrolled_list"],
            {
                "action": "showGrid",
                "_dc": str(timestamp),
                "page": "1",
                "start": "0",
                "limit": "999999",
            }
        )

        headers = get_ajax_headers(
            referer=self._build_url(self.ENDPOINTS["enroll_page"], {"action": "go"})
        )

        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        except Timeout:
            raise NTNUClientError("Get enrolled courses request timed out")
        except RequestException as e:
            raise NTNUClientError(f"Get enrolled courses request failed: {e}")

        self._rate_limiter.record_request()

        if response.status_code == 200:
            await self._session_manager.update_activity(self.ntnu_account_id)
            self._fingerprint.on_success()

            try:
                data = response.json()
                return self._parse_enrolled_courses(data)
            except Exception:
                return {"raw": response.text, "success": False}

        elif response.status_code in [401, 403]:
            raise NTNUSessionExpiredError("Session expired")
        else:
            self._fingerprint.on_error()
            raise NTNUClientError(f"Get enrolled courses failed: {response.status_code}")

    def _parse_enrolled_courses(self, data: Any) -> dict[str, Any]:
        """
        Parse enrolled courses from StfseldListCtrl?action=showGrid response.

        Actual response format (confirmed from HTML source):
        {
            "Count": N,
            "List": [{
                "acadmYear", "acadmTerm", "stdNo",
                "courseCode", "courseGroup", "deptCode",
                "formS", "class1", "deptGroup",
                "moeCredit", "chnName", "optionCode",
                "v_serialNo", "v_teacher", "v_timeInfo",
                "v_deptChiabbr", "v_limitCountH", ...
            }]
        }
        """
        if not isinstance(data, dict):
            return {"raw": data, "success": False}

        courses = []
        rows = data.get("List", data.get("rows", data.get("data", [])))

        for row in rows:
            if isinstance(row, dict):
                # Parse credit as float
                credit_str = row.get("moeCredit", row.get("credit", "0"))
                try:
                    credits = float(credit_str) if isinstance(credit_str, str) else credit_str
                except (ValueError, TypeError):
                    credits = 0.0

                courses.append({
                    # Primary identifiers for display
                    "serial_no": row.get("v_serialNo", ""),
                    "course_code": row.get("courseCode", ""),
                    "course_name": row.get("chnName", ""),
                    "teacher": row.get("v_teacher", ""),
                    "credits": credits,
                    "time_info": row.get("v_timeInfo", ""),
                    "option_code": row.get("optionCode", ""),
                    "dept_name": row.get("v_deptChiabbr", ""),
                    "max_capacity": row.get("v_limitCountH", ""),
                    "phase": row.get("v_phase", ""),
                    "stage": row.get("v_stage", ""),
                    # Keys needed for drop_course API
                    "_drop_params": {
                        "acadm_year": row.get("acadmYear", ""),
                        "acadm_term": row.get("acadmTerm", ""),
                        "course_code": row.get("courseCode", ""),
                        "course_group": row.get("courseGroup", ""),
                        "dept_code": row.get("deptCode", ""),
                        "form_s": row.get("formS", ""),
                        "class1": row.get("class1", ""),
                        "dept_group": row.get("deptGroup", ""),
                        "credit": credit_str,
                    },
                })

        return {
            "success": True,
            "total": data.get("Count", data.get("total", len(courses))),
            "courses": courses,
        }

    async def check_course_availability(
        self,
        serial_no: str,
    ) -> dict[str, Any]:
        """
        Check if a course has available seats.

        Args:
            serial_no: Course serial number

        Returns:
            Dict with availability info including:
            - has_vacancy: True if seats available
            - current_enrolled: Current enrollment count (v_stfseld)
            - max_capacity: Maximum capacity (limitCountH)
            - course: Full course info
        """
        result = await self.search_courses(serial_no=serial_no)

        if not result.get("success") or not result.get("courses"):
            return {
                "success": False,
                "message": "Course not found",
                "has_vacancy": False,
            }

        course = result["courses"][0]
        current = int(course.get("current_enrolled", 0))
        max_cap = int(course.get("max_capacity", 0))
        is_full = course.get("is_full", False)

        # Check vacancy: either by is_full flag or by comparing numbers
        if is_full:
            has_vacancy = False
        elif max_cap > 0:
            has_vacancy = current < max_cap
        else:
            # No limit set
            has_vacancy = True

        return {
            "success": True,
            "course": course,
            "current_enrolled": current,
            "max_capacity": max_cap,
            "available_seats": max(0, max_cap - current) if max_cap > 0 else None,
            "has_vacancy": has_vacancy,
            "is_full": is_full,
        }

    async def enroll_course(
        self,
        serial_no: str,
    ) -> dict[str, Any]:
        """
        Attempt to enroll in a course.

        NOTE: This is a placeholder. The actual enrollment API
        endpoint needs to be discovered during enrollment period.

        Args:
            serial_no: Course serial number

        Returns:
            Dict with enrollment result

        Raises:
            NTNUSessionExpiredError: If session is expired
            NTNUClientError: If request fails
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.ENROLL)

        # TODO: Implement actual enrollment after discovering API
        # Expected endpoint: POST /EnrollCtrl with action=add or similar
        # Need to record actual enrollment requests during enrollment period

        raise NTNUClientError(
            "Enrollment API not yet implemented. "
            "Need to record actual enrollment during enrollment period."
        )

    async def drop_course(
        self,
        serial_no: str | None = None,
        drop_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Drop a course.

        API discovered from StfseldListCtrl HTML:
        - URL: StfseldListCtrl
        - Action: remove1Stfseld
        - Required params: acadm_year, acadm_term, course_code,
          course_group, dept_code, form_s, class1, dept_group, credit

        Args:
            serial_no: Course serial number (will look up drop_params)
            drop_params: Direct drop parameters from get_enrolled_courses()
                        (use _drop_params from course object)

        Returns:
            Dict with drop result
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.ENROLL)

        # If drop_params not provided, look up from enrolled courses
        if drop_params is None:
            if serial_no is None:
                raise NTNUClientError("Either serial_no or drop_params required")

            enrolled = await self.get_enrolled_courses()
            if not enrolled.get("success"):
                raise NTNUClientError("Failed to get enrolled courses")

            # Find the course by serial_no
            course = None
            for c in enrolled.get("courses", []):
                if c.get("serial_no") == serial_no:
                    course = c
                    break

            if not course:
                raise NTNUClientError(f"Course {serial_no} not found in enrolled list")

            drop_params = course.get("_drop_params")
            if not drop_params:
                raise NTNUClientError("Drop parameters not available for course")

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["enrolled_list"])

        post_data = {
            "action": "remove1Stfseld",
            "acadm_year": drop_params.get("acadm_year", ""),
            "acadm_term": drop_params.get("acadm_term", ""),
            "course_code": drop_params.get("course_code", ""),
            "course_group": drop_params.get("course_group", ""),
            "dept_code": drop_params.get("dept_code", ""),
            "form_s": drop_params.get("form_s", ""),
            "class1": drop_params.get("class1", ""),
            "dept_group": drop_params.get("dept_group", ""),
            "credit": drop_params.get("credit", ""),
        }

        headers = get_ajax_headers(
            referer=self._build_url(self.ENDPOINTS["enroll_page"], {"action": "go"})
        )

        try:
            response = session.post(
                url, data=post_data, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except Timeout:
            raise NTNUClientError("Drop course request timed out")
        except RequestException as e:
            raise NTNUClientError(f"Drop course request failed: {e}")

        self._rate_limiter.record_request()

        if response.status_code == 200:
            await self._session_manager.update_activity(self.ntnu_account_id)

            try:
                result = response.json()
                msg = result.get("msg", "")
                flag = result.get("flag", "")

                # Check if confirmation needed (flag A, B, or C)
                if flag in ["A", "B", "C"]:
                    return {
                        "success": False,
                        "needs_confirmation": True,
                        "confirmation_flag": flag,
                        "message": msg,
                    }

                # Success response
                return {
                    "success": True,
                    "message": msg or "Course dropped successfully",
                }

            except Exception:
                # Non-JSON response, check for error patterns
                if "失敗" in response.text or "錯誤" in response.text:
                    return {"success": False, "message": response.text}
                return {"success": True, "message": "Course dropped"}

        elif response.status_code in [401, 403]:
            raise NTNUSessionExpiredError("Session expired")
        else:
            raise NTNUClientError(f"Drop course failed: {response.status_code}")

    async def confirm_drop_course(self, confirmation_flag: str) -> dict[str, Any]:
        """
        Confirm course drop when additional confirmation is required.

        Some drop operations require a second confirmation (flag A, B, or C).
        Call this after drop_course returns needs_confirmation=True.

        Args:
            confirmation_flag: The flag returned from drop_course ("A", "B", or "C")

        Returns:
            Dict with drop result
        """
        if not await self._restore_session():
            raise NTNUSessionExpiredError("No active session")

        await self._rate_limiter.wait_for_slot(RequestType.ENROLL)

        session = self._get_session()
        url = self._build_url(self.ENDPOINTS["enrolled_list"])

        post_data = {
            "action": "remove2Stfseld",
            "flag": confirmation_flag,
        }

        headers = get_ajax_headers(
            referer=self._build_url(self.ENDPOINTS["enroll_page"], {"action": "go"})
        )

        try:
            response = session.post(
                url, data=post_data, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except Timeout:
            raise NTNUClientError("Confirm drop request timed out")
        except RequestException as e:
            raise NTNUClientError(f"Confirm drop request failed: {e}")

        self._rate_limiter.record_request()

        if response.status_code == 200:
            await self._session_manager.update_activity(self.ntnu_account_id)

            try:
                result = response.json()
                msg = result.get("msg", "")
                return {
                    "success": True,
                    "message": msg or "Course dropped successfully",
                }
            except Exception:
                if "失敗" in response.text or "錯誤" in response.text:
                    return {"success": False, "message": response.text}
                return {"success": True, "message": "Course dropped"}

        elif response.status_code in [401, 403]:
            raise NTNUSessionExpiredError("Session expired")
        else:
            raise NTNUClientError(f"Confirm drop failed: {response.status_code}")

    async def keepalive(self) -> bool:
        """
        Send keepalive request to maintain session.

        Uses Wakeup.do endpoint discovered from actual system.
        Session expires after 20 minutes, so call this every 15-17 minutes.

        Returns:
            True if session is still valid
        """
        if not await self._restore_session():
            return False

        await self._rate_limiter.wait_for_slot(RequestType.HEARTBEAT)

        session = self._get_session()
        # Use Wakeup.do endpoint with the required parameter
        url = self._build_url(self.ENDPOINTS["wakeup"], {"something": "111"})
        headers = get_ajax_headers(
            referer=self._build_url(self.ENDPOINTS["enroll_page"], {"action": "go"})
        )

        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            self._rate_limiter.record_request()

            if response.status_code == 200:
                await self._session_manager.update_activity(self.ntnu_account_id)
                return True
            else:
                return False

        except Exception:
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
