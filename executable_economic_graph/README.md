# Executable Economic Graph Prototype

Run a local executable version of the recursive economic graph.

## Start server
```bash
python app.py
```

## Simulate events
```bash
python app.py --simulate
```

## Ingest an event
```bash
curl -X POST http://localhost:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": "test-1",
    "tenant_id": "default",
    "payload": {
      "value": 1000,
      "cost_budget": 200,
      "probability_success": 0.82,
      "roi_target": 1.5
    }
  }'
```

## Inspect state
```bash
curl http://localhost:8000/state
curl http://localhost:8000/graph
```
