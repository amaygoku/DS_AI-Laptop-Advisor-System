require("dotenv").config();
const express = require("express");

const app = express();

const PORT = process.env.PORT || 3000;
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8000";
const API_PATH = process.env.API_PATH || "/recommend_from_text";

app.set("view engine", "ejs");
app.use(express.urlencoded({ extended: true }));
app.use(express.json());
app.use("/public", express.static("public"));

// Home page
app.get("/", (req, res) => {
  res.render("index", {
    apiBase: API_BASE,
    apiPath: API_PATH,
  });
});

// Proxy endpoint from UI -> FastAPI
app.post("/api/recommend", async (req, res) => {
  try {
    const payload = req.body || {};

    const url = `${API_BASE}${API_PATH}`;
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await r.json();
    if (!r.ok) {
      return res.status(r.status).json(data);
    }
    return res.json(data);
  } catch (e) {
    return res.status(502).json({ error: `UI proxy failed: ${e?.message || e}` });
  }
});

app.listen(PORT, () => {
  console.log(`UI running at http://127.0.0.1:${PORT}`);
  console.log(`Proxy -> ${API_BASE}${API_PATH}`);
});
