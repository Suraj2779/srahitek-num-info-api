import os
import duckdb
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional

app = FastAPI(title="SRA CyberTech Database Search API")

HF_TOKEN = os.getenv("HF_TOKEN", "")
DATASET_BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

# Saari 20 files ki list generate kar rahe hain
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]

LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SRA CyberTech API Gateway</title>
    <style>
        body { margin: 0; background-color: #050505; color: #00ffcc; font-family: 'Courier New', Courier, monospace; }
        .overlay { 
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); 
            text-align: center; background: rgba(10, 10, 10, 0.85); padding: 40px; 
            border: 1px solid #00ffcc; border-radius: 12px; box-shadow: 0 0 25px rgba(0, 255, 204, 0.3); 
        }
        h1 { margin: 0 0 15px 0; font-size: 2.5em; text-transform: uppercase; letter-spacing: 4px; }
        p { font-size: 1.1em; color: #ccc; }
        .highlight { color: #00ffcc; font-weight: bold; }
    </style>
</head>
<body>
    <div class="overlay">
        <h1>SYSTEM ONLINE</h1>
        <p>API Gateway: <span class="highlight">Active & Secured</span></p>
        <p>Dataset: <span class="highlight">MRSHREY197/Hitekdatabase</span></p>
    </div>
</body>
</html>
"""

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": "rejected",
                "message": "Invalid endpoint. Use /search with valid parameters.",
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
            }
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}
    )

@app.get("/", response_class=HTMLResponse)
def root_landing_page():
    return HTMLResponse(content=LANDING_PAGE_HTML, status_code=200)

def search_single_shard(shard_file: str, where_clause: str, limit: int):
    """Ek single shard file ko scan karne ke liye execution function"""
    conn = None
    try:
        if HF_TOKEN:
            parquet_url = f"{DATASET_BASE_URL}/{shard_file}?token={HF_TOKEN}"
        else:
            parquet_url = f"{DATASET_BASE_URL}/{shard_file}"

        conn = duckdb.connect()
        conn.execute("SET memory_limit='150MB';")
        conn.execute("SET threads=1;")

        query = f"SELECT *, '{shard_file}' AS _source_file FROM read_parquet('{parquet_url}') WHERE {where_clause} LIMIT {limit}"
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        if rows:
            return [dict(zip(columns, [str(val) if val is not None else "" for val in row])) for row in rows]
        return []
    except Exception:
        return []
    finally:
        if conn:
            conn.close()

@app.get("/search")
def search_records(
    mobile: Optional[str] = Query(None, description="Search by Mobile Number"),
    alt: Optional[str] = Query(None, description="Search by Alternate Number"),
    name: Optional[str] = Query(None, description="Search by Name"),
    fname: Optional[str] = Query(None, description="Search by Father Name"),
    id: Optional[str] = Query(None, description="Search by ID"),
    email: Optional[str] = Query(None, description="Search by Email"),
    address: Optional[str] = Query(None, description="Search by Address"),
    limit: int = Query(50, description="Max records to return")
):
    # Dynamic Search Conditions
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
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Kam se kam ek search parameter (mobile, alt, name, fname, id, email, address) dena zaroori hai."
            }
        )

    where_clause = " AND ".join(conditions)
    all_results = []

    # Parallel Scan across all 20 files with max 3 workers to prevent memory overload
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(search_single_shard, shard, where_clause, limit) for shard in ALL_SHARDS]
        for future in as_completed(futures):
            res = future.result()
            if res:
                all_results.extend(res)
                if len(all_results) >= limit:
                    break

    if not all_results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "No records found matching your query across all 20 database shards."
            }
        )

    return {
        "status": "success",
        "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
        "total_shards_scanned": 20,
        "count": len(all_results[:limit]),
        "results": all_results[:limit]
    }
