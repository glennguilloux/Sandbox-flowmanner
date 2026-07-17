from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.program_update_status_type_0 import ProgramUpdateStatusType0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cron_trigger import CronTrigger
    from ..models.manual_trigger import ManualTrigger
    from ..models.program_update_base_constraints_type_0 import ProgramUpdateBaseConstraintsType0
    from ..models.program_update_base_context_files_type_0 import ProgramUpdateBaseContextFilesType0
    from ..models.program_update_base_context_urls_type_0 import ProgramUpdateBaseContextUrlsType0
    from ..models.webhook_trigger import WebhookTrigger


T = TypeVar("T", bound="ProgramUpdate")


@_attrs_define
class ProgramUpdate:
    """Request body for ``PATCH /programs/{id}`` — PATCH semantics.

    All fields Optional. ``status`` is restricted to the documented literals
    so a typo in the client returns 422, not 500.

        Attributes:
            name (None | str | Unset):
            description (None | str | Unset):
            mission_type (None | str | Unset):
            base_constraints (None | ProgramUpdateBaseConstraintsType0 | Unset):
            base_context_files (None | ProgramUpdateBaseContextFilesType0 | Unset):
            base_context_urls (None | ProgramUpdateBaseContextUrlsType0 | Unset):
            trigger_config (CronTrigger | ManualTrigger | None | Unset | WebhookTrigger):
            per_run_budget_usd (float | None | Unset):
            monthly_budget_usd (float | None | Unset):
            status (None | ProgramUpdateStatusType0 | Unset):
    """

    name: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    mission_type: None | str | Unset = UNSET
    base_constraints: None | ProgramUpdateBaseConstraintsType0 | Unset = UNSET
    base_context_files: None | ProgramUpdateBaseContextFilesType0 | Unset = UNSET
    base_context_urls: None | ProgramUpdateBaseContextUrlsType0 | Unset = UNSET
    trigger_config: CronTrigger | ManualTrigger | None | Unset | WebhookTrigger = UNSET
    per_run_budget_usd: float | None | Unset = UNSET
    monthly_budget_usd: float | None | Unset = UNSET
    status: None | ProgramUpdateStatusType0 | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.cron_trigger import CronTrigger
        from ..models.manual_trigger import ManualTrigger
        from ..models.program_update_base_constraints_type_0 import ProgramUpdateBaseConstraintsType0
        from ..models.program_update_base_context_files_type_0 import ProgramUpdateBaseContextFilesType0
        from ..models.program_update_base_context_urls_type_0 import ProgramUpdateBaseContextUrlsType0
        from ..models.webhook_trigger import WebhookTrigger

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        mission_type: None | str | Unset
        if isinstance(self.mission_type, Unset):
            mission_type = UNSET
        else:
            mission_type = self.mission_type

        base_constraints: dict[str, Any] | None | Unset
        if isinstance(self.base_constraints, Unset):
            base_constraints = UNSET
        elif isinstance(self.base_constraints, ProgramUpdateBaseConstraintsType0):
            base_constraints = self.base_constraints.to_dict()
        else:
            base_constraints = self.base_constraints

        base_context_files: dict[str, Any] | None | Unset
        if isinstance(self.base_context_files, Unset):
            base_context_files = UNSET
        elif isinstance(self.base_context_files, ProgramUpdateBaseContextFilesType0):
            base_context_files = self.base_context_files.to_dict()
        else:
            base_context_files = self.base_context_files

        base_context_urls: dict[str, Any] | None | Unset
        if isinstance(self.base_context_urls, Unset):
            base_context_urls = UNSET
        elif isinstance(self.base_context_urls, ProgramUpdateBaseContextUrlsType0):
            base_context_urls = self.base_context_urls.to_dict()
        else:
            base_context_urls = self.base_context_urls

        trigger_config: dict[str, Any] | None | Unset
        if isinstance(self.trigger_config, Unset):
            trigger_config = UNSET
        elif isinstance(self.trigger_config, CronTrigger):
            trigger_config = self.trigger_config.to_dict()
        elif isinstance(self.trigger_config, WebhookTrigger):
            trigger_config = self.trigger_config.to_dict()
        elif isinstance(self.trigger_config, ManualTrigger):
            trigger_config = self.trigger_config.to_dict()
        else:
            trigger_config = self.trigger_config

        per_run_budget_usd: float | None | Unset
        if isinstance(self.per_run_budget_usd, Unset):
            per_run_budget_usd = UNSET
        else:
            per_run_budget_usd = self.per_run_budget_usd

        monthly_budget_usd: float | None | Unset
        if isinstance(self.monthly_budget_usd, Unset):
            monthly_budget_usd = UNSET
        else:
            monthly_budget_usd = self.monthly_budget_usd

        status: None | str | Unset
        if isinstance(self.status, Unset):
            status = UNSET
        elif isinstance(self.status, ProgramUpdateStatusType0):
            status = self.status.value
        else:
            status = self.status

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if description is not UNSET:
            field_dict["description"] = description
        if mission_type is not UNSET:
            field_dict["mission_type"] = mission_type
        if base_constraints is not UNSET:
            field_dict["base_constraints"] = base_constraints
        if base_context_files is not UNSET:
            field_dict["base_context_files"] = base_context_files
        if base_context_urls is not UNSET:
            field_dict["base_context_urls"] = base_context_urls
        if trigger_config is not UNSET:
            field_dict["trigger_config"] = trigger_config
        if per_run_budget_usd is not UNSET:
            field_dict["per_run_budget_usd"] = per_run_budget_usd
        if monthly_budget_usd is not UNSET:
            field_dict["monthly_budget_usd"] = monthly_budget_usd
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cron_trigger import CronTrigger
        from ..models.manual_trigger import ManualTrigger
        from ..models.program_update_base_constraints_type_0 import ProgramUpdateBaseConstraintsType0
        from ..models.program_update_base_context_files_type_0 import ProgramUpdateBaseContextFilesType0
        from ..models.program_update_base_context_urls_type_0 import ProgramUpdateBaseContextUrlsType0
        from ..models.webhook_trigger import WebhookTrigger

        d = dict(src_dict)

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))

        def _parse_mission_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_type = _parse_mission_type(d.pop("mission_type", UNSET))

        def _parse_base_constraints(data: object) -> None | ProgramUpdateBaseConstraintsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_constraints_type_0 = ProgramUpdateBaseConstraintsType0.from_dict(data)

                return base_constraints_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramUpdateBaseConstraintsType0 | Unset, data)

        base_constraints = _parse_base_constraints(d.pop("base_constraints", UNSET))

        def _parse_base_context_files(data: object) -> None | ProgramUpdateBaseContextFilesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_context_files_type_0 = ProgramUpdateBaseContextFilesType0.from_dict(data)

                return base_context_files_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramUpdateBaseContextFilesType0 | Unset, data)

        base_context_files = _parse_base_context_files(d.pop("base_context_files", UNSET))

        def _parse_base_context_urls(data: object) -> None | ProgramUpdateBaseContextUrlsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_context_urls_type_0 = ProgramUpdateBaseContextUrlsType0.from_dict(data)

                return base_context_urls_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramUpdateBaseContextUrlsType0 | Unset, data)

        base_context_urls = _parse_base_context_urls(d.pop("base_context_urls", UNSET))

        def _parse_trigger_config(data: object) -> CronTrigger | ManualTrigger | None | Unset | WebhookTrigger:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trigger_config_type_0_type_0 = CronTrigger.from_dict(data)

                return trigger_config_type_0_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trigger_config_type_0_type_1 = WebhookTrigger.from_dict(data)

                return trigger_config_type_0_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                trigger_config_type_0_type_2 = ManualTrigger.from_dict(data)

                return trigger_config_type_0_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CronTrigger | ManualTrigger | None | Unset | WebhookTrigger, data)

        trigger_config = _parse_trigger_config(d.pop("trigger_config", UNSET))

        def _parse_per_run_budget_usd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        per_run_budget_usd = _parse_per_run_budget_usd(d.pop("per_run_budget_usd", UNSET))

        def _parse_monthly_budget_usd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        monthly_budget_usd = _parse_monthly_budget_usd(d.pop("monthly_budget_usd", UNSET))

        def _parse_status(data: object) -> None | ProgramUpdateStatusType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_type_0 = ProgramUpdateStatusType0(data)

                return status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramUpdateStatusType0 | Unset, data)

        status = _parse_status(d.pop("status", UNSET))

        program_update = cls(
            name=name,
            description=description,
            mission_type=mission_type,
            base_constraints=base_constraints,
            base_context_files=base_context_files,
            base_context_urls=base_context_urls,
            trigger_config=trigger_config,
            per_run_budget_usd=per_run_budget_usd,
            monthly_budget_usd=monthly_budget_usd,
            status=status,
        )

        return program_update
