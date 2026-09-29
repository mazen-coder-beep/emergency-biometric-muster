/**
 * dashboard_auth_patch.js
 * ────────────────────────
 * Drop-in replacement for the <script> block in dashboard.html.
 *
 * Changes vs v1
 * ─────────────
 * 1. Fetches a JWT from /auth/token on load using dashboard credentials.
 * 2. Passes ?token=<jwt> when opening the WebSocket.
 * 3. On STATE_SNAPSHOT message, populates occupants from DB instead of
 *    the hardcoded JS array.
 * 4. exportPoliceBrief() fetches /api/export/police-brief from the server
 *    (auth header) and formats the response for download locally.
 * 5. Adds exponential-backoff WebSocket reconnection.
 *
 * Usage
 * ─────
 * In dashboard.html, replace the entire <script>…</script> block with:
 *   <script src="dashboard_auth_patch.js"></script>
 *
 * Set these two constants to match your .env values:
 */

const DASHBOARD_CLIENT_ID     = "dashboard_01";
const DASHBOARD_CLIENT_SECRET = "replace_me_dashboard_secret";
const BACKEND_HTTP            = "http://localhost:8000";
const BACKEND_WS              = "ws://localhost:8000";

// ── State ─────────────────────────────────────────────────────────────────────

let occupants    = [];   // populated from STATE_SNAPSHOT, then mutated live
let currentFloor  = 1;
let currentFilter = "all";
let _jwt          = null;
let _wsRetryDelay = 1000; // ms, doubles on each failed reconnect (cap 30 s)

// ── Auth ──────────────────────────────────────────────────────────────────────

