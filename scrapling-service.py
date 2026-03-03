import os
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from urllib.parse import urljoin, urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize Scrapling fetcher with error handling
fetcher = None
try:
    from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
    # Use StealthyFetcher for better anti-bot protection
    fetcher = StealthyFetcher()
    logger.info("Scrapling StealthyFetcher initialized successfully")
except ImportError as e:
    logger.error(f"Failed to import Scrapling: {e}")
except Exception as e:
    logger.error(f"Error initializing Scrapling Fetcher: {e}")
    logger.error(f"Error type: {type(e).__name__}")
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")

def classify_url(url):
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

def crawl_page(url):
    """Crawl a single page using Scrapling"""
    if not fetcher:
        logger.error("Scrapling fetcher not available")
        return None
        
    try:
        logger.info(f"Crawling: {url}")
        
        # Use the StealthyFetcher instance method
        result = fetcher.fetch(url)
        
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result attributes: {dir(result)}")
        
        if result:
            logger.info(f"Got result from Scrapling")
            
            # Extract content using Scrapling's result object
            title = ""
            description = ""
            content = ""
            links = []
            
            # Use Scrapling's built-in content extraction
            title = getattr(result, 'title', '')
            logger.info(f"Extracted title: {title}")
            
            # Get HTML content
            html_content = getattr(result, 'html', '')
            if html_content:
                content = getattr(result, 'text', '') or html_content
                logger.info(f"Got content, length: {len(content)}")
            
            # Get links from Scrapling
            links = getattr(result, 'links', [])
            logger.info(f"Found {len(links)} links")
            
            # If no links, try to extract from HTML using Scrapling's methods
            if not links and hasattr(result, 'css'):
                try:
                    # Use Scrapling's built-in link extraction
                    found_links = result.css('a::attr(href)')
                    links = [link for link in found_links if link]
                    logger.info(f"Extracted {len(links)} links using css")
                except Exception as e:
                    logger.error(f"Error extracting links: {e}")
                    links = []
            
            # Classify URL
            category = classify_url(url)
            
            page_data = {
                'url': url,
                'title': title,
                'description': description,
                'content': content[:5000],  # Limit content length
                'category': category,
                'links': links[:50],  # Limit number of links
                'status_code': 200,  # Success since we got HTML
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Successfully crawled page: {url}, title: {title}")
            return page_data
        else:
            logger.error(f"Failed to crawl {url}: No result returned")
            return None
            
    except Exception as e:
        logger.error(f"Error crawling {url}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def crawl_site(start_url, max_pages=20, delay_ms=1000):
    """Crawl entire site using Scrapling"""
    logger.info(f"Starting Scrapling crawl of {start_url}, max pages: {max_pages}")
    
    crawled = []
    to_crawl = [start_url]
    seen = set()  # Don't add start_url to seen initially
    base_domain = urlparse(start_url).netloc
    
    logger.info(f"Initial crawl queue: {to_crawl}")
    logger.info(f"Seen URLs: {seen}")
    logger.info(f"Base domain: {base_domain}")
    
    while to_crawl and len(crawled) < max_pages:
        url = to_crawl.pop(0)
        logger.info(f"Processing URL from queue: {url}")
        
        if url in seen:
            logger.info(f"URL already seen, skipping: {url}")
            continue
            
        seen.add(url)  # Add to seen AFTER processing, not before
        logger.info(f"Added URL to seen: {url}")
        
        logger.info(f"About to call crawl_page for: {url}")
        page_data = crawl_page(url)
        logger.info(f"crawl_page returned: {page_data is not None}")
        
        if page_data:
            crawled.append(page_data)
            logger.info(f"Successfully crawled page: {url}, total crawled: {len(crawled)}")
            
            # Add new links to crawl queue
            for link in page_data['links']:
                # Normalize URL and check if it belongs to same domain
                if link.startswith('http') and base_domain in link:
                    if link not in seen and len(to_crawl) + len(crawled) < max_pages:
                        to_crawl.append(link)
                        logger.info(f"Added absolute link to queue: {link}")
                elif link.startswith('/'):
                    # Convert relative URLs to absolute
                    absolute_url = urljoin(start_url, link)
                    if absolute_url not in seen and len(to_crawl) + len(crawled) < max_pages:
                        to_crawl.append(absolute_url)
                        logger.info(f"Added relative link to queue: {absolute_url}")
            
            # Polite delay between requests
            if delay_ms > 0 and len(crawled) < max_pages:
                logger.info(f"Waiting {delay_ms}ms before next request")
                time.sleep(delay_ms / 1000)
        else:
            logger.error(f"Failed to crawl page: {url}")
    
    logger.info(f"Scrapling crawl completed: {len(crawled)} pages crawled")
    return crawled

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'framework': 'scrapling',
        'fetcher_available': fetcher is not None
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
        },
        'fetcher_available': fetcher is not None
    })

@app.route('/crawl', methods=['POST'])
def start_crawl():
    try:
        if not fetcher:
            return jsonify({'error': 'Scrapling fetcher not available'}), 500
            
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        url = data['url']
        max_pages = data.get('maxPages', 20)  # Note: maxPages not max_page
        delay_ms = data.get('delayMs', 1000)
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        # Run crawl
        pages = crawl_site(url, max_pages, delay_ms)
        
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
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Scrapling fetcher available: {fetcher is not None}")
    
    # Ensure the app binds to 0.0.0.0 for Railway
    app.run(host='0.0.0.0', port=port, debug=debug)
