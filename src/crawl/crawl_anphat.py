import os
import sys
sys.path.append(os.getcwd())  # NOQA

import json
import time
import traceback
import re
from source.utils.selenium import ChromeDriver # Giả định bạn có file này

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from source.crawl.base_crawler import BaseCrawler # Sửa đường dẫn nếu cần
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

class Anphat(BaseCrawler):

    def __init__(self, headless: bool = True):
        # 1. Đọc file config mới (anphat.json)
        self.config = self.load_config('anphat.json') 
        self.headless = headless
        self.log("Anphat Crawler khởi tạo.")
        # Không cần kết nối DB (theo logic crawl_ap.py)

    # ----------------- 1. Get all product links -----------------

    def __parse_product_links(self, page_source: str) -> list:
            """Trích xuất URL sản phẩm từ HTML trang danh mục."""
            urls = []
            try:
                soup = bs(page_source, 'html.parser')
                
                # 1. Tìm khối container chính (để giới hạn phạm vi tìm kiếm)
                product_list_div = soup.select_one('div.p-list-container.d-flex.flex-wrap')

                if product_list_div:
                    # 2. SỬA LỖI: Tìm TẤT CẢ các div con của TỪNG SẢN PHẨM
                    # Dựa trên phân tích của bạn, chúng ta tìm các khối item riêng lẻ.
                    # Phỏng đoán class của item là 'div.product' (rất phổ biến)
                    product_items = product_list_div.select('div.p-item.js-p-item.summary-loaded') 
                    
                    self.log(f"Tìm thấy {len(product_items)} khối 'div.p-item.js-p-item.summary-loaded'.")

                    # === PHƯƠNG ÁN DỰ PHÒNG ===
                    # Nếu 'div.product' không trả về gì, có thể class là 'product-item'
                    if not product_items:
                        product_items = product_list_div.select('div.product-item') 
                        self.log(f"Không tìm thấy 'div.product', thử 'div.product-item', tìm thấy: {len(product_items)}.")
                    
                    if not product_items:
                        self.log("LỖI: Không tìm thấy BẤT KỲ khối sản phẩm con nào (đã thử 'div.product' và 'div.product-item').", color='red')

                    # 3. Lặp qua TỪNG khối sản phẩm
                    for item_div in product_items:
                        # 4. Tìm thẻ <a> BÊN TRONG mỗi khối đó
                        # Ta bỏ bớt '.button__link' để tăng khả năng tìm thấy,
                        # vì 'a.product__link' có vẻ là selector quan trọng nhất.
                        #item = item_div.select_one('div.product-info')
                        link_tag = item_div.select_one('a.p-img, a.product__link')
                        
                        if link_tag:
                            print("sucess")
                            href = link_tag.get('href')
                            href = "https://www.anphatpc.com.vn" + href if href else None
                            print(href)
                            if href:
                                url = f'{href}'
                                print (url)
                                if url.endswith('.html') and ('laptop' in url or 'macbook' in url):
                                    urls.append(url)
                        else:
                            # Bỏ qua item này nếu không có link (có thể là quảng cáo, v.v.)
                            pass
                else:
                    self.log("Không tìm thấy khối container 'product_list_div'.", color='red')
                
                urls = list(dict.fromkeys(urls)) # Loại bỏ trùng lặp
                
            except Exception as e:
                self.log(f'Lỗi khi parse links: {traceback.format_exc()}', color='red')
            finally:
                self.log(f'Tìm thấy {len(urls)} links sản phẩm')
            return urls

    def get_all_product_links(self):
        """
        Lặp qua từng HÃNG SẢN XUẤT trong config để lấy link.
        (Đã cập nhật logic chờ và "Xem thêm")
        """
        self.log('Bắt đầu lấy links sản phẩm...', color='yellow')
        driver = ChromeDriver(headless=self.headless).driver
        
        all_links = {} 

        for manufacturer, url in self.config.items():
            self.log(f"--- Đang xử lý hãng: {manufacturer.upper()} ---")
            driver.get(url)
            
            try:
                # SỬA LỖI: Chờ đúng khối container sản phẩm
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.p-list-container.d-flex.flex-wrap'))
                )
                self.log(f'Đã tải trang {manufacturer}.')
            except Exception:
                self.log(f"Không tìm thấy sản phẩm cho: {manufacturer} (Timeout khi chờ).", color='red')
                all_links[manufacturer] = []
                continue

            # --- THÊM LẠI LOGIC "XEM THÊM" ---
            # Trang của từng hãng cũng có nút "Xem thêm"
            # --- THÊM LẠI LOGIC "XEM THÊM" ---
            while True:
                try:
                    # 1. Chờ cho nút TỒN TẠI (chưa cần click được)
                    show_more_btn = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'btn-view-more'))
                    )
                    
                    # 2. CẢI THIỆN LOGIC DỪNG: Kiểm tra cả style và thuộc tính 'disabled'
                    style = show_more_btn.get_attribute('style')
                    is_disabled = show_more_btn.get_attribute('disabled') # (Trả về 'true' hoặc None)

                    if (style and "display: none" in style) or is_disabled:
                        self.log('Không còn nút "Xem thêm" (bị ẩn hoặc vô hiệu hóa).', color='green')
                        break
                        
                    # 3. SỬA LỖI QUAN TRỌNG: Cuộn nút vào tầm nhìn
                    # (true = cuộn lên đầu màn hình, false = cuộn xuống cuối màn hình)
                    driver.execute_script("arguments[0].scrollIntoView(false);", show_more_btn)
                    self.log('Đã cuộn tới nút "Xem thêm".')
                    time.sleep(0.5) # Chờ 0.5s để cuộn và các hiệu ứng (nếu có) hoàn tất

                    # 4. SỬA LỖI CLICK: Chờ click được VÀ click ngay
                    # Cách này an toàn hơn là tách 'wait' và 'click'
                    WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable(show_more_btn)
                    ).click()
                    
                    self.log('Đã nhấp "Xem thêm" (Click của Selenium)...')
                    time.sleep(2) # Chờ 2 giây để sản phẩm tải
                    
                except Exception as e:
                    # Ghi log rõ hơn về lý do dừng
                    if 'TimeoutException' in str(e):
                        self.log('Kết thúc "Xem thêm" (Không tìm thấy nút sau 5s).')
                    else:
                        self.log(f'Kết thúc "Xem thêm" (Lỗi: {e.__class__.__name__})')
                    break
            # --- KẾT THÚC LOGIC "XEM THÊM" ---
            # --- KẾT THÚC LOGIC "XEM THÊM" ---

            self.log('Đang phân tích (parsing) source trang...')
            urls = self.__parse_product_links(driver.page_source)
            all_links[manufacturer] = urls
        
        driver.quit()

        # Lưu kết quả
        save_dir = 'data/anphat'
        os.makedirs(save_dir, exist_ok=True)
        out_path = os.path.join(save_dir, 'anphat_product_links.json')
        
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(all_links, f, indent=4, ensure_ascii=False)
            
        self.log(f'========>> Đã lưu links vào: {out_path}', color='green')

    # ----------------- 2. Fetch all raw_htmls -----------------
    
    # SỬA: Hàm này giờ NHẬN driver làm tham số
    def __fetch_html(self, driver, url: str, manufacturer: str, idx: int) -> dict | None:
        """Cào HTML thô, specs (modal hoặc table) và giá sản phẩm từ anphat."""
        try:
            driver.get(url)
            time.sleep(2)

            # ----------------------
            # 1. LẤY GIÁ NIÊM YẾT
            XPATH_NIEMYET_PRICE = "//td[contains(text(), 'Giá niêm yết:')]/following-sibling::td/del"

            niemyet_price_text = None

            try:
                # Tìm kiếm phần tử bằng XPath
                elem = driver.find_element(By.XPATH, XPATH_NIEMYET_PRICE) 
                
                # Lấy nội dung văn bản
                if elem.text.strip():
                    niemyet_price_text = elem.text.strip()
                    print(f"Giá niêm yết tìm thấy (Text): {niemyet_price_text}")

            except Exception as e:
                print(f"Không tìm thấy giá niêm yết bằng XPath: {e}")
                
            # 2. Làm sạch và Chuyển đổi thành số
            if niemyet_price_text:
                # Loại bỏ dấu chấm (.), khoảng trắng và ký tự 'đ'
                cleaned_price = re.sub(r'[.\sđ]', '', niemyet_price_text)
                
                try:
                    # Chuyển đổi thành số nguyên
                    final_price_number = int(cleaned_price)
                    print(f"Giá niêm yết dạng số: {final_price_number}") # Output: 32990000
                except ValueError:
                    print("Không thể chuyển đổi giá trị đã làm sạch thành số.")

            # ----------------------
            # 2. SCROLL ĐẾN THÔNG SỐ KỸ THUẬT
            # ----------------------
            try:
                tech_block = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-spec-group.mb-4.font-300"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tech_block)
                time.sleep(1.5)
            except Exception as e:
                self.log(f"Không tìm thấy khối thông số: {e}", color='red')

            # ----------------------
            # 3. CLICK NÚT "XEM TẤT CẢ"
            # ----------------------
            modal_opened = False
            detail_html = None

            try:
                show_btn_xpath = "//a[contains(., 'XEM THÊM THÔNG SỐ')]" 
    
                # Chờ nút xuất hiện và có thể tương tác (visibility_of_element_located)
                show_btn = WebDriverWait(driver, 15).until(
                    EC.visibility_of_element_located((By.XPATH, show_btn_xpath))
                )
                
                # Cuộn vào giữa màn hình để đảm bảo nút hiển thị và không bị che
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", show_btn)
                time.sleep(0.4)
                
                # Click nút bằng Selenium's .click() hoặc JavaScript (để vượt qua các vấn đề click)
                show_btn.click() 
                
                modal_opened = True
                time.sleep(1.5)
                
            except Exception as e:
                # self.log(f"Không click được nút XEM THÊM THÔNG SỐ: {e}", color='yellow')
                print(f"Không click được nút XEM THÊM THÔNG SỐ: {e}") # Sử dụng print nếu không có hàm self.log

            # ----------------------
            # 4. LẤY SPECS (MODAL HOẶC BẢNG)
            # ----------------------
            detail_html = None
            MAX_SCROLL_ATTEMPTS = 20

            if modal_opened:
                try:
                    # Selector mới: Nhắm thẳng vào thẻ <table> bên trong div#pro-spec
                    # Sử dụng CSS Selector: div#pro-spec table
                    TABLE_SELECTOR = "div#pro-spec table"
                    
                    # Chờ thẻ table xuất hiện trong DOM
                    table_elem = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_SELECTOR))
                    )
                    
                    # ⚠️ QUAN TRỌNG: Nếu bảng vẫn cần cuộn bên trong div#pro-spec
                    # (Thường thì chỉ cần cuộn nếu nội dung div#pro-spec quá lớn)
                    # Bạn có thể giữ lại logic cuộn nếu cần, nhưng phải cuộn thẻ div#pro-spec
                    # Tốt nhất là bạn nên tìm lại thẻ div#pro-spec để cuộn:
                    
                    pro_spec_div = driver.find_element(By.CSS_SELECTOR, "div#pro-spec")
                    last_height = 0
                    for i in range(MAX_SCROLL_ATTEMPTS):
                        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", pro_spec_div)
                        time.sleep(0.3)
                        new_height = driver.execute_script("return arguments[0].scrollHeight;", pro_spec_div)
                        if new_height == last_height:
                            break
                        last_height = new_height
                    
                    # Lấy toàn bộ HTML của TABLE
                    # Dùng .get_attribute("outerHTML") để lấy cả thẻ <table>
                    detail_html = table_elem.get_attribute("outerHTML")
                    # self.log("Đã lấy thành công HTML của bảng specs.", color='blue')

                except Exception as e:
                    # self.log(f"Không lấy được table specs: {e}", color='red')
                    print(f"Không lấy được table specs: {e}")
                    
            # --------------------
            # FALLBACK: Phần fallback có thể không cần thiết nếu logic trên hoạt động
            # --------------------
            if detail_html is None:
                # Bạn có thể bỏ qua phần này nếu bạn tin tưởng vào selector TABLE_SELECTOR ở trên
                try:
                    # Fallback có thể tìm kiếm bất kỳ bảng specs nào khác
                    table = driver.find_element(By.CSS_SELECTOR, "table.technical-content")
                    detail_html = table.get_attribute("outerHTML")
                except Exception as e:
                    # self.log(f"Không tìm thấy specs (table): {e}", color='red')
                    print(f"Không tìm thấy specs (table): {e}")
                    detail_html = ""

            # ----------------------
            # 5. LƯU RAW HTML VÀ DETAIL HTML
            # ----------------------
            raw_html = driver.page_source

            raw_dir = 'data/anphat/raw_htmls'
            detail_dir = 'data/anphat/detail_htmls'

            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(detail_dir, exist_ok=True)

            raw_path = os.path.join(raw_dir, f"{manufacturer}_{idx}.html")
            detail_path = os.path.join(detail_dir, f"{manufacturer}_{idx}_specs.html")

            with open(raw_path, 'w', encoding='utf-8') as f:
                f.write(raw_html)

            with open(detail_path, 'w', encoding='utf-8') as f:
                f.write(detail_html)

            # ----------------------
            # 6. TRẢ KẾT QUẢ
            # ----------------------
            return {
                'manufacturer': manufacturer,
                'url': url,
                'saved_path': raw_path,
                'detail_specs_html_path': detail_path,
                'price': final_price_number
            }

        except Exception as e:
            self.log(f"Lỗi khi cào {url}: {e}", color='red')
            return None





    def extract_price(self, html):
        soup = bs(html, "html.parser")

        # Ưu tiên cách mới
        price = soup.select_one(".product__price--show")

        # Nếu không thấy, thử fallback
        if not price:
            price = soup.select_one("span.product__price--show")

        if not price:
            return None

        text = price.get_text(strip=True)
        clean = (
            text.replace("₫", "")
                .replace(".", "")
                .replace(",", "")
                .strip()
        )

        try:
            return int(clean)
        except:
            return None

    def crawl_raw_htmls(self):
        """Cào HTML thô và chi tiết cho tất cả sản phẩm bằng đa luồng."""

        links_path = 'data/anphat/anphat_product_links.json'
        if not os.path.exists(links_path):
            self.log(f'File links không tìm thấy: {links_path}. Hãy chạy get_all_product_links() trước.', color='red')
            return

        with open(links_path, 'r', encoding='utf-8') as f:
            product_links = json.load(f)

        manifest = []

        for manufacturer, urls in product_links.items():

            self.log(f'========>> Bắt đầu cào HTML của {manufacturer.upper()} (total {len(urls)})',
                    color='yellow')

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []

                for idx, url in enumerate(urls):
                    # dùng worker wrapper
                    futures.append(
                        executor.submit(self._fetch_html_worker, url, manufacturer, idx)
                    )

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        manifest.append(result)

        # Lưu manifest
        manifest_path = 'data/anphat/raw_htmls_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        self.log(f'Đã lưu manifest: {manifest_path}', color='green')
    def _fetch_html_worker(self, url, manufacturer, idx):
        """Worker: tạo driver riêng, fetch, rồi đóng."""
        driver = None
        try:
            driver = ChromeDriver(headless=self.headless).driver
            result = self.__fetch_html(driver, url, manufacturer, idx)
            return result
        except Exception as e:
            self.log(f"Lỗi khi cào {url}: {e}", color="red")
            return None
        finally:
            if driver:
                driver.quit()

    def parse_specs(self):

        self.log('Chưa hoàn thiện logic parsing cho anphat.', color='yellow')

        # ... (Cần code parsing mới cho HTML chi tiết của anphat) ...



if __name__ == "__main__":
    # 1. Chạy để lấy links (Dùng headless=False để dễ debug)
    #crawler_links = Anphat(headless=False) 
    #crawler_links.get_all_product_links() 

    # 2. Chạy để cào HTML (sau khi có file links)
    crawler_html = Anphat(headless=True) # Dùng True để chạy ngầm
    crawler_html.crawl_raw_htmls()