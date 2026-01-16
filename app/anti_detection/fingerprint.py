"""TLS fingerprint configuration for curl_cffi."""

from typing import Literal

# Available browser impersonation options in curl_cffi
# These simulate the TLS fingerprint (JA3/JA4) of real browsers
BrowserImpersonate = Literal[
    "chrome131",
    "chrome130",
    "chrome129",
    "chrome128",
    "chrome127",
    "chrome126",
    "edge131",
    "edge130",
    "safari18_0",
    "safari17_5",
]

# Default browser to impersonate
DEFAULT_BROWSER: BrowserImpersonate = "chrome131"

# Rotation pool for browser fingerprints
BROWSER_POOL: list[BrowserImpersonate] = [
    "chrome131",
    "chrome130",
    "chrome129",
]


def get_random_browser() -> BrowserImpersonate:
    """Get a random browser impersonation target."""
    import random
    return random.choice(BROWSER_POOL)


class FingerprintConfig:
    """Configuration for TLS fingerprint impersonation."""

    def __init__(
        self,
        browser: BrowserImpersonate = DEFAULT_BROWSER,
        rotate_on_error: bool = True,
    ) -> None:
        """
        Initialize fingerprint configuration.

        Args:
            browser: Browser to impersonate
            rotate_on_error: Whether to rotate browser on request errors
        """
        self.browser = browser
        self.rotate_on_error = rotate_on_error
        self._error_count = 0
        self._max_errors_before_rotate = 3

    def get_browser(self) -> BrowserImpersonate:
        """Get current browser impersonation target."""
        return self.browser

    def on_error(self) -> None:
        """Handle request error, potentially rotating browser."""
        if not self.rotate_on_error:
            return

        self._error_count += 1

        if self._error_count >= self._max_errors_before_rotate:
            self.rotate_browser()
            self._error_count = 0

    def rotate_browser(self) -> None:
        """Rotate to a different browser fingerprint."""
        import random
        available = [b for b in BROWSER_POOL if b != self.browser]
        if available:
            self.browser = random.choice(available)

    def on_success(self) -> None:
        """Handle successful request."""
        self._error_count = 0


# Global fingerprint config
_fingerprint_config: FingerprintConfig | None = None


def get_fingerprint_config() -> FingerprintConfig:
    """Get the global fingerprint configuration."""
    global _fingerprint_config
    if _fingerprint_config is None:
        _fingerprint_config = FingerprintConfig()
    return _fingerprint_config
