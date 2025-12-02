import os
import json
import re
import csv
from pathlib import Path
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
OUT_JSON_DIR = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\anphat\parsed_products_json"
OUT_CSV = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\anphat\parsed_products.csv"

CSV_FIELDS = [
    "Product Name","Manufacturer","CPU manufacturer","CPU brand modifier","CPU generation",
    "CPU Speed (GHz)","RAM (GB)","RAM Type","Bus (MHz)","Storage (GB)",
    "Screen Size (inch)","Screen Resolution","Refresh Rate (Hz)","GPU manufacturer",
    "Weight (kg)","Battery","Price (VND)","url","saved_path","detail_specs_html_path"
]


# ---------- Helpers tên & file ----------

def extract_name_from_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return "" 
    slug = url.rstrip("/").split("/")[-1]
    if slug.endswith(".html"):
        slug = slug[:-5]
    name = slug.replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    # Title-case but giữ các brand / acronyms
    name = " ".join([
        w.upper() if w.lower() in (
            "hp","lenovo","dell","acer","asus","macbook","msi",
            "gigabyte","rtx","ryzen","intel","amd"
        ) else w.capitalize()
        for w in name.split()
    ])
    return name

def clean_product_name(name: str) -> str:
    parts = name.split()
    if parts and parts[0].lower() == "laptop":
        parts = parts[1:]
    return " ".join(parts)

def load_file_text(path):
    if not isinstance(path, (str, Path)) or not path:
        return None
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def parse_price_to_int(price_raw):
    if not price_raw:
        return None
    if not isinstance(price_raw, str):
        price_raw = str(price_raw)
    numbers = re.sub(r"[^\d]", "", price_raw)
    return int(numbers) if numbers else None


# ---------- Các hàm parse spec từ HTML (logic chuẩn hơn) ----------

def parse_manufacturer(text: str):
    if not text:
        return None
    parts = text.replace("Laptop", "").strip().split()
    return parts[-1] if parts else text.strip()


def parse_cpu_fields(cpu_info: str):
    """
    Trích xuất Nhà sản xuất, Phân khúc, và Mã SKU/Thế hệ từ chuỗi tên CPU.
    
    Trả về: (CPU manufacturer, brand modifier, generation code)
    ví dụ: 'Intel Core i5-1334U' -> ('Intel', 'Core i5', '1334')
           'Ultra 7 155H' -> ('Intel', 'Core Ultra 7', '155')
           'Ryzen 5 7600U' -> ('AMD', 'Ryzen 5', '7600')
    """
    if not cpu_info:
        return None, None, None

    # Loại bỏ ký tự đặc biệt và đưa về chữ thường để dễ xử lý Regex
    t = cpu_info.replace("®", "").replace("™", "").replace("-", " ").strip()
    
    # Khởi tạo
    manu = None
    brand = None
    gen = None

    # --- 1. Brand modifier: Ryzen 7, Core i5, Core Ultra 7,... ---
    # Ưu tiên tìm Brand/Phân khúc trước vì nó giúp suy luận Manufacturer sau.
    brand_patterns = [
        # AMD Ryzen
        r"\bRyzen(?:\s+AI)?\s+\d+\b", 
        # Intel Core Ultra (Core Ultra 7, Core Ultra 5)
        r"\bCore\s+Ultra\s+\d+\b", 
        # Intel Core iX (Core i7, Core i5)
        r"\bCore\s+i\d+\b", 
        # Intel Core (Core 7, Core 5)
        r"\bCore\s+\d+\b",
        # Apple (M3 Pro, M2 Max,...)
        r"\bM\d+(?:\s+(?:Pro|Max|Ultra))\b",
        r"\bUltra\s+\d+\b",
        r"\bSnapdragon\s+X\s+(?:Elite|Plus)\b",
        r"\bCore\s+U\s+\d+\b",
        r"\bSnapdragon\s+X\s+X\d(?:\-\d{2})?\b"
    ]
    
    for pat in brand_patterns:
        m = re.search(pat, t, re.I)
        if m:
            brand = m.group(0).replace("  ", " ").strip() # Xóa khoảng trắng thừa
            break

    # --- 2. Manufacturer: Suy luận từ Brand/Tên chip ---
    
    # 2a. Dựa trên tên hãng rõ ràng
    if re.search(r"\bAMD\b", t, re.I):
        manu = "AMD"
    elif re.search(r"\bIntel\b", t, re.I):
        manu = "Intel"
    elif re.search(r"\bApple\b", t, re.I):
        manu = "Apple"
    # Thêm kiểm tra cho Qualcomm và Snapdragon
    elif re.search(r"\bQualcomm\b|\bSnapdragon\b", t, re.I):
        manu = "Qualcomm"
        
    # 2b. Suy luận từ Brand nếu Manufacturer chưa được tìm thấy
    if manu is None:
        if brand and ("Ryzen" in brand or "RYZEN" in brand):
            manu = "AMD"
        elif brand and ("Core" in brand or "Ultra" in brand):
            manu = "Intel"
        elif brand and "M" in brand:
            manu = "Apple"
        
        # Xử lý các trường hợp không đầy đủ (chỉ nhập "Ultra 7")
        if manu is None:
            if "Ultra" in t or "Core i" in t or re.search(r"\bCore\s+\d", t, re.I):
                manu = "Intel"
            elif re.search(r"\bRyzen\s+\d", t, re.I):
                manu = "AMD"


    # --- 3. Generation code: (Mã số SKU/Thế hệ, đã loại hậu tố) ---
    
    # Tăng giới hạn số chữ số lên 5 để bắt các mã mới (ví dụ: 14900, 15500)
    # Tìm kiếm các nhóm 3-5 chữ số, sau đó là 0-3 chữ cái (hậu tố)
    # Ví dụ: 7445HS, 1334U, 7600
    
    # Mẫu Regex: (\d{3,5}) -> Bắt phần số; [A-Za-z]{0,3} -> Bắt 0-3 chữ cái (tùy chọn)
    gens = re.findall(r"\b(\d{3,5})[A-Za-z]{0,3}\b", t)
    
    if gens:
        # Lấy phần tử cuối cùng để đảm bảo đó là mã SKU của CPU (chứ không phải mã model laptop)
        gen_raw = gens[-1]
        
        # Loại bỏ các chữ cái (hậu tố) nếu chúng vẫn còn dính vào (đã được xử lý bởi Regex, 
        # nhưng thêm rstrip để đảm bảo nếu regex không chính xác hoàn toàn)
        gen = gen_raw.rstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')

    return manu, brand, gen

def parse_cpu_speed(cpu_speed_text, cpu_speed_text2, cpu_info):
    """
    Lấy tốc độ GHz xuất hiện trong text (ưu tiên có ghi rõ).
    """
    for src in [cpu_speed_text, cpu_speed_text2, cpu_info]:
        if not src:
            continue
        t_no_space = src.replace(" ", "")
        m = re.search(r"(\d+(?:\.\d+)?)GHz", t_no_space, re.I)
        if not m:
            m = re.search(r"(\d+(?:\.\d+)?)\s*GHz", src, re.I)
        
        if not m and cpu_speed_text == "Tốc độ tối đa":
            m = re.search(r"(\d+(?:\.\d+)?)", t_no_space, re.I)

        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None

import re

