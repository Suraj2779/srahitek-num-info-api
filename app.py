from fastapi import FastAPI, Query, Request, Depends, HTTPException, status, Cookie, Form, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.exceptions import HTTPException as StarletteHTTPException
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import duckdb
import os
import secrets
import hashlib
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv
import traceback

# Load Environment Variables
load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

# Security Token Hash
ADMIN_HASH = hashlib.sha256(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).hexdigest()

# Set Your Hidden Admin Path
SECRET_ADMIN_PATH = "/sra-secret-panel"

# Initialize MongoDB with better error handling
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
    db = mongo_client["hitek_gateway"]
    keys_collection = db["api_keys"]
    logs_collection = db["api_logs"]
    # Test connection
    mongo_client.admin.command('ping')
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    mongo_client = None
    keys_collection = None
    logs_collection = None

# Initialize FastAPI & DuckDB
app = FastAPI(docs_url=None, redoc_url=None) 
con = duckdb.connect()
con.execute("INSTALL httpfs;")
con.execute("LOAD httpfs;")

# Security Dependencies
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

# Helper function to clean NaN values for JSON compliance
def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj

# Cookie Based Admin Auth with error handling
def verify_admin(admin_auth: str = Cookie(None)):
    if not admin_auth or admin_auth != ADMIN_HASH:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# API Key Validation with error handling
def verify_api_key(request: Request, key_header: str = Depends(api_key_header), key_query: str = Depends(api_key_query)):
    api_key = key_header or key_query
    if not api_key:
        raise HTTPException(status_code=401, detail="API is missing")
    
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database connection error")
    
    try:
        key_data = keys_collection.find_one({"api_key": api_key})
        if not key_data:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        
        if not key_data.get("is_active"):
            raise HTTPException(status_code=401, detail="API Key has been revoked")
            
        if datetime.utcnow() > key_data.get("expires_at"):
            keys_collection.update_one({"api_key": api_key}, {"$set": {"is_active": False}})
            raise HTTPException(status_code=401, detail="API Key has expired")
        
        # Track Usage & Logs
        keys_collection.update_one({"api_key": api_key}, {"$inc": {"usage_count": 1}})
        if logs_collection is not None:
            logs_collection.insert_one({
                "client_name": key_data["client_name"],
                "api_key": api_key,
                "endpoint": request.url.path,
                "ip_address": request.client.host,
                "timestamp": datetime.utcnow()
            })
    except Exception as e:
        print(f"❌ API Key verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during verification")
    
    return api_key

# ----------------- EXCEPTION HANDLERS -----------------
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code in [401, 403]:
        return JSONResponse(
            status_code=exc.status_code, 
            content={
                "status": "error",
                "message": "API Key is missing or invalid.",
                "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
                "Buy_API": "Contact: https://t.me/SRACyberTechPvtLtd"
            }
        )
    return JSONResponse(
        status_code=exc.status_code, 
        content={"status": "rejected", "message": exc.detail, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"❌ Unhandled Exception: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal Server Error",
            "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
            "detail": str(exc)
        }
    )

# ----------------- PUBLIC ROUTES -----------------
@app.get("/", response_class=JSONResponse)
def root_landing_page():
    return {
        "status": "Api is running",
        "message": "SRA Phone Info API is running",
        "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot",
        "Channel": "https://t.me/SRACyberTechPvtLtd"
    }

