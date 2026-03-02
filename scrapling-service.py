"""
AgentEnable Scrapling Service
Full site crawling with polite rate limiting
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from scrapling.spiders import Spider, Response
import os
import asyncio
import logging
from urllib.parse import urlparse
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for API access

class PoliteSiteCrawler(Spider):
    """Polite crawler with rate limiting and smart filtering"""
    
    def __init__(self, start_url, max_pages=20, delay_ms=1000, respect_robots=True):
        self.start_urls = [start_url]
        self.max_pages = max_pages
        self.delay_ms = delay_ms
        self.respect_robots = respect_robots
        self.pages_crawled = 0
        self.base_domain = urlparse(start_url).netloc
        self.last_request_time = 0
    
    async def parse(self, response: Response):
        """Parse individual pages with rate limiting"""
        if self.pages_crawled >= self.max_pages:
            return
            
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < (self.delay_ms / 1000):
            await asyncio.sleep((self.delay_ms / 1000) - time_since_last)
        
        self.last_request_time = time.time()
        
        # Extract content
        yield {
            "url": response.url,
            "markdown": response.markdown or '',
            "html": response.html or '',
            "title": response.css('title::text').get() or '',
            "description": response.css('meta[name="description"]::attr(content)').get() or '',
            "links": response.css('a::attr(href)').getall() or [],
            "timestamp": time.time()
        }
        
        self.pages_crawled += 1
        logger.info(f"Crawled page {self.pages_crawled}/{self.max_pages}: {response.url}")
        
        # Follow links to same domain
        for link in response.css('a::attr(href)').getall() or []:
            if self.pages_crawled < self.max_pages:
                # Convert relative URLs to absolute
                if link.startswith('/'):
                    link = f"https://{self.base_domain}{link}"
                
                # Only follow same-domain links
                if urlparse(link).netloc == self.base_domain:
                    yield response.follow(link, self.parse)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "agent-enable-scrapling",
        "version": "1.0.0",
        "timestamp": time.time()
    })

@app.route('/crawl', methods=['POST'])
def crawl():
    """Main crawling endpoint"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        url = data.get('url')
        max_pages = data.get('maxPages', 20)
        delay_ms = data.get('delayMs', 1000)
        respect_robots = data.get('respectRobotsTxt', True)
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({"error": "Invalid URL format"}), 400
        
        logger.info(f"Starting crawl: {url} (max_pages={max_pages}, delay={delay_ms}ms)")
        
        # Create and run crawler
        spider = PoliteSiteCrawler(url, max_pages, delay_ms, respect_robots)
        result = spider.start()
        
        pages = list(result.items)
        
        logger.info(f"Crawl completed: {len(pages)} pages found")
        
        return jsonify({
            "success": True,
            "pages": pages,
            "total": len(pages),
            "settings": {
                "url": url,
                "maxPages": max_pages,
                "delayMs": delay_ms,
                "respectRobotsTxt": respect_robots
            }
        })
        
    except Exception as e:
        logger.error(f"Crawl error: {str(e)}")
        return jsonify({
            "error": f"Crawl failed: {str(e)}",
            "success": False
        }), 500

@app.route('/info', methods=['GET'])
def info():
    """Service information"""
    return jsonify({
        "service": "AgentEnable Scrapling Service",
        "version": "1.0.0",
        "description": "Full site crawling with polite rate limiting",
        "endpoints": {
            "health": "GET /health",
            "crawl": "POST /crawl",
            "info": "GET /info"
        },
        "usage": {
            "crawl": {
                "method": "POST",
                "body": {
                    "url": "string (required)",
                    "maxPages": "number (optional, default: 20)",
                    "delayMs": "number (optional, default: 1000)",
                    "respectRobotsTxt": "boolean (optional, default: true)"
                }
            }
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting Scrapling service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)