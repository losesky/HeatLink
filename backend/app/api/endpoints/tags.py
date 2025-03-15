from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser
from app.crud.tag import (
    get_tag, get_tag_by_slug, get_tag_by_name, get_tags,
    create_tag, update_tag, delete_tag, get_or_create_tag
)
from app.schemas.tag import Tag, TagCreate, TagUpdate

router = APIRouter()


@router.get("/", response_model=List[Tag])
def read_tags(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
) -> Any:
    """
    Retrieve tags.
    """
    tags = get_tags(
        db,
        skip=skip,
        limit=limit,
        search=search
    )
    return tags


@router.post("/", response_model=Tag)
def create_new_tag(
    *,
    db: Session = Depends(get_db),
    tag_in: TagCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create new tag.
    """
    # Check if name already exists
    existing_by_name = get_tag_by_name(db, name=tag_in.name)
    if existing_by_name:
        raise HTTPException(
            status_code=400,
            detail=f"Tag with name '{tag_in.name}' already exists",
        )
    
    # Check if slug already exists
    existing_by_slug = get_tag_by_slug(db, slug=tag_in.slug)
    if existing_by_slug:
        raise HTTPException(
            status_code=400,
            detail=f"Tag with slug '{tag_in.slug}' already exists",
        )
    
    tag = create_tag(db, tag_in)
    return tag


@router.post("/get-or-create", response_model=Tag)
def get_or_create_tag_api(
    *,
    db: Session = Depends(get_db),
    name: str = Query(..., description="Tag name"),
    slug: Optional[str] = Query(None, description="Tag slug (optional)"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Get a tag by name or create it if it doesn't exist.
    """
    tag = get_or_create_tag(db, name=name, slug=slug)
    return tag


@router.get("/{tag_id}", response_model=Tag)
def read_tag(
    *,
    db: Session = Depends(get_db),
    tag_id: int = Path(..., description="The ID of the tag to get"),
) -> Any:
    """
    Get tag by ID.
    """
    tag = get_tag(db, tag_id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )
    return tag


@router.get("/slug/{slug}", response_model=Tag)
def read_tag_by_slug(
    *,
    db: Session = Depends(get_db),
    slug: str = Path(..., description="The slug of the tag to get"),
) -> Any:
    """
    Get tag by slug.
    """
    tag = get_tag_by_slug(db, slug=slug)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )
    return tag


@router.get("/name/{name}", response_model=Tag)
def read_tag_by_name(
    *,
    db: Session = Depends(get_db),
    name: str = Path(..., description="The name of the tag to get"),
) -> Any:
    """
    Get tag by name.
    """
    tag = get_tag_by_name(db, name=name)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )
    return tag


@router.put("/{tag_id}", response_model=Tag)
def update_tag_api(
    *,
    db: Session = Depends(get_db),
    tag_id: int = Path(..., description="The ID of the tag to update"),
    tag_in: TagUpdate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Update a tag.
    """
    tag = get_tag(db, tag_id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )
    
    # Check if name already exists if changing
    if tag_in.name and tag_in.name != tag.name:
        existing = get_tag_by_name(db, name=tag_in.name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tag with name '{tag_in.name}' already exists",
            )
    
    # Check if slug already exists if changing
    if tag_in.slug and tag_in.slug != tag.slug:
        existing = get_tag_by_slug(db, slug=tag_in.slug)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Tag with slug '{tag_in.slug}' already exists",
            )
    
    tag = update_tag(db, tag_id=tag_id, tag=tag_in)
    return tag


@router.delete("/{tag_id}", response_model=bool)
def delete_tag_api(
    *,
    db: Session = Depends(get_db),
    tag_id: int = Path(..., description="The ID of the tag to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a tag.
    """
    tag = get_tag(db, tag_id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=404,
            detail="Tag not found",
        )
    
    result = delete_tag(db, tag_id=tag_id)
    return result 