from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    mission_id: None | Unset | UUID = UNSET,
    program_id: None | Unset | UUID = UNSET,
    critic_kind: None | str | Unset = UNSET,
    min_score_overall: float | None | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_mission_id: None | str | Unset
    if isinstance(mission_id, Unset):
        json_mission_id = UNSET
    elif isinstance(mission_id, UUID):
        json_mission_id = str(mission_id)
    else:
        json_mission_id = mission_id
    params["mission_id"] = json_mission_id

    json_program_id: None | str | Unset
    if isinstance(program_id, Unset):
        json_program_id = UNSET
    elif isinstance(program_id, UUID):
        json_program_id = str(program_id)
    else:
        json_program_id = program_id
    params["program_id"] = json_program_id

    json_critic_kind: None | str | Unset
    if isinstance(critic_kind, Unset):
        json_critic_kind = UNSET
    else:
        json_critic_kind = critic_kind
    params["critic_kind"] = json_critic_kind

    json_min_score_overall: float | None | Unset
    if isinstance(min_score_overall, Unset):
        json_min_score_overall = UNSET
    else:
        json_min_score_overall = min_score_overall
    params["min_score_overall"] = json_min_score_overall

    params["page"] = page

    params["per_page"] = per_page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/critiques",
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
    *,
    client: AuthenticatedClient,
    mission_id: None | Unset | UUID = UNSET,
    program_id: None | Unset | UUID = UNSET,
    critic_kind: None | str | Unset = UNSET,
    min_score_overall: float | None | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[Any | HTTPValidationError]:
    """List Critiques

     Paginated list of critiques for the current user+workspace.

    Filters are all optional. The route is the only place where
    ``page``/``per_page`` are converted to ``offset``/``limit`` for
    the service layer (service uses limit/offset; route exposes
    page/per_page for clients — the v2 envelope convention).

    Args:
        mission_id (None | Unset | UUID):
        program_id (None | Unset | UUID):
        critic_kind (None | str | Unset):
        min_score_overall (float | None | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        program_id=program_id,
        critic_kind=critic_kind,
        min_score_overall=min_score_overall,
        page=page,
        per_page=per_page,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    mission_id: None | Unset | UUID = UNSET,
    program_id: None | Unset | UUID = UNSET,
    critic_kind: None | str | Unset = UNSET,
    min_score_overall: float | None | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Any | HTTPValidationError | None:
    """List Critiques

     Paginated list of critiques for the current user+workspace.

    Filters are all optional. The route is the only place where
    ``page``/``per_page`` are converted to ``offset``/``limit`` for
    the service layer (service uses limit/offset; route exposes
    page/per_page for clients — the v2 envelope convention).

    Args:
        mission_id (None | Unset | UUID):
        program_id (None | Unset | UUID):
        critic_kind (None | str | Unset):
        min_score_overall (float | None | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        mission_id=mission_id,
        program_id=program_id,
        critic_kind=critic_kind,
        min_score_overall=min_score_overall,
        page=page,
        per_page=per_page,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mission_id: None | Unset | UUID = UNSET,
    program_id: None | Unset | UUID = UNSET,
    critic_kind: None | str | Unset = UNSET,
    min_score_overall: float | None | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[Any | HTTPValidationError]:
    """List Critiques

     Paginated list of critiques for the current user+workspace.

    Filters are all optional. The route is the only place where
    ``page``/``per_page`` are converted to ``offset``/``limit`` for
    the service layer (service uses limit/offset; route exposes
    page/per_page for clients — the v2 envelope convention).

    Args:
        mission_id (None | Unset | UUID):
        program_id (None | Unset | UUID):
        critic_kind (None | str | Unset):
        min_score_overall (float | None | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        program_id=program_id,
        critic_kind=critic_kind,
        min_score_overall=min_score_overall,
        page=page,
        per_page=per_page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    mission_id: None | Unset | UUID = UNSET,
    program_id: None | Unset | UUID = UNSET,
    critic_kind: None | str | Unset = UNSET,
    min_score_overall: float | None | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Any | HTTPValidationError | None:
    """List Critiques

     Paginated list of critiques for the current user+workspace.

    Filters are all optional. The route is the only place where
    ``page``/``per_page`` are converted to ``offset``/``limit`` for
    the service layer (service uses limit/offset; route exposes
    page/per_page for clients — the v2 envelope convention).

    Args:
        mission_id (None | Unset | UUID):
        program_id (None | Unset | UUID):
        critic_kind (None | str | Unset):
        min_score_overall (float | None | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            mission_id=mission_id,
            program_id=program_id,
            critic_kind=critic_kind,
            min_score_overall=min_score_overall,
            page=page,
            per_page=per_page,
        )
    ).parsed