def parse_ram_capacity_and_type(ram_text: str, ram_type_text: str):
    """
    Trích xuất dung lượng (GB) và loại RAM từ hai trường văn bản, xử lý định dạng X*YG.
    """
    
    # Khởi tạo
    gb = None
    ram_type = None
    
    # Tạo chuỗi tổng hợp để tìm kiếm linh hoạt hơn
    t = (ram_text or "") + " " + (ram_type_text or "")
    t = t.replace("\xa0", " ").strip()
    
    # --- 1. Trích xuất Dung lượng GB (Capacity) ---
    
    # 1a. Mẫu phức tạp: Xử lý định dạng [Số thanh] * [Dung lượng mỗi thanh]
    # Ví dụ: 1*16G, 2x8GB
    # Mẫu Regex: (\d+)\s*[x\*]\s*(\d+(?:\.\d+)?)\s*G[B]?
    m_combo = re.search(r"(\d+)\s*[x\*]\s*(\d+(?:\.\d+)?)\s*G[B]?", t, re.I)
    
    if m_combo:
        try:
            num_sticks = int(m_combo.group(1))
            capacity_per_stick = float(m_combo.group(2))
            gb = num_sticks * capacity_per_stick
        except ValueError:
            # Bỏ qua nếu giá trị không hợp lệ
            pass
    
    # 1b. Mẫu chuẩn: Xử lý định dạng [Dung lượng] GB/G (Chỉ chạy nếu 1a thất bại)
    if gb is None:
        # Ví dụ: 16GB, 8G
        m_standard = re.search(r"(\d+(?:\.\d+)?)\s*G[B]?", t, re.I)
        if m_standard:
             try:
                gb = float(m_standard.group(1))
             except ValueError:
                pass
                
    # --- 2. Trích xuất Loại RAM (Type) ---
    
    # Tìm kiếm các mẫu chi tiết (LPDDRx) trong chuỗi tổng hợp
    m_type = re.search(r"\b(LP?DDR\dX?)\b", t, re.I)
    
    # Nếu không tìm thấy, tìm các mẫu chung (DDRx)
    if not m_type:
        m_type = re.search(r"\bDDR\d\b", t, re.I)
        
    ram_type = m_type.group(0).upper() if m_type else None

    return gb, ram_type


def parse_bus_mhz(ram_bus_text, ram_text):
    for src in (ram_bus_text, ram_text):
        if not src:
            continue
        t = src.replace(",", " ")
        m = re.search(r"(\d{3,5})\s*(?:MHz|MT/s)?", t, re.I)
        if m:
            return int(m.group(1))
    return None

def parse_storage_gb(storage_text: str):
    if not storage_text:
        return None
    t = storage_text.replace("\xa0", " ")
    # ưu tiên TB trước
    m_tb = re.search(r"(\d+)\s*TB", t, re.I)
    if m_tb:
        return int(m_tb.group(1)) * 1024
    m = re.search(r"(\d+)\s*GB", t, re.I)
    return int(m.group(1)) if m else None

def parse_screen_size_inch(screen_size_text: str):
    if not screen_size_text:
        return None
    t = screen_size_text.replace("\xa0", " ")
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*(inch|inches|in)?", t, re.I)
    return float(m.group(1)) if m else None

import re

