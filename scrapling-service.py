import asyncio
import os
from collections import deque
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

# Verify FetcherSession is importable at startup
try:
    from scrapling.fetchers import FetcherSession
    logger.info("Scrapling FetcherSession imported successfully")
    fetcher_available = True
except Exception as e:
    logger.error(f"Failed to import Scrapling FetcherSession: {e}")
    fetcher_available = False


def classify_url(url):
    """Classify URL based on path patterns."""
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


def _parse_page(page, url):
    """Extract title, description, markdown, and links from a Scrapling page object."""
    title = ""
    description = ""

    try:
        title_elem = page.css('title::text')
        if title_elem:
            title = title_elem[0].get() if hasattr(title_elem[0], 'get') else str(title_elem[0])
            title = title.strip()
    except Exception:
        pass

    try:
        desc_elem = page.css('meta[name="description"]::attr(content)')
        if not desc_elem:
            desc_elem = page.css('meta[property="og:description"]::attr(content)')
        if desc_elem:
            description = desc_elem[0].get() if hasattr(desc_elem[0], 'get') else str(desc_elem[0])
            description = description.strip()
    except Exception:
        pass

    text_content = ""
    try:
        text_content = page.get_all_text(strip=True, ignore_tags=('script', 'style', 'nav', 'header', 'footer'))
        text_content = str(text_content) if text_content else ""
    except Exception as e:
        logger.error(f"Error extracting text from {url}: {e}")

    markdown_content = ""
    if text_content:
        markdown_content = f"# {title}\n\n"
        if description:
            markdown_content += f"{description}\n\n"
        markdown_content += text_content
    else:
        logger.warning(f"No text content extracted for {url}")

    links = []
    try:
        link_elements = page.css('a::attr(href)')
        links = [lnk.get() if hasattr(lnk, 'get') else str(lnk) for lnk in link_elements if lnk]
        links = [lnk for lnk in links if lnk and isinstance(lnk, str)][:50]
    except Exception as e:
        logger.error(f"Error extracting links from {url}: {e}")

    return title, description, markdown_content, links


async def crawl_page(session, url):
    """
    Fetch and parse a single page using the shared FetcherSession.
    The session keeps the underlying HTTP connection alive across all
    concurrent calls, giving the ~10x speed improvement noted in the
    Scrapling docs versus creating a new session per request.
    """
    try:
        logger.info(f"Fetching: {url}")

        # asyncio.wait_for enforces a hard per-page timeout
        page = await asyncio.wait_for(
            session.get(url, follow_redirects=True),
            timeout=15
        )

        if not page:
            logger.warning(f"No response for {url}")
            return None

        title, description, markdown_content, links = _parse_page(page, url)

        logger.info(f"Done: {url} — title={title[:40]!r}, chars={len(markdown_content)}, links={len(links)}")

        return {
            'url': url,
            'title': title,
            'description': description,
            'markdown': markdown_content[:10000],
            'category': classify_url(url),
            'links': links,
            'status_code': 200,
            'timestamp': datetime.now().isoformat()
        }

    except asyncio.TimeoutError:
        logger.error(f"Timeout (15s) fetching {url}")
        return None
    except Exception as e:
        logger.error(f"Error crawling {url}: {e}")
        return None


async def crawl_site(start_url, max_pages=10):
    """
    Two-phase async crawl using a single shared FetcherSession:

      Phase 1 — await the start page to discover links.
      Phase 2 — await all discovered pages simultaneously via asyncio.gather().

    A single FetcherSession is opened for the entire crawl so every
    concurrent request reuses the same HTTP connection pool — no
    re-handshaking, no repeated TLS negotiation.
    """
    logger.info(f"Starting async crawl: {start_url}, max_pages={max_pages}")
    base_domain = urlparse(start_url).netloc

    async with FetcherSession(retries=2) as session:

        # --- Phase 1: fetch the entry page to discover links ---
        first_page = await crawl_page(session, start_url)
        if not first_page:
            logger.error("Failed to fetch start URL — aborting crawl")
            return []

        results = [first_page]
        seen = {start_url}

        # Build the list of candidate URLs using a deque (O(1) pops)
        queue = deque()
        for link in first_page['links']:
            if len(queue) + 1 >= max_pages:
                break
            if link.startswith('http') and base_domain in link and link not in seen:
                queue.append(link)
                seen.add(link)
            elif link.startswith('/'):
                abs_url = urljoin(start_url, link)
                if abs_url not in seen:
                    queue.append(abs_url)
                    seen.add(abs_url)

        urls_to_crawl = list(queue)[:max_pages - 1]
        logger.info(f"Discovered {len(urls_to_crawl)} URLs — firing asyncio.gather()")

        # --- Phase 2: fetch all discovered pages concurrently ---
        if urls_to_crawl:
            # return_exceptions=True means one failed page never cancels the rest
            page_results = await asyncio.gather(
                *[crawl_page(session, url) for url in urls_to_crawl],
                return_exceptions=True
            )
            for item in page_results:
                if isinstance(item, Exception):
                    logger.error(f"Page fetch raised: {item}")
                elif item is not None:
                    results.append(item)

    logger.info(f"Crawl complete: {len(results)} pages returned")
    return results


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '3.0.0',
        'framework': 'scrapling',
        'fetcher_available': fetcher_available
    })


@app.route('/info', methods=['GET'])
def service_info():
    return jsonify({
        'service': 'AgentEnable Scrapling Service',
        'version': '3.0.0',
        'framework': 'scrapling',
        'description': 'Web crawling service using Scrapling FetcherSession (async)',
        'endpoints': {
            '/health': 'Health check',
            '/info': 'Service information',
            '/crawl': 'POST - Crawl a site following links',
            '/scrape-batch': 'POST - Scrape a list of specific URLs in one session'
        },
        'fetcher_available': fetcher_available
    })


@app.route('/crawl', methods=['POST'])
async def start_crawl():
    """
    Async Flask route — requires flask[async] (asgiref) to be installed.
    Flask runs this coroutine via asgiref so gunicorn gthread workers
    continue to handle multiple simultaneous callers without change.
    """
    try:
        if not fetcher_available:
            return jsonify({'error': 'Scrapling not available'}), 500

        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400

        url = data['url']
        max_pages = min(data.get('maxPages', 10), 10)

        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'Invalid URL format'}), 400

        logger.info(f"Crawl request: url={url}, max_pages={max_pages}")

        # delayMs accepted for backward compatibility but intentionally ignored
        pages = await crawl_site(url, max_pages)

        # Return results in Firecrawl-compatible format
        firecrawl_results = [
            {
                'url': page['url'],
                'markdown': page['markdown'],
                'html': '',
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
            for page in pages
        ]

        logger.info(f"Returning {len(firecrawl_results)} pages to caller")

        return jsonify({
            'success': True,
            'results': firecrawl_results,
            'total': len(firecrawl_results),
            'crawled_url': url,
            'framework': 'scrapling'
        })

    except Exception as e:
        logger.error(f"Crawl error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/scrape-batch', methods=['POST'])
async def scrape_batch():
    """
    Scrape a specific list of URLs using a single shared FetcherSession.

    All URLs are fetched concurrently via asyncio.gather() — one TLS handshake,
    one connection pool, maximum reuse. This is the fast path for targeted
    scraping where the URLs are already known (e.g. from a sitemap).

    Request body:
      {
        "urls": ["https://example.com/page1", "https://example.com/page2", ...],
        "timeout": 20   // optional per-page timeout in seconds, default 20
      }

    Response mirrors /crawl format so the client needs no special handling.
    """
    try:
        if not fetcher_available:
            return jsonify({'error': 'Scrapling not available'}), 500

        data = request.get_json()
        if not data or 'urls' not in data:
            return jsonify({'error': 'urls array is required'}), 400

        urls = data['urls']
        if not isinstance(urls, list) or len(urls) == 0:
            return jsonify({'error': 'urls must be a non-empty array'}), 400

        per_page_timeout = min(int(data.get('timeout', 20)), 60)

        valid_urls = [u for u in urls if isinstance(u, str) and u.startswith(('http://', 'https://'))]
        if not valid_urls:
            return jsonify({'error': 'No valid URLs provided'}), 400

        logger.info(f"Batch scrape: {len(valid_urls)} URLs, timeout={per_page_timeout}s each")

        async def fetch_one(session, url):
            try:
                page = await asyncio.wait_for(
                    session.get(url, follow_redirects=True),
                    timeout=per_page_timeout
                )
                if not page:
                    return None
                title, description, markdown_content, _ = _parse_page(page, url)
                return {
                    'url': url,
                    'title': title,
                    'description': description,
                    'markdown': markdown_content[:10000],
                    'category': classify_url(url),
                    'status_code': 200,
                    'timestamp': datetime.now().isoformat()
                }
            except asyncio.TimeoutError:
                logger.error(f"Timeout ({per_page_timeout}s) fetching {url}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

        async with FetcherSession(retries=2) as session:
            raw_results = await asyncio.gather(
                *[fetch_one(session, url) for url in valid_urls],
                return_exceptions=True
            )

        pages = []
        for item in raw_results:
            if isinstance(item, Exception):
                logger.error(f"Batch page raised: {item}")
            elif item is not None:
                pages.append(item)

        firecrawl_results = [
            {
                'url': page['url'],
                'markdown': page['markdown'],
                'html': '',
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
            for page in pages
        ]

        logger.info(f"Batch scrape complete: {len(firecrawl_results)}/{len(valid_urls)} pages returned")

        return jsonify({
            'success': True,
            'results': firecrawl_results,
            'total': len(firecrawl_results),
            'framework': 'scrapling'
        })

    except Exception as e:
        logger.error(f"Batch scrape error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Local development only — production uses gunicorn (see gunicorn.conf.py)
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    logger.info(f"Dev server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
