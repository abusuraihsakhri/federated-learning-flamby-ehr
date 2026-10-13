"""
FastAPI REST API Server for Federated Learning Flamby Ehr.
"""
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .base import AuditLogger, PHIGuard, SecurityException
from .models import SystemTaskPayload, ConsensusDossier
from .supervisor import SystemSupervisor

supervisor = SystemSupervisor(model_provider="mock")

app = FastAPI(
    title="Federated Learning Flamby Ehr API",
    description="Enterprise Distributed Component Platform (Privacy-Preserving Federated Healthcare & FHE)",
    version="3.0.0-ENTERPRISE",
)


class ChatRequest(BaseModel):
    query: str


@app.get("/", include_in_schema=False)
def console():
    """Serve the local operations console; the API remains server-side."""
    page = Path(__file__).resolve().parent.parent / "web" / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="Console file is unavailable")
    return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"status": "HEALTHY", "service": "federated-learning-flamby-ehr", "domain": "Privacy-Preserving Federated Healthcare & FHE", "standard": "HIPAA Safe Harbor §164.514 / Google SecAgg Standards", "version": "3.0.0-ENTERPRISE"}


@app.get("/metrics")
def metrics():
    return {
        "dossiers_processed_total": len(supervisor.dossier_registry),
        "audit_blocks_total": len(AuditLogger.get_trail()),
        "system_status": "RUNNING"
    }


@app.post("/api/audit")
def api_audit(payload: SystemTaskPayload):
    try:
        dossier = supervisor.process_task(payload)
    except SecurityException:
        raise HTTPException(status_code=422, detail="Input contains a disallowed identifier")
    return dossier.to_dict()


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    try:
        ans = supervisor.query_supervisory_chat(req.query)
        return {"response": ans}
    except SecurityException:
        raise HTTPException(status_code=422, detail="Input contains a disallowed identifier")


@app.get("/api/audit/logs")
def api_audit_logs():
    return {"audit_trail": AuditLogger.get_trail(), "verified": AuditLogger.verify_integrity()}
