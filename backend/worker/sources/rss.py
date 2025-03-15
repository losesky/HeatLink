import datetime
import hashlib
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

from worker.sources.base import NewsSource, NewsItemModel
from worker.utils.http_client import http_client


class RSSNewsSource(NewsSource):
    """
    RSS feed news source adapter
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        feed_url: str,
        update_interval: int = 600,
        cache_ttl: int = 300,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None,
        logo_url: Optional[str] = None,
        content_selector: Optional[str] = None,
        image_selector: Optional[str] = None,
        mobile_url_pattern: Optional[str] = None,
        summary_length: int = 200
    ):
        super().__init__(
            source_id=source_id,
            name=name,
            update_interval=update_interval,
            cache_ttl=cache_ttl,
            category=category,
            country=country,
            language=language
        )
        self.feed_url = feed_url
        self.logo_url = logo_url
        self.content_selector = content_selector
        self.image_selector = image_selector
        self.mobile_url_pattern = mobile_url_pattern
        self.summary_length = summary_length
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        Fetch news from RSS feed
        """
        # Fetch RSS feed content
        response = await http_client.fetch(
            url=self.feed_url,
            method="GET",
            response_type="text",
            cache_ttl=self.cache_ttl
        )
        
        # Parse feed
        feed = feedparser.parse(response)
        
        # Process entries
        news_items = []
        for entry in feed.entries:
            # Generate unique ID
            entry_id = self._generate_id(entry)
            
            # Get published date
            published_at = self._parse_date(entry)
            
            # Get content
            content = self._get_content(entry)
            
            # Get summary
            summary = self._get_summary(entry, content)
            
            # Get image URL
            image_url = self._get_image_url(entry)
            
            # Get mobile URL
            mobile_url = self._get_mobile_url(entry.link)
            
            # Create news item
            news_item = NewsItemModel(
                id=entry_id,
                title=entry.title,
                url=entry.link,
                mobile_url=mobile_url,
                content=content,
                summary=summary,
                image_url=image_url,
                published_at=published_at,
                extra={
                    "author": getattr(entry, "author", None),
                    "tags": [tag.term for tag in getattr(entry, "tags", [])],
                    "source": {
                        "id": self.source_id,
                        "name": self.name,
                        "logo_url": self.logo_url
                    }
                }
            )
            
            news_items.append(news_item)
        
        return news_items
    
    def _generate_id(self, entry: Any) -> str:
        """
        Generate unique ID for entry
        """
        # Use guid if available
        if hasattr(entry, "id"):
            return f"{self.source_id}:{hashlib.md5(entry.id.encode()).hexdigest()}"
        
        # Use link as fallback
        return f"{self.source_id}:{hashlib.md5(entry.link.encode()).hexdigest()}"
    
    def _parse_date(self, entry: Any) -> Optional[datetime.datetime]:
        """
        Parse published date from entry
        """
        # Try different date fields
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if hasattr(entry, date_field):
                time_struct = getattr(entry, date_field)
                if time_struct:
                    return datetime.datetime.fromtimestamp(
                        datetime.datetime(*time_struct[:6]).timestamp(),
                        tz=datetime.timezone.utc
                    )
        
        return None
    
    def _get_content(self, entry: Any) -> Optional[str]:
        """
        Get content from entry
        """
        # Try to get content from entry
        if hasattr(entry, "content"):
            for content in entry.content:
                if content.get("type") == "text/html":
                    return content.value
        
        # Try to get content from summary_detail
        if hasattr(entry, "summary_detail") and entry.summary_detail.get("type") == "text/html":
            return entry.summary_detail.value
        
        # Try to get content from summary
        if hasattr(entry, "summary"):
            return entry.summary
        
        return None
    
    def _get_summary(self, entry: Any, content: Optional[str]) -> Optional[str]:
        """
        Get or generate summary
        """
        # Try to get summary from entry
        if hasattr(entry, "summary"):
            return entry.summary[:self.summary_length] + "..." if len(entry.summary) > self.summary_length else entry.summary
        
        # Generate summary from content
        if content:
            # Remove HTML tags
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            
            # Truncate to summary length
            return text[:self.summary_length] + "..." if len(text) > self.summary_length else text
        
        return None
    
    def _get_image_url(self, entry: Any) -> Optional[str]:
        """
        Get image URL from entry
        """
        # Try to get image from media_content
        if hasattr(entry, "media_content"):
            for media in entry.media_content:
                if media.get("medium") == "image":
                    return media.get("url")
        
        # Try to get image from media_thumbnail
        if hasattr(entry, "media_thumbnail"):
            for thumbnail in entry.media_thumbnail:
                return thumbnail.get("url")
        
        # Try to get image from links
        if hasattr(entry, "links"):
            for link in entry.links:
                if link.get("type", "").startswith("image/"):
                    return link.get("href")
        
        # Try to get image from enclosures
        if hasattr(entry, "enclosures"):
            for enclosure in entry.enclosures:
                if enclosure.get("type", "").startswith("image/"):
                    return enclosure.get("href")
        
        return None
    
    def _get_mobile_url(self, url: str) -> Optional[str]:
        """
        Get mobile URL from regular URL
        """
        if not self.mobile_url_pattern:
            return None
        
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Replace domain with mobile pattern
        mobile_domain = self.mobile_url_pattern.format(domain=domain)
        
        # Create mobile URL
        mobile_url = parsed_url._replace(netloc=mobile_domain).geturl()
        
        return mobile_url 