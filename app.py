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

# ========== কনফিগারেশন ==========
# আপনার ডেটাসেটের সঠিক URL
BASE_URL = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"

# ========== হেল্পার ফাংশন ==========
def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj

# ========== এন্ডপয়েন্ট ==========
@app.get("/")
def root():
    return {
        "status": "SRA API is running",
        "message": "Phone number info API",
        "Developer": "Team SRA (Salman | Raj | Akash)"
    }

@app.get("/FetchData")
def fetch_data(Number: str = Query(None)):
    if not Number or not Number.isdigit() or len(Number) < 10 or len(Number) > 15:
        return JSONResponse(
            status_code=400,
            content={
                "status": "rejected",
                "message": "Invalid parameter. Use /FetchData?Number=01XXXXXXXXX",
                "Developer": "Team SRA (Salman | Raj | Akash)"
            }
        )
    
    last_digit = Number[-1]
    
    # শুধু শেষ ডিজিটের শার্ডে সার্চ (বন্ধুর মতো)
    primary_url = f"{BASE_URL}/final_master_shard_{last_digit}.parquet"
    alt_url = f"{BASE_URL}/alt_master_shard_{last_digit}.parquet"
    
    try:
        query = f"""
            SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') WHERE mobile = '{Number}'
            UNION ALL
            SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') WHERE alt = '{Number}'
        """
        raw_results = con.execute(query).df().to_dict(orient="records")
        
        # NaN ক্লিনিং
        cleaned_results = clean_nan(raw_results)
        
        main_records = []
        alt_records = []
        
        for row in cleaned_results:
            rec_type = row.pop('_record_type', None)
            if rec_type == 'Main':
                main_records.append(row)
            elif rec_type == 'Alt':
                alt_records.append(row)
        
        if not main_records and not alt_records:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "phone": Number,
                    "Developer": "Team SRA (Salman | Raj | Akash)"
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
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Database processing error: {str(e)}",
                "Developer": "Team SRA (Salman | Raj | Akash)"
            }
        )

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "rejected",
            "message": exc.detail,
            "Developer": "Team SRA (Salman | Raj | Akash)"
        }
    )
