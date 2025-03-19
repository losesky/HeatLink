from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import datetime

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def get_category(db: Session, category_id: int) -> Optional[Category]:
    category = db.query(Category).filter(Category.id == category_id).first()
    if category and category.order is None:
        category.order = 0
    return category


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    category = db.query(Category).filter(Category.slug == slug).first()
    if category and category.order is None:
        category.order = 0
    return category


def get_categories(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    parent_id: Optional[int] = None
) -> List[Category]:
    query = db.query(Category)
    
    if parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    
    categories = query.order_by(Category.order).offset(skip).limit(limit).all()
    
    # 确保所有记录的 order 字段都有值
    for category in categories:
        if category.order is None:
            category.order = 0
    
    return categories


def get_root_categories(db: Session) -> List[Category]:
    categories = db.query(Category).filter(Category.parent_id == None).order_by(Category.order).all()
    
    # 确保所有记录的 order 字段都有值
    for category in categories:
        if category.order is None:
            category.order = 0
    
    return categories


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
    category_dict = {}
    for category in categories:
        # 确保 order 有有效值
        order = 0 if category.order is None else category.order
        
        # 确保日期时间信息正确格式化为 ISO 字符串
        created_at = category.created_at.isoformat() if category.created_at else datetime.datetime.utcnow().isoformat()
        updated_at = category.updated_at.isoformat() if category.updated_at else datetime.datetime.utcnow().isoformat()
        
        category_dict[category.id] = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "slug": category.slug,
            "parent_id": category.parent_id,
            "icon": category.icon,
            "order": order,
            "created_at": created_at,
            "updated_at": updated_at,
            "children": []
        }
    
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