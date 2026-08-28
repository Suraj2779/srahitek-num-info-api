import os
import io
import time
import requests
import pandas as pd
import pyarrow.parquet as pq
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========== কনফিগারেশন ==========
SHARDS = range(10)  # 0-9
BASE_URL = "https://huggingface.co/buckets/CutehackX/hitek-data-bucket/resolve/main"
TIMEOUT = 45  # বড় ফাইলের জন্য বেশি সময়

# যে ফাইল সেটগুলো স্ক্যান করব (alt ও final)
FILE_SETS = [
    {"prefix": "alt_master_shard", "suffix": ".parquet"},
    {"prefix": "final_master_shard", "suffix": ".parquet"},
]

# যে কলামগুলোতে সার্চ করব (শুধু টেক্সট কলাম)
SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email']

# ========== হেল্পার ফাংশন ==========
def fetch_parquet_safe(shard, prefix):
    """একটি নির্দিষ্ট শার্ড ও প্রিফিক্সের ফাইল ডাউনলোড করে DataFrame রিটার্ন করে, এরর হলে None"""
    url = f"{BASE_URL}/{prefix}_{shard}.parquet"
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        table = pq.read_table(io.BytesIO(response.content))
        df = table.to_pandas()
        # NaN গুলোকে খালি স্ট্রিং করি, JSON ব্রেক করবে না
        df = df.fillna("")
        return df
    except Exception as e:
        # কোনো এরর (404, টাইমআউট, করাপ্ট) হলে None
        return None

def search_in_all_files(query):
    """সব শার্ড ও সব ফাইল সেটে query খোঁজে (সব টেক্সট কলামে)"""
    if not query or len(query) < 2:
        return [], 0, 0, 0
    
    all_results = []
    total_files = 0
    successful_files = 0
    failed_files = 0
    
    for shard in SHARDS:
        for file_set in FILE_SETS:
            prefix = file_set["prefix"]
            total_files += 1
            df = fetch_parquet_safe(shard, prefix)
            if df is None:
                failed_files += 1
                continue
            
            successful_files += 1
            
            # সব টেক্সট কলামে সার্চ (কেস ইনসেনসিটিভ)
            mask = pd.Series([False] * len(df))
            for col in SEARCH_COLUMNS:
                if col in df.columns:
                    mask = mask | df[col].astype(str).str.contains(query, case=False, na=False)
            
            filtered_df = df[mask]
            if not filtered_df.empty:
                records = filtered_df.to_dict(orient='records')
                for rec in records:
                    rec['_shard'] = shard
                    rec['_source'] = f"{prefix}_{shard}.parquet"
                all_results.extend(records)
    
    return all_results, successful_files, failed_files, total_files

# ========== হোম পেজ ==========
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>SRA CyberTech - ULTIMATE</title>
    <style>body{background:#000;color:#0f0;text-align:center;padding-top:15%;font-family:monospace;} h1{color:#00ffcc;} .dev{color:#888;}</style>
    </head>
    <body>
        <h1>🚀 SRA CYBERTECH ULTIMATE API</h1>
        <p>Status: <span style="color:#0f0;">● LIVE</span></p>
        <p>Developer: Salman | Raj | Akash</p>
        <p class="dev">Use: /search?q=Gautam</p>
        <p class="dev">Use: /FetchData?Number=9831477801</p>
        <p class="dev">Scans all 20 Parquet files (alt + final)</p>
    </body>
    </html>
    """

# ========== সার্চ এন্ডপয়েন্ট (সব ফিল্ড) ==========
@app.route('/search', methods=['GET'])
def search_endpoint():
    query = request.args.get('q')
    
    if not query or len(query) < 2:
        return jsonify({
            "status": "error",
            "message": "Missing 'q' parameter or query too short (min 2 chars)",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
    start_time = time.time()
    results, success, failed, total = search_in_all_files(query)
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    if not results:
        return jsonify({
            "status": "not_found",
            "query": query,
            "message": "No results found in any field",
            "files_successful": success,
            "files_failed": failed,
            "total_files": total,
            "time_ms": elapsed_ms,
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 404
    
    return jsonify({
        "status": "success",
        "query": query,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": total,
        "time_ms": elapsed_ms,
        "results": results,
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

# ========== ফেচডাটা (শুধু মোবাইল/অল্ট) ==========
@app.route('/FetchData', methods=['GET'])
def fetch_data():
    number = request.args.get('Number')
    
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({
            "status": "rejected",
            "message": "Invalid parameter. Use /FetchData?Number=01XXXXXXXXX",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
    start_time = time.time()
    all_results = []
    success_files = 0
    failed_files = 0
    total_files = 0
    
    for shard in SHARDS:
        for file_set in FILE_SETS:
            prefix = file_set["prefix"]
            total_files += 1
            df = fetch_parquet_safe(shard, prefix)
            if df is None:
                failed_files += 1
                continue
            
            success_files += 1
            
            # শুধু mobile ও alt কলাম চেক
            mask = pd.Series([False] * len(df))
            if 'mobile' in df.columns:
                mask = mask | df['mobile'].astype(str).str.contains(number, case=False, na=False)
            if 'alt' in df.columns:
                mask = mask | df['alt'].astype(str).str.contains(number, case=False, na=False)
            
            filtered_df = df[mask]
            if not filtered_df.empty:
                records = filtered_df.to_dict(orient='records')
                for rec in records:
                    rec['_shard'] = shard
                    rec['_source'] = f"{prefix}_{shard}.parquet"
                all_results.extend(records)
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    if not all_results:
        return jsonify({
            "status": "not_found",
            "phone": number,
            "files_successful": success_files,
            "files_failed": failed_files,
            "total_files": total_files,
            "time_ms": elapsed_ms,
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 404
    
    return jsonify({
        "status": "success",
        "phone": number,
        "count": len(all_results),
        "files_successful": success_files,
        "files_failed": failed_files,
        "total_files": total_files,
        "time_ms": elapsed_ms,
        "results": all_results,
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

# ========== ৪০৪ হ্যান্ডলার ==========
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "status": "rejected",
        "message": "Invalid endpoint. Use /search?q=... or /FetchData?Number=...",
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }), 404

# ========== সার্ভার চালানো ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
