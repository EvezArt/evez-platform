"""EVEZ Client SDK"""
import requests, json

class EvezClient:
    def __init__(self, api_key, base_url="http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        
    def submit_task(self, task_data, priority="normal"):
        resp = requests.post(
            f"{self.base_url}/v1/task",
            json={"task": task_data, "priority": priority},
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return resp.json()
    
    def get_status(self, task_id):
        resp = requests.get(f"{self.base_url}/v1/task/{task_id}")
        return resp.json()
    
    def get_usage(self):
        resp = requests.get(f"{self.base_url}/v1/usage", 
                          headers={"Authorization": f"Bearer {self.api_key}"})
        return resp.json()
