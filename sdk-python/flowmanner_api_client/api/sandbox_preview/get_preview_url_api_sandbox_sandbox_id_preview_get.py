from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.sandbox_preview_response import SandboxPreviewResponse
from ...types import Response


def _get_kwargs(
    sandbox_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/sandbox/{sandbox_id}/preview".format(
            sandbox_id=quote(str(sandbox_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SandboxPreviewResponse | None:
    if response.status_code == 200:
        response_200 = SandboxPreviewResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | SandboxPreviewResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    sandbox_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | SandboxPreviewResponse]:
    """Get Preview Url

     Return the live preview info for a sandbox.

    Proxies to sandboxd's ``GET /v1/sandboxes/{id}`` and extracts the
    ``preview`` sub-object.  The preview URL format is::

        s-<sandbox-id>-<port>.preview.<domain>

    Each exposed port gets its own subdomain; Traefik routes based on
    the ``Host`` header.

    Args:
        sandbox_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SandboxPreviewResponse]
    """

    kwargs = _get_kwargs(
        sandbox_id=sandbox_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    sandbox_id: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | SandboxPreviewResponse | None:
    """Get Preview Url

     Return the live preview info for a sandbox.

    Proxies to sandboxd's ``GET /v1/sandboxes/{id}`` and extracts the
    ``preview`` sub-object.  The preview URL format is::

        s-<sandbox-id>-<port>.preview.<domain>

    Each exposed port gets its own subdomain; Traefik routes based on
    the ``Host`` header.

    Args:
        sandbox_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SandboxPreviewResponse
    """

    return sync_detailed(
        sandbox_id=sandbox_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    sandbox_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | SandboxPreviewResponse]:
    """Get Preview Url

     Return the live preview info for a sandbox.

    Proxies to sandboxd's ``GET /v1/sandboxes/{id}`` and extracts the
    ``preview`` sub-object.  The preview URL format is::

        s-<sandbox-id>-<port>.preview.<domain>

    Each exposed port gets its own subdomain; Traefik routes based on
    the ``Host`` header.

    Args:
        sandbox_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SandboxPreviewResponse]
    """

    kwargs = _get_kwargs(
        sandbox_id=sandbox_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    sandbox_id: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | SandboxPreviewResponse | None:
    """Get Preview Url

     Return the live preview info for a sandbox.

    Proxies to sandboxd's ``GET /v1/sandboxes/{id}`` and extracts the
    ``preview`` sub-object.  The preview URL format is::

        s-<sandbox-id>-<port>.preview.<domain>

    Each exposed port gets its own subdomain; Traefik routes based on
    the ``Host`` header.

    Args:
        sandbox_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SandboxPreviewResponse
    """

    return (
        await asyncio_detailed(
            sandbox_id=sandbox_id,
            client=client,
        )
    ).parsed
