import os
import json
import re
import csv
from pathlib import Path
from bs4 import BeautifulSoup
from pprint import pprint

# ---------- CONFIG ----------
# KHÔNG GÁN GIÁ TRỊ CỨNG Ở ĐÂY. SỬ DỤNG GIÁ TRỊ TỪ COMMAND LINE HOẶC KHAI BÁO CỦA BẠN.
# Tôi đặt nó là None ở đây, sẽ được load từ tham số run_pipeline
MANIFEST_PATH_DEFAULT = "raw_htmls_manifest.json" 
OUT_JSON_DIR = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\cellphones\parsed_products_json"
OUT_CSV = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\cellphones\parsed_products.csv"

# 🌟 CẬP NHẬT: Các cột CSV chỉ bao gồm thông số kỹ thuật
CSV_FIELDS = [
    "Product Name","Manufacturer","CPU manufacturer","CPU brand modifier","CPU generation",
    "CPU Speed (GHz)","RAM (GB)","RAM Type","Bus (MHz)","Storage (GB)",
    "Screen Size (inch)","Screen Resolution","Refresh Rate (Hz)","GPU manufacturer",
    "Weight (kg)","Battery","Price (VND)", "url","saved_path","detail_specs_html_path"
]

# ---------- Helpers ----------
def extract_name_from_url(url: str) -> str:
    # Đã sửa lỗi NoneType và SyntaxWarning
    if not isinstance(url, str) or not url:
        return "" 
    
    slug = url.rstrip("/").split("/")[-1]
    if slug.endswith(".html"):
        slug = slug[:-5]
    name = slug.replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    # Title-case but keep common acronyms uppercase
    name = " ".join([w.upper() if w.lower() in ("hp","lenovo","dell","acer","asus","macbook","msi","gigabyte","rtx","ryzen","intel","amd") else w.capitalize() for w in name.split()])
    return name

def clean_product_name(name:str)->str:
    parts = name.split()
    if parts and parts[0].lower()=="laptop":
        parts = parts[1:]
    return " ".join(parts)

def load_file_text(path):
    # Đã sửa lỗi NoneType và kiểm tra Path
    if not isinstance(path, (str, Path)) or not path:
        return None
        
    path = os.path.normpath(path)
    
    if not os.path.exists(path):
        return None
        
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# parse specs table -> dict label -> value
def parse_specs_html(detail_html: str) -> dict:
    if not detail_html:
        return {}
    soup = BeautifulSoup(detail_html, "html.parser")
    specs = {}
    # select rows
    rows = soup.select("table.technical-content tr.technical-content-item")
    
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 2:
            k = cols[0].get_text(" ", strip=True)
            v = cols[1].get_text(" ", strip=True)
            specs[k] = v

    # Also try to parse section titles with inline tables (fallback)
    if not specs or len(specs) < 5: # Chỉ chạy fallback nếu ít data
        # search for any table rows
        rows2 = soup.select("tr")
        for r in rows2:
            cols = r.find_all("td")
            if len(cols) >= 2:
                k = cols[0].get_text(" ", strip=True)
                v = cols[1].get_text(" ", strip=True)
                if k and k not in specs: # chỉ thêm key chưa có
                    specs[k] = v
    return specs

# ---------- Field parsers ----------
import re

