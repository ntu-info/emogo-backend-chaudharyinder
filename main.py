import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from bson import ObjectId
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()

app = FastAPI()

# 2. Ensure 'videos' directory exists to prevent crash
os.makedirs("videos", exist_ok=True)

# 3. MOUNT STATIC FILES
# This allows the URL /videos/filename.mp4 to serve files from the "videos" folder
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

# 4. DATABASE CONNECTION
MONGO_URL = os.getenv("MONGODB_URL")
if not MONGO_URL:
    print("WARNING: MONGODB_URL is not set!")

client = AsyncIOMotorClient(MONGO_URL)
db = client.emogo_db
collection = db.records

# 5. DATA MODEL
class EmoRecord(BaseModel):
    mood: str
    latitude: float
    longitude: float
    timestamp: str
    vlog_file: Optional[str] = "demo_vlog.mp4" # Default to your fake video
    note: Optional[str] = None

# ==========================
#        ENDPOINTS
# ==========================

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Live (HTML Version)!"}

@app.post("/record", status_code=201)
async def add_record(record: EmoRecord):
    result = await collection.insert_one(record.dict())
    return {"status": "success", "id": str(result.inserted_id)}

# --- DASHBOARD ENDPOINT (Required by Prof) ---
@app.get("/export", response_class=HTMLResponse)
async def export_dashboard():
    # Fetch all records, sorted by newest first
    records = []
    async for doc in collection.find().sort("timestamp", -1):
        records.append(doc)

    # Generate HTML Table Rows
    table_rows = ""
    for r in records:
        # Logic to handle the video link
        filename = r.get('vlog_file', 'demo_vlog.mp4')
        
        # Determine if we should show a link or "No Video"
        if not filename or filename == "no_video.mp4":
            video_display = "<span style='color:gray'>No Video</span>"
        else:
            video_display = f"<a href='/videos/{filename}' target='_blank'>Watch/Download</a>"
        
        table_rows += f"""
        <tr>
            <td>{r.get('timestamp')}</td>
            <td>{r.get('mood')}</td>
            <td>{r.get('latitude')}, {r.get('longitude')}</td>
            <td>{r.get('note', '')}</td>
            <td>{video_display}</td>
            <td><button onclick="deleteRecord('{str(r['_id'])}')" style="background-color:#dc3545;">Delete</button></td>
        </tr>
        """

    # The Full HTML Page with JavaScript for deletion
    html_content = f"""
    <html>
        <head>
            <title>EmoGo Admin Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }}
                h1 {{ color: #333; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; shadow: 0 1px 3px rgba(0,0,0,0.2); }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #007bff; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                a, button {{ text-decoration: none; color: white; background-color: #28a745; padding: 5px 10px; border-radius: 4px; border: none; cursor: pointer; }}
                a:hover {{ background-color: #218838; }}
            </style>
            <script>
                async function deleteRecord(id) {{
                    if(confirm("Are you sure you want to delete this record?")) {{
                        const response = await fetch('/record/' + id, {{ method: 'DELETE' }});
                        if (response.ok) {{
                            window.location.reload();
                        }} else {{
                            alert("Failed to delete");
                        }}
                    }}
                }}
            </script>
        </head>
        <body>
            <h1>📊 EmoGo Backend Dashboard</h1>
            <p>
                This page lists all collected user data. <br>
                <a href="/docs" style="background-color:#6c757d;">Add Data via API Docs</a>
            </p>
            <table>
                <tr>
                    <th>Timestamp</th>
                    <th>Mood</th>
                    <th>Location (GPS)</th>
                    <th>Note</th>
                    <th>Vlog Evidence</th>
                    <th>Action</th>
                </tr>
                {table_rows}
            </table>
        </body>
    </html>
    """
    return html_content

# --- CLEANUP ENDPOINTS (New) ---

@app.delete("/record/{record_id}")
async def delete_record(record_id: str):
    # Validate ObjectId
    if not ObjectId.is_valid(record_id):
        raise HTTPException(status_code=400, detail="Invalid record_id")
    
    # Attempt delete
    result = await collection.delete_one({"_id": ObjectId(record_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")
        
    return {"status": "success", "deleted": str(record_id)}

@app.delete("/records/cleanup")
async def cleanup_empty_vlogs():
    # Delete posts where vlog_file is missing, null, empty, or using old placeholders
    query = {
        "$or": [
            {"vlog_file": {"$exists": False}},
            {"vlog_file": None},
            {"vlog_file": ""},
            {"vlog_file": "video_placeholder.mp4"}, 
            {"vlog_file": "my_day_video.mp4"}
        ]
    }
    result = await collection.delete_many(query)
    return {"status": "success", "deleted_count": result.deleted_count}