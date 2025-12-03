import os
from fastapi import FastAPI, HTTPException, Request
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

# 2. Ensure 'videos' directory exists
os.makedirs("videos", exist_ok=True)

# 3. Mount Static Files (Crucial for video playback)
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

# 4. Database Connection
MONGO_URL = os.getenv("MONGODB_URL")
if not MONGO_URL:
    print("WARNING: MONGODB_URL is not set!")

client = AsyncIOMotorClient(MONGO_URL)
db = client.emogo_db
collection = db.records

# 5. Data Model
class EmoRecord(BaseModel):
    mood: str
    latitude: float
    longitude: float
    timestamp: str
    vlog_file: Optional[str] = "demo_vlog.mp4"
    note: Optional[str] = None

# ==========================
#        API ROUTES
# ==========================

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Live (Rich Dashboard Version)!"}

@app.post("/record", status_code=201)
async def add_record(record: EmoRecord):
    result = await collection.insert_one(record.dict())
    return {"status": "success", "id": str(result.inserted_id)}

@app.get("/records")
async def list_records():
    # Return raw records as JSON for the interactive dashboard
    items = []
    # Sort by newest first
    async for doc in collection.find().sort("timestamp", -1):
        # Convert ObjectId to string for JSON serialization
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"records": items}

# ==========================
#    INTERACTIVE DASHBOARD
# ==========================

