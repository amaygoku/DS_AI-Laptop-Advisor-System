import pandas as pd
from advisor.advisor import recommend_laptops

df = pd.read_csv(r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_features.csv")

query = {
    "usage_type": "gaming",
    "price_max": 25000000,
    "min_ram_gb": 16
}

result = recommend_laptops(df, query, top_n=5)

print(result[[
    "Product Name",
    "Price (VND)",
    "gpu_model",
    "final_score"
]])
