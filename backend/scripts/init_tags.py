#!/usr/bin/env python
"""
初始化脚本：将常用标签导入到数据库中
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.tag import Tag

# 常用标签数据
TAGS = [
    {"name": "热门", "slug": "hot", "description": "热门新闻"},
    {"name": "科技", "slug": "tech", "description": "科技相关新闻"},
    {"name": "财经", "slug": "finance", "description": "财经相关新闻"},
    {"name": "政治", "slug": "politics", "description": "政治相关新闻"},
    {"name": "社会", "slug": "society", "description": "社会相关新闻"},
    {"name": "国际", "slug": "international", "description": "国际相关新闻"},
    {"name": "娱乐", "slug": "entertainment", "description": "娱乐相关新闻"},
    {"name": "体育", "slug": "sports", "description": "体育相关新闻"},
    {"name": "健康", "slug": "health", "description": "健康相关新闻"},
    {"name": "教育", "slug": "education", "description": "教育相关新闻"},
    {"name": "旅游", "slug": "travel", "description": "旅游相关新闻"},
    {"name": "美食", "slug": "food", "description": "美食相关新闻"},
    {"name": "汽车", "slug": "auto", "description": "汽车相关新闻"},
    {"name": "房产", "slug": "realestate", "description": "房产相关新闻"},
    {"name": "时尚", "slug": "fashion", "description": "时尚相关新闻"},
    {"name": "AI", "slug": "ai", "description": "人工智能相关新闻"},
    {"name": "区块链", "slug": "blockchain", "description": "区块链相关新闻"},
    {"name": "元宇宙", "slug": "metaverse", "description": "元宇宙相关新闻"},
    {"name": "Web3", "slug": "web3", "description": "Web3相关新闻"},
    {"name": "创业", "slug": "startup", "description": "创业相关新闻"},
    {"name": "知识", "slug": "knowledge", "description": "知识和学习相关内容"},
    {"name": "Linux", "slug": "linux", "description": "Linux相关新闻和讨论"},
    {"name": "应用", "slug": "app", "description": "移动应用和软件相关内容"},
    {"name": "BBC", "slug": "bbc", "description": "BBC新闻内容"},
    {"name": "彭博社", "slug": "bloomberg", "description": "彭博社财经新闻"},
    {"name": "市场", "slug": "market", "description": "市场分析和行情"}
]

def init_tags():
    """初始化数据库中的标签数据"""
    db = SessionLocal()
    try:
        # 创建标签
        for tag_data in TAGS:
            # 检查标签是否已存在
            db_tag = db.query(Tag).filter(Tag.slug == tag_data["slug"]).first()
            if not db_tag:
                db_tag = Tag(
                    name=tag_data["name"],
                    slug=tag_data["slug"],
                    description=tag_data["description"]
                )
                db.add(db_tag)
                print(f"添加标签: {tag_data['name']} ({tag_data['slug']})")
            else:
                print(f"标签已存在: {tag_data['name']} ({tag_data['slug']})")
        
        db.commit()
        print("标签初始化完成！")
    except Exception as e:
        db.rollback()
        print(f"初始化失败: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    init_tags() 