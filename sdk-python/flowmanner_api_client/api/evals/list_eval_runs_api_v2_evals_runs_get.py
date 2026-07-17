from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.eval_run_list_response import EvalRunListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    dataset_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_dataset_id: None | str | Unset
    if isinstance(dataset_id, Unset):
        json_dataset_id = UNSET
    else:
        json_dataset_id = dataset_id
    params["dataset_id"] = json_dataset_id

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/evals/runs",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EvalRunListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EvalRunListResponse.from_dict(response.json())

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
) -> Response[EvalRunListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    dataset_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[EvalRunListResponse | HTTPValidationError]:
    """List Eval Runs

     List eval runs, optionally filtered by dataset or status.

    Args:
        dataset_id (None | str | Unset):
        status (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalRunListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        status=status,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    dataset_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> EvalRunListResponse | HTTPValidationError | None:
    """List Eval Runs

     List eval runs, optionally filtered by dataset or status.

    Args:
        dataset_id (None | str | Unset):
        status (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalRunListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        dataset_id=dataset_id,
        status=status,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    dataset_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[EvalRunListResponse | HTTPValidationError]:
    """List Eval Runs

     List eval runs, optionally filtered by dataset or status.

    Args:
        dataset_id (None | str | Unset):
        status (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EvalRunListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dataset_id=dataset_id,
        status=status,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    dataset_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> EvalRunListResponse | HTTPValidationError | None:
    """List Eval Runs

     List eval runs, optionally filtered by dataset or status.

    Args:
        dataset_id (None | str | Unset):
        status (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EvalRunListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            dataset_id=dataset_id,
            status=status,
            limit=limit,
        )
    ).parsed