def parse_cpu(cpu_raw: str):
    # 1. Kiểm tra đầu vào
    if not cpu_raw: 
        return (None, None, None, None)
    
    cpu = cpu_raw.lower()
    cpu = cpu.replace("®", "").replace("™", "").replace("-", " ").replace("tm", "").strip()

    # 2. Hãng sản xuất (Manufacturer) - Bổ sung suy luận từ tên dòng sản phẩm (iX, Ryzen, M-series)
    cpu_manufacturer = None

    # Ưu tiên các từ khóa mạnh và đặc trưng
    if re.search(r"\bintel\b|\bi[3579]\b|\bcore\s*(?:tm)?\s*(?:ultra)?\s*[u]?[3579]\b|\bceleron\b|\bpentium\b", cpu, re.I):
        cpu_manufacturer = "Intel"
    # Bắt AMD dựa trên Ryzen và Ryzen AI
    elif re.search(r"\bamd\b|\bryzen\b|\bryzen\s*ai\s*(?:max|plus)?\b", cpu, re.I): 
        cpu_manufacturer = "AMD"
    elif re.search(r"\bapple\b|\bm\d\b", cpu, re.I):
        cpu_manufacturer = "Apple"
    elif re.search(r"\bqualcomm\b|\bsnapdragon\b|\borion\b|\bx\s*(?:elite|plus|\d)\b", cpu, re.I):
        cpu_manufacturer = "Qualcomm"
        
    # 3. Dòng/Biến thể (Brand Modifier)
    brand_mod = None
    
    # Regex bắt tất cả các dòng sản phẩm quan trọng:
    # 1. Core Ultra X (ví dụ: Core Ultra 7) HOẶC Core X (ví dụ: Core 5)
    # 2. Ryzen AI X (ví dụ: Ryzen AI 9, Ryzen AI 300) HOẶC Ryzen X
    # 3. iX, M-series, X Elite/Plus, Celeron/Pentium
    m = re.search(
        r"(core\s*(?:ultra)?\s*[u]?[3579]|i[3579]|ryzen\s*ai\s*(?:max|plus|\d+)|ryzen\s*\d|ryzen\s*r*\d|ryzen\s*ai\s*\d|m\d\s*(?:pro|max|ultra)?|snapdragon\s*x\s*(?:elite|plus|\d)?|celeron|pentium)",
        cpu, 
        re.I
    )
    
    if m:
        brand_mod_raw = m.group(1).replace(" ", "")
        
        # Xử lý đặc biệt cho Intel để lấy đúng tên dòng
        if re.match(r"i\d", brand_mod_raw.lower()):
            # Core i5, Core i7
            brand_mod = "Core " + brand_mod_raw.upper()
            
        elif re.match(r"coreultra\d", brand_mod_raw.lower()):
            # Core Ultra 5, 7, 9 (Ví dụ: COREULTRA7)
            brand_mod = "Core Ultra " + brand_mod_raw[-1]
            
        elif re.match(r"core\d", brand_mod_raw.lower()):
            # Core 3, 5, 7 (Ví dụ: CORE5)
            brand_mod = "Core " + brand_mod_raw[-1]
            
        elif re.match(r"ryzenai\d+", brand_mod_raw.lower()):
            # Ryzen AI 9, Ryzen AI 300 (Ví dụ: RYZENAI9)
            brand_mod = "Ryzen AI " + brand_mod_raw[-1]
        elif re.match(r"snapdragonx(elite|plus|\d+)?", brand_mod_raw.lower()):
            # Snapdragon X Elite/Plus/5 (Ví dụ: SNAPDRAGONXELITE)
            suffix = brand_mod_raw[12:]  # Lấy phần sau "snapdragonx"
            if suffix:
                brand_mod = "Snapdragon X " + suffix.capitalize()
            else:
                brand_mod = "Snapdragon X"
        elif re.match(r"m\d(pro|max|ultra)?", brand_mod_raw.lower()):
            # M1, M2 Pro, M3 Max (Ví dụ: M2PRO)
            suffix = brand_mod_raw[2:]  # Lấy phần sau "mX"
            if suffix:
                brand_mod = "M" + brand_mod_raw[1] + " " + suffix.capitalize()
            else:
                brand_mod = "M" + brand_mod_raw[1]
            
        else:
            # RYZEN7, CELERON, PENTIUM, XPLUS, M3MAX, v.v.
            brand_mod = brand_mod_raw.capitalize()
    
    # 4. Thế hệ (Generation)
    gen = None
    
    # A. Xử lý Apple (M1, M2, M3...)
    if cpu_manufacturer == "Apple":
        m_apple = re.search(r"m(\d)", cpu)
        gen = m_apple.group(1) if m_apple else None
    
    # B. Xử lý Intel/AMD (Mô hình số 3-5 chữ số)
    # B. Xử lý Intel/AMD (Mô hình số 3-5 chữ số)
    elif cpu_manufacturer == "Intel" or cpu_manufacturer == "AMD":
    
        clean_cpu = re.sub(r'[^a-z0-9]', ' ', cpu) 
        
        # Bắt toàn bộ chuỗi số 3-5 chữ số (ví dụ: 13600, 7840)
        m2 = re.search(r"(\d{3,5})", clean_cpu) 
        
        if m2:
            # Lấy toàn bộ chuỗi số
            gen = m2.group(1) 
                
    # 5. Tốc độ (Speed - GHz)
    speed = None
    m3 = re.search(r"(\d+(?:\.\d+)?)\s*ghz", cpu, re.I)
    if m3:
        speed = float(m3.group(1))
        
    return cpu_manufacturer, brand_mod, gen, speed

