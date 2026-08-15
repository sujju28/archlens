"""Detect Kafka / RabbitMQ / SQS event producers and consumers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from archlens.config import ArchLensConfig
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot
from archlens.scanner import collect_files

# Patterns: (regex, role, technology, topic_group)
EVENT_PATTERNS: list[tuple[re.Pattern[str], str, str, int]] = [
    # Kafka
    (re.compile(r"KafkaTemplate\s*<[^>]*>\s*\w+|kafkaTemplate\.send\s*\(\s*[\"']([^\"']+)[\"']", re.I), "producer", "Kafka", 1),
    (re.compile(r"@KafkaListener\s*\([^)]*topics\s*=\s*[\"']([^\"']+)[\"']", re.I), "consumer", "Kafka", 1),
    (re.compile(r"@KafkaListener\s*\([^)]*topics\s*=\s*\{?\s*[\"']([^\"']+)[\"']", re.I), "consumer", "Kafka", 1),
    (re.compile(r"consumer\.subscribe\s*\(\s*\[[\"']([^\"']+)[\"']", re.I), "consumer", "Kafka", 1),
    (re.compile(r"producer\.send\s*\(\s*[\"']([^\"']+)[\"']", re.I), "producer", "Kafka", 1),
    (re.compile(r"aiokafka|AIOKafkaProducer|KafkaProducer", re.I), "producer", "Kafka", 0),
    (re.compile(r"AIOKafkaConsumer|KafkaConsumer", re.I), "consumer", "Kafka", 0),
    # RabbitMQ
    (re.compile(r"@RabbitListener\s*\([^)]*queues\s*=\s*[\"']([^\"']+)[\"']", re.I), "consumer", "RabbitMQ", 1),
    (re.compile(r"rabbitTemplate\.convertAndSend\s*\(\s*[\"']([^\"']+)[\"']", re.I), "producer", "RabbitMQ", 1),
    (re.compile(r"channel\.basic_publish\s*\([^)]*routing_key\s*=\s*[\"']([^\"']+)[\"']", re.I), "producer", "RabbitMQ", 1),
    (re.compile(r"aio_pika|pika\.BlockingConnection", re.I), "producer", "RabbitMQ", 0),
    # SQS
    (re.compile(r"send_message\s*\([^)]*QueueUrl\s*=\s*[\"']([^\"']+)[\"']", re.I), "producer", "SQS", 1),
    (re.compile(r"receive_message\s*\([^)]*QueueUrl\s*=\s*[\"']([^\"']+)[\"']", re.I), "consumer", "SQS", 1),
    (re.compile(r"@SqsListener\s*\(\s*[\"']([^\"']+)[\"']", re.I), "consumer", "SQS", 1),
    (re.compile(r"boto3\.client\s*\(\s*[\"']sqs[\"']", re.I), "producer", "SQS", 0),
    # NestJS / TS
    (re.compile(r"@EventPattern\s*\(\s*[\"']([^\"']+)[\"']", re.I), "consumer", "Kafka", 1),
    (re.compile(r"@MessagePattern\s*\(\s*[\"']([^\"']+)[\"']", re.I), "consumer", "NATS/RMQ", 1),
    (re.compile(r"client\.emit\s*\(\s*[\"']([^\"']+)[\"']", re.I), "producer", "Kafka", 1),
]


@dataclass
class EventEndpoint:
    role: str  # producer | consumer
    technology: str
    topic: str
    file_path: str
    element_id: str | None = None
    element_name: str | None = None


@dataclass
class EventFlowReport:
    endpoints: list[EventEndpoint] = field(default_factory=list)
    topics: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    relationships: list[ArchRelationship] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "endpoint_count": len(self.endpoints),
            "topics": self.topics,
            "endpoints": [
                {
                    "role": e.role,
                    "technology": e.technology,
                    "topic": e.topic,
                    "file_path": e.file_path,
                    "element_id": e.element_id,
                    "element_name": e.element_name,
                }
                for e in self.endpoints
            ],
            "relationships": [r.model_dump() for r in self.relationships],
        }


class EventFlowTracer:
    def __init__(self, config: ArchLensConfig | None = None):
        self.config = config or ArchLensConfig()

    def scan_repo(
        self,
        repo_path: Path | str,
        snapshot: ArchSnapshot | None = None,
    ) -> EventFlowReport:
        repo = Path(repo_path)
        files = collect_files(repo, self.config)
        endpoints: list[EventEndpoint] = []

        by_file: dict[str, list[ArchElement]] = {}
        if snapshot:
            for el in snapshot.elements:
                by_file.setdefault(el.file_path.replace("\\", "/"), []).append(el)

        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(fp.relative_to(repo)).replace("\\", "/") if fp.is_relative_to(repo) else str(fp)
            for pattern, role, tech, group in EVENT_PATTERNS:
                for match in pattern.finditer(text):
                    topic = match.group(group) if group and match.lastindex and match.lastindex >= group else f"{tech}-unknown"
                    if not topic or topic == tech:
                        topic = f"{tech}-default"
                    el = None
                    for candidate in by_file.get(rel, []):
                        el = candidate
                        break
                    endpoints.append(
                        EventEndpoint(
                            role=role,
                            technology=tech,
                            topic=topic,
                            file_path=rel,
                            element_id=el.id if el else None,
                            element_name=el.name if el else Path(rel).stem,
                        )
                    )

        return self._build_report(endpoints)

    def link_across_snapshots(self, reports: list[EventFlowReport]) -> EventFlowReport:
        """Merge event reports and create producer→consumer edges by topic."""
        merged = EventFlowReport()
        for r in reports:
            merged.endpoints.extend(r.endpoints)
        return self._build_report(merged.endpoints)

    def _build_report(self, endpoints: list[EventEndpoint]) -> EventFlowReport:
        # Dedupe
        seen: set[tuple] = set()
        unique: list[EventEndpoint] = []
        for e in endpoints:
            key = (e.role, e.technology, e.topic, e.file_path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)

        topics: dict[str, dict[str, list[str]]] = {}
        for e in unique:
            bucket = topics.setdefault(e.topic, {"producers": [], "consumers": [], "technology": e.technology})
            label = e.element_name or e.file_path
            if e.role == "producer" and label not in bucket["producers"]:
                bucket["producers"].append(label)
            if e.role == "consumer" and label not in bucket["consumers"]:
                bucket["consumers"].append(label)

        relationships: list[ArchRelationship] = []
        producers = [e for e in unique if e.role == "producer"]
        consumers = [e for e in unique if e.role == "consumer"]
        for p in producers:
            for c in consumers:
                if p.topic == c.topic and p.file_path != c.file_path:
                    src = p.element_id or f"event-producer:{p.file_path}"
                    tgt = c.element_id or f"event-consumer:{c.file_path}"
                    relationships.append(
                        ArchRelationship(
                            source_id=src,
                            target_id=tgt,
                            rel_type="publishes_to",
                            description=f"{p.topic} ({p.technology})",
                            technology=p.technology,
                        )
                    )

        return EventFlowReport(endpoints=unique, topics=topics, relationships=relationships)
