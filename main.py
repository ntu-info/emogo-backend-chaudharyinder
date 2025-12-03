"""
EmoGo Backend API
A FastAPI application for mood tracking with video vlogs.
"""

import os
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
VIDEOS_DIR = "videos"
MONGO_URL = os.getenv("MONGODB_URL")
DB_NAME = "emogo_db"
COLLECTION_NAME = "records"

# ==================== LIFESPAN CONTEXT ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection lifecycle"""
    # Startup
    if not MONGO_URL:
        logger.error("MONGODB_URL environment variable is not set!")
        raise RuntimeError("MONGODB_URL is required")
    
    app.mongodb_client = AsyncIOMotorClient(MONGO_URL)
    app.database = app.mongodb_client[DB_NAME]
    app.collection = app.database[COLLECTION_NAME]
    logger.info("Connected to MongoDB")
    
    yield
    
    # Shutdown
    app.mongodb_client.close()
    logger.info("Closed MongoDB connection")

# ==================== APP INITIALIZATION ====================
app = FastAPI(
    title="EmoGo Backend API",
    description="Mood tracking with video vlogs and geolocation",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure videos directory exists and mount static files
os.makedirs(VIDEOS_DIR, exist_ok=True)
app.mount(f"/{VIDEOS_DIR}", StaticFiles(directory=VIDEOS_DIR), name="videos")

# ==================== PYDANTIC MODELS ====================
class EmoRecord(BaseModel):
    """Model for emotion record"""
    mood: str = Field(..., min_length=1, max_length=50, description="User's mood")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    timestamp: str = Field(..., description="ISO format timestamp")
    vlog_file: Optional[str] = Field(default="demo_vlog.mp4", description="Video filename or URL")
    note: Optional[str] = Field(default=None, max_length=500, description="Optional note")

    @validator('timestamp')
    def validate_timestamp(cls, v):
        """Ensure timestamp is not empty"""
        if not v or not v.strip():
            raise ValueError("Timestamp cannot be empty")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "mood": "happy",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timestamp": "2025-12-03T10:30:00Z",
                "vlog_file": "my_vlog.mp4",
                "note": "Beautiful day in NYC"
            }
        }

class RecordResponse(BaseModel):
    """Response model for record operations"""
    status: str
    id: Optional[str] = None
    deleted: Optional[str] = None
    deleted_count: Optional[int] = None

