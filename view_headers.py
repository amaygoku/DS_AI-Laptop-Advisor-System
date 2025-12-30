import pandas as pd

# Just read headers and first few rows
df_old = pd.read_csv(r'data\processed\laptops_features2 (1).csv', nrows=5)
df_new = pd.read_csv(r'data\processed\laptops_features2.csv', nrows=5)

print("OLD COLUMNS:", list(df_old.columns))
print("\nNEW COLUMNS:", list(df_new.columns))

score_cols = [c for c in df_new.columns if 'score' in c.lower()]
print("\nSCORE COLUMNS:", score_cols)

print("\nOLD DATA (first 5 rows, score columns only):")
print(df_old[score_cols])

print("\nNEW DATA (first 5 rows, score columns only):")
print(df_new[score_cols])
