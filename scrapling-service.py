import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from scrapling import Fetcher, StealthyFetcher
from scrapling.tools import get_async_engine
import asyncio
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScraplingCrawler:
    def __init__(self):
        self.fetcher = StealthyFetcher()
        
    def _classify_url(self, url):
        """Classify URL based on path patterns"""
        path = url.split('/')[-1].lower() if '/' in url else ''
        
        patterns = {
            'contact': ['contact', 'about', 'team', 'staff'],
            'services': ['service', 'services', 'products', 'solutions'],
            'pricing': ['pricing', 'price', 'rates', 'fees', 'cost'],
            'faq': ['faq', 'frequently-asked-questions', 'help', 'support'],
            'reviews': ['review', 'reviews', 'testimonial', 'testimonials'],
            'blog': ['blog', 'news', 'article', 'articles'],
            'home': ['home', 'index', '']
        }
        
        for category, keywords in patterns.items():
            if any(keyword in path for keyword in keywords):
                return category
        
        return 'other'
    
    async def crawl_page(self, url):
        """Crawl a single page using Scrapling"""
        try:
            logger.info(f"Crawling: {url}")
            result = self.fetcher.get(url)
            
            if result.status_code == 200:
                # Extract content using Scrapling's built-in methods
                title = result.soup.title.string if result.soup.title else ''
                
                # Get meta description
                meta_desc = result.soup.find('meta', attrs={'name': 'description'})
                description = meta_desc.get('content', '') if meta_desc else ''
                
                # Get clean text content
                for script in result.soup(["script", "style"]):
                    script.decompose()
                content = result.soup.get_text()
                content = ' '.join(content.split())  # Clean whitespace
                
                # Classify URL
                category = self._classify_url(url)
                
                # Extract links
                links = []
                for link in result.soup.find_all('a', href=True):
                    href = link['href']
                    if href.startswith('http') and url.split('/')[2] in href:
                        links.append(href)
                
                return {
                    'url': url,
                    'title': title,
                    'description': description,
                    'content': content[:5000],  # Limit content length
                    'category': category,
                    'links': links[:50],  # Limit number of links
                    'status_code': result.status_code,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                logger.error(f"Failed to crawl {url}: HTTP {result.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error crawling {url}: {str(e)}")
            return None
    
    async def crawl_site(self, start_url, max_pages=20):
        """Crawl entire site using Scrapling"""
        logger.info(f"Starting Scrapling crawl of {start_url}, max pages: {max_pages}")
        
        crawled = []
        to_crawl = [start_url]
        seen = set([start_url])
        
        while to_crawl and len(crawled) < max_pages:
            # Process multiple pages concurrently
            batch_size = min(3, len(to_crawl), max_pages - len(crawled))
            current_batch = to_crawl[:batch_size]
            to_crawl = to_crawl[batch_size:]
            
            # Crawl batch concurrently
            tasks = [self.crawl_page(url) for url in current_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result:
                    crawled.append(result)
                    
                    # Add new links to crawl queue
                    for link in result['links']:
                        if link not in seen and len(to_crawl) + len(crawled) < max_pages:
                            to_crawl.append(link)
                            seen.add(link)
        
        logger.info(f"Scrapling crawl completed: {len(crawled)} pages crawled")
        return crawled

# Initialize crawler
crawler = ScraplingCrawler()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'framework': 'scrapling'
    })

@app.route('/info', methods=['GET'])
def service_info():
    return jsonify({
        'service': 'AgentEnable Scrapling Service',
        'version': '1.0.0',
        'framework': 'scrapling',
        'description': 'Web crawling service using Scrapling framework',
        'endpoints': {
            '/health': 'Health check',
            '/info': 'Service information',
            '/crawl': 'POST - Start crawling'
        }
    })

@app.route('/crawl', methods=['POST'])
def start_crawl():
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        url = data['url']
        max_pages = data.get('max_pages', 20)
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Run async crawl
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            pages = loop.run_until_complete(crawler.crawl_site(url, max_pages))
        finally:
            loop.close()
        
        # Convert to Firecrawl format for compatibility
        firecrawl_results = []
        for page in pages:
            result = {
                'url': page['url'],
                'markdown': f"# {page['title']}\n\n{page['content']}",
                'html': '',  # Not including HTML to save space
                'metadata': {
                    'title': page['title'],
                    'description': page['description'],
                    'sourceURL': page['url'],
                    'urlCategory': page['category'],
                    'urlCategoryConfidence': 0.8,
                    'statusCode': page['status_code'],
                    'timestamp': page['timestamp']
                }
            }
            firecrawl_results.append(result)
        
        return jsonify({
            'success': True,
            'results': firecrawl_results,
            'total': len(firecrawl_results),
            'crawled_url': url,
            'framework': 'scrapling'
        })
        
    except Exception as e:
        logger.error(f"Crawl error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting Scrapling service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
