import os
import time
import duckdb
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional

app = FastAPI(title="SRA CyberTech Ultimate Search API")

# ======== শুধু এই ডেটাসেট ========
DATASET_BASE = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

# সব ২০টি ফাইল (Alt 0-9 + Final 0-9)
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]

# ========== ল্যান্ডিং পেজ ==========
LANDING_HTML = """
<!DOCTYPE html>
<html>
<head><title>SRA CyberTech LIVE</title>
<style>
body{background:#000;color:#0f0;font-family:monospace;text-align:center;padding-top:15%;}
h1{color:#00ffcc;font-size:3em;text-shadow:0 0 20px #00ffcc;}
.status{color:#0f0;animation:blink 1s infinite;}
@keyframes blink{50%{opacity:0;}}
</style>
</head>
<body>
    <h1>🚀 SRA CYBERTECH</h1>
    <p>Status: <span class="status">● ULTIMATE LIVE</span></p>
    <p>Dataset: MRSHREY197/Hitekdatabase</p>
    <p>Developer: Team SRA (Salman | Raj | Akash)</p>
    <p style="color:#666;">Try: /search?mobile=9831477801  or  /search?name=rahul</p>
</body>
</html>
"""

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(exc.detail), "Developer": "Team SRA"}
    )

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content=LANDING_HTML)

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": time.time()}

# ========== ডিবাগ ==========
@app.get("/debug/schema")
def debug_schema():
    try:
        url = f"{DATASET_BASE}/alt_master_shard_0.parquet"
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("SET http_timeout=120;")
        query = f"SELECT * FROM read_parquet('{url}') LIMIT 1"
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        conn.close()
        return {
            "dataset": DATASET_BASE,
            "columns": columns,
            "sample": dict(zip(columns, row)) if row else {}
        }
    except Exception as e:
        return {"error": str(e)}

# ========== মেইন সার্চ ==========
@app.get("/search")
def search(
    mobile: Optional[str] = Query(None),
    alt: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    fname: Optional[str] = Query(None),
    id: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    address: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50)
):
    start = time.time()
    conditions = []

    if mobile:
        conditions.append(f"CAST(mobile AS VARCHAR) LIKE '%{mobile}%'")
    if alt:
        conditions.append(f"CAST(alt AS VARCHAR) LIKE '%{alt}%'")
    if name:
        conditions.append(f"LOWER(name) LIKE LOWER('%{name}%')")
    if fname:
        conditions.append(f"LOWER(fname) LIKE LOWER('%{fname}%')")
    if id:
        conditions.append(f"CAST(id AS VARCHAR) LIKE '%{id}%'")
    if email:
        conditions.append(f"LOWER(email) LIKE LOWER('%{email}%')")
    if address:
        conditions.append(f"LOWER(address) LIKE LOWER('%{address}%')")

    if not conditions:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Give at least one parameter"})

    where = " AND ".join(conditions)
    all_results = []
    failed = 0
    scanned = 0

    conn = None
    try:
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("SET memory_limit='256MB';")
        conn.execute("SET threads=2;")
        conn.execute("SET http_timeout=120;")  # ২ মিনিট টাইমআউট

        for shard in ALL_SHARDS:
            scanned += 1
            try:
                url = f"{DATASET_BASE}/{shard}"
                q = f"""
                    SELECT *,
                        '{shard}' AS _source
                    FROM read_parquet('{url}')
                    WHERE {where}
                    LIMIT {limit}
                """
                cursor = conn.execute(q)
                cols = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                if rows:
                    formatted = [
                        {col: (str(val) if val is not None else "") for col, val in zip(cols, row)}
                        for row in rows
                    ]
                    all_results.extend(formatted)
                    if len(all_results) >= limit:
                        break
            except Exception as e:
                failed += 1
                continue
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if conn:
            conn.close()

    elapsed = round((time.time() - start) * 1000, 2)

    if not all_results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "shards_checked": scanned,
                "shards_failed": failed,
                "time_ms": elapsed,
                "tip": "Check /debug/schema to see actual column names"
            }
        )

    return {
        "status": "success",
        "developer": "Team SRA",
        "shards_checked": scanned,
        "shards_failed": failed,
        "time_ms": elapsed,
        "count": len(all_results),
        "results": all_results[:limit]
    }
