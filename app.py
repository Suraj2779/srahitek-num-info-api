import os
import io
import time
import requests
import pandas as pd
import pyarrow.parquet as pq
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========== কনফিগারেশন ==========
BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

FILE_NAMES = []
for i in range(10):
    FILE_NAMES.append(f"alt_master_shard_{i}.parquet")
    FILE_NAMES.append(f"final_master_shard_{i}.parquet")

SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']
TIMEOUT = 300  # ৫ মিনিট (বড় ফাইলের জন্য)
MAX_RETRIES = 2  # কোনো ফাইল ডাউনলোডে ব্যর্থ হলে ২ বার রিট্রাই

# ========== হেল্পার ফাংশন (রিট্রাই সহ) ==========
def fetch_parquet_safe(file_name):
    """রিট্রাই মেকানিজম সহ Parquet ডাউনলোড"""
    url = f"{BASE_URL}/{file_name}"
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=TIMEOUT, stream=True)
            response.raise_for_status()
            
            # স্ট্রিমিং করে ডাউনলোড (মেমোরি বাঁচায়)
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            table = pq.read_table(io.BytesIO(content))
            df = table.to_pandas()
            df = df.fillna("")
            return df
            
        except Exception as e:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2)  # রিট্রাই করার আগে ২ সেকেন্ড অপেক্ষা
    
    return None

def search_in_all_files(query):
    """সব ২০টি ফাইলে সার্চ"""
    if not query or len(query) < 2:
        return [], 0, 0, 0
    
    all_results = []
    success = 0
    failed = 0
    
    for file_name in FILE_NAMES:
        df = fetch_parquet_safe(file_name)
        if df is None:
            failed += 1
            continue
        
        success += 1
        
        # সব কলামে সার্চ
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

# ========== ল্যান্ডিং পেজ ==========
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
        <p class="dev" style="color:#ff0;">Timeout: 300s | Retry: 2</p>
    </body>
    </html>
    """

# ========== সার্চ এন্ডপয়েন্ট ==========
@app.route('/search', methods=['GET'])
def search_endpoint():
    start_time = time.time()
    query = request.args.get('q')
    
    if not query or len(query) < 2:
        return jsonify({
            "status": "error",
            "message": "Missing 'q' parameter or query too short (min 2 chars)",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
    results, success, failed, total = search_in_all_files(query)
    elapsed = (time.time() - start_time) * 1000
    
    if not results:
        return jsonify({
            "status": "not_found",
            "query": query,
            "message": "No results found in any field",
            "files_successful": success,
            "files_failed": failed,
            "total_files": total,
            "time_ms": round(elapsed, 2),
            "Developer": "Team SRA (Salman | Raj | Akash)"
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
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

# ========== ফেচডাটা এন্ডপয়েন্ট ==========
@app.route('/FetchData', methods=['GET'])
def fetch_data():
    start_time = time.time()
    number = request.args.get('Number')
    
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({
            "status": "rejected",
            "message": "Invalid parameter. Use /FetchData?Number=01XXXXXXXXX",
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }), 400
    
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
    
    elapsed = (time.time() - start_time) * 1000
    
    if not all_results:
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
        "count": len(all_results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "time_ms": round(elapsed, 2),
        "results": all_results,
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

# ========== ৪০৪ এরর হ্যান্ডলার ==========
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
