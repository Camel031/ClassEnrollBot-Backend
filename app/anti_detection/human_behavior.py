"""Human behavior simulation for browser automation."""

import asyncio
import math
import random
from typing import List, Tuple


def bezier_curve(
    start: Tuple[int, int],
    end: Tuple[int, int],
    control_points: int = 2,
) -> List[Tuple[int, int]]:
    """
    Generate bezier curve points for natural mouse movement.

    Args:
        start: Starting position (x, y)
        end: Ending position (x, y)
        control_points: Number of control points

    Returns:
        List of (x, y) points along the curve
    """
    points = [start]

    # Generate random control points
    controls = []
    for _ in range(control_points):
        cx = random.randint(min(start[0], end[0]), max(start[0], end[0]))
        cy = random.randint(min(start[1], end[1]), max(start[1], end[1]))
        controls.append((cx, cy))

    # Generate curve points
    steps = random.randint(20, 40)
    for i in range(1, steps + 1):
        t = i / steps

        # Simple quadratic bezier if we have control points
        if controls:
            ctrl = controls[0]
            x = int((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * end[0])
            y = int((1 - t) ** 2 * start[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * end[1])
        else:
            x = int(start[0] + (end[0] - start[0]) * t)
            y = int(start[1] + (end[1] - start[1]) * t)

        points.append((x, y))

    return points


def generate_typing_delays(text: str) -> List[float]:
    """
    Generate human-like typing delays for each character.

    Args:
        text: Text to type

    Returns:
        List of delays in seconds for each character
    """
    delays = []
    for i, char in enumerate(text):
        # Base delay with normal distribution
        delay = random.gauss(0.12, 0.04)

        # Longer delay after spaces or punctuation
        if i > 0 and text[i - 1] in " .,!?":
            delay += random.uniform(0.1, 0.3)

        # Occasional pause (thinking)
        if random.random() < 0.05:
            delay += random.uniform(0.3, 0.8)

        # Clamp values
        delay = max(0.05, min(0.4, delay))
        delays.append(delay)

    return delays


async def simulate_reading(min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
    """
    Simulate user reading the page.

    Args:
        min_seconds: Minimum reading time
        max_seconds: Maximum reading time
    """
    reading_time = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(reading_time)


async def simulate_scroll_behavior(page: any, scroll_count: int | None = None) -> None:
    """
    Simulate user scrolling behavior on a page.

    Args:
        page: Browser page object (nodriver page)
        scroll_count: Number of scroll actions (random if None)
    """
    if scroll_count is None:
        scroll_count = random.randint(1, 3)

    for _ in range(scroll_count):
        scroll_amount = random.randint(100, 400)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.5, 1.5))


class HumanBehaviorSimulator:
    """Simulates human-like browser interactions."""

    def __init__(self, page: any) -> None:
        """
        Initialize simulator with a browser page.

        Args:
            page: nodriver page object
        """
        self.page = page
        self._last_mouse_position = (random.randint(0, 500), random.randint(0, 500))

    async def move_mouse_to(self, x: int, y: int) -> None:
        """
        Move mouse to position with natural bezier curve.

        Args:
            x: Target X position
            y: Target Y position
        """
        path = bezier_curve(self._last_mouse_position, (x, y))

        for px, py in path:
            await self.page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(0.01, 0.03))

        self._last_mouse_position = (x, y)

    async def click_element(self, element: any) -> None:
        """
        Click an element with human-like behavior.

        Args:
            element: Page element to click
        """
        # Get element bounds
        box = await element.get_position()

        # Click at a random position within the element
        target_x = int(box.x + random.randint(5, max(6, int(box.width) - 5)))
        target_y = int(box.y + random.randint(5, max(6, int(box.height) - 5)))

        # Move mouse to element
        await self.move_mouse_to(target_x, target_y)

        # Random delay before click
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Click with random hold time
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.page.mouse.up()

        # Small delay after click
        await asyncio.sleep(random.uniform(0.1, 0.2))

    async def type_text(self, element: any, text: str, make_typos: bool = True) -> None:
        """
        Type text with human-like delays and occasional typos.

        Args:
            element: Input element to type into
            text: Text to type
            make_typos: Whether to occasionally make and correct typos
        """
        await self.click_element(element)
        await asyncio.sleep(random.uniform(0.2, 0.5))

        delays = generate_typing_delays(text)

        for i, (char, delay) in enumerate(zip(text, delays)):
            # Occasionally make a typo and correct it (5% chance)
            if make_typos and random.random() < 0.05 and i < len(text) - 1:
                wrong_char = random.choice("qwertyuiopasdfghjklzxcvbnm")
                await self.page.keyboard.type(wrong_char)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await self.page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.1, 0.2))

            # Type the correct character
            await self.page.keyboard.type(char)
            await asyncio.sleep(delay)

    async def fill_form_field(self, element: any, value: str) -> None:
        """
        Fill a form field naturally.

        Args:
            element: Form field element
            value: Value to fill
        """
        # Clear existing content
        await self.click_element(element)
        await self.page.keyboard.press("Control+a")
        await asyncio.sleep(random.uniform(0.05, 0.1))

        # Type new value
        await self.type_text(element, value, make_typos=False)
