"""OCR captcha recognition service for NTNU system."""

import re
from typing import Tuple

import ddddocr

from app.core.exceptions import CaptchaError


class CaptchaService:
    """
    Handle NTNU captcha recognition with OCR.
    Supports both text and math expression captchas.
    """

    # Pattern for math expressions like "5 + 3 = ?" or "5+3=?"
    MATH_PATTERN = re.compile(r"(\d+)\s*([+\-×÷xX*])\s*(\d+)")

    def __init__(self) -> None:
        self._ocr: ddddocr.DdddOcr | None = None

    def _get_ocr(self) -> ddddocr.DdddOcr:
        """Get or create OCR instance."""
        if self._ocr is None:
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def recognize(self, image_bytes: bytes) -> str:
        """
        Recognize captcha from image bytes.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Recognized text or calculated result

        Raises:
            CaptchaError: If recognition fails
        """
        try:
            ocr = self._get_ocr()
            raw_text = ocr.classification(image_bytes)

            if not raw_text:
                raise CaptchaError("OCR returned empty result")

            # Check if it's a math expression
            result = self._try_solve_math(raw_text)
            if result is not None:
                return result

            # Return raw text (cleaned)
            return self._clean_text(raw_text)

        except CaptchaError:
            raise
        except Exception as e:
            raise CaptchaError(f"Captcha recognition failed: {str(e)}")

    def _try_solve_math(self, text: str) -> str | None:
        """
        Try to solve if the text is a math expression.

        Args:
            text: OCR result text

        Returns:
            Calculated result as string, or None if not a math expression
        """
        match = self.MATH_PATTERN.search(text)
        if not match:
            return None

        try:
            num1 = int(match.group(1))
            operator = match.group(2)
            num2 = int(match.group(3))

            if operator in ["+", "+"]:
                result = num1 + num2
            elif operator in ["-", "-"]:
                result = num1 - num2
            elif operator in ["×", "x", "X", "*"]:
                result = num1 * num2
            elif operator in ["÷", "/"]:
                result = num1 // num2  # Integer division
            else:
                return None

            return str(result)

        except (ValueError, ZeroDivisionError):
            return None

    def _clean_text(self, text: str) -> str:
        """
        Clean OCR result text.

        Args:
            text: Raw OCR text

        Returns:
            Cleaned text
        """
        # Remove common OCR artifacts
        text = text.strip()
        # Remove spaces (some captchas have no spaces)
        text = text.replace(" ", "")
        # Convert to uppercase if alphabetic
        if text.isalpha():
            text = text.upper()
        return text

    async def solve_with_retry(
        self,
        get_image_func,
        max_attempts: int = 3,
    ) -> Tuple[str, bytes]:
        """
        Attempt to solve captcha with retries.

        Args:
            get_image_func: Async function that returns captcha image bytes
            max_attempts: Maximum number of attempts

        Returns:
            Tuple of (answer, image_bytes)

        Raises:
            CaptchaError: If all attempts fail
        """
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                # Get new captcha image
                image_bytes = await get_image_func()

                # Attempt recognition
                answer = self.recognize(image_bytes)

                # Basic validation
                if len(answer) < 2:
                    raise CaptchaError("Answer too short")

                return answer, image_bytes

            except CaptchaError as e:
                last_error = e
                continue

        raise CaptchaError(
            f"Failed to solve captcha after {max_attempts} attempts: {last_error}"
        )


# Global captcha service instance
_captcha_service: CaptchaService | None = None


def get_captcha_service() -> CaptchaService:
    """Get the global captcha service instance."""
    global _captcha_service
    if _captcha_service is None:
        _captcha_service = CaptchaService()
    return _captcha_service
