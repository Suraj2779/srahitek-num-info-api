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

# ফোন নাম্বার (mobile + alt) দিয়ে সার্চ
@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number or not Number.isdigit() or len(Number) < 10 or len(Number) > 15:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid number. Use 10-15 digits.", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

    last_digit = Number[-1]
    primary_url = f"{base}/final_master_shard_{last_digit}.parquet"
    alt_url = f"{base}/alt_master_shard_{last_digit}.parquet"

    try:
        # Main + Alt দুই জায়গাতেই খোঁজা হচ্ছে
        query = f"""
            SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') WHERE mobile = '{Number}'
            UNION ALL
            SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') WHERE alt = '{Number}'
        """
        df = con.execute(query).df()
        if df.empty:
            return JSONResponse(status_code=404, content={"status": "not_found", "phone": Number, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
        
        raw = df.to_dict(orient="records")
        cleaned = clean_nan(raw)
        
        main_records = []
        alt_records = []
        for row in cleaned:
            rec_type = row.get('_record_type')
            row.pop('_record_type', None)
            if rec_type == 'Main':
                main_records.append(row)
            else:
                alt_records.append(row)

        return {"status": "success", "Total_Main_Results": len(main_records), "Total_Alt_Results": len(alt_records), "Data": {"Main_Records": main_records, "Alt_Records": alt_records}, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "Channel": "https://t.me/SRACyberTechPvtLtd"}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e), "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

# ID (id) দিয়ে সার্চ - এটা আলফানিউমেরিক সহ যেকোনো ID খুঁজবে
@app.get("/FetchID")
def fetch_id(ID: str = Query(None)):
    if not ID or len(ID) < 5:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid ID. Minimum length is 5.", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

    main_records = []
    alt_records = []

    try:
        # 0-9 পর্যন্ত ১০টা শার্ড চেক করা হবে (Main + Alt)
        for i in range(10):
            primary_url = f"{base}/final_master_shard_{i}.parquet"
            alt_url = f"{base}/alt_master_shard_{i}.parquet"

            # Main ফাইলে খোঁজা (আলফানিউমেরিক আইডির জন্য সিঙ্গেল কোটেশন ব্যবহার)
            query_main = f"SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') WHERE id = '{ID}' LIMIT 1"
            df_main = con.execute(query_main).df()
            if not df_main.empty:
                raw = df_main.to_dict(orient="records")
                cleaned = clean_nan(raw)
                for row in cleaned:
                    row.pop('_record_type', None)
                    main_records.append(row)

            # Alt ফাইলে খোঁজা
            query_alt = f"SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') WHERE id = '{ID}' LIMIT 1"
            df_alt = con.execute(query_alt).df()
            if not df_alt.empty:
                raw = df_alt.to_dict(orient="records")
                cleaned = clean_nan(raw)
                for row in cleaned:
                    row.pop('_record_type', None)
                    alt_records.append(row)

            # দুই জায়গাতেই পাওয়া গেলে লুপ বন্ধ
            if main_records or alt_records:
                break

        if not main_records and not alt_records:
            return JSONResponse(status_code=404, content={"status": "not_found", "id": ID, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

        return {"status": "success", "Total_Main_Results": len(main_records), "Total_Alt_Results": len(alt_records), "Data": {"Main_Records": main_records, "Alt_Records": alt_records}, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot", "Channel": "https://t.me/SRACyberTechPvtLtd"}

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e), "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "rejected", "message": "Invalid endpoint. Use /FetchData?Number=... or /FetchID?ID=...", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