# ==================== HELPER FUNCTIONS ====================
def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to JSON-serializable dict"""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

async def get_collection():
    """Dependency to get collection"""
    return app.collection

# ==================== API ROUTES ====================

@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "message": "EmoGo Backend is Live!",
        "version": "2.0.0",
        "status": "operational"
    }

@app.post(
    "/record",
    status_code=status.HTTP_201_CREATED,
    response_model=RecordResponse,
    tags=["Records"]
)
async def add_record(record: EmoRecord):
    """
    Create a new emotion record with optional video vlog
    
    - **mood**: User's current mood
    - **latitude**: Geolocation latitude
    - **longitude**: Geolocation longitude
    - **timestamp**: When the record was created
    - **vlog_file**: Optional video file name or URL
    - **note**: Optional text note
    """
    try:
        result = await app.collection.insert_one(record.model_dump())
        logger.info(f"Created record with ID: {result.inserted_id}")
        return RecordResponse(status="success", id=str(result.inserted_id))
    except Exception as e:
        logger.error(f"Error creating record: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create record"
        )

@app.get("/records", tags=["Records"])
async def list_records(
    limit: int = 100,
    skip: int = 0,
    mood: Optional[str] = None
):
    """
    List all emotion records with optional filtering
    
    - **limit**: Maximum number of records to return (default: 100)
    - **skip**: Number of records to skip (default: 0)
    - **mood**: Filter by specific mood (optional)
    """
    try:
        query = {"mood": mood} if mood else {}
        cursor = app.collection.find(query).sort("timestamp", -1).skip(skip).limit(limit)
        
        items = []
        async for doc in cursor:
            items.append(serialize_doc(doc))
        
        return {"records": items, "count": len(items)}
    except Exception as e:
        logger.error(f"Error fetching records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch records"
        )

@app.get("/record/{record_id}", tags=["Records"])
async def get_record(record_id: str):
    """Get a single record by ID"""
    if not ObjectId.is_valid(record_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid record ID format"
        )
    
    doc = await app.collection.find_one({"_id": ObjectId(record_id)})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found"
        )
    
    return serialize_doc(doc)

@app.delete(
    "/record/{record_id}",
    response_model=RecordResponse,
    tags=["Records"]
)
async def delete_record(record_id: str):
    """Delete a single record by ID"""
    if not ObjectId.is_valid(record_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid record ID format"
        )
    
    result = await app.collection.delete_one({"_id": ObjectId(record_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found"
        )
    
    logger.info(f"Deleted record: {record_id}")
    return RecordResponse(status="success", deleted=record_id)

@app.delete(
    "/records/cleanup",
    response_model=RecordResponse,
    tags=["Maintenance"]
)
async def cleanup_empty_vlogs():
    """Remove all records with missing or empty video files"""
    query = {
        "$or": [
            {"vlog_file": {"$exists": False}},
            {"vlog_file": None},
            {"vlog_file": ""}
        ]
    }
    
    result = await app.collection.delete_many(query)
    logger.info(f"Cleaned up {result.deleted_count} records without videos")
    return RecordResponse(status="success", deleted_count=result.deleted_count)

# ==================== ADMIN DASHBOARD ====================

@app.get("/export", response_class=HTMLResponse, tags=["Dashboard"])
async def export_dashboard(request: Request):
    """Interactive admin dashboard with statistics and filtering"""
    base_url = str(request.base_url).rstrip("/")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EmoGo Admin Dashboard</title>
        <style>
            :root {{
                --bg-primary: #0f172a;
                --bg-secondary: #1e293b;
                --bg-card: rgba(30, 41, 59, 0.8);
                --text-primary: #f1f5f9;
                --text-secondary: #94a3b8;
                --accent: #3b82f6;
                --accent-hover: #2563eb;
                --success: #10b981;
                --success-hover: #059669;
                --danger: #ef4444;
                --danger-hover: #dc2626;
                --border: #334155;
            }}
            
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                color: var(--text-primary);
                min-height: 100vh;
                padding: 2rem;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            
            header {{
                margin-bottom: 2rem;
            }}
            
            h1 {{
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.5rem;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            .subtitle {{
                color: var(--text-secondary);
                font-size: 0.95rem;
            }}
            
            .dashboard-grid {{
                display: grid;
                gap: 1.5rem;
                grid-template-columns: 1fr;
            }}
            
            @media (min-width: 1024px) {{
                .dashboard-grid {{
                    grid-template-columns: 380px 1fr;
                }}
            }}
            
            .card {{
                background: var(--bg-card);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 1.5rem;
                backdrop-filter: blur(10px);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            
            .card-title {{
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 1rem;
                color: var(--text-primary);
            }}
            
            /* Stats Grid */
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.75rem;
                margin-bottom: 1.5rem;
            }}
            
            .stat-card {{
                background: var(--bg-secondary);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1rem;
            }}
            
            .stat-label {{
                font-size: 0.75rem;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 0.5rem;
            }}
            
            .stat-value {{
                font-size: 1.75rem;
                font-weight: 700;
                color: var(--accent);
            }}
            
            /* Controls */
            .controls {{
                display: grid;
                grid-template-columns: 1fr;
                gap: 0.75rem;
                margin-bottom: 1.5rem;
            }}
            
            @media (min-width: 640px) {{
                .controls {{
                    grid-template-columns: repeat(2, 1fr);
                }}
            }}
            
            input, select {{
                width: 100%;
                padding: 0.65rem 1rem;
                background: var(--bg-secondary);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--text-primary);
                font-size: 0.9rem;
                transition: all 0.2s;
            }}
            
            input:focus, select:focus {{
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
            }}
            
            input::placeholder {{
                color: var(--text-secondary);
            }}
            
            .button-group {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.75rem;
            }}
            
            button {{
                padding: 0.65rem 1.25rem;
                border: none;
                border-radius: 8px;
                font-size: 0.9rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                background: var(--bg-secondary);
                color: var(--text-primary);
            }}
            
            button:hover {{
                transform: translateY(-1px);
            }}
            
            button.primary {{
                background: var(--accent);
                color: white;
            }}
            
            button.primary:hover {{
                background: var(--accent-hover);
            }}
            
            button.danger {{
                background: var(--danger);
                color: white;
                padding: 0.5rem 0.75rem;
                font-size: 0.85rem;
            }}
            
            button.danger:hover {{
                background: var(--danger-hover);
            }}
            
            /* Table */
            .table-container {{
                overflow-x: auto;
                border-radius: 12px;
                border: 1px solid var(--border);
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            
            th, td {{
                padding: 1rem;
                text-align: left;
                border-bottom: 1px solid var(--border);
            }}
            
            th {{
                background: var(--bg-secondary);
                font-weight: 600;
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: var(--text-secondary);
            }}
            
            tr:last-child td {{
                border-bottom: none;
            }}
            
            tbody tr:hover {{
                background: rgba(59, 130, 246, 0.05);
            }}
            
            .badge {{
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 500;
                background: var(--bg-secondary);
                border: 1px solid var(--border);
            }}
            
            .video-link {{
                display: inline-block;
                padding: 0.4rem 0.9rem;
                background: var(--success);
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-size: 0.85rem;
                font-weight: 600;
                transition: all 0.2s;
            }}
            
            .video-link:hover {{
                background: var(--success-hover);
                transform: translateY(-1px);
            }}
            
            .empty-state {{
                text-align: center;
                padding: 3rem 1rem;
                color: var(--text-secondary);
            }}
            
            .chart-container {{
                margin-top: 1rem;
                height: 200px;
            }}
            
            footer {{
                text-align: center;
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid var(--border);
                color: var(--text-secondary);
                font-size: 0.85rem;
            }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🎭 EmoGo Dashboard</h1>
                <p class="subtitle">Manage emotion records, analyze patterns, and track mood trends</p>
            </header>

            <div class="dashboard-grid">
                <!-- Sidebar: Stats & Controls -->
                <div>
                    <div class="card">
                        <h2 class="card-title">📊 Statistics</h2>
                        <div class="stats-grid">
                            <div class="stat-card">
                                <div class="stat-label">Total Records</div>
                                <div id="statTotal" class="stat-value">0</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-label">With Videos</div>
                                <div id="statWithVid" class="stat-value">0</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-label">Unique Moods</div>
                                <div id="statMoods" class="stat-value">0</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-label">Latest Entry</div>
                                <div id="statLatest" class="stat-value" style="font-size: 0.9rem;">—</div>
                            </div>
                        </div>
                    </div>

                    <div class="card" style="margin-top: 1.5rem;">
                        <h2 class="card-title">🔍 Filters</h2>
                        <div class="controls">
                            <input id="searchNote" type="text" placeholder="Search notes...">
                            <select id="moodFilter">
                                <option value="">All moods</option>
                            </select>
                            <input id="dateFrom" type="date" placeholder="From date">
                            <input id="dateTo" type="date" placeholder="To date">
                        </div>
                        <div class="button-group">
                            <button id="resetBtn">Reset</button>
                            <button id="refreshBtn" class="primary">Refresh</button>
                        </div>
                    </div>

                    <div class="card" style="margin-top: 1.5rem;">
                        <h2 class="card-title">📈 Mood Distribution</h2>
                        <div class="chart-container">
                            <canvas id="moodChart"></canvas>
                        </div>
                    </div>

                    <div class="card" style="margin-top: 1.5rem;">
                        <h2 class="card-title">📅 Timeline</h2>
                        <div class="chart-container">
                            <canvas id="timelineChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Main: Data Table -->
                <div class="card">
                    <h2 class="card-title">📋 Records</h2>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Mood</th>
                                    <th>Location</th>
                                    <th>Note</th>
                                    <th>Video</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="tableBody">
                                <tr><td colspan="6" class="empty-state">Loading records...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <footer>
                Powered by EmoGo Backend v2.0 • Static files: {base_url}/videos
            </footer>
        </div>

        <script>
            const BASE_URL = "{base_url}";
            let allRecords = [];
            let filteredRecords = [];
            let moodChart, timelineChart;

            const elements = {{
                tableBody: document.getElementById("tableBody"),
                moodFilter: document.getElementById("moodFilter"),
                searchNote: document.getElementById("searchNote"),
                dateFrom: document.getElementById("dateFrom"),
                dateTo: document.getElementById("dateTo"),
                resetBtn: document.getElementById("resetBtn"),
                refreshBtn: document.getElementById("refreshBtn"),
                statTotal: document.getElementById("statTotal"),
                statWithVid: document.getElementById("statWithVid"),
                statMoods: document.getElementById("statMoods"),
                statLatest: document.getElementById("statLatest"),
            }};

            // Utility Functions
            function getVideoUrl(file) {{
                if (!file) return "";
                return file.startsWith("http") ? file : `${{BASE_URL}}/videos/${{file}}`;
            }}

            function parseDate(dateStr) {{
                const date = new Date(dateStr);
                return isNaN(date.getTime()) ? null : date;
            }}

            function formatDate(date) {{
                if (!date) return "—";
                return new Intl.DateTimeFormat('en-US', {{
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                }}).format(date);
            }}

            // Delete Record
            async function deleteRecord(id) {{
                if (!confirm("Delete this record permanently?")) return;
                
                try {{
                    const response = await fetch(`${{BASE_URL}}/record/${{id}}`, {{
                        method: "DELETE"
                    }});
                    
                    if (response.ok) {{
                        await fetchRecords();
                    }} else {{
                        alert("Failed to delete record");
                    }}
                }} catch (error) {{
                    console.error("Delete error:", error);
                    alert("Error deleting record");
                }}
            }}

            // Fetch Records
            async function fetchRecords() {{
                try {{
                    const response = await fetch(`${{BASE_URL}}/records?limit=1000`);
                    const data = await response.json();
                    allRecords = data.records || [];
                    initializeMoodOptions();
                    applyFilters();
                }} catch (error) {{
                    console.error("Fetch error:", error);
                    elements.tableBody.innerHTML = `
                        <tr><td colspan="6" class="empty-state">
                            Failed to load records. Please try again.
                        </td></tr>
                    `;
                }}
            }}

            // Initialize Mood Filter
            function initializeMoodOptions() {{
                const moods = [...new Set(allRecords.map(r => r.mood).filter(Boolean))].sort();
                elements.moodFilter.innerHTML = 
                    '<option value="">All moods</option>' +
                    moods.map(m => `<option value="${{m}}">${{m}}</option>`).join('');
            }}

            // Apply Filters
            function applyFilters() {{
                const searchTerm = elements.searchNote.value.toLowerCase();
                const selectedMood = elements.moodFilter.value;
                const fromDate = parseDate(elements.dateFrom.value);
                const toDate = parseDate(elements.dateTo.value);

                filteredRecords = allRecords.filter(record => {{
                    const note = (record.note || "").toLowerCase();
                    const matchesSearch = !searchTerm || note.includes(searchTerm);
                    const matchesMood = !selectedMood || record.mood === selectedMood;
                    
                    const recordDate = parseDate(record.timestamp);
                    const matchesFrom = !fromDate || (recordDate && recordDate >= fromDate);
                    const matchesTo = !toDate || (recordDate && recordDate <= toDate);

                    return matchesSearch && matchesMood && matchesFrom && matchesTo;
                }});

                renderTable();
                updateStatistics();
                renderCharts();
            }}

            // Render Table
            function renderTable() {{
                if (filteredRecords.length === 0) {{
                    elements.tableBody.innerHTML = `
                        <tr><td colspan="6" class="empty-state">
                            No records match your filters
                        </td></tr>
                    `;
                    return;
                }}

                elements.tableBody.innerHTML = filteredRecords.map(record => {{
                    const videoUrl = getVideoUrl(record.vlog_file);
                    const location = [record.latitude, record.longitude]
                        .filter(v => v != null)
                        .join(", ");
                    
                    const videoCell = videoUrl 
                        ? `<a href="${{videoUrl}}" target="_blank" class="video-link">▶ Watch</a>`
                        : '<span class="badge">No video</span>';

                    return `
                        <tr>
                            <td>${{formatDate(parseDate(record.timestamp))}}</td>
                            <td><span class="badge">${{record.mood || "—"}}</span></td>
                            <td>${{location || "—"}}</td>
                            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">
                                ${{record.note || ""}}
                            </td>
                            <td>${{videoCell}}</td>
                            <td>
                                <button class="danger" onclick="deleteRecord('${{record._id}}')">
                                    🗑️ Delete
                                </button>
                            </td>
                        </tr>
                    `;
                }}).join('');
            }}

            // Update Statistics
            function updateStatistics() {{
                elements.statTotal.textContent = filteredRecords.length;
                
                const withVideo = filteredRecords.filter(r => r.vlog_file).length;
                elements.statWithVid.textContent = withVideo;
                
                const uniqueMoods = new Set(filteredRecords.map(r => r.mood).filter(Boolean));
                elements.statMoods.textContent = uniqueMoods.size;
                
                const latestDate = filteredRecords
                    .map(r => parseDate(r.timestamp))
                    .filter(Boolean)
                    .sort((a, b) => b - a)[0];
                
                elements.statLatest.textContent = formatDate(latestDate);
            }}

            // Render Charts
            function renderCharts() {{
                // Mood Distribution
                const moodCounts = filteredRecords.reduce((acc, r) => {{
                    if (r.mood) acc[r.mood] = (acc[r.mood] || 0) + 1;
                    return acc;
                }}, {{}});
                
                const moodLabels = Object.keys(moodCounts);
                const moodData = moodLabels.map(k => moodCounts[k]);

                if (moodChart) moodChart.destroy();
                moodChart = new Chart(document.getElementById("moodChart"), {{
                    type: "doughnut",
                    data: {{
                        labels: moodLabels,
                        datasets: [{{
                            data: moodData,
                            backgroundColor: [
                                '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', 
                                '#10b981', '#06b6d4', '#ef4444'
                            ],
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                position: 'bottom',
                                labels: {{ color: '#94a3b8', font: {{ size: 11 }} }}
                            }}
                        }}
                    }}
                }});

                // Timeline Chart
                const byDay = filteredRecords.reduce((acc, r) => {{
                    const date = parseDate(r.timestamp);
                    if (!date) return acc;
                    const key = date.toISOString().split('T')[0];
                    acc[key] = (acc[key] || 0) + 1;
                    return acc;
                }}, {{}});
                
                const timelineLabels = Object.keys(byDay).sort();
                const timelineData = timelineLabels.map(k => byDay[k]);

                if (timelineChart) timelineChart.destroy();
                timelineChart = new Chart(document.getElementById("timelineChart"), {{
                    type: "line",
                    data: {{
                        labels: timelineLabels,
                        datasets: [{{
                            label: "Records",
                            data: timelineData,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            x: {{ ticks: {{ color: '#64748b', maxRotation: 45 }} }},
                            y: {{ 
                                ticks: {{ color: '#64748b' }}, 
                                beginAtZero: true 
                            }}
                        }}
                    }}
                }});
            }}

            // Event Listeners
            ["input", "change"].forEach(event => {{
                elements.searchNote.addEventListener(event, applyFilters);
                elements.moodFilter.addEventListener(event, applyFilters);
                elements.dateFrom.addEventListener(event, applyFilters);
                elements.dateTo.addEventListener(event, applyFilters);
            }});

            elements.resetBtn.addEventListener("click", () => {{
                elements.searchNote.value = "";
                elements.moodFilter.value = "";
                elements.dateFrom.value = "";
                elements.dateTo.value = "";
                applyFilters();
            }});

            elements.refreshBtn.addEventListener("click", fetchRecords);

            // Initialize
            fetchRecords();
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

# ==================== ERROR HANDLERS ====================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={"error": "Resource not found", "path": str(request.url)}
    )

@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    """Custom 500 handler"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )