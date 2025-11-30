import re
import csv
from pathlib import Path

from bs4 import BeautifulSoup

COLUMNS = [
    "Manufacturer",
    "CPU manufacturer",
    "CPU brand modifier",
    "CPU generation",
    "CPU Speed (GHz)",
    "RAM (GB)",
    "RAM Type",
    "Bus (MHz)",
    "Storage (GB)",
    "Screen Size (inch)",
    "Screen Resolution",
    "Refresh Rate (Hz)",
    "GPU manufacturer",
    "Weight (kg)",
    "Battery",
]

HTML_FILES = [f"data/anphat/detail_htmls/hp_{i}_specs.html" for i in range(6)]  # sửa nếu cần


# ----------------- Các hàm parse nhỏ ----------------- #

def parse_manufacturer(text: str):
    if not text:
        return None
    # "Laptop HP" -> "HP"
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
    Lấy tốc độ GHz lớn nhất xuất hiện trong text.
    """
    for src in [cpu_speed_text, cpu_speed_text2, cpu_info]:
        if not src:
            continue
        # dạng "up to 4.7 GHz"
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
    m2 = re.search(r"\b(LP?DDR\d)\b", t, re.I)
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
    m = re.search(r"(\d+)\s*GB", t, re.I)
    return int(m.group(1)) if m else None


def parse_screen_size_inch(screen_size_text: str):
    if not screen_size_text:
        return None
    t = screen_size_text.replace("\xa0", " ")
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*inch", t, re.I)
    return float(m.group(1)) if m else None


def parse_screen_resolution(screen_res_text: str):
    if not screen_res_text:
        return None
    t = screen_res_text.replace("\xa0", " ")
    m = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", t)
    if not m:
        return None
    return f"{m.group(1)} x {m.group(2)}"


def parse_refresh_hz(refresh_text, screen_size_text, screen_extra):
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
    if re.search(r"NVIDIA", gpu_text, re.I):
        return "NVIDIA"
    if re.search(r"AMD", gpu_text, re.I):
        return "AMD"
    if re.search(r"Intel", gpu_text, re.I):
        return "Intel"
    return None


def parse_weight_kg(weight_text: str):
    if not weight_text:
        return None
    t = weight_text.replace(",", ".").replace("\xa0", " ")
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", t, re.I)
    return float(m.group(1)) if m else None


def parse_battery(battery_text: str):
    return battery_text.strip() if battery_text else None


# ----------------- Parse HTML thành raw spec ----------------- #

def parse_specs_from_html(path: Path):
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
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
        # Header section (1 cột, colspan=2)
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


# ----------------- Build row cho CSV ----------------- #

def build_row(spec_raw: dict):
    manu = parse_manufacturer(spec_raw["manufacturer"])
    cpu_manu, cpu_brand, cpu_gen = parse_cpu_fields(spec_raw["cpu_info"])
    cpu_speed = parse_cpu_speed(
        spec_raw["cpu_speed_text"],
        spec_raw["cpu_speed_text2"],
        spec_raw["cpu_info"],
    )
    ram_gb, ram_type = parse_ram_gb_and_type(spec_raw["ram_text"])
    bus = parse_bus_mhz(spec_raw["ram_bus_text"], spec_raw["ram_text"])
    storage = parse_storage_gb(spec_raw["storage_text"])
    screen_size = parse_screen_size_inch(spec_raw["screen_size_text"])
    screen_res = parse_screen_resolution(spec_raw["screen_res_text"])
    refresh = parse_refresh_hz(
        spec_raw["refresh_text"],
        spec_raw["screen_size_text"],
        spec_raw["screen_extra_text"],
    )
    gpu_manu = parse_gpu_manufacturer(spec_raw["gpu_text"])
    weight = parse_weight_kg(spec_raw["weight_text"])
    battery = parse_battery(spec_raw["battery_text"])

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


# ----------------- Main ----------------- #

def main():
    rows = []
    for fname in HTML_FILES:
        path = Path(fname)
        if not path.exists():
            print(f"WARNING: {fname} not found, skip")
            continue
        spec_raw = parse_specs_from_html(path)
        row = build_row(spec_raw)
        rows.append(row)

    # Ghi ra CSV
    out_path = Path("data/anphat/hp_specs_parsed.csv")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Saved {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
