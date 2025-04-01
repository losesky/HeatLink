#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存监控工具

监控并分析各个新闻源的缓存行为，生成报告，帮助优化缓存策略
"""

import os
import sys
import asyncio
import logging
import time
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple
import argparse
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from tabulate import tabulate

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cache_monitor")

# 添加项目根目录到PATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 正确的导入
from worker.sources.provider import DefaultNewsSourceProvider
from worker.sources.base import NewsSource
from backend.worker.utils.cache_enhancer import enhance_all_sources, cache_monitor

# 创建缓存监控处理器
class CacheMonitor:
    """缓存行为监控工具"""
    
    def __init__(self, db_path="cache_monitor.db"):
        """初始化监控器"""
        self.db_path = db_path
        self.conn = None
        self.setup_database()
        
    def setup_database(self):
        """设置数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # 创建源配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                cache_ttl INTEGER,
                update_interval INTEGER,
                last_check TIMESTAMP
            )
            ''')
            
            # 创建缓存事件表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                event_type TEXT,
                event_time TIMESTAMP,
                cache_size INTEGER,
                cache_age REAL,
                response_time REAL,
                success INTEGER,
                message TEXT,
                FOREIGN KEY (source_id) REFERENCES sources (source_id)
            )
            ''')
            
            # 创建性能指标表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                timestamp TIMESTAMP,
                force_update INTEGER,
                response_time REAL,
                news_count INTEGER,
                from_cache INTEGER,
                cache_valid INTEGER,
                FOREIGN KEY (source_id) REFERENCES sources (source_id)
            )
            ''')
            
            self.conn.commit()
            logger.info(f"数据库设置完成: {self.db_path}")
        except Exception as e:
            logger.error(f"设置数据库时出错: {str(e)}")
            if self.conn:
                self.conn.close()
            raise
            
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            
    async def register_sources(self):
        """从源提供者注册所有可用源"""
        try:
            provider = DefaultNewsSourceProvider()
            all_sources = provider.get_all_sources()
            
            # 构建与原代码兼容的字典格式
            sources = {}
            for source in all_sources:
                sources[source.source_id] = {
                    'name': getattr(source, 'name', source.source_id),
                    'category': getattr(source, 'category', ''),
                    'country': getattr(source, 'country', ''),
                    'language': getattr(source, 'language', '')
                }
            
            cursor = self.conn.cursor()
            for source_id, info in sources.items():
                # 获取源实例来获取详细配置
                source = provider.get_source(source_id)
                if not source:
                    continue
                    
                source_type = source.__class__.__name__
                cache_ttl = getattr(source, 'cache_ttl', 0)
                update_interval = getattr(source, 'update_interval', 0)
                
                # 插入或更新源信息
                cursor.execute('''
                INSERT OR REPLACE INTO sources 
                (source_id, name, type, cache_ttl, update_interval, last_check) 
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (source_id, info.get('name', ''), source_type, 
                     cache_ttl, update_interval, datetime.datetime.now().isoformat()))
            
            self.conn.commit()
            logger.info(f"已注册 {len(sources)} 个新闻源")
            return sources
        except Exception as e:
            logger.error(f"注册源时出错: {str(e)}")
            return {}
    
    async def test_source_caching(self, source_id: str, test_count: int = 3):
        """测试指定源的缓存行为"""
        logging.info(f"开始测试 {source_id} 源的缓存行为...")
        
        provider = DefaultNewsSourceProvider()
        
        # 获取源并应用缓存增强
        provider_sources = provider.get_all_sources()
        
        # 查找指定的源
        source = None
        if isinstance(provider_sources, dict):
            if source_id not in provider_sources:
                logging.error(f"未找到源 {source_id}")
                return
            source = provider_sources[source_id]
        else:
            # 如果provider_sources是列表，遍历查找匹配的source_id
            source = next((s for s in provider_sources if s.source_id == source_id), None)
            if not source:
                logging.error(f"未找到源 {source_id}")
                return
        
        # 注册到缓存监控器 - 这会自动增强源
        cache_monitor.register_source(source)
        
        logging.info(f"源初始化完成: {source.source_id} - {source.name}")
        logging.info(f"缓存设置: update_interval={source.update_interval}, cache_ttl={source.cache_ttl}")
        
        # 测试场景1: 强制更新 (绕过缓存，测试实际获取性能)
        logging.info("\n=== 场景1: 强制更新 ===")
        forced_times = []
        for i in range(test_count):
            start_time = time.time()
            news = await source.get_news(force_update=True)
            elapsed = time.time() - start_time
            forced_times.append(elapsed)
            
            logging.info(f"强制更新 #{i+1}: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
            if i < test_count - 1:
                await asyncio.sleep(1)  # 短暂暂停防止请求频率过高
        
        avg_forced = sum(forced_times) / len(forced_times)
        logging.info(f"强制更新平均耗时: {avg_forced:.3f}秒")
        
        # 测试场景2: 缓存检索 (不强制更新，使用缓存)
        logging.info("\n=== 场景2: 缓存检索 ===")
        cache_times = []
        for i in range(test_count):
            start_time = time.time()
            news = await source.get_news(force_update=False)
            elapsed = time.time() - start_time
            cache_times.append(elapsed)
            
            logging.info(f"缓存检索 #{i+1}: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
            if i < test_count - 1:
                await asyncio.sleep(0.5)
        
        avg_cache = sum(cache_times) / len(cache_times) if cache_times else 0
        logging.info(f"缓存检索平均耗时: {avg_cache:.3f}秒")
        
        # 测试场景3: 缓存清除后检索 (模拟缓存过期)
        logging.info("\n=== 场景3: 缓存清除 ===")
        await source.clear_cache()
        start_time = time.time()
        news = await source.get_news()
        elapsed = time.time() - start_time
        
        logging.info(f"清除缓存后检索: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
        
        # 汇总当前缓存指标和保护状态
        cache_status = source.cache_status()
        
        # 计算加速比
        acceleration_ratio = avg_forced / max(avg_cache, 0.001)
        
        logging.info("\n=== 测试结果汇总 ===")
        logging.info(f"强制更新平均耗时: {avg_forced:.3f}秒")
        logging.info(f"缓存检索平均耗时: {avg_cache:.3f}秒")
        logging.info(f"缓存加速比: {acceleration_ratio:.2f}x")
        
        # 输出缓存状态和保护指标
        logging.info("\n=== 缓存状态和保护指标 ===")
        logging.info(f"缓存条目数: {cache_status['cache_state']['items_count']}")
        logging.info(f"缓存有效性: {cache_status['cache_state']['valid']}")
        logging.info(f"缓存命中率: {cache_status['metrics']['hit_ratio']:.2%}")
        
        # 保护统计
        protections = cache_status['protection_stats']
        logging.info(f"保护统计: 空结果保护={protections['empty_protection_count']}, " +
                     f"错误保护={protections['error_protection_count']}, " +
                     f"数据减少保护={protections['shrink_protection_count']}")
        
        if protections['total_protection_count'] > 0:
            logging.info("保护机制已激活，缓存保持了数据完整性")
    
    def _record_performance(self, source_id: str, force_update: bool, 
                          response_time: float, news_count: int,
                          from_cache: bool, cache_valid: bool):
        """记录性能数据到数据库"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT INTO performance 
            (source_id, timestamp, force_update, response_time, news_count, from_cache, cache_valid) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (source_id, datetime.datetime.now().isoformat(), 
                 1 if force_update else 0, response_time, news_count,
                 1 if from_cache else 0, 1 if cache_valid else 0))
            self.conn.commit()
        except Exception as e:
            logger.error(f"记录性能数据时出错: {str(e)}")
    
    def record_cache_event(self, source_id: str, event_type: str, cache_size: int,
                         cache_age: float, response_time: float, success: bool, message: str = ""):
        """记录缓存事件"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
            INSERT INTO cache_events 
            (source_id, event_type, event_time, cache_size, cache_age, response_time, success, message) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (source_id, event_type, datetime.datetime.now().isoformat(), 
                 cache_size, cache_age, response_time, 1 if success else 0, message))
            self.conn.commit()
        except Exception as e:
            logger.error(f"记录缓存事件时出错: {str(e)}")
    
    def analyze_performance(self, source_id: Optional[str] = None, days: int = 7):
        """分析缓存性能"""
        try:
            query = '''
            SELECT source_id, force_update, AVG(response_time) as avg_time,
                   COUNT(*) as count, AVG(news_count) as avg_news_count,
                   SUM(from_cache) as cache_hits
            FROM performance 
            WHERE timestamp > datetime('now', '-{} days')
            '''.format(days)
            
            if source_id:
                query += f" AND source_id = '{source_id}'"
                
            query += " GROUP BY source_id, force_update"
            
            df = pd.read_sql_query(query, self.conn)
            
            # 计算缓存加速比
            results = []
            
            for sid in df['source_id'].unique():
                force_df = df[(df['source_id'] == sid) & (df['force_update'] == 1)]
                cache_df = df[(df['source_id'] == sid) & (df['force_update'] == 0)]
                
                if not force_df.empty and not cache_df.empty:
                    force_time = force_df['avg_time'].values[0]
                    cache_time = cache_df['avg_time'].values[0]
                    speedup = force_time / cache_time if cache_time > 0 else 0
                    
                    results.append({
                        'source_id': sid,
                        'force_update_time': force_time,
                        'cache_time': cache_time,
                        'speedup': speedup,
                        'force_count': force_df['count'].values[0],
                        'cache_count': cache_df['count'].values[0],
                        'cache_hits': cache_df['cache_hits'].values[0],
                        'cache_hit_rate': cache_df['cache_hits'].values[0] / cache_df['count'].values[0] if cache_df['count'].values[0] > 0 else 0,
                        'avg_news_count': cache_df['avg_news_count'].values[0]
                    })
            
            return results
        except Exception as e:
            logger.error(f"分析性能时出错: {str(e)}")
            return []
    
    def generate_report(self, days: int = 7):
        """生成缓存性能报告"""
        try:
            # 获取源信息
            cursor = self.conn.cursor()
            cursor.execute('SELECT source_id, name, type, cache_ttl, update_interval FROM sources')
            sources = {row[0]: {'name': row[1], 'type': row[2], 'cache_ttl': row[3], 'update_interval': row[4]} 
                      for row in cursor.fetchall()}
            
            # 分析性能
            performance = self.analyze_performance(days=days)
            
            # 生成报告
            report = {
                'timestamp': datetime.datetime.now().isoformat(),
                'period_days': days,
                'sources': len(sources),
                'analyzed_sources': len(performance),
                'summary': {
                    'avg_speedup': sum(p['speedup'] for p in performance) / len(performance) if performance else 0,
                    'effective_cache_count': sum(1 for p in performance if p['speedup'] > 1.5),
                    'avg_cache_hit_rate': sum(p['cache_hit_rate'] for p in performance) / len(performance) if performance else 0
                },
                'source_details': []
            }
            
            # 添加每个源的详细信息
            for p in performance:
                source_id = p['source_id']
                source_info = sources.get(source_id, {})
                
                report['source_details'].append({
                    'source_id': source_id,
                    'name': source_info.get('name', ''),
                    'type': source_info.get('type', ''),
                    'cache_ttl': source_info.get('cache_ttl', 0),
                    'update_interval': source_info.get('update_interval', 0),
                    'performance': {
                        'force_update_time': p['force_update_time'],
                        'cache_time': p['cache_time'],
                        'speedup': p['speedup'],
                        'cache_effective': p['speedup'] > 1.5,
                        'cache_hit_rate': p['cache_hit_rate'],
                        'avg_news_count': p['avg_news_count']
                    }
                })
            
            return report
        except Exception as e:
            logger.error(f"生成报告时出错: {str(e)}")
            return {}
    
    def save_report(self, report, output_file="cache_report.json"):
        """保存报告到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"报告已保存到: {output_file}")
        except Exception as e:
            logger.error(f"保存报告时出错: {str(e)}")
    
    def print_report_summary(self, report):
        """打印报告摘要"""
        if not report:
            logger.error("无报告数据")
            return
            
        print("\n" + "="*80)
        print(f"缓存性能报告摘要 ({report['timestamp']})")
        print("="*80)
        
        print(f"\n分析周期: {report['period_days']} 天")
        print(f"分析源数量: {report['analyzed_sources']} / {report['sources']}")
        print(f"平均缓存加速比: {report['summary']['avg_speedup']:.2f}x")
        print(f"有效缓存比例: {report['summary']['effective_cache_count']} / {report['analyzed_sources']} ({report['summary']['effective_cache_count']/report['analyzed_sources']*100:.1f}%)")
        print(f"平均缓存命中率: {report['summary']['avg_cache_hit_rate']*100:.1f}%")
        
        # 打印表格
        table_data = []
        for detail in sorted(report['source_details'], key=lambda x: x['performance']['speedup'], reverse=True):
            perf = detail['performance']
            table_data.append([
                detail['source_id'],
                detail['name'],
                detail['type'],
                f"{perf['speedup']:.2f}x",
                "✓" if perf['cache_effective'] else "✗",
                f"{perf['cache_hit_rate']*100:.1f}%",
                f"{detail['cache_ttl']//60} 分钟",
                f"{detail['update_interval']//60} 分钟",
                f"{perf['avg_news_count']:.1f}"
            ])
        
        headers = ["源ID", "名称", "类型", "加速比", "有效", "命中率", "缓存TTL", "更新间隔", "平均条数"]
        print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # 输出建议
        print("\n" + "-"*80)
        print("缓存优化建议:")
        print("-"*80)
        
        # 找出缓存不有效的源
        ineffective = [d for d in report['source_details'] if not d['performance']['cache_effective']]
        if ineffective:
            print(f"\n以下 {len(ineffective)} 个源缓存性能不佳，需要优化:")
            for d in ineffective:
                print(f"  - {d['source_id']} ({d['name']}): 加速比 {d['performance']['speedup']:.2f}x")
            
        # 找出TTL过长或过短的源
        ttl_issues = [d for d in report['source_details'] 
                      if (d['cache_ttl'] > d['update_interval'] * 0.8) or 
                         (d['cache_ttl'] < d['update_interval'] * 0.3 and d['cache_ttl'] > 0)]
        if ttl_issues:
            print(f"\n以下 {len(ttl_issues)} 个源缓存TTL配置可能需要调整:")
            for d in ttl_issues:
                if d['cache_ttl'] > d['update_interval'] * 0.8:
                    print(f"  - {d['source_id']}: TTL过长 ({d['cache_ttl']//60}分钟 vs 更新间隔{d['update_interval']//60}分钟)")
                else:
                    print(f"  - {d['source_id']}: TTL过短 ({d['cache_ttl']//60}分钟 vs 更新间隔{d['update_interval']//60}分钟)")
        
        print("\n" + "="*80)
            
    def plot_performance(self, report, output_file="cache_performance.png"):
        """绘制性能图表"""
        try:
            if not report or not report['source_details']:
                logger.error("无报告数据可绘制")
                return
                
            source_ids = [d['source_id'] for d in report['source_details']]
            speedups = [d['performance']['speedup'] for d in report['source_details']]
            hit_rates = [d['performance']['cache_hit_rate'] * 100 for d in report['source_details']]
            
            # 按加速比排序
            sorted_indices = sorted(range(len(speedups)), key=lambda i: speedups[i], reverse=True)
            source_ids = [source_ids[i] for i in sorted_indices]
            speedups = [speedups[i] for i in sorted_indices]
            hit_rates = [hit_rates[i] for i in sorted_indices]
            
            # 绘图
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
            
            # 绘制加速比
            bars1 = ax1.bar(source_ids, speedups, color='skyblue')
            ax1.axhline(y=1.5, color='r', linestyle='-', alpha=0.7, label='有效加速阈值 (1.5x)')
            ax1.set_title('缓存加速比 (越高越好)')
            ax1.set_xlabel('新闻源ID')
            ax1.set_ylabel('加速比')
            ax1.legend()
            
            # 高亮有效加速的条
            for i, bar in enumerate(bars1):
                if speedups[i] >= 1.5:
                    bar.set_color('green')
                    
            # 旋转x轴标签以避免重叠
            plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
            
            # 绘制命中率
            bars2 = ax2.bar(source_ids, hit_rates, color='lightgreen')
            ax2.axhline(y=90, color='r', linestyle='-', alpha=0.7, label='理想命中率 (90%)')
            ax2.set_title('缓存命中率 (越高越好)')
            ax2.set_xlabel('新闻源ID')
            ax2.set_ylabel('命中率 (%)')
            ax2.legend()
            
            # 高亮高命中率的条
            for i, bar in enumerate(bars2):
                if hit_rates[i] >= 90:
                    bar.set_color('green')
                    
            # 旋转x轴标签以避免重叠
            plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            plt.savefig(output_file)
            logger.info(f"性能图表已保存到: {output_file}")
            
            # 关闭图表
            plt.close()
        except Exception as e:
            logger.error(f"绘制图表时出错: {str(e)}")

async def register_sources():
    """注册源，使用新的缓存增强器统一改进所有源"""
    logging.info("初始化新闻提供者...")
    provider = DefaultNewsSourceProvider()
    
    # 增强所有源
    enhance_all_sources(provider)
    
    logging.info(f"成功注册了 {len(provider.get_all_sources())} 个新闻源，所有源已经过缓存增强")
    return provider

async def test_source_caching(source_id: str, test_count: int = 3):
    """测试指定源的缓存行为"""
    logging.info(f"开始测试 {source_id} 源的缓存行为...")
    
    provider = DefaultNewsSourceProvider()
    
    # 获取源并应用缓存增强
    provider_sources = provider.get_all_sources()
    
    # 查找指定的源
    source = None
    if isinstance(provider_sources, dict):
        if source_id not in provider_sources:
            logging.error(f"未找到源 {source_id}")
            return
        source = provider_sources[source_id]
    else:
        # 如果provider_sources是列表，遍历查找匹配的source_id
        source = next((s for s in provider_sources if s.source_id == source_id), None)
        if not source:
            logging.error(f"未找到源 {source_id}")
            return
    
    # 注册到缓存监控器 - 这会自动增强源
    cache_monitor.register_source(source)
    
    logging.info(f"源初始化完成: {source.source_id} - {source.name}")
    logging.info(f"缓存设置: update_interval={source.update_interval}, cache_ttl={source.cache_ttl}")
    
    # 测试场景1: 强制更新 (绕过缓存，测试实际获取性能)
    logging.info("\n=== 场景1: 强制更新 ===")
    forced_times = []
    for i in range(test_count):
        start_time = time.time()
        news = await source.get_news(force_update=True)
        elapsed = time.time() - start_time
        forced_times.append(elapsed)
        
        logging.info(f"强制更新 #{i+1}: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
        if i < test_count - 1:
            await asyncio.sleep(1)  # 短暂暂停防止请求频率过高
    
    avg_forced = sum(forced_times) / len(forced_times)
    logging.info(f"强制更新平均耗时: {avg_forced:.3f}秒")
    
    # 测试场景2: 缓存检索 (不强制更新，使用缓存)
    logging.info("\n=== 场景2: 缓存检索 ===")
    cache_times = []
    for i in range(test_count):
        start_time = time.time()
        news = await source.get_news(force_update=False)
        elapsed = time.time() - start_time
        cache_times.append(elapsed)
        
        logging.info(f"缓存检索 #{i+1}: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
        if i < test_count - 1:
            await asyncio.sleep(0.5)
    
    avg_cache = sum(cache_times) / len(cache_times) if cache_times else 0
    logging.info(f"缓存检索平均耗时: {avg_cache:.3f}秒")
    
    # 测试场景3: 缓存清除后检索 (模拟缓存过期)
    logging.info("\n=== 场景3: 缓存清除 ===")
    await source.clear_cache()
    start_time = time.time()
    news = await source.get_news()
    elapsed = time.time() - start_time
    
    logging.info(f"清除缓存后检索: 获取了 {len(news)} 条新闻, 耗时: {elapsed:.3f}秒")
    
    # 汇总当前缓存指标和保护状态
    cache_status = source.cache_status()
    
    # 计算加速比
    acceleration_ratio = avg_forced / max(avg_cache, 0.001)
    
    logging.info("\n=== 测试结果汇总 ===")
    logging.info(f"强制更新平均耗时: {avg_forced:.3f}秒")
    logging.info(f"缓存检索平均耗时: {avg_cache:.3f}秒")
    logging.info(f"缓存加速比: {acceleration_ratio:.2f}x")
    
    # 输出缓存状态和保护指标
    logging.info("\n=== 缓存状态和保护指标 ===")
    logging.info(f"缓存条目数: {cache_status['cache_state']['items_count']}")
    logging.info(f"缓存有效性: {cache_status['cache_state']['valid']}")
    logging.info(f"缓存命中率: {cache_status['metrics']['hit_ratio']:.2%}")
    
    # 保护统计
    protections = cache_status['protection_stats']
    logging.info(f"保护统计: 空结果保护={protections['empty_protection_count']}, " +
                 f"错误保护={protections['error_protection_count']}, " +
                 f"数据减少保护={protections['shrink_protection_count']}")
    
    if protections['total_protection_count'] > 0:
        logging.info("保护机制已激活，缓存保持了数据完整性")
    
    return True

async def enhanced_cache_status(source_id: Optional[str] = None):
    """显示源的增强缓存状态"""
    provider = DefaultNewsSourceProvider()
    
    # 增强所有源
    enhance_all_sources(provider)
    
    if source_id:
        # 显示单个源的详细状态
        sources = provider.get_all_sources()
        
        # 查找指定的源
        source = None
        if isinstance(sources, dict):
            if source_id not in sources:
                logging.error(f"未找到源 {source_id}")
                return
            source = sources[source_id]
        else:
            # 如果sources是列表，遍历查找匹配的source_id
            source = next((s for s in sources if s.source_id == source_id), None)
            if not source:
                logging.error(f"未找到源 {source_id}")
                return
        
        status = source.cache_status()
        
        logging.info(f"\n=== {source_id} ({source.name}) 缓存状态 ===")
        logging.info(f"缓存配置: update_interval={status['cache_config']['update_interval']}秒, " +
                     f"cache_ttl={status['cache_config']['cache_ttl']}秒")
        
        # 显示自适应设置（如果有）
        if status['cache_config']['adaptive_enabled']:
            logging.info(f"自适应间隔: {status['cache_config']['current_adaptive_interval']}秒")
        
        # 缓存状态
        cache_state = status['cache_state']
        logging.info("\n缓存状态:")
        logging.info(f"  条目数: {cache_state['items_count']}")
        logging.info(f"  最后更新: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cache_state['last_update']))}")
        logging.info(f"  缓存年龄: {cache_state['cache_age_seconds']:.1f}秒")
        logging.info(f"  是否过期: {cache_state['is_expired']}")
        logging.info(f"  是否有效: {cache_state['valid']}")
        
        # 保护统计
        protections = status['protection_stats']
        logging.info("\n保护统计:")
        logging.info(f"  空结果保护: {protections['empty_protection_count']} 次")
        logging.info(f"  错误保护: {protections['error_protection_count']} 次")
        logging.info(f"  数据减少保护: {protections['shrink_protection_count']} 次")
        logging.info(f"  总保护次数: {protections['total_protection_count']} 次")
        
        if protections['recent_protections']:
            logging.info("\n最近保护事件:")
            for event in protections['recent_protections']:
                event_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event['time']))
                if event['type'] == 'empty_protection':
                    logging.info(f"  {event_time}: 空结果保护 (保护了 {event['cache_size']} 条数据)")
                elif event['type'] == 'error_protection':
                    logging.info(f"  {event_time}: 错误保护 - {event['error']} (保护了 {event['cache_size']} 条数据)")
                elif event['type'] == 'shrink_protection':
                    ratio = event['reduction_ratio'] * 100
                    logging.info(f"  {event_time}: 数据减少保护 - 从 {event['old_size']} 到 {event['new_size']} 条 (减少 {ratio:.1f}%)")
        
        # 性能指标
        metrics = status['metrics']
        logging.info("\n性能指标:")
        logging.info(f"  缓存命中: {metrics['cache_hit_count']} 次")
        logging.info(f"  缓存未命中: {metrics['cache_miss_count']} 次")
        logging.info(f"  命中率: {metrics['hit_ratio']:.2%}")
        logging.info(f"  空结果次数: {metrics['empty_result_count']} 次")
        logging.info(f"  获取错误次数: {metrics['fetch_error_count']} 次")
    else:
        # 显示全局状态
        global_status = cache_monitor.get_global_status()
        metrics = global_status['global_metrics']
        
        logging.info("\n=== 全局缓存状态 ===")
        logging.info(f"增强的源数量: {len(global_status['sources'])}")
        logging.info(f"总缓存命中: {metrics['total_cache_hits']} 次")
        logging.info(f"总缓存未命中: {metrics['total_cache_misses']} 次")
        logging.info(f"全局命中率: {metrics['global_hit_ratio']:.2%}")
        logging.info(f"总保护次数: {metrics['total_protections']} 次")
        
        # 保护分类
        logging.info("\n保护分类:")
        logging.info(f"  空结果保护: {metrics['protection_breakdown']['empty_protections']} 次")
        logging.info(f"  错误保护: {metrics['protection_breakdown']['error_protections']} 次")
        logging.info(f"  数据减少保护: {metrics['protection_breakdown']['shrink_protections']} 次")
        
        # 源状态摘要
        logging.info("\n源摘要:")
        for source_id, source_status in global_status['sources'].items():
            protection_count = source_status['protection_stats']['total_protection_count']
            cache_size = source_status['cache_state']['items_count']
            hit_ratio = source_status['metrics']['hit_ratio']
            
            protection_indicator = "🛡️ " if protection_count > 0 else ""
            logging.info(f"  {protection_indicator}{source_id}: {cache_size}条数据, 命中率={hit_ratio:.2%}, 保护次数={protection_count}")

async def main():
    parser = argparse.ArgumentParser(description="新闻源缓存监控工具")
    parser.add_argument("--register", action="store_true", help="注册所有新闻源")
    parser.add_argument("--test", type=str, help="测试指定源的缓存行为")
    parser.add_argument("--status", action="store_true", help="显示所有源的缓存状态")
    parser.add_argument("--source-status", type=str, help="显示指定源的详细缓存状态")
    parser.add_argument("--debug", action="store_true", help="开启调试日志")
    
    args = parser.parse_args()
    
    # 设置日志级别
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    if args.register:
        await register_sources()
    elif args.test:
        await test_source_caching(args.test)
    elif args.status:
        await enhanced_cache_status()
    elif args.source_status:
        await enhanced_cache_status(args.source_status)
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main()) 