from enum import Enum


class ReindexQdrantApiAdminReindexPostSource2(str, Enum):
    DB = "db"
    REGISTRY = "registry"

    def __str__(self) -> str:
        return str(self.value)
