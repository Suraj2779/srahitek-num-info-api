from flask import Flask, request, jsonify
import os
import io
import requests
import pandas as pd
import pyarrow.parquet as pq

app = Flask(__name__)

# ---------- ল্যান্ডিং পেজ ----------
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>SRA CyberTech - Vercel</title>
    <style>body{background:#000;color:#0f0;text-align:center;padding-top:15%;font-family:monospace;} h1{color:#00ffcc;} .dev{color:#888;}</style>
    </head>
    <body>
        <h1>🚀 SRA CYBERTECH API</h1>
        <p>Status: <span style="color:#0f0;">● LIVE on Vercel</span></p>
        <p>Developer: Salman | Raj | Akash</p>
        <p class="dev">Use: /FetchData?Number=01XXXXXXXXX</p>
    </body>
    </html>
    """

# ---------- ৪০৪ এরর হ্যান্ডলার ----------
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "status": "rejected",
        "message": "Invalid endpoint. STRICTLY use /FetchData?Number=XXXXXXXXXX",
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }), 404

# ---------- মেইন API এন্ডপয়েন্ট ----------
@app.route('/FetchData', methods=['GET'])
def fetch_data():
    number = request.args.get('Number')
    
    if not number or not number.isdigit() or len(number) < 10 or len(number) > 15:
        return jsonify({
            "status": "rejected",
            "message": "Invalid parameter. Use /FetchData?Number=01XXXXXXXXX",
            "Developer": "Team SRA"
        }), 400

    last_digit = number[-1]
    
    # Hugging Face ডেটাসেটের লিংক
    primary_url = f"https://huggingface.co/datasets/CutehackX/hitek-data-bucket/resolve/main/final_master_shard_{last_digit}.parquet"
    alt_url = f"https://huggingface.co/datasets/CutehackX/hitek-data-bucket/resolve/main/alt_master_shard_{last_digit}.parquet"

    def fetch_parquet(url, column_name):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            table = pq.read_table(io.BytesIO(response.content))
            df = table.to_pandas()
            filtered = df[df[column_name] == number]
            return filtered.to_dict(orient='records')
        except Exception as e:
            return []

    main_records = fetch_parquet(primary_url, 'mobile')
    alt_records = fetch_parquet(alt_url, 'alt')

    if not main_records and not alt_records:
        return jsonify({
            "status": "not_found",
            "phone": number,
            "Developer": "Team SRA"
        }), 404

    return jsonify({
        "status": "success",
        "Data": {
            "Main_Records": main_records,
            "Alt_Records": alt_records
        },
        "Developer": "Team SRA (Salman | Raj | Akash)"
    })

# Vercel-এর জন্য app instance export করা আবশ্যক
# (উপরে already 'app = Flask(__name__)' করা আছে)
