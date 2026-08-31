import duckdb
import math
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(docs_url=None, redoc_url=None)

# DuckDB কানেক্ট ও HTTPFS চালু (রিমোট Parquet পড়ার জন্য)
con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# ProPortalx ডেটাসেটের ৯৬টা শার্ডের লিংক
base = "https://huggingface.co/datasets/ProPortalx/Telegram-Database/resolve/refs%2Fconvert%2Fparquet/default/train/"
shard_urls = [f"{base}{i:04d}.parquet" for i in range(96)]

@app.get("/")
def root():
    return {"status": "ProPortalx TG API is running", "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}

# ✅ শুধুমাত্র account_id দিয়ে সার্চ করার Endpoint
@app.get("/FetchID")
def fetch_id(account_id: str = Query(None)):
    if not account_id or not account_id.isdigit():
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID. Only digits allowed."})

    # ৯৬টা শার্ডকে ১০টা করে গ্রুপে ভাগ করা হয়েছে (টাইমআউট ও RAM বাঁচাতে)
    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        # DuckDB-কে URL লিস্ট দেওয়ার ফরম্যাট
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"

        try:
            # account_id স্ট্রিং, তাই কোয়েরিতে সিঙ্গেল কোটেশন ('{account_id}') লাগবে
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE account_id = '{account_id}' LIMIT 1"
            df = con.execute(query).df()

            if not df.empty:
                data = df.to_dict('records')[0]
                # NaN (খালি ভ্যালু) গুলোকে null বানানো
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            # কোনো শার্ডে সাময়িক সমস্যা হলে, পরের গ্রুপে চলে যাও
            continue

    return JSONResponse(status_code=404, content={"status": "not_found", "id": account_id})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "rejected", "message": "Invalid endpoint. Use /FetchID?account_id=...", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}
    )
