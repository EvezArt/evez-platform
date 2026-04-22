#!/usr/bin/env python3
"""EVEZ AUTONOMOUS AGENT"""
class Agent:
    def __init__(self):
        self.name = "EVEZ-Agent-1"
        self.tasks = 0
        
    def cycle(self, task):
        self.tasks += 1
        return {"agent": self.name, "task": task, "cycle": self.tasks}

if __name__ == "__main__":
    a = Agent()
    print(a.cycle("test"))
