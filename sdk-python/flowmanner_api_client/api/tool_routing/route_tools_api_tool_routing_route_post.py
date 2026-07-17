from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.route_request import RouteRequest
from ...models.tool_route_result import ToolRouteResult
from ...types import Response


def _get_kwargs(
    *,
    body: RouteRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/tool-routing/route",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ToolRouteResult | None:
    if response.status_code == 200:
        response_200 = ToolRouteResult.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | ToolRouteResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: RouteRequest,
) -> Response[HTTPValidationError | ToolRouteResult]:
    """Route Tools

     Score and select top-k tool candidates for a task.

    Returns a bounded candidate set when confidence is high enough,
    or falls back to the full registry when confidence is low.

    Args:
        body (RouteRequest): Request body for POST /tool-routing/route.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolRouteResult]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: RouteRequest,
) -> HTTPValidationError | ToolRouteResult | None:
    """Route Tools

     Score and select top-k tool candidates for a task.

    Returns a bounded candidate set when confidence is high enough,
    or falls back to the full registry when confidence is low.

    Args:
        body (RouteRequest): Request body for POST /tool-routing/route.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolRouteResult
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: RouteRequest,
) -> Response[HTTPValidationError | ToolRouteResult]:
    """Route Tools

     Score and select top-k tool candidates for a task.

    Returns a bounded candidate set when confidence is high enough,
    or falls back to the full registry when confidence is low.

    Args:
        body (RouteRequest): Request body for POST /tool-routing/route.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolRouteResult]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: RouteRequest,
) -> HTTPValidationError | ToolRouteResult | None:
    """Route Tools

     Score and select top-k tool candidates for a task.

    Returns a bounded candidate set when confidence is high enough,
    or falls back to the full registry when confidence is low.

    Args:
        body (RouteRequest): Request body for POST /tool-routing/route.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolRouteResult
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
