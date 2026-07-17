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
    cost_headroom: float | Unset = 1.5,
    latency_headroom: float | Unset = 2.0,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_run_id: None | str | Unset
    if isinstance(run_id, Unset):
        json_run_id = UNSET
    else:
        json_run_id = run_id
    params["run_id"] = json_run_id

    params["cost_headroom"] = cost_headroom

    params["latency_headroom"] = latency_headroom

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/regression/{mission_id}/freeze-baseline".format(
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
    cost_headroom: float | Unset = 1.5,
    latency_headroom: float | Unset = 2.0,
) -> Response[Any | HTTPValidationError]:
    r"""Freeze Baseline

     Extract expected behaviors from a successful run and save to the mission's template.

    This is the \"record expected behavior\" action. Run it on a known-good
    mission to establish the baseline for future regression checks.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)
        cost_headroom (float | Unset): Cost ceiling headroom multiplier Default: 1.5.
        latency_headroom (float | Unset): Latency ceiling headroom multiplier Default: 2.0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        run_id=run_id,
        cost_headroom=cost_headroom,
        latency_headroom=latency_headroom,
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
    cost_headroom: float | Unset = 1.5,
    latency_headroom: float | Unset = 2.0,
) -> Any | HTTPValidationError | None:
    r"""Freeze Baseline

     Extract expected behaviors from a successful run and save to the mission's template.

    This is the \"record expected behavior\" action. Run it on a known-good
    mission to establish the baseline for future regression checks.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)
        cost_headroom (float | Unset): Cost ceiling headroom multiplier Default: 1.5.
        latency_headroom (float | Unset): Latency ceiling headroom multiplier Default: 2.0.

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
        cost_headroom=cost_headroom,
        latency_headroom=latency_headroom,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    run_id: None | str | Unset = UNSET,
    cost_headroom: float | Unset = 1.5,
    latency_headroom: float | Unset = 2.0,
) -> Response[Any | HTTPValidationError]:
    r"""Freeze Baseline

     Extract expected behaviors from a successful run and save to the mission's template.

    This is the \"record expected behavior\" action. Run it on a known-good
    mission to establish the baseline for future regression checks.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)
        cost_headroom (float | Unset): Cost ceiling headroom multiplier Default: 1.5.
        latency_headroom (float | Unset): Latency ceiling headroom multiplier Default: 2.0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        run_id=run_id,
        cost_headroom=cost_headroom,
        latency_headroom=latency_headroom,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    run_id: None | str | Unset = UNSET,
    cost_headroom: float | Unset = 1.5,
    latency_headroom: float | Unset = 2.0,
) -> Any | HTTPValidationError | None:
    r"""Freeze Baseline

     Extract expected behaviors from a successful run and save to the mission's template.

    This is the \"record expected behavior\" action. Run it on a known-good
    mission to establish the baseline for future regression checks.

    Args:
        mission_id (UUID):
        run_id (None | str | Unset): Override run_id (defaults to mission's latest)
        cost_headroom (float | Unset): Cost ceiling headroom multiplier Default: 1.5.
        latency_headroom (float | Unset): Latency ceiling headroom multiplier Default: 2.0.

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
            cost_headroom=cost_headroom,
            latency_headroom=latency_headroom,
        )
    ).parsed
