from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.category import Category, EntityType
from app.modules.categories.schemas import CategoryCreate, CategoryPatch

_VALID_ENTITY_TYPES = {e.value for e in EntityType}


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"entity_type inválido. Valores aceitos: {sorted(_VALID_ENTITY_TYPES)}",
        )


def list_categories(
    db: Session,
    company_id: UUID,
    entity_type: Optional[str] = None,
) -> List[Category]:
    q = db.query(Category).filter(Category.company_id == company_id)
    if entity_type:
        _validate_entity_type(entity_type)
        q = q.filter(Category.entity_type == entity_type)
    return q.order_by(Category.entity_type, Category.sort_order).all()


def create_category(db: Session, company_id: UUID, data: CategoryCreate) -> Category:
    _validate_entity_type(data.entity_type)

    conflict = (
        db.query(Category)
        .filter(
            Category.company_id == company_id,
            Category.name == data.name,
            Category.entity_type == data.entity_type,
        )
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Categoria '{data.name}' já existe para o tipo '{data.entity_type}'",
        )

    category = Category(
        company_id=company_id,
        name=data.name,
        entity_type=data.entity_type,
        is_default=False,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def get_category_or_404(db: Session, company_id: UUID, category_id: UUID) -> Category:
    category = (
        db.query(Category)
        .filter(
            Category.company_id == company_id,
            Category.category_id == category_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return category


def patch_category(
    db: Session,
    company_id: UUID,
    category_id: UUID,
    data: CategoryPatch,
) -> Category:
    category = get_category_or_404(db, company_id, category_id)

    if category.is_default:
        # Categorias default: apenas is_active é alterável
        forbidden = {k for k in ("name", "entity_type", "sort_order")
                     if getattr(data, k) is not None}
        if forbidden:
            raise HTTPException(
                status_code=422,
                detail="Categorias padrão só podem ter is_active alterado.",
            )

    updates = data.model_dump(exclude_none=True)

    if "entity_type" in updates:
        _validate_entity_type(updates["entity_type"])

    for field, value in updates.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, company_id: UUID, category_id: UUID) -> None:
    category = get_category_or_404(db, company_id, category_id)

    if category.is_default:
        raise HTTPException(
            status_code=422,
            detail="Categorias padrão não podem ser excluídas. Use is_active=false para desativá-las.",
        )

    db.delete(category)
    db.commit()