# 🌟 HÀM ĐƯỢC SỬA: Khắc phục dấu gạch ngang và đơn vị Bus (MT/s, MHz)
def parse_ram(ram_raw: str, ram_type_raw: str):
    ram_gb = None
    if ram_raw:
        m = re.search(r"(\d+)\s*gb", ram_raw, re.I)
        if m:
            ram_gb = int(m.group(1))
            
    ram_type = None
    bus = None
    if ram_type_raw:
        # 🌟 KHẮC PHỤC DẤU GẠCH NGANG và chuẩn hóa chuỗi
        normalized_raw = ram_type_raw.replace('-', ' ') 

        # 1. Tìm kiếm tổng quát: Bắt LPDDRxX, LPDDRx, DDRxX, DDRx (Tối ưu)
        # lp?ddr: Bắt LPDDR hoặc DDR
        # \d: Bắt số thế hệ
        # X?: Bắt hậu tố X (tùy chọn)
        m_type = re.search(r"\b(lp?ddr\dX?)\b", normalized_raw, re.I)
        if not m_type:
            # 1b. Bắt riêng lẻ: Bắt LPDDR hoặc DDR nếu không có số thế hệ
            m_type = re.search(r"\b(ddr\d?[a-z]?)\b", normalized_raw, re.I)
        if m_type:
            # Lấy chuỗi khớp và chuẩn hóa thành chữ hoa (ví dụ: DDR4X)
            ram_type = m_type.group(1).upper()
            
        # Không cần khối 'if not m_type' thứ hai vì regex đã bao hàm hết
            
        # 2. Bắt Bus Speed: Bắt Bus + đơn vị (mhz|mt/s)
        m2 = re.search(r"(\d{3,4})\s*(mhz|mt/s)", normalized_raw, re.I)
        if m2:
            bus = int(m2.group(1))
        else:
            # 3. Bắt dự phòng (Bus speed thường là số 3-4 chữ số lớn hơn 1000)
            m3 = re.search(r"(\d{3,4})", normalized_raw, re.I)
            if m3:
                num_candidate = int(m3.group(1))
                if num_candidate >= 1000:
                    bus = num_candidate
            
    return ram_gb, ram_type, bus

def parse_storage(raw: str):
    if not raw: return None
    m = re.search(r"(\d+)\s*tb", raw, re.I)
    if m:
        return int(m.group(1))*1024
    m = re.search(r"(\d+)\s*gb", raw, re.I)
    if m:
        return int(m.group(1))
    return None

# 🌟 HÀM MỚI: Xử lý Tần số quét (Refresh Rate) độc lập
def parse_refresh_rate(raw: str):
    if not raw: return None
    # Bắt số và đơn vị Hz
    m = re.search(r"(\d{2,3})\s*hz", raw, re.I)
    if m:
        return int(m.group(1))
    return None

def parse_screen(size_raw, res_raw):
    # Tần số quét (refresh rate) đã được tách ra, chỉ giữ lại size và resolution
    size = None
    if size_raw:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(inches|inch|in)?", size_raw, re.I)
        if m:
            size = float(m.group(1))
    
    resolution = None
    if res_raw:
        m = re.search(r"(\d{3,4}\s*x\s*\d{3,4})", res_raw.replace("×","x"))
        if m:
            resolution = m.group(1)
            
    return size, resolution, None # Trả về None cho refresh

