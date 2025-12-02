import json
import os
import re
from bs4 import BeautifulSoup
from pathlib import Path

# ---------- Config ----------
MANIFEST_PATH = Path(r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\fpt\raw_htmls_manifest.json")
TEST_COUNT = 1
PROJECT_ROOT = MANIFEST_PATH.parent.parent.parent


# ---------- Helpers ----------
def extract_name_from_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return "" 
    slug = url.rstrip("/").split("/")[-1]
    if slug.endswith(".html"):
        slug = slug[:-5]
    name = slug.replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip() 
    name = " ".join([
        w.upper() if w.lower() in ("hp","lenovo","dell","acer","asus","msi",
                                   "apple","macbook","intel","amd") else w.capitalize()
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


# ---------- Parse raw specs HTML ----------
def parse_specs_html(detail_html: str) -> dict:
    if not detail_html:
        return {}

    soup = BeautifulSoup(detail_html, "html.parser")
    specs = {}

    # -------- FPT HTML mới (dạng spec-item-x) --------
    blocks = soup.select("[id^='spec-item']")
    for block in blocks:
        rows = block.select(".flex.gap-2")
        for r in rows:
            cols = r.find_all(recursive=False)

            if len(cols) < 2:
                continue

            key_el = cols[0]
            val_el = cols[1]

            k = key_el.get_text(" ", strip=True)
            v = val_el.get_text(" ", strip=True)

            if k and v:
                specs[k] = v

    # -------- Fallback: FPT cũ --------
    if not specs:
        rows = soup.select(".st-card-specification .st-row")
        for r in rows:
            key = r.select_one(".st-title")
            val = r.select_one(".st-info")
            if key and val:
                specs[key.get_text(" ", strip=True)] = val.get_text(" ", strip=True)

    # -------- Fallback: CellphoneS --------
    if not specs:
        rows = soup.select("table tr")
        for r in rows:
            cols = r.find_all("td")
            if len(cols) >= 2:
                specs[cols[0].get_text(" ", strip=True)] = cols[1].get_text(" ", strip=True)

    # -------- Fallback: TGDĐ --------
    if not specs:
        rows = soup.select(".parameter__list .item")
        for r in rows:
            k = r.select_one("p")
            v = r.select_one("div")
            if k and v:
                specs[k.get_text(strip=True)] = v.get_text(" ", strip=True)

    return specs



# ---------- Field parsers ----------
def parse_cpu(cpu_raw: str, specs_map=None):
    if not cpu_raw:
        return (None, None, None, None)

    cpu = cpu_raw.lower()

    # ---------- CPU Manufacturer ----------
    cpu_manufacturer = None
    if "intel" in cpu:
        cpu_manufacturer = "Intel"
    elif "amd" in cpu:
        cpu_manufacturer = "AMD"

    # ---------- Brand Modifier ----------
    brand_mod = None

    patterns = [
        r"(core\s*ultra\s*\d+)",     # Core Ultra 5
        r"(ultra\s*\d+)",            # Ultra 5
        r"(core\s*i[3579])",         # Core i5
        r"(i[3579])",                # i5
        r"(ryzen\s*\d+)",            # Ryzen 5
    ]

    for p in patterns:
        m = re.search(p, cpu, re.I)
        if m:
            brand_mod = m.group(1).title()
            break

    # ---------- Generation ----------
    gen = None
    if brand_mod:
        num = re.findall(r"\d+", brand_mod)
        if num:
            gen = num[0]

    # ---------- CPU Speed ----------
    speed = None
    if specs_map:
        speed_raw = specs_map.get("Tốc độ tối đa") or specs_map.get("Tốc độ CPU tối đa")
        print("tốc độ tối đa",speed_raw)
        if speed_raw:
            m = re.search(r"(\d+[\.,]?\d*)\s*(ghz|mhz)", speed_raw, re.I)
            if m:
                speed = float(m.group(1))
    else:
        print("error")

    return cpu_manufacturer, brand_mod, gen, speed



def parse_ram(ram_raw: str, ram_type_raw: str, ram_bus: str):
    ram_gb = None
    if ram_raw:
        m = re.search(r"(\d+)\s*gb", ram_raw, re.I)
        if m:
            ram_gb = int(m.group(1))

    ram_type = None
    bus = None
    if ram_type_raw:
        normalized_raw = ram_type_raw.replace('-', ' ') 
        m = re.search(r"(ddr\d)", normalized_raw, re.I)
        if m:
            ram_type = m.group(1).upper()
    if ram_bus:
        m = re.search(r"(\d{3,4})\s*(mhz|mt/s)", ram_bus, re.I)
        if m:
            bus = m.group(1)
    return ram_gb, ram_type, bus


def parse_storage(raw: str):
    if not raw:
        return None
    m = raw
    
    if m:
        return int(m)
    return None


def parse_screen(size_raw, res_raw):
    size = None
    if size_raw:
        m = re.search(r"(\d+(?:\.\d+)?)", size_raw, re.I)
        if m:
            size = float(m.group(1))

    resolution = None
    if res_raw:
        m = re.search(r"(\d{3,4}\s*[x×]\s*\d{3,4})", res_raw.replace(" ", ""))
        if m:
            resolution = m.group(1).replace("×","x")

    return size, resolution, None


def parse_refresh_rate(raw: str):
    if not raw:
        return None
    m = re.search(r"(\d{2,3})\s*hz", raw, re.I)
    if m:
        return int(m.group(1))
    return None


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
    return None


def parse_weight(raw: str):
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", raw, re.I)
    if m:
        return float(m.group(1))
    return None


def parse_battery(raw: str):
    return raw.strip() if raw else None


def parse_price_to_int(price_raw):
    if price_raw is None:
        return None
    price_raw = str(price_raw)
    nums = re.sub(r"[^\d]", "", price_raw)
    return int(nums) if nums else None


# ---------- Normalize ----------
def normalize_specs(product_name, price_raw, specs_html, manifest):
    specs_map = parse_specs_html(specs_html)

    # CPU: ghép các field lại
    cpu_raw = (
        (specs_map.get("Hãng CPU") or "") + " " +
        (specs_map.get("Công nghệ CPU") or "") + " " +
        (specs_map.get("Loại CPU") or "") + " " +
        (specs_map.get("Bộ xử lý") or "")
    ).strip()

    # GPU
    gpu_raw = (
        (specs_map.get("Hãng (Card Oboard)") or "") + " " +
        (specs_map.get("Tên đầy đủ (Card onbroad)") or "") + " " +
        (specs_map.get("Card đồ họa") or "")
    ).strip()

    # RAM
    ram_raw = specs_map.get("Dung lượng RAM") or specs_map.get("RAM") or ""
    ram_type_raw = specs_map.get("Loại RAM") or ""
    ram_bus = specs_map.get("Tốc độ RAM") or ""
    print("tốc độ tối đa",ram_bus)

    # Storage
    storage_raw = (
        (specs_map.get("Dung lượng SSD") or "")
    ).strip()

    # Screen
    screen_size_raw = specs_map.get("Kích thước màn hình") or ""
    screen_res_raw = specs_map.get("Độ phân giải") or ""

    # Refresh
    refresh_raw = specs_map.get("Tần số quét") or ""

    # Weight
    weight_raw = specs_map.get("Trọng lượng sản phẩm") or specs_map.get("Trọng lượng") or ""

    battery_raw = (
        (specs_map.get("Dung lượng pin") or "") + " " +
        (specs_map.get("Power Supply") or "")
    ).strip()

    # ---- PARSE ----
    cpu_manufacturer, cpu_brand_mod, cpu_gen, cpu_speed = parse_cpu(cpu_raw, specs_map)
    ram_gb, ram_type, bus = parse_ram(ram_raw, ram_type_raw, ram_bus)
    storage_gb = parse_storage(storage_raw)
    screen_size, screen_res, _ = parse_screen(screen_size_raw, screen_res_raw)
    refresh_rate = parse_refresh_rate(refresh_raw)
    gpu_manu = parse_gpu(gpu_raw)
    weight_kg = parse_weight(weight_raw)
    battery = parse_battery(battery_raw)
    price_vnd = parse_price_to_int(price_raw)

    manufacturer = manifest.get("manufacturer") or (product_name.split()[0].lower())

    return {
        "Product Name": product_name,
        "Manufacturer": manufacturer,
        "CPU manufacturer": cpu_manufacturer,
        "CPU brand modifier": cpu_brand_mod,
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
        "Price (VND)": price_vnd,
        "url": manifest.get("url"),
        "saved_path": manifest.get("saved_path"),
        "detail_specs_html_path": manifest.get("detail_specs_html_path"),
    }


# ---------- Load manifest & Test ----------
with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
    manifests = json.load(f)

print(f"Bắt đầu xử lý {TEST_COUNT} mẫu từ {MANIFEST_PATH}")

for i, manifest in enumerate(manifests[:TEST_COUNT]):
    print("\n==========================")
    print("INDEX:", i)
    url = manifest.get("url")
    print("URL:", url)

    product_name = clean_product_name(extract_name_from_url(url))
    print("Product Name:", product_name)

    detail_relative_path = manifest.get("detail_specs_html_path")
    detail_path = os.path.join(PROJECT_ROOT, detail_relative_path) if detail_relative_path else None
    detail_html = load_file_text(detail_path)

    if detail_html is None:
        print(f"❌ detail_specs_html_path not found: {detail_path}")
        continue

    result = normalize_specs(product_name, manifest.get("price"), detail_html, manifest)
    print(result)
