"""Estado de la licencia (sin secretos): válida/motivo, huella del equipo y
cliente. Lo consume el panel para avisar si falta licencia o caducó."""
from fastapi import APIRouter, Depends

from app.models.user import User
from app.services import licensing
from app.services.auth import get_current_user

router = APIRouter(prefix="/license", tags=["license"])


@router.get("")
def license_status(_: User = Depends(get_current_user)) -> dict:
    return licensing.license_status()
