import logging
import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import jieba
import jieba.analyse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from worker.sources.base import NewsItemModel
from worker.sources.manager import source_manager

logger = logging.getLogger(__name__)


class NewsCluster:
    """
    新闻聚类
    表示一组相似的新闻
    """
    
    def __init__(self, main_news: NewsItemModel):
        self.main_news = main_news  # 主要新闻（代表性新闻）
        self.related_news: List[NewsItemModel] = []  # 相关新闻
        self.sources: List[str] = [main_news.extra.get("source_id", "unknown")]  # 新闻来源
        self.keywords: List[str] = []  # 关键词
        self.created_at = datetime.datetime.now()  # 创建时间
        self.updated_at = self.created_at  # 更新时间
        self.score = 0  # 热度分数
    
    def add_news(self, news: NewsItemModel) -> None:
        """
        添加相关新闻
        """
        self.related_news.append(news)
        source_id = news.extra.get("source_id", "unknown")
        if source_id not in self.sources:
            self.sources.append(source_id)
        self.updated_at = datetime.datetime.now()
        self.calculate_score()
    
    def calculate_score(self) -> None:
        """
        计算热度分数
        基于新闻数量、来源数量、时间衰减等因素
        """
        # 基础分数：相关新闻数量 + 来源数量
        base_score = len(self.related_news) + len(self.sources)
        
        # 时间衰减因子：24小时内的新闻权重更高
        now = datetime.datetime.now()
        time_decay = 1.0
        if self.main_news.published_at:
            hours_diff = (now - self.main_news.published_at).total_seconds() / 3600
            if hours_diff <= 24:
                time_decay = 2.0 - (hours_diff / 24)  # 24小时内线性衰减
        
        # 置顶加成
        top_bonus = 1.5 if self.main_news.is_top else 1.0
        
        # 最终分数
        self.score = base_score * time_decay * top_bonus
    
    def extract_keywords(self, top_k: int = 5) -> List[str]:
        """
        提取关键词
        """
        # 合并所有标题和摘要
        text = self.main_news.title
        if self.main_news.summary:
            text += " " + self.main_news.summary
        
        for news in self.related_news:
            text += " " + news.title
            if news.summary:
                text += " " + news.summary
        
        # 使用jieba提取关键词
        self.keywords = jieba.analyse.extract_tags(text, topK=top_k)
        return self.keywords
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        """
        return {
            "main_news": self.main_news.to_dict(),
            "related_news": [news.to_dict() for news in self.related_news],
            "sources": self.sources,
            "keywords": self.keywords or self.extract_keywords(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "score": self.score,
            "news_count": len(self.related_news) + 1
        }


class NewsAggregator:
    """
    新闻聚合器
    负责聚合相似新闻，生成热门话题
    """
    
    def __init__(self):
        self.clusters: List[NewsCluster] = []
        self.vectorizer = TfidfVectorizer(
            analyzer='word',
            tokenizer=self._tokenize,
            stop_words=self._get_stop_words(),
            max_features=5000
        )
        self.similarity_threshold = 0.6  # 相似度阈值
        self.max_clusters = 100  # 最大聚类数量
        self.last_update_time = 0  # 上次更新时间
    
    def _tokenize(self, text: str) -> List[str]:
        """
        分词
        """
        return jieba.lcut(text)
    
    def _get_stop_words(self) -> List[str]:
        """
        获取停用词
        """
        # 简单的停用词列表，实际应用中可以加载更完整的停用词表
        return ['的', '了', '和', '是', '在', '有', '为', '与', '等', '这', '那', '也', '中', '上', '下']
    
    def _calculate_similarity(self, news1: NewsItemModel, news2: NewsItemModel) -> float:
        """
        计算两条新闻的相似度
        """
        # 合并标题和摘要
        text1 = news1.title
        if news1.summary:
            text1 += " " + news1.summary
        
        text2 = news2.title
        if news2.summary:
            text2 += " " + news2.summary
        
        # 转换为TF-IDF向量
        try:
            tfidf_matrix = self.vectorizer.fit_transform([text1, text2])
            # 计算余弦相似度
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return similarity
        except Exception as e:
            logger.error(f"Error calculating similarity: {str(e)}")
            # 如果计算失败，使用简单的标题比较
            from difflib import SequenceMatcher
            return SequenceMatcher(None, news1.title, news2.title).ratio()
    
    def _find_best_cluster(self, news: NewsItemModel) -> Tuple[Optional[NewsCluster], float]:
        """
        为新闻找到最佳聚类
        返回最佳聚类和相似度
        """
        best_cluster = None
        best_similarity = 0
        
        for cluster in self.clusters:
            similarity = self._calculate_similarity(news, cluster.main_news)
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster
        
        return best_cluster, best_similarity
    
    def add_news(self, news: NewsItemModel) -> None:
        """
        添加新闻到聚合器
        """
        # 查找最佳聚类
        best_cluster, similarity = self._find_best_cluster(news)
        
        # 如果相似度超过阈值，添加到现有聚类
        if best_cluster and similarity >= self.similarity_threshold:
            best_cluster.add_news(news)
            logger.debug(f"Added news to existing cluster: {news.title[:30]}... (similarity: {similarity:.2f})")
        else:
            # 否则创建新聚类
            new_cluster = NewsCluster(news)
            self.clusters.append(new_cluster)
            logger.debug(f"Created new cluster for news: {news.title[:30]}...")
        
        # 如果聚类数量超过最大值，删除得分最低的聚类
        if len(self.clusters) > self.max_clusters:
            self.clusters.sort(key=lambda x: x.score, reverse=True)
            self.clusters = self.clusters[:self.max_clusters]
    
    def add_news_batch(self, news_items: List[NewsItemModel]) -> None:
        """
        批量添加新闻
        """
        for news in news_items:
            self.add_news(news)
    
    def get_hot_topics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取热门话题
        """
        # 计算所有聚类的得分
        for cluster in self.clusters:
            cluster.calculate_score()
        
        # 按得分排序
        self.clusters.sort(key=lambda x: x.score, reverse=True)
        
        # 返回前N个聚类
        return [cluster.to_dict() for cluster in self.clusters[:limit]]
    
    def get_topics_by_category(self, category: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        按分类获取话题
        """
        # 过滤指定分类的聚类
        category_clusters = []
        for cluster in self.clusters:
            if cluster.main_news.extra.get("category") == category:
                category_clusters.append(cluster)
        
        # 按得分排序
        category_clusters.sort(key=lambda x: x.score, reverse=True)
        
        # 返回前N个聚类
        return [cluster.to_dict() for cluster in category_clusters[:limit]]
    
    async def update(self, force: bool = False) -> None:
        """
        更新聚合器
        从所有新闻源获取最新新闻并聚合
        """
        current_time = datetime.datetime.now().timestamp()
        
        # 每小时更新一次，除非强制更新
        if not force and current_time - self.last_update_time < 3600:
            logger.debug("Skipping update, last update was less than 1 hour ago")
            return
        
        # 获取所有新闻
        all_news = await source_manager.fetch_all_news(force_update=force)
        
        # 聚合所有新闻
        for source_id, news_items in all_news.items():
            self.add_news_batch(news_items)
        
        self.last_update_time = current_time
        logger.info(f"Updated aggregator, {len(self.clusters)} clusters")


# 全局单例
aggregator_manager = NewsAggregator() 