from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import duckdb
import math

app = FastAPI(docs_url=None, redoc_url=None)

# DuckDB কানেক্ট
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

# ডেটার বেস URL
base = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
# ০ থেকে ৯ পর্যন্ত ১০টা শার্ড ফাইল
shard_indices = list(range(10))

@app.get("/")
def root():
    return {
        "status": "SRA API is running",
        "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
        "channel": "https://t.me/SRACyberTechPvtLtd"
    }

# ইউনিভার্সাল সার্চ ইঞ্জিন: Number, ID, অথবা Alt, যেকোনো একটা দিলেই কাজ করবে
@app.get("/FetchData")
def fetch_data(Number: str = Query(None), ID: str = Query(None), Alt: str = Query(None)):
    # যেটা দেওয়া আছে সেটাকে টার্গেট ভ্যালু বানানো
    target_value = Number if Number else (ID if ID else Alt)
    
    if not target_value:
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid input. Pass Number, ID, or Alt.",
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
            }
        )

    # যেহেতু ID তে "Cqj2509776" এর মতো অক্ষর থাকতে পারে, তাই আমরা ডিজিট চেক সরিয়ে দিচ্ছি
    # আমরা শুধু নিশ্চিত করছি ভ্যালুটা খালি না।
    if not target_value.strip():
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid input. Value cannot be empty.",
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
            }
        )

    main_records = []
    alt_records = []

    try:
        for i in shard_indices:
            primary_url = f"{base}/final_master_shard_{i}.parquet"
            alt_url = f"{base}/alt_master_shard_{i}.parquet"

            # Main শার্ডে তিনটা কলামেই (mobile, id, alt) খোঁজা হচ্ছে
            query_main = f"""
                SELECT *, 'Main' AS _record_type 
                FROM read_parquet('{primary_url}') 
                WHERE mobile = '{target_value}' OR id = '{target_value}' OR alt = '{target_value}'
            """
            df_main = con.execute(query_main).df()
            
            if not df_main.empty:
                raw = df_main.to_dict(orient="records")
                cleaned = clean_nan(raw)
                for row in cleaned:
                    row.pop('_record_type', None)
                    main_records.append(row)

            # Alt শার্ডে তিনটা কলামেই খোঁজা হচ্ছে
            query_alt = f"""
                SELECT *, 'Alt' AS _record_type 
                FROM read_parquet('{alt_url}') 
                WHERE mobile = '{target_value}' OR id = '{target_value}' OR alt = '{target_value}'
            """
            df_alt = con.execute(query_alt).df()
            
            if not df_alt.empty:
                raw = df_alt.to_dict(orient="records")
                cleaned = clean_nan(raw)
                for row in cleaned:
                    row.pop('_record_type', None)
                    alt_records.append(row)

            # যদি কোনো শার্ডে রেজাল্ট পাওয়া যায়, তাহলে লুপ বন্ধ করা হচ্ছে
            if main_records or alt_records:
                break
        
        if not main_records and not alt_records:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "query": target_value,
                    "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
                }
            )

        return {
            "status": "success",
            "Total_Main_Results": len(main_records),
            "Total_Alt_Results": len(alt_records),
            "Data": {
                "Main_Records": main_records,
                "Alt_Records": alt_records
            },
            "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
            "Channel": "https://t.me/SRACyberTechPvtLtd"
        }

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
            }
        )

@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "rejected",
            "message": "Invalid endpoint. Use /FetchData?Number=... or /FetchData?ID=... or /FetchData?Alt=...",
            "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
        }
    )
