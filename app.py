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

# ProPortalx ডেটাসেটের ৯৬টা শার্ড
base = "https://huggingface.co/datasets/ProPortalx/Telegram-Database/resolve/refs%2Fconvert%2Fparquet/default/train/"
shard_urls = [f"{base}{i:04d}.parquet" for i in range(96)]

@app.get("/")
def root():
    return {"status": "ProPortalx TG API is running", "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}

# Request থেকে ডিরেক্টলি ভ্যালু নেবে, তাই user_id/account_id দুটোই কাজ করবে
@app.get("/FetchID")
def fetch_id(request: Request):
    target_id = request.query_params.get('account_id') or request.query_params.get('user_id')

    if not target_id or not target_id.isdigit():
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID. Only digits allowed."})

    # ১০টা করে গ্রুপে সার্চ
    for i in range(0, len(shard_urls), 10):
        chunk = shard_urls[i:i+10]
        url_list_str = "[" + ",".join(f"'{url}'" for url in chunk) + "]"

        try:
            # ফোন ও অ্যাকাউন্ট আইডি স্ট্রিং, তাই কোটেশন লাগবে
            query = f"SELECT * FROM read_parquet({url_list_str}) WHERE account_id = '{target_id}' LIMIT 1"
            df = con.execute(query).df()

            if not df.empty:
                data = df.to_dict('records')[0]
                for k, v in data.items():
                    if isinstance(v, float) and math.isnan(v):
                        data[k] = None
                return JSONResponse(content={"status": "success", "data": data})
        except Exception:
            continue

    return JSONResponse(status_code=404, content={"status": "not_found", "id": target_id})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "rejected", "message": "Invalid endpoint. Use /FetchID?account_id=...", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}
    )
