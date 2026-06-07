from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class AlarmType(str, Enum):
    # Eléctricas
    LAMP_OUT = "LAMP_OUT"
    LINE_FAILURE = "LINE_FAILURE"
    OVERVOLTAGE = "OVERVOLTAGE"
    UNDERVOLTAGE = "UNDERVOLTAGE"
    OVERCURRENT = "OVERCURRENT"
    # Detección por desviación de consumo (DECISIONS §6.6)
    CIRCUIT_LOAD_DROP = "CIRCUIT_LOAD_DROP"      # consumo muy bajo respecto al esperado
    CIRCUIT_OVERLOAD = "CIRCUIT_OVERLOAD"        # consumo muy alto: fuga, derivación
    CONTACTOR_STUCK = "CONTACTOR_STUCK"          # ordenado OFF pero sigue consumiendo
    # Infraestructura del cuadro
    DOOR_OPEN = "DOOR_OPEN"
    CABINET_OVERTEMP = "CABINET_OVERTEMP"
    INTRUSION = "INTRUSION"
    # Comunicaciones
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
