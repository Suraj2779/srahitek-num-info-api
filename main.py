import os
import duckdb
from fastapi import FastAPI, HTTPException, Query
from huggingface_hub import login
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="SRA CyberTech Database Search API")

# =====================================================================
# CONFIGURATION
# =====================================================================
DEVELOPER_NAME = "@SRA_CyberTech_Pvt_Ltd_Owner_bot"
CHANNEL_URL = "https://t.me/SRACyberTechPvtLtd"
DATASET_BASE_URL = "hf://datasets/MRSHREY197/Hitekdatabase"

# Hugging Face Access Token Setup
HF_TOKEN = os.getenv("HF_TOKEN")
if HF_TOKEN:
    login(token=HF_TOKEN)

# =====================================================================
# DYNAMIC API KEY SYSTEM
# =====================================================================
TODAY = datetime.now()
TODAY_STR = TODAY.strftime("%Y-%m-%d")

def get_expiry(days):
    return (TODAY + timedelta(days=days)).strftime("%Y-%m-%d")

API_KEYS = {
    "SRA_DEMO_3DAYS": {
        "key": "SRA_DEMO_3DAYS",
        "plan": "Demo (3 Days)",
        "days": 3,
        "daily_limit": 50,
        "created": TODAY_STR,
        "expiry": get_expiry(3),
        "used_today": 0,
        "last_reset": TODAY_STR
    },
    "SRA_MONTHLY_001": {
        "key": "SRA_MONTHLY_001",
        "plan": "1 Month",
        "days": 30,
        "daily_limit": 1000,
        "created": TODAY_STR,
        "expiry": get_expiry(30),
        "used_today": 0,
        "last_reset": TODAY_STR
    },
    "SRA_2MONTH_001": {
        "key": "SRA_2MONTH_001",
        "plan": "2 Months",
        "days": 60,
        "daily_limit": 2000,
        "created": TODAY_STR,
        "expiry": get_expiry(60),
        "used_today": 0,
        "last_reset": TODAY_STR
    },
    "SRA_3MONTH_001": {
        "key": "SRA_3MONTH_001",
        "plan": "3 Months",
        "days": 90,
        "daily_limit": 3000,
        "created": TODAY_STR,
        "expiry": get_expiry(90),
        "used_today": 0,
        "last_reset": TODAY_STR
    },
    "SRA_MASTER_001": {
        "key": "SRA_MASTER_001",
        "plan": "Master (1 Year)",
        "days": 365,
        "daily_limit": 10000,
        "created": TODAY_STR,
        "expiry": get_expiry(365),
        "used_today": 0,
        "last_reset": TODAY_STR
    }
}

def validate_api_key(api_key: str):
    if api_key not in API_KEYS:
        return None, "❌ Invalid API Key!"
    
    key_data = API_KEYS[api_key]
    expiry_date = datetime.strptime(key_data["expiry"], "%Y-%m-%d")
    
    if datetime.now() > expiry_date:
        return None, "❌ API Key Expired!"
    
    current_today = datetime.now().strftime("%Y-%m-%d")
    if key_data["last_reset"] != current_today:
        key_data["used_today"] = 0
        key_data["last_reset"] = current_today
    
    if key_data["used_today"] >= key_data["daily_limit"]:
        return None, f"❌ Daily Limit Reached! ({key_data['used_today']}/{key_data['daily_limit']} used)"
    
    return key_data, None

def get_key_info(api_key: str):
    if api_key not in API_KEYS:
        return None
    
    key_data = API_KEYS[api_key]
    expiry_date = datetime.strptime(key_data["expiry"], "%Y-%m-%d")
    days_left = (expiry_date - datetime.now()).days
    
    return {
        "plan": key_data["plan"],
        "expiry": key_data["expiry"],
        "days_left": max(days_left, 0),
        "daily_limit": key_data["daily_limit"],
        "used_today": key_data["used_today"],
        "remaining_today": key_data["daily_limit"] - key_data["used_today"],
        "status": "Active" if days_left >= 0 else "Expired"
    }

# =====================================================================
# API ENDPOINTS
# =====================================================================

@app.get("/")
def home():
    return {
        "status": "SRA CyberTech Search API Active",
        "developer": DEVELOPER_NAME,
        "channel": CHANNEL_URL,
        "available_plans": {
            "Demo (3 Days)": {"key": "SRA_DEMO_3DAYS", "daily_limit": 50},
            "1 Month": {"key": "SRA_MONTHLY_001", "daily_limit": 1000},
            "2 Months": {"key": "SRA_2MONTH_001", "daily_limit": 2000},
            "3 Months": {"key": "SRA_3MONTH_001", "daily_limit": 3000},
            "Master (1 Year)": {"key": "SRA_MASTER_001", "daily_limit": 10000}
        }
    }

@app.get("/keyinfo/{api_key}")
def key_info_endpoint(api_key: str):
    info = get_key_info(api_key)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid API Key")
    return {
        "status": "success",
        "key_info": info,
        "developer": DEVELOPER_NAME,
        "channel": CHANNEL_URL
    }

@app.get("/search")
def search_records(
    api_key: str = Query(..., description="Your API Key"),
    shard_name: str = Query(..., description="Parquet file name (e.g., alt_master_shard_0.parquet)"),
    name: Optional[str] = Query(None, description="Search by Name"),
    fname: Optional[str] = Query(None, description="Search by Father Name"),
    id: Optional[str] = Query(None, description="Search by ID"),
    alt: Optional[str] = Query(None, description="Search by Alternate Number"),
    email: Optional[str] = Query(None, description="Search by Email"),
    mobile: Optional[str] = Query(None, description="Search by Mobile Number"),
    address: Optional[str] = Query(None, description="Search by Address"),
    limit: int = Query(50, description="Max records to return")
):
    # Key validation
    key_data, error = validate_api_key(api_key)
    if not key_data:
        raise HTTPException(status_code=403, detail=error)
    
    # Query building for Hugging Face Parquet dataset via DuckDB
    try:
        parquet_url = f"{DATASET_BASE_URL}/{shard_name}"
        conn = duckdb.connect()
        
        conditions = []        
        if name:
            conditions.append(f"LOWER(name) LIKE LOWER('%{name}%')")
        if fname:
            conditions.append(f"LOWER(fname) LIKE LOWER('%{fname}%')")
        if id:
            conditions.append(f"CAST(id AS VARCHAR) LIKE '%{id}%'")
        if alt:
            conditions.append(f"CAST(alt AS VARCHAR) LIKE '%{alt}%'")
        if email:
            conditions.append(f"LOWER(email) LIKE LOWER('%{email}%')")
        if mobile:
            conditions.append(f"CAST(mobile AS VARCHAR) LIKE '%{mobile}%'")
        if address:
            conditions.append(f"LOWER(address) LIKE LOWER('%{address}%')")
            
        if not conditions:
            raise HTTPException(status_code=400, detail="At least one search filter (name, fname, mobile, address, etc.) must be provided.")
        
        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM '{parquet_url}' WHERE {where_clause} LIMIT {limit}"
        
        df = conn.execute(query).df()
        df = df.fillna("")
        
        # Deduct usage count on success
        key_data["used_today"] += 1
        
        return {
            "status": "success",
            "developer": DEVELOPER_NAME,
            "channel": CHANNEL_URL,
            "key_info": get_key_info(api_key),
            "count": len(df),
            "results": df.to_dict(orient="records")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
