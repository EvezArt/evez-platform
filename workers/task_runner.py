#!/usr/bin/env python3
"""Ray-compatible worker for EVEZ"""
import json, time, random, redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

MODELS = {
    "nano": {"cost": 0.001, "latency": 200},
    "small": {"cost": 0.003, "latency": 500},
    "medium": {"cost": 0.015, "latency": 1000},
    "large": {"cost": 0.075, "latency": 2000}
}

def execute_task(task_data):
    """Execute a task and return result"""
    tenant = task_data.get("tenant_id", "default")
    complexity = task_data.get("complexity", 1)
    
    # Select model based on complexity
    model = "nano" if complexity < 2 else "small" if complexity < 3 else "medium"
    cfg = MODELS[model]
    
    # Simulate work
    time.sleep(cfg["latency"] / 1000)
    
    result = {
        "status": "success",
        "model": model,
        "latency_ms": cfg["latency"],
        "cost": cfg["cost"],
        "tenant": tenant
    }
    
    # Update metrics
    r.incrbyfloat(f"metrics:{tenant}:compute_cost", cfg["cost"])
    r.incrby(f"metrics:{tenant}:tasks_completed", 1)
    
    return result

def worker_loop():
    """Main worker loop"""
    print("Worker started")
    while True:
        task_json = r.rpop("global_task_queue")
        if task_json:
            task = json.loads(task_json)
            result = execute_task(task)
            print(f"Task {task['task_id']} -> {result['model']} (${result['cost']})")
        time.sleep(0.5)

if __name__ == "__main__":
    worker_loop()
