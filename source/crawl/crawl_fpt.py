# source/crawl/crawl_fpt.py
import os
import sys
sys.path.append(os.getcwd())  # NOQA

import json
import time
import re
import traceback
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup as bs

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from source.utils.selenium import ChromeDriver
from source.crawl.base_crawler import BaseCrawler


class Fpt(BaseCrawler):
    """
    Crawler FPT KHÔNG dùng database.
    Pipeline:
      1) get_all_product_links() -> data/fpt/fpt_product_links.json
      2) crawl_raw_htmls() -> raw/detail + manifest
      3) parse_specs() -> data/fpt/parse_results.json
      4) enhancer() -> data/fpt/all_columns_fpt.json
      5) __main__ -> regex cleaning + CSV
    """

    MAX_PAGES = 5  # <= yêu cầu: chỉ crawl 5 trang / manufacturer

    def __init__(self, headless: bool = False):
        self.fpt_config = self.load_config('fpt.json')
        self.headless = headless

        os.makedirs('data/fpt', exist_ok=True)
        os.makedirs('data/fpt/raw_htmls', exist_ok=True)
        os.makedirs('data/fpt/detail_htmls', exist_ok=True)
        os.makedirs('data/fpt/_debug', exist_ok=True)

    # ==========================
    # Helpers for navigation
    # ==========================

    def _close_overlays(self, driver):
        """Đóng các overlay/popup/cookie thường gặp để tránh che DOM."""
        try:
            selectors = [
                ".btn-accept", ".btn-primary.cookie-close", ".js-cookie-accept", ".close-cookie",
                ".cps-popup .btn-close", ".modal .btn-close",
                ".os-clickable",
                ".btn.btn-accept",
                ".close", ".close-modal"
            ]
            for sel in selectors:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    try:
                        driver.execute_script("arguments[0].click();", elems[0])
                        time.sleep(0.15)
                    except Exception:
                        pass
            driver.execute_script("document.body.click();")
        except Exception:
            pass

    def _wait_products_or_empty(self, driver, timeout=15) -> str:
        """
        Chờ 1 trong 2 tình huống:
          - Có ít nhất 1 item '.cdt-product'
          - Hoặc hiển thị trạng thái rỗng (không có sản phẩm)
        Trả về: 'products' | 'empty'
        """
        end = time.time() + timeout
        while time.time() < end:
            self._close_overlays(driver)

            for y in (200, 600, 1200):
                driver.execute_script(f"window.scrollTo(0, {y});")
                time.sleep(0.15)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.15)

            items = driver.find_elements(By.CSS_SELECTOR, ".cdt-product")
            if items:
                return "products"

            body_txt = (driver.page_source or "").lower()
            for t in ("không tìm thấy", "không có sản phẩm", "chưa có sản phẩm"):
                if t in body_txt:
                    return "empty"

            time.sleep(0.2)

        html = driver.page_source or ""
        dbg_path = f"data/fpt/_debug/{int(time.time())}.html"
        with open(dbg_path, "w", encoding="utf-8") as f:
            f.write(html[:800_000])
        raise TimeoutException(f"Neither products nor empty state appeared. Dump: {dbg_path}")

    # ==========================
    # Step 1: Get all product links
    # ==========================

    def __parse_product_links(self, page_source: str) -> List[str]:
        urls: List[str] = []
        try:
            soup = bs(page_source, 'html.parser')

            for item in soup.select(".cdt-product"):
                a = item.find("a", href=True)
                if not a:
                    continue
                href = a["href"].strip()
                if href.startswith("/"):
                    href = f"https://fptshop.com.vn{href}"
                elif not href.startswith("http"):
                    href = f"https://fptshop.com.vn/{href.lstrip('/')}"
                urls.append(href)

            if not urls:
                for a in soup.select("a[href*='/may-tinh-xach-tay/']"):
                    href = a.get("href", "").strip()
                    if not href:
                        continue
                    if href.startswith("/"):
                        href = f"https://fptshop.com.vn{href}"
                    elif not href.startswith("http"):
                        href = f"https://fptshop.com.vn/{href.lstrip('/')}"
                    urls.append(href)

        except Exception:
            self.log(traceback.format_exc(), color='red')
        finally:
            seen, dedup = set(), []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    dedup.append(u)
            self.log(f'Found {len(dedup)} product links')
        return dedup

    def _requests_parse_links(self, url: str) -> List[str]:
        """Fallback: parse link bằng requests nếu Selenium không render được."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            }
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            soup = bs(r.text, "html.parser")
            urls: List[str] = []

            for item in soup.select(".cdt-product a[href]"):
                href = item.get("href", "").strip()
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://fptshop.com.vn" + href
                elif not href.startswith("http"):
                    href = "https://fptshop.com.vn/" + href.lstrip("/")
                urls.append(href)

            if not urls:
                for a in soup.select("a[href*='/may-tinh-xach-tay/']"):
                    href = a.get("href", "").strip()
                    if href.startswith("/"):
                        href = "https://fptshop.com.vn" + href
                    elif not href.startswith("http"):
                        href = "https://fptshop.com.vn/" + href.lstrip("/")
                    urls.append(href)

            seen, out = set(), []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return out
        except Exception:
            return []

    def __get_product_link(self, driver, manufacturer: str) -> List[str]:
        """
        Phân trang an toàn: ?trang=1 → tăng dần, dừng khi rỗng hoặc ít item.
        Có fallback requests nếu Selenium timeout.
        """
        base_url = self.fpt_config[manufacturer]
        if "?trang=" in base_url:
            base_url = base_url.split("?trang=")[0]

        all_urls: List[str] = []
        page = 1
        max_pages = self.MAX_PAGES

        while page <= max_pages:
            url = f"{base_url}?trang={page}"
            self.log(f'[{manufacturer.upper()}] Loading page {page}: {url}')
            driver.get(url)

            try:
                state = self._wait_products_or_empty(driver, timeout=15)
            except TimeoutException as te:
                self.log(f'Timeout. Trying requests fallback... ({te})', color='yellow')
                urls = self._requests_parse_links(url)
                if urls:
                    self.log(f'[Requests] Got {len(urls)} links on page {page}', color='green')
                    for u in urls:
                        if u not in all_urls:
                            all_urls.append(u)
                    if len(urls) < 20:
                        break
                    page += 1
                    continue
                else:
                    self.log('Requests fallback empty. Refreshing once...', color='yellow')
                    driver.refresh()
                    try:
                        state = self._wait_products_or_empty(driver, timeout=12)
                    except TimeoutException:
                        self.log('Still timeout. Stop this brand.', color='red')
                        break

            if state == "empty":
                self.log(f'[{manufacturer.upper()}] Empty at page {page}. Stop.', color='yellow')
                break

            urls = self.__parse_product_links(driver.page_source)
            if not urls:
                urls = self._requests_parse_links(url)

            if not urls:
                self.log(f'[{manufacturer.upper()}] No URLs parsed at page {page}. Stop.', color='yellow')
                break

            for u in urls:
                if u not in all_urls:
                    all_urls.append(u)

            if len(urls) < 20:
                break

            page += 1
            time.sleep(0.25)

        self.log(f'[{manufacturer.upper()}] Total products collected: {len(all_urls)}', color='green')
        return all_urls

    def get_all_product_links(self):
        """Lấy URL sản phẩm của tất cả hãng và lưu JSON."""
        self.log('Getting the driver')
        driver = ChromeDriver(headless=self.headless).driver

        urls: Dict[str, List[str]] = {}
        for manufacturer in self.fpt_config.keys():
            self.log(f'=====> {manufacturer.upper()}')
            urls[manufacturer] = self.__get_product_link(driver=driver, manufacturer=manufacturer)

        self.log('Closing the driver')
        try:
            driver.quit()
        except Exception:
            pass

        out_path = 'data/fpt/fpt_product_links.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(urls, f, indent=4, ensure_ascii=False)
        self.log(f'Saving the result to file: {out_path}', color='green')

    # ==========================
    # Step 2: Fetch raw HTMLs
    # ==========================
    def _open_specs_tab_and_get_html(self, driver, wait_secs: int = 10) -> str:
        """
        Cố gắng bấm vào:
        - Tab 'Thông số kỹ thuật' / 'Cấu hình'
        - Hoặc nút 'Xem tất cả thông số' / 'Xem thêm cấu hình'
        Trả về HTML vùng thông số. Trống nếu không tìm được.
        """
        try:
            clicked = False

            # === 1. Click nút/tab "Thông số kỹ thuật" hoặc "Cấu hình" ===
            tab_selectors = [
                "a[href*='thong-so']", "a[href*='thongso']", "a[href*='cau-hinh']",
                ".tab a", ".nav-tabs a", ".tabs a", ".product-tabs a",
                "button", "li a"
            ]
            for sel in tab_selectors:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    text = (el.text or "").strip().lower()
                    if any(kw in text for kw in ["thông số", "kỹ thuật", "cấu hình"]):
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.3)
                        try:
                            driver.execute_script("arguments[0].click();", el)
                        except Exception:
                            try:
                                el.click()
                            except Exception:
                                pass
                        clicked = True
                        break
                if clicked:
                    break

            # === 2. Nếu có nút "Xem tất cả thông số" / "Xem thêm cấu hình" ===
            see_more_selectors = [
                "button", "a", ".btn", ".viewmore", ".readmore"
            ]
            for sel in see_more_selectors:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                for b in buttons:
                    label = (b.text or "").strip().lower()
                    if any(x in label for x in ["xem tất cả", "xem thêm", "xem cấu hình", "xem thông số"]):
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                        time.sleep(0.3)
                        try:
                            driver.execute_script("arguments[0].click();", b)
                        except Exception:
                            try:
                                b.click()
                            except Exception:
                                pass
                        clicked = True
                        break
                if clicked:
                    break

            # === 3. Đợi vùng thông số xuất hiện sau khi click ===
            content_selectors = [
                ".st-pd-table", ".parameter", ".content-parameter",
                ".product-specs", ".st-specification", ".specifications",
                ".cps-block-spec", ".parameter__list", ".parameter__item"
            ]
            end = time.time() + wait_secs
            spec_html = ""
            while time.time() < end:
                for cs in content_selectors:
                    boxes = driver.find_elements(By.CSS_SELECTOR, cs)
                    if boxes:
                        try:
                            spec_html = driver.execute_script("return arguments[0].outerHTML;", boxes[0])
                            if spec_html and len(spec_html) > 30:
                                return spec_html
                        except Exception:
                            continue
                time.sleep(0.4)

            return spec_html or ""

        except Exception as e:
            self.log(f"[_open_specs_tab_and_get_html] Error: {e}", color="red")
            return ""

    def crawl_raw_htmls(self) -> None:

        links_path = 'data/fpt/fpt_product_links.json'
        if not os.path.exists(links_path):
            self.log(f'File links không tồn tại: {links_path}. Hãy chạy get_all_product_links() trước.', color='red')
            return

        with open(links_path, 'r', encoding='utf-8') as f:
            urls_by_brand: Dict[str, List[str]] = json.load(f)

        os.makedirs('data/fpt/raw_htmls', exist_ok=True)
        os.makedirs('data/fpt/detail_htmls', exist_ok=True)

        manifest: List[Dict[str, Any]] = []

        # Duyệt theo hãng: mỗi hãng dùng 1 driver để ổn định & hiệu năng
        for brand, url_list in urls_by_brand.items():
            if not url_list:
                continue

            self.log(f'========>> Fetching RAW & DETAIL HTML of {brand.upper()} (total {len(url_list)})', color='yellow')
            driver = ChromeDriver(headless=self.headless).driver

            try:
                for idx, url in enumerate(url_list, start=1):
                    attempt, success, last_err = 0, False, None

                    while attempt < 2 and not success:
                        attempt += 1
                        try:
                            # 1) Mở trang
                            driver.get(url)
                            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
                            time.sleep(0.6)

                            # 2) Đóng overlay/popup nếu có
                            try:
                                self._close_overlays(driver)
                            except Exception:
                                pass

                            # 3) Lấy RAW HTML
                            raw_html = driver.page_source or ""
                            raw_path = f'data/fpt/raw_htmls/{brand}_{idx}.html'
                            with open(raw_path, 'w', encoding='utf-8') as rf:
                                rf.write(raw_html[:8_000_000])  # cắt 8MB tránh quá lớn

                            # 4) Bấm “Thông số kỹ thuật” / “Xem tất cả thông số” và lấy DETAIL HTML
                            detail_html = self._open_specs_tab_and_get_html(driver, wait_secs=12)

                            # Fallback nếu lần đầu chưa có: cuộn & thử lại
                            if not detail_html:
                                for y in (200, 600, 1200, 0):
                                    driver.execute_script(f"window.scrollTo(0, {y});")
                                    time.sleep(0.2)
                                detail_html = self._open_specs_tab_and_get_html(driver, wait_secs=8)

                            # 5) Lưu DETAIL HTML (kể cả rỗng để debug)
                            detail_path = f'data/fpt/detail_htmls/{brand}_{idx}.html'
                            with open(detail_path, 'w', encoding='utf-8') as df:
                                df.write(detail_html or "")

                            # 6) Cập nhật manifest
                            manifest.append({
                                "Manufacturer": brand,
                                "Url": url,
                                "Raw_html_path": raw_path,
                                "Detail_specs_html_path": detail_path,
                                "Success": True
                            })
                            self.log(f'[OK] {brand} #{idx}: saved RAW & DETAIL', color='green')
                            success = True

                        except Exception as e:
                            last_err = str(e)
                            if attempt < 2:
                                self.log(f'[WARN] {brand} #{idx} attempt {attempt} failed → retry... ({e})', color='yellow')
                                # làm sạch nhẹ trước khi thử lại
                                try:
                                    driver.delete_all_cookies()
                                    driver.refresh()
                                    time.sleep(0.6)
                                except Exception:
                                    pass
                            else:
                                self.log(f'[FAIL] {brand} #{idx} {url}: {e}', color='red')
                                manifest.append({
                                    "Manufacturer": brand,
                                    "Url": url,
                                    "Raw_html_path": None,
                                    "Detail_specs_html_path": None,
                                    "Success": False,
                                    "Error": last_err or "unknown"
                                })

                    # throttle nhẹ để tránh bị rate-limit
                    if idx % 10 == 0:
                        time.sleep(0.3)

            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

        # 7) Ghi manifest để parse_specs() dùng
        manifest_path = 'data/fpt/raw_htmls_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as mf:
            json.dump(manifest, mf, indent=2, ensure_ascii=False)
        self.log(f'Finish fetching. Manifest saved to {manifest_path}', color='green')



    # ==========================
    # Step 3: Parse specs (mạnh)
    # ==========================

    @staticmethod
    def _parse_from_html(raw_html: str, url: str) -> Dict[str, Any]:
        soup = bs(raw_html, 'html.parser')

        # name
        name = None
        og = soup.select_one("meta[property='og:title'], meta[name='title']")
        if og and og.get('content'):
            name = og['content'].strip()
        if not name:
            h1 = soup.find('h1')
            if h1:
                name = h1.get_text(' ', strip=True)

        # meta description
        meta_desc = ''
        md = soup.select_one("meta[name='description'], meta[property='og:description']")
        if md and md.get('content'):
            meta_desc = md['content'].strip()

        # price (giữ nguyên phần bạn đã làm)
        price_raw = None
        mp = soup.select_one("meta[itemprop='price'], meta[property='product:price:amount'], meta[name='price']")
        if mp and mp.get('content'):
            price_raw = mp['content'].strip()
        if not price_raw:
            for sc in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(sc.string)
                except Exception:
                    continue
                if isinstance(data, dict):
                    offers = data.get('offers')
                    if isinstance(offers, dict) and offers.get('price'):
                        price_raw = str(offers['price'])
                        break
        if not price_raw:
            price_el = soup.select_one('.st-price, .product-price, .price, .fs-dtprice, .gia, .box-price .price')
            if price_el:
                t = price_el.get_text(' ', strip=True)
                if any(c.isdigit() for c in t):
                    price_raw = t
        price = None
        if price_raw:
            digits = re.findall(r'\d+', price_raw.replace('.', '').replace(',', ''))
            if digits:
                price = int(''.join(digits))

        # image
        image = None
        ogi = soup.select_one("meta[property='og:image']")
        if ogi and ogi.get('content'):
            image = ogi['content'].strip()

           # ====== SPECS (gom cả JSON-LD additionalProperty) ======
        specs: Dict[str, str] = {}

        def put(k, v):
            if not k or not v:
                return
            k = re.sub(r'\s+', ' ', str(k).strip())
            v = re.sub(r'\s+', ' ', str(v).strip())
            if k and v and len(k) < 120 and k not in specs:
                specs[k] = v

        # 1) Quét JSON-LD
        for sc in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(sc.string)
            except Exception:
                continue

            def walk(obj):
                if isinstance(obj, dict):
                    # offers.price đã xử lý ở trên; ở đây quan tâm additionalProperty
                    if "additionalProperty" in obj and isinstance(obj["additionalProperty"], list):
                        for p in obj["additionalProperty"]:
                            if isinstance(p, dict):
                                put(p.get("name") or p.get("propertyID"), p.get("value") or p.get("description"))
                    for k, v in obj.items():
                        walk(v)
                elif isinstance(obj, list):
                    for it in obj:
                        walk(it)
            walk(data)

        # 2) Quét vùng container specs trong DOM (mở rộng selector)
        containers = soup.select(
            ".st-pd-table, .parameter, .parameter__list, .parameter__item, "
            ".fs-ctbox, .product-specs, .card.card-normal, .box_content, "
            ".st-card, .st-card__content, .st-specification, .specifications"
        )
        if not containers:
            containers = [soup]

        for root in containers:
            for table in root.find_all('table'):
                for tr in table.find_all('tr'):
                    tds = tr.find_all(['th', 'td'])
                    if len(tds) >= 2:
                        put(tds[0].get_text(' ', strip=True), tds[1].get_text(' ', strip=True))
            for dl in root.find_all('dl'):
                dts = dl.find_all('dt'); dds = dl.find_all('dd')
                for dt, dd in zip(dts, dds):
                    put(dt.get_text(' ', strip=True), dd.get_text(' ', strip=True))
            for li in root.find_all('li'):
                txt = li.get_text(' ', strip=True)
                if 5 <= len(txt) <= 300:
                    if ':' in txt:
                        k, v = [p.strip() for p in txt.split(':', 1)]
                        put(k, v)
                    elif ' - ' in txt:
                        parts = txt.split(' - ', 1)
                        if len(parts) == 2:
                            put(parts[0].strip(), parts[1].strip())

        # Lọc rác breadcrumb/marketing
        junk = re.compile(r'^(Trang chủ|Laptop|Chọn khu vực|Khuyến mãi|apple|iphone|watch|ưu đãi)$', re.I)
        specs = {k: v for k, v in specs.items() if not junk.search(k)}

        # ===== gom mô tả + URL vào extra_text để regex ăn thêm (i3-N305, 16GB/512GB, RTX...) =====
        extras: List[str] = []
    # mô tả/ngắn
        for sel in [".ctText", ".short", ".description", ".fs-ctbox", ".box_content",
                    ".st-pd-table", ".parameter", ".product-specs", ".content-parameter"]:
            for e in soup.select(sel):
                try:
                    extras.append(e.get_text(' ', strip=True))
                except Exception:
                    pass
        if meta_desc:
            extras.append(meta_desc)
        if name:
            extras.append(name)

        long_text = ' | '.join(extras) if extras else ''
        kv_blob = " | ".join([f"{k}: {v}" for k, v in specs.items()]) if specs else ''
        extra_text = ' | '.join([p for p in [long_text, kv_blob] if p]) 


        features = Fpt._extract_features(
            title=name or "",
            specs=specs,
            price_value=price,
            extra_text=extra_text
        )

        return {
            "url": url,
            "name": name,
            "price": price,
            "price_raw": price_raw,
            "image": image,
            "specs": specs,
            "features": features
        }



    @staticmethod
    def _extract_features(title: str,
                        specs: Dict[str, str],
                        price_value: Optional[int],
                        extra_text: str = "") -> Dict[str, Optional[str]]:
        fields = [
            'Manufacturer', 'CPU manufacturer', 'CPU brand modifier', 'CPU generation', 'CPU Speed (GHz)',
            'RAM (GB)', 'RAM Type', 'Bus (MHz)', 'Storage (GB)', 'Screen Size (inch)', 'Screen Resolution',
            'Refresh Rate (Hz)', 'GPU manufacturer', 'Weight (kg)', 'Battery', 'Price (VND)'
        ]
        out: Dict[str, Optional[str]] = {k: None for k in fields}

        kv_texts = [f"{k}: {v}" for k, v in specs.items() if v]
        all_text = ' '.join([title or ''] + kv_texts + [extra_text or ''])
        all_text_l = all_text.lower()
        title_l = (title or '').lower()

        # ===== Manufacturer
        mbrand = re.match(r'^\s*([A-Za-z]+)', (title or '').strip())
        if mbrand:
            out['Manufacturer'] = mbrand.group(1).lower()
        for k, v in specs.items():
            if re.search(r'^(hãng|thương\s*hiệu|brand|manufacturer|hãng\s*sản\s*xuất)$', k.strip(), re.I):
                out['Manufacturer'] = str(v).strip().lower()
                break

        # ===== CPU
        # Core Ultra
        # Intel N-series (N305, N100, N200)
        n_series = re.search(r'\b(n\d{3,4})\b', all_text_l)
        if n_series:
            out['CPU manufacturer'] = out['CPU manufacturer'] or 'Intel'
            out['CPU brand modifier'] = n_series.group(1).lower()

        # Intel U/P/H mới (1215U, 1315U, 13420H…)
        intel_uph = re.search(r'\b(i[3579])[-\s]*(\d{3,5}[a-z]?)\b', all_text_l, re.I)
        if intel_uph:
            out['CPU manufacturer'] = 'Intel'
            out['CPU brand modifier'] = f"{intel_uph.group(1)}-{intel_uph.group(2)}".lower()
            sn = re.search(r'([1-9]\d{1,3})', intel_uph.group(2))
            if sn:
                s = sn.group(1)
                out['CPU generation'] = s[:2] if len(s) >= 2 else s

        # AMD 7xxxU/H/HS/… (Ryzen 5 7520U, 7730U…)
        amd7 = re.search(r'\bryzen\s*([3579])?\s*(\d{3,4}[a-z]?)\b', all_text_l, re.I)
        if amd7:
            out['CPU manufacturer'] = 'AMD'
            fam = amd7.group(1) or ''
            code = amd7.group(2)
            out['CPU brand modifier'] = f"Ryzen {fam} {code}".strip()
            g = re.match(r'([1-9])', code)
            if g: out['CPU generation'] = g.group(1)

        # Core Ultra 5/7/9
        ultra = re.search(r'\bcore\s*ultra\s*(\d)\b', all_text_l, re.I)
        if ultra:
            out['CPU manufacturer'] = 'Intel'
            out['CPU brand modifier'] = f"Core Ultra {ultra.group(1)}"
            out['CPU generation'] = None  # Ultra không map “gen” kiểu i-series


        sp = re.search(r'(\d+(?:\.\d+)?)\s*ghz', all_text_l)
        if sp:
            out['CPU Speed (GHz)'] = sp.group(1)

        # ===== RAM / Storage (ưu tiên trong title/url)
        m_rs = re.search(r'(\d+)\s*g(b)?\s*[/|\\]\s*(\d+)\s*g(b)?', all_text_l)
        if m_rs:
            out['RAM (GB)'] = m_rs.group(1)
            out['Storage (GB)'] = m_rs.group(3)
        else:
            m_ram = re.search(r'(\d+)\s*gb\s*ram|\bram\s*(\d+)\s*gb', all_text_l)
            if m_ram:
                out['RAM (GB)'] = m_ram.group(1) or m_ram.group(2)
            m_st = re.search(r'(\d+(?:\.\d+)?)\s*(tb|gb)\s*(ssd|hdd|nvme)?', all_text_l, re.I)
            if m_st:
                qty = float(m_st.group(1)); unit = m_st.group(2).lower()
                out['Storage (GB)'] = str(int(qty * 1000) if unit == 'tb' else int(qty))

        # RAM Type + Bus (LPDDR5X-6400, DDR5-5600…)
        m_rtype_bus = re.search(r'\b((?:lp)?ddr[2345x])[-\s]?(\d{3,5})\b', all_text_l, re.I)
        if m_rtype_bus:
            out['RAM Type'] = m_rtype_bus.group(1).upper()
            out['Bus (MHz)'] = m_rtype_bus.group(2)
        else:
            rt = re.search(r'\b(lp)?ddr[2345x]\b', all_text_l, re.I)
            if rt:
                out['RAM Type'] = rt.group(0).upper()
            bus = re.search(r'(\d{3,5})\s*mhz', all_text_l)
            if bus:
                out['Bus (MHz)'] = bus.group(1)

        # ===== Màn hình
        # size: bắt cả dấu ngoặc kép thẳng " và cong ”
        sz = re.search(r'(\d{2}(?:\.\d)?)\s*(?:inch|["”])', all_text_l)
        if sz:
            out['Screen Size (inch)'] = sz.group(1)

        # resolution: số x số
        numres = re.search(r'(\d{3,4})\s*[x×]\s*(\d{3,4})', all_text_l)
        if numres:
            out['Screen Resolution'] = f"{numres.group(1)}x{numres.group(2)}"
        else:
            name_map = [
                (r'(wuxga|fhd\+|1920\s*x\s*1200|1200p)', '1920x1200'),
                (r'(fhd|full\s*hd|1920\s*x\s*1080)', '1920x1080'),
                (r'(qhd|2k|2560\s*x\s*1440|wqhd)', '2560x1440'),
                (r'(wqxga|2560\s*x\s*1600)', '2560x1600'),
                (r'(3k|2880\s*x\s*1800)', '2880x1800'),
                (r'(3\.2k|3200\s*x\s*2000)', '3200x2000'),
                (r'(2\.8k|2880p)', '2880x1800'),
                # CHỈ map 4K khi có số 3840x2160; bỏ "uhd" để tránh false positive
                (r'(3840\s*x\s*2160)', '3840x2160'),
                (r'(wxga|1366\s*x\s*768)', '1366x768')
            ]
            for pat, val in name_map:
                if re.search(pat, all_text_l):
                    out['Screen Resolution'] = val
                    break

        rr = re.search(r'(\d{2,3})\s*hz', all_text_l)
        if rr:
            out['Refresh Rate (Hz)'] = rr.group(1)

        # ===== GPU (rộng hơn: RTX/GTX/MX/ARC/Iris/UHD)
        if re.search(r'\brtx\s*\d{3,4}\b|\bgeforce\b|\bnvidia\b|\bgtx\s*\d{3,4}\b', all_text_l):
            out['GPU manufacturer'] = 'NVIDIA'
        elif re.search(r'\bradeon\b|\b(rx\s*\d{3,4}|vega)\b', all_text_l):
            out['GPU manufacturer'] = 'AMD'
        elif re.search(r'\barc\s*a\d{3,4}\b', all_text_l):
            out['GPU manufacturer'] = 'Intel'
        elif re.search(r'\bintel\b.*\b(iris|xe|uhd|hd)\b', all_text_l):
            out['GPU manufacturer'] = 'Intel'
        elif re.search(r'\bapple\b.*\bm[1234]\b', all_text_l):
            out['GPU manufacturer'] = 'Apple'

        # ===== Map key tiếng Việt → canonical field =====
        vi_map = {
            # RAM
            r'^(ram|bộ nhớ ram)$': 'RAM (GB)',
            r'^(chuẩn ram|loại ram|ram type)$': 'RAM Type',
            r'^(bus ram|tốc độ bus ram)$': 'Bus (MHz)',
            # Storage
            r'^(ổ cứng|lưu trữ|dung lượng lưu trữ|bộ nhớ trong|storage)$': 'Storage (GB)',
            # Màn hình
            r'^(kích thước màn hình|màn hình|độ phân giải|tần số quét)$': None,  # sẽ bắt bằng regex dưới
            # GPU
            r'^(card đồ họa|đồ họa|gpu|vga|card màn hình)$': 'GPU manufacturer',
            # Trọng lượng
            r'^(trọng lượng|khối lượng|trọng lượng\s*cả\s*pin)$': 'Weight (kg)',
            # Pin
            r'^(pin|dung lượng pin|thời lượng pin|battery)$': 'Battery',
            # CPU (thường ít khi đặt đúng chuẩn, vẫn fallback regex ở trên)
        }

        def map_key(k: str) -> Optional[str]:
            k = k.strip().lower()
            for pat, target in vi_map.items():
                if re.match(pat, k, flags=re.I):
                    return target
            return None

        # ƯU TIÊN value đến từ specs (nếu map được)
        for k, v in specs.items():
            tgt = map_key(k)
            if not tgt or not v:
                continue
            s = str(v)

            if tgt == 'RAM (GB)':
                m = re.search(r'(\d+)\s*gb', s, re.I)
                if m: out['RAM (GB)'] = m.group(1)

            elif tgt == 'RAM Type':
                m = re.search(r'(ddr[2345x]|lpddr[45x]?)', s, re.I)
                if m: out['RAM Type'] = m.group(1).upper()

            elif tgt == 'Bus (MHz)':
                m = re.search(r'(\d{3,4})\s*mhz', s, re.I)
                if m: out['Bus (MHz)'] = m.group(1)

            elif tgt == 'Storage (GB)':
                m = re.search(r'(\d+(?:\.\d+)?)\s*(tb|gb)', s, re.I)
                if m:
                    qty = float(m.group(1)); unit = m.group(2).lower()
                    out['Storage (GB)'] = str(int(qty*1000) if unit == 'tb' else int(qty))

            elif tgt == 'GPU manufacturer':
                if re.search(r'\bnvidia\b|rtx|gtx', s, re.I): out['GPU manufacturer'] = 'NVIDIA'
                elif re.search(r'\bradeon\b|\bamd\b', s, re.I): out['GPU manufacturer'] = 'AMD'
                elif re.search(r'\bintel\b.*(iris|xe|uhd|hd)', s, re.I): out['GPU manufacturer'] = 'Intel'
                elif re.search(r'\bapple\b.*m[123]', s, re.I): out['GPU manufacturer'] = 'Apple'

            elif tgt == 'Weight (kg)':
                m = re.search(r'(\d+(?:[\.,]\d+)?)\s*(kg|g)\b', s, re.I)
                if m:
                    val = m.group(1).replace(',', '.'); unit = m.group(2).lower()
                    if unit == 'g':
                        try: val = f"{round(float(val)/1000, 2)}"
                        except: pass
                    out['Weight (kg)'] = val

            elif tgt == 'Battery':
                mwh = re.search(r'(\d+(?:[\.,]\d+)?)\s*wh\b', s, re.I)
                mmah = re.search(r'(\d{4,6})\s*mah\b', s, re.I)
                mcell = re.search(r'(\d+)\s*-?\s*cell\b', s, re.I)
                if mwh: out['Battery'] = f"{mwh.group(1).replace(',', '.')}Wh"
                elif mmah: out['Battery'] = f"{mmah.group(1)}mAh"
                elif mcell: out['Battery'] = f"{mcell.group(1)} cell"

        # ===== Fallback từ toàn văn (nếu vẫn thiếu) =====
        if not out['Weight (kg)']:
            m = re.search(r'(\d+(?:[\.,]\d+)?)\s*kg', all_text_l)
            if m: out['Weight (kg)'] = m.group(1).replace(',', '.')

        if not out['Battery']:
            mwh = re.search(r'(\d+(?:[\.,]\d+)?)\s*wh\b', all_text_l)
            mmah = re.search(r'(\d{4,6})\s*mah\b', all_text_l)
            mcell = re.search(r'(\d+)\s*-?\s*cell\b', all_text_l)
            if mwh: out['Battery'] = f"{mwh.group(1).replace(',', '.')}Wh"
            elif mmah: out['Battery'] = f"{mmah.group(1)}mAh"
            elif mcell: out['Battery'] = f"{mcell.group(1)} cell"

        # ===== Giá
        if price_value is not None:
            out['Price (VND)'] = str(price_value)
        else:
            p = re.search(r'(\d[\d\.,]+)\s*(đ|vnđ|vnd)', all_text_l, re.I)
            if p:
                out['Price (VND)'] = re.sub(r'[^0-9]', '', p.group(1))

        return out




    def parse_specs(self) -> List[Dict[str, Any]]:
        """
        Đọc manifest, parse từng RAW/DETAIL html -> parse_results.json (mạnh).
        """
        manifest_path = 'data/fpt/raw_htmls_manifest.json'
        if not os.path.exists(manifest_path):
            self.log('Manifest not found. Run crawl_raw_htmls() first.', color='red')
            return []

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        results: List[Dict[str, Any]] = []
        for item in manifest:
            if not item.get('Success') or not item.get('Raw_html_path'):
                continue

            try:
                with open(item['Raw_html_path'], 'r', encoding='utf-8') as rf:
                    raw_html = rf.read()

                parsed = self._parse_from_html(raw_html, item.get('Url'))
                # Gắn Manufacturer từ manifest (nếu chưa có trong parsed)
                manu = item.get('Manufacturer') or parsed["features"].get("Manufacturer")
                results.append({
                    "Manufacturer": manu,
                    "Url": item.get('Url'),
                    "Name": parsed.get("name"),
                    "Price (VND)": parsed["features"].get("Price (VND)"),
                    "Specs": parsed.get("specs"),
                    "Features": parsed.get("features")
                })

            except Exception as e:
                self.log(f'Parse error {item.get("Url")}: {e}', color='red')
                continue

        out_path = 'data/fpt/parse_results.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        self.log(f'Parsed {len(results)} items → {out_path}', color='green')

        return results

    # ==========================
    # Step 4: Enhance feature columns
    # ==========================

    def _enhancing_features(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chuẩn hóa 16 cột từ block Features (nếu có) + Specs.
        """
        required_features = {
            'Manufacturer': 1,
            'CPU manufacturer': 2,
            'CPU brand modifier': 3,
            'CPU generation': 4,
            'CPU Speed (GHz)': 5,
            'RAM (GB)': 6,
            'RAM Type': 7,
            'Bus (MHz)': 8,
            'Storage (GB)': 9,
            'Screen Size (inch)': 10,
            'Screen Resolution': 11,
            'Refresh Rate (Hz)': 12,
            'GPU manufacturer': 13,
            'Weight (kg)': 14,
            'Battery': 15,
            'Price (VND)': 16
        }

        feats = product.get("Features") or {}
        specs = product.get("Specs") or {}

        out = {
            "Manufacturer": feats.get("Manufacturer") or product.get("Manufacturer"),
            "CPU manufacturer": feats.get("CPU manufacturer"),
            "CPU brand modifier": feats.get("CPU brand modifier"),
            "CPU generation": feats.get("CPU generation"),
            "CPU Speed (GHz)": feats.get("CPU Speed (GHz)"),
            "RAM (GB)": feats.get("RAM (GB)") or specs.get("RAM") or specs.get("Bộ nhớ RAM"),
            "RAM Type": feats.get("RAM Type") or specs.get("Loại RAM") or specs.get("Chuẩn RAM"),
            "Bus (MHz)": feats.get("Bus (MHz)") or specs.get("Tốc độ Bus RAM") or specs.get("Bus RAM"),
            "Storage (GB)": feats.get("Storage (GB)") or specs.get("Dung lượng lưu trữ") or specs.get("Ổ cứng") or specs.get("Bộ nhớ trong"),
            "Screen Size (inch)": feats.get("Screen Size (inch)") or specs.get("Kích thước màn hình") or specs.get("Màn hình"),
            "Screen Resolution": feats.get("Screen Resolution") or specs.get("Độ phân giải"),
            "Refresh Rate (Hz)": feats.get("Refresh Rate (Hz)") or specs.get("Tần số quét"),
            "GPU manufacturer": feats.get("GPU manufacturer") or specs.get("Card đồ họa") or specs.get("GPU"),
            "Weight (kg)": feats.get("Weight (kg)") or specs.get("Khối lượng") or specs.get("Trọng lượng"),
            "Battery": feats.get("Battery") or specs.get("Dung lượng pin") or specs.get("Pin"),
            "Price (VND)": feats.get("Price (VND)") or product.get("Price (VND)")
        }

        # đảm bảo đủ key & thứ tự
        for k in list(required_features.keys()):
            out.setdefault(k, None)
        out = dict(sorted(out.items(), key=lambda item: required_features[item[0]]))
        return out

    def enhancer(self):
        in_path = 'data/fpt/parse_results.json'
        if not os.path.exists(in_path):
            self.log('parse_results.json chưa có. Hãy chạy parse_specs() trước.', color='red')
            return

        with open(in_path, 'r', encoding='utf-8') as f:
            products = json.load(f)

        results = [self._enhancing_features(p) for p in products]

        out_path = 'data/fpt/all_columns_fpt.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        self.log(f'Enhanced {len(results)} items → {out_path}', color='green')

    # ==========================
    # Step 5: Regex cleaning & CSV
    # ==========================

    def regexing(self, product: Dict[str, Any]) -> Dict[str, Any]:
        def first_num(s: Optional[str], fp=False):
            if not s:
                return None
            m = re.findall(r"\d+(?:\.\d+)?", str(s))
            if not m:
                return None
            return float(m[0]) if fp else int(float(m[0]))

        price_val = None
        if product.get('Price (VND)'):
            raw = str(product['Price (VND)']).replace('₫', '').replace('.', '').replace(',', '')
            m = re.findall(r"\d+", raw)
            if m:
                price_val = int(m[0])

        res = product.get('Screen Resolution')
        if res:
            m = re.findall(r"\d+\s*x\s*\d+", str(res).lower())
            res = m[0].replace(" ", "") if m else None

        gpu = product.get('GPU manufacturer') or ''
        mfg_gpu = None
        if re.search(r"nvidia", str(gpu), re.I):
            mfg_gpu = "NVIDIA"
        elif re.search(r"amd|radeon", str(gpu), re.I):
            mfg_gpu = "AMD"
        elif re.search(r"intel", str(gpu), re.I):
            mfg_gpu = "Intel"
        elif re.search(r"apple", str(gpu), re.I):
            mfg_gpu = "Apple"

        return {
            "Manufacturer": product.get('Manufacturer'),
            "CPU manufacturer": product.get('CPU manufacturer'),
            "CPU brand modifier": product.get('CPU brand modifier'),
            "CPU generation": first_num(product.get('CPU generation')),
            "CPU Speed (GHz)": first_num(product.get('CPU Speed (GHz)'), fp=True),
            "RAM (GB)": first_num(product.get('RAM (GB)')),
            "RAM Type": product.get('RAM Type'),
            "Bus (MHz)": first_num(product.get('Bus (MHz)')),
            "Storage (GB)": first_num(product.get('Storage (GB)')),
            "Screen Size (inch)": first_num(product.get('Screen Size (inch)'), fp=True),
            "Screen Resolution": res,
            "Refresh Rate (Hz)": first_num(product.get('Refresh Rate (Hz)')),
            "GPU manufacturer": mfg_gpu or product.get('GPU manufacturer') or 'Intel',
            "Weight (kg)": first_num(product.get('Weight (kg)'), fp=True),
            "Battery": first_num(product.get('Battery')),
            "Price (VND)": price_val
        }


