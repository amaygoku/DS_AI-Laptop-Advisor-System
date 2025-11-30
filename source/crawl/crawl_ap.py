import pandas as pd
import polars as pl
import json
import os
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 1. Định nghĩa các trường thông tin cần thiết ---
REQUIRED_FEATURES = [
    "Manufacturer", "CPU manufacturer", "CPU brand modifier", "CPU generation",
    "CPU Speed (GHz)", "RAM (GB)", "RAM Type", "Bus (MHz)", "Storage (GB)",
    "Screen Size (inch)", "Screen Resolution", "Refresh Rate (Hz)",
    "GPU manufacturer", "Weight (kg)", "Battery", "Price (VND)"
]

# --- 2. Hàm Trích xuất Thông số Kỹ thuật (Sử dụng 2 tham số) ---

def extract_anphat_features(html_content: str, manufacturer: str) -> dict:
    """
    Sử dụng BeautifulSoup và Regex để trích xuất và chuẩn hóa 16 đặc trưng
    từ HTML thô của trang An Phát PC.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Khởi tạo dict kết quả và gán Manufacturer
    product = {feature: None for feature in REQUIRED_FEATURES}
    product['Manufacturer'] = manufacturer.capitalize()
    
    # Khai báo các biến lưu thông tin thô
    cpu = ram = storage = screen = battery = weight = vga = None

    # --- 2.1 Trích xuất Thông số Thô từ Khối "pro-info-summary" ---
    specs_from_html = [span.get_text(strip=True) for span in soup.select('div.pro-info-summary span.item')]
    
    try:
        # CPU Name: Thường là item đầu tiên
        cpu_text = specs_from_html[0].replace("CPU: ", "")
        cpu = cpu_text.replace("-", " ").replace("™", "").replace("®", "").replace("  ", " ").lower()

        for item in specs_from_html[1:]:
            if "RAM:" in item:
                ram = item.replace("RAM:", "").replace("-", " ").lower()
            elif "Ổ cứng:" in item:
                storage = item.replace("Ổ cứng:", "").lower()
            elif "Màn hình:" in item:
                screen = item.replace("Màn hình:", "").lower()
            elif "Pin:" in item:
                battery = item.replace("Pin:", "").lower().replace("whrs", "wh").replace("whr", "wh")
            elif "Cân nặng:" in item:
                weight = item.replace("Cân nặng:", "").lower()
            elif "VGA:" in item:
                vga = item.replace("VGA:", "").lower()
                
    except IndexError:
        pass
    
    # --- 2.2 Trích xuất Giá (Price) ---
    price = None
    try: 
        # Giá gốc (đã gạch) nằm trong thẻ <del class='font-500'>
        price_del = soup.find('del', class_='font-500')
        if price_del:
            price_text = price_del.get_text(strip = True).replace('.','').replace(' đ','')
            price = int(re.search(r'\d+', price_text).group(0))
    except Exception:
        # Nếu không có giá gốc, Price (VND) sẽ là None (hoặc bạn có thể thêm logic lấy giá hiện tại)
        pass 
        
    product['Price (VND)'] = price
    
    # --- 2.3 Áp dụng Regex và Chuẩn hóa các đặc trưng còn lại ---

    if cpu:
        # Logic CPU (Manufacturer, Brand Modifier, Generation, Speed)
        if "intel" in cpu:
            product['CPU manufacturer'] = "Intel"
            cbm_match = re.search(r'i([3579])', cpu)
            if cbm_match: product['CPU brand modifier'] = int(cbm_match.group(1))
            
            cg_match = re.search(r'i[3579]-?(\d{2})\d{2}[a-z]', cpu)
            if cg_match: product['CPU generation'] = int(cg_match.group(1))
            else:
                cg_match = re.search(r'\s(\d{4,5})[a-z]{1,2}', cpu)
                if cg_match: product['CPU generation'] = int(cg_match.group(1)[:2])
        
        elif "ryzen" in cpu or "amd" in cpu:
            product['CPU manufacturer'] = "AMD"
            cbm_match = re.search(r'ryzen\s+([3579])', cpu)
            if cbm_match: product['CPU brand modifier'] = int(cbm_match.group(1))
            
            cg_match = re.search(r'(\d)\d{3}[a-z]{1,2}', cpu)
            if cg_match: product['CPU generation'] = int(cg_match.group(1))
        
        cs_match = re.search(r'to\s+(\d+(\.\d+)?)\s*ghz', cpu)
        if cs_match: product['CPU Speed (GHz)'] = float(cs_match.group(1))
        else:
            cs_match = re.search(r'(\d+(\.\d+)?)\s*ghz', cpu)
            if cs_match: product['CPU Speed (GHz)'] = float(cs_match.group(1))

    # RAM (GB), RAM Type, Bus (MHz)
    if ram:
        ram_match = re.search(r'(\d+)\s*gb', ram)
        if ram_match: product['RAM (GB)'] = int(ram_match.group(1))
        
        ram_types = ["ddr4", "lpddr4", "lpddr4x", "ddr5", "lpddr5", "lpddr5x"]
        for r_type in ram_types:
            if r_type in ram: product['RAM Type'] = r_type.upper(); break
        
        bus_match = re.search(r'(\d{4})', ram)
        if bus_match: product['Bus (MHz)'] = int(bus_match.group(1))

    # Storage (GB)
    if storage:
        storage_match = re.search(r'(\d+)\s*(gb|tb)', storage)
        if storage_match:
            storage_value = int(storage_match.group(1))
            unit = storage_match.group(2)
            if unit == "tb": product['Storage (GB)'] = storage_value * 1024 
            else: product['Storage (GB)'] = storage_value

    # Screen Size (inch), Resolution, Refresh Rate (Hz)
    if screen:
        ss_match = re.search(r'(\d+(\.\d+)?)', screen)
        if ss_match:
            screen_size = float(ss_match.group(1))
            if 10 < screen_size < 50: product['Screen Size (inch)'] = screen_size
        
        sr_match = re.search(r'(\d+)\s*x\s*(\d+)', screen)
        if sr_match: product['Screen Resolution'] = f"{sr_match.group(1)}x{sr_match.group(2)}"
            
        rr_match = re.search(r'(\d+)\s*hz', screen)
        if rr_match: product['Refresh Rate (Hz)'] = int(rr_match.group(1))
        elif screen: product['Refresh Rate (Hz)'] = 60 

    # GPU manufacturer
    if vga:
        gpu_manufacturers = ['NVIDIA', 'AMD', 'Intel', 'GeForce']
        for g_man in gpu_manufacturers:
            if g_man.lower() in vga:
                product['GPU manufacturer'] = "Nvidia" if g_man == "GeForce" else g_man
                break
        if not product['GPU manufacturer'] and product['CPU manufacturer'] == "Intel":
             product['GPU manufacturer'] = "Intel" 

    # Weight (kg)
    if weight:
        w_match_kg = re.search(r'(\d+(\.\d+)?)\s*kg', weight)
        w_match_g = re.search(r'(\d+(\.\d+)?)\s*g', weight)
        if w_match_kg: product['Weight (kg)'] = float(w_match_kg.group(1))
        elif w_match_g: product['Weight (kg)'] = float(w_match_g.group(1)) / 1000

    # Battery (Wh)
    if battery:
        b_match = re.search(r'(\d+(\.\d+)?)\s*wh', battery)
        if b_match: product['Battery'] = float(b_match.group(1))
        elif 'cell' in battery: product['Battery'] = None 

    return product

# --- 3. Hàm Quản lý Đọc File và Xử lý Đa luồng (Đã sửa lỗi) ---

def process_anphat_manifest(manifest_path: str, raw_html_dir: str) -> list:
    """
    Đọc manifest, xử lý lỗi KeyError và gọi hàm trích xuất.
    Sử dụng khóa 'saved_path' và 'manufacturer' từ manifest của bạn.
    """
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
    except FileNotFoundError:
        print(f"DEBUG ERROR: Không tìm thấy Manifest tại: {manifest_path}")
        return []
    except json.JSONDecodeError:
        print("DEBUG ERROR: Lỗi đọc file JSON manifest (File bị rỗng hoặc hỏng).")
        return []
    
    # Nếu Manifest là Dict (format cũ), chuyển nó thành List
    if isinstance(manifest_data, dict):
        all_records = []
        for manufacturer, records in manifest_data.items():
            for record in records:
                record['manufacturer'] = manufacturer
                all_records.append(record)
        manifest_data = all_records
    
    results = []
    
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = []
        
        for record in manifest_data:
            try:
                # SỬ DỤNG KHÓA ĐƯỢC LƯU TRONG CRAWL_AP.PY
                manufacturer = record['manufacturer']
                # Lấy đường dẫn file đã lưu (là saved_path)
                raw_html_path = record['saved_path'] 
            except KeyError as e:
                print(f"DEBUG ERROR: Lỗi KeyError {e} trong Manifest. Bỏ qua bản ghi.")
                continue

            # Xử lý đường dẫn: Manifest của bạn lưu đường dẫn đầy đủ, 
            # nhưng ta cần đảm bảo nó trỏ đúng nếu đường dẫn tương đối bị thay đổi
            # Nếu saved_path là đường dẫn tuyệt đối (VD: D:\...) thì không cần os.path.join
            if not os.path.isabs(raw_html_path):
                # Nếu saved_path là tương đối (VD: data/anphat/raw_htmls/...), ta dùng nó trực tiếp
                full_path = raw_html_path 
            else:
                 # Nếu saved_path là tuyệt đối, ta dùng nó trực tiếp
                full_path = raw_html_path
            
            if os.path.exists(full_path):
                # FIX LỖI: Gọi hàm extract_anphat_features với chỉ 2 tham số
                futures.append(executor.submit(
                    _read_and_extract_anphat, full_path, manufacturer
                ))

        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
            
    return results

def _read_and_extract_anphat(file_path, manufacturer):
    """ Hàm đọc file và gọi hàm trích xuất """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        # SỬA LỖI: Chỉ truyền 2 tham số: html_content và manufacturer
        # An Phát PC không cần file HTML specs riêng, trang chính chứa tất cả.
        return extract_anphat_features(html_content, manufacturer) 
        
    except Exception as e:
        print(f"Error reading or parsing {file_path}: {e}")
        return None

# --- 4. Hướng dẫn sử dụng trong __main__ ---

if __name__ == '__main__':
    # 1. Cấu hình đúng đường dẫn (từ thư mục gốc dự án)
    MANIFEST_FILE = 'data/anphat/raw_htmls_manifest.json' 
    # RAW_HTML_DIR không cần thiết vì saved_path đã là đường dẫn đầy đủ (hoặc tương đối)
    # OUTPUT_CSV phải là nơi bạn muốn lưu file CSV
    OUTPUT_CSV = 'data/anphat/anphat_processed_features.csv'
    
    print("--- BẮT ĐẦU TRÍCH XUẤT ĐẶC TRƯNG AN PHÁT PC ---")
    
    final_data = process_anphat_manifest(
        manifest_path=MANIFEST_FILE, 
        raw_html_dir='.' # Truyền thư mục gốc (hoặc bất kỳ ký tự nào, vì logic sửa đã bỏ qua nó)
    )
    
    if final_data:
        # Tạo thư mục data/anphat nếu chưa có
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        
        df = pl.DataFrame(final_data)
        df.write_csv(OUTPUT_CSV)
        
        print(f"\n✅ HOÀN THÀNH. Đã xử lý {len(df)} sản phẩm và lưu vào {OUTPUT_CSV}")
    else:
        print("❌ KHÔNG CÓ DỮ LIỆU ĐỂ XỬ LÝ. KIỂM TRA LẠI FILE MANIFEST VÀ CẤU TRÚC FOLDER.")