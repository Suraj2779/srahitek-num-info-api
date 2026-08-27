import os
import time
import logging
from typing import Optional
from contextlib import contextmanager

import duckdb
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

# ========== লগিং সেটআপ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("sra-api")

# ========== FastAPI অ্যাপ ==========
app = FastAPI(
    title="SRA CyberTech Search API",
    description="Multi-shard Parquet search engine powered by DuckDB",
    version="3.0.0"
)

# সিকিউরিটি: শুধু নির্দিষ্ট হোস্ট থেকে কল গ্রহণ (Render-এর জন্য)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # প্রোডাকশনে নির্দিষ্ট ডোমেইন দিন
)

# ========== কনফিগারেশন ==========
DATASET_BASE = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]
HF_TOKEN = os.getenv("HF_TOKEN", "")

# DuckDB কানেকশন পুল (প্রতি রিকোয়েস্টে নতুন)
@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("SET memory_limit='256MB';")
        conn.execute("SET threads=2;")
        conn.execute("SET http_timeout=60;")  # 60 সেকেন্ড টাইমআউট
        yield conn
    except Exception as e:
        logger.error(f"DuckDB connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

# ========== ল্যান্ডিং পেজ ==========
LANDING_HTML = """
<!DOCTYPE html>
<html>
<head><title>SRA CyberTech API</title>
<style>
body{background:#0a0a0a;color:#00ffcc;font-family:monospace;text-align:center;padding-top:15%}
h1{font-size:3em;text-shadow:0 0 20px #00ffcc}
.status{color:#0f0;animation:blink 1s infinite}
@keyframes blink{50%{opacity:0}}
</style>
</head>
<body>
<h1>🚀 SRA CYBERTECH</h1>
<p>Status: <span class="status">● LIVE</span></p>
<p>Developer: Team SRA (Salman | Raj | Akash)</p>
<p style="color:#888;font-size:0.8em;">Use /search?name=rahul or /search?mobile=9876543210</p>
</body>
</html>
"""

# ========== এরর হ্যান্ডলার ==========
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "Developer": "Team SRA"
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error. Please try again later.",
            "Developer": "Team SRA"
        }
    )

# ========== হেলথ চেক (Render-এর জন্য) ==========
@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": time.time()}

# ========== রুট ==========
@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content=LANDING_HTML)

# ========== মেইন সার্চ এন্ডপয়েন্ট (ক্র্যাশ-প্রুফ) ==========
@app.get("/search")
def search(
    request: Request,
    mobile: Optional[str] = Query(None, regex="^[0-9]{10,15}$", description="Mobile number (10-15 digits)"),
    alt: Optional[str] = Query(None, regex="^[0-9]{10,15}$", description="Alternate number"),
    name: Optional[str] = Query(None, min_length=2, max_length=50, description="Full name"),
    fname: Optional[str] = Query(None, min_length=2, max_length=50, description="Father's name"),
    id: Optional[str] = Query(None, max_length=30, description="ID number"),
    email: Optional[str] = Query(None, max_length=50, description="Email address"),
    address: Optional[str] = Query(None, max_length=100, description="Address"),
    limit: int = Query(20, ge=1, le=50, description="Max results (1-50)")
):
    start_time = time.time()
    logger.info(f"Search request from {request.client.host} with params: {dict(request.query_params)}")

    # ===== ১. কন্ডিশন বিল্ড =====
    conditions = []
    if mobile:
        conditions.append(f"mobile = '{mobile}'")
    if alt:
        conditions.append(f"alt = '{alt}'")
    if name:
        conditions.append(f"LOWER(name) LIKE '%{name.lower()}%'")
    if fname:
        conditions.append(f"LOWER(fname) LIKE '%{fname.lower()}%'")
    if id:
        conditions.append(f"id = '{id}'")
    if email:
        conditions.append(f"LOWER(email) LIKE '%{email.lower()}%'")
    if address:
        conditions.append(f"LOWER(address) LIKE '%{address.lower()}%'")

    if not conditions:
        raise HTTPException(status_code=400, detail="At least one search parameter required")

    where_clause = " AND ".join(conditions)

    # ===== ২. সিকোয়েন্সিয়াল সার্চ (সব শার্ড) =====
    all_results = []
    scanned = 0
    errors = []

    for shard in ALL_SHARDS:
        scanned += 1
        try:
            with get_db_connection() as conn:
                token_param = f"?token={HF_TOKEN}" if HF_TOKEN else ""
                parquet_url = f"{DATASET_BASE}/{shard}{token_param}"
                
                query = f"""
                    SELECT 
                        mobile, name, fname, address, alt, circle, id, email,
                        '{shard}' AS _source_file
                    FROM read_parquet('{parquet_url}') 
                    WHERE {where_clause}
                    LIMIT {limit - len(all_results)}
                """
                cursor = conn.execute(query)
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
            error_msg = f"Shard {shard} failed: {str(e)[:100]}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    # ===== ৩. ফলাফল ফেরত =====
    if not all_results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "No matching records found",
                "shards_scanned": scanned,
                "developer": "Team SRA"
            }
        )

    return {
        "status": "success",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "shards_scanned": scanned,
        "shards_with_errors": len(errors),
        "count": len(all_results),
        "time_ms": round((time.time() - start_time) * 1000, 2),
        "results": all_results[:limit]
    }
