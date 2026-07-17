from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.file_content_response import FileContentResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    sandbox_id: str,
    *,
    path: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["path"] = path

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/playground/sandboxes/{sandbox_id}/files/read".format(
            sandbox_id=quote(str(sandbox_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FileContentResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FileContentResponse.from_dict(response.json())

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
) -> Response[FileContentResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    sandbox_id: str,
    *,
    client: AuthenticatedClient | Client,
    path: str,
) -> Response[FileContentResponse | HTTPValidationError]:
    """Read Sandbox File

     Read a file from a playground sandbox workspace.

    Args:
        sandbox_id (str):
        path (str): File path relative to workspace

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FileContentResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        sandbox_id=sandbox_id,
        path=path,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    sandbox_id: str,
    *,
    client: AuthenticatedClient | Client,
    path: str,
) -> FileContentResponse | HTTPValidationError | None:
    """Read Sandbox File

     Read a file from a playground sandbox workspace.

    Args:
        sandbox_id (str):
        path (str): File path relative to workspace

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FileContentResponse | HTTPValidationError
    """

    return sync_detailed(
        sandbox_id=sandbox_id,
        client=client,
        path=path,
    ).parsed


async def asyncio_detailed(
    sandbox_id: str,
    *,
    client: AuthenticatedClient | Client,
    path: str,
) -> Response[FileContentResponse | HTTPValidationError]:
    """Read Sandbox File

     Read a file from a playground sandbox workspace.

    Args:
        sandbox_id (str):
        path (str): File path relative to workspace

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FileContentResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        sandbox_id=sandbox_id,
        path=path,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    sandbox_id: str,
    *,
    client: AuthenticatedClient | Client,
    path: str,
) -> FileContentResponse | HTTPValidationError | None:
    """Read Sandbox File

     Read a file from a playground sandbox workspace.

    Args:
        sandbox_id (str):
        path (str): File path relative to workspace

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FileContentResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            sandbox_id=sandbox_id,
            client=client,
            path=path,
        )
    ).parsed