# ==========================
# Main runner
# ==========================

# ==========================
# Quick test với 1–2 link
# ==========================

def _fetch_html_requests(url: str) -> Optional[str]:
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120 Safari/537.36"),
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=25)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def _fetch_html_selenium(url: str, headless: bool = True) -> Optional[str]:
    try:
        driver = ChromeDriver(headless=headless).driver
        driver.get(url)
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(1.2)  # đợi JS render
        html = driver.page_source
        try:
            driver.quit()
        except Exception:
            pass
        return html
    except Exception:
        return None

def quick_test_two_links(urls: List[str], use_selenium_fallback: bool = True, headless: bool = True):
    os.makedirs('data/fpt/_test', exist_ok=True)
    results = []
    for i, url in enumerate(urls, 1):
        Fpt.log(None, f'[TEST] Loading #{i}: {url}')
        raw_html = _fetch_html_requests(url)
        if (not raw_html or len(raw_html) < 20000) and use_selenium_fallback:
            Fpt.log(None, f'[TEST] Requests HTML ít dữ liệu → thử Selenium headless...', color='yellow')
            raw_html = _fetch_html_selenium(url, headless=headless)

        if not raw_html:
            Fpt.log(None, f'[TEST-ERR] Không tải được HTML: {url}', color='red')
            continue

        # Lưu html thô để soi nhanh
        out_html = f'data/fpt/_test/test_{i}.html'
        with open(out_html, 'w', encoding='utf-8') as f:
            f.write(raw_html)

        try:
            parsed = Fpt._parse_from_html(raw_html, url)
            results.append(parsed)
            # In nhanh các feature chính để bạn đánh giá
            feats = parsed.get('features', {})
            Fpt.log(None, f"[TEST-OK #{i}] Name: {parsed.get('name')}", color='green')
            Fpt.log(None, f"  Price (VND): {feats.get('Price (VND)')}", color='green')
            Fpt.log(None, f"  CPU: {feats.get('CPU manufacturer')} | {feats.get('CPU brand modifier')} | Gen {feats.get('CPU generation')}", color='green')
            Fpt.log(None, f"  RAM: {feats.get('RAM (GB)')} {feats.get('RAM Type')} Bus {feats.get('Bus (MHz)')}", color='green')
            Fpt.log(None, f"  Storage: {feats.get('Storage (GB)')} GB", color='green')
            Fpt.log(None, f"  Screen: {feats.get('Screen Size (inch)')}\" {feats.get('Screen Resolution')} @ {feats.get('Refresh Rate (Hz)')} Hz", color='green')
            Fpt.log(None, f"  GPU: {feats.get('GPU manufacturer')}", color='green')
        except Exception as e:
            Fpt.log(None, f'[TEST-ERR] {url}: {e}', color='red')

    # Lưu JSON kết quả test
    out_json = 'data/fpt/test_results.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    Fpt.log(None, f'Saved {out_json}', color='green')