async function fetchToken() {
  try {
    const res = await fetch(`${BACKEND_HTTP}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: DASHBOARD_CLIENT_ID,
        client_secret: DASHBOARD_CLIENT_SECRET,
      }),
    });
    if (!res.ok) throw new Error(`Auth failed: ${res.status}`);
    const data = await res.json();
    _jwt = data.access_token;
    console.log("[Auth] JWT obtained.");
    return true;
  } catch (e) {
    console.error("[Auth] Could not obtain token:", e);
    return false;
  }
}

// ── WebSocket with reconnect ──────────────────────────────────────────────────

function setupWebSocket() {
  if (!_jwt) {
    setWsStatus("offline");
    return;
  }

  let ws;
  try {
    ws = new WebSocket(`${BACKEND_WS}/ws?token=${encodeURIComponent(_jwt)}`);
  } catch (e) {
    console.error("[WS] Construction failed:", e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    _wsRetryDelay = 1000;
    setWsStatus("online");
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "STATE_SNAPSHOT") {
      // Replace local state with server truth
      occupants = data.occupants;
      updateStats();
      renderRoster();
      renderFloorPlan();
      checkHotzoneBanner();
      return;
    }

    if (data.type === "EVENT") {
      addLog(data.msg, data.eventType);
      if (data.occupant) {
        // Upsert into local array to match server state
        const idx = occupants.findIndex(o => o.id === data.occupant.id);
        if (idx !== -1) {
          occupants[idx] = data.occupant;
        } else {
          occupants.unshift(data.occupant);
        }
        updateStats();
        renderRoster();
        renderFloorPlan();
        checkHotzoneBanner();
      }
    }
  };

  ws.onerror = (err) => {
    console.error("[WS] Error:", err);
  };

  ws.onclose = () => {
    setWsStatus("offline");
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  console.log(`[WS] Reconnecting in ${_wsRetryDelay / 1000}s…`);
  setTimeout(async () => {
    // Re-fetch token in case it expired
    await fetchToken();
    setupWebSocket();
  }, _wsRetryDelay);
  _wsRetryDelay = Math.min(_wsRetryDelay * 2, 30_000);
}

function setWsStatus(state) {
  const el = document.getElementById("ws-status");
  if (!el) return;
  if (state === "online") {
    el.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span> Live Backend Connected`;
    el.className = `text-[11px] font-mono px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5`;
  } else {
    el.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span> Offline (Simulation Mode)`;
    el.className = `text-[11px] font-mono px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1.5`;
  }
}

// ── Server-side export ────────────────────────────────────────────────────────

async function exportPoliceBrief() {
  if (!_jwt) {
    alert("Not authenticated. Cannot generate server-side brief.");
    return;
  }

  try {
    const res = await fetch(`${BACKEND_HTTP}/api/export/police-brief`, {
      headers: { Authorization: `Bearer ${_jwt}` },
    });
    if (!res.ok) throw new Error(`Export failed: ${res.status}`);
    const d = await res.json();

    let report = `=====================================================\n`;
    report    += `  POLICE & FIREFIGHTER FORENSIC EVIDENCE DOSSIER     \n`;
    report    += `=====================================================\n`;
    report    += `Generated : ${d.generated_at}\n`;
    report    += `Facility  : ${d.facility}\n`;
    report    += `Hotzone Breaches      : ${d.summary.hotzone_breaches}\n`;
    report    += `Missing Employees     : ${d.summary.missing_employees}\n`;
    report    += `Lobby Visitors        : ${d.summary.lobby_visitors}\n\n`;

    report += `--- SECTION 1: RESTRICTED HOTZONE BREACH ALERTS ---\n`;
    if (d.hotzone_breaches.length === 0) {
      report += `[NO HOTZONE BREACHES DETECTED]\n\n`;
    } else {
      d.hotzone_breaches.forEach((h, i) => {
        report += `${i + 1}. ${h.name}\n`;
        report += `   Zone  : Floor ${h.floor} – ${h.zone} (${h.camera})\n`;
        report += `   Status: 🔥 RESTRICTED HOTZONE BREACH\n\n`;
      });
    }

    report += `--- SECTION 2: MISSING REGISTERED OCCUPANTS ---\n`;
    d.missing_employees.forEach((m, i) => {
      report += `${i + 1}. ${m.name} (${m.role})\n`;
      report += `   Last seen: Floor ${m.floor} – ${m.zone} (${m.camera})\n\n`;
    });

    report += `--- SECTION 3: RECENT EVENT LOG (last 50) ---\n`;
    d.recent_event_log.forEach(e => {
      report += `[${e.timestamp}] [${e.event_type.toUpperCase()}] ${e.msg}\n`;
      report += `   Camera: ${e.camera} | Zone: ${e.zone} | Posted by: ${e.posted_by}\n`;
    });

    const blob = new Blob([report], { type: "text/plain" });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement("a"), {
      href: url,
      download: `Police_Forensic_Brief_${Date.now()}.txt`,
    });
    a.click();
    URL.revokeObjectURL(url);

  } catch (e) {
    alert(`Export error: ${e.message}`);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  // Seed the UI with hardcoded data first so the dashboard isn't blank
  // while we wait for auth + WS STATE_SNAPSHOT
  occupants = [
    { id: 101, name: "Dr. Aris Thorne",  type: "REGISTERED",          role: "Lead Systems Engineer",          status: "MISSING",          floor: 2, zone: "Server Room B",         isHotzone: true,  camera: "CAM-204",       entryTime: "08:14:02 AM", avatar: "👨‍💻" },
    { id: 102, name: "Elena Rostova",    type: "REGISTERED",          role: "Operations Director",             status: "MISSING",          floor: 3, zone: "Executive Suite 301",    isHotzone: true,  camera: "CAM-301",       entryTime: "08:22:15 AM", avatar: "👩‍💼" },
    { id: 103, name: "Marcus Vance",     type: "REGISTERED",          role: "DevOps Technician",              status: "MISSING",          floor: 1, zone: "North Stairwell Entrance",isHotzone: false, camera: "CAM-102",       entryTime: "08:45:00 AM", avatar: "👨‍🔧" },
    { id: 104, name: "Sarah Lin",        type: "REGISTERED",          role: "Security Analyst",               status: "MISSING",          floor: 2, zone: "Research Lab 2B",         isHotzone: true,  camera: "CAM-209",       entryTime: "08:50:33 AM", avatar: "👩‍🔬" },
    { id: 105, name: "David Kim",        type: "REGISTERED",          role: "Product Manager",                status: "MISSING",          floor: 1, zone: "East Corridor",           isHotzone: false, camera: "CAM-105",       entryTime: "09:01:10 AM", avatar: "👨‍💼" },
    { id: 106, name: "Amara Oke",        type: "REGISTERED",          role: "QA Engineer",                    status: "MISSING",          floor: 3, zone: "Conference Room 3A",      isHotzone: true,  camera: "CAM-304",       entryTime: "09:05:44 AM", avatar: "👩‍💻" },
    { id: 107, name: "Robert Chen",      type: "REGISTERED",          role: "Hardware Architect",             status: "MISSING",          floor: 2, zone: "Testing Lab 210",         isHotzone: true,  camera: "CAM-203",       entryTime: "09:12:00 AM", avatar: "👨‍🔬" },
    { id: 108, name: "Hannah Abbott",    type: "REGISTERED",          role: "HR Generalist",                  status: "MISSING",          floor: 1, zone: "Break Room 102",          isHotzone: false, camera: "CAM-108",       entryTime: "09:15:20 AM", avatar: "👩‍💼" },
    { id: 111, name: "Lucas Miller",     type: "REGISTERED",          role: "Frontend Dev",                   status: "SAFE",             floor: 0, zone: "Assembly Zone Alpha",      isHotzone: false, camera: "OUTDOOR-CAM-01",entryTime: "08:30:00 AM", avatar: "👨‍💻" },
    { id: 112, name: "Sophia Patel",     type: "REGISTERED",          role: "UX Designer",                    status: "SAFE",             floor: 0, zone: "Assembly Zone Alpha",      isHotzone: false, camera: "OUTDOOR-CAM-01",entryTime: "08:35:12 AM", avatar: "👩‍🎨" },
    { id: 801, name: "VISITOR (Guest Badge #42)", type: "VISITOR_LOBBY", role: "Lobby / Waiting Area Visitor",status: "VISITOR_ALLOWED",  floor: 1, zone: "Lobby & Reception",       isHotzone: false, camera: "CAM-101",       entryTime: "09:40:15 AM", avatar: "👤"  },
    { id: 999, name: "UNREGISTERED INTRUDER #01", type: "UNREGISTERED_HOTZONE", role: "BREACH: Present in Restricted Hotzone", status: "HOTZONE_BREACH", floor: 2, zone: "Server Room B", isHotzone: true, camera: "CAM-204", entryTime: "UNREGISTERED INTRUSION", avatar: "🕵️‍♂️" },
  ];

  checkHotzoneBanner();
  renderFloorPlan();
  renderRoster();
  renderLogs();
  updateStats();

  // Auth + live connection
  const ok = await fetchToken();
  if (ok) setupWebSocket();
  else setWsStatus("offline");
}

// ── All functions below are unchanged from v1 ─────────────────────────────────
// (floorZones, initialLogs, renderFloorPlan, renderRoster, setRosterFilter,
//  simulateLobbyVisitor, simulateHotzoneIntrusion, simulateTurnstileCheckIn,
//  markSafe, flagForPolice, updateStats, addLog, renderLogs, switchFloor,
//  checkHotzoneBanner)
// Copy them verbatim from dashboard.html's existing <script> block.
// Only init(), setupWebSocket(), and exportPoliceBrief() are replaced above.
