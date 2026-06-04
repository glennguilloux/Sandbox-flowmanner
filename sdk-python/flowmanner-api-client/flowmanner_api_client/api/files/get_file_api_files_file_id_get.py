from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.file_response import FileResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response, Unset


def _get_kwargs(
    file_id: str,
    *,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/files/{file_id}".format(
            file_id=quote(str(file_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FileResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FileResponse.from_dict(response.json())

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
) -> Response[FileResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    file_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[FileResponse | HTTPValidationError]:
    """Get File

    Args:
        file_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FileResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        file_id=file_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    file_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> FileResponse | HTTPValidationError | None:
    """Get File

    Args:
        file_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FileResponse | HTTPValidationError
    """

    return sync_detailed(
        file_id=file_id,
        client=client,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    file_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[FileResponse | HTTPValidationError]:
    """Get File

    Args:
        file_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FileResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        file_id=file_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    file_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> FileResponse | HTTPValidationError | None:
    """Get File

    Args:
        file_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FileResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            file_id=file_id,
            client=client,
            accept_version=accept_version,
        )
    ).parsed
