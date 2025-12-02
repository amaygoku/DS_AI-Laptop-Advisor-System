import os
import json
import re
import csv
from pathlib import Path
from bs4 import BeautifulSoup

# ===================== CONFIG =====================
OUT_JSON_DIR = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\fpt\parsed_products_json"
OUT_CSV = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\fpt\parsed_products.csv"

CSV_FIELDS = [
    "Product Name","Manufacturer","CPU manufacturer","CPU brand modifier","CPU generation",
    "CPU Speed (GHz)","RAM (GB)","RAM Type","Bus (MHz)","Storage (GB)",
    "Screen Size (inch)","Screen Resolution","Refresh Rate (Hz)","GPU manufacturer",
    "Weight (kg)","Battery","Price (VND)", "url","saved_path","detail_specs_html_path"
]


# ===================== HELPERS =====================

def extract_name_from_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return "" 
    slug = url.rstrip("/").split("/")[-1]
    if slug.endswith(".html"):
        slug = slug[:-5]
    name = slug.replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    name = " ".join([
        w.upper() if w.lower() in (
            "hp","lenovo","dell","acer","asus","macbook","apple","msi",
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
    if price_raw is None:
        return None
    price_raw = str(price_raw)
    nums = re.sub(r"[^\d]", "", price_raw)
    return int(nums) if nums else None


# ===================== PARSE FPT HTML (CHUẨN) =====================

def parse_specs_from_html(detail_html: str) -> dict:
    """Parse đa nền tảng: FPT mới → FPT cũ → CellphoneS → TGDĐ"""
    if not detail_html:
        return {}

    soup = BeautifulSoup(detail_html, "html.parser")
    specs = {}

    # -------- FPT HTML mới (spec-item-x) --------
    blocks = soup.select("[id^='spec-item']")
    for block in blocks:
        rows = block.select(".flex.gap-2")
        for r in rows:
            cols = r.find_all(recursive=False)
            if len(cols) < 2:
                continue
            k = cols[0].get_text(" ", strip=True)
            v = cols[1].get_text(" ", strip=True)
            if k and v:
                specs[k] = v

    # -------- FPT cũ --------
    if not specs:
        rows = soup.select(".st-card-specification .st-row")
        for r in rows:
            key = r.select_one(".st-title")
            val = r.select_one(".st-info")
            if key and val:
                specs[key.get_text(" ", strip=True)] = val.get_text(" ", strip=True)

    # -------- CellphoneS --------
    if not specs:
        rows = soup.select("table tr")
        for r in rows:
            cols = r.find_all("td")
            if len(cols) >= 2:
                specs[cols[0].get_text(" ", strip=True)] = cols[1].get_text(" ", strip=True)

    # -------- TGDĐ --------
    if not specs:
        rows = soup.select(".parameter__list .item")
        for r in rows:
            k = r.select_one("p")
            v = r.select_one("div")
            if k and v:
                specs[k.get_text(strip=True)] = v.get_text(" ", strip=True)

    return specs


# ===================== FIELD PARSERS =====================

def parse_cpu(cpu_raw: str, specs_map=None):
    if not cpu_raw:
        return (None, None, None, None)

    cpu = cpu_raw.lower()

    # Manufacturer
    cpu_manu = "Intel" if "intel" in cpu else ("AMD" if "amd" in cpu else "Apple" if "apple" in cpu else ("Qualcomm" if "qualcomm" in cpu else None))

    # Brand modifier
    brand_mod = None
    patterns = [
        r"(core\s*ultra\s*\d+)",     # Core Ultra 5
        r"(ultra\s*\d+)",            # Ultra 5
        r"(core\s*i[3579])",         # Core i5
        r"(core\s*\d+)",             # ⭐ Core 5, Core 7, Core 9 → MỚI THÊM
        r"(i[3579])",                # i5
        r"(ryzen\s*\d+)",            # Ryzen 5
        r"(\d+)\s*core",              # 5 Core
    ]
    for p in patterns:
        m = re.search(p, cpu, re.I)
        if m:
            brand_mod = m.group(1).title()
            break
        else:
            brand_mod = specs_map.get("Công nghệ CPU") or specs_map.get("Loại CPU") or None

    # Generation
    gen = None
    cpu_gen = specs_map.get("Loại CPU") or ""
    if cpu_gen:
        nums = re.findall(r"\d+", cpu_gen)
        if nums:
            gen = nums[0]

    # CPU Speed
    speed = None
    if specs_map:
        speed_raw = specs_map.get("Tốc độ tối đa") or specs_map.get("Tốc độ CPU tối đa")
        speed_raw1 = specs_map.get("Tốc độ CPU tối thiểu") or ""
        if speed_raw:
            m = re.search(r"(\d+[\.,]?\d*)\s*(ghz)?", speed_raw, re.I)
            if m:
                speed = float(m.group(1))
        elif speed_raw1:
            m = re.search(r"(\d+[\.,]?\d*)\s*(ghz)?", speed_raw1, re.I)
            if m:
                speed = float(m.group(1))
    return cpu_manu, brand_mod, gen, speed


def parse_ram(ram_raw: str, ram_type_raw: str, ram_bus: str):
    ram_gb = None
    if ram_raw:
        m = re.search(r"(\d+)\s*gb", ram_raw, re.I)
        if m:
            ram_gb = int(m.group(1))
    
    general_pattern = r"^(LP)?DDR\d+X?$|^SDRAM$"
    ram_type = None
    if ram_type_raw:
        ram_type = ram_type_raw.upper()

        if ram_type and not re.match(general_pattern, ram_type):
            ram_type = None

    bus = None
    if ram_bus:
        m = re.search(r"(\d{3,4})\s*(mhz|mt/s)", ram_bus, re.I)
        if m:
            bus = int(m.group(1))

    return ram_gb, ram_type, bus


def parse_storage(raw: str):
    if not raw:
        return None
    nums = re.findall(r"\d+", raw)
    if nums:
        size_gb = int(nums[0])
        if "tb" in raw.lower() or size_gb < 10:
            size_gb *= 1024
        return size_gb
    return int(nums[0]) if nums else None


def parse_screen(size_raw, res_raw):
    size = None
    if size_raw:
        m = re.search(r"(\d+(?:\.\d+)?)", size_raw)
        if m:
            size = float(m.group(1))

    resolution = None
    if res_raw:
        m = re.search(r"(\d{3,4}\s*[x×]\s*\d{3,4})", res_raw.replace(" ", ""))
        if m:
            resolution = m.group(1).replace("×", "x")

    return size, resolution, None


def parse_refresh_rate(raw: str):
    if not raw:
        return None
    m = re.search(r"(\d{2,3})\s*hz", raw, re.I)
    return int(m.group(1)) if m else None


def parse_gpu(raw: str):
    if not raw:
        return None
    r = raw.lower()
    if "nvidia" in r or "geforce" in r:
        return "NVIDIA"
    if "intel" in r:
        return "Intel"
    if "amd" in r or "radeon" in r:
        return "AMD"
    if "apple" in r or "m1" in r or "m2" in r:
        return "Apple"
    return None


def parse_weight(raw: str):
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", raw)
    return float(m.group(1)) if m else None


def parse_battery(raw: str):
    return raw.strip() if raw else None


# ===================== BUILD ROW (FPT) =====================

def build_specs_row_from_fpt(specs):
    cpu_raw = (
        (specs.get("Hãng CPU") or "") + " " +
        (specs.get("Công nghệ CPU") or "") + " " +
        (specs.get("Loại CPU") or "") + " " +
        (specs.get("Bộ xử lý") or "")
    ).strip()

    gpu_raw = (
        (specs.get("Hãng (Card Oboard)") or (specs.get("Hãng (Card rời)") or "")) + " " +
        (specs.get("Tên đầy đủ (Card onbroad)") or "") + " " +
        (specs.get("Card đồ họa") or "")
    ).strip()

    cpu_man, cpu_brand, cpu_gen, cpu_speed = parse_cpu(cpu_raw, specs)

    ram_raw = specs.get("Dung lượng RAM") or specs.get("RAM") or ""
    ram_type_raw = specs.get("Loại RAM") or ""
    ram_bus = specs.get("Tốc độ RAM") or ""
    ram_gb, ram_type, bus = parse_ram(ram_raw, ram_type_raw, ram_bus)

    storage_gb = parse_storage(specs.get("Dung lượng SSD") or "")

    screen_size, screen_res, _ = parse_screen(
        specs.get("Kích thước màn hình") or "",
        specs.get("Độ phân giải") or ""
    )

    refresh_rate = parse_refresh_rate(specs.get("Tần số quét") or "")

    gpu_manu = parse_gpu(gpu_raw)

    weight_kg = parse_weight(specs.get("Trọng lượng sản phẩm") or specs.get("Trọng lượng") or "")
    battery = parse_battery(
        ( (specs.get("Loại pin") or "") + " " +
            (specs.get("Dung lượng pin") or "") + " " +
         (specs.get("Power Supply") or "")).strip()
    )
    

    return {
        "Manufacturer": specs.get("Hãng sản xuất") or None,
        "CPU manufacturer": cpu_man,
        "CPU brand modifier": cpu_brand,
        "CPU generation": cpu_gen,
        "CPU Speed (GHz)": cpu_speed,
        "RAM (GB)": ram_gb,
        "RAM Type": ram_type,
        "Bus (MHz)": bus,
        "Storage (GB)": storage_gb,
        "Screen Size (inch)": screen_size,
        "Screen Resolution": screen_res,
        "Refresh Rate (Hz)": refresh_rate,
        "GPU manufacturer": gpu_manu,
        "Weight (kg)": weight_kg,
        "Battery": battery,
    }


# ===================== NORMALIZE FINAL =====================

def normalize_specs(product_name, price_raw, detail_html, manifest):
    specs_map = parse_specs_from_html(detail_html)
    specs_row = build_specs_row_from_fpt(specs_map)

    manufacturer = specs_row["Manufacturer"] or manifest.get("manufacturer") \
        or (product_name.split()[0] if product_name else None)

    specs_row["Manufacturer"] = manufacturer
    specs_row["Product Name"] = product_name
    specs_row["Price (VND)"] = parse_price_to_int(price_raw)

    specs_row.update({
        "url": manifest.get("url"),
        "saved_path": manifest.get("saved_path"),
        "detail_specs_html_path": manifest.get("detail_specs_html_path"),
    })
    return specs_row


# ===================== PIPELINE =====================

def run_pipeline(manifest_path_str):
    MANIFEST_PATH = Path(manifest_path_str)
    PROJECT_ROOT = MANIFEST_PATH.parent.parent.parent

    os.makedirs(OUT_JSON_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifests = json.load(f)

    parsed_rows = []
    errors = []

    print(f"Bắt đầu xử lý TẤT CẢ ({len(manifests)}) mẫu")

    for i, manifest in enumerate(manifests):
        try:
            url = manifest.get("url")
            product_name = clean_product_name(extract_name_from_url(url))

            detail_relative_path = manifest.get("detail_specs_html_path")
            detail_path = os.path.join(PROJECT_ROOT, detail_relative_path) if detail_relative_path else None
            detail_html = load_file_text(detail_path)

            if detail_html is None:
                errors.append({"index": i, "reason": "detail_html_missing", "manifest": manifest})
                print(f"[WARN] missing detail html for {url}")
                continue

            normalized = normalize_specs(product_name, manifest.get("price"), detail_html, manifest)

            # write JSON
            manufacturer_slug = (normalized.get("Manufacturer") or "unknown").lower()
            slug = re.sub(r"[^\w\-_]", "_", product_name.lower())[:80] or f"product_{i}"
            json_fn = os.path.join(OUT_JSON_DIR, f"{manufacturer_slug}_{slug}.json")

            with open(json_fn, "w", encoding="utf-8") as jf:
                json.dump(normalized, jf, ensure_ascii=False, indent=2)

            parsed_rows.append(normalized)
            print(f"[OK] {product_name}")

        except Exception as e:
            errors.append({"index": i, "error": str(e), "manifest": manifest})
            print(f"[ERR] index {i} ({url}): {e}")

    # write CSV
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in parsed_rows:
            out_row = {k: row.get(k) for k in CSV_FIELDS}
            writer.writerow(out_row)

    if errors:
        with open("fpt_parse_errors.json", "w", encoding="utf-8") as ef:
            json.dump(errors, ef, ensure_ascii=False, indent=2)

    print("--- DONE ---")
    print(f"Parsed: {len(parsed_rows)}")
    print(f"CSV -> {OUT_CSV}")
    print(f"JSON -> {OUT_JSON_DIR}")
    if errors:
        print(f"Errors: {len(errors)} (see fpt_parse_errors.json)")


if __name__ == "__main__":
    manifest_path_for_run = r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\fpt\raw_htmls_manifest.json"
    run_pipeline(manifest_path_for_run)
