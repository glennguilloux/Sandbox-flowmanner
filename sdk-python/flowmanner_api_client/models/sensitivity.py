from enum import Enum


class Sensitivity(str, Enum):
    NORMAL = "normal"
    RESTRICTED = "restricted"
    SENSITIVE = "sensitive"

    def __str__(self) -> str:
        return str(self.value)
