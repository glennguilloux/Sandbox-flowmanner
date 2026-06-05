from pydantic import BaseModel


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class TopFailedMission(BaseModel):
    mission_name: str
    failure_count: int

    model_config = {
        "alias_generator": lambda x: to_camel(x),
        "populate_by_name": True,
    }


class DashboardAnalyticsResponse(BaseModel):
    seven_day_success_rate: float
    avg_runtime_seconds: float
    current_queue_depth: int
    top_failed_missions: list[TopFailedMission]

    model_config = {
        "alias_generator": lambda x: to_camel(x),
        "populate_by_name": True,
    }


class ErrorCodeCount(BaseModel):
    code: str
    count: int

    model_config = {
        "alias_generator": lambda x: to_camel(x),
        "populate_by_name": True,
    }


class ManualInterventionMission(BaseModel):
    missionId: str
    errorCode: str
    lastUpdateTimestamp: str

    model_config = {
        "alias_generator": lambda x: to_camel(x),
        "populate_by_name": True,
    }


class FirefightingMetricsResponse(BaseModel):
    failedMissionCount: int
    avgRetryCount: float
    topErrorCodes: list[ErrorCodeCount]
    manualInterventionMissions: list[ManualInterventionMission]

    model_config = {
        "alias_generator": lambda x: to_camel(x),
        "populate_by_name": True,
    }
