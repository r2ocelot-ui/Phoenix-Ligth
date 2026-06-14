"""Project / city endpoints.

- Owner sees & creates everything.
- Anyone else sees only the project they are assigned to (so an admin de
  proyecto navigates to /projects and sees a list of one).
- Assignment of users to a project is owner-only.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.core.config import settings
from app.schemas.project import (
    ProjectAssignUser, ProjectCreate, ProjectRead, ProjectTariffUpdate,
)
from app.services import audit_log, ranks, tenancy
from app.services.auth import get_current_user, require_permission

router = APIRouter(prefix="/projects", tags=["projects"])


def _require_owner(actor: User) -> None:
    if not tenancy.is_global(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el owner puede gestionar proyectos")


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    q = db.query(Project).order_by(Project.id)
    if tenancy.is_global(actor):
        return q.all()
    # Multi-proyecto: devuelve TODOS los proyectos asignados al usuario.
    ids = tenancy.scoped_project_ids(actor) or set()
    if not ids:
        return []
    return q.filter(Project.id.in_(ids)).all()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    _require_owner(actor)
    if db.query(Project).filter(Project.code == body.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un proyecto con ese código")
    project = Project(code=body.code, name=body.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    audit_log.record(db, username=actor.username, action="project.create",
                     target=project.code, detail={"name": project.name})
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    _require_owner(actor)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    # Refuse if anyone is still pinned to it (cabinets or users). Para usuarios
    # se mira tanto el principal como la lista multi-proyecto (JSON → en Python).
    from app.models.cabinet import Cabinet
    in_use_u = sum(
        1 for u in db.query(User).all()
        if u.project_id == project_id or project_id in (u.project_ids or [])
    )
    in_use_c = db.query(Cabinet).filter(Cabinet.project_id == project_id).count()
    if in_use_u or in_use_c:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede borrar: {in_use_u} usuarios y {in_use_c} cuadros aún lo referencian.",
        )
    db.delete(project)
    db.commit()
    audit_log.record(db, username=actor.username, action="project.delete",
                     target=project.code)
    return {"ok": True}


@router.post("/assign-user")
def assign_user(
    body: ProjectAssignUser,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    """Owner asigna a un usuario su conjunto de proyectos (multi-proyecto).
    ``project_ids`` reemplaza la lista; lista vacía = global (sin proyecto)."""
    _require_owner(actor)
    user = db.get(User, body.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    # Resolver el conjunto: prioriza la lista; si no, el id único (legacy).
    if body.project_ids is not None:
        ids = list(dict.fromkeys(body.project_ids))  # dedup, conserva orden
    elif body.project_id is not None:
        ids = [body.project_id]
    else:
        ids = []
    for pid in ids:
        if not db.get(Project, pid):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Proyecto {pid} no encontrado")
    old = list(user.project_ids or [])
    user.project_ids = ids
    user.project_id = ids[0] if ids else None  # "principal" = el primero
    db.commit()
    audit_log.record(db, username=actor.username, action="project.assign_user",
                     target=user.username, detail={"from": old, "to": ids})
    return {"ok": True, "user_id": user.id, "project_ids": user.project_ids,
            "project_id": user.project_id}


@router.get("/{project_id}/tariff")
def get_project_tariff(
    project_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Topes de tarifa del proyecto + los efectivos (sustituyendo NULL por el
    global). La UI puede pintar el valor actual y marcar "personalizado" cuando
    el campo del proyecto no es NULL."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    # Director/operador solo ve los proyectos a los que pertenece.
    if not tenancy.is_global(actor):
        scoped = tenancy.scoped_project_ids(actor) or set()
        if project_id not in scoped:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Proyecto fuera de tu ámbito")
    return {
        "project_id": project.id,
        "project": {
            "tariff_cap_punta": project.tariff_cap_punta,
            "tariff_cap_llano": project.tariff_cap_llano,
            "tariff_cap_valle": project.tariff_cap_valle,
            "tariff_floor_level": project.tariff_floor_level,
        },
        "effective": {
            "tariff_cap_punta": project.tariff_cap_punta if project.tariff_cap_punta is not None else settings.tariff_cap_punta,
            "tariff_cap_llano": project.tariff_cap_llano if project.tariff_cap_llano is not None else settings.tariff_cap_llano,
            "tariff_cap_valle": project.tariff_cap_valle if project.tariff_cap_valle is not None else settings.tariff_cap_valle,
            "tariff_floor_level": project.tariff_floor_level if project.tariff_floor_level is not None else settings.tariff_floor_level,
        },
        "defaults": {
            "tariff_cap_punta": settings.tariff_cap_punta,
            "tariff_cap_llano": settings.tariff_cap_llano,
            "tariff_cap_valle": settings.tariff_cap_valle,
            "tariff_floor_level": settings.tariff_floor_level,
        },
    }


@router.put("/{project_id}/tariff")
def set_project_tariff(
    project_id: int,
    body: ProjectTariffUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
) -> dict:
    """Actualiza los topes de tarifa del proyecto. Solo owner: los topes
    afectan al gasto del cliente y al confort, decisión de cabeza de proyecto."""
    _require_owner(actor)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    data = body.model_dump(exclude_unset=True)
    old = {k: getattr(project, k) for k in data}
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    audit_log.record(db, username=actor.username, action="project.tariff_update",
                     target=project.code, detail={"from": old, "to": data})
    return {"ok": True, "project_id": project.id, **data}


@router.post("/{project_id}/assign-cabinet/{cabinet_code}")
def assign_cabinet(
    project_id: int, cabinet_code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(ranks.P_USER_MANAGE)),
):
    _require_owner(actor)
    from app.models.cabinet import Cabinet
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    cab = db.query(Cabinet).filter(Cabinet.code == cabinet_code).first()
    if not cab:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuadro no encontrado")
    old = cab.project_id
    cab.project_id = project_id
    db.commit()
    audit_log.record(db, username=actor.username, action="project.assign_cabinet",
                     target=cabinet_code, detail={"from": old, "to": project_id})
    return {"ok": True}
