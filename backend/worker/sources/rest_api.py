import datetime
import hashlib
import json
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from worker.sources.base import NewsSource, NewsItemModel
from worker.utils.http_client import http_client


class RESTNewsSource(NewsSource):
    """
    REST API news source adapter
    """
    
    def __init__(
        self,
        source_id: str,
        name: str,
        api_url: str,
        api_key: Optional[str] = None,
        update_interval: int = 600,
        cache_ttl: int = 300,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None,
        logo_url: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        items_path: str = "articles",
        id_field: Optional[str] = None,
        title_field: str = "title",
        url_field: str = "url",
        content_field: Optional[str] = "content",
        summary_field: Optional[str] = "description",
        image_field: Optional[str] = "urlToImage",
        date_field: Optional[str] = "publishedAt",
        date_format: Optional[str] = None,
        mobile_url_pattern: Optional[str] = None,
        summary_length: int = 200,
        custom_parser: Optional[Callable[[Dict[str, Any]], List[NewsItemModel]]] = None
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
        self.api_url = api_url
        self.api_key = api_key
        self.logo_url = logo_url
        self.params = params or {}
        self.headers = headers or {}
        self.items_path = items_path
        self.id_field = id_field
        self.title_field = title_field
        self.url_field = url_field
        self.content_field = content_field
        self.summary_field = summary_field
        self.image_field = image_field
        self.date_field = date_field
        self.date_format = date_format
        self.mobile_url_pattern = mobile_url_pattern
        self.summary_length = summary_length
        self.custom_parser = custom_parser
        
        # Add API key to headers or params if provided
        if api_key:
            if "apiKey" in self.params:
                self.params["apiKey"] = api_key
            elif "api_key" in self.params:
                self.params["api_key"] = api_key
            elif "key" in self.params:
                self.params["key"] = api_key
            elif "apikey" in self.params:
                self.params["apikey"] = api_key
            elif "x-api-key" in self.headers:
                self.headers["x-api-key"] = api_key
            elif "Authorization" in self.headers:
                self.headers["Authorization"] = f"Bearer {api_key}"
            else:
                # Default to adding as a query parameter
                self.params["apiKey"] = api_key
    
    async def fetch(self) -> List[NewsItemModel]:
        """
        Fetch news from REST API
        """
        # Fetch API response
        response = await http_client.fetch(
            url=self.api_url,
            method="GET",
            params=self.params,
            headers=self.headers,
            response_type="json",
            cache_ttl=self.cache_ttl
        )
        
        # Use custom parser if provided
        if self.custom_parser:
            return self.custom_parser(response)
        
        # Get items from response
        items = self._get_items_from_response(response)
        
        # Process items
        news_items = []
        for item in items:
            # Generate unique ID
            item_id = self._generate_id(item)
            
            # Get title and URL (required fields)
            title = self._get_field_value(item, self.title_field)
            url = self._get_field_value(item, self.url_field)
            
            if not title or not url:
                continue
            
            # Get published date
            published_at = self._parse_date(item)
            
            # Get content
            content = self._get_content(item)
            
            # Get summary
            summary = self._get_summary(item, content)
            
            # Get image URL
            image_url = self._get_image_url(item)
            
            # Get mobile URL
            mobile_url = self._get_mobile_url(url)
            
            # Create news item
            news_item = NewsItemModel(
                id=item_id,
                title=title,
                url=url,
                mobile_url=mobile_url,
                content=content,
                summary=summary,
                image_url=image_url,
                published_at=published_at,
                extra={
                    "author": self._get_field_value(item, "author"),
                    "source": {
                        "id": self.source_id,
                        "name": self.name,
                        "logo_url": self.logo_url
                    },
                    "raw_item": item
                }
            )
            
            news_items.append(news_item)
        
        return news_items
    
    def _get_items_from_response(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get items from response using items_path
        """
        if not self.items_path:
            # If no items_path is provided, assume the response is a list of items
            if isinstance(response, list):
                return response
            # If response is a dict, return it as a single item list
            return [response]
        
        # Navigate through the response using items_path
        current = response
        for path_part in self.items_path.split('.'):
            if isinstance(current, dict) and path_part in current:
                current = current[path_part]
            else:
                return []
        
        # Ensure we have a list of items
        if isinstance(current, list):
            return current
        elif isinstance(current, dict):
            return [current]
        
        return []
    
    def _generate_id(self, item: Dict[str, Any]) -> str:
        """
        Generate unique ID for item
        """
        # Use specified ID field if available
        if self.id_field and self.id_field in item:
            return f"{self.source_id}:{hashlib.md5(str(item[self.id_field]).encode()).hexdigest()}"
        
        # Use URL as fallback
        url = self._get_field_value(item, self.url_field)
        if url:
            return f"{self.source_id}:{hashlib.md5(url.encode()).hexdigest()}"
        
        # Use entire item as last resort
        return f"{self.source_id}:{hashlib.md5(json.dumps(item, sort_keys=True).encode()).hexdigest()}"
    
    def _get_field_value(self, item: Dict[str, Any], field: Optional[str]) -> Optional[str]:
        """
        Get field value from item, supporting nested fields with dot notation
        """
        if not field:
            return None
        
        # Handle nested fields with dot notation
        current = item
        for path_part in field.split('.'):
            if isinstance(current, dict) and path_part in current:
                current = current[path_part]
            else:
                return None
        
        return str(current) if current is not None else None
    
    def _parse_date(self, item: Dict[str, Any]) -> Optional[datetime.datetime]:
        """
        Parse published date from item
        """
        if not self.date_field:
            return None
        
        date_str = self._get_field_value(item, self.date_field)
        if not date_str:
            return None
        
        try:
            if self.date_format:
                # Parse using specified format
                return datetime.datetime.strptime(date_str, self.date_format)
            else:
                # Try ISO format
                return datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            try:
                # Try RFC 1123 format (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
                import email.utils
                parsed_date = email.utils.parsedate_to_datetime(date_str)
                return parsed_date
            except (ValueError, TypeError):
                return None
    
    def _get_content(self, item: Dict[str, Any]) -> Optional[str]:
        """
        Get content from item
        """
        if not self.content_field:
            return None
        
        return self._get_field_value(item, self.content_field)
    
    def _get_summary(self, item: Dict[str, Any], content: Optional[str]) -> Optional[str]:
        """
        Get or generate summary
        """
        # Try to get summary from item
        if self.summary_field:
            summary = self._get_field_value(item, self.summary_field)
            if summary:
                return summary[:self.summary_length] + "..." if len(summary) > self.summary_length else summary
        
        # Generate summary from content
        if content:
            # Remove HTML tags
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            
            # Truncate to summary length
            return text[:self.summary_length] + "..." if len(text) > self.summary_length else text
        
        return None
    
    def _get_image_url(self, item: Dict[str, Any]) -> Optional[str]:
        """
        Get image URL from item
        """
        if not self.image_field:
            return None
        
        return self._get_field_value(item, self.image_field)
    
    def _get_mobile_url(self, url: str) -> Optional[str]:
        """
        Get mobile URL from regular URL
        """
        if not self.mobile_url_pattern or not url:
            return None
        
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Replace domain with mobile pattern
        mobile_domain = self.mobile_url_pattern.format(domain=domain)
        
        # Create mobile URL
        mobile_url = parsed_url._replace(netloc=mobile_domain).geturl()
        
        return mobile_url 