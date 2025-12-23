export default function LaptopCards({ results }: { results: any[] }) {
  if (!Array.isArray(results) || results.length === 0) {
    return <div className="muted">Không có laptop phù hợp (sau lọc).</div>;
  }

  const fmtVnd = (n: any) => {
    if (typeof n !== "number") return "N/A";
    return n.toLocaleString("vi-VN") + "đ";
  };

  return (
    <div className="cards">
      {results.map((r, i) => (
        <div className="card" key={i}>
          <div className="cardTitle">
            {r.product_name || "Laptop"}
            {r.manufacturer ? ` — ${r.manufacturer}` : ""}
          </div>
          <div className="cardLine">Giá: <b>{fmtVnd(r.price_vnd)}</b></div>
          <div className="cardLine">Nặng: <b>{r.weight_kg ?? "N/A"}kg</b></div>
          <div className="cardLine">
            RAM: <b>{r.ram_gb ?? "N/A"}GB</b> • SSD: <b>{r.storage_gb ?? "N/A"}GB</b>
          </div>

          <div className="badges">
            {r.final_score != null && <span className="badge">final: {r.final_score}</span>}
            {r.task_score != null && <span className="badge">task: {Number(r.task_score).toFixed(2)}</span>}
            {r.price_fit != null && <span className="badge">price_fit: {Number(r.price_fit).toFixed(2)}</span>}
            {r.affordability_score != null && <span className="badge">afford: {Number(r.affordability_score).toFixed(2)}</span>}
            {r.weight_score != null && <span className="badge">light: {Number(r.weight_score).toFixed(2)}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
