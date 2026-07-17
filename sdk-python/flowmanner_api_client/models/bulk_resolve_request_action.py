from enum import Enum


class BulkResolveRequestAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"

    def __str__(self) -> str:
        return str(self.value)