def parse_screen_resolution(screen_res_text: str):
    if not screen_res_text:
        return None
        
    t = screen_res_text.replace("\xa0", " ").replace("×", "x").strip()
    
    resolution = None

    # 1. Ưu tiên tìm định dạng số (ví dụ: 1920 x 1080)
    m_num = re.search(r"(\d{3,5})\s*[x\*×]\s*(\d{3,5})", t, re.I)
    if m_num:
        # Nếu tìm thấy số, trả về chuỗi số (ví dụ: '1920 x 1080')
        resolution = f"{m_num.group(1)} x {m_num.group(2)}"
        return resolution

    # 2. Nếu không tìm thấy số, tìm các Tên gọi Phổ biến
    
    # Từ điển mới: KEY là TÊN GỌI (đã chuẩn hóa), VALUE là TÊN GỌI XUẤT RA
    # Tôi sẽ giữ giá trị số cho mục đích tra cứu, nhưng thêm các tên gọi vào KEY
    resolution_mapping = {
        "8K": "8K", "UHD": "4K", 
        "4K": "4K", "QHD": "2K", 
        "2K": "2K", "3K": "3K",
        "FHD": "FHD", "FULLHD": "FHD",
        "HD+": "HD+", "HD": "HD",
        # Bạn có thể thêm các key khác nếu muốn, ví dụ: '1440P': '2K'
    }
    
    # Tạo mẫu Regex để bắt TẤT CẢ các tên gọi
    name_pattern = r"\b(?:HD\+|HD|FHD|FULL\s*HD|QHD|UHD|(\d)K)\b"
    m_name = re.search(name_pattern, t, re.I)

    if m_name:
        
        # 2a. Xử lý trường hợp xK (ví dụ: 2K, 3K, 4K, 8K)
        if m_name.group(1): 
            matched_name = m_name.group(1) + "K"
        else:
            # 2b. Xử lý các tên gọi truyền thống (FHD, QHD, HD, UHD...)
            matched_name = m_name.group(0).upper().replace(" ", "")
        
        # Trả về tên gọi đã chuẩn hóa (ví dụ: '3K')
        return resolution_mapping.get(matched_name)

    return resolution

# --- Ví dụ kiểm tra ---
# print(parse_screen_resolution_v3("14 inch 3K OLED"))           # -> '3K'
# print(parse_screen_resolution_v3("Màn hình QHD"))             # -> '2K'
# print(parse_screen_resolution_v3("Laptop 15.6 inch 3840 x 2160")) # -> '3840 x 2160'

def parse_refresh_hz(refresh_text, screen_size_text, screen_extra):
    """
    Tìm Hz trong 3 nguồn text khác nhau.
    """
    for src in (refresh_text, screen_size_text, screen_extra):
        if not src:
            continue
        t = src.replace("\xa0", " ")
        m = re.search(r"(\d{2,3})\s*Hz", t, re.I)
        if m:
            return int(m.group(1))
    return None

def parse_gpu_manufacturer(gpu_text: str):
    if not gpu_text:
        return None
    if re.search(r"NVIDIA|GeForce|RTX", gpu_text, re.I):
        return "NVIDIA"
    if re.search(r"AMD|Radeon", gpu_text, re.I):
        return "AMD"
    if re.search(r"Intel|ARC", gpu_text, re.I):
        return "Intel"
    if re.search(r"Qualcomm", gpu_text, re.I):
        return "Qualcomm"
    return None


