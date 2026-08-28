from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import duckdb
import math
import os

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

@app.get("/")
def root():
    return {
        "status": "SRA API is running 🚀",
        "developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
        "channel": "https://t.me/SRACyberTechPvtLtd"
    }

@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number or not Number.isdigit() or len(Number) < 10 or len(Number) > 15:
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid number. Use /FetchData?Number=01XXXXXXXXX",
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
            }
        )
    
    last_digit = Number[-1]
    base = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
    primary_url = f"{base}/final_master_shard_{last_digit}.parquet"
    alt_url = f"{base}/alt_master_shard_{last_digit}.parquet"
    
    try:
        query = f"""
            SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') WHERE mobile = '{Number}'
            UNION ALL
            SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') WHERE alt = '{Number}'
        """
        raw_results = con.execute(query).df().to_dict(orient="records")
        cleaned = clean_nan(raw_results)
        
        main_records = [r for r in cleaned if r.pop('_record_type') == 'Main']
        alt_records = [r for r in cleaned if r.pop('_record_type') == 'Alt']
        
        if not main_records and not alt_records:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "phone": Number,
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
            "message": exc.detail,
            "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
