import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables (for local testing)
load_dotenv()

app = FastAPI()

# 1. Database Connection
# We use an environment variable so we don't hardcode passwords!
MONGO_URL = os.getenv("MONGODB_URL")
if not MONGO_URL:
    print("Warning: MONGODB_URL not set")

# Create the MongoDB client
client = AsyncIOMotorClient(MONGO_URL)
db = client.emogo_db  # This creates a database named 'emogo_db'
collection = db.records # This creates a collection named 'records'

# 2. Data Model
# Based on the slides, we need to store mood, location, and time [cite: 29, 57]
class EmoRecord(BaseModel):
    mood: str          # e.g., "Sadness", "Joy"
    latitude: float    # e.g., 121.5434
    longitude: float   # e.g., 25.0330
    timestamp: str     # ISO format string
    note: Optional[str] = None

# 3. API Endpoints

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is running!"}

# Endpoint to SAVE data (POST)
@app.post("/record", status_code=201)
async def create_record(record: EmoRecord):
    # Convert Pydantic model to dictionary
    record_dict = record.dict()
    
    # Insert into MongoDB [cite: 535]
    result = await collection.insert_one(record_dict)
    
    return {"id": str(result.inserted_id), "message": "Record saved successfully"}

# Endpoint to EXPORT data (GET) - Required by Assignment [cite: 195]
@app.get("/export")
async def export_records():
    records = []
    # Find all documents in the collection
    cursor = collection.find({})
    
    async for document in cursor:
        # Convert ObjectId to string for JSON compatibility
        document["_id"] = str(document["_id"])
        records.append(document)
        
    return records