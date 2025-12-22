import pandas as pd
from advisor.advisor import recommend_laptops

df = pd.read_csv(r"D:\DS_project\DS_AI-Laptop-Advisor-System\data\processed\laptops_features.csv")

query = {
    "price_max": 15000000,
}

result = recommend_laptops(df, query, top_n=5)
if result.empty:
    print("❌ Không có laptop phù hợp. Gợi ý nới điều kiện.")
else:
    print(result[[
        "Product Name",
        "Price (VND)",
        "gaming_score",
        "office_score",
        "ai_graphics_score",
        "final_score"
    ]])
    