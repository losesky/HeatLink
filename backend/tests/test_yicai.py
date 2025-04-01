#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本：测试第一财经新闻适配器
测试包括：
1. 使用NewsSourceFactory创建第一财经适配器
2. 获取新闻数据
3. 将获取的数据保存到数据库
4. 验证数据是否正确保存
"""

import sys
import os
import asyncio
import logging
import datetime
from pathlib import Path

# 添加项目根目录到Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from worker.sources.factory import NewsSourceFactory
from app.db.session import SessionLocal
from app.crud.news import get_news_by_original_id, create_news
from app.crud.source import get_source, create_source
from app.schemas.news import NewsCreate
from sqlalchemy import text
from app.schemas.source import SourceCreate
from app.models.source import SourceType, SourceStatus

# 导入模型以确保能够创建表
from app.models.source import Source
from app.models.news import News
from app.models.category import Category
from app.models.tag import Tag

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_yicai")

# 测试配置
TEST_SOURCE_ID = "yicai"
TEST_SOURCE_NAME = "第一财经"
MAX_DISPLAY_ITEMS = 5  # 最多显示的新闻条数

async def test_yicai():
    """测试第一财经新闻源适配器"""
    logger.info("开始测试 YiCaiNewsSource 适配器")
    
    # 创建源实例
    source = NewsSourceFactory.create_source(TEST_SOURCE_ID)
    if not source:
        logger.error(f"创建源失败: {TEST_SOURCE_ID}")
        return
        
    logger.info(f"创建源: {source.source_id} (类型: {source.__class__.__name__})")
    
    # 连接数据库
    db = SessionLocal()
    
    try:
        # 检查数据库连接
        db.execute(text("SELECT 1"))
        logger.info("数据库连接成功")
        
        # 检查源是否在数据库中存在
        db_source = get_source(db, TEST_SOURCE_ID)
        if not db_source:
            logger.warning(f"数据库中不存在源 {TEST_SOURCE_ID}，将创建...")
            try:
                # 创建源数据
                source_data = SourceCreate(
                    id=TEST_SOURCE_ID,
                    name=TEST_SOURCE_NAME,
                    description="第一财经新闻源 - 测试创建",
                    url="https://www.yicai.com/",
                    type=SourceType.WEB,
                    status=SourceStatus.ACTIVE,
                    country="CN",
                    language="zh-CN",
                    update_interval=1800,  # 30分钟
                    cache_ttl=900,  # 15分钟
                    config={
                        "use_selenium": True,
                        "headless": True
                    }
                )
                
                # 保存到数据库并提交事务
                db_source = create_source(db, source_data)
                db.commit()
                logger.info(f"成功创建源: {db_source.id} - {db_source.name}")
            except Exception as e:
                logger.error(f"创建源失败: {str(e)}")
                db.rollback()
                logger.error("无法继续测试，因为保存新闻需要有效的源记录")
                return
        else:
            logger.info(f"数据库中找到源: {db_source.id} - {db_source.name}")
        
        # 获取新闻数据
        logger.info("开始获取新闻数据...")
        news_items = await source.fetch()
        
        # 打印结果
        if not news_items:
            logger.warning("没有获取到新闻数据")
            return
            
        logger.info(f"成功获取 {len(news_items)} 条新闻")
        
        # 打印前几条新闻
        for i, item in enumerate(news_items[:MAX_DISPLAY_ITEMS]):
            logger.info(f"新闻 {i+1}: {item.title}")
            logger.info(f"  链接: {item.url}")
            logger.info(f"  发布时间: {item.published_at}")
            logger.info(f"  类型: {item.extra.get('type', 'unknown')}")
            logger.info("")
        
        # 保存到数据库
        logger.info("开始保存新闻到数据库...")
        saved_count = 0
        error_count = 0
        
        for item in news_items:
            try:
                # 检查新闻是否已存在
                existing_news = get_news_by_original_id(db, item.source_id, item.id)
                
                if not existing_news:
                    # 创建新闻
                    news_data = NewsCreate(
                        title=item.title,
                        content=item.content,
                        summary=item.summary,
                        url=item.url,
                        image_url=item.image_url,
                        published_at=item.published_at,
                        source_id=item.source_id,
                        original_id=item.id,
                        category_id=None,  # 可以根据需要设置
                        extra=item.extra
                    )
                    create_news(db, news_data)
                    db.commit()  # 确保每条记录都提交到数据库
                    saved_count += 1
                else:
                    logger.debug(f"新闻已存在，跳过: {item.title}")
            except Exception as e:
                error_count += 1
                logger.error(f"保存新闻失败: {str(e)}")
                # 如果出现异常，进行回滚以避免事务被挂起
                db.rollback()
                
                # 超过5个错误，停止尝试保存
                if error_count >= 5:
                    logger.error("错误过多，停止保存")
                    break
                
                continue
        
        logger.info(f"成功保存 {saved_count} 条新闻到数据库，失败 {error_count} 条")
        
        # 验证数据
        if saved_count > 0:
            logger.info("验证已保存的数据...")
            
            # 随机选择几条新闻进行验证
            verify_items = news_items[:MAX_DISPLAY_ITEMS]
            
            verified_count = 0
            for item in verify_items:
                db_news = get_news_by_original_id(db, item.source_id, item.id)
                if db_news:
                    logger.info(f"验证通过: {db_news.title}")
                    verified_count += 1
                else:
                    logger.warning(f"验证失败: {item.title} 未找到在数据库中")
            
            logger.info(f"验证结果: {verified_count}/{len(verify_items)} 条记录验证通过")
        
        logger.info("测试完成！")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
    finally:
        # 关闭数据库连接
        db.close()
        
        # 确保关闭资源
        await source.close()

if __name__ == "__main__":
    asyncio.run(test_yicai()) 