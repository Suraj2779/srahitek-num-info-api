import os
import io
import time
import math
import requests
import pandas as pd
import pyarrow.parquet as pq
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========== কনফিগারেশন ==========
REPO_NAME = "MRSHREY197/Hitekdatabase"
BASE_URL = f"https://huggingface.co/datasets/{REPO_NAME}/resolve/main"
TIMEOUT = 120
MAX_RETRIES = 2
SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']

# ========== Hugging Face API থেকে ফাইল লিস্ট ফেচ ==========
def fetch_parquet_files():
    """Hugging Face API থেকে সব .parquet ফাইলের নাম নিয়ে আসে"""
    api_url = f"https://huggingface.co/api/datasets/{REPO_NAME}"
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        siblings = data.get('siblings', [])
        files = [item['rfilename'] for item in siblings if item['rfilename'].endswith('.parquet')]
        if files:
            print(f"✅ পাওয়া গেছে {len(files)} টি Parquet ফাইল")
            return files
        else:
            print("⚠️ কোনো Parquet ফাইল পাওয়া যায়নি")
            return []
    except Exception as e:
        print(f"⚠️ ফাইল লিস্ট ফেচ করতে ব্যর্থ: {e}")
        fallback = []
        for i in range(10):
            fallback.append(f"alt_master_shard_{i}.parquet")
            fallback.append(f"final_master_shard_{i}.parquet")
        print(f"⚠️ ফ্যালব্যাক ব্যবহার করা হচ্ছে: {len(fallback)} টি ফাইল")
        return fallback

# অ্যাপ স্টার্ট হলে ফাইল লিস্ট লোড করুন
FILE_NAMES = fetch_parquet_files()
print(f"📁 মোট ফাইল: {len(FILE_NAMES)}")

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
@app.route('/')
def home():
    return jsonify({
        "status": "SRA CyberTech API is LIVE 🚀",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "files_found": len(FILE_NAMES),
        "files_list": FILE_NAMES,
        "endpoints": {
            "/search?q=...": "Search in all fields (mobile, name, fname, address, alt, circle, email, id)",
            "/FetchData?Number=...": "Search by mobile or alt number"
        }
    })

@app.route('/search')
def search_all_fields():
    query = request.args.get('q')
    if not query or len(query) < 2:
        return jsonify({
            "status": "error",
            "message": "Missing 'q' parameter or query too short (min 2 chars)",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
    start = time.time()
    results, success, failed = search_in_all_files(query)
    elapsed = (time.time() - start) * 1000
    
    if not results:
        return jsonify({
            "status": "not_found",
            "query": query,
            "files_successful": success,
            "files_failed": failed,
            "total_files": len(FILE_NAMES),
            "time_ms": round(elapsed, 2),
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 404
    
    return jsonify({
        "status": "success",
        "query": query,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": clean_nan(results),
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

@app.route('/FetchData')
def fetch_by_number():
    number = request.args.get('Number')
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({
            "status": "rejected",
            "message": "Invalid parameter. Use /FetchData?Number=01XXXXXXXXX",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
    start = time.time()
    results, success, failed = search_number_in_all_files(number)
    elapsed = (time.time() - start) * 1000
    
    if not results:
        return jsonify({
            "status": "not_found",
            "phone": number,
            "files_successful": success,
            "files_failed": failed,
            "total_files": len(FILE_NAMES),
            "time_ms": round(elapsed, 2),
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 404
    
    return jsonify({
        "status": "success",
        "phone": number,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": clean_nan(results),
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "status": "rejected",
        "message": "Invalid endpoint. Use /search?q=... or /FetchData?Number=...",
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
