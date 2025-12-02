import os
from fastapi import FastAPI
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, List

app = FastAPI()

# Database Connection
MONGO_URL = os.getenv("MONGODB_URL")
client = AsyncIOMotorClient(MONGO_URL)
db = client.emogo_db
collection = db.records

# Updated Data Model: Includes Vlog, Mood, and GPS
class EmoRecord(BaseModel):
    mood: str              # Sentiment
    latitude: float        # GPS
    longitude: float       # GPS
    timestamp: str         # Time
    vlog_file: Optional[str] = "no_video.mp4"  # NEW: Vlog filename
    note: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Running"}

# Endpoint to Add Data
@app.post("/record")
async def add_record(record: EmoRecord):
    await collection.insert_one(record.dict())
    return {"status": "success", "msg": "Record saved!"}

# Endpoint to Export Data (The one TAs will check)
@app.get("/export")
async def export_records():
    records = []
    # We exclude '_id' so the output is clean JSON
    async for doc in collection.find({}, {"_id": 0}):
        records.append(doc)
    return records