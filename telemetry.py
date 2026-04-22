"""Telemetry for EVEZ"""
from datetime import datetime
import json

def track(event, data=None):
    return {
        "event": event,
        "data": data or {},
        "timestamp": datetime.now().isoformat()
    }

def report():
    return {
        "events": [],
        "errors": 0,
        "uptime": "100%"
    }

if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
