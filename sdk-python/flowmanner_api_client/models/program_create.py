from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cron_trigger import CronTrigger
    from ..models.manual_trigger import ManualTrigger
    from ..models.program_create_base_constraints_type_0 import ProgramCreateBaseConstraintsType0
    from ..models.program_create_base_context_files_type_0 import ProgramCreateBaseContextFilesType0
    from ..models.program_create_base_context_urls_type_0 import ProgramCreateBaseContextUrlsType0
    from ..models.webhook_trigger import WebhookTrigger


T = TypeVar("T", bound="ProgramCreate")


@_attrs_define
class ProgramCreate:
    """Request body for ``POST /programs``.

    Attributes:
        name (str):
        description (str | Unset):  Default: ''.
        mission_type (None | str | Unset):
        base_constraints (None | ProgramCreateBaseConstraintsType0 | Unset):
        base_context_files (None | ProgramCreateBaseContextFilesType0 | Unset):
        base_context_urls (None | ProgramCreateBaseContextUrlsType0 | Unset):
        trigger_config (CronTrigger | ManualTrigger | None | Unset | WebhookTrigger):
        per_run_budget_usd (float | None | Unset):
        monthly_budget_usd (float | None | Unset):
    """

    name: str
    description: str | Unset = ""
    mission_type: None | str | Unset = UNSET
    base_constraints: None | ProgramCreateBaseConstraintsType0 | Unset = UNSET
    base_context_files: None | ProgramCreateBaseContextFilesType0 | Unset = UNSET
    base_context_urls: None | ProgramCreateBaseContextUrlsType0 | Unset = UNSET
    trigger_config: CronTrigger | ManualTrigger | None | Unset | WebhookTrigger = UNSET
    per_run_budget_usd: float | None | Unset = UNSET
    monthly_budget_usd: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.cron_trigger import CronTrigger
        from ..models.manual_trigger import ManualTrigger
        from ..models.program_create_base_constraints_type_0 import ProgramCreateBaseConstraintsType0
        from ..models.program_create_base_context_files_type_0 import ProgramCreateBaseContextFilesType0
        from ..models.program_create_base_context_urls_type_0 import ProgramCreateBaseContextUrlsType0
        from ..models.webhook_trigger import WebhookTrigger

        name = self.name

        description = self.description

        mission_type: None | str | Unset
        if isinstance(self.mission_type, Unset):
            mission_type = UNSET
        else:
            mission_type = self.mission_type

        base_constraints: dict[str, Any] | None | Unset
        if isinstance(self.base_constraints, Unset):
            base_constraints = UNSET
        elif isinstance(self.base_constraints, ProgramCreateBaseConstraintsType0):
            base_constraints = self.base_constraints.to_dict()
        else:
            base_constraints = self.base_constraints

        base_context_files: dict[str, Any] | None | Unset
        if isinstance(self.base_context_files, Unset):
            base_context_files = UNSET
        elif isinstance(self.base_context_files, ProgramCreateBaseContextFilesType0):
            base_context_files = self.base_context_files.to_dict()
        else:
            base_context_files = self.base_context_files

        base_context_urls: dict[str, Any] | None | Unset
        if isinstance(self.base_context_urls, Unset):
            base_context_urls = UNSET
        elif isinstance(self.base_context_urls, ProgramCreateBaseContextUrlsType0):
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

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
            }
        )
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

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cron_trigger import CronTrigger
        from ..models.manual_trigger import ManualTrigger
        from ..models.program_create_base_constraints_type_0 import ProgramCreateBaseConstraintsType0
        from ..models.program_create_base_context_files_type_0 import ProgramCreateBaseContextFilesType0
        from ..models.program_create_base_context_urls_type_0 import ProgramCreateBaseContextUrlsType0
        from ..models.webhook_trigger import WebhookTrigger

        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description", UNSET)

        def _parse_mission_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mission_type = _parse_mission_type(d.pop("mission_type", UNSET))

        def _parse_base_constraints(data: object) -> None | ProgramCreateBaseConstraintsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_constraints_type_0 = ProgramCreateBaseConstraintsType0.from_dict(data)

                return base_constraints_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramCreateBaseConstraintsType0 | Unset, data)

        base_constraints = _parse_base_constraints(d.pop("base_constraints", UNSET))

        def _parse_base_context_files(data: object) -> None | ProgramCreateBaseContextFilesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_context_files_type_0 = ProgramCreateBaseContextFilesType0.from_dict(data)

                return base_context_files_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramCreateBaseContextFilesType0 | Unset, data)

        base_context_files = _parse_base_context_files(d.pop("base_context_files", UNSET))

        def _parse_base_context_urls(data: object) -> None | ProgramCreateBaseContextUrlsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                base_context_urls_type_0 = ProgramCreateBaseContextUrlsType0.from_dict(data)

                return base_context_urls_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ProgramCreateBaseContextUrlsType0 | Unset, data)

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

        program_create = cls(
            name=name,
            description=description,
            mission_type=mission_type,
            base_constraints=base_constraints,
            base_context_files=base_context_files,
            base_context_urls=base_context_urls,
            trigger_config=trigger_config,
            per_run_budget_usd=per_run_budget_usd,
            monthly_budget_usd=monthly_budget_usd,
        )

        return program_create
