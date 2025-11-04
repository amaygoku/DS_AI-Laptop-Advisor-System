"""Standalone An Phat crawler (no DB) that fetches laptop products and extracts specs.

Saves results to data/anphat_laptops.json
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


CATEGORY_URL = 'https://www.anphatpc.com.vn/may-tinh-xach-tay-laptop.html'
MAX_PAGES = 5
OUTPUT_PATH = 'data/anphat_laptops.json'


def create_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; Anphat-NoDB/1.0)'
    })
    return s


def parse_category_page(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, 'html.parser')
    urls: List[str] = []
    # Try the known container first
    container = soup.find('div', {'class': 'p-list-container d-flex flex-wrap'})
    if container:
        list_divs = container.find_all('div', {'class': 'p-item js-p-item'})
        for product in list_divs:
            a = product.find('a')
            if not a:
                continue
            href = a.get('href')
            if not href:
                continue
            if href.startswith('/'):
                href = base.rstrip('/') + href
            urls.append(href)
        if urls:
            return list(dict.fromkeys(urls))

    # Additional common containers used by ecommerce themes
    alt_containers = [
        ("div", {"class": "product-list"}),
        ("div", {"class": "product-grid"}),
        ("ul", {"class": "products"}),
        ("div", {"class": "product-item"}),
    ]
    for tag, attrs in alt_containers:
        c = soup.find(tag, attrs)
        if c:
            for a in c.select('a'):
                href = a.get('href')
                if not href:
                    continue
                if href.startswith('/'):
                    href = base.rstrip('/') + href
                urls.append(href)
            if urls:
                return list(dict.fromkeys(urls))

    # More robust fallback: scan anchors and use heuristics to pick laptop/product links
    for a in soup.select('a'):
        href = a.get('href')
        if not href:
            continue
        href = href.strip()
        # normalize
        if href.startswith('/'):
            href = base.rstrip('/') + href
        # ignore external
        parsed = requests.utils.urlparse(href)
        if parsed.netloc and parsed.netloc != requests.utils.urlparse(base).netloc:
            continue
        # heuristics: prefer links that contain laptop-related slugs or product id pattern
        if re.search(r"_dm\d+\.html", href) or re.search(r"/(?:may-tinh|may-tinh-xach-tay|laptop|notebook)/", href, re.I) or 'may-tinh' in href.lower() or 'laptop' in href.lower():
            urls.append(href)
            continue
        # also accept anchors inside product-item like elements
        parent = a
        for _ in range(6):
            try:
                parent = getattr(parent, 'parent', None)
                if not parent:
                    break
                cls_attr = parent.get('class') or [] if hasattr(parent, 'get') else []
                # Normalize class string
                cls = ' '.join(cls_attr).lower()
                # Use simple substring checks instead of regex to avoid heavy compilation on large strings
                keywords = ('product', 'p-item', 'product-item', 'product-card', 'p-list-container', 'p-item')
                if any(k in cls for k in keywords):
                    urls.append(href)
                    break
            except Exception:
                # defensive: don't let a single problematic node stop parsing
                break

    # deduplicate while preserving order
    return list(dict.fromkeys(urls))


def parse_product_page(html: str, url: str) -> Dict:
    soup = BeautifulSoup(html, 'html.parser')
    # name
    name = ''
    og = soup.select_one("meta[property='og:title'], meta[name='title']")
    if og and og.get('content'):
        name = og['content'].strip()
    else:
        h1 = soup.find('h1')
        if h1:
            name = h1.get_text(strip=True)

    # price
    price_raw = None
    meta_price = soup.select_one("meta[itemprop='price'], meta[property='product:price:amount'], meta[name='price']")
    if meta_price and meta_price.get('content'):
        price_raw = meta_price['content'].strip()
    else:
        el = soup.select_one("[itemprop='price']")
        if el:
            price_raw = el.get_text(strip=True)
    price = None
    if price_raw:
        m = re.findall(r"[0-9]+", price_raw.replace('.', '').replace(',', ''))
        if m:
            price = int(''.join(m))

    # image
    image = None
    ogi = soup.select_one("meta[property='og:image']")
    if ogi and ogi.get('content'):
        image = ogi['content']

    # specs table / lists
    specs: Dict[str, str] = {}
    table = soup.find('table')
    if table:
        for row in table.find_all('tr'):
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 2:
                k = cols[0].get_text(' ', strip=True)
                v = cols[1].get_text(' ', strip=True)
                specs[k] = v

    if not specs:
        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                k = dt.get_text(strip=True)
                v = dd.get_text(strip=True)
                specs[k] = v

    if not specs:
        for li in soup.find_all('li'):
            text = li.get_text(' ', strip=True)
            if ':' in text:
                k, v = [p.strip() for p in text.split(':', 1)]
                specs[k] = v

    features = extract_features(name, specs, price)

    return {
        'url': url,
        'name': name,
        'price': price,
        'price_raw': price_raw,
        'image': image,
        'specs': specs,
        'features': features,
    }


def extract_features(title: str, specs: Dict[str, str], price_value: Optional[int]) -> Dict[str, Optional[str]]:
    # reuse the same heuristics as in crawl_ap.py
    fields = [
        'Manufacturer', 'CPU manufacturer', 'CPU brand modifier', 'CPU generation', 'CPU Speed (GHz)',
        'RAM (GB)', 'RAM Type', 'Bus (MHz)', 'Storage (GB)', 'Screen Size (inch)', 'Screen Resolution',
        'Refresh Rate (Hz)', 'GPU manufacturer', 'Weight (kg)', 'Battery', 'Price (VND)'
    ]
    out: Dict[str, Optional[str]] = {k: None for k in fields}

    all_text = ' '.join([f"{k}: {v}" for k, v in specs.items() if v]) + ' ' + (title or '')
    all_text_l = all_text.lower()

    # Manufacturer
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

    cpu_match = re.search(r"(i[3579]-?\d{2,4}|core\s+i[3579]|ryzen\s*\d+)", all_text_l, re.I)
    if cpu_match:
        cm = cpu_match.group(0)
        out['CPU brand modifier'] = cm.strip()
        gen = re.search(r"i[3579]-?(\d{2})", cm, re.I)
        if gen:
            out['CPU generation'] = gen.group(1)
        ry = re.search(r"ryzen\s*(\d)", cm, re.I)
        if ry:
            out['CPU generation'] = ry.group(1)

    speed = re.search(r"(\d+(?:\.\d+)?)\s*ghz", all_text_l, re.I)
    if speed:
        out['CPU Speed (GHz)'] = speed.group(1)

    ram_m = re.search(r"(\d+)\s*gb", all_text_l, re.I)
    if ram_m:
        out['RAM (GB)'] = ram_m.group(1)
    ram_type = re.search(r"(ddr[2345x])", all_text_l, re.I)
    if ram_type:
        out['RAM Type'] = ram_type.group(1).upper()
    bus = re.search(r"(\d{3,4})\s*mhz", all_text_l, re.I)
    if bus:
        out['Bus (MHz)'] = bus.group(1)

    st = re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb)", all_text_l, re.I)
    if st:
        qty = float(st.group(1))
        unit = st.group(2).lower()
        if unit == 'tb':
            out['Storage (GB)'] = str(int(qty * 1000))
        else:
            out['Storage (GB)'] = str(int(qty))

    sz = re.search(r"(\d+(?:\.\d+)?)\s*(inch|\")", all_text_l, re.I)
    if sz:
        out['Screen Size (inch)'] = sz.group(1)
    res = re.search(r"(\d{3,4}x\d{3,4})", all_text_l)
    if res:
        out['Screen Resolution'] = res.group(1)
    rr = re.search(r"(\d{2,3})\s*hz", all_text_l, re.I)
    if rr:
        out['Refresh Rate (Hz)'] = rr.group(1)

    if re.search(r"\bnvidia\b", all_text_l):
        out['GPU manufacturer'] = 'NVIDIA'
    elif re.search(r"\bradeon\b|\bamd\b", all_text_l):
        out['GPU manufacturer'] = 'AMD'
    elif re.search(r"\bintel\b", all_text_l) and re.search(r"intel.*(uhd|iris|xe|hd)", all_text_l):
        out['GPU manufacturer'] = 'Intel'

    w = re.search(r"(\d+(?:\.\d+)?)\s*kg", all_text_l, re.I)
    if w:
        out['Weight (kg)'] = w.group(1)

    batt = re.search(r"(\d+\s?m?ah|\d+\s?wh)", all_text_l, re.I)
    if batt:
        out['Battery'] = batt.group(0)

    if price_value is not None:
        out['Price (VND)'] = str(price_value)
    else:
        p = re.search(r"(\d[\d\.,]+)\s*(đ|vnd)", all_text_l, re.I)
        if p:
            out['Price (VND)'] = re.sub(r"[^0-9]", "", p.group(1))

    return out


def crawl_category(category_url: str, max_pages: int = MAX_PAGES) -> List[Dict]:
    session = create_session()
    base = requests.utils.urlparse(category_url).scheme + '://' + requests.utils.urlparse(category_url).netloc

    product_urls: List[str] = []
    for page in range(1, max_pages + 1):
        url = f"{category_url}?page={page}"
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            urls = parse_category_page(r.text, base)
            if not urls:
                break
            product_urls.extend(urls)
            time.sleep(0.3)
        except Exception:
            break

    # deduplicate while preserving order
    seen = set()
    product_urls = [x for x in product_urls if not (x in seen or seen.add(x))]

    results: List[Dict] = []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(session.get, u, timeout=15): u for u in product_urls}
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                r = fut.result()
                if r.status_code == 200:
                    # quick laptop page check: look for 'laptop' in title or breadcrumbs
                    html = r.text
                    if 'laptop' not in html.lower() and 'máy tính xách tay' not in html.lower():
                        # skip non-laptop pages
                        continue
                    parsed = parse_product_page(html, u)
                    results.append(parsed)
                time.sleep(0.1)
            except Exception:
                continue

    return results


def main():
    os.makedirs('data', exist_ok=True)
    items = crawl_category(CATEGORY_URL, MAX_PAGES)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f'Saved {len(items)} items to {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
