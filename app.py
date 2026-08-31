import duckdb
import math
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(docs_url=None, redoc_url=None)

# DuckDB কানেক্ট ও HTTPFS চালু
con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# ProPortalx ডেটাসেটের ৯৬টা ছোট শার্ডের URL লিস্ট
base = "https://huggingface.co/datasets/ProPortalx/Telegram-Database/resolve/refs%2Fconvert%2Fparquet/default/train/"
shard_urls = [f"{base}{i:04d}.parquet" for i in range(96)]

@app.get("/")
def root():
    return {
        "status": "TG Data API is running",
        "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
    }

# Telegram ID দিয়ে সার্চ
@app.get("/FetchID")
def fetch_id(user_id: str = Query(None)):
    if not user_id or not user_id.isdigit():
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID."})

    # রেন্ডারের টাইমআউট এড়াতে ১০টা করে ফাইল গ্রুপ করে চেক করা হচ্ছে
    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        # ডাকব-কে লিস্ট আকারে URL দেওয়া
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"

        try:
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE user_id = {user_id} LIMIT 1"
            df = con.execute(query).df()

            if not df.empty:
                data = df.to_dict('records')[0]
                # NaN (খালি) ভ্যালু ক্লিন করা
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            # কোনো শার্ডে সমস্যা হলে পরের গ্রুপে চলে যাই
            continue

    return JSONResponse(status_code=404, content={"status": "not_found", "id": user_id})

# ফোন নম্বর দিয়ে সার্চ (ইন্ডিয়ান নম্বরও এখানে পাবে)
@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number or not Number.isdigit() or len(Number) < 10:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid number."})
    
    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"
        try:
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE phone = '{Number}' LIMIT 1"
            df = con.execute(query).df()
            if not df.empty:
                data = df.to_dict('records')[0]
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            continue
    
    return JSONResponse(status_code=404, content={"status": "not_found", "phone": Number})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "rejected", "message": "Invalid endpoint. Use /FetchID?user_id=... or /FetchData?Number=..."}
    )
