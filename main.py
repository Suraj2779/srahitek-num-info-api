from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import duckdb
import math
import os

app = FastAPI(docs_url=None, redoc_url=None)

# 🚀 VERCEL FIXES
# 1. DuckDB को home directory बताएँ (Vercel में HOME missing है)
os.environ['DUCKDB_HOME'] = '/tmp'

# 2. Extension install करने के लिए writable folder
EXTENSION_DIR = "/tmp/duckdb_ext"
os.makedirs(EXTENSION_DIR, exist_ok=True)
duckdb.default_extension_directory = EXTENSION_DIR

# अब DuckDB connect करें और httpfs load करें
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
        "status": "SRA API is running",
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
                "message": "Invalid number. Use 10-15 digits.",
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
        df = con.execute(query).df()
        if df.empty:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "phone": Number,
                    "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
                }
            )
        
        raw = df.to_dict(orient="records")
        cleaned = clean_nan(raw)
        
        main_records = []
        alt_records = []
        for row in cleaned:
            rec_type = row.get('_record_type')
            if rec_type == 'Main':
                row.pop('_record_type', None)
                main_records.append(row)
            elif rec_type == 'Alt':
                row.pop('_record_type', None)
                alt_records.append(row)
            else:
                row.pop('_record_type', None)
                alt_records.append(row)
        
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
            "message": "Invalid endpoint. Use /FetchData?Number=...",
            "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
        }
    )
