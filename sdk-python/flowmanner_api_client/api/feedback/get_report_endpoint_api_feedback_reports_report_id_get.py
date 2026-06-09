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
    report_id: str,
    *,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/feedback/reports/{report_id}".format(
            report_id=quote(str(report_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FeedbackReportResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FeedbackReportResponse.from_dict(response.json())

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
) -> Response[FeedbackReportResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    report_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[FeedbackReportResponse | HTTPValidationError]:
    """Get Report Endpoint

     Get a specific feedback report.

    Args:
        report_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedbackReportResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        report_id=report_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    report_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> FeedbackReportResponse | HTTPValidationError | None:
    """Get Report Endpoint

     Get a specific feedback report.

    Args:
        report_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedbackReportResponse | HTTPValidationError
    """

    return sync_detailed(
        report_id=report_id,
        client=client,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    report_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[FeedbackReportResponse | HTTPValidationError]:
    """Get Report Endpoint

     Get a specific feedback report.

    Args:
        report_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedbackReportResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        report_id=report_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    report_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> FeedbackReportResponse | HTTPValidationError | None:
    """Get Report Endpoint

     Get a specific feedback report.

    Args:
        report_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedbackReportResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            report_id=report_id,
            client=client,
            accept_version=accept_version,
        )
    ).parsed