@app.get("/export", response_class=HTMLResponse)
async def export_dashboard(request: Request):
    base = str(request.base_url).rstrip("/")

    # Serve a rich HTML page that fetches data from /records and renders stats + charts
    html_content = f"""
    <html>
    <head>
        <title>EmoGo Admin Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            :root {{
                --bg: #0f172a;
                --panel: #111827;
                --text: #e5e7eb;
                --accent: #60a5fa;
                --muted: #9ca3af;
                --green: #22c55e;
                --red: #ef4444;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                padding: 24px;
                background: linear-gradient(180deg, #0b1220, #0f172a 40%, #0b1220);
                color: var(--text);
                font-family: Inter, Segoe UI, system-ui, Arial, sans-serif;
            }}
            h1 {{
                margin: 0 0 8px 0;
                font-size: 28px;
                font-weight: 700;
                letter-spacing: 0.2px;
            }}
            .subtitle {{
                color: var(--muted);
                margin-bottom: 22px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: 1fr;
                gap: 16px;
            }}
            @media (min-width: 1100px) {{
                .grid {{
                    grid-template-columns: 360px 1fr;
                }}
            }}
            .card {{
                background: rgba(17, 24, 39, 0.75);
                border: 1px solid #1f2937;
                border-radius: 12px;
                backdrop-filter: blur(6px);
                padding: 16px;
            }}
            .stat {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-bottom: 12px;
            }}
            .stat .item {{
                background: #0b1627;
                border: 1px solid #1f2937;
                border-radius: 10px;
                padding: 12px;
            }}
            .label {{ color: var(--muted); font-size: 12px; }}
            .value {{ font-size: 20px; font-weight: 700; }}
            .controls {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 10px;
                margin-bottom: 12px;
            }}
            input, select {{
                width: 100%;
                padding: 8px 10px;
                border-radius: 8px;
                border: 1px solid #374151;
                background: #0b1627;
                color: var(--text);
                outline: none;
            }}
            input::placeholder {{ color: #6b7280; }}
            button {{
                padding: 8px 12px;
                border-radius: 8px;
                border: 1px solid #374151;
                background: #0b1627;
                color: var(--text);
                cursor: pointer;
            }}
            button.primary {{
                background: #1d4ed8;
                border-color: #1d4ed8;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 8px;
            }}
            th, td {{
                padding: 10px;
                border-bottom: 1px solid #1f2937;
                text-align: left;
                font-size: 14px;
            }}
            th {{
                color: var(--muted);
                font-weight: 600;
            }}
            tr:hover td {{
                background: rgba(29, 78, 216, 0.08);
                transition: background 150ms;
            }}
            .pill {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: 999px;
                font-size: 12px;
                border: 1px solid #374151;
                color: var(--muted);
                background: #0b1627;
            }}
            .link-btn {{
                text-decoration: none;
                color: white;
                background-color: #10b981;
                padding: 6px 10px;
                border-radius: 6px;
            }}
            .link-btn:hover {{
                background-color: #059669;
            }}
            .empty {{
                padding: 18px;
                color: var(--muted);
                text-align: center;
            }}
            .footer {{
                color: var(--muted);
                text-align: center;
                margin-top: 16px;
                font-size: 12px;
            }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <h1>EmoGo Admin Dashboard</h1>
        <div class="subtitle">Explore records, filter by mood and date, and view summary statistics.</div>

        <div class="grid">
            <div class="card">
                <div class="controls">
                    <input id="searchNote" type="text" placeholder="Search note text…" />
                    <select id="moodFilter">
                        <option value="">All moods</option>
                    </select>
                    <input id="dateFrom" type="date" />
                </div>
                <div class="controls">
                    <input id="dateTo" type="date" />
                    <button id="resetBtn">Reset</button>
                    <button id="refreshBtn" class="primary">Refresh</button>
                </div>

                <div class="stat">
                    <div class="item">
                        <div class="label">Total Records</div>
                        <div id="statTotal" class="value">0</div>
                    </div>
                    <div class="item">
                        <div class="label">With Videos</div>
                        <div id="statWithVid" class="value">0</div>
                    </div>
                </div>
                <div class="stat">
                    <div class="item">
                        <div class="label">Unique Moods</div>
                        <div id="statMoods" class="value">0</div>
                    </div>
                    <div class="item">
                        <div class="label">Latest Timestamp</div>
                        <div id="statLatest" class="value">—</div>
                    </div>
                </div>

                <canvas id="moodChart" height="160"></canvas>
                <div style="height: 16px"></div>
                <canvas id="timelineChart" height="160"></canvas>
            </div>

            <div class="card">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Mood</th>
                            <th>Location</th>
                            <th>Note</th>
                            <th>Vlog</th>
                            <th>ID</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody">
                        <tr><td colspan="6" class="empty">Loading…</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer">Static files served from {base}/videos. Full URLs in vlog_file are used directly.</div>

        <script>
            const base = "{base}";
            let all = [];
            let filtered = [];
            let moodChart, timelineChart;

            const els = {{
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

            function fullVideoHref(file) {{
                if (!file) return "";
                return (file.startsWith("http")) ? file : `${{base}}/videos/${{file}}`;
            }}

            function parseDate(s) {{
                const d = new Date(s);
                return isNaN(d.getTime()) ? null : d;
            }}

            function fetchData() {{
                return fetch(`${{base}}/records`).then(r => r.json()).then(data => {{
                    all = Array.isArray(data.records) ? data.records : [];
                    initMoodOptions(all);
                    applyFilters();
                }}).catch(err => {{
                    els.tableBody.innerHTML = `<tr><td colspan="6" class="empty">Failed to load: ${{err}}</td></tr>`;
                }});
            }}

            function initMoodOptions(items) {{
                const moods = Array.from(new Set(items.map(r => r.mood).filter(Boolean))).sort();
                els.moodFilter.innerHTML = `<option value="">All moods</option>` + moods.map(m => `<option value="${{m}}">${{m}}</option>`).join("");
            }}

            function applyFilters() {{
                const q = (els.searchNote.value || "").toLowerCase();
                const mood = els.moodFilter.value || "";
                const from = parseDate(els.dateFrom.value);
                const to = parseDate(els.dateTo.value);
                filtered = all.filter(r => {{
                    const note = (r.note || "").toLowerCase();
                    const okNote = q ? note.includes(q) : true;
                    const okMood = mood ? r.mood === mood : true;
                    const d = parseDate(r.timestamp);
                    const okFrom = from ? (d && d >= from) : true;
                    const okTo = to ? (d && d <= to) : true;
                    return okNote && okMood && okFrom && okTo;
                }});
                renderTable(filtered);
                renderStats(filtered);
                renderCharts(filtered);
            }}

            function renderTable(items) {{
                if (!items.length) {{
                    els.tableBody.innerHTML = `<tr><td colspan="6" class="empty">No records found</td></tr>`;
                    return;
                }}
                els.tableBody.innerHTML = items.map(r => {{
                    const href = fullVideoHref(r.vlog_file);
                    const loc = [r.latitude, r.longitude].filter(v => v !== undefined && v !== null).join(", ");
                    const link = href ? `<a class="link-btn" href="${{href}}" target="_blank">Open</a>` : `<span class="pill">No video</span>`;
                    return `
                        <tr>
                            <td>${{r.timestamp || "—"}}</td>
                            <td><span class="pill">${{r.mood || "—"}}</span></td>
                            <td>${{loc || "—"}}</td>
                            <td>${{r.note || ""}}</td>
                            <td>${{link}}</td>
                            <td><span class="pill">${{r._id}}</span></td>
                        </tr>
                    `;
                }}).join("");
            }}

            function renderStats(items) {{
                els.statTotal.textContent = items.length;
                const withVid = items.filter(r => !!r.vlog_file).length;
                els.statWithVid.textContent = withVid;
                const uniqueMoods = new Set(items.map(r => r.mood).filter(Boolean));
                els.statMoods.textContent = uniqueMoods.size;
                const latest = items
                    .map(r => parseDate(r.timestamp))
                    .filter(Boolean)
                    .sort((a, b) => b - a)[0];
                els.statLatest.textContent = latest ? latest.toISOString() : "—";
            }}

            function renderCharts(items) {{
                const counts = items.reduce((acc, r) => {{
                    if (r.mood) acc[r.mood] = (acc[r.mood] || 0) + 1;
                    return acc;
                }}, {{}});
                const labels = Object.keys(counts);
                const values = labels.map(k => counts[k]);

                if (moodChart) moodChart.destroy();
                moodChart = new Chart(document.getElementById("moodChart"), {{
                    type: "bar",
                    data: {{
                        labels,
                        datasets: [{{
                            label: "Mood frequency",
                            data: values,
                            backgroundColor: labels.map(() => "rgba(96,165,250,0.5)"),
                            borderColor: labels.map(() => "#60a5fa"),
                            borderWidth: 1
                        }}]
                    }},
                    options: {{
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            x: {{ ticks: {{ color: "#cbd5e1" }} }},
                            y: {{ ticks: {{ color: "#cbd5e1" }}, beginAtZero: true }}
                        }}
                    }}
                }});

                const byDay = items.reduce((acc, r) => {{
                    const d = parseDate(r.timestamp);
                    if (!d) return acc;
                    const key = d.toISOString().slice(0, 10);
                    acc[key] = (acc[key] || 0) + 1;
                    return acc;
                }}, {{}});
                const tLabels = Object.keys(byDay).sort();
                const tValues = tLabels.map(k => byDay[k]);

                if (timelineChart) timelineChart.destroy();
                timelineChart = new Chart(document.getElementById("timelineChart"), {{
                    type: "line",
                    data: {{
                        labels: tLabels,
                        datasets: [{{
                            label: "Records per day",
                            data: tValues,
                            fill: false,
                            borderColor: "#22c55e",
                            tension: 0.3
                        }}]
                    }},
                    options: {{
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            x: {{ ticks: {{ color: "#cbd5e1" }} }},
                            y: {{ ticks: {{ color: "#cbd5e1" }}, beginAtZero: true }}
                        }}
                    }}
                }});
            }}

            ["input", "change"].forEach(evt => {{
                els.searchNote.addEventListener(evt, applyFilters);
                els.moodFilter.addEventListener(evt, applyFilters);
                els.dateFrom.addEventListener(evt, applyFilters);
                els.dateTo.addEventListener(evt, applyFilters);
            }});
            els.resetBtn.addEventListener("click", () => {{
                els.searchNote.value = "";
                els.moodFilter.value = "";
                els.dateFrom.value = "";
                els.dateTo.value = "";
                applyFilters();
            }});
            els.refreshBtn.addEventListener("click", fetchData);

            fetchData();
        </script>
    </body>
    </html>
    """
    return html_content

# ==========================
#     CLEANUP UTILITIES
# ==========================

@app.delete("/record/{record_id}")
async def delete_record(record_id: str):
    # Validate ObjectId
    if not ObjectId.is_valid(record_id):
        raise HTTPException(status_code=400, detail="Invalid record_id")
    result = await collection.delete_one({"_id": ObjectId(record_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "success", "deleted": str(record_id)}

@app.delete("/records/cleanup")
async def cleanup_empty_vlogs():
    # Delete posts with missing/empty vlog_file
    query = {
        "$or": [
            {"vlog_file": {"$exists": False}},
            {"vlog_file": None},
            {"vlog_file": ""},
        ]
    }
    result = await collection.delete_many(query)
    return {"status": "success", "deleted_count": result.deleted_count}