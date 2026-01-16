"""Browser headers configuration for anti-detection."""

import random
from typing import Dict

# Chrome versions to rotate
CHROME_VERSIONS = ["131", "130", "129", "128"]

# Windows versions
WINDOWS_VERSIONS = [
    "Windows NT 10.0; Win64; x64",
    "Windows NT 11.0; Win64; x64",
]


def get_user_agent(chrome_version: str | None = None) -> str:
    """Generate a realistic Chrome User-Agent string."""
    if chrome_version is None:
        chrome_version = random.choice(CHROME_VERSIONS)

    windows = random.choice(WINDOWS_VERSIONS)
    return (
        f"Mozilla/5.0 ({windows}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36"
    )


def get_sec_ch_ua(chrome_version: str | None = None) -> str:
    """Generate Sec-Ch-Ua header matching the User-Agent."""
    if chrome_version is None:
        chrome_version = random.choice(CHROME_VERSIONS)

    return f'"Google Chrome";v="{chrome_version}", "Chromium";v="{chrome_version}", "Not_A Brand";v="24"'


def get_browser_headers(referer: str | None = None) -> Dict[str, str]:
    """
    Get complete browser headers for HTTP requests.
    These headers mimic a real Chrome browser to avoid detection.
    """
    chrome_version = random.choice(CHROME_VERSIONS)

    headers = {
        "User-Agent": get_user_agent(chrome_version),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": get_sec_ch_ua(chrome_version),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }

    if referer:
        headers["Referer"] = referer

    return headers


def get_ajax_headers(referer: str | None = None) -> Dict[str, str]:
    """Get headers for AJAX/API requests."""
    chrome_version = random.choice(CHROME_VERSIONS)

    headers = {
        "User-Agent": get_user_agent(chrome_version),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Ch-Ua": get_sec_ch_ua(chrome_version),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Connection": "keep-alive",
    }

    if referer:
        headers["Referer"] = referer

    return headers
