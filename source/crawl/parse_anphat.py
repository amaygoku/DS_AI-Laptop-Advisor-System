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
    "Weight (kg)","Battery","Price (VND)"
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
    Trả về: (CPU manufacturer, brand modifier, generation code)
    ví dụ: 'Intel Core i5-1334U' -> ('Intel', 'Core i5', '1334U')
    """
    if not cpu_info:
        return None, None, None

    t = cpu_info.replace("®", "").replace("™", "")

    # Manufacturer
    manu = None
    if re.search(r"\bAMD\b", t, re.I):
        manu = "AMD"
    elif re.search(r"\bIntel\b", t, re.I):
        manu = "Intel"

    # Brand modifier: Ryzen 7, Core i5, Core Ultra 7,...
    brand = None
    for pat in [r"\bRyzen\s+\d+\b", r"\bCore\s+Ultra\s+\d+\b", r"\bCore\s+i\d+\b"]:
        m = re.search(pat, t, re.I)
        if m:
            brand = m.group(0)
            break

    # Generation code: 7445HS, 1334U, 1315U, 225H, 255U, ...
    gen = None
    gens = re.findall(r"\b(\d{3,4}[A-Za-z]{1,3})\b", t)
    if gens:
        gen = gens[-1]

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
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None

def parse_ram_gb_and_type(ram_text: str):
    if not ram_text:
        return None, None
    t = ram_text.replace("\xa0", " ")
    # GB
    m = re.search(r"(\d+(?:\.\d+)?)\s*GB", t, re.I)
    gb = float(m.group(1)) if m else None
    # DDR type
    m2 = re.search(r"\b(LP?DDR\dX?)\b", t, re.I)
    if not m2:
        m2 = re.search(r"\bDDR\d\b", t, re.I)
    ram_type = m2.group(0).upper() if m2 else None
    return gb, ram_type

def parse_bus_mhz(ram_bus_text, ram_text):
    for src in (ram_bus_text, ram_text):
        if not src:
            continue
        t = src.replace(",", " ")
        m = re.search(r"(\d{3,5})\s*(?:MHz|MT/s)", t, re.I)
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

def parse_screen_resolution(screen_res_text: str):
    if not screen_res_text:
        return None
    t = screen_res_text.replace("\xa0", " ").replace("×", "x")
    m = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", t)
    if not m:
        return None
    return f"{m.group(1)} x {m.group(2)}"

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
    if re.search(r"NVIDIA|GeForce", gpu_text, re.I):
        return "NVIDIA"
    if re.search(r"AMD|Radeon", gpu_text, re.I):
        return "AMD"
    if re.search(r"Intel|ARC", gpu_text, re.I):
        return "Intel"
    return None

def parse_weight_kg(weight_text: str):
    if not weight_text:
        return None
    t = weight_text.replace(",", ".").replace("\xa0", " ")
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", t, re.I)
    if m:
        return float(m.group(1))
    m2 = re.search(r"(\d+)\s*g", t, re.I)
    if m2:
        return float(m2.group(1)) / 1000.0
    return None

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

        # RAM
        if (section and "Bộ nhớ trong (RAM)" in section or label == "RAM") and label in ("Dung lượng", "RAM"):
            if not data["ram_text"]:
                data["ram_text"] = val
        if "Tốc độ Bus RAM" in label:
            data["ram_bus_text"] = val

        # Storage
        if section and "Ổ cứng" in section and label == "Dung lượng":
            data["storage_text"] = val

        # Screen
        screen_section = section and ("Hiển thị" in section or section == "Màn hình")
        if screen_section and (label == "Màn hình" or "Kích thước màn hình" in label):
            data["screen_size_text"] = val
        if screen_section and ("Công nghệ màn hình" in label or "Tần số quét" in label):
            if "Hz" in val and not data["refresh_text"]:
                data["refresh_text"] = val
            data["screen_extra_text"] = (data["screen_extra_text"] or "") + " " + val
        if screen_section and "Độ phân giải" in label:
            data["screen_res_text"] = val

        # GPU
        if "Card màn hình" in label:
            data["gpu_text"] = val

        # Weight
        if "Trọng Lượng" in label or "Trọng lượng" in label:
            data["weight_text"] = val

        # Battery
        if "Kiểu Pin" in label or label == "Pin":
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
    ram_gb, ram_type = parse_ram_gb_and_type(spec_raw.get("ram_text"))
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