def parse_gpu(raw: str):
    if not raw: return None
    r = raw.lower()
    if "nvidia" in r or "geforce" in r:
        return "NVIDIA"
    if "intel" in r:
        return "Intel"
    if "amd" in r or "radeon" in r:
        return "AMD"
    if "apple" in r or "m series" in r:
        return "Apple"
    if "qualcomm" in r or "adreno" in r:
        return "Qualcomm"
    return None

def parse_weight(raw: str):
    if not raw: return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", raw, re.I)
    if m:
        return float(m.group(1))
    # sometimes in grams
    m2 = re.search(r"(\d+)\s*g", raw, re.I)
    if m2:
        return float(m2.group(1))/1000.0
    return None

def parse_battery(raw: str):
    return raw.strip() if raw else None

def parse_price_to_int(price_raw: str):
    if not price_raw:
        return None
    numbers = re.sub(r"[^\d]", "", price_raw)
    return int(numbers) if numbers else None

# ---------- Main normalize ----------
def normalize_specs(product_name, price_raw, specs_html, manifest):
    specs_map = parse_specs_html(specs_html)

    # Chuẩn hoá key -> lowercase để tra cứu linh hoạt
    norm_map = {}
    for k, v in specs_map.items():
        if not k:
            continue
        norm_map[k.strip().lower()] = v

    # ---------- CPU ----------
    cpu_main = (
        norm_map.get("loại cpu")
        or norm_map.get("loại bộ vi xử lý")
        or norm_map.get("bộ xử lý")
        or norm_map.get("bộ vi xử lý")
        or norm_map.get("công nghệ cpu")
        or ""
    )
    cpu_speed_extra = (
        norm_map.get("tốc độ")
        or norm_map.get("tốc độ cpu")
        or norm_map.get("tốc độ tối đa")
        or ""
    )
    # Ghép name + tốc độ để parse 1 lần
    cpu_raw = " ".join(s for s in [cpu_main, cpu_speed_extra] if s)

    cpu_manufacturer, cpu_brand, cpu_gen, cpu_speed = parse_cpu(cpu_raw)
    if cpu_manufacturer is None:
        if "apple" in product_name.lower() or "macbook" in product_name.lower():
            cpu_manufacturer = "Apple"

    # ---------- RAM ----------
    ram_raw = norm_map.get("dung lượng ram") or norm_map.get("ram")

    # Nếu vẫn chưa có, scan theo pattern: có "GB" và "DDR"
    if not ram_raw:
        for v in specs_map.values():
            lv = v.lower()
            if "ddr" in lv and re.search(r"\b\d+\s*gb\b", v, re.I):
                ram_raw = v
                break

    # Loại RAM / Bus: ưu tiên key riêng, nếu không lấy từ ram_raw luôn
    ram_type_raw = (
        norm_map.get("loại ram")
        or norm_map.get("kiểu ram")
        or ram_raw
    )

    ram_gb, ram_type, bus = parse_ram(ram_raw, ram_type_raw)

    # ---------- Storage ----------
    storage_raw = None

    # Ưu tiên các key liên quan ổ cứng
    for k, v in specs_map.items():
        lk = k.lower()
        lv = v.lower()
        if ("ổ cứng" in lk) or ("lưu trữ" in lk) or ("bộ nhớ trong" in lk):
            if re.search(r"\b\d+\s*(gb|tb)\b", v, re.I):
                storage_raw = v
                break

    # Nếu vẫn chưa có, scan theo pattern: có SSD/HDD + GB/TB nhưng KHÔNG có "ddr"
    if not storage_raw:
        for v in specs_map.values():
            lv = v.lower()
            if any(w in lv for w in ["ssd", "hdd", "emmc"]):
                if re.search(r"\b\d+\s*(gb|tb)\b", v, re.I) and "ddr" not in lv:
                    storage_raw = v
                    break

    storage_gb = parse_storage(storage_raw)

    # ---------- Screen size & resolution ----------
    screen_size_raw = (
        norm_map.get("kích thước màn hình")
        or norm_map.get("kích thước")
        or norm_map.get("màn hình")   # An Phát dùng "Màn hình"
    )

    if not screen_size_raw:
        # fallback: tìm value có "inch"
        for v in specs_map.values():
            if re.search(r"\d+(?:\.\d+)?\s*(\"|inch)", v.lower()):
                screen_size_raw = v
                break

    screen_res_raw = (
        norm_map.get("độ phân giải màn hình")
        or norm_map.get("độ phân giải")
    )

    if not screen_res_raw:
        for v in specs_map.values():
            if re.search(r"\d{3,4}\s*[x×]\s*\d{3,4}", v):
                screen_res_raw = v
                break

    screen_size, resolution, _ = parse_screen(screen_size_raw, screen_res_raw)

    # ---------- Refresh rate ----------
    refresh_raw = norm_map.get("tần số quét")

    if not refresh_raw:
        # An Phát hay nhét vào "Công nghệ màn hình"
        for k, v in specs_map.items():
            lk = k.lower()
            if any(word in lk for word in ["tần số quét", "công nghệ màn hình", "màn hình"]):
                if re.search(r"\d{2,3}\s*hz", v, re.I):
                    refresh_raw = v
                    break

    refresh_rate = parse_refresh_rate(refresh_raw)

    # ---------- GPU ----------
    gpu_raw = (
        specs_map.get("Loại card đồ họa")
        or specs_map.get("Đồ họa")
        or specs_map.get("Card đồ họa")
        or specs_map.get("Card màn hình")   # An Phát
        or specs_map.get("VGA")
        or specs_map.get("GPU")
        or ""
    )

    if not gpu_raw:
        # fallback: value chứa tên GPU
        for v in specs_map.values():
            lv = v.lower()
            if any(g in lv for g in ["rtx", "gtx", "radeon", "iris xe", "geforce"]):
                gpu_raw = v
                break

    gpu_manu = parse_gpu(gpu_raw)
    if gpu_manu is None:
        if "apple" in product_name.lower() or "macbook" in product_name.lower():
            gpu_manu = "Apple"

    # ---------- Weight ----------
    weight_raw = (
        specs_map.get("Trọng lượng")
        or specs_map.get("Trọng Lượng")   # case khác
        or specs_map.get("Cân nặng")
    )

    if not weight_raw:
        for v in specs_map.values():
            if re.search(r"\d+(?:\.\d+)?\s*kg", v.lower()):
                weight_raw = v
                break

    weight_kg = parse_weight(weight_raw)

    # ---------- Battery ----------
    battery_raw = (
        specs_map.get("Pin")
        or specs_map.get("Kiểu Pin")
        or specs_map.get("Dung lượng pin")
    )

    if not battery_raw:
        # fallback: chuỗi có "Wh"
        for v in specs_map.values():
            if "wh" in v.lower():
                battery_raw = v
                break

    battery = parse_battery(battery_raw)

    # ---------- Price ----------
    price_vnd = parse_price_to_int(price_raw)

    # ---------- Manufacturer ----------
    manufacturer = manifest.get("manufacturer")
    if not manufacturer:
        manufacturer = (product_name.split()[0] if product_name else None)
        # chuẩn hoá 1 số hãng
        if manufacturer:
            low = manufacturer.lower()
            if low in ["hp", "dell", "asus", "acer", "lenovo", "msi"]:
                manufacturer = low.upper()

    return {
        "Product Name": product_name,
        "Manufacturer": manufacturer,
        "CPU manufacturer": cpu_manufacturer,
        "CPU brand modifier": cpu_brand,
        "CPU generation": cpu_gen,
        "CPU Speed (GHz)": cpu_speed,
        "RAM (GB)": ram_gb,
        "RAM Type": ram_type,
        "Bus (MHz)": bus,
        "Storage (GB)": storage_gb,
        "Screen Size (inch)": screen_size,
        "Screen Resolution": resolution,
        "Refresh Rate (Hz)": refresh_rate,
        "GPU manufacturer": gpu_manu,
        "Weight (kg)": weight_kg,
        "Battery": battery,
        "Price (VND)": price_vnd,
        # giữ nguyên cho JSON
        "url": manifest.get("url"),
        "saved_path": manifest.get("saved_path"),
        "detail_specs_html_path": manifest.get("detail_specs_html_path"),
    }


