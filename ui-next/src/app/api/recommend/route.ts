import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const base = process.env.FASTAPI_BASE_URL || "http://127.0.0.1:8000";
    const path = process.env.FASTAPI_RECOMMEND_PATH || "/recommend_from_text";
    const url = `${base}${path}`;

    const payload = await req.json();

    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      // Node runtime: do not cache
      cache: "no-store"
    });

    const text = await r.text();
    // Pass through status + JSON if possible
    const contentType = r.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return NextResponse.json(JSON.parse(text), { status: r.status });
    }
    return new NextResponse(text, { status: r.status });
  } catch (e: any) {
    return NextResponse.json(
      { error: `UI proxy failed: ${e?.message || String(e)}` },
      { status: 502 }
    );
  }
}
