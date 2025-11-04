"""Simple crawler for An Phat (store máy tính An Phát) product pages.

Features:
- Crawl a category or list page to collect product links
- Parse product pages for: name, price, specs (key/value when available), product url, image url
- Save results to JSON or CSV

Notes:
- The site structure may change; adjust CSS selectors in `find_product_links` and
  `parse_product_page` if results are incomplete.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

LOG = logging.getLogger(__name__)

# Default site/category to crawl when no --category provided
DEFAULT_CATEGORY = "https://www.anphatpc.com.vn/may-tinh-xach-tay-laptop.html"


@dataclass
class Product:
	name: str
	price: Optional[int]
	price_raw: Optional[str]
	specs: Dict[str, str]
	# Normalized feature fields requested by user
	features: Dict[str, Optional[str]]
	url: str
	image: Optional[str]


def create_session(retries: int = 3, backoff_factor: float = 0.3) -> requests.Session:
	s = requests.Session()
	retries = Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=(500, 502, 503, 504))
	s.mount("https://", HTTPAdapter(max_retries=retries))
	s.mount("http://", HTTPAdapter(max_retries=retries))
	s.headers.update({
		"User-Agent": "Mozilla/5.0 (compatible; AP-Crawler/1.0; +https://example.local)"
	})
	return s


def to_int_price(text: Optional[str]) -> Optional[int]:
	if not text:
		return None
	# extract digits, remove thousand separators and currency symbols
	m = re.findall(r"[0-9]+", text.replace('.', '').replace(',', ''))
	if not m:
		return None
	try:
		return int(''.join(m))
	except ValueError:
		return None


def find_product_links(soup: BeautifulSoup, base_url: str, category_url: Optional[str] = None) -> List[str]:
	"""Try to extract product page links from a listing/category page.

	This is intentionally generic; adjust selectors if you know the site's structure.
	"""
	links = set()
	# common container classes that hold product cards
	candidates = soup.select('a')
	# category slug (last path segment) to prefer links that belong to this category
	category_slug = None
	if category_url:
		try:
			category_slug = requests.utils.urlparse(category_url).path.strip('/').split('/')[-1]
			if category_slug and category_slug.endswith('.html'):
				category_slug = category_slug.replace('.html', '')
		except Exception:
			category_slug = None
	for a in candidates:
		href = a.get('href')
		if not href:
			continue
		href = href.strip()
		# skip anchors and javascript
		if href.startswith('#') or href.startswith('javascript:'):
			continue
		# normalize relative URLs
		if href.startswith('/'):
			href = base_url.rstrip('/') + href
		# only keep links within same domain
		parsed = requests.utils.urlparse(href)
		if parsed.netloc and parsed.netloc != requests.utils.urlparse(base_url).netloc:
			continue

		# Heuristics to restrict to product pages within the category (laptops):
		# Require at least one of:
		#  - URL contains the category slug (from the category page)
		#  - URL matches product id pattern like '_dm1234.html'
		#  - URL path contains laptop-related keywords (may-tinh, laptop)
		is_product = False
		href_path = requests.utils.urlparse(href).path.lower()
		if category_slug and category_slug.lower() in href_path:
			is_product = True
		elif re.search(r"_dm\d+\.html", href_path):
			is_product = True
		elif re.search(r"/(?:may-tinh|may-tinh-xach-tay|laptop|notebook)/?", href_path, re.I) or re.search(r"(laptop|may-tinh|notebook)", href_path, re.I):
			is_product = True

		# If still not sure, check if anchor is inside a product container (class names)
		if not is_product:
			parent = a
			for _ in range(6):
				parent = getattr(parent, 'parent', None)
				if not parent:
					break
				cls_attr = parent.get('class') or [] if hasattr(parent, 'get') else []
				cls = ' '.join(cls_attr)
				if re.search(r"(product|item|card|listing|list|product-item|product-card)", cls, re.I):
					is_product = True
					break

		if is_product:
			links.add(href)
	return list(links)


def parse_product_page(html: str, url: str) -> Product:
	# Use Python's built-in parser to avoid dependency on lxml native wheels
	soup = BeautifulSoup(html, "html.parser")
	# Name: prefer structured/meta fields, then h1/h2
	name = ""
	og_title = soup.select_one("meta[property='og:title'], meta[name='title']")
	if og_title and og_title.get('content'):
		name = og_title['content'].strip()
	else:
		# try common header tags (product title often in h1)
		h1 = soup.find('h1')
		if h1 and h1.get_text(strip=True):
			name = h1.get_text(strip=True)
		else:
			h2 = soup.find('h2')
			name = h2.get_text(strip=True) if h2 and h2.get_text(strip=True) else ""

	# Price: prefer meta/itemprop/classed price fields; avoid script/style text nodes
	price_raw = None
	# 1) meta tags
	meta_price = soup.select_one("meta[itemprop='price'], meta[property='product:price:amount'], meta[name='price']")
	if meta_price and meta_price.get('content'):
		price_raw = meta_price['content'].strip()
	# 2) itemprop
	if not price_raw:
		el = soup.select_one("[itemprop='price']")
		if el:
			price_raw = el.get_text(strip=True)
	# 3) class/id contains 'price' or Vietnamese 'gia'/'giá'
	if not price_raw:
		el = soup.select_one("[class*='price'], [id*='price'], [class*='gia'], [id*='gia'], [class*='Giá'], [id*='Giá']")
		if el:
			price_raw = el.get_text(strip=True)
	# 4) fallback: search visible text nodes but skip script/style/noscript
	if not price_raw:
		candidates = []
		for s in soup.find_all(string=re.compile(r"\d+[\.,]?\d*\s*(đ|vnd)?", re.I)):
			parent = getattr(s, 'parent', None)
			if parent and parent.name and parent.name.lower() in ('script', 'style', 'noscript'):
				continue
			txt = s.strip()
			if len(txt) > 0:
				candidates.append(txt)
		if candidates:
			price_raw = candidates[0]

	price = to_int_price(price_raw)

	# Image: try meta og:image or first product img
	image = None
	og = soup.select_one("meta[property='og:image']")
	if og and og.get('content'):
		image = og['content']
	else:
		img_tag = soup.select_one("img")
		if img_tag and img_tag.get('src'):
			image = img_tag['src']

	# Specs: try to extract tables or lists with labels
	specs: Dict[str, str] = {}

	# Look for definition lists, tables, or key:value lists
	# 1) table with two columns
	table = soup.find('table')
	if table:
		for row in table.find_all('tr'):
			cols = row.find_all(['td', 'th'])
			if len(cols) >= 2:
				key = cols[0].get_text(separator=' ', strip=True)
				val = cols[1].get_text(separator=' ', strip=True)
				if key:
					specs[key] = val

	# 2) definition lists
	if not specs:
		for dl in soup.find_all('dl'):
			dts = dl.find_all('dt')
			dds = dl.find_all('dd')
			for dt, dd in zip(dts, dds):
				key = dt.get_text(strip=True)
				val = dd.get_text(strip=True)
				if key:
					specs[key] = val

	# 3) lists of li elements with colon-separated text
	if not specs:
		for li in soup.find_all('li'):
			text = li.get_text(separator=' ', strip=True)
			if ':' in text:
				parts = text.split(':', 1)
				k = parts[0].strip()
				v = parts[1].strip()
				if k:
					specs[k] = v

	# Fallback: grab some small paragraphs if nothing found
	if not specs:
		ptexts = [p.get_text(strip=True) for p in soup.select('p') if len(p.get_text(strip=True)) > 30]
		if ptexts:
			specs['description'] = ptexts[0]

	# Normalize/spec extraction into requested feature fields
	features = extract_features(name, specs, price)

	return Product(name=name, price=price, price_raw=price_raw, specs=specs, features=features, url=url, image=image)


def product_is_laptop_page(html: str) -> bool:
	"""Return True if the product page HTML indicates this is a laptop product.

	Checks breadcrumb, meta tags, and title for laptop-related keywords.
	"""
	soup = BeautifulSoup(html, 'html.parser')
	# Check breadcrumbs or nav elements
	breadcrumb_texts = []
	for sel in ('nav.breadcrumb', 'ul.breadcrumb', '.breadcrumb', '.breadcrumbs', '.breadcrumb-list'):
		for el in soup.select(sel):
			breadcrumb_texts.append(el.get_text(' ', strip=True).lower())
	bc = ' '.join(breadcrumb_texts)
	if any(k in bc for k in ('laptop', 'máy tính xách tay', 'may tinh xach tay', 'notebook')):
		return True

	# Check meta category/section
	meta = soup.select_one("meta[property='article:section'], meta[name='category'], meta[name='section']")
	if meta and meta.get('content') and any(k in meta['content'].lower() for k in ('laptop', 'máy tính', 'may tinh')):
		return True

	# Check title and h1 for laptop keywords
	title = (soup.title.string if soup.title and soup.title.string else '').lower()
	if any(k in title for k in ('laptop', 'máy tính', 'may tinh', 'notebook')):
		return True
	h1 = soup.find('h1')
	if h1 and any(k in h1.get_text().lower() for k in ('laptop', 'máy tính', 'may tinh', 'notebook')):
		return True

	return False


def extract_features(title: str, specs: Dict[str, str], price_value: Optional[int]) -> Dict[str, Optional[str]]:
	"""Map raw spec keys/values and title into the requested normalized fields.

	Returns a dict with these keys:
	Brand, Series/Model, CPU, RAM, Storage Capacity, GPU, Display Size, Display Resolution,
	Display Type / Refresh Rate, Battery, Weight, Material, Operating System, Year,
	Market Segment / Category
	"""
	# Initialize target fields
	fields = [
		'Manufacturer', 'CPU manufacturer', 'CPU brand modifier', 'CPU generation', 'CPU Speed (GHz)',
		'RAM (GB)', 'RAM Type', 'Bus (MHz)', 'Storage (GB)', 'Screen Size (inch)', 'Screen Resolution',
		'Refresh Rate (Hz)', 'GPU manufacturer', 'Weight (kg)', 'Battery', 'Price (VND)'
	]
	out: Dict[str, Optional[str]] = {k: None for k in fields}

	# Combine all text to search
	all_text = ' '.join([f"{k}: {v}" for k, v in specs.items() if v]) + ' ' + (title or '')
	all_text_l = all_text.lower()

	# Manufacturer from title or spec
	m = re.search(r"^(?:([A-Za-z0-9\-]+)\s+)", title)
	if m:
		out['Manufacturer'] = m.group(1)
	for k, v in specs.items():
		kl = k.lower()
		if not out['Manufacturer'] and any(x in kl for x in ('hãng', 'thương hiệu', 'brand', 'manufacturer')):
			out['Manufacturer'] = v

	# CPU manufacturer
	if re.search(r"\bintel\b", all_text_l):
		out['CPU manufacturer'] = 'Intel'
	elif re.search(r"\bamd\b|\bryzen\b", all_text_l):
		out['CPU manufacturer'] = 'AMD'

	# CPU brand modifier and generation and speed
	cpu_match = re.search(r"(i[3579]-?\d{2,4}|core\s+i[3579]|ryzen\s*\d+)", all_text_l, re.I)
	if cpu_match:
		cm = cpu_match.group(0)
		out['CPU brand modifier'] = cm.strip()
		# generation: try extract leading digits after hyphen or number sequence
		gen = re.search(r"i[3579]-?(\d{2})", cm, re.I)
		if gen:
			out['CPU generation'] = gen.group(1)
		ry = re.search(r"ryzen\s*(\d)", cm, re.I)
		if ry:
			out['CPU generation'] = ry.group(1)

	speed = re.search(r"(\d+(?:\.\d+)?)\s*ghz", all_text_l, re.I)
	if speed:
		out['CPU Speed (GHz)'] = speed.group(1)

	# RAM (GB) and type
	ram_m = re.search(r"(\d+)\s*gb", all_text_l, re.I)
	if ram_m:
		out['RAM (GB)'] = ram_m.group(1)
	ram_type = re.search(r"(ddr[2345x])", all_text_l, re.I)
	if ram_type:
		out['RAM Type'] = ram_type.group(1).upper()
	bus = re.search(r"(\d{3,4})\s*mhz", all_text_l, re.I)
	if bus:
		out['Bus (MHz)'] = bus.group(1)

	# Storage (GB) — convert TB to GB if needed
	st = re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb)", all_text_l, re.I)
	if st:
		qty = float(st.group(1))
		unit = st.group(2).lower()
		if unit == 'tb':
			out['Storage (GB)'] = str(int(qty * 1000))
		else:
			out['Storage (GB)'] = str(int(qty))

	# Screen size, resolution, refresh
	sz = re.search(r"(\d+(?:\.\d+)?)\s*(inch|\")", all_text_l, re.I)
	if sz:
		out['Screen Size (inch)'] = sz.group(1)
	res = re.search(r"(\d{3,4}x\d{3,4})", all_text_l)
	if res:
		out['Screen Resolution'] = res.group(1)
	rr = re.search(r"(\d{2,3})\s*hz", all_text_l, re.I)
	if rr:
		out['Refresh Rate (Hz)'] = rr.group(1)

	# GPU manufacturer
	if re.search(r"\bnvidia\b", all_text_l):
		out['GPU manufacturer'] = 'NVIDIA'
	elif re.search(r"\bradeon\b|\bamd\b", all_text_l):
		out['GPU manufacturer'] = 'AMD'
	elif re.search(r"\bintel\b", all_text_l) and re.search(r"intel.*(uhd|iris|xe|hd)", all_text_l):
		out['GPU manufacturer'] = 'Intel'

	# Weight (kg)
	w = re.search(r"(\d+(?:\.\d+)?)\s*kg", all_text_l, re.I)
	if w:
		out['Weight (kg)'] = w.group(1)

	# Battery
	batt = re.search(r"(\d+\s?m?ah|\d+\s?wh)", all_text_l, re.I)
	if batt:
		out['Battery'] = batt.group(0)

	# Price (VND)
	if price_value is not None:
		out['Price (VND)'] = str(price_value)
	else:
		# fallback: try extracting from text
		p = re.search(r"(\d[\d\.,]+)\s*(đ|vnd)", all_text_l, re.I)
		if p:
			out['Price (VND)'] = re.sub(r"[^0-9]", "", p.group(1))

	return out


def crawl_category(start_url: str, max_products: int = 50, delay: float = 1.0) -> List[Product]:
	session = create_session()
	LOG.info('Fetching category page: %s', start_url)
	r = session.get(start_url, timeout=15)
	r.raise_for_status()
	# Use Python's built-in parser to avoid dependency on lxml native wheels
	soup = BeautifulSoup(r.text, 'html.parser')

	# Use base url for normalizing relative links
	base_url = '{scheme}://{host}'.format(scheme=requests.utils.urlparse(start_url).scheme,
										   host=requests.utils.urlparse(start_url).netloc)

	links = find_product_links(soup, base_url, category_url=start_url)
	LOG.info('Found %d candidate links', len(links))

	products: List[Product] = []
	for link in links[:max_products]:
		try:
			LOG.info('Fetching product: %s', link)
			time.sleep(delay)
			pr = session.get(link, timeout=15)
			pr.raise_for_status()
			# Verify this product page is actually a laptop product before parsing/saving
			if not product_is_laptop_page(pr.text):
				LOG.info('Skipping non-laptop product: %s', link)
				continue
			product = parse_product_page(pr.text, link)
			products.append(product)
		except Exception as e:
			LOG.exception('Failed to fetch/parse %s: %s', link, e)
	return products


def save_json(products: List[Product], path: str) -> None:
	with open(path, 'w', encoding='utf-8') as f:
		json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)


def main() -> None:
	parser = argparse.ArgumentParser(description='Crawl An Phat store computer products')
	parser.add_argument('--category', '-c', default=DEFAULT_CATEGORY,
						help=f'Category or listing page URL to crawl (default: {DEFAULT_CATEGORY})')
	parser.add_argument('--out', '-o', default='products.json', help='Output JSON file')
	parser.add_argument('--max', '-m', type=int, default=50, help='Maximum number of products to fetch')
	parser.add_argument('--delay', '-d', type=float, default=0.8, help='Delay between product requests (s)')
	parser.add_argument('--verbose', '-v', action='store_true')
	args = parser.parse_args()

	logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(levelname)s: %(message)s')

	products = crawl_category(args.category, max_products=args.max, delay=args.delay)
	LOG.info('Crawled %d products', len(products))
	save_json(products, args.out)
	LOG.info('Saved to %s', args.out)


if __name__ == '__main__':
	main()
