import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    STARTING = "starting"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class ElementLocator:
    ref: str
    tag: str
    text: str
    role: str
    selector: str
    xpath: str | None = None
    # Bounding box for coordinate-based fallback (self-healing)
    bbox_x: float | None = None
    bbox_y: float | None = None
    bbox_width: float | None = None
    bbox_height: float | None = None
    bbox_center_x: float | None = None
    bbox_center_y: float | None = None


@dataclass
class BrowserSession:
    session_id: str
    user_id: str
    status: SessionStatus = SessionStatus.STARTING
    playwright: Any = None
    browser: Any = None
    context: Any = None
    page: Any = None
    last_user_interaction: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    timeout_seconds: int = 300
    timeout_task: asyncio.Task | None = None
    on_timeout_callback: Any = None
    element_map: dict[str, ElementLocator] = field(default_factory=dict)
    element_counter: int = 0
    snapshot_fingerprint: str = ""
    # P3 features
    navigation_history: list[dict] = field(default_factory=list)
    console_logs: list[dict] = field(default_factory=list)
    ad_blocking: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    session_token: str = ""

    async def start(self, on_timeout_callback=None):
        import uuid

        from playwright.async_api import async_playwright

        self.status = SessionStatus.STARTING
        self.on_timeout_callback = on_timeout_callback
        self.session_token = uuid.uuid4().hex[:12]

        pw = await async_playwright().start()
        self.playwright = pw

        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        self.browser = browser

        context = await browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.37",
        )
        self.context = context

        page = await context.new_page()
        self.page = page

        # Capture console logs
        page.on("console", self._on_console_message)
        page.on("pageerror", self._on_page_error)

        self.status = SessionStatus.ACTIVE
        self.last_user_interaction = datetime.now(UTC)
        self.last_activity = datetime.now(UTC)

        self._start_timeout_watchdog()

        logger.info(f"Browser session {self.session_id} started for user {self.user_id}")

    def _start_timeout_watchdog(self):
        async def watchdog():
            while self.status == SessionStatus.ACTIVE:
                await asyncio.sleep(10)
                idle_time = (datetime.now(UTC) - self.last_user_interaction).total_seconds()
                if idle_time >= self.timeout_seconds:
                    logger.info(f"Session {self.session_id} timed out after {idle_time}s")
                    if self.on_timeout_callback:
                        await self.on_timeout_callback(self.session_id)
                    break

        self.timeout_task = asyncio.create_task(watchdog())

    async def close(self):
        self.status = SessionStatus.CLOSING

        if self.timeout_task:
            self.timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.timeout_task

        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

        self.status = SessionStatus.CLOSED
        logger.info(f"Browser session {self.session_id} closed")

    def touch_user_interaction(self):
        self.last_user_interaction = datetime.now(UTC)

    def touch(self):
        self.last_activity = datetime.now(UTC)

    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE and self.page is not None

    def register_element(self, tag: str, text: str, role: str, selector: str, xpath: str | None = None, bbox: dict | None = None) -> str:
        self.element_counter += 1
        ref = f"e{self.element_counter}"
        self.element_map[ref] = ElementLocator(
            ref=ref,
            tag=tag,
            text=text,
            role=role,
            selector=selector,
            xpath=xpath,
            bbox_x=bbox.get("x") if bbox else None,
            bbox_y=bbox.get("y") if bbox else None,
            bbox_width=bbox.get("width") if bbox else None,
            bbox_height=bbox.get("height") if bbox else None,
            bbox_center_x=(bbox.get("x", 0) + bbox.get("width", 0) / 2) if bbox else None,
            bbox_center_y=(bbox.get("y", 0) + bbox.get("height", 0) / 2) if bbox else None,
        )
        return ref

    def get_locator(self, ref: str) -> ElementLocator | None:
        return self.element_map.get(ref)

    def clear_elements(self):
        self.element_map.clear()
        self.element_counter = 0
        self.snapshot_fingerprint = ""

    def _on_console_message(self, msg):
        self.console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        # Keep only last 200 entries
        if len(self.console_logs) > 200:
            self.console_logs = self.console_logs[-200:]

    def _on_page_error(self, err):
        self.console_logs.append({
            "type": "error",
            "text": str(err),
            "timestamp": datetime.now(UTC).isoformat(),
        })

    def add_navigation_entry(self, url: str, title: str):
        self.navigation_history.append({
            "url": url,
            "title": title,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        # Keep only last 50 entries
        if len(self.navigation_history) > 50:
            self.navigation_history = self.navigation_history[-50:]

    async def resize_viewport(self, width: int, height: int):
        """Resize the browser viewport."""
        self.viewport_width = width
        self.viewport_height = height
        await self.page.set_viewport_size({"width": width, "height": height})
        # Stabilize after resize — re-layout can race with screenshot
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            logger.debug("viewport_stabilize_failed", exc_info=True)

    async def set_ad_blocking(self, enabled: bool) -> bool:
        """Toggle ad blocking via route interception."""
        self.ad_blocking = enabled
        # Common ad/tracker domains to block
        blocked_patterns = [
            "*://*.doubleclick.net/*",
            "*://*.googleadservices.com/*",
            "*://*.googlesyndication.com/*",
            "*://*.google-analytics.com/*",
            "*://*.facebook.com/tr*",
            "*://*.adsrvr.org/*",
            "*://*.adnxs.com/*",
            "*://*.adsafeprotected.com/*",
            "*://*.outbrain.com/*",
            "*://*.taboola.com/*",
        ]

        async def _abort_handler(route):
            await route.abort()

        if enabled:
            for pattern in blocked_patterns:
                await self.page.route(pattern, _abort_handler)
        else:
            # Only unroute the ad-block patterns, not ALL routes
            for pattern in blocked_patterns:
                await self.page.unroute(pattern)
        return True