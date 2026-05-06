from datetime import datetime, timedelta
from logging import Logger
import random
import math
import time
from playwright.sync_api import FrameLocator, Locator, Page


class HumanMouseSimulator:
    """
    Simulates human-like mouse movements and interactions for Playwright.
    Provides methods for realistic cursor behavior including Bézier curves,
    acceleration/deceleration, random jitter, and shaky-hand movements.
    """

    def __init__(self, page: Page, logger: Logger):
        """
        Initialize the HumanMouseSimulator.

        Args:
            page: Playwright Page instance
            logger: Logger instance for debug output
        """
        self.page = page
        self.logger = logger

        # Set initial position based on viewport dimensions
        viewport = page.viewport_size
        if viewport:
            # Random position within viewport (avoiding edges)
            margin = 50  # Pixels from edge
            x = random.randint(margin, max(margin + 1, viewport['width'] - margin))
            y = random.randint(margin, max(margin + 1, viewport['height'] - margin))
            self.last_position = {"x": x, "y": y}
            self.logger.debug(f"Initial mouse position set to: {self.last_position} (viewport: {viewport['width']}x{viewport['height']})")
        else:
            # Fallback if viewport is not available
            self.last_position = {"x": 1, "y": 1}
            self.logger.debug("Viewport unavailable, using default position (1, 1)")

    def enable_mouse_tracking(self):
        """Enable mouse position tracking in the page and all frames."""
        script = """
            window._mouseX = 0;
            window._mouseY = 0;
            window.addEventListener('mousemove', e => {
                window._mouseX = e.clientX;
                window._mouseY = e.clientY;
                //console.log(window._mouseX + "," + window._mouseY)
            }, true);
        """

        # Inject into main page
        self.page.add_init_script(script)
        self.page.evaluate(script)

        # Inject into existing iframes
        for frame in self.page.frames:
            try:
                frame.evaluate(script)
            except:
                pass

        # Inject into future iframes
        def on_frame_attached(frame):
            try:
                frame.evaluate(script)
            except:
                pass

        self.page.on("frameattached", on_frame_attached)

        # Force initialization to last known position
        self.page.mouse.move(self.last_position["x"], self.last_position["y"])

    @staticmethod
    def safe_bounding_box(locator: Locator, retries: int = 10, delay: float = 0.05):
        """
        Safely get element bounding box with retries.

        Args:
            locator: Playwright Locator
            retries: Number of retry attempts
            delay: Delay between retries in seconds

        Returns:
            Bounding box dictionary with x, y, width, height

        Raises:
            RuntimeError: If bounding box is still None after all retries
        """
        for _ in range(retries):
            box = locator.bounding_box()
            if box is not None:
                return box
            time.sleep(delay)
        raise RuntimeError("Element bounding box is None after retries")

    def reset_position(self, x: int = None, y: int = None, randomize: bool = True):
        """
        Reset the last known mouse position.

        Args:
            x: X coordinate to reset to (optional)
            y: Y coordinate to reset to (optional)
            randomize: If True and x/y not provided, set random position based on viewport (default: True)
        """
        if x is not None and y is not None:
            # Use provided coordinates
            self.last_position = {"x": x, "y": y}
            self.logger.debug(f"Reset mouse position to: {self.last_position}")
        elif randomize:
            # Set random position based on viewport
            viewport = self.page.viewport_size
            if viewport:
                margin = 50
                x = random.randint(margin, max(margin + 1, viewport['width'] - margin))
                y = random.randint(margin, max(margin + 1, viewport['height'] - margin))
                self.last_position = {"x": x, "y": y}
                self.logger.debug(f"Reset mouse position to random: {self.last_position}")
            else:
                self.last_position = {"x": 1, "y": 1}
                self.logger.debug("Viewport unavailable, reset to default (1, 1)")
        else:
            # No randomization, use default
            self.last_position = {"x": 1, "y": 1}
            self.logger.debug(f"Reset mouse position to default: {self.last_position}")

    def get_real_mouse_position(self):
        """
        Get the current mouse position from tracked coordinates.
        Falls back to last known position if tracking data is unavailable.
        Checks both main page and iframe contexts.

        Returns:
            Dictionary with x and y coordinates
        """
        # Try main page first
        pos = self.page.evaluate("({ x: window._mouseX, y: window._mouseY })")

        # If main page has valid position, use it
        if pos["x"] is not None and pos["y"] is not None and pos["x"] != 0 and pos["y"] != 0:
            self.last_position = {"x": pos["x"], "y": pos["y"]}
            self.logger.debug(f"Cursor position (main page): {pos}")
            return pos

        # Try to get position from iframes
        for frame in self.page.frames:
            if frame != self.page.main_frame:
                try:
                    frame_pos = frame.evaluate("({ x: window._mouseX, y: window._mouseY })")
                    if frame_pos["x"] is not None and frame_pos["y"] is not None and frame_pos["x"] != 0 and frame_pos["y"] != 0:
                        # Convert iframe coordinates to page coordinates if needed
                        # For now, we'll use the values as-is since mouse.move() uses page coordinates
                        self.last_position = {"x": frame_pos["x"], "y": frame_pos["y"]}
                        self.logger.debug(f"Cursor position (iframe): {frame_pos}")
                        return frame_pos
                except Exception as e:
                    self.logger.debug(f"Could not get position from frame: {e}")
                    continue

        # Fallback to last known position
        self.logger.debug(f"Mouse position unavailable, using last known position: {self.last_position}")
        return self.last_position

    def mouse_move2(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        steps: int = 40,
        shaky_hand: bool = True
    ):
        """
        Human-like mouse movement with:
        - segmented movement
        - overshoot + correction
        - acceleration/deceleration
        - jitter + tremor
        - micro-pauses
        """

        # -----------------------------
        # 1. Randomized target inside element
        # -----------------------------
        end_x += random.uniform(-2, 2)
        end_y += random.uniform(-2, 2)

        # -----------------------------
        # 2. Overshoot (humans rarely stop perfectly)
        # -----------------------------
        overshoot_x = end_x + random.uniform(-8, 8)
        overshoot_y = end_y + random.uniform(-8, 8)

        # Movement segments: rough → correction → fine adjust
        segments = [
            (start_x, start_y, overshoot_x, overshoot_y, int(steps * 0.6)),
            (overshoot_x, overshoot_y, end_x, end_y, int(steps * 0.4)),
        ]

        for (sx, sy, ex, ey, seg_steps) in segments:

            # Random control point for curvature
            cx = (sx + ex) / 2 + random.randint(-90, 90)
            cy = (sy + ey) / 2 + random.randint(-90, 90)

            for i in range(seg_steps + 1):
                t = i / seg_steps

                # Smooth acceleration/deceleration
                t = t * t * (3 - 2 * t)

                # Quadratic Bézier curve
                x = (1 - t)**2 * sx + 2 * (1 - t) * t * cx + t**2 * ex
                y = (1 - t)**2 * sy + 2 * (1 - t) * t * cy + t**2 * ey

                # Natural jitter
                x += random.uniform(-0.8, 0.8)
                y += random.uniform(-0.8, 0.8)

                # Shaky hand micro-oscillation
                if shaky_hand:
                    x += math.sin(t * math.pi * random.randint(2, 4)) * random.uniform(0.3, 1.0)
                    y += math.cos(t * math.pi * random.randint(2, 4)) * random.uniform(0.3, 1.0)

                # Move mouse
                self.page.mouse.move(x, y)

                # Variable delay (more natural)
                base_delay = 0.003 + (1 - abs(0.5 - t)) * 0.012
                time.sleep(base_delay + random.uniform(0.001, 0.004))

            # Micro pause between segments
            time.sleep(random.uniform(0.015, 0.045))

        # -----------------------------
        # 3. Final tremor (tiny human correction)
        # -----------------------------
        for _ in range(random.randint(1, 3)):
            tremor_x = end_x + random.uniform(-1.2, 1.2)
            tremor_y = end_y + random.uniform(-1.2, 1.2)
            self.page.mouse.move(tremor_x, tremor_y)
            time.sleep(random.uniform(0.01, 0.025))

        # Update last known position
        self.last_position = {"x": end_x, "y": end_y}

    def mouse_move(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        steps: int = 40,
        shaky_hand: bool = True
    ):
        """
        Move mouse in a curved, human-like path with:
        - Bézier curve
        - Acceleration/deceleration
        - Random jitter
        - Optional shaky-hand micro movements

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            steps: Number of movement steps
            shaky_hand: Enable micro oscillations for realism
        """
        # Random control point for curve
        cx = (start_x + end_x) / 2 + random.randint(-80, 80)
        cy = (start_y + end_y) / 2 + random.randint(-80, 80)

        for i in range(steps + 1):
            # Ease-in / ease-out curve
            t = i / steps
            t = t * t * (3 - 2 * t)  # smoothstep easing

            # Quadratic Bézier curve
            x = (1 - t)**2 * start_x + 2 * (1 - t) * t * cx + t**2 * end_x
            y = (1 - t)**2 * start_y + 2 * (1 - t) * t * cy + t**2 * end_y

            # Small jitter
            x += random.uniform(-1.2, 1.2)
            y += random.uniform(-1.2, 1.2)

            # Shaky hand mode (micro oscillations)
            if shaky_hand:
                x += math.sin(t * math.pi * random.randint(2, 5)) * random.uniform(0.5, 1.5)
                y += math.cos(t * math.pi * random.randint(2, 5)) * random.uniform(0.5, 1.5)

            self.logger.debug(f"Mouse move {x},{y}")
            self.page.mouse.move(x, y)

            # Variable delay (slower at start/end)
            base_delay = 0.004 + (1 - abs(0.5 - t)) * 0.01
            time.sleep(base_delay + random.uniform(0.001, 0.004))

        # Update last known position to final destination
        self.last_position = {"x": end_x, "y": end_y}

    def mouse_move_fast(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        steps: int = 28,          # fewer steps = faster movement
        shaky_hand: bool = True
    ):
        """
        Faster human-like mouse movement using:
        - Quadratic Bézier curve
        - Smoothstep easing
        - Lightweight jitter
        - Optional micro-oscillation
        """

        # Precompute random control point
        cx = (start_x + end_x) * 0.5 + random.uniform(-60, 60)
        cy = (start_y + end_y) * 0.5 + random.uniform(-60, 60)

        # Pre-generate oscillation frequencies (avoids randint inside loop)
        osc_x = random.randint(2, 5)
        osc_y = random.randint(2, 5)

        for i in range(steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)  # smoothstep easing

            # Bézier curve
            mt = 1 - t
            x = mt * mt * start_x + 2 * mt * t * cx + t * t * end_x
            y = mt * mt * start_y + 2 * mt * t * cy + t * t * end_y

            # Small jitter
            x += random.uniform(-0.8, 0.8)
            y += random.uniform(-0.8, 0.8)

            # Shaky-hand micro oscillations
            if shaky_hand:
                x += math.sin(t * math.pi * osc_x) * random.uniform(0.3, 1.0)
                y += math.cos(t * math.pi * osc_y) * random.uniform(0.3, 1.0)

            self.logger.debug(f"Mouse move {x},{y}")
            self.page.mouse.move(x, y)

            # Much faster delay
            #delay = 0.0015 + (1 - abs(0.5 - t)) * 0.003 / 3
            #delay += random.uniform(0.0003, 0.0012)
            #delay = random.uniform(0.000001, 0.00003)
            #time.sleep(delay)

        self.last_position = {"x": end_x, "y": end_y}

    def move_and_type(self, locator: Locator, text: str, delay: float = None):
        """
        Move mouse to element, click it, and fill with text.

        Args:
            locator: Playwright Locator
            text: Text to fill into the element
        """
        locator.wait_for(state="visible")
        box = self.safe_bounding_box(locator)

        # target_x = box["x"] + box["width"] / 2
        # target_y = box["y"] + box["height"] / 2
        target_x = box["x"] + random.uniform(0.3, 0.7) * box["width"]
        target_y = box["y"] + random.uniform(0.3, 0.7) * box["height"]

        # Current mouse position
        pos = self.get_real_mouse_position()
        start_x, start_y = pos["x"], pos["y"]

        # Human-like movement
        self.mouse_move(start_x, start_y, target_x, target_y)

        # Click
        self.page.mouse.click(target_x, target_y)

        # Type
        # locator.fill(text)
        self.logger.debug(f'Fill text {text}')
        locator.press_sequentially(text, delay=delay)

    def drag_slider(self, start_locator: Locator, end_locator: Locator):
        """
        Drag a slider from start position to end position with human-like movement.

        Args:
            start_locator: Locator for slider handle
            end_locator: Locator for slider target
        """
        # Wait for elements
        start_locator.wait_for(state="visible")
        end_locator.wait_for(state="visible")

        # Get bounding boxes
        start_box = self.safe_bounding_box(start_locator)
        end_box = self.safe_bounding_box(end_locator)

        # Start position = center of slider handle
        start_x = start_box["x"] + start_box["width"] / 2
        start_y = start_box["y"] + start_box["height"] / 2

        # End position = center of slider target
        end_x = end_box["x"] + end_box["width"] / 2
        end_y = end_box["y"] + end_box["height"] / 2

        # Move mouse to start (human-like)
        pos = self.get_real_mouse_position()
        rd = random.randint(0,100)
        if rd < 50:
            self.mouse_move(pos["x"], pos["y"], start_x, start_y, 28)
        elif rd >= 50 and rd < 75:
            self.mouse_move2(pos["x"], pos["y"], start_x, start_y)
        else:
            self.mouse_move_fast(pos["x"], pos["y"], start_x, start_y)

        # Real mouse down
        self.page.mouse.down()

        # Small human hesitation
        time.sleep(random.uniform(0.05, 0.15))

        # Drag to end (human-like)
        self.mouse_move(start_x, start_y, end_x, end_y)

        # Real mouse up
        self.page.mouse.up()

    def click(self, locator: Locator, shaky_hand: bool = True):
        """
        Move the mouse to the locator using human-like movement,
        then perform a real click (mouse.down + mouse.up).

        Args:
            locator: Playwright Locator
            shaky_hand: Enable shaky hand micro movements
        """
        # Ensure element is visible
        locator.wait_for(state="visible")

        # Get element bounding box
        box = self.safe_bounding_box(locator)

        target_x = box["x"] + box["width"] / 2
        target_y = box["y"] + box["height"] / 2

        # Current mouse position
        pos = self.get_real_mouse_position()
        start_x, start_y = pos["x"], pos["y"]

        # Move mouse to target with human-like curve
        self.mouse_move(
            start_x,
            start_y,
            target_x,
            target_y,
            shaky_hand=shaky_hand
        )

        # Small hesitation before clicking
        time.sleep(random.uniform(0.05, 0.15))

        # Real click
        self.page.mouse.down()
        time.sleep(random.uniform(0.03, 0.08))  # human click duration
        self.page.mouse.up()

    def human_delay(self, base, jitter_ratio=0.3, min_delay=0.05):
        jitter = base * jitter_ratio
        return max(min_delay, random.uniform(base - jitter, base + jitter))

    def simulate_human_typing(self, sequences, fill_func):
        """
        sequences: liste avec start, end, duration, number
        fill_func: fonction qui remplit un champ (locator, value)
        """

        first = sequences[0].duration / 2
        reaction_time = first + random.uniform(0.3, 0.8)
        self.logger.info(f'Sleep during {reaction_time} seconds')
        time.sleep(reaction_time)

        last_time = reaction_time

        for i, seq in enumerate(sequences):
            if i > 0:
                gap = seq.start - last_time
                base_delay = gap * random.uniform(0.4, 0.8)
                human_delay = self.human_delay(base_delay)
                self.logger.info(f'Sleep during {human_delay} seconds')
                time.sleep(human_delay)

            typing_speed = random.uniform(0.08, 0.2)
            fill_func(i, seq.number, typing_speed)

            if random.random() < 0.2:
                time.sleep(random.uniform(0.1, 0.4))

            last_time = seq.start

    @staticmethod
    def wait_for_frame_selector(frame: FrameLocator, locator: str, timeout_seconds: int = 30) -> bool:
        """
        Wait for a selector to appear in a frame.

        Args:
            frame: Playwright FrameLocator
            locator: CSS selector string
            timeout_seconds: Maximum time to wait in seconds

        Returns:
            True if selector appears, False if timeout reached
        """
        old_date = datetime.now()
        timeout = timedelta(seconds=timeout_seconds)

        while True:
            if frame.locator(locator).count() > 0:
                return True
            time.sleep(0.5)
            if datetime.now() > (old_date + timeout):
                return False

    def random_mouse_movements(self, count: int = 10, allow_scroll: bool = True):
        """
        Simulate random human-like mouse movements across the viewport.

        Args:
            count: number of movements
            allow_scroll: randomly perform scroll actions
        """

        viewport = self.page.viewport_size
        if not viewport:
            self.logger.debug("Viewport unavailable, skipping random_mouse_movements")
            return

        width = viewport["width"]
        height = viewport["height"]

        self.logger.debug(f"Starting random_mouse_movements with {count} moves")

        for i in range(count):
            # Get current position (real if possible)
            pos = self.get_real_mouse_position()
            start_x, start_y = pos["x"], pos["y"]

            # Random target (avoid edges)
            margin = 50
            target_x = random.randint(margin, max(margin + 1, width - margin))
            target_y = random.randint(margin, max(margin + 1, height - margin))

            self.logger.debug(f"[Move {i+1}] {start_x},{start_y} → {target_x},{target_y}")

            # Use your BEST movement (mouse_move2 = ultra réaliste)
            self.mouse_move2(
                start_x,
                start_y,
                target_x,
                target_y,
                steps=random.randint(25, 60),
                shaky_hand=True
            )

            # Micro pause (humain)
            pause = random.uniform(0.2, 1.2)
            self.logger.debug(f"Pause after move: {pause:.2f}s")
            time.sleep(pause)

            # Scroll occasionnel (très important pour Datadome)
            if allow_scroll and random.random() < 0.35:
                scroll_amount = random.randint(100, 800) * random.choice([-1, 1])
                self.logger.debug(f"Scrolling: {scroll_amount}")

                self.page.mouse.wheel(0, scroll_amount)

                # Pause après scroll
                time.sleep(random.uniform(0.3, 1.0))

            # Micro "hover hesitation"
            if random.random() < 0.2:
                jitter_x = target_x + random.uniform(-5, 5)
                jitter_y = target_y + random.uniform(-5, 5)

                self.logger.debug(f"Micro hover jitter: {jitter_x},{jitter_y}")
                self.page.mouse.move(jitter_x, jitter_y)
                time.sleep(random.uniform(0.05, 0.2))

        self.logger.debug("Finished random_mouse_movements")