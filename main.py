import os
import duckdb
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional

app = FastAPI(title="SRA CyberTech Database Search API")

# ========== কনফিগারেশন ==========
HF_TOKEN = os.getenv("HF_TOKEN", "")  # প্রাইভেট ডেটাসেট হলে টোকেন দেবেন
DATASET_BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

# ২০টি ফাইলের লিস্ট (Alt 0-9, তারপর Final 0-9)
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]

# ========== ডাকবি গ্লোবাল কানেকশন (প্রতিবার নতুন না খুলে রি-ইউজ) ==========
def get_db_connection():
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs;")   # HTTP থেকে পড়ার প্লাগইন
    conn.execute("LOAD httpfs;")      # লোড করা
    conn.execute("SET memory_limit='256MB';")  # Render-এর ৫১২MB-র মধ্যে থাকবে
    conn.execute("SET threads=2;")    # CPU থ্রেড লিমিট
    conn.execute("SET http_timeout=120;")  # বড় ফাইল ডাউনলোডে টাইমআউট না হয়
    return conn

# ========== ল্যান্ডিং পেজ (HTML) ==========
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
        <h1>🚀 SRA CYBERTECH</h1>
        <p>API Gateway: <span class="highlight">Active & Secured</span></p>
        <p>Dataset: <span class="highlight">MRSHREY197/Hitekdatabase</span></p>
        <p style="font-size:0.8em; color:#666;">Developer: Team SRA (Salman | Raj | Akash)</p>
    </div>
</body>
</html>
"""

# ========== এরর হ্যান্ডলার ==========
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": "rejected",
                "message": "Invalid endpoint. Use /search with valid parameters.",
                "Developer": "Team SRA"
            }
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "Developer": "Team SRA"}
    )

# ========== রুট ==========
@app.get("/", response_class=HTMLResponse)
def root_landing_page():
    return HTMLResponse(content=LANDING_PAGE_HTML, status_code=200)

# ========== মেইন সার্চ এন্ডপয়েন্ট (স্টেবল ভার্সন) ==========
@app.get("/search")
def search_records(
    mobile: Optional[str] = Query(None, description="Search by Mobile Number"),
    alt: Optional[str] = Query(None, description="Search by Alternate Number"),
    name: Optional[str] = Query(None, description="Search by Name"),
    fname: Optional[str] = Query(None, description="Search by Father Name"),
    id: Optional[str] = Query(None, description="Search by ID"),
    email: Optional[str] = Query(None, description="Search by Email"),
    address: Optional[str] = Query(None, description="Search by Address"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return")
):
    # কন্ডিশন বানানো
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
    scanned_count = 0

    # ========== সিকোয়েন্সিয়াল সার্চ (মেমোরি বাঁচাতে) ==========
    for shard_file in ALL_SHARDS:
        scanned_count += 1
        conn = None
        try:
            # টোকেন থাকলে URL-এ যোগ করুন
            if HF_TOKEN:
                parquet_url = f"{DATASET_BASE_URL}/{shard_file}?token={HF_TOKEN}"
            else:
                parquet_url = f"{DATASET_BASE_URL}/{shard_file}"

            conn = get_db_connection()
            
            query = f"""
                SELECT *, '{shard_file}' AS _source_file 
                FROM read_parquet('{parquet_url}') 
                WHERE {where_clause} 
                LIMIT {limit}
            """
            cursor = conn.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            if rows:
                formatted_rows = [
                    dict(zip(columns, [str(val) if val is not None else "" for val in row])) 
                    for row in rows
                ]
                all_results.extend(formatted_rows)
                
                # লিমিট পূর্ণ হলে থামুন
                if len(all_results) >= limit:
                    break
        except Exception as e:
            # কোনো শার্ড ফেইল করলে নেক্সটে যান (লগ রাখতে চাইলে প্রিন্ট করুন)
            # print(f"Shard {shard_file} error: {e}")
            continue
        finally:
            if conn:
                conn.close()

    # ফলাফল ফেরত
    if not all_results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "No records found matching your query across the database.",
                "total_shards_checked": scanned_count
            }
        )

    return {
        "status": "success",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "total_shards_checked": scanned_count,
        "count": len(all_results[:limit]),
        "results": all_results[:limit]
    }
