"""Notes-template storage: list/create/get/update/delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..auth import get_current_user
from ..db import get_session
from ..models import Template
from .schemas import TemplateBody

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _get_owned(session: Session, template_id: int, user: str) -> Template:
    tpl = session.get(Template, template_id)
    if tpl is None or tpl.user_id != user:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.get("", response_model=list[Template])
def list_templates(
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> list[Template]:
    stmt = select(Template).where(Template.user_id == user).order_by(col(Template.name))
    return list(session.exec(stmt).all())


@router.post("", response_model=Template, status_code=201)
def create_template(
    body: TemplateBody,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Template:
    tpl = Template(
        user_id=user, name=body.name, content=body.content, is_default=body.is_default
    )
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return tpl


@router.get("/{template_id}", response_model=Template)
def get_template(
    template_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Template:
    return _get_owned(session, template_id, user)


@router.put("/{template_id}", response_model=Template)
def update_template(
    template_id: int,
    body: TemplateBody,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Template:
    tpl = _get_owned(session, template_id, user)
    tpl.name = body.name
    tpl.content = body.content
    tpl.is_default = body.is_default
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> None:
    tpl = _get_owned(session, template_id, user)
    session.delete(tpl)
    session.commit()
