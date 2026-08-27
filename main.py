import os
import duckdb
from fastapi import FastAPI, HTTPException, Query
from huggingface_hub import login
from typing import Optional

app = FastAPI(title="Hitek Database Search API")

# Setup Hugging Face Access Token
HF_TOKEN = os.getenv("HF_TOKEN")
if HF_TOKEN:
    login(token=HF_TOKEN)

# Remote Dataset path reference
DATASET_BASE_URL = "hf://datasets/MRSHREY197/Hitekdatabase"

@app.get("/search")
def search_records(
    shard_name: str = Query(..., description="Target Parquet file name, e.g., alt_master_shard_0.parquet"),
    name: Optional[str] = Query(None, description="Search by Name"),
    fname: Optional[str] = Query(None, description="Search by Father Name"),
    id: Optional[str] = Query(None, description="Search by ID / Aadhaar / Reg No"),
    alt: Optional[str] = Query(None, description="Search by Alternate Number"),
    email: Optional[str] = Query(None, description="Search by Email"),
    mobile: Optional[str] = Query(None, description="Search by Mobile Number"),
    address: Optional[str] = Query(None, description="Search by Address / Location"),
    limit: int = Query(50, description="Max records to return")
):
    """
    Search records using multiple parameters dynamically across remote Parquet files.
    Now supports searching by address as well.
    """
    try:
        parquet_url = f"{DATASET_BASE_URL}/{shard_name}"
        conn = duckdb.connect()
        
        # Build dynamic SQL WHERE clause
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
            raise HTTPException(status_code=400, detail="At least one search parameter must be provided.")
        
        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM '{parquet_url}' WHERE {where_clause} LIMIT {limit}"
        
        df = conn.execute(query).df()
        
        # Replace NaN/null values for valid JSON response
        df = df.fillna("")
        
        return {
            "count": len(df),
            "results": df.to_dict(orient="records")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def health_check():
    return {"status": "Search API is online", "dataset": "MRSHREY197/Hitekdatabase"}
