#!/usr/bin/env python3
"""EVEZ API Gateway - Multi-tenant entry point"""
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import redis, uuid, time
from typing import Optional

app = FastAPI(title="EVEZ Platform API")
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

class TaskRequest(BaseModel):
    task: dict
    priority: str = "normal"

class TenantRequest(BaseModel):
    name: str
    plan: str = "free"

def verify_api_key(authorization: str):
    """Verify tenant API key"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth")
    token = authorization.replace("Bearer ", "")
    # In production, validate against stored keys
    return "default"

@app.post("/v1/task")
async def submit_task(req: TaskRequest, authorization: Optional[str] = Header(None)):
    tenant = verify_api_key(authorization)
    task_id = str(uuid.uuid4())
    
    task = req.task.copy()
    task["task_id"] = task_id
    task["tenant_id"] = tenant
    task["priority"] = req.priority
    task["submitted_at"] = time.time()
    
    r.hset(f"tasks:{tenant}", task_id, json.dumps(task))
    r.lpush("global_task_queue", json.dumps({"task_id": task_id, "tenant": tenant, "complexity": task.get("complexity", 1)}))
    
    return {"job_id": task_id, "status": "queued", "tenant": tenant}

@app.get("/v1/task/{task_id}")
async def get_task(task_id: str, authorization: Optional[str] = Header(None)):
    tenant = verify_api_key(authorization)
    task = r.hget(f"tasks:{tenant}", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(task)

@app.get("/v1/usage")
async def get_usage(authorization: Optional[str] = Header(None)):
    tenant = verify_api_key(authorization)
    keys = r.keys(f"metrics:{tenant}:*")
    usage = {}
    for k in keys:
        metric = k.split(":")[-1]
        usage[metric] = float(r.get(k) or 0)
    return {"tenant": tenant, "usage": usage}

@app.get("/health")
async def health():
    return {"status": "ok", "platform": "EVEZ"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
