import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/browser", tags=["browser"])


class PingRequest(BaseModel):
    message: str = "hello"


class PingResponse(BaseModel):
    success: bool
    message: str
    context_user: str


@router.post("/ping", response_model=PingResponse)
async def ping(
    request: PingRequest,
    current_user: User = Depends(get_current_user),
):
    from app.tools.base import ToolRegistry
    from app.tools.browser_ping import BrowserPingInput

    tool = ToolRegistry.get("browser_ping")  # type: ignore[arg-type]
    if tool is None:
        raise HTTPException(status_code=500, detail="browser_ping tool not registered")

    input_model = BrowserPingInput(message=request.message)
    result = await tool.run(  # type: ignore[attr-defined]
        input_dict={"message": input_model.message},
        context={"user_id": str(current_user.id)},
    )

    if result.status.value != "success":
        raise HTTPException(status_code=500, detail=result.error)

    return PingResponse(
        success=result.data["success"],
        message=result.data["message"],
        context_user=result.data["context_user"],
    )


class NavigateRequest(BaseModel):
    url: str


class NavigateResponse(BaseModel):
    success: bool
    url: str | None = None
    title: str | None = None
    status: int | None = None
    error: str | None = None


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(
    request: NavigateRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.navigate(str(current_user.id), request.url)

    if result.get("success"):
        return NavigateResponse(
            success=True,
            url=result.get("url"),
            title=result.get("title"),
            status=result.get("status"),
        )
    else:
        return NavigateResponse(
            success=False,
            error=result.get("error"),
        )


class ScreenshotResponse(BaseModel):
    success: bool
    screenshot: str | None = None
    url: str | None = None
    title: str | None = None
    error: str | None = None


@router.get("/screenshot", response_model=ScreenshotResponse)
async def screenshot(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.screenshot(str(current_user.id))

    if result.get("success"):
        return ScreenshotResponse(
            success=True,
            screenshot=result.get("screenshot"),
            url=result.get("url"),
            title=result.get("title"),
        )
    return ScreenshotResponse(success=False, error=result.get("error"))


@router.post("/close")
async def close(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.close(str(current_user.id))

    if result.get("success"):
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@router.get("/status")
async def status(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.status(str(current_user.id))
    return result


@router.get("/health")
async def health():
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    return service.health()


class ElementResponse(BaseModel):
    ref: str
    tag: str
    text: str
    role: str
    bbox: dict | None = None


class SnapshotResponse(BaseModel):
    success: bool
    elements: list[ElementResponse] = []
    fingerprint: str = ""
    url: str | None = None
    title: str | None = None
    error: str | None = None


@router.post("/snapshot", response_model=SnapshotResponse)
async def snapshot(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.snapshot(str(current_user.id))

    if result.get("success"):
        return SnapshotResponse(
            success=True,
            elements=result.get("elements", []),
            fingerprint=result.get("fingerprint", ""),
            url=result.get("url"),
            title=result.get("title"),
        )
    else:
        return SnapshotResponse(
            success=False,
            error=result.get("error"),
        )


class ClickRequest(BaseModel):
    ref: str


class ClickResponse(BaseModel):
    success: bool
    stale_ref: bool = False
    method: str | None = None
    healed: bool | None = None
    clicked_at: dict | None = None
    suggest_resnapshot: bool | None = None
    error: str | None = None


@router.post("/click", response_model=ClickResponse)
async def click(
    request: ClickRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.click(str(current_user.id), request.ref)

    if result.get("success"):
        return ClickResponse(
            success=True,
            stale_ref=result.get("stale_ref", False),
            method=result.get("method"),
            healed=result.get("healed"),
            clicked_at=result.get("clicked_at"),
        )
    else:
        return ClickResponse(
            success=False,
            error=result.get("error"),
            stale_ref=result.get("stale_ref", False),
            suggest_resnapshot=result.get("suggest_resnapshot"),
        )


class TypeRequest(BaseModel):
    ref: str
    text: str
    submit: bool = False


class TypeResponse(BaseModel):
    success: bool
    stale_ref: bool = False
    method: str | None = None
    healed: bool | None = None
    suggest_resnapshot: bool | None = None
    error: str | None = None


@router.post("/type", response_model=TypeResponse)
async def type_text(
    request: TypeRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.type_text(
        str(current_user.id),
        request.ref,
        request.text,
        request.submit,
    )

    if result.get("success"):
        return TypeResponse(
            success=True,
            stale_ref=result.get("stale_ref", False),
            method=result.get("method"),
            healed=result.get("healed"),
        )
    else:
        return TypeResponse(
            success=False,
            error=result.get("error"),
            stale_ref=result.get("stale_ref", False),
            suggest_resnapshot=result.get("suggest_resnapshot"),
        )


class ScrollRequest(BaseModel):
    x: int = 0
    y: int = 300


class ScrollResponse(BaseModel):
    success: bool
    error: str | None = None


@router.post("/scroll", response_model=ScrollResponse)
async def scroll(
    request: ScrollRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.scroll(str(current_user.id), request.x, request.y)

    if result.get("success"):
        return ScrollResponse(success=True)
    else:
        return ScrollResponse(success=False, error=result.get("error"))


# ─── P3 Feature Endpoints ───


class ViewportRequest(BaseModel):
    width: int = 1280
    height: int = 720


class ViewportResponse(BaseModel):
    success: bool
    width: int | None = None
    height: int | None = None
    error: str | None = None


@router.post("/viewport", response_model=ViewportResponse)
async def resize_viewport(
    request: ViewportRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.resize_viewport(str(current_user.id), request.width, request.height)
    if result.get("success"):
        return ViewportResponse(success=True, width=result["width"], height=result["height"])
    return ViewportResponse(success=False, error=result.get("error"))


class ConsoleLogEntry(BaseModel):
    type: str
    text: str
    timestamp: str


class ConsoleLogsResponse(BaseModel):
    success: bool
    logs: list[ConsoleLogEntry] = []
    error: str | None = None


@router.get("/console", response_model=ConsoleLogsResponse)
async def get_console_logs(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.get_console_logs(str(current_user.id))
    return ConsoleLogsResponse(
        success=result["success"],
        logs=result.get("logs", []),
        error=result.get("error"),
    )


class FullScreenshotResponse(BaseModel):
    success: bool
    screenshot: str | None = None
    url: str | None = None
    title: str | None = None
    error: str | None = None


@router.get("/screenshot/full", response_model=FullScreenshotResponse)
async def screenshot_full_page(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.screenshot_full_page(str(current_user.id))
    if result.get("success"):
        return FullScreenshotResponse(
            success=True,
            screenshot=result.get("screenshot"),
            url=result.get("url"),
            title=result.get("title"),
        )
    return FullScreenshotResponse(success=False, error=result.get("error"))


class AdBlockRequest(BaseModel):
    enabled: bool


class AdBlockResponse(BaseModel):
    success: bool
    ad_blocking: bool = False
    error: str | None = None


@router.post("/adblock", response_model=AdBlockResponse)
async def toggle_ad_blocking(
    request: AdBlockRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.toggle_ad_blocking(str(current_user.id), request.enabled)
    if result.get("success"):
        return AdBlockResponse(success=True, ad_blocking=result["ad_blocking"])
    return AdBlockResponse(success=False, error=result.get("error"))


class NavHistoryEntry(BaseModel):
    url: str
    title: str
    timestamp: str


class NavHistoryResponse(BaseModel):
    success: bool
    history: list[NavHistoryEntry] = []
    error: str | None = None


@router.get("/history", response_model=NavHistoryResponse)
async def get_navigation_history(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.get_navigation_history(str(current_user.id))
    return NavHistoryResponse(
        success=result["success"],
        history=result.get("history", []),
        error=result.get("error"),
    )


class ShareResponse(BaseModel):
    success: bool
    session_token: str | None = None
    share_url: str | None = None
    error: str | None = None


@router.get("/share", response_model=ShareResponse)
async def get_share_url(
    current_user: User = Depends(get_current_user),
):
    from app.services.browser_service import get_browser_service

    service = get_browser_service()
    result = await service.get_share_url(str(current_user.id))
    if result.get("success"):
        return ShareResponse(
            success=True,
            session_token=result["session_token"],
            share_url=result["share_url"],
        )
    return ShareResponse(success=False, error=result.get("error"))


class BrowserChatRequest(BaseModel):
    message: str
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    byok_key: str | None = None
    byok_base_url: str | None = None


class BrowserChatAction(BaseModel):
    tool: str
    result: str


class BrowserChatResponse(BaseModel):
    response: str
    actions: list[BrowserChatAction] = []
    final_url: str | None = None
    screenshot: str | None = None
    success: bool = True


@router.post("/chat", response_model=BrowserChatResponse)
async def browser_agent_chat(
    request: BrowserChatRequest,
    current_user: User = Depends(get_current_user),
):
    """LLM-powered browser agent chat endpoint."""
    from app.services.browser_agent import run_browser_agent
    from app.services.browser_manager import get_browser_manager
    from app.services.browser_service import get_browser_service

    user_id = str(current_user.id)

    try:
        result = await run_browser_agent(
            user_id,
            request.message,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            system_prompt=request.system_prompt,
            byok_key=request.byok_key,
            byok_base_url=request.byok_base_url,
        )

        # Build actions list
        actions = [BrowserChatAction(tool=a["tool"], result=a["result"]) for a in result.get("actions", [])]

        # Get screenshot for final state
        screenshot = result.get("screenshot")
        final_url = result.get("final_url")
        if not final_url:
            mgr = get_browser_manager()
            session = mgr.get_user_session(user_id)
            if session and session.is_active():
                try:
                    final_url = session.page.url
                    if not screenshot:
                        svc = get_browser_service()
                        ss = await svc.screenshot(user_id)
                        if ss.get("success"):
                            screenshot = ss.get("screenshot")
                            if not final_url:
                                final_url = ss.get("url")
                except Exception:
                    logger.debug("browser_agent_screenshot_fallback_failed", exc_info=True)

        logger.info(
            "Browser agent completed for user %s: %s",
            user_id,
            result.get("response", "")[:100],
        )

        return BrowserChatResponse(
            response=result.get("response", "Task completed."),
            actions=actions,
            final_url=final_url,
            screenshot=screenshot,
            success=result.get("success", True),
        )

    except Exception as e:
        logger.error("Browser agent error for user %s: %s", user_id, e, exc_info=True)
        return BrowserChatResponse(
            response=f"Agent error: {e!s}",
            actions=[],
            success=False,
        )
