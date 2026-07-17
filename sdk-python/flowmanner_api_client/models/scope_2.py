from enum import Enum


class Scope2(str, Enum):
    PERSONAL = "personal"
    PRIVATE = "private"
    PROGRAM = "program"
    WORKSPACE = "workspace"

    def __str__(self) -> str:
        return str(self.value)
