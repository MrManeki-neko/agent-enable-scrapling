"""
AgentEnable Scrapling Service
Full site crawling with polite rate limiting
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
from urllib.parse import urlparse, urljoin
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

def extract_links(html, base_url):
    """Extract links from HTML"""
    # Simple regex to find href attributes
    links = re.findall(r'href=[\'"]?([^\'" >]+)', html)
    absolute_links = []
    
    for link in links:
        if link.startswith('http'):
            absolute_links.append(link)
        elif link.startswith('/'):
            absolute_links.append(urljoin(base_url, link))
        elif not link.startswith('#'):
            absolute_links.append(urljoin(base_url, link))
    
    return absolute_links

def extract_title(html):
    """Extract title from HTML"""
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return title_match.group(1).strip() if title_match else ''

def extract_description(html):
    """Extract description from HTML"""
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    return desc_match.group(1).strip() if desc_match else ''

def html_to_markdown(html):
    """Convert basic HTML to markdown"""
    # Simple conversion - you can enhance this
    import re
    
    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE | re.DOTALL)
    
    # Convert basic tags
    html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<[^>]+>', '', html)  # Remove remaining tags
    
    # Clean up whitespace
    return re.sub(r'\n\s*\n\s*\n', '\n\n', html).strip()

class SimpleCrawler:
    """Simple web crawler with rate limiting"""
    
    def __init__(self, start_url, max_pages=20, delay_ms=1000):
        self.start_url = start_url
        self.max_pages = max_pages
        self.delay_ms = delay_ms
        self.pages_crawled = 0
        self.base_domain = urlparse(start_url).netloc
        self.visited_urls = set()
        self.last_request_time = 0
    
    def crawl(self):
        """Crawl the website"""
        results = []
        urls_to_visit = [self.start_url]
        
        while urls_to_visit and self.pages_crawled < self.max_pages:
            url = urls_to_visit.pop(0)
            
            if url in self.visited_urls:
                continue
                
            # Rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < (self.delay_ms / 1000):
                time.sleep((self.delay_ms / 1000) - time_since_last)
            
            self.last_request_time = time.time()
            
            try:
                logger.info(f"Crawling page {self.pages_crawled + 1}/{self.max_pages}: {url}")
                
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'AgentEnable Scrapling Service 1.0'
                })
                
                if response.status_code == 200:
                    html = response.text
                    markdown = html_to_markdown(html)
                    title = extract_title(html)
                    description = extract_description(html)
                    links = extract_links(html, url)
                    
                    # Filter links to same domain
                    same_domain_links = [
                        link for link in links 
                        if urlparse(link).netloc == self.base_domain
                    ]
                    
                    result = {
                        "url": url,
                        "markdown": markdown,
                        "html": html,
                        "title": title,
                        "description": description,
                        "links": same_domain_links,
                        "timestamp": time.time()
                    }
                    
                    results.append(result)
                    self.visited_urls.add(url)
                    self.pages_crawled += 1
                    
                    # Add new links to visit
                    for link in same_domain_links:
                        if link not in self.visited_urls and link not in urls_to_visit:
                            urls_to_visit.append(link)
                            
                else:
                    logger.warning(f"Failed to fetch {url}: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error crawling {url}: {str(e)}")
        
        return results

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
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({"error": "Invalid URL format"}), 400
        
        logger.info(f"Starting crawl: {url} (max_pages={max_pages}, delay={delay_ms}ms)")
        
        # Create and run crawler
        crawler = SimpleCrawler(url, max_pages, delay_ms)
        pages = crawler.crawl()
        
        logger.info(f"Crawl completed: {len(pages)} pages found")
        
        return jsonify({
            "success": True,
            "pages": pages,
            "total": len(pages),
            "settings": {
                "url": url,
                "maxPages": max_pages,
                "delayMs": delay_ms
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
                    "delayMs": "number (optional, default: 1000)"
                }
            }
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting Scrapling service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
