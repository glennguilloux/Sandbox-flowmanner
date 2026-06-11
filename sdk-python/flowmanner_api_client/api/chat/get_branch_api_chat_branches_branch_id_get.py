from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.chat_branch_response import ChatBranchResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response, Unset


def _get_kwargs(
    branch_id: int,
    *,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chat/branches/{branch_id}".format(
            branch_id=quote(str(branch_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ChatBranchResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChatBranchResponse.from_dict(response.json())

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
) -> Response[ChatBranchResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    branch_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[ChatBranchResponse | HTTPValidationError]:
    """Get Branch

    Args:
        branch_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatBranchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        branch_id=branch_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    branch_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> ChatBranchResponse | HTTPValidationError | None:
    """Get Branch

    Args:
        branch_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatBranchResponse | HTTPValidationError
    """

    return sync_detailed(
        branch_id=branch_id,
        client=client,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    branch_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[ChatBranchResponse | HTTPValidationError]:
    """Get Branch

    Args:
        branch_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatBranchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        branch_id=branch_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    branch_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> ChatBranchResponse | HTTPValidationError | None:
    """Get Branch

    Args:
        branch_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatBranchResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            branch_id=branch_id,
            client=client,
            accept_version=accept_version,
        )
    ).parsed
