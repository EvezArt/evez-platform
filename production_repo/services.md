# PRODUCTION REPO STRUCTURE
# Full microservice architecture for Economic Graph Platform

## Directory Tree
kiloclaw/
├── services/
│   ├── ingestor/
│   │   └── main.py
│   ├── qualifier/
│   │   └── main.py
│   ├── gpu_router/
│   │   ├── router.py
│   │   └── models.py
│   ├── inference_worker/
│   │   └── vllm_server.py
│   ├── closer/
│   │   └── main.py
│   ├── pricing_engine/
│   │   └── main.py
│   ├── product_engine/
│   │   └── generator.py
│   ├── composio_executor/
│   │   └── executor.py
│   ├── observability/
│   │   ├── traces.py
│   │   ├── metrics.py
│   │   └── logger.py
│   └── learning/
│       └── optimizer.py
│
├── common/
│   ├── event_bus.py
│   ├── schemas.py
│   ├── retry.py
│   └── tenant.py
│
├── schemas/
│   ├── lead.proto
│   ├── inference.proto
│   ├── action.proto
│   └── conversion.proto
│
├── infra/
│   ├── docker-compose.yml
│   ├── prometheus.yml
│   ├── grafana/
│   └── kafka/
│
├── helm/
│   └── kiloclaw/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
├── .github/
│   └── workflows/
│       └── deploy.yml
│
├── tests/
│   ├── test_scoring.py
│   ├── test_routing.py
│   └── test_events.py
│
├── Dockerfile
├── requirements.txt
└── README.md

---

## 1. COMMON - SHARED EVENT BUS

common/event_bus.py:
"""Kafka event bus wrapper"""
from kafka import KafkaProducer, KafkaConsumer
import json
import os
from typing import Dict, Any, Optional

BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")

class EventBus:
    def __init__(self, broker: str = BROKER):
        self.broker = broker
        self.producer: Optional[KafkaProducer] = None
        
    def get_producer(self) -> KafkaProducer:
        if not self.producer:
            self.producer = KafkaProducer(
                bootstrap_servers=self.broker,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )
        return self.producer
    
    def publish(self, topic: str, event: Dict[str, Any], key: Optional[str] = None):
        self.get_producer().send(topic, value=event, key=key)
        self.get_producer().flush()
        
    def consume(self, topic: str, group_id: str) -> KafkaConsumer:
        return KafkaConsumer(
            topic,
            bootstrap_servers=self.broker,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )

# Topic definitions
TOPICS = {
    "lead.ingest": "lead.ingest",
    "lead.scored": "lead.scored",
    "inference.request": "inference.request",
    "inference.response": "inference.response",
    "action.tool.request": "action.tool.request",
    "action.tool.result": "action.tool.result",
    "payment.created": "payment.created",
    "payment.confirmed": "payment.confirmed",
    "fulfillment.started": "fulfillment.started",
    "fulfillment.completed": "fulfillment.completed",
    "telemetry.raw": "telemetry.raw",
    "telemetry.featured": "telemetry.featured",
    "anomaly.detected": "anomaly.detected",
    "product.opportunity": "product.opportunity",
    "product.spec.created": "product.spec.created",
    "pricing.updated": "pricing.updated"
}