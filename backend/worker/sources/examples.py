"""
Example news source configurations for testing
"""
from worker.sources.rss import RSSNewsSource
from worker.sources.rest_api import RESTNewsSource


# Example RSS news sources
cnn_rss = RSSNewsSource(
    source_id="cnn",
    name="CNN",
    feed_url="http://rss.cnn.com/rss/edition.rss",
    category="general",
    country="us",
    language="en",
    logo_url="https://cdn.cnn.com/cnn/.e/img/3.0/global/misc/cnn-logo.png",
    mobile_url_pattern="m.{domain}"
)

bbc_rss = RSSNewsSource(
    source_id="bbc",
    name="BBC News",
    feed_url="http://feeds.bbci.co.uk/news/rss.xml",
    category="general",
    country="gb",
    language="en",
    logo_url="https://news.bbcimg.co.uk/nol/shared/img/bbc_news_120x60.gif",
    mobile_url_pattern="m.{domain}"
)

reuters_rss = RSSNewsSource(
    source_id="reuters",
    name="Reuters",
    feed_url="http://feeds.reuters.com/reuters/topNews",
    category="general",
    country="us",
    language="en",
    logo_url="https://www.reuters.com/pf/resources/images/reuters/logo-vertical-default.svg?d=108",
    mobile_url_pattern="mobile.{domain}"
)

techcrunch_rss = RSSNewsSource(
    source_id="techcrunch",
    name="TechCrunch",
    feed_url="https://techcrunch.com/feed/",
    category="technology",
    country="us",
    language="en",
    logo_url="https://techcrunch.com/wp-content/uploads/2015/02/cropped-cropped-favicon-gradient.png",
    mobile_url_pattern="m.{domain}"
)

# Example REST API news sources
newsapi_top_headlines = RESTNewsSource(
    source_id="newsapi_top",
    name="NewsAPI Top Headlines",
    api_url="https://newsapi.org/v2/top-headlines",
    api_key="YOUR_API_KEY",  # Replace with actual API key
    params={
        "country": "us",
        "pageSize": 100
    },
    category="general",
    country="us",
    language="en",
    logo_url="https://newsapi.org/images/n-logo-border.png"
)

newsapi_tech = RESTNewsSource(
    source_id="newsapi_tech",
    name="NewsAPI Technology",
    api_url="https://newsapi.org/v2/top-headlines",
    api_key="YOUR_API_KEY",  # Replace with actual API key
    params={
        "country": "us",
        "category": "technology",
        "pageSize": 100
    },
    category="technology",
    country="us",
    language="en",
    logo_url="https://newsapi.org/images/n-logo-border.png"
)

# List of example sources
example_sources = [
    cnn_rss,
    bbc_rss,
    reuters_rss,
    techcrunch_rss,
    newsapi_top_headlines,
    newsapi_tech
]


def register_example_sources(registry):
    """
    Register example sources to the registry
    """
    for source in example_sources:
        registry.sources[source.source_id] = source 