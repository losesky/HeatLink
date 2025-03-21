#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新闻源适配器验证工具

此脚本用于检查数据库中的新闻源记录与代码中的适配器是否完全匹配。
它会检测以下问题:
1. 代码中有适配器但数据库中没有对应记录
2. 数据库中有记录但代码中没有对应适配器
3. 适配器和数据库记录的基本属性不匹配(例如name, url等)

运行方式:
python -m backend.scripts.validate_sources [选项]

参数:
--fix: 自动修复发现的问题(创建缺失的数据库记录或更新不匹配的记录)
--verbose: 显示详细输出
--export FILE: 导出验证报告到指定文件
--clean: 清理无效的数据库记录
--batch: 批处理模式，无需用户交互
--analyze: 分析代码和数据库之间的差异
"""

import sys
import os
import argparse
import logging
import inspect
from typing import Dict, List, Set, Any, Optional, Tuple
import datetime
import enum
import json
import re
import signal
from contextlib import contextmanager

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# 导入dotenv加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("source_validator")

# 从worker模块导入适配器相关类
from worker.sources.factory import NewsSourceFactory
from worker.sources.base import NewsSource
import worker.sources.sites as sites_module

# 手动定义SourceType，避免导入模型类
class SourceType(enum.Enum):
    RSS = "RSS"
    API = "API"
    WEB = "WEB"
    MIXED = "MIXED"

# 添加超时处理
class TimeoutError(Exception):
    pass

@contextmanager
def timeout(seconds):
    """超时装饰器，用于限制操作的最大执行时间"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"操作超时 ({seconds}秒)")

    # 设置SIGALRM处理器
    original_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)
    
    # 启动定时器
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # 恢复之前的信号处理器并取消定时器
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)

class SourceValidator:
    """新闻源适配器验证工具"""
    
    def __init__(self, fix: bool = False, verbose: bool = False, batch: bool = False):
        """初始化验证工具
        
        Args:
            fix: 是否自动修复发现的问题
            verbose: 是否显示详细输出
            batch: 是否使用批处理模式，无需用户交互
        """
        self.fix = fix
        self.verbose = verbose
        self.batch = batch
        self.db = self._create_db_session()
        
        # 初始化计数器
        self.missing_db_records = 0
        self.missing_adapters = 0
        self.mismatched_records = 0
        self.fixed_records = 0
        
        # 已知需要额外参数的通用适配器类型
        self.GENERAL_ADAPTERS = ["rss"]
        
        # 初始化源列表
        self.db_sources: Dict[str, Any] = {}
        self.code_adapters: Dict[str, Dict[str, Any]] = {}
        
    def _create_db_session(self):
        """创建数据库会话"""
        # 导入这里以避免模型重复定义问题
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.exc import OperationalError
        
        # 从环境变量获取数据库连接URL
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("环境变量DATABASE_URL未设置，请确保.env文件已加载")
            
        self.log(f"连接到数据库: {database_url}", "debug")
        try:
            engine = create_engine(database_url)
            # 测试连接
            engine.connect().close()
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            return SessionLocal()
        except OperationalError as e:
            print("\n" + "="*50)
            print("错误: 无法连接到数据库")
            print("="*50)
            print("可能原因:")
            print("1. 数据库服务未启动")
            print("2. 数据库连接信息不正确")
            print("3. 数据库拒绝连接 (权限问题)")
            print("\n建议操作:")
            print("1. 检查数据库服务是否运行: docker ps | grep postgres")
            print("2. 确认环境变量DATABASE_URL配置正确")
            print("3. 尝试手动连接数据库验证凭据: psql -U [用户名] -h [主机] -d [数据库名]")
            print("="*50)
            print(f"原始错误: {str(e)}")
            print("="*50 + "\n")
            sys.exit(1)
        
    def log(self, message: str, level: str = "info"):
        """记录日志
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "debug" and self.verbose:
            logger.debug(message)
    
    def load_db_sources(self):
        """从数据库加载所有新闻源记录"""
        self.log("从数据库加载新闻源记录...", "debug")
        
        # 使用SQL直接查询，避免导入模型类
        from sqlalchemy import text
        query = text("SELECT id, name, url, update_interval, cache_ttl, type, country, language, config FROM sources")
        result = self.db.execute(query)
        
        for row in result:
            # 将查询结果转换为字典
            source = {
                'id': row[0],
                'name': row[1],
                'url': row[2],
                'update_interval': row[3],
                'cache_ttl': row[4],
                'type': row[5],
                'country': row[6],
                'language': row[7],
                'config': row[8]
            }
            self.db_sources[source['id']] = source
            
        self.log(f"从数据库加载了 {len(self.db_sources)} 个新闻源记录", "info")
    
    def load_code_adapters(self):
        """从代码中加载所有适配器"""
        self.log("从代码中加载适配器...", "debug")
        
        # 方法1: 从NewsSourceFactory.create_default_sources方法中提取
        factory_sources = self._extract_sources_from_factory()
        
        # 方法2: 通过反射获取所有适配器类
        adapter_classes = self._discover_adapter_classes()
        
        # 合并两种方法的结果
        self.code_adapters = {}
        self.code_adapters.update(factory_sources)
        
        for class_name, adapter_class in adapter_classes.items():
            # 如果适配器类已经在factory中,则跳过
            if self._get_adapter_source_id(adapter_class) in self.code_adapters:
                continue
                
            # 获取默认参数
            defaults = self._get_adapter_defaults(adapter_class)
            if defaults and 'source_id' in defaults:
                self.code_adapters[defaults['source_id']] = defaults
        
        self.log(f"从代码中加载了 {len(self.code_adapters)} 个适配器", "info")
    
    def _extract_sources_from_factory(self) -> Dict[str, Dict[str, Any]]:
        """从NewsSourceFactory.create_default_sources方法中提取适配器"""
        self.log("从NewsSourceFactory提取适配器...", "debug")
        
        try:
            # 获取create_source方法中的适配器信息
            sources: Dict[str, Dict[str, Any]] = {}
            
            # 解析create_source方法
            source_code = inspect.getsource(NewsSourceFactory.create_source)
            lines = source_code.split('\n')
            
            current_source_id = None
            for line in lines:
                line = line.strip()
                
                # 查找elif source_type == "xxx": 模式
                if 'source_type ==' in line or 'source_type==' in line:
                    # 提取source_id
                    try:
                        source_id = line.split('"')[1]
                        current_source_id = source_id
                        sources[source_id] = {'source_id': source_id}
                    except (IndexError, KeyError):
                        pass
                
                # 查找adapter_class(**kwargs)模式
                elif current_source_id and 'return' in line and '(' in line and ')' in line:
                    adapter_name = line.split('return ')[1].split('(')[0].strip()
                    sources[current_source_id]['adapter_class'] = adapter_name
                    
                    # 尝试获取适配器类的默认参数
                    try:
                        # 从global命名空间或当前模块中获取类
                        adapter_class = None
                        try:
                            # 先尝试直接eval
                            adapter_class = eval(adapter_name)
                        except (NameError, AttributeError):
                            # 从sites模块尝试导入
                            if hasattr(sites_module, adapter_name):
                                adapter_class = getattr(sites_module, adapter_name)
                        
                        if adapter_class:
                            # 获取默认参数
                            defaults = self._get_adapter_defaults(adapter_class)
                            if defaults:
                                # 不覆盖source_id
                                defaults['source_id'] = current_source_id 
                                sources[current_source_id].update(defaults)
                            
                            # 获取类的名称作为默认名称
                            if 'name' not in sources[current_source_id]:
                                class_name = adapter_class.__name__
                                # 将驼峰命名转换为空格分隔的标题
                                name = re.sub(r'([a-z])([A-Z])', r'\1 \2', class_name)
                                # 移除NewsSource后缀
                                name = name.replace('News Source', '').strip()
                                sources[current_source_id]['name'] = name
                    except Exception as e:
                        self.log(f"获取适配器{adapter_name}信息失败: {str(e)}", "debug")
            
            # 使用硬编码默认值填充缺失的关键属性
            for source_id, info in sources.items():
                if 'name' not in info or not info['name']:
                    # 将source_id转换为可读名称
                    name = source_id.replace('-', ' ').replace('_', ' ').title()
                    info['name'] = name
                
                # 确保有URL
                if 'url' not in info or not info.get('url'):
                    # 为常见源设置默认URL
                    if 'bloomberg' in source_id:
                        info['url'] = 'https://www.bloomberg.com'
                    elif 'bbc' in source_id:
                        info['url'] = 'https://www.bbc.com'
                    elif 'techcrunch' in source_id:
                        info['url'] = 'https://techcrunch.com'
                    elif 'the_verge' in source_id:
                        info['url'] = 'https://www.theverge.com'
                    elif 'hacker_news' in source_id:
                        info['url'] = 'https://news.ycombinator.com'
                    elif 'zhihu' in source_id:
                        info['url'] = 'https://www.zhihu.com'
                    elif 'ifanr' in source_id:
                        info['url'] = 'https://www.ifanr.com'
                    elif 'cls' in source_id:
                        info['url'] = 'https://www.cls.cn'
                    elif 'coolapk' in source_id:
                        info['url'] = 'https://www.coolapk.com'
                    elif 'linuxdo' in source_id:
                        info['url'] = 'https://linux.cn'
                    elif 'fastbull' in source_id:
                        info['url'] = 'https://www.fastbull.cn'
                    elif 'thepaper' in source_id:
                        info['url'] = 'https://www.thepaper.cn'
                    else:
                        info['url'] = f"https://example.com/{source_id}"
                    
                # 确保有更新间隔
                if 'update_interval' not in info:
                    info['update_interval'] = 1800  # 默认30分钟
                
                # 确保有缓存TTL
                if 'cache_ttl' not in info:
                    info['cache_ttl'] = 900  # 默认15分钟
                
                # 确保有描述
                if 'description' not in info or not info.get('description'):
                    info['description'] = f"{info['name']} 新闻源"
                
                # 语言和国家
                if 'language' not in info or not info.get('language'):
                    # 根据source_id猜测语言
                    if any(term in source_id for term in ['bbc', 'bloomberg', 'techcrunch', 'the_verge', 'hacker_news']):
                        info['language'] = 'en-US'
                    else:
                        info['language'] = 'zh-CN'
                    
                if 'country' not in info or not info.get('country'):
                    # 根据source_id猜测国家
                    if any(term in source_id for term in ['bbc', 'bloomberg', 'techcrunch', 'the_verge', 'hacker_news']):
                        info['country'] = 'USA'
                    else:
                        info['country'] = '中国'
            
            self.log(f"从factory中提取了 {len(sources)} 个适配器", "debug")
            return sources
            
        except Exception as e:
            self.log(f"从factory提取适配器失败: {str(e)}", "error")
            return {}
    
    def _discover_adapter_classes(self) -> Dict[str, type]:
        """通过反射获取所有适配器类"""
        self.log("通过反射获取适配器类...", "debug")
        
        adapter_classes = {}
        
        # 获取sites模块中的所有类
        for name in dir(sites_module):
            if name.startswith('_'):
                continue
                
            attr = getattr(sites_module, name)
            
            # 检查是否是NewsSource的子类
            if (inspect.isclass(attr) and 
                issubclass(attr, NewsSource) and 
                attr is not NewsSource):
                
                adapter_classes[name] = attr
        
        self.log(f"通过反射获取了 {len(adapter_classes)} 个适配器类", "debug")
        return adapter_classes
    
    def _get_adapter_source_id(self, adapter_class) -> Optional[str]:
        """获取适配器类的source_id"""
        try:
            # 查看__init__方法的默认参数
            signature = inspect.signature(adapter_class.__init__)
            parameters = signature.parameters
            
            # 获取source_id参数的默认值
            if 'source_id' in parameters and parameters['source_id'].default is not inspect.Parameter.empty:
                return parameters['source_id'].default
        except Exception:
            pass
        
        return None
    
    def _get_adapter_defaults(self, adapter_class) -> Dict[str, Any]:
        """获取适配器类的默认参数"""
        defaults = {}
        
        try:
            # 查看__init__方法的默认参数
            signature = inspect.signature(adapter_class.__init__)
            parameters = signature.parameters
            
            # 获取所有参数的默认值
            for name, param in parameters.items():
                if param.default is not inspect.Parameter.empty and name != 'self' and name != 'config':
                    defaults[name] = param.default
            
            # 获取类的注释和文档
            if adapter_class.__doc__:
                defaults['description'] = adapter_class.__doc__.strip().split('\n')[0]
        except Exception as e:
            self.log(f"获取适配器{adapter_class.__name__}默认参数失败: {str(e)}", "debug")
        
        return defaults
    
    def analyze_differences(self):
        """分析代码和数据库之间的差异，提供更详细的统计和报告"""
        # 初始化统计
        stats = {
            "timestamp": datetime.datetime.now().isoformat(),
            "total_db_sources": len(self.db_sources),
            "total_code_adapters": len(self.code_adapters),
            "missing_db_records": 0,
            "missing_adapters": 0,
            "mismatched_records": 0,
            "requires_extra_params": [],
            "source_type_stats": {},
            "active_vs_inactive": {"active": 0, "inactive": 0},
            "errors": []
        }
        
        # 检查每个代码适配器
        for source_id, adapter_info in self.code_adapters.items():
            # 分类源类型
            source_type = self._guess_source_type(adapter_info)
            source_type_value = source_type.value if isinstance(source_type, enum.Enum) else str(source_type)
            if source_type_value not in stats["source_type_stats"]:
                stats["source_type_stats"][source_type_value] = 0
            stats["source_type_stats"][source_type_value] += 1
            
            # 检查是否需要额外参数
            if self._requires_extra_params(source_id):
                stats["requires_extra_params"].append(source_id)
            
            # 检查是否缺少数据库记录
            if source_id not in self.db_sources:
                stats["missing_db_records"] += 1
        
        # 检查每个数据库记录
        for source_id, source in self.db_sources.items():
            # 统计活跃状态
            is_active = source.get('active', True)  # 默认假设活跃
            if is_active:
                stats["active_vs_inactive"]["active"] += 1
            else:
                stats["active_vs_inactive"]["inactive"] += 1
            
            # 检查是否缺少代码适配器
            if source_id not in self.code_adapters:
                stats["missing_adapters"] += 1
            
            # 如果存在对应的代码适配器，检查是否属性不匹配
            elif source_id in self.code_adapters:
                adapter_info = self.code_adapters[source_id]
                mismatches = self._check_mismatches(source_id, adapter_info, source)
                if mismatches:
                    stats["mismatched_records"] += 1
        
        # 打印分析报告
        self.log("\n==== 数据源差异分析 ====", "info")
        self.log(f"数据库源总数: {stats['total_db_sources']}", "info")
        self.log(f"代码适配器总数: {stats['total_code_adapters']}", "info")
        self.log(f"缺失数据库记录: {stats['missing_db_records']}", "info")
        self.log(f"缺失代码适配器: {stats['missing_adapters']}", "info")
        self.log(f"属性不匹配记录: {stats['mismatched_records']}", "info")
        
        self.log("\n源类型统计:", "info")
        for source_type, count in stats["source_type_stats"].items():
            self.log(f"- {source_type}: {count}", "info")
        
        self.log(f"\n活跃/非活跃源: 活跃={stats['active_vs_inactive']['active']}, 非活跃={stats['active_vs_inactive']['inactive']}", "info")
        
        if stats["requires_extra_params"]:
            self.log(f"\n需要额外参数的源 ({len(stats['requires_extra_params'])}):", "info")
            for i, source_id in enumerate(sorted(stats["requires_extra_params"])):
                self.log(f"- {source_id}", "info")
        
        return stats
    
    def _check_mismatches(self, source_id: str, adapter_info: Dict[str, Any], db_source: Dict[str, Any]) -> List[str]:
        """检查适配器和数据库记录之间的不匹配"""
        mismatches = []
        
        # 检查名称
        if 'name' in adapter_info and adapter_info['name'] != db_source['name']:
            mismatches.append(f"名称不匹配: {db_source['name']} (DB) vs {adapter_info['name']} (代码)")
        
        # 检查URL
        adapter_url = adapter_info.get('url') or adapter_info.get('api_url') or adapter_info.get('feed_url')
        if adapter_url and adapter_url != db_source['url']:
            mismatches.append(f"URL不匹配: {db_source['url']} (DB) vs {adapter_url} (代码)")
        
        # 检查更新间隔(注意单位转换)
        if 'update_interval' in adapter_info and db_source['update_interval'] is not None:
            # 适配器中通常以秒为单位
            code_interval = adapter_info['update_interval']
            # 将数据库中的timedelta转换为秒
            try:
                # 解析数据库返回的interval字符串 (例如 "1 day, 0:00:00")
                interval_str = str(db_source['update_interval'])
                total_seconds = 0
                
                # 解析天数
                days_match = re.search(r'(\d+) day', interval_str)
                if days_match:
                    total_seconds += int(days_match.group(1)) * 86400
                
                # 解析时:分:秒
                time_match = re.search(r'(\d+):(\d+):(\d+)', interval_str)
                if time_match:
                    hours = int(time_match.group(1))
                    minutes = int(time_match.group(2))
                    seconds = int(time_match.group(3))
                    total_seconds += hours * 3600 + minutes * 60 + seconds
                
                db_interval = total_seconds
                
                if abs(code_interval - db_interval) > 1:  # 允许1秒误差
                    mismatches.append(f"更新间隔不匹配: {db_interval}秒 (DB) vs {code_interval}秒 (代码)")
            except Exception as e:
                self.log(f"解析更新间隔失败: {str(e)}", "debug")
        
        return mismatches
    
    def export_report(self, filepath: str):
        """导出验证报告到文件"""
        # 生成报告数据
        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "database": {
                "total_sources": len(self.db_sources),
                "sources": {
                    source_id: {
                        "name": source.get("name", "未知"),
                        "url": source.get("url", ""),
                        "type": source.get("type", "")
                    }
                    for source_id, source in self.db_sources.items()
                }
            },
            "code": {
                "total_adapters": len(self.code_adapters),
                "adapters": {
                    source_id: {
                        "name": adapter_info.get("name", "未知"),
                        "requires_extra_params": self._requires_extra_params(source_id)
                    }
                    for source_id, adapter_info in self.code_adapters.items()
                }
            },
            "differences": {
                "missing_db_records": [
                    {"id": source_id, "name": adapter_info.get("name", "未知")}
                    for source_id, adapter_info in self.code_adapters.items()
                    if source_id not in self.db_sources
                ],
                "missing_adapters": [
                    {"id": source_id, "name": source.get("name", "未知")}
                    for source_id, source in self.db_sources.items()
                    if source_id not in self.code_adapters
                ],
                "mismatched_records": [
                    {
                        "id": source_id, 
                        "name": source.get("name", "未知"),
                        "mismatches": self._check_mismatches(source_id, self.code_adapters[source_id], source)
                    }
                    for source_id, source in self.db_sources.items()
                    if source_id in self.code_adapters and self._check_mismatches(source_id, self.code_adapters[source_id], source)
                ]
            }
        }
        
        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.log(f"验证报告已导出到 {filepath}", "info")

    def validate(self, export_file: Optional[str] = None, analyze: bool = False, clean: bool = False):
        """执行验证
        
        Args:
            export_file: 导出报告的文件路径
            analyze: 是否分析差异
            clean: 是否清理无效的数据库记录
        """
        self.log("开始验证新闻源适配器...", "info")
        
        # 加载数据
        self.load_db_sources()
        self.load_code_adapters()
        
        # 如果请求分析差异，则执行分析
        if analyze:
            self.analyze_differences()
        
        # 对比代码和数据库
        self.check_missing_db_records()
        self.check_missing_adapters()
        self.check_mismatched_records()
        
        # 如果请求清理无效记录，则执行清理
        if clean:
            self.clean_invalid_db_records()
        
        # 如果请求导出报告，则导出
        if export_file:
            self.export_report(export_file)
        
        # 输出统计信息
        self.print_summary()
    
    def check_missing_db_records(self):
        """检查代码中有适配器但数据库中没有对应记录的情况"""
        self.log("检查缺失的数据库记录...", "debug")
        
        for source_id, adapter_info in self.code_adapters.items():
            if source_id not in self.db_sources:
                self.missing_db_records += 1
                self.log(f"缺失数据库记录: {source_id} ({adapter_info.get('name', '未知')})", "warning")
                
                # 如果需要修复,则创建数据库记录
                if self.fix:
                    self.create_db_record(source_id, adapter_info)
    
    def check_missing_adapters(self):
        """检查数据库中有记录但代码中没有对应适配器的情况"""
        self.log("检查缺失的适配器...", "debug")
        
        for source_id, source in self.db_sources.items():
            if source_id not in self.code_adapters:
                self.missing_adapters += 1
                self.log(f"缺失适配器: {source_id} ({source['name']})", "warning")
    
    def check_mismatched_records(self):
        """检查适配器和数据库记录的基本属性不匹配的情况"""
        self.log("检查属性不匹配的记录...", "debug")
        
        for source_id, adapter_info in self.code_adapters.items():
            if source_id in self.db_sources:
                db_source = self.db_sources[source_id]
                
                # 检查基本属性
                mismatches = []
                
                # 检查名称
                if 'name' in adapter_info and adapter_info['name'] != db_source['name']:
                    mismatches.append(f"名称不匹配: {db_source['name']} (DB) vs {adapter_info['name']} (代码)")
                
                # 检查URL
                adapter_url = adapter_info.get('url') or adapter_info.get('api_url') or adapter_info.get('feed_url')
                if adapter_url and adapter_url != db_source['url']:
                    mismatches.append(f"URL不匹配: {db_source['url']} (DB) vs {adapter_url} (代码)")
                
                # 检查更新间隔(注意单位转换)
                if 'update_interval' in adapter_info and db_source['update_interval'] is not None:
                    # 适配器中通常以秒为单位
                    code_interval = adapter_info['update_interval']
                    # 将数据库中的timedelta转换为秒
                    try:
                        # 解析数据库返回的interval字符串 (例如 "1 day, 0:00:00")
                        interval_str = str(db_source['update_interval'])
                        total_seconds = 0
                        
                        # 解析天数
                        days_match = re.search(r'(\d+) day', interval_str)
                        if days_match:
                            total_seconds += int(days_match.group(1)) * 86400
                        
                        # 解析时:分:秒
                        time_match = re.search(r'(\d+):(\d+):(\d+)', interval_str)
                        if time_match:
                            hours = int(time_match.group(1))
                            minutes = int(time_match.group(2))
                            seconds = int(time_match.group(3))
                            total_seconds += hours * 3600 + minutes * 60 + seconds
                        
                        db_interval = total_seconds
                        
                        if abs(code_interval - db_interval) > 1:  # 允许1秒误差
                            mismatches.append(f"更新间隔不匹配: {db_interval}秒 (DB) vs {code_interval}秒 (代码)")
                    except Exception as e:
                        self.log(f"解析更新间隔失败: {str(e)}", "debug")
                
                # 如果有不匹配的属性
                if mismatches:
                    self.mismatched_records += 1
                    self.log(f"属性不匹配: {source_id} ({db_source['name']})", "warning")
                    for mismatch in mismatches:
                        self.log(f"  - {mismatch}", "warning")
                    
                    # 如果需要修复
                    if self.fix:
                        self.update_db_record(source_id, adapter_info, mismatches)
    
    def create_db_record(self, source_id: str, adapter_info: Dict[str, Any]):
        """创建数据库记录"""
        try:
            # 获取source_type
            source_type = self._guess_source_type(adapter_info)
            
            # 获取url
            url = adapter_info.get('url') or adapter_info.get('api_url') or adapter_info.get('feed_url') or ""
            
            # 获取update_interval和cache_ttl (秒)
            update_interval_seconds = adapter_info.get('update_interval', 1800)
            cache_ttl_seconds = adapter_info.get('cache_ttl', 900)
            
            # 提取配置并转换为JSON字符串，确保使用单引号避免SQL注入
            config_dict = self._extract_config(adapter_info) or {}
            config_json = json.dumps(config_dict).replace("'", "''")
            
            # 构建SQL插入语句，使用直接的JSON字符串而不是参数绑定
            sql_str = f"""
            INSERT INTO sources 
            (id, name, description, url, type, status, update_interval, cache_ttl, country, language, config, created_at, updated_at) 
            VALUES 
            (:id, :name, :description, :url, :type, :status, 
            INTERVAL '{update_interval_seconds} seconds', 
            INTERVAL '{cache_ttl_seconds} seconds', 
            :country, :language, '{config_json}'::jsonb, now(), now())
            """
            
            from sqlalchemy import text
            sql = text(sql_str)
            
            # 参数 (排除config，因为已直接放入SQL)
            params = {
                'id': source_id,
                'name': adapter_info.get('name', f"未命名源 ({source_id})"),
                'description': adapter_info.get('description', ""),
                'url': url,
                'type': source_type.value if isinstance(source_type, enum.Enum) else source_type,
                'status': 'ACTIVE',  # 默认设置为ACTIVE状态
                'country': adapter_info.get('country', ""),
                'language': adapter_info.get('language', "")
            }
            
            # 执行SQL
            self.db.execute(sql, params)
            self.db.commit()
            
            self.fixed_records += 1
            self.log(f"已创建数据库记录: {source_id}", "info")
        except Exception as e:
            self.log(f"创建数据库记录失败 {source_id}: {str(e)}", "error")
            self.db.rollback()
    
    def update_db_record(self, source_id: str, adapter_info: Dict[str, Any], mismatches: List[str]):
        """更新数据库记录"""
        try:
            # 初始化参数和更新字段
            params = {'id': source_id}
            
            # 构建字段更新部分
            update_parts = []
            
            if any("名称不匹配" in m for m in mismatches):
                update_parts.append("name = :name")
                params['name'] = adapter_info.get('name')
            
            if any("URL不匹配" in m for m in mismatches):
                update_parts.append("url = :url")
                params['url'] = adapter_info.get('url') or adapter_info.get('api_url') or adapter_info.get('feed_url')
            
            # 处理更新间隔，直接在SQL中使用INTERVAL语法
            if any("更新间隔不匹配" in m for m in mismatches):
                update_interval_seconds = adapter_info.get('update_interval', 1800)
                update_parts.append(f"update_interval = INTERVAL '{update_interval_seconds} seconds'")
            
            # 更新updated_at字段
            update_parts.append("updated_at = now()")
            
            # 如果有字段需要更新
            if update_parts:
                # 构建SQL更新语句
                sql_str = f"UPDATE sources SET {', '.join(update_parts)} WHERE id = :id"
                from sqlalchemy import text
                sql = text(sql_str)
                
                # 执行SQL
                self.db.execute(sql, params)
                self.db.commit()
                
                self.fixed_records += 1
                self.log(f"已更新数据库记录: {source_id}", "info")
        except Exception as e:
            self.log(f"更新数据库记录失败 {source_id}: {str(e)}", "error")
            self.db.rollback()
    
    def _guess_source_type(self, adapter_info: Dict[str, Any]) -> SourceType:
        """猜测源类型"""
        adapter_class = adapter_info.get('adapter_class', '')
        
        if 'RSS' in adapter_class:
            return SourceType.RSS
        elif 'API' in adapter_class:
            return SourceType.API
        elif 'Web' in adapter_class:
            return SourceType.WEB
        else:
            return SourceType.MIXED
    
    def _extract_config(self, adapter_info: Dict[str, Any]) -> Dict[str, Any]:
        """提取配置信息"""
        config = {}
        
        # 排除已知的基本属性
        basic_props = {'source_id', 'name', 'url', 'api_url', 'feed_url', 'update_interval', 'cache_ttl', 
                      'category', 'country', 'language', 'adapter_class', 'description'}
        
        for key, value in adapter_info.items():
            if key not in basic_props:
                # 确保值是JSON可序列化的
                if isinstance(value, (str, int, float, bool, list, dict)):
                    config[key] = value
        
        return config
    
    def print_summary(self):
        """打印验证结果摘要"""
        self.log("\n验证结果摘要:", "info")
        self.log(f"- 数据库中的新闻源记录: {len(self.db_sources)}", "info")
        self.log(f"- 代码中的适配器: {len(self.code_adapters)}", "info")
        self.log(f"- 缺失数据库记录: {self.missing_db_records}", "info")
        self.log(f"- 缺失适配器: {self.missing_adapters}", "info")
        self.log(f"- 属性不匹配记录: {self.mismatched_records}", "info")
        
        if self.fix:
            self.log(f"- 已修复记录: {self.fixed_records}", "info")
        
        if self.missing_db_records == 0 and self.missing_adapters == 0 and self.mismatched_records == 0:
            self.log("\n✅ 所有新闻源记录与适配器完全匹配!", "info")
        else:
            self.log("\n❌ 发现不匹配的情况,请检查并修复", "warning")
            
            if not self.fix:
                self.log("提示: 运行 'python -m backend.scripts.validate_sources --fix' 自动修复问题", "info")
    
    def close(self):
        """关闭数据库连接"""
        self.db.close()

    def _requires_extra_params(self, source_id: str) -> bool:
        """检查源类型是否需要额外参数"""
        # 检查是否是已知的通用适配器类型
        if source_id in self.GENERAL_ADAPTERS:
            return True
        
        # 尝试创建实例，看是否会因缺少参数而失败
        try:
            # 使用短超时避免阻塞
            with timeout(2):
                NewsSourceFactory.create_source(source_id)
            return False
        except TypeError as e:
            # 如果错误信息包含"missing required argument"，则需要额外参数
            if "missing required argument" in str(e):
                self.log(f"源 {source_id} 需要额外参数: {str(e)}", "debug")
                return True
        except TimeoutError:
            self.log(f"创建源 {source_id} 超时，可能需要额外操作", "debug")
            return True
        except Exception as e:
            # 其他错误不视为需要额外参数
            self.log(f"创建源 {source_id} 时发生错误: {str(e)}", "debug")
            pass
        
        return False

    def clean_invalid_db_records(self):
        """清理数据库中无效或过时的记录"""
        candidates_for_removal = []
        
        # 检查每个数据库记录
        for source_id, source in self.db_sources.items():
            # 如果代码中没有对应适配器，并且记录是非活跃的
            if source_id not in self.code_adapters and not source.get('active', True):
                candidates_for_removal.append(source_id)
        
        # 没有找到需要清理的记录
        if not candidates_for_removal:
            self.log("\n没有找到需要清理的无效记录", "info")
            return
        
        # 请求用户确认（除非处于批处理模式）
        self.log(f"\n发现 {len(candidates_for_removal)} 个可能需要删除的非活跃记录:", "warning")
        for i, source_id in enumerate(candidates_for_removal):
            self.log(f"{i+1}. {source_id} ({self.db_sources[source_id]['name']})", "warning")
        
        if self.fix:
            # 在批处理模式下自动确认，否则请求用户输入
            if self.batch:
                confirm = "y"
            else:
                confirm = input("\n确认删除这些记录吗? [y/N]: ")
                
            if confirm.lower() == 'y':
                self._delete_db_records(candidates_for_removal)
                self.log(f"已删除 {len(candidates_for_removal)} 个非活跃记录", "info")
            else:
                self.log("已取消删除操作", "info")
        else:
            self.log("提示: 使用 --fix 选项可以删除这些非活跃记录", "info")
    
    def _delete_db_records(self, source_ids: List[str]):
        """从数据库中删除记录
        
        Args:
            source_ids: 要删除的源ID列表
        """
        if not source_ids:
            return
            
        try:
            from sqlalchemy import text
            
            # 构建删除语句
            placeholders = ', '.join([f"'{source_id}'" for source_id in source_ids])
            sql = text(f"DELETE FROM sources WHERE id IN ({placeholders})")
            
            # 执行SQL
            result = self.db.execute(sql)
            self.db.commit()
            
            self.log(f"已从数据库中删除 {result.rowcount} 条记录", "info")
        except Exception as e:
            self.log(f"删除记录失败: {str(e)}", "error")
            self.db.rollback()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="验证新闻源适配器")
    parser.add_argument("--fix", action="store_true", help="自动修复发现的问题")
    parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    parser.add_argument("--export", type=str, help="导出验证报告到指定文件")
    parser.add_argument("--clean", action="store_true", help="清理无效的数据库记录")
    parser.add_argument("--batch", action="store_true", help="批处理模式，无需用户交互")
    parser.add_argument("--analyze", action="store_true", help="分析代码和数据库之间的差异")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        validator = SourceValidator(fix=args.fix, verbose=args.verbose, batch=args.batch)
        try:
            validator.validate(export_file=args.export, analyze=args.analyze, clean=args.clean)
        finally:
            validator.close()
    except ValueError as e:
        # 处理配置或参数错误
        print(f"\n错误: {str(e)}")
        print("请检查环境变量配置和命令行参数。\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n操作被用户中断。")
        sys.exit(0)
    except Exception as e:
        # 处理其他未预期的错误
        print("\n" + "="*50)
        print(f"发生未预期的错误:")
        print("="*50)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("\n如果这个问题持续存在，请检查以下内容:")
        print("1. 数据库结构是否与代码匹配")
        print("2. 项目依赖是否完整安装")
        print("3. 环境变量是否正确配置")
        if args.verbose:
            print("\n详细错误信息:")
            import traceback
            traceback.print_exc()
        print("="*50 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main() 