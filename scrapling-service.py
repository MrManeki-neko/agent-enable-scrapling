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

# Initialize Scrapling - Use Fetcher class (faster than StealthyFetcher)
try:
    from scrapling.fetchers import Fetcher
    logger.info("Scrapling Fetcher imported successfully")
    fetcher_available = True
except ImportError as e:
    logger.error(f"Failed to import Scrapling: {e}")
    fetcher_available = False
except Exception as e:
    logger.error(f"Error importing Scrapling: {e}")
    fetcher_available = False

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
    """Crawl a single page using Scrapling with native markdown conversion"""
    if not fetcher_available:
        logger.error("Scrapling not available")
        return None
        
    try:
        logger.info(f"Crawling: {url}")
        
        # Use Fetcher.get() static method (recommended approach)
        page = Fetcher.get(url, follow_redirects=True)
        
        if not page:
            logger.error(f"Failed to fetch {url}")
            return None
        
        logger.info(f"Successfully fetched page")
        
        # Extract metadata
        title = ""
        description = ""
        
        try:
            title_elem = page.css('title::text')
            if title_elem:
                title = title_elem[0].get() if hasattr(title_elem[0], 'get') else str(title_elem[0])
                title = title.strip()
        except:
            pass
        
        try:
            desc_elem = page.css('meta[name="description"]::attr(content)')
            if not desc_elem:
                desc_elem = page.css('meta[property="og:description"]::attr(content)')
            if desc_elem:
                description = desc_elem[0].get() if hasattr(desc_elem[0], 'get') else str(desc_elem[0])
                description = description.strip()
        except:
            pass
        
        # Use Scrapling's native markdown conversion
        markdown_content = ""
        try:
            # Get markdown representation of the page
            # Scrapling can convert HTML to markdown natively
            markdown_content = page.markdown if hasattr(page, 'markdown') else ""
            
            # If no native markdown, fallback to text content
            if not markdown_content:
                text_content = page.text if hasattr(page, 'text') else ""
                if text_content:
                    markdown_content = f"# {title}\n\n{text_content}"
        except Exception as e:
            logger.error(f"Error getting markdown: {e}")
            # Final fallback
            try:
                text_content = page.text if hasattr(page, 'text') else ""
                markdown_content = f"# {title}\n\n{text_content}" if text_content else ""
            except:
                markdown_content = ""
        
        # Extract links
        links = []
        try:
            link_elements = page.css('a::attr(href)')
            links = [link.get() if hasattr(link, 'get') else str(link) for link in link_elements if link]
            links = [link for link in links if link and isinstance(link, str)][:50]
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
        
        # Classify URL
        category = classify_url(url)
        
        logger.info(f"Extracted - Title: {title[:50]}, Markdown length: {len(markdown_content)}, Links: {len(links)}")
        
        return {
            'url': url,
            'title': title,
            'description': description,
            'markdown': markdown_content[:10000],  # Limit to 10KB
            'category': category,
            'links': links,
            'status_code': 200,
            'timestamp': datetime.now().isoformat()
        }
            
    except Exception as e:
        logger.error(f"Error crawling {url}: {str(e)}")
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
        'fetcher_available': fetcher_available
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
        'fetcher_available': fetcher_available
    })

@app.route('/crawl', methods=['POST'])
def start_crawl():
    try:
        if not fetcher_available:
            return jsonify({'error': 'Scrapling not available'}), 500
            
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        url = data['url']
        max_pages = min(data.get('maxPages', 10), 10)  # Max 10 pages
        delay_ms = data.get('delayMs', 300)  # Reduced to 300ms
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400
        
        logger.info(f"Starting crawl: {url}, max_pages: {max_pages}, delay_ms: {delay_ms}")
        
        # Run crawl (removed timeout handler as it doesn't work properly with threading)
        pages = crawl_site(url, max_pages, delay_ms)
        
        # Convert to Firecrawl format for compatibility
        firecrawl_results = []
        for page in pages:
            result = {
                'url': page['url'],
                'markdown': page['markdown'],  # Use native markdown from Scrapling
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
        
        logger.info(f"Crawl completed: {len(firecrawl_results)} pages")
        
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
    logger.info(f"Scrapling fetcher available: {fetcher_available}")
    
    # Ensure the app binds to 0.0.0.0 for Railway
    app.run(host='0.0.0.0', port=port, debug=debug)
