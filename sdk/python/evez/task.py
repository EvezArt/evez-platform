"""Task definition for EVEZ"""
from functools import wraps

class Step:
    def __init__(self, func):
        self.func = func
        self.name = func.__name__

class Task:
    def __init__(self, name, steps=None):
        self.name = name
        self.steps = steps or []
        
    def add_step(self, step):
        self.steps.append(step)
        
    def to_dict(self):
        return {
            "task_name": self.name,
            "steps": [s.name for s in self.steps]
        }

def step(func):
    """Decorator to mark a function as a task step"""
    return Step(func)
