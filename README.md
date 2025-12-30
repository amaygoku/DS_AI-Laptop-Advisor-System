# Laptop Advisor System

Hệ thống tư vấn laptop sử dụng AI để hiểu ý định người dùng và đề xuất laptop phù hợp.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy hệ thống

### 1. Backend API
```bash
uvicorn src.api.main:app --reload --port 8000
```

### 2. Frontend
Mở file `frontend/index.html` trong trình duyệt.

---

## Evaluation Module

Module đánh giá chất lượng hệ thống đề xuất sử dụng các metrics chuẩn IR.

### Metrics

| Metric | Mô tả |
|--------|-------|
| **Precision@K** | Tỷ lệ laptops phù hợp trong top-K |
| **NDCG@K** | Normalized Discounted Cumulative Gain |
| **MRR** | Mean Reciprocal Rank |
| **CSR** | Constraint Satisfaction Rate |

### Cách chạy

**1. Đảm bảo server đang chạy:**
```bash
uvicorn src.api.main:app --port 8000
```

**2. Chạy evaluation với file test queries:**
```bash
python3 -m src.evaluation.run_evaluation \
    --file data/test_queries.json \
    --output data/evaluation_results.json \
    --metrics-output data/metrics_summary.json
```

**3. Chạy evaluation với 1 query:**
```bash
python -m src.evaluation.run_evaluation \
    --query "Tôi cần laptop gaming giá 25 triệu"
```

### Options

| Option | Mô tả | Mặc định |
|--------|-------|----------|
| `-f, --file` | File JSON chứa test queries | - |
| `-q, --query` | Đánh giá 1 query | - |
| `-o, --output` | Lưu kết quả đầy đủ | - |
| `-m, --metrics-output` | Lưu metrics summary | - |
| `--top-k` | Số recommendations đánh giá | 3 |
| `--sleep` | Delay giữa các Gemini calls | 1.5s |

### Format test queries

```json
[
    {
        "query": "Laptop gaming giá 25 triệu",
        "expected_constraints": {
            "is_gaming_ready": true,
            "price_min": 23000000,
            "price_max": 27000000
        }
    }
]
```

### Kết quả mẫu

```
📊 AGGREGATE EVALUATION RESULTS
═══════════════════════════════
📈 Tested 60 queries (Top-3)

📉 Aggregate Metrics:
   • Avg Precision@K: 89.33%
   • Avg NDCG@K: 0.9029
   • MRR: 0.9200
   • Avg CSR: 68.18%
```
