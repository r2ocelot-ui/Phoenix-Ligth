from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class AlarmType(str, Enum):
    LAMP_OUT = "LAMP_OUT"
    LINE_FAILURE = "LINE_FAILURE"
    OVERVOLTAGE = "OVERVOLTAGE"
    UNDERVOLTAGE = "UNDERVOLTAGE"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"


class AlarmSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alarm(BaseModel):
    cabinet_id: str
    type: AlarmType
    severity: AlarmSeverity
    message: str
    timestamp: datetime
    value: float | None = None
