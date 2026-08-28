import os
import time
import math
import requests
import pandas as pd
import pyarrow.parquet as pq
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

# ========== কনফিগারেশন ==========
REPO_NAME = "MRSHREY197/Hitekdatabase"
BASE_URL = f"https://huggingface.co/datasets/{REPO_NAME}/resolve/main"
TIMEOUT = 120
MAX_RETRIES = 2
SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']

# ========== ডায়নামিক ফাইল লিস্ট ফেচ ==========
def fetch_parquet_files():
    """Hugging Face API থেকে আসল ফাইল নামগুলো খুঁজে বের করে"""
    api_url = f"https://huggingface.co/api/datasets/{REPO_NAME}/refs/main"
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # 'tree' কী তে ফাইলের তালিকা থাকে
        tree = data.get('tree', [])
        if not tree and isinstance(data, list):
            tree = data
            
        files = [item['path'] for item in tree if item['path'].endswith('.parquet')]
        if files:
            print(f"✅ পাওয়া গেছে {len(files)} টি Parquet ফাইল: {files}")
            return files
    except Exception as e:
        print(f"⚠️ ফাইল লিস্ট ফেচ করতে ব্যর্থ: {e}")
    
    # API কাজ না করলে ফ্যালব্যাক (সাধারণ নাম)
    fallback = []
    for i in range(10):
        fallback.append(f"alt_master_shard_{i}.parquet")
        fallback.append(f"final_master_shard_{i}.parquet")
    print(f"⚠️ ফ্যালব্যাক ব্যবহার করা হচ্ছে: {fallback}")
    return fallback

# অ্যাপ স্টার্ট হলে ফাইল লিস্ট লোড করুন
FILE_NAMES = fetch_parquet_files()

# ========== হেল্পার ফাংশন ==========
def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj

def fetch_parquet_safe(file_name):
    url = f"{BASE_URL}/{file_name}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            table = pq.read_table(io.BytesIO(response.content))
            df = table.to_pandas()
            df = df.fillna("")
            return df
        except Exception:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2)
    return None

def search_in_all_files(query):
    if not query or len(query) < 2:
        return [], 0, 0
    
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        df = fetch_parquet_safe(file_name)
        if df is None:
            failed += 1
            continue
        success += 1
        
        mask = pd.Series([False] * len(df))
        for col in SEARCH_COLUMNS:
            if col in df.columns:
                mask = mask | df[col].astype(str).str.contains(query, case=False, na=False)
        
        filtered_df = df[mask]
        if not filtered_df.empty:
            records = filtered_df.to_dict(orient='records')
            for rec in records:
                rec['_source_file'] = file_name
            all_results.extend(records)
    
    return all_results, success, failed

def search_number_in_all_files(number):
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        df = fetch_parquet_safe(file_name)
        if df is None:
            failed += 1
            continue
        success += 1
        
        mask = pd.Series([False] * len(df))
        if 'mobile' in df.columns:
            mask = mask | df['mobile'].astype(str).str.contains(number, case=False, na=False)
        if 'alt' in df.columns:
            mask = mask | df['alt'].astype(str).str.contains(number, case=False, na=False)
        
        filtered_df = df[mask]
        if not filtered_df.empty:
            records = filtered_df.to_dict(orient='records')
            for rec in records:
                rec['_source_file'] = file_name
            all_results.extend(records)
    
    return all_results, success, failed

# ========== এন্ডপয়েন্ট ==========
@app.get("/")
def home():
    return {
        "status": "SRA CyberTech API is LIVE",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "files_found": len(FILE_NAMES),
        "files_list": FILE_NAMES[:5],  # প্রথম ৫টা দেখাচ্ছি
        "endpoints": {
            "/search?q=...": "Search in all fields",
            "/FetchData?Number=...": "Search by mobile or alt number"
        }
    }

@app.get("/search")
def search_all_fields(q: str = Query(..., min_length=2, description="Search term")):
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
        "results": clean_nan(results),
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }

@app.get("/FetchData")
def fetch_by_number(Number: str = Query(..., min_length=10, max_length=15, description="Mobile number")):
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
        "results": clean_nan(results),
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
