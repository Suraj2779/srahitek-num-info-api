from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import duckdb
import math

app = FastAPI(docs_url=None, redoc_url=None)

con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj

base = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

@app.get("/")
def root():
    return {"status": "SRA API is running", "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "channel": "https://t.me/SRACyberTechPvtLtd"}

@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number or not Number.isdigit() or len(Number) < 10 or len(Number) > 15:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid number. Use 10-15 digits.", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

    last_digit = Number[-1]
    primary_url = f"{base}/final_master_shard_{last_digit}.parquet"

    try:
        query = f"SELECT * FROM read_parquet('{primary_url}') WHERE mobile = '{Number}' LIMIT 1"
        df = con.execute(query).df()
        if df.empty:
            return JSONResponse(status_code=404, content={"status": "not_found", "phone": Number, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
        cleaned = clean_nan(df.to_dict(orient="records"))
        return {"status": "success", "Total_Results": len(cleaned), "Data": cleaned, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "Channel": "https://t.me/SRACyberTechPvtLtd"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e), "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

@app.get("/FetchID")
def fetch_id(ID: str = Query(None)):
    if not ID or len(ID) < 5:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID. Minimum length is 5.", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

    main_records = []

    try:
        # 0-9 পর্যন্ত ১০টা Main শার্ড চেক করা হবে (Alt বাদ, তাই ফাস্ট)
        for i in range(10):
            primary_url = f"{base}/final_master_shard_{i}.parquet"

            # `id` কলামটি টেক্সট, তাই সিঙ্গেল কোটেশন ('{ID}') ব্যবহার করো
            query = f"SELECT * FROM read_parquet('{primary_url}') WHERE id = '{ID}' LIMIT 1"
            df = con.execute(query).df()

            if not df.empty:
                raw = df.to_dict(orient="records")
                cleaned = clean_nan(raw)
                main_records.extend(cleaned)
                break

        if not main_records:
            return JSONResponse(status_code=404, content={"status": "not_found", "id": ID, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

        return {"status": "success", "Total_Results": len(main_records), "Data": main_records, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "Channel": "https://t.me/SRACyberTechPvtLtd"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e), "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "rejected", "message": "Invalid endpoint. Use /FetchData?Number=... or /FetchID?ID=...", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
