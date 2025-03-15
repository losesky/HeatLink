from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.tag import Tag
from app.schemas.tag import TagCreate, TagUpdate


def get_tag(db: Session, tag_id: int) -> Optional[Tag]:
    return db.query(Tag).filter(Tag.id == tag_id).first()


def get_tag_by_slug(db: Session, slug: str) -> Optional[Tag]:
    return db.query(Tag).filter(Tag.slug == slug).first()


def get_tag_by_name(db: Session, name: str) -> Optional[Tag]:
    return db.query(Tag).filter(Tag.name == name).first()


def get_tags(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None
) -> List[Tag]:
    query = db.query(Tag)
    
    if search:
        query = query.filter(Tag.name.ilike(f"%{search}%"))
    
    return query.order_by(Tag.name).offset(skip).limit(limit).all()


def create_tag(db: Session, tag: TagCreate) -> Tag:
    db_tag = Tag(**tag.model_dump())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag


def update_tag(db: Session, tag_id: int, tag: TagUpdate) -> Optional[Tag]:
    db_tag = get_tag(db, tag_id)
    if not db_tag:
        return None
    
    update_data = tag.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_tag, key, value)
    
    db.commit()
    db.refresh(db_tag)
    return db_tag


def delete_tag(db: Session, tag_id: int) -> bool:
    db_tag = get_tag(db, tag_id)
    if not db_tag:
        return False
    
    db.delete(db_tag)
    db.commit()
    return True


def get_or_create_tag(db: Session, name: str, slug: Optional[str] = None) -> Tag:
    """
    Get a tag by name or create it if it doesn't exist
    """
    db_tag = get_tag_by_name(db, name)
    if db_tag:
        return db_tag
    
    # Create a slug if not provided
    if not slug:
        import re
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[\s_-]+', '-', slug)
        slug = re.sub(r'^-+|-+$', '', slug)
    
    # Create the tag
    tag_data = TagCreate(name=name, slug=slug)
    return create_tag(db, tag_data) 