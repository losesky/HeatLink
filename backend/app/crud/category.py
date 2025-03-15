from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def get_category(db: Session, category_id: int) -> Optional[Category]:
    return db.query(Category).filter(Category.id == category_id).first()


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    return db.query(Category).filter(Category.slug == slug).first()


def get_categories(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    parent_id: Optional[int] = None
) -> List[Category]:
    query = db.query(Category)
    
    if parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    
    return query.order_by(Category.order).offset(skip).limit(limit).all()


def get_root_categories(db: Session) -> List[Category]:
    return db.query(Category).filter(Category.parent_id == None).order_by(Category.order).all()


def create_category(db: Session, category: CategoryCreate) -> Category:
    db_category = Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(db: Session, category_id: int, category: CategoryUpdate) -> Optional[Category]:
    db_category = get_category(db, category_id)
    if not db_category:
        return None
    
    update_data = category.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_category, key, value)
    
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int) -> bool:
    db_category = get_category(db, category_id)
    if not db_category:
        return False
    
    # Check if there are any child categories
    children = db.query(Category).filter(Category.parent_id == category_id).count()
    if children > 0:
        return False
    
    db.delete(db_category)
    db.commit()
    return True


def get_category_tree(db: Session) -> List[Dict[str, Any]]:
    """
    Get a hierarchical tree of categories
    """
    # Get all categories
    categories = db.query(Category).all()
    
    # Create a dictionary to store the tree
    category_dict = {category.id: {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "slug": category.slug,
        "icon": category.icon,
        "order": category.order,
        "children": []
    } for category in categories}
    
    # Build the tree
    root_categories = []
    for category in categories:
        if category.parent_id is None:
            root_categories.append(category_dict[category.id])
        else:
            if category.parent_id in category_dict:
                category_dict[category.parent_id]["children"].append(category_dict[category.id])
    
    # Sort by order
    for category in category_dict.values():
        category["children"].sort(key=lambda x: x["order"])
    
    root_categories.sort(key=lambda x: x["order"])
    
    return root_categories 