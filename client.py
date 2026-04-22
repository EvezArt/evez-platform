"""EVEZ Python Client"""
import requests

class EVEZClient:
    def __init__(self, base_url="https://api.evez.art"):
        self.base_url = base_url
    
    def health(self):
        r = requests.get(f"{self.base_url}/health")
        return r.json()
    
    def inference(self, prompt, model="gpt"):
        r = requests.post(f"{self.base_url}/inference", json={"prompt": prompt, "model": model})
        return r.json()
    
    def quantum(self, circuit):
        r = requests.post(f"{self.base_url}/quantum", json=circuit)
        return r.json()