def safe_load_json(path: str, default):
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return default
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'[WARN] Cannot load JSON {path}: {e}')
        return default 


# if __name__ == '__main__':
#     # ===== Chế độ TEST CHỈ 1–2 LINK =====
#     TEST_URLS = [
#         "https://fptshop.com.vn/may-tinh-xach-tay/asus-vivobook-go-15-e1504ga-bq1141w-i3-n305",
#         "https://fptshop.com.vn/may-tinh-xach-tay/asus-vivobook-gaming-k3605vc-rp431w-i5-13420h",
#         "https://fptshop.com.vn/may-tinh-xach-tay/lenovo-ideapad-slim-3-14irh10-83k00008vn",
#         "https://fptshop.com.vn/may-tinh-xach-tay/msi-gaming-katana-15-b13vfk-676vn-i7-13620h"
#     ]
#     quick_test_two_links(TEST_URLS, use_selenium_fallback=True, headless=True)

#     # ===== Nếu muốn chạy pipeline đầy đủ thì bật các dòng dưới đây =====
#     fpt = Fpt(headless=True)
#     fpt.get_all_product_links()
#     fpt.crawl_raw_htmls()
#     fpt.parse_specs()
#     fpt.enhancer()
#     products = safe_load_json('data/fpt/all_columns_fpt.json', default=[])
#     if products:
#         cleaned = [fpt.regexing(p) for p in products]
#         import pandas as pd
#         pd.DataFrame(cleaned).to_csv('data/fpt/fpt.csv', index=False)
#         print('Saved CSV to data/fpt/fpt.csv')




if __name__ == '__main__':
    # Nếu site chặn headless, thử headless=False để test lần đầu
    fpt = Fpt(headless=True)

    # 1) Lấy link sản phẩm (tối đa 5 trang/brand)
    fpt.get_all_product_links()

    # 2) Tải RAW + DETAIL HTML (reuse 1 driver/brand)
    fpt.crawl_raw_htmls()

    # 3) Parse specs (mạnh)
    fpt.parse_specs()

    # 4) Chuẩn hóa 16 cột
    fpt.enhancer()

    # 5) Regex cleaning + CSV (không cần polars)
    products = safe_load_json('data/fpt/all_columns_fpt.json', default=[])
    if not products:
        print('File all_columns_fpt.json rỗng/chưa có. Hãy chạy enhancer() sau khi parse.')
    else:
        cleaned = [fpt.regexing(p) for p in products]
        import pandas as pd
        os.makedirs('data/fpt', exist_ok=True)
        pd.DataFrame(cleaned).to_csv('data/fpt/fpt.csv', index=False)
        print('Saved CSV to data/fpt/fpt.csv')