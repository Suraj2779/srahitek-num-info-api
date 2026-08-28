import os
import time
import json
import requests
import pandas as pd
import pyarrow.parquet as pq
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========== কনফিগারেশন ==========
BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
FILE_NAMES = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]
SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']
CACHE_DIR = "/tmp/parquet_cache"  # Render-এর tmp ডিরেক্টরিতে ক্যাশে করব

# ক্যাশে ডিরেক্টরি তৈরি
os.makedirs(CACHE_DIR, exist_ok=True)

# ========== ক্যাশে ফাংশন ==========
def get_cached_df(file_name):
    """ফাইল ডাউনলোড করে ক্যাশে থেকে পড়ে, নাহলে ডাউনলোড করে ক্যাশে সেভ করে"""
    cache_path = os.path.join(CACHE_DIR, file_name.replace('.parquet', '.pkl'))
    
    # ক্যাশে থাকলে সেখান থেকে লোড করি
    if os.path.exists(cache_path):
        try:
            return pd.read_pickle(cache_path)
        except:
            pass  # করাপ্ট হলে ডাউনলোড করব
    
    # ডাউনলোড করি
    url = f"{BASE_URL}/{file_name}"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        table = pq.read_table(io.BytesIO(response.content))
        df = table.to_pandas().fillna("")
        # ক্যাশে সেভ করি
        df.to_pickle(cache_path)
        return df
    except Exception as e:
        return None

def search_in_all_files(query):
    """সব ফাইলে ক্যাশে থেকে পড়ে সার্চ করে"""
    if not query or len(query) < 2:
        return [], 0, 0, 0
    
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        df = get_cached_df(file_name)
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
    
    return all_results, success, failed, len(FILE_NAMES)

# ========== এন্ডপয়েন্টসমূহ ==========
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html><head><title>SRA CyberTech - CACHED</title>
    <style>body{background:#000;color:#0f0;text-align:center;padding-top:15%;font-family:monospace;} h1{color:#00ffcc;}</style>
    </head>
    <body>
        <h1>🚀 SRA CYBERTECH CACHED API</h1>
        <p>Status: <span style="color:#0f0;">● LIVE</span></p>
        <p>Developer: Salman | Raj | Akash</p>
        <p class="dev">Use: /search?q=Gautam</p>
        <p class="dev">Use: /FetchData?Number=9831477801</p>
        <p class="dev">Data cached in /tmp after first request</p>
    </body>
    </html>
    """

@app.route('/search', methods=['GET'])
def search_endpoint():
    start = time.time()
    query = request.args.get('q')
    if not query or len(query) < 2:
        return jsonify({"status": "error", "message": "Min 2 chars"}), 400
    
    results, success, failed, total = search_in_all_files(query)
    elapsed = (time.time() - start) * 1000
    
    if not results:
        return jsonify({
            "status": "not_found",
            "query": query,
            "files_successful": success,
            "files_failed": failed,
            "total_files": total,
            "time_ms": round(elapsed, 2),
            "Developer": "Team SRA"
        }), 404
    
    return jsonify({
        "status": "success",
        "query": query,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": total,
        "time_ms": round(elapsed, 2),
        "results": results,
        "Developer": "Team SRA"
    })

@app.route('/FetchData', methods=['GET'])
def fetch_data():
    start = time.time()
    number = request.args.get('Number')
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({"status": "rejected", "message": "Invalid number"}), 400
    
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        df = get_cached_df(file_name)
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
    
    elapsed = (time.time() - start) * 1000
    if not all_results:
        return jsonify({
            "status": "not_found",
            "phone": number,
            "files_successful": success,
            "files_failed": failed,
            "total_files": len(FILE_NAMES),
            "time_ms": round(elapsed, 2),
            "Developer": "Team SRA"
        }), 404
    
    return jsonify({
        "status": "success",
        "phone": number,
        "count": len(all_results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": all_results,
        "Developer": "Team SRA"
    })

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "rejected", "message": "Invalid endpoint", "Developer": "Team SRA"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
