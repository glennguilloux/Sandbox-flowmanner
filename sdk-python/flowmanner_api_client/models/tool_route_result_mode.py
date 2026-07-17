from enum import Enum


class ToolRouteResultMode(str, Enum):
    FALLBACK_FULL_REGISTRY = "fallback-full-registry"
    SPARSE = "sparse"

    def __str__(self) -> str:
        return str(self.value)
