# Real-Time Biometric Muster & Forensic Perimeter Engine 🚨

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](backend/server.py)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-emerald.svg)](backend/server.py)
[![WebSockets](https://img.shields.io/badge/WebSockets-Realtime-purple.svg)](backend/server.py)

An applied Computer Vision, Edge AI, and Spatial Analytics platform designed for **Automated Building Fire Evacuation Tracking** and **Police Forensic Perimeter Defense**.

---

## 📌 Abstract & Problem Statement

During emergency building evacuations (e.g., fires or active safety alerts), manual roll-call checklists leave first responders blind regarding **who is still trapped inside** and **where they are located**. Furthermore, security teams lack real-time forensic oversight regarding unauthorized individuals present inside critical infrastructure during evacuation windows.

This research project introduces a 3-tier architecture:
1. **Turnstile Biometric Vector Ingestion (`IN_BUILDING` Matrix)**: Logs employees scanning their face upon entry, querying only active daily occupants during emergencies.
2. **Spatial Zone Security Classification (Public vs. Hotzones)**:
   * **Public Zones (Lobby/Reception)**: Non-employee guests are logged without false alarms.
   * **Restricted Hotzones (Server Rooms/Labs)**: Unregistered face vectors immediately trigger high-priority **Police Forensic Breach Alerts**.
3. **Automated First Responder & Police Dossier Export**: Generates floor-coordinate rosters for firefighters and high-resolution forensic snapshot evidence for law enforcement.

---

## 🏗️ System Architecture

```
                                +-----------------------------------+
                                |   Turnstile Entrance Face Scanner |
                                +-----------------+-----------------+
                                                  |
                                                  v  (Face Embedding & Timestamp)
+-------------------------+     +-----------------+-----------------+
|  IP Cameras / Edge Cams | --> |  FastAPI & WebSocket Event Engine |
|  (Lobby & Hotzone Cams) |     +-----------------+-----------------+
+-------------------------+                       |
                                                  v  (Real-Time Broadcast)
                                +-----------------+-----------------+
                                |  Emergency Response Dashboard UI  |
                                |  (Interactive Floor Plan Map)     |
                                +-----------------+-----------------+
                                                  |
                                                  v  (Export On-Demand)
                                +-----------------+-----------------+
                                |  Firefighter & Police Brief PDF   |
                                +-----------------------------------+
```

---

## 📂 Repository Structure

```
emergency-biometric-muster/
├── LICENSE                 # MIT License with Copyright Notice
├── README.md               # Research documentation & Setup Guide
├── frontend/
│   └── index.html          # Interactive Emergency Dashboard UI
├── backend/
│   ├── server.py           # FastAPI & WebSocket Event Server
│   └── requirements.txt    # Python Dependencies
└── cv_engine/
    └── webcam_detector.py  # Laptop Webcam / CV Detector Script
```

---

## 🚀 Quickstart Guide

### 1. Run the Backend WebSocket Server

```bash
cd backend
pip install -r requirements.txt
python server.py
```
*The server will start on `http://localhost:8000` with WebSocket support at `ws://localhost:8000/ws`.*

### 2. Open the Emergency Dashboard

Open `frontend/index.html` in any web browser, or serve it via Python:

```bash
cd frontend
python -m http.server 3000
```
*Navigate to `http://localhost:3000` to view the live building floor plan and occupant roster.*

### 3. Run the Laptop Webcam Detection Script (Optional)

```bash
cd cv_engine
python webcam_detector.py
```
*Point your laptop webcam at yourself to simulate real-time face detection events broadcasted directly to the live dashboard!*

---

## 🛡️ Privacy & Biometric Ethics

* **Zero-Knowledge Biometrics**: Raw face photos are processed locally on edge nodes. Only mathematical 512-dimensional vector embeddings are stored in volatile memory during the active shift.
* **Shift Expiration**: Biometric entry logs automatically purge 24 hours after shift completion to comply with global privacy standards (GDPR / CCPA).

---

## 📄 License & Attribution

This project is open-sourced under the **MIT License**. Feel free to use, modify, and extend this project for academic research, hackathons, or safety innovations with attribution.
