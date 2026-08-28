import os
import time
import duckdb
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

# DuckDB কানেক্ট
con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# আপনার ডেটাসেটের ফাইল লিস্ট
REPO_NAME = "MRSHREY197/Hitekdatabase"
BASE_URL = f"https://huggingface.co/datasets/{REPO_NAME}/resolve/main"

# ২০টি ফাইল
FILE_NAMES = []
for i in range(10):
    FILE_NAMES.append(f"alt_master_shard_{i}.parquet")
    FILE_NAMES.append(f"final_master_shard_{i}.parquet")

# যে কলামে সার্চ করবেন
SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']

# ===== হেল্পার ফাংশন =====
def search_in_all_files(query):
    if not query or len(query) < 2:
        return [], 0, 0
    
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        url = f"{BASE_URL}/{file_name}"
        try:
            # DuckDB দিয়ে SQL চালান
            conditions = []
            for col in SEARCH_COLUMNS:
                conditions.append(f"CAST({col} AS VARCHAR) ILIKE '%{query}%'")
            where_clause = " OR ".join(conditions)
            
            sql = f"""
                SELECT *, '{file_name}' AS _source_file
                FROM read_parquet('{url}')
                WHERE {where_clause}
            """
            df = con.execute(sql).df()
            if not df.empty:
                records = df.to_dict(orient='records')
                all_results.extend(records)
            success += 1
        except Exception:
            failed += 1
            continue
    
    return all_results, success, failed

def search_number_in_all_files(number):
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        url = f"{BASE_URL}/{file_name}"
        try:
            sql = f"""
                SELECT *, '{file_name}' AS _source_file
                FROM read_parquet('{url}')
                WHERE CAST(mobile AS VARCHAR) = '{number}' OR CAST(alt AS VARCHAR) = '{number}'
            """
            df = con.execute(sql).df()
            if not df.empty:
                records = df.to_dict(orient='records')
                all_results.extend(records)
            success += 1
        except Exception:
            failed += 1
            continue
    
    return all_results, success, failed

# ===== এন্ডপয়েন্ট =====
@app.get("/")
def home():
    return {
        "status": "SRA CyberTech API is LIVE 🚀",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "files_found": len(FILE_NAMES),
        "endpoints": {
            "/search?q=...": "Search in all fields",
            "/FetchData?Number=...": "Search by mobile or alt number"
        }
    }

@app.get("/search")
def search_all_fields(q: str = Query(..., min_length=2)):
    start = time.time()
    results, success, failed = search_in_all_files(q)
    elapsed = (time.time() - start) * 1000
    
    if not results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "query": q,
                "files_successful": success,
                "files_failed": failed,
                "total_files": len(FILE_NAMES),
                "time_ms": round(elapsed, 2),
                "Developer": "Team SRA (Salman | Raj | Akash)"
            }
        )
    
    return {
        "status": "success",
        "query": q,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": results,
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }

@app.get("/FetchData")
def fetch_by_number(Number: str = Query(..., min_length=10, max_length=15)):
    start = time.time()
    results, success, failed = search_number_in_all_files(Number)
    elapsed = (time.time() - start) * 1000
    
    if not results:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "phone": Number,
                "files_successful": success,
                "files_failed": failed,
                "total_files": len(FILE_NAMES),
                "time_ms": round(elapsed, 2),
                "Developer": "Team SRA (Salman | Raj | Akash)"
            }
        )
    
    return {
        "status": "success",
        "phone": Number,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": results,
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "rejected",
            "message": "Invalid endpoint. Use /search?q=... or /FetchData?Number=...",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }
    )
