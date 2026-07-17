from enum import Enum


class ListPoisonScansApiGovernancePoisonScansGetSource5(str, Enum):
    ALL = "all"
    LIVE = "live"
    RETRO = "retro"

    def __str__(self) -> str:
        return str(self.value)
