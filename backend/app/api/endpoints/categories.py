from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_superuser
from app.crud.category import (
    get_category, get_category_by_slug, get_categories, get_root_categories,
    create_category, update_category, delete_category, get_category_tree
)
from app.schemas.category import (
    Category, CategoryCreate, CategoryUpdate, CategoryWithChildren, CategoryTree
)

router = APIRouter()


@router.get("/", response_model=List[Category])
def read_categories(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    parent_id: Optional[int] = None,
) -> Any:
    """
    Retrieve categories.
    """
    categories = get_categories(
        db,
        skip=skip,
        limit=limit,
        parent_id=parent_id
    )
    return categories


@router.get("/root", response_model=List[Category])
def read_root_categories(
    db: Session = Depends(get_db),
) -> Any:
    """
    Retrieve root categories.
    """
    categories = get_root_categories(db)
    return categories


@router.get("/tree", response_model=CategoryTree)
def read_category_tree(
    db: Session = Depends(get_db),
) -> Any:
    """
    Retrieve category tree.
    """
    categories = get_category_tree(db)
    return {"categories": categories}


@router.post("/", response_model=Category)
def create_new_category(
    *,
    db: Session = Depends(get_db),
    category_in: CategoryCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create new category.
    """
    # Check if slug already exists
    existing = get_category_by_slug(db, slug=category_in.slug)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Category with slug '{category_in.slug}' already exists",
        )
    
    # Check if parent exists if specified
    if category_in.parent_id:
        parent = get_category(db, category_id=category_in.parent_id)
        if not parent:
            raise HTTPException(
                status_code=404,
                detail="Parent category not found",
            )
    
    category = create_category(db, category_in)
    return category


@router.get("/{category_id}", response_model=Category)
def read_category(
    *,
    db: Session = Depends(get_db),
    category_id: int = Path(..., description="The ID of the category to get"),
) -> Any:
    """
    Get category by ID.
    """
    category = get_category(db, category_id=category_id)
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )
    return category


@router.get("/slug/{slug}", response_model=Category)
def read_category_by_slug(
    *,
    db: Session = Depends(get_db),
    slug: str = Path(..., description="The slug of the category to get"),
) -> Any:
    """
    Get category by slug.
    """
    category = get_category_by_slug(db, slug=slug)
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )
    return category


@router.put("/{category_id}", response_model=Category)
def update_category_api(
    *,
    db: Session = Depends(get_db),
    category_id: int = Path(..., description="The ID of the category to update"),
    category_in: CategoryUpdate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Update a category.
    """
    category = get_category(db, category_id=category_id)
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )
    
    # Check if slug already exists if changing
    if category_in.slug and category_in.slug != category.slug:
        existing = get_category_by_slug(db, slug=category_in.slug)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Category with slug '{category_in.slug}' already exists",
            )
    
    # Check if parent exists if changing
    if category_in.parent_id and category_in.parent_id != category.parent_id:
        parent = get_category(db, category_id=category_in.parent_id)
        if not parent:
            raise HTTPException(
                status_code=404,
                detail="Parent category not found",
            )
        # Prevent circular references
        if category_in.parent_id == category_id:
            raise HTTPException(
                status_code=400,
                detail="Category cannot be its own parent",
            )
    
    category = update_category(db, category_id=category_id, category=category_in)
    return category


@router.delete("/{category_id}", response_model=bool)
def delete_category_api(
    *,
    db: Session = Depends(get_db),
    category_id: int = Path(..., description="The ID of the category to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a category.
    """
    category = get_category(db, category_id=category_id)
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )
    
    result = delete_category(db, category_id=category_id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with child categories",
        )
    
    return result 