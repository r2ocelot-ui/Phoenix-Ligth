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
from app.schemas.project import ProjectAssignUser, ProjectCreate, ProjectRead
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
    if not tenancy.is_global(actor):
        if actor.project_id is None:
            return []
        return q.filter(Project.id == actor.project_id).all()
    return q.all()


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
    # Refuse if anyone is still pinned to it (cabinets or users).
    from app.models.cabinet import Cabinet
    in_use_u = db.query(User).filter(User.project_id == project_id).count()
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
    """Owner moves a user into a project (or out, with project_id=None)."""
    _require_owner(actor)
    user = db.get(User, body.user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if body.project_id is not None and not db.get(Project, body.project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    old = user.project_id
    user.project_id = body.project_id
    db.commit()
    audit_log.record(db, username=actor.username, action="project.assign_user",
                     target=user.username, detail={"from": old, "to": body.project_id})
    return {"ok": True, "user_id": user.id, "project_id": user.project_id}


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
