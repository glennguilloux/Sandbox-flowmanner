from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.feedback_report_response import FeedbackReportResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast


def _get_kwargs(
    mission_id: str,
    *,
    offset: int | Unset = 0,
    limit: int | Unset = 20,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    params["offset"] = offset

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/feedback/missions/{mission_id}/reports".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[FeedbackReportResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = FeedbackReportResponse.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[FeedbackReportResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 20,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | list[FeedbackReportResponse]]:
    """List Reports Endpoint

     List feedback reports for a mission.

    Args:
        mission_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[FeedbackReportResponse]]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 20,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | list[FeedbackReportResponse] | None:
    """List Reports Endpoint

     List feedback reports for a mission.

    Args:
        mission_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[FeedbackReportResponse]
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 20,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | list[FeedbackReportResponse]]:
    """List Reports Endpoint

     List feedback reports for a mission.

    Args:
        mission_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[FeedbackReportResponse]]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 20,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | list[FeedbackReportResponse] | None:
    """List Reports Endpoint

     List feedback reports for a mission.

    Args:
        mission_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[FeedbackReportResponse]
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            offset=offset,
            limit=limit,
            accept_version=accept_version,
        )
    ).parsed
