from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
import duckdb
import os
import time
from typing import Optional

app = FastAPI(title="SRA CyberTech Search API")

DATASET_BASE = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
ALL_SHARDS = [f"alt_master_shard_{i}.parquet" for i in range(10)] + [f"final_master_shard_{i}.parquet" for i in range(10)]

@app.get("/search")
def search(
    mobile: Optional[str] = Query(None, regex="^[0-9]{10,15}$"),
    alt: Optional[str] = Query(None, regex="^[0-9]{10,15}$"),
    name: Optional[str] = Query(None, min_length=2, max_length=50),
    fname: Optional[str] = Query(None, min_length=2, max_length=50),
    id: Optional[str] = Query(None, max_length=20),
    email: Optional[str] = Query(None, max_length=50),
    address: Optional[str] = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100)
):
    start = time.time()
    conditions = []
    if mobile:
        conditions.append(f"mobile = '{mobile}'")
    if alt:
        conditions.append(f"alt = '{alt}'")
    if name:
        conditions.append(f"LOWER(name) LIKE '%{name.lower()}%'")
    # ... বাকি

    if not conditions:
        return JSONResponse(status_code=400, content={"error": "At least one search param required"})

    where = " AND ".join(conditions)
    conn = duckdb.connect()
    conn.execute("SET memory_limit='400MB';")
    conn.execute("SET threads=4;")
    conn.execute("SET http_timeout=60;")
    
    try:
        # সব শার্ডের UNION
        union = " UNION ALL ".join([
            f"SELECT *, '{shard}' as _source FROM read_parquet('{DATASET_BASE}/{shard}')"
            for shard in ALL_SHARDS
        ])
        query = f"SELECT * FROM ({union}) WHERE {where} LIMIT {limit}"
        df = conn.execute(query).df()
        if df.empty:
            return JSONResponse(status_code=404, content={"status": "not_found"})
        records = df.to_dict(orient='records')
        return {
            "status": "success",
            "count": len(records),
            "time_ms": round((time.time()-start)*1000, 2),
            "results": records
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        conn.close()