def parse_weight_kg(weight_text: str):
    if not weight_text:
        return None
        
    # Chuẩn hóa:
    # 1. Thay thế dấu phẩy bằng dấu chấm
    # 2. Thay thế khoảng trắng đặc biệt (\xa0) bằng khoảng trắng thường
    t = weight_text.replace(",", ".").replace("\xa0", " ").strip()

    # 1. Trích xuất Kilogram (kg)
    # (\d+[\.]?\d*): Bắt số nguyên hoặc thập phân
    # \s*: Bắt khoảng trắng TÙY CHỌN (giải quyết 1.5kg và 1.5 kg)
    m = re.search(r"(\d+[\.]?\d*)\s*kg", t, re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None # Trả về None nếu không chuyển đổi được (ví dụ: '..')
    
    # 2. Trích xuất Gram (g) và chuyển đổi sang kg
    # m2 = re.search(r"(\d+)\s*g", t, re.I) # Sửa để bắt g/gram
    m2 = re.search(r"(\d+)\s*g(?:ram)?\b", t, re.I) # Bắt 'g' hoặc 'gram'
    if m2:
        try:
            # Chuyển đổi gram sang kg (chia cho 1000)
            return float(m2.group(1)) / 1000.0
        except ValueError:
            return None
            
    return None

# --- Ví dụ kiểm tra ---
# print(parse_weight_kg("1.5kg")) # -> 1.5
# print(parse_weight_kg("1,5 kg")) # -> 1.5
# print(parse_weight_kg("900g")) # -> 0.9

def parse_battery(battery_text: str):
    return battery_text.strip() if battery_text else None


# ---------- Parse HTML thô thành spec_raw ----------

def parse_specs_from_html(detail_html: str) -> dict:
    """
    Dùng chung cho tất cả sản phẩm An Phát, cấu trúc giống hp_0_specs.html…
    Trả về dict spec_raw để build thành row sau.
    """
    if not detail_html:
        return {}

    soup = BeautifulSoup(detail_html, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr") if table else []

    section = None
    data = {
        "manufacturer": None,
        "cpu_info": None,
        "cpu_speed_text": None,
        "cpu_speed_text2": None,
        "ram_text": None,
        "ram_bus_text": None,
        "storage_text": None,
        "screen_size_text": None,
        "screen_res_text": None,
        "screen_extra_text": None,
        "refresh_text": None,
        "gpu_text": None,
        "weight_text": None,
        "battery_text": None,
    }

    for tr in rows:
        tds = tr.find_all("td")
        # Header section (1 cột)
        if len(tds) == 1:
            section = tds[0].get_text(" ", strip=True)
            continue
        if len(tds) < 2:
            continue

        label = tds[0].get_text(" ", strip=True)
        val = tds[1].get_text(" ", strip=True)

        # Manufacturer
        if "Hãng sản xuất" in label:
            data["manufacturer"] = val

        # CPU
        if "Bộ vi xử lý" in label or "Công nghệ CPU" in label:
            data["cpu_info"] = val
        if "Tốc độ tối đa" in label:
            data["cpu_speed_text"] = val
        if label == "Tốc độ" and section and "Bộ vi xử lý" in section:
            data["cpu_speed_text2"] = val
        if label == "CPU" in label:
            data["cpu_info"] = val
            data["cpu_speed_text"] = val
        if label == "Tốc độ":
            data["cpu_speed_text2"] = val


        # RAM
        # Sửa lỗi: Nhóm tất cả các điều kiện OR trước khi kết hợp với AND cuối cùng.
        if ((section and ("Bộ nhớ trong (RAM)" in section or "Bộ nhớ trong" in section)) or label == "RAM") and label in ("Dung lượng", "RAM"):
            data["ram_text"] = val
        if "Tốc độ Bus RAM" in label:
            data["ram_bus_text"] = val
        if label == "RAM":
            data["ram_text"] = val
            data["ram_bus_text"] = val
        if label == "Loại RAM":
            data["ram_type_text"] = val

        # Giả định data đã được khởi tạo: data = {"storage_text": None, "screen_size_text": None, "refresh_text": None, "screen_extra_text": None, "screen_res_text": None}

# ... (Khối RAM ở trên) ...

        # Sửa Khối Ổ cứng (Storage)
        # Thường thì toàn bộ thông số ổ cứng nằm dưới nhãn "Ổ cứng" hoặc "Lưu trữ"
        if section and "Ổ cứng" in section:
            # Nếu label là "Dung lượng" hoặc không có label phụ nào (val chứa thông tin)
            if label == "Dung lượng" or not label: 
                if not data["storage_text"]:
                    data["storage_text"] = val
            
            # Cần thêm logic để xử lý trường hợp thông tin nằm ở nhãn chính "Ổ cứng"
        if label == "Ổ cứng":
            if not data["storage_text"]:
                data["storage_text"] = val

        # --- MÀN HÌNH (SCREEN) ---
        screen_section = section and ("Hiển thị" in section or section == "Màn hình")

        if screen_section:
            # 1. Trích xuất Kích thước màn hình (Size) - Ưu tiên nhãn rõ ràng
            if label == "Màn hình" or "Kích thước màn hình" in label:
                data["screen_size_text"] = val
                
            # 2. Trích xuất Độ phân giải (Resolution) - CẦN REGEX nếu val quá dài
            if "Độ phân giải" in label:
                data["screen_res_text"] = val
            # Hoặc nếu val chứa chuỗi phân giải (1920x1080, 2K, 4K)
            elif "1920 x 1080" in val or "2K" in val or "4K" in val:
                # Nếu đã có data["screen_res_text"], không ghi đè
                if not data["screen_res_text"]:
                    # Chỉ gán phần chứa độ phân giải
                    m = re.search(r"(\d{3,4}\s*[xX]\s*\d{3,4})", val)
                    data["screen_res_text"] = m.group(1) if m else val 
                    
            # 3. Trích xuất Tần số quét (Refresh Rate) và các thông tin phụ
            is_extra_info = ("Công nghệ màn hình" in label or "Tần số quét" in label or label == "Màn hình")
            
            if is_extra_info:
                # Tần số quét (Hz)
                if "Hz" in val and not data["refresh_text"]:
                    # Chỉ lấy số Hz bằng Regex để có giá trị sạch
                    m_hz = re.search(r"(\d+)\s*Hz", val, re.I)
                    data["refresh_text"] = m_hz.group(1) if m_hz else val
                    
                # Thông tin phụ khác (gộp)
                # Bằng cách này, bạn gộp các công nghệ màn hình, anti-glare, nits,...
                if val != data["screen_res_text"]: # Tránh lặp lại độ phân giải
                    data["screen_extra_text"] = (data["screen_extra_text"] or "") + " " + val
        if not screen_section:
            if label == "Màn hình":
                data["screen_size_text"] = val
                data["screen_res_text"] = val
                data["refresh_text"] = val
        # ... (Khối code tiếp theo) ...

        # GPU
        if "Card màn hình" in label or "Card đồ họa" in label:
            data["gpu_text"] = val

        # Weight
        if "Trọng Lượng" in label or "Trọng lượng" in label:
            data["weight_text"] = val

        # Battery
        if "Kiểu Pin" in label or label == "Pin" or label == "Dung lượng pin":
            data["battery_text"] = val

    return data


def build_specs_row(spec_raw: dict):
    manu = parse_manufacturer(spec_raw.get("manufacturer"))
    cpu_manu, cpu_brand, cpu_gen = parse_cpu_fields(spec_raw.get("cpu_info"))
    cpu_speed = parse_cpu_speed(
        spec_raw.get("cpu_speed_text"),
        spec_raw.get("cpu_speed_text2"),
        spec_raw.get("cpu_info"),
    )
    ram_gb, ram_type = parse_ram_capacity_and_type(spec_raw.get("ram_text"), spec_raw.get("ram_type_text"))
    bus = parse_bus_mhz(spec_raw.get("ram_bus_text"), spec_raw.get("ram_text"))
    storage = parse_storage_gb(spec_raw.get("storage_text"))
    screen_size = parse_screen_size_inch(spec_raw.get("screen_size_text"))
    screen_res = parse_screen_resolution(spec_raw.get("screen_res_text"))
    refresh = parse_refresh_hz(
        spec_raw.get("refresh_text"),
        spec_raw.get("screen_size_text"),
        spec_raw.get("screen_extra_text"),
    )
    gpu_manu = parse_gpu_manufacturer(spec_raw.get("gpu_text"))
    weight = parse_weight_kg(spec_raw.get("weight_text"))
    battery = parse_battery(spec_raw.get("battery_text"))

    return {
        "Manufacturer": manu,
        "CPU manufacturer": cpu_manu,
        "CPU brand modifier": cpu_brand,
        "CPU generation": cpu_gen,
        "CPU Speed (GHz)": cpu_speed,
        "RAM (GB)": ram_gb,
        "RAM Type": ram_type,
        "Bus (MHz)": bus,
        "Storage (GB)": storage,
        "Screen Size (inch)": screen_size,
        "Screen Resolution": screen_res,
        "Refresh Rate (Hz)": refresh,
        "GPU manufacturer": gpu_manu,
        "Weight (kg)": weight,
        "Battery": battery,
    }


# ---------- Normalize + pipeline ----------

def normalize_specs(product_name, price_raw, detail_html, manifest):
    spec_raw = parse_specs_from_html(detail_html)
    specs_row = build_specs_row(spec_raw)

    # Manufacturer fallback
    manufacturer = specs_row["Manufacturer"] or manifest.get("manufacturer") \
        or (product_name.split()[0] if product_name else None)
    specs_row["Manufacturer"] = manufacturer

    # Price
    price_vnd = parse_price_to_int(price_raw)

    specs_row.update({
        "Product Name": product_name,
        "Price (VND)": price_vnd,
        "url": manifest.get("url"),
        "saved_path": manifest.get("saved_path"),
        "detail_specs_html_path": manifest.get("detail_specs_html_path"),
    })
    return specs_row


def run_pipeline(manifest_path_str):
    MANIFEST_PATH = Path(manifest_path_str)
    PROJECT_ROOT = MANIFEST_PATH.parent.parent.parent
    
    os.makedirs(OUT_JSON_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifests = json.load(f)

    parsed_rows = []
    errors = []
    manifests_to_run = manifests

    print(f"Bắt đầu xử lý TẤT CẢ ({len(manifests_to_run)}) mẫu từ {MANIFEST_PATH}")
    
    for i, manifest in enumerate(manifests_to_run):
        # DEBUG: chỉ chạy 6 mẫu đầu. Bỏ if này nếu muốn chạy full.
        

        try:
            url = manifest.get("url")
            product_name = clean_product_name(extract_name_from_url(url))

            detail_relative_path = manifest.get("detail_specs_html_path")
            print(detail_relative_path)

            if detail_relative_path:
                detail_path = os.path.join(PROJECT_ROOT, detail_relative_path)
                print(detail_path)
            else:
                detail_path = None

            detail_html = load_file_text(detail_path)

            if detail_html is None:
                errors.append({"index": i, "reason": "detail_html_missing", "manifest": manifest})
                print(f"[WARN] detail html missing for {url} -> skipping")
                continue

            normalized = normalize_specs(product_name, manifest.get("price"), detail_html, manifest)

            # write product json
            manufacturer_slug = (normalized.get("Manufacturer") or "unknown").lower()
            slug = re.sub(r"[^\w\-_]", "_", product_name.lower())[:80] or f"product_{i}"
            json_fn = os.path.join(OUT_JSON_DIR, f"{manufacturer_slug}_{slug}.json")

            with open(json_fn, "w", encoding="utf-8") as jf:
                json.dump(normalized, jf, ensure_ascii=False, indent=2)

            parsed_rows.append(normalized)
            print(f"[OK] Parsed {product_name} ({url})")

        except Exception as e:
            errors.append({"index": i, "error": str(e), "manifest": manifest})
            print(f"[ERR] Failed to parse manifest index {i} ({url}): {e}")

    # write CSV (chỉ các field kỹ thuật + name + price)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in parsed_rows:
            out_row = {k: row.get(k) if k in row else None for k in CSV_FIELDS}
            writer.writerow(out_row)

    if errors:
        with open("anphat_parse_errors.json", "w", encoding="utf-8") as ef:
            json.dump(errors, ef, ensure_ascii=False, indent=2)

    print("--- Pipeline finished ---")
    print(f"Parsed {len(parsed_rows)} products. CSV -> {OUT_CSV}, JSONs -> {OUT_JSON_DIR}")
    if errors:
        print(f"Có {len(errors)} lỗi hoặc cảnh báo. Xem anphat_parse_errors.json")


if __name__ == "__main__":
    manifest_path_for_run = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\anphat\raw_htmls_manifest.json"
    run_pipeline(manifest_path_for_run)
