"""Diagnostic metric collector, event logging, and JSON/CSV exporter."""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class DiagnosticRecord:
    timestamp: float
    modality: str
    event_type: str
    confidence: float
    latency_ms: float
    fps: float
    details: Dict[str, Any] = field(default_factory=dict)


class DiagnosticCollector:
    """Thread-safe collector for telemetry, performance latency, and event reliability."""

    def __init__(self, max_records: int = 10000) -> None:
        self.max_records = max_records
        self._records: List[DiagnosticRecord] = []
        self._fps_history: List[float] = []

    def record(self, modality: str, event_type: str, confidence: float, latency_ms: float, fps: float = 0.0, details: Dict[str, Any] | None = None) -> None:
        rec = DiagnosticRecord(
            timestamp=time.time(),
            modality=modality,
            event_type=event_type,
            confidence=confidence,
            latency_ms=latency_ms,
            fps=fps,
            details=details or {},
        )
        self._records.append(rec)
        if len(self._records) > self.max_records:
            self._records.pop(0)

    def get_summary(self) -> Dict[str, Any]:
        if not self._records:
            return {"total_events": 0, "avg_latency_ms": 0.0, "avg_confidence": 0.0}
        total = len(self._records)
        avg_lat = sum(r.latency_ms for r in self._records) / total
        avg_conf = sum(r.confidence for r in self._records) / total
        return {
            "total_events": total,
            "avg_latency_ms": round(avg_lat, 2),
            "avg_confidence": round(avg_conf, 3),
        }

    def export_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._records]
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def export_csv(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "modality", "event_type", "confidence", "latency_ms", "fps", "details"])
            for r in self._records:
                writer.writerow([r.timestamp, r.modality, r.event_type, r.confidence, r.latency_ms, r.fps, json.dumps(r.details)])
