#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工作模块的数据模型
包含新闻条目、新闻源等数据模型
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field

@dataclass
class NewsItemModel:
    """新闻条目模型"""
    
    title: str
    url: str
    source_id: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def dict(self) -> Dict[str, Any]:
        """将对象转换为字典"""
        result = {
            "title": self.title,
            "url": self.url,
            "source_id": self.source_id
        }
        
        # 添加可选字段
        if self.published_at:
            result["published_at"] = self.published_at.isoformat()
        if self.author:
            result["author"] = self.author
        if self.summary:
            result["summary"] = self.summary
        if self.content:
            result["content"] = self.content
        if self.image_url:
            result["image_url"] = self.image_url
        if self.categories:
            result["categories"] = self.categories
        if self.tags:
            result["tags"] = self.tags
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NewsItemModel':
        """从字典创建对象"""
        # 处理日期字段
        published_at = data.get("published_at")
        if published_at and isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except ValueError:
                published_at = None
        
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            source_id=data.get("source_id", ""),
            published_at=published_at,
            author=data.get("author"),
            summary=data.get("summary"),
            content=data.get("content"),
            image_url=data.get("image_url"),
            categories=data.get("categories", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {})
        ) 