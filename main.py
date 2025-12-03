import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# 1. MOUNT STATIC FILES (Crucial for Video Download)
# This tells FastAPI: "If someone asks for /videos/filename, look in the 'videos' folder"
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

# 2. DATABASE CONNECTION
MONGO_URL = os.getenv("MONGODB_URL")
client = AsyncIOMotorClient(MONGO_URL)
db = client.emogo_db
collection = db.records

# 3. DATA MODEL
class EmoRecord(BaseModel):
    mood: str
    latitude: float
    longitude: float
    timestamp: str
    vlog_file: Optional[str] = "demo_vlog.mp4" # Default to our fake video
    note: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Live (HTML Version)!"}

# Endpoint to Add Data (Same as before)
@app.post("/record")
async def add_record(record: EmoRecord):
    await collection.insert_one(record.dict())
    return {"status": "success", "msg": "Record saved!"}

# Endpoint to Export Data (UPDATED: Returns HTML Dashboard)
@app.get("/export", response_class=HTMLResponse)
async def export_dashboard():
    # Fetch all records from MongoDB
    records = []
    async for doc in collection.find().sort("timestamp", -1): # Sort by newest first
        records.append(doc)

    # Generate the HTML Table Rows
    table_rows = ""
    for r in records:
        # Create a clickable link for the video
        # The link points to /videos/{filename}
        video_link = f"<a href='/videos/{r.get('vlog_file', 'demo_vlog.mp4')}' target='_blank'>Watch/Download</a>"
        
        table_rows += f"""
        <tr>
            <td>{r.get('timestamp')}</td>
            <td>{r.get('mood')}</td>
            <td>{r.get('latitude')}, {r.get('longitude')}</td>
            <td>{r.get('note', '')}</td>
            <td>{video_link}</td>
        </tr>
        """

    # The Full HTML Page
    html_content = f"""
    <html>
        <head>
            <title>EmoGo Admin Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }}
                h1 {{ color: #333; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #007bff; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                a {{ text-decoration: none; color: white; background-color: #28a745; padding: 5px 10px; border-radius: 4px; }}
                a:hover {{ background-color: #218838; }}
            </style>
        </head>
        <body>
            <h1>📊 EmoGo Backend Dashboard</h1>
            <p>This page lists all collected user data. Click the button to view/download the vlog.</p>
            <table>
                <tr>
                    <th>Timestamp</th>
                    <th>Mood</th>
                    <th>Location (GPS)</th>
                    <th>Note</th>
                    <th>Vlog Evidence</th>
                </tr>
                {table_rows}
            </table>
        </body>
    </html>
    """
    return html_content