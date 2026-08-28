from flask import Flask, request, jsonify
import os
import io
import requests
import pandas as pd
import pyarrow.parquet as pq

app = Flask(__name__)

# ========== কনফিগারেশন ==========
BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
FILE_NAMES = []
for i in range(10):
    FILE_NAMES.append(f"alt_master_shard_{i}.parquet")
    FILE_NAMES.append(f"final_master_shard_{i}.parquet")

SEARCH_COLUMNS = ['mobile', 'name', 'fname', 'address', 'alt', 'circle', 'email', 'id']

# ========== হেল্পার ফাংশন ==========
def fetch_parquet_safe(file_name):
    url = f"{BASE_URL}/{file_name}"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        table = pq.read_table(io.BytesIO(response.content))
        df = table.to_pandas()
        df = df.fillna("")
        return df
    except Exception:
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
        "status": "SRA CyberTech API is LIVE",
        "developer": "Team SRA (Salman | Raj | Akash)",
        "files": len(FILE_NAMES),
        "endpoints": {
            "/search?q=...": "Search in all fields",
            "/FetchData?Number=...": "Search by mobile or alt number"
        }
    })

@app.route('/search')
def search():
    query = request.args.get('q')
    if not query or len(query) < 2:
        return jsonify({"status": "error", "message": "q parameter required (min 2 chars)"}), 400
    
    results, success, failed = search_in_all_files(query)
    
    if not results:
        return jsonify({
            "status": "not_found",
            "query": query,
            "files_successful": success,
            "files_failed": failed,
            "total_files": len(FILE_NAMES),
            "Developer": "Team SRA"
        }), 404
    
    return jsonify({
        "status": "success",
        "query": query,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "results": results,
        "Developer": "Team SRA"
    })

@app.route('/FetchData')
def fetch_data():
    number = request.args.get('Number')
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({
            "status": "rejected",
            "message": "Invalid number. Use /FetchData?Number=01XXXXXXXXX",
            "Developer": "Team SRA"
        }), 400
    
    results, success, failed = search_number_in_all_files(number)
    
    if not results:
        return jsonify({
            "status": "not_found",
            "phone": number,
            "files_successful": success,
            "files_failed": failed,
            "total_files": len(FILE_NAMES),
            "Developer": "Team SRA"
        }), 404
    
    return jsonify({
        "status": "success",
        "phone": number,
        "count": len(results),
        "files_successful": success,
        "files_failed": failed,
        "total_files": len(FILE_NAMES),
        "results": results,
        "Developer": "Team SRA"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
