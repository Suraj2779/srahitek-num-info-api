import os
import time
import requests
import duckdb
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional

app = FastAPI(title="SRA CyberTech Ultimate Search API")

# ========== আপনার দেওয়া লিংক ==========
DATASET_BASE = "https://huggingface.co/buckets/MRSHREY197/Hitekdatabase-bucket/resolve/main"

# সব ২০টি ফাইল (Alt 0-9 + Final 0-9)
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]

# ========== ল্যান্ডিং পেজ ==========
LANDING_HTML = """
<!DOCTYPE html>
<html>
<head><title>SRA CyberTech Ultimate API</title>
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
    <p>Dataset: <span style="color:#00ffcc;">MRSHREY197/Hitekdatabase-bucket</span></p>
    <p>Developer: Team SRA (Salman | Raj | Akash)</p>
    <p style="color:#666;">Use: /search?name=rahul</p>
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

# ========== হেলথ চেক ==========
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time(), "dataset": "MRSHREY197/Hitekdatabase-bucket"}

# ========== ডায়াগনস্টিক: কোন কলামগুলো আছে দেখুন ==========
@app.get("/schema")
def show_schema():
    """প্রথম শার্ডের কলামগুলোর নাম ও ডেটা টাইপ দেখায়"""
    conn = None
    try:
        url = f"{DATASET_BASE}/alt_master_shard_0.parquet"
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("SET memory_limit='256MB';")
        conn.execute("SET threads=2;")
        conn.execute("SET http_timeout=60;")
        
        query = f"SELECT * FROM read_parquet('{url}') LIMIT 1"
        df = conn.execute(query).df()
        
        columns_info = []
        for col in df.columns:
            columns_info.append({
                "name": col,
                "dtype": str(df[col].dtype),
                "sample_value": str(df[col].iloc[0]) if not df.empty else None
            })
        
        return {
            "status": "success",
            "dataset": "MRSHREY197/Hitekdatabase-bucket",
            "shard": "alt_master_shard_0.parquet",
            "columns": columns_info,
            "total_columns": len(df.columns),
            "sample_row": df.iloc[0].to_dict() if not df.empty else None
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
    finally:
        if conn:
            conn.close()

# ========== মেইন সার্চ (সব প্যারামিটার সহ) ==========
@app.get("/search")
def search_records(
    mobile: Optional[str] = Query(None, description="Mobile Number"),
    alt: Optional[str] = Query(None, description="Alternate Number"),
    name: Optional[str] = Query(None, description="Name"),
    fname: Optional[str] = Query(None, description="Father Name"),
    id: Optional[str] = Query(None, description="ID"),
    email: Optional[str] = Query(None, description="Email"),
    address: Optional[str] = Query(None, description="Address"),
    limit: int = Query(10, ge=1, le=50, description="Max records")
):
    start_time = time.time()
    
    # ===== প্যারামিটার চেক =====
    # প্রথমে ডেটাসেটের আসল কলামের নাম বের করা যায়? 
    # আমরা একটা ফাংশন বানাবো যা কলামের নাম ম্যাপ করবে
    
    # ডেটাসেটের কলামের নামগুলো (এই ফাইলগুলোর জন্য)
    # আমরা আগে থেকেই জেনে রাখি কলামগুলো কী কী
    # আপনার আউটপুট থেকে দেখা যাচ্ছে: mobile, name, fname, address, alt, circle, id, email
    
    conditions = []
    
    # এখন আমরা প্রতিটি প্যারামিটারের জন্য আলাদাভাবে কোয়েরি বানাবো
    if mobile:
        # mobile কলামে search
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
            content={"status": "error", "message": "At least one search parameter required"}
        )

    where_clause = " AND ".join(conditions)
    all_results = []
    failed_shards = 0
    scanned_count = 0
    shard_names = []

    # ===== সব ২০টি ফাইলেই সার্চ =====
    conn = None
    try:
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")
        conn.execute("SET memory_limit='256MB';")
        conn.execute("SET threads=2;")
        conn.execute("SET http_timeout=60;")
        
        for shard_file in ALL_SHARDS:
            scanned_count += 1
            try:
                url = f"{DATASET_BASE}/{shard_file}"
                
                # ফাইল আছে কিনা চেক
                try:
                    head_resp = requests.head(url, timeout=5)
                    if head_resp.status_code != 200:
                        failed_shards += 1
                        continue
                except:
                    failed_shards += 1
                    continue
                
                # কোয়েরি চালান
                query = f"""
                    SELECT 
                        mobile, name, fname, address, alt, circle, id, email,
                        '{shard_file}' AS _source 
                    FROM read_parquet('{url}') 
                    WHERE {where_clause} 
                    LIMIT {limit}
                """
                cursor = conn.execute(query)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                
                if rows:
                    formatted = [
                        {col: (str(val) if val is not None else "") for col, val in zip(columns, row)}
                        for row in rows
                    ]
                    all_results.extend(formatted)
                    shard_names.append(shard_file)
                    
                    if len(all_results) >= limit:
                        break
                        
            except Exception as e:
                failed_shards += 1
                continue
                
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Database error: {str(e)}",
                "Developer": "Team SRA"
            }
        )
    finally:
        if conn:
            conn.close()

    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    if not all_results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "No records found",
                "shards_checked": scanned_count,
                "shards_failed": failed_shards,
                "time_ms": elapsed_ms
            }
        )

    return {
        "status": "success",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "dataset": "MRSHREY197/Hitekdatabase-bucket",
        "shards_checked": scanned_count,
        "shards_failed": failed_shards,
        "shards_with_data": list(set(shard_names)),
        "time_ms": elapsed_ms,
        "count": len(all_results),
        "results": all_results[:limit]
    }
