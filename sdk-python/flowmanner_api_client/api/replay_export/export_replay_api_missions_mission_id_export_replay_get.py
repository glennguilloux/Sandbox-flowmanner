from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    mission_id: UUID,
    *,
    format_: str | Unset = "html",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["format"] = format_

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/{mission_id}/export-replay".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    format_: str | Unset = "html",
) -> Response[Any | HTTPValidationError]:
    r"""Export Replay

     Export a mission's replay as a shareable report.

    Returns a self-contained HTML page (default) or JSON showing
    the full event timeline, cost breakdown, and execution summary.

    This is the \"proof\" layer: clients get a deliverable AND a
    step-by-step replay of how the AI produced it.

    Args:
        mission_id (UUID):
        format_ (str | Unset): Export format: 'html' or 'json' Default: 'html'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        format_=format_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    format_: str | Unset = "html",
) -> Any | HTTPValidationError | None:
    r"""Export Replay

     Export a mission's replay as a shareable report.

    Returns a self-contained HTML page (default) or JSON showing
    the full event timeline, cost breakdown, and execution summary.

    This is the \"proof\" layer: clients get a deliverable AND a
    step-by-step replay of how the AI produced it.

    Args:
        mission_id (UUID):
        format_ (str | Unset): Export format: 'html' or 'json' Default: 'html'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        format_=format_,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    format_: str | Unset = "html",
) -> Response[Any | HTTPValidationError]:
    r"""Export Replay

     Export a mission's replay as a shareable report.

    Returns a self-contained HTML page (default) or JSON showing
    the full event timeline, cost breakdown, and execution summary.

    This is the \"proof\" layer: clients get a deliverable AND a
    step-by-step replay of how the AI produced it.

    Args:
        mission_id (UUID):
        format_ (str | Unset): Export format: 'html' or 'json' Default: 'html'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        format_=format_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    format_: str | Unset = "html",
) -> Any | HTTPValidationError | None:
    r"""Export Replay

     Export a mission's replay as a shareable report.

    Returns a self-contained HTML page (default) or JSON showing
    the full event timeline, cost breakdown, and execution summary.

    This is the \"proof\" layer: clients get a deliverable AND a
    step-by-step replay of how the AI produced it.

    Args:
        mission_id (UUID):
        format_ (str | Unset): Export format: 'html' or 'json' Default: 'html'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            format_=format_,
        )
    ).parsed