@app.get("/FetchData")
def fetch_data(Number: str = Query(None), api_key: str = Depends(verify_api_key)):
    if not Number or not Number.isdigit() or len(Number) < 10 or len(Number) > 15:
        return JSONResponse(status_code=400, content={"status": "rejected", "message": "Invalid parameter.", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
    
    last_digit = Number[-1]
    
    # ================== আপনার ডেটাসেটের URL ==================
    base = "https://huggingface.co/datasets/MRSHREY197/Hitekdatabase/resolve/main"
    primary_url = f"{base}/final_master_shard_{last_digit}.parquet"
    alt_url = f"{base}/alt_master_shard_{last_digit}.parquet"
    
    try:
        # Query to fetch ALL matching records
        query = f"""
            SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') WHERE mobile = '{Number}'
            UNION ALL
            SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') WHERE alt = '{Number}'
        """
        raw_results = con.execute(query).df().to_dict(orient="records")
        
        # Clean NaN values
        cleaned_results = clean_nan(raw_results)
        
        # Group all matching rows into respective lists
        main_records = []
        alt_records = []
        for row in cleaned_results:
            row_type = row.pop('_record_type', '')
            if row_type == 'Main':
                main_records.append(row)
            elif row_type == 'Alt':
                alt_records.append(row)
        
        if not main_records and not alt_records:
            return JSONResponse(status_code=404, content={"status": "not_found", "phone": Number, "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})
            
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
        print(f"❌ DUCKDB CRASH LOG: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Data process error: {str(e)}", "Developer": "@SRA_CyberTech_Pvt_Ltd_Owner_bot"})

# ----------------- SECURE FORM LOGIN SYSTEM -----------------
LOGIN_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><title>SRA Security Login</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{background:#0a0a0a;height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif}}
        .box{{background:#141414;padding:40px;border-radius:16px;border:1px solid #00d4ff;width:380px}}
        h2{{color:#00d4ff;text-align:center;margin-bottom:24px;font-weight:600}}
        input{{width:100%;padding:14px;margin-bottom:16px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:14px}}
        input:focus{{outline:none;border-color:#00d4ff}}
        button{{width:100%;padding:14px;background:#00d4ff;color:#000;border:none;border-radius:8px;font-weight:700;font-size:16px;cursor:pointer;transition:0.2s}}
        button:hover{{background:#00b8e6}}
    </style>
</head>
<body>
    <div class="box">
        <h2>🔐 SRA Admin Access</h2>
        <form action="{SECRET_ADMIN_PATH}/login" method="POST">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login to Dashboard</button>
        </form>
    </div>
</body>
</html>
"""

@app.get(SECRET_ADMIN_PATH, response_class=HTMLResponse)
def admin_dashboard(request: Request, admin_auth: str = Cookie(None)):
    if not admin_auth or admin_auth != ADMIN_HASH:
        return HTMLResponse(content=LOGIN_HTML)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SRA Admin Console</title>
        <style>
            *{{margin:0;padding:0;box-sizing:border-box}}
            body{{background:#0a0a0a;color:#eee;font-family:system-ui,sans-serif;padding:24px}}
            .container{{max-width:1200px;margin:0 auto}}
            .header{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #00d4ff;padding-bottom:16px;margin-bottom:24px}}
            .header h1{{color:#00d4ff;font-size:28px}}
            .badge{{background:#003333;color:#00d4ff;padding:6px 16px;border-radius:20px;font-size:13px}}
            .logout{{background:#b91c1c;color:#fff;padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px}}
            .card{{background:#141414;padding:24px;border-radius:12px;border:1px solid #222;margin-bottom:24px}}
            .card h3{{color:#00d4ff;margin-bottom:16px}}
            .row{{display:flex;flex-wrap:wrap;gap:12px;align-items:center}}
            .row input,.row select{{padding:12px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;flex:1 1 180px}}
            .row button{{padding:12px 28px;background:#00d4ff;color:#000;border:none;border-radius:8px;font-weight:700;cursor:pointer}}
            .row button:hover{{background:#00b8e6}}
            .key-display{{margin-top:12px;color:#4ade80;font-weight:700}}
            table{{width:100%;border-collapse:collapse;font-size:14px}}
            th{{text-align:left;padding:12px 8px;color:#888;border-bottom:1px solid #222}}
            td{{padding:12px 8px;border-bottom:1px solid #111}}
            .status-active{{color:#4ade80;font-weight:700}}
            .status-disabled{{color:#facc15;font-weight:700}}
            .actions button{{padding:4px 12px;border:none;border-radius:4px;cursor:pointer;font-size:12px;margin-right:4px}}
            .actions .toggle{{background:#4b5563;color:#fff}}
            .actions .extend{{background:#2563eb;color:#fff}}
            .actions .delete{{background:#b91c1c;color:#fff}}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 SRA Security Dashboard</h1>
                <div>
                    <span class="badge">Dev: @SRA_CyberTech_Pvt_Ltd_Owner_bot</span>
                    <a href="{SECRET_ADMIN_PATH}/logout" class="logout">Logout</a>
                </div>
            </div>
            
            <div class="card">
                <h3>🔑 Issue API Key</h3>
                <div class="row">
                    <input type="text" id="clientName" placeholder="Client Name*">
                    <input type="text" id="customKey" placeholder="Custom API Key (Optional)">
                    <select id="daysValid">
                        <option value="7">7 Days</option>
                        <option value="30" selected>30 Days</option>
                        <option value="365">1 Year</option>
                    </select>
                    <button onclick="createKey()">Generate Key</button>
                </div>
                <div id="newKeyDisplay" class="key-display"></div>
            </div>

            <div class="card">
                <h3>📋 API Keys</h3>
                <div style="overflow-x:auto">
                    <table>
                        <thead>
                            <tr><th>Client</th><th>API Key</th><th>Usage</th><th>Expires At</th><th>Status</th><th>Actions</th></tr>
                        </thead>
                        <tbody id="keysTable"></tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <script>
            const adminPath = "{SECRET_ADMIN_PATH}";
            let fetchInterval;
            
            async function fetchKeys() {{
                try {{
                    const res = await fetch(adminPath + '/api/keys');
                    if(res.status === 401) {{ window.location.reload(); return; }}
                    if(!res.ok) throw new Error('Failed to fetch keys');
                    const data = await res.json();
                    let html = '';
                    data.keys.forEach(k => {{
                        const statusClass = k.is_active ? 'status-active' : 'status-disabled';
                        const statusText = k.is_active ? 'Active' : 'Disabled';
                        html += `
                        <tr>
                            <td><strong>${{k.client_name}}</strong></td>
                            <td style="font-family:monospace;color:#00d4ff">${{k.api_key}}</td>
                            <td style="font-weight:700;color:#a78bfa">${{k.usage_count || 0}}</td>
                            <td>${{new Date(k.expires_at).toLocaleDateString()}}</td>
                            <td class="${{statusClass}}">${{statusText}}</td>
                            <td class="actions">
                                <button class="toggle" onclick="toggleKey('${{k.api_key}}')">Toggle</button>
                                <button class="extend" onclick="extendKey('${{k.api_key}}')">+30d</button>
                                <button class="delete" onclick="deleteKey('${{k.api_key}}')">Del</button>
                            </td>
                        </tr>`;
                    }});
                    document.getElementById('keysTable').innerHTML = html;
                }} catch(e) {{
                    console.error('Fetch keys error:', e);
                }}
            }}
            
            async function createKey() {{
                const client = document.getElementById('clientName').value.trim();
                const custom = document.getElementById('customKey').value.trim();
                const days = document.getElementById('daysValid').value;
                if(!client) {{ alert('Enter Client Name'); return; }}
                
                const url = `${{adminPath}}/api/keys?client_name=${{encodeURIComponent(client)}}&days=${{days}}&custom_key=${{encodeURIComponent(custom)}}`;
                try {{
                    const res = await fetch(url, {{method: 'POST'}});
                    if(!res.ok) {{
                        const text = await res.text();
                        throw new Error(text || 'Server error');
                    }}
                    const data = await res.json();
                    document.getElementById('newKeyDisplay').innerText = `✅ SUCCESS! Key: ${{data.api_key}}`;
                    fetchKeys();
                }} catch(e) {{
                    alert('Error creating key: ' + e.message);
                }}
            }}
            
            async function toggleKey(key) {{
                try {{
                    await fetch(`${{adminPath}}/api/keys/toggle?api_key=${{key}}`, {{method: 'POST'}});
                    fetchKeys();
                }} catch(e) {{ alert('Error: ' + e.message); }}
            }}
            
            async function extendKey(key) {{
                if(!confirm('Extend 30 days?')) return;
                try {{
                    await fetch(`${{adminPath}}/api/keys/extend?api_key=${{key}}&days=30`, {{method: 'POST'}});
                    fetchKeys();
                }} catch(e) {{ alert('Error: ' + e.message); }}
            }}
            
            async function deleteKey(key) {{
                if(!confirm('Delete permanently?')) return;
                try {{
                    await fetch(`${{adminPath}}/api/keys/delete?api_key=${{key}}`, {{method: 'DELETE'}});
                    fetchKeys();
                }} catch(e) {{ alert('Error: ' + e.message); }}
            }}
            
            fetchKeys();
            fetchInterval = setInterval(fetchKeys, 10000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post(SECRET_ADMIN_PATH + "/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        response = RedirectResponse(url=SECRET_ADMIN_PATH, status_code=303)
        response.set_cookie(key="admin_auth", value=ADMIN_HASH, httponly=True, max_age=86400)
        return response
    
    return HTMLResponse(content="<script>alert('Invalid Credentials!'); window.location.href='" + SECRET_ADMIN_PATH + "';</script>")

@app.get(SECRET_ADMIN_PATH + "/logout")
def logout():
    response = RedirectResponse(url=SECRET_ADMIN_PATH, status_code=303)
    response.delete_cookie("admin_auth")
    return response

# ----------------- ADMIN API MANAGEMENT LOGIC (with error handling) -----------------
@app.post(f"{SECRET_ADMIN_PATH}/api/keys")
def create_api_key(client_name: str, days: int = 30, custom_key: str = None, is_admin: bool = Depends(verify_admin)):
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        new_key = custom_key.strip() if custom_key else "SRA_" + secrets.token_hex(4)
        if keys_collection.find_one({"api_key": new_key}):
            raise HTTPException(status_code=400, detail="Custom Key already exists!")
        keys_collection.insert_one({
            "client_name": client_name,
            "api_key": new_key,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=days),
            "is_active": True,
            "usage_count": 0
        })
        return {"status": "success", "api_key": new_key}
    except Exception as e:
        print(f"❌ Create key error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(f"{SECRET_ADMIN_PATH}/api/keys")
def list_api_keys(is_admin: bool = Depends(verify_admin)):
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        keys = list(keys_collection.find({}, {"_id": 0}).sort("created_at", -1))
        return {"keys": keys}
    except Exception as e:
        print(f"❌ List keys error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post(f"{SECRET_ADMIN_PATH}/api/keys/toggle")
def toggle_api_key(api_key: str, is_admin: bool = Depends(verify_admin)):
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        key_data = keys_collection.find_one({"api_key": api_key})
        if not key_data:
            raise HTTPException(status_code=404, detail="Key not found")
        keys_collection.update_one({"api_key": api_key}, {"$set": {"is_active": not key_data["is_active"]}})
        return {"status": "success"}
    except Exception as e:
        print(f"❌ Toggle key error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post(f"{SECRET_ADMIN_PATH}/api/keys/extend")
def extend_api_key(api_key: str, days: int = 30, is_admin: bool = Depends(verify_admin)):
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        key_data = keys_collection.find_one({"api_key": api_key})
        if not key_data:
            raise HTTPException(status_code=404, detail="Key not found")
        keys_collection.update_one({"api_key": api_key}, {"$set": {"expires_at": key_data["expires_at"] + timedelta(days=days)}})
        return {"status": "success"}
    except Exception as e:
        print(f"❌ Extend key error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete(f"{SECRET_ADMIN_PATH}/api/keys/delete")
def delete_api_key(api_key: str, is_admin: bool = Depends(verify_admin)):
    if keys_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        if keys_collection.delete_one({"api_key": api_key}).deleted_count > 0:
            if logs_collection is not None:
                logs_collection.delete_many({"api_key": api_key})
            return {"status": "deleted"}
        raise HTTPException(status_code=404, detail="Key not found")
    except Exception as e:
        print(f"❌ Delete key error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