# ---------- Pipeline ----------
def run_pipeline(manifest_path_str):
    # Lấy đường dẫn chính xác từ giá trị bạn đã cung cấp ở ngoài hàm main
    MANIFEST_PATH = Path(manifest_path_str)
    # 🌟 KHÔNG CẦN CHỈ ĐỊNH ROOT EXPLICITLY NỮA: Ta có thể dùng MANIFEST_PATH.parent
    # Tuy nhiên, để khớp với logic data/... cũ, ta dùng .parent.parent.parent
    PROJECT_ROOT = MANIFEST_PATH.parent.parent.parent 
    
    # make output dirs
    os.makedirs(OUT_JSON_DIR, exist_ok=True)

    # load manifest
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifests = json.load(f)

    parsed_rows = []
    errors = []
    
    # 🌟 CẬP NHẬT: Xử lý TẤT CẢ các mẫu
    manifests_to_run = manifests 

    print(f"Bắt đầu xử lý TẤT CẢ ({len(manifests_to_run)}) mẫu từ {MANIFEST_PATH}")
    
    for i, manifest in enumerate(manifests_to_run):
        try:
            url = manifest.get("url")
            product_name = clean_product_name(extract_name_from_url(url))
            
            detail_relative_path = manifest.get("detail_specs_html_path")
            
            # Ghép đường dẫn tuyệt đối an toàn
            if detail_relative_path:
                detail_path = os.path.join(PROJECT_ROOT, detail_relative_path)
            else:
                detail_path = None
                
            detail_html = load_file_text(detail_path)
            
            if detail_html is None:
                # error but continue
                errors.append({"index": i, "reason": "detail_html_missing", "manifest": manifest})
                print(f"[WARN] detail html missing for {url} -> skipping")
                continue

            normalized = normalize_specs(product_name, manifest.get("price"), detail_html, manifest)

            # write product json
            # Thêm manufacturer vào tên file để tránh trùng lặp giữa các hãng
            manufacturer_slug = normalized.get("Manufacturer", "unknown").lower()
            slug = re.sub(r"[^\w\-_]", "_", product_name.lower())[:80] or f"product_{i}"
            json_fn = os.path.join(OUT_JSON_DIR, f"{manufacturer_slug}_{slug}.json")
            
            with open(json_fn, "w", encoding="utf-8") as jf:
                json.dump(normalized, jf, ensure_ascii=False, indent=2)

            parsed_rows.append(normalized)
            print(f"[OK] Parsed {product_name} ({url})")

        except Exception as e:
            errors.append({"index": i, "error": str(e), "manifest": manifest})
            print(f"[ERR] Failed to parse manifest index {i} ({url}): {e}")

    # write CSV
    # 🌟 CẬP NHẬT: Chỉ bao gồm các trường được định nghĩa trong CSV_FIELDS
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in parsed_rows:
            # Lọc row chỉ lấy các cột trong CSV_FIELDS
            out_row = {k: row.get(k) if k in row else None for k in CSV_FIELDS}
            writer.writerow(out_row)

    # write errors log
    if errors:
        with open("parse_errors.json", "w", encoding="utf-8") as ef:
            json.dump(errors, ef, ensure_ascii=False, indent=2)

    print("--- Pipeline finished ---")
    print(f"Parsed {len(parsed_rows)} products. CSV -> {OUT_CSV}, JSONs -> {OUT_JSON_DIR}")
    if errors:
        print(f"Có {len(errors)} lỗi hoặc cảnh báo. Xem parse_errors.json")

if __name__ == "__main__":
    # Sử dụng giá trị MANIFEST_PATH bạn đã cung cấp
    manifest_path_for_run = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\cellphones\raw_htmls_manifest.json"
    run_pipeline(manifest_path_for_run)