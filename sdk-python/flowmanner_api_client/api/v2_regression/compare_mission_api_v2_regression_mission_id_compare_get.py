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
    run_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_run_id: None | str | Unset
    if isinstance(run_id, Unset):
        json_run_id = UNSET
    else:
        json_run_id = run_id
    params["run_id"] = json_run_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/regression/{mission_id}/compare".format(
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
    run_id: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    r"""Compare Mission

     Compare a run against its template's expected behaviors.

    Returns a structured regression report with pass/fail/warn for each
    assertion, or a \"no baseline\" message if no expected_behaviors exist.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        run_id=run_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    run_id: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    r"""Compare Mission

     Compare a run against its template's expected behaviors.

    Returns a structured regression report with pass/fail/warn for each
    assertion, or a \"no baseline\" message if no expected_behaviors exist.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        run_id=run_id,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    run_id: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    r"""Compare Mission

     Compare a run against its template's expected behaviors.

    Returns a structured regression report with pass/fail/warn for each
    assertion, or a \"no baseline\" message if no expected_behaviors exist.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        run_id=run_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    run_id: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    r"""Compare Mission

     Compare a run against its template's expected behaviors.

    Returns a structured regression report with pass/fail/warn for each
    assertion, or a \"no baseline\" message if no expected_behaviors exist.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)

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
            run_id=run_id,
        )
    ).parsed
