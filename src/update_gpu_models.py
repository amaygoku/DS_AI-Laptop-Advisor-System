import csv
import json
import os
import glob

def update_gpu_models():
    csv_path = r'd:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_normalized.csv'
    json_dir = r'd:\DS_project\DS_AI-Laptop-Advisor-System\parsed_products_json'
    
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    if not os.path.exists(json_dir):
        print(f"Error: JSON directory not found at {json_dir}")
        return

    # Load mapping from CSV
    mapping = {}
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                detail_path = row.get('detail_specs_html_path')
                gpu_model = row.get('gpu_model')
                if detail_path:
                    # Normalize path to use forward slashes for matching
                    norm_path = detail_path.replace('\\', '/')
                    mapping[norm_path] = gpu_model
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    updated_count = 0
    total_json_files = 0
    not_found_count = 0
    
    # Iterate through JSON files
    json_files = glob.glob(os.path.join(json_dir, '*.json'))
    total_json_files = len(json_files)
    
    for json_file_path in json_files:
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {json_file_path}: {e}")
            continue
        
        detail_path = data.get('detail_specs_html_path')
        if detail_path:
            # Normalize path in JSON
            norm_detail_path = detail_path.replace('\\', '/')
            
            if norm_detail_path in mapping:
                gpu_model = mapping[norm_detail_path]
                data['GPU model'] = gpu_model
                
                # Save updated JSON
                try:
                    with open(json_file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    updated_count += 1
                except Exception as e:
                    print(f"Error writing {json_file_path}: {e}")
            else:
                not_found_count += 1
        
    print(f"Total JSON files processed: {total_json_files}")
    print(f"Successfully updated: {updated_count}")
    print(f"Matches not found in CSV: {not_found_count}")

if __name__ == "__main__":
    update_gpu_models()
