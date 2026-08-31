import requests
import duckdb
import math
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(docs_url=None, redoc_url=None)

# DuckDB কানেক্ট ও HTTPFS চালু
con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# ✅ ডাইনামিক শার্ড লোডার: Hugging Face থেকে নিজে শার্ডের লিংক বের করবে
def get_shard_urls():
    try:
        url = "https://datasets-server.huggingface.co/parquet?dataset=MRSHREY197/Telegram-Database"
        response = requests.get(url)
        data = response.json()
        return [file['url'] for file in data.get('parquet_files', [])]
    except:
        return []

# ডেটা লোড করার সময় একবার শার্ড লিস্ট বের করা হচ্ছে
shard_urls = get_shard_urls()

@app.get("/ping")
def ping():
    return {"message": "New MRSHREY Database API is running", "version": "v3.0"}

@app.get("/")
def root():
    return {"status": "MRSHREY DB API is running", "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "total_shards": len(shard_urls)}

# ✅ শুধুমাত্র ID (account_id / user_id) দিয়ে সার্চ করার Endpoint
@app.get("/FetchID")
def fetch_id(request: Request):
    # Query string থেকে প্যারামিটার খোঁজা হচ্ছে
    target_id = request.query_params.get('account_id') or request.query_params.get('user_id')
    
    if not target_id or not target_id.isdigit():
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID. Only digits allowed."})

    if not shard_urls:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Shards not found. Check dataset name."})

    # RAM বাঁচাতে ১০টা করে শার্ড গ্রুপ করে সার্চ
    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"

        try:
            # account_id স্ট্রিং, তাই কোটেশন ('{target_id}') লাগবে
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE account_id = '{target_id}' LIMIT 1"
            df = con.execute(query).df()

            if not df.empty:
                data = df.to_dict('records')[0]
                # NaN (খালি ভ্যালু) ক্লিন করা
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            # কোনো শার্ডে সমস্যা হলে পরের গ্রুপে চলে যাও
            continue

    return JSONResponse(status_code=404, content={"status": "not_found", "id": target_id})

# ✅ ফোন নম্বর দিয়ে সার্চ করার Endpoint (অপশনাল)
@app.get("/FetchData")
def fetch_data(request: Request):
    number = request.query_params.get('Number')
    if not number or not number.isdigit():
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid Number."})

    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"

        try:
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE phone = '{number}' LIMIT 1"
            df = con.execute(query).df()
            if not df.empty:
                data = df.to_dict('records')[0]
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            continue

    return JSONResponse(status_code=404, content={"status": "not_found", "phone": number})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "rejected", "message": "Invalid endpoint. Use /FetchID?account_id=... or /FetchData?Number=...", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}
    )
