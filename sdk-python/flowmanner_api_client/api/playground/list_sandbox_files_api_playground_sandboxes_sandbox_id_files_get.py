from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.file_entry import FileEntry
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    sandbox_id: str,
    *,
    path: str | Unset = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["path"] = path

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/playground/sandboxes/{sandbox_id}/files".format(
            sandbox_id=quote(str(sandbox_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[FileEntry] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = FileEntry.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[FileEntry]]:
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
    path: str | Unset = "",
) -> Response[HTTPValidationError | list[FileEntry]]:
    """List Sandbox Files

     List files in a playground sandbox.

    Requires session token via query param for anonymous sandboxes,
    or auth for claimed sandboxes.

    Args:
        sandbox_id (str):
        path (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[FileEntry]]
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
    path: str | Unset = "",
) -> HTTPValidationError | list[FileEntry] | None:
    """List Sandbox Files

     List files in a playground sandbox.

    Requires session token via query param for anonymous sandboxes,
    or auth for claimed sandboxes.

    Args:
        sandbox_id (str):
        path (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[FileEntry]
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
    path: str | Unset = "",
) -> Response[HTTPValidationError | list[FileEntry]]:
    """List Sandbox Files

     List files in a playground sandbox.

    Requires session token via query param for anonymous sandboxes,
    or auth for claimed sandboxes.

    Args:
        sandbox_id (str):
        path (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[FileEntry]]
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
    path: str | Unset = "",
) -> HTTPValidationError | list[FileEntry] | None:
    """List Sandbox Files

     List files in a playground sandbox.

    Requires session token via query param for anonymous sandboxes,
    or auth for claimed sandboxes.

    Args:
        sandbox_id (str):
        path (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[FileEntry]
    """

    return (
        await asyncio_detailed(
            sandbox_id=sandbox_id,
            client=client,
            path=path,
        )
    ).parsed
