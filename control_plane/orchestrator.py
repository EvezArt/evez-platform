#!/usr/bin/env python3
"""EVEZ Control Plane - The brain of the operation"""
import redis, json, time, uuid
from datetime import datetime

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

class EvezControlPlane:
    def __init__(self):
        self.state = {"tasks": {}, "tenants": {}, "metrics": {}}
        
    def submit_task(self, task, tenant_id):
        task_id = str(uuid.uuid4())
        task["task_id"] = task_id
        task["tenant_id"] = tenant_id
        task["submitted_at"] = datetime.now().isoformat()
        task["status"] = "queued"
        
        r.hset(f"tasks:{tenant_id}", task_id, json.dumps(task))
        r.lpush("global_task_queue", json.dumps({"task_id": task_id, "tenant": tenant_id}))
        
        log(f"Task {task_id} queued for tenant {tenant_id}")
        return task_id
    
    def get_task_status(self, task_id, tenant_id):
        task = r.hget(f"tasks:{tenant_id}", task_id)
        return json.loads(task) if task else None
    
    def update_metrics(self, tenant_id, metric, value):
        key = f"metrics:{tenant_id}:{metric}"
        r.incrbyfloat(key, value)
    
    def get_tenant_usage(self, tenant_id):
        keys = r.keys(f"metrics:{tenant_id}:*")
        usage = {}
        for k in keys:
            metric = k.split(":")[-1]
            usage[metric] = float(r.get(k) or 0)
        return usage

if __name__ == "__main__":
    cp = EvezControlPlane()
    print("EVEZ Control Plane online")
    while True:
        time.sleep(10)
