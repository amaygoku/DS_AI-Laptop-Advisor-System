import os
import sys
sys.path.append(os.getcwd())  # NOQA

import json
import time
import traceback
import re
import requests

from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup as bs
from concurrent.futures import ThreadPoolExecutor, as_completed

from source.crawl.base_crawler import BaseCrawler


class Anphat(BaseCrawler):

    MAX_PAGES = 10
    BASE = "https://www.anphatpc.com.vn"

    # Các từ khoá URL trang danh mục/collection để loại
    CATEGORY_KEYWORDS = (
        'gaming-laptop', 'may-tinh-xach-tay-laptop', 'laptop-theo-hang',
        'laptop-rtx-40-series', 'laptop-rtx-50-series', 'laptop-ai',
        'hoc-tap-van-phong', 'doanh-nhan', 'doanh-nghiep', 'sinh-vien'
    )

    def __init__(self):
        # Không còn connect DB
        self.anphat_config = self.load_config('anphat.json')

        # Session nhẹ có UA
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AnphatCrawler-NoDB/1.0)"
        })

    # ------------------------------- Utils -------------------------------

    @staticmethod
    def _dedup_preserve_order(items):
        seen = set()
        out = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def _normalize_same_domain_html_url(self, href: str) -> str | None:
        """Chuẩn hoá URL, chỉ nhận .html cùng domain, không query/fragment."""
        if not href:
            return None
        href = href.strip()
        if href.startswith('#') or href.startswith('javascript:'):
            return None
        url = urljoin(self.BASE, href)
        p = urlparse(url)
        if p.netloc != urlparse(self.BASE).netloc:
            return None
        if not p.path.endswith('.html'):
            return None
        if p.query or p.fragment:
            return None
        path_l = p.path.lower()
        if any(kw in path_l for kw in self.CATEGORY_KEYWORDS):
            return None
        if any(b in path_l for b in ('/tin-', '/news', '/blog', '/khuyen-mai', '/phu-kien-', '/linh-kien-')):
            return None
        return f'{p.scheme}://{p.netloc}{p.path}'

    # ------------------ Parse a category page → product URLs ------------------

    def __parse_category_page(self, url: str) -> dict:
        """
        Quét tất cả <a>, lọc theo pattern URL CHI TIẾT sản phẩm:
            /ten-san-pham_dm1234.html
            /ten-san-pham_sp1234.html
            /ten-san-pham_dp1234.html
            /ten-san-pham-p1234.html
        """
        urls = []
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()

            # Trang danh mục rỗng
            if 'Sản phẩm đang được cập nhật' in resp.text:
                return {'status': 'error', 'message': f'Error: {url} is not available', 'data': []}

            soup = bs(resp.text, 'html.parser')

            product_detail_re = re.compile(r"/[^/]+(?:_(?:dm|sp|dp)\d+|-p\d+)\.html$", re.I)

            for a in soup.find_all('a', href=True):
                norm = self._normalize_same_domain_html_url(a['href'])
                if not norm:
                    continue
                # chỉ nhận URL trông như chi tiết sản phẩm
                if not product_detail_re.search(urlparse(norm).path.lower()):
                    continue
                urls.append(norm)

            urls = self._dedup_preserve_order(urls)
            return {
                'status': 'success',
                'message': f'Get product urls of {url} successfully',
                'data': urls
            }

        except Exception as e:
            self.log(f"Error: {str(e)}", color='red')
            return {'status': 'error', 'message': f'Error: {str(e)}', 'data': []}

    # ------------------ Iterate pages for a manufacturer ------------------

    def _get_product_urls(self, manufacturer: str) -> list:
        """
        Lấy toàn bộ URL chi tiết sản phẩm của 1 hãng (tối đa MAX_PAGES).
        """
        urls = []
        url = self.anphat_config[manufacturer]
        self.log(f"==>> {manufacturer.upper()} url: {url}")

        # Danh sách trang phân trang
        url_list_pages = [f'{url}?page={i}' for i in range(1, self.MAX_PAGES + 1)]

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self.__parse_category_page, u) for u in url_list_pages]

            for future in as_completed(futures):
                result = future.result()
                if result['status'] == 'success':
                    self.log(f'==> {result["message"]}: {len(result["data"])} products', color='green')
                    urls.extend(result['data'])
                else:
                    self.log(f'==> {result["message"]}', color='red')

        urls = self._dedup_preserve_order(urls)
        self.log('==>> Total products: {}'.format(len(urls)))
        return urls

    # ------------------ Public: get all links for all manufacturers ------------------

    def get_all_product_links(self):
        """
        Lấy URL sản phẩm của tất cả hãng trong config và lưu JSON.
        """
        save_dir = 'data/anphat'
        os.makedirs(save_dir, exist_ok=True)

        anphat_product_links = {}
        for manufacturer in self.anphat_config:
            self.log(f'========>> Getting product urls of {manufacturer.upper()}', color='yellow')
            urls = self._get_product_urls(manufacturer)
            anphat_product_links[manufacturer] = urls

        out_path = os.path.join(save_dir, 'anphat_product_links.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(anphat_product_links, f, indent=4, ensure_ascii=False)

        self.log(f'========>> Saved links: {out_path}', color='green')
        self.log('========>> Done!', color='green')

    def __fetch_html(self, url: str) -> dict:
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                return {'status': 'success', 'message': f'Get {url} successfully', 'data': r.text}
            else:
                return {'status': 'error', 'message': f'Error: {url} is not available (status {r.status_code})', 'data': []}
        except Exception as e:
            return {'status': 'error', 'message': f'Error: {str(e)}', 'data': []}

    def crawl_raw_htmls(self):

        links_path = 'data/anphat/anphat_product_links.json'
        if not os.path.exists(links_path):
            self.log(f'Links file not found: {links_path}. Hãy chạy get_all_product_links() trước.', color='red')
            return

        with open(links_path, 'r', encoding='utf-8') as f:
            anphat_product_links = json.load(f)

        save_dir = 'data/anphat/raw_htmls'
        os.makedirs(save_dir, exist_ok=True)

        manifest = []  # list of dict {manufacturer, url, saved_path}

        # Tải theo từng hãng để dễ theo dõi log
        for manufacturer in anphat_product_links:
            urls = anphat_product_links[manufacturer]
            self.log(f'========>> Getting raw htmls of {manufacturer.upper()} (total {len(urls)})', color='yellow')

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(self.__fetch_html, url): url for url in urls}

                for idx, future in enumerate(as_completed(list(futures.keys()))):
                    url = futures[future]
                    result = future.result()
                    total = len(futures)

                    if result['status'] == 'success':
                        self.log(f'==>{idx+1:>4}/{total:<4} {result["message"]}', color='green')

                        # Tạo tên file gọn
                        filename = f'{manufacturer}_{idx+1}.html'
                        save_path = os.path.join(save_dir, filename)

                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(result['data'])

                        manifest.append({
                            "manufacturer": manufacturer,
                            "url": url,
                            "saved_path": save_path
                        })

                    else:
                        self.log(f'==>{idx+1:>4}/{total:<4} {result["message"]}', color='red')

                    # nương tay tránh bị rate-limit
                    if (idx + 1) % 20 == 0:
                        time.sleep(0.2)

        # Lưu manifest
        manifest_path = 'data/anphat/raw_htmls_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        self.log(f'HTML saved. Manifest: {manifest_path}', color='green')



    def parse_specs(self):

        self.log('parse_specs() is not implemented yet (no DB version).', color='yellow')


if __name__ == "__main__":
    anphat = Anphat()
    anphat.get_all_product_links()
    anphat.crawl_raw_htmls()

    anphat.parse_specs()
