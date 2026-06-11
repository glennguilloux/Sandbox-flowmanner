import logging
from urllib.parse import urlparse

from app.services.browser_manager import SessionCapacityError, get_browser_manager

logger = logging.getLogger(__name__)

BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}
BLOCKED_HOSTS = {"localhost", "0.0.0.0", "::1"}
BLOCKED_IP_RANGES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
]


def validate_url_for_navigation(url: str) -> tuple[bool, str | None]:
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower() if parsed.hostname else ""

        if scheme in BLOCKED_SCHEMES:
            return False, f"URL scheme '{scheme}://' is blocked"

        if host in BLOCKED_HOSTS:
            return False, f"localhost URLs are blocked"

        if host.startswith("127."):
            return False, f"127.x.x.x addresses are blocked"

        for ip_range in BLOCKED_IP_RANGES:
            if host.startswith(ip_range.split("/")[0].rsplit(".", 1)[0]):
                return False, f"Private IP ranges are blocked: {host}"

        return True, None
    except Exception as e:
        return False, f"URL validation error: {e!s}"


class BrowserService:
    async def navigate(self, user_id: str, url: str) -> dict:
        valid, error = validate_url_for_navigation(url)
        if not valid:
            return {"success": False, "error": error}

        manager = get_browser_manager()

        try:
            session = await manager.get_or_create_session(user_id)
        except SessionCapacityError as e:
            return {"success": False, "error": str(e)}

        try:
            page = session.page

            response = await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            final_url = page.url

            valid_redirect, redirect_error = validate_url_for_navigation(final_url)
            if not valid_redirect:
                return {
                    "success": False,
                    "error": f"Redirect blocked: {redirect_error}",
                }

            title = await page.title()

            session.touch_user_interaction()
            session.add_navigation_entry(final_url, title)

            return {
                "success": True,
                "url": final_url,
                "title": title,
                "status": response.status if response else 200,
            }
        except Exception as e:
            logger.error("Navigation error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def screenshot(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            page = session.page

            screenshot_bytes = await page.screenshot(type="png")
            import base64

            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            current_url = page.url
            title = await page.title()

            session.touch()

            return {
                "success": True,
                "screenshot": screenshot_b64,
                "url": current_url,
                "title": title,
            }
        except Exception as e:
            logger.error("Screenshot error for user %s: %s", user_id, e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def close(self, user_id: str) -> dict:
        manager = get_browser_manager()

        try:
            await manager.close_user_session(user_id)
            return {"success": True}
        except Exception as e:
            logger.error("Close error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def snapshot(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            page = session.page

            # Inject accessibility tree script
            accessibility_script = """
            () => {
                const getAriaRole = (el) => {
                    const role = el.getAttribute('role');
                    if (role) return role;
                    if (el.tagName === 'INPUT') return 'textbox';
                    if (el.tagName === 'BUTTON') return 'button';
                    if (el.tagName === 'A') return 'link';
                    if (el.tagName === 'CHECKBOX') return 'checkbox';
                    if (el.tagName === 'RADIO') return 'radio';
                    if (el.tagName === 'SELECT') return 'combobox';
                    if (el.tagName === 'IMG') return 'img';
                    return 'none';
                };

                const getText = (el) => {
                    if (el.alt) return el.alt;
                    if (el.value && el.type !== 'submit') return el.value;
                    return (el.textContent || '').trim().substring(0, 100);
                };

                const elements = [];
                const selector = (el) => {
                    if (el.id) return '#' + el.id;
                    if (el.className) return el.className.split(' ')[0] ? '.' + el.className.split(' ')[0].replace(/[^a-zA-Z0-9_-]/g, '') : null;
                    return null;
                };

                // Get all interactive elements
                const all = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"]');
                const seen = new Set();

                all.forEach((el, idx) => {
                    if (seen.has(el)) return;
                    seen.add(el);

                    const sel = selector(el);
                    const role = getAriaRole(el);
                    const text = getText(el);

                    if (sel || text) {
                        elements.push({
                            tag: el.tagName.toLowerCase(),
                            text: text,
                            role: role,
                            selector: sel,
                        });
                    }
                });

                // Generate fingerprint
                const fingerprint = btoa(JSON.stringify(elements.slice(0, 10).map(e => e.text))).substring(0, 32);

                return { elements, fingerprint };
            }
            """

            result = await page.evaluate(f"({accessibility_script})()")
            elements_data = result.get("elements", [])
            fingerprint = result.get("fingerprint", "")

            # Clear old elements and register new ones
            session.clear_elements()
            registered_elements = []

            for el_data in elements_data:
                bbox = None
                selector = el_data.get("selector")
                if selector:
                    try:
                        handle = await page.query_selector(selector)
                        if handle:
                            box = await handle.bounding_box()
                            if box:
                                bbox = {
                                    "x": box["x"],
                                    "y": box["y"],
                                    "width": box["width"],
                                    "height": box["height"],
                                    "center_x": box["x"] + box["width"] / 2,
                                    "center_y": box["y"] + box["height"] / 2,
                                }
                    except Exception:
                        logger.debug("snapshot_bbox_failed", exc_info=True)

                ref = session.register_element(
                    tag=el_data["tag"],
                    text=el_data["text"],
                    role=el_data["role"],
                    selector=selector or "",
                    bbox=bbox,
                )
                registered_elements.append(
                    {
                        "ref": ref,
                        "tag": el_data["tag"],
                        "text": el_data["text"],
                        "role": el_data["role"],
                        "bbox": bbox,
                    }
                )

            session.snapshot_fingerprint = fingerprint
            session.touch()

            current_url = page.url
            title = await page.title()

            return {
                "success": True,
                "elements": registered_elements,
                "fingerprint": fingerprint,
                "url": current_url,
                "title": title,
            }
        except Exception as e:
            logger.error("Snapshot error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def _click_by_coordinates(self, page, x: float, y: float) -> bool:
        try:
            await page.mouse.click(x, y)
            return True
        except Exception:
            return False

    async def click(self, user_id: str, ref: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            locator = session.get_locator(ref)
            if not locator:
                return {"success": False, "error": f"Element ref '{ref}' not found"}

            page = session.page

            selector = locator.selector
            if not selector:
                return {"success": False, "error": f"No selector for element {ref}"}

            try:
                handle = await page.query_selector(selector)
                if handle:
                    await handle.click(timeout=5000)
                session.touch_user_interaction()
                return {
                    "success": True,
                    "stale_ref": False,
                    "method": "ref",
                }
            except Exception:
                logger.debug("click_selector_failed", exc_info=True)

            if locator.bbox_center_x is not None and locator.bbox_center_y is not None:
                healed = await self._click_by_coordinates(page, locator.bbox_center_x, locator.bbox_center_y)
                if healed:
                    session.touch_user_interaction()
                    return {
                        "success": True,
                        "stale_ref": False,
                        "method": "coordinate",
                        "healed": True,
                        "clicked_at": {
                            "x": locator.bbox_center_x,
                            "y": locator.bbox_center_y,
                        },
                    }

            return {
                "success": False,
                "error": "Element not found — ref stale and coordinates unavailable",
                "stale_ref": True,
                "suggest_resnapshot": True,
            }
        except Exception as e:
            logger.error("Click error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def type_text(self, user_id: str, ref: str, text: str, submit: bool = False) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            locator = session.get_locator(ref)
            if not locator:
                return {"success": False, "error": f"Element ref '{ref}' not found"}

            page = session.page

            selector = locator.selector
            if not selector:
                return {"success": False, "error": f"No selector for element {ref}"}

            is_input = locator.tag in ["input", "textarea"]
            if not is_input and locator.role in ["textbox", "combobox"]:
                is_input = True

            if not is_input:
                return {
                    "success": False,
                    "error": f"Element {ref} is not an input field",
                }

            try:
                handle = await page.query_selector(selector)
                if handle:
                    await handle.fill(text)
                else:
                    raise Exception("No handle")
            except Exception:
                if locator.bbox_center_x is not None and locator.bbox_center_y is not None:
                    healed = await self._click_by_coordinates(page, locator.bbox_center_x, locator.bbox_center_y)
                    if healed:
                        await page.keyboard.type(text)
                        if submit:
                            await page.keyboard.press("Enter")
                        session.touch_user_interaction()
                        return {
                            "success": True,
                            "stale_ref": False,
                            "method": "coordinate",
                            "healed": True,
                        }
                return {
                    "success": False,
                    "error": "Element not found — ref stale and coordinates unavailable",
                    "stale_ref": True,
                    "suggest_resnapshot": True,
                }

            if submit:
                try:
                    await page.press(selector, "Enter")
                except Exception:
                    await page.keyboard.press("Enter")

            session.touch_user_interaction()
            return {
                "success": True,
                "stale_ref": False,
                "method": "ref",
            }
        except Exception as e:
            logger.error("Type error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def scroll(self, user_id: str, x: int = 0, y: int = 300) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            page = session.page

            await page.evaluate(f"window.scrollBy({x}, {y})")
            session.touch()

            return {"success": True}
        except Exception as e:
            logger.error("Scroll error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def status(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {
                "success": True,
                "active": False,
                "url": None,
                "title": None,
            }

        try:
            current_url = session.page.url
            title = await session.page.title()

            return {
                "success": True,
                "active": True,
                "url": current_url,
                "title": title,
                "last_interaction": session.last_user_interaction.isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def health(self) -> dict:
        manager = get_browser_manager()
        stats = manager.get_stats()

        return {
            "status": "ok",
            "active_sessions": stats["active_sessions"],
            "max_sessions": stats["max_sessions"],
            "available_slots": stats["available_slots"],
        }

    # ─── P3 Features ───

    async def resize_viewport(self, user_id: str, width: int, height: int) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            await session.resize_viewport(width, height)
            session.touch()
            return {"success": True, "width": width, "height": height}
        except Exception as e:
            logger.error("Viewport resize error for user %s: %s", user_id, e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_console_logs(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session", "logs": []}

        return {"success": True, "logs": session.console_logs[-100:]}

    async def screenshot_full_page(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            import base64

            page = session.page
            screenshot_bytes = await page.screenshot(type="png", full_page=True)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            session.touch()
            return {
                "success": True,
                "screenshot": screenshot_b64,
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as e:
            logger.error("Full-page screenshot error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def toggle_ad_blocking(self, user_id: str, enabled: bool) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        try:
            await session.set_ad_blocking(enabled)
            session.touch()
            return {"success": True, "ad_blocking": enabled}
        except Exception as e:
            logger.error("Ad blocking toggle error for user %s: %s", user_id, e)
            return {"success": False, "error": str(e)}

    async def get_navigation_history(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {
                "success": False,
                "error": "No active browser session",
                "history": [],
            }

        return {"success": True, "history": session.navigation_history}

    async def get_share_url(self, user_id: str) -> dict:
        manager = get_browser_manager()
        session = manager.get_user_session(user_id)

        if not session or not session.is_active():
            return {"success": False, "error": "No active browser session"}

        return {
            "success": True,
            "session_token": session.session_token,
            "share_url": f"/tools/browser?session={session.session_token}",
        }


_browser_service_instance = None


def get_browser_service():
    """Return the BrowserService singleton (Playwright-based).

    Previously used a FLOWMANNER_HARNESS_MODE feature flag to choose
    between Playwright BrowserService and CDP HarnessBrowserService.
    The feature flag and HarnessBrowserService have been removed.
    """
    global _browser_service_instance
    if _browser_service_instance is None:
        _browser_service_instance = BrowserService()
    return _browser_service_instance
