"""
HDSP Anomaly Detector for On-Prem K8s Monitoring.

Detects Kubernetes cluster anomalies including:
- Pod failures (CrashLoopBackOff, OOMKilled, excessive restarts)
- Node pressure (MemoryPressure, DiskPressure, NotReady)
- Resource anomalies (high CPU/Memory usage)
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.agents.hdsp.services.prometheus_client import PrometheusClient, PrometheusQueryResult

logger = logging.getLogger(__name__)


class HDSPAnomalyType(str, Enum):
    """Types of K8s anomalies detected by HDSP Agent."""

    POD_FAILURE = "pod_failure"
    NODE_PRESSURE = "node_pressure"
    RESOURCE_ANOMALY = "resource_anomaly"
    POD_RESTART = "pod_restart"
    OOM_KILLED = "oom_killed"
    CRASH_LOOP = "crash_loop"


class HDSPSeverity(str, Enum):
    """Severity levels for HDSP anomalies."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class HDSPAnomaly:
    """Single HDSP anomaly detection result."""

    anomaly_type: HDSPAnomalyType
    severity: HDSPSeverity
    namespace: str
    resource_name: str  # Pod name or Node name
    resource_type: str  # "pod" or "node"
    message: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "namespace": self.namespace,
            "resource_name": self.resource_name,
            "resource_type": self.resource_type,
            "message": self.message,
            "metrics": self.metrics,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


@dataclass
class HDSPDetectionResult:
    """Complete HDSP detection result with all anomalies."""

    anomalies: List[HDSPAnomaly]
    total_anomalies: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    detection_timestamp: str
    cluster_name: str
    namespaces_checked: List[str]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "anomalies": [a.to_dict() for a in self.anomalies],
            "total_anomalies": self.total_anomalies,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "detection_timestamp": self.detection_timestamp,
            "cluster_name": self.cluster_name,
            "namespaces_checked": self.namespaces_checked,
            "summary": self.summary,
        }

    @property
    def has_critical(self) -> bool:
        """Check if any critical anomalies exist."""
        return self.critical_count > 0

    @property
    def has_anomalies(self) -> bool:
        """Check if any anomalies were detected."""
        return self.total_anomalies > 0


class HDSPAnomalyDetector:
    """
    HDSP Anomaly Detector for On-Prem Kubernetes clusters.

    Detects and classifies K8s anomalies using Prometheus metrics.

    Usage:
        detector = HDSPAnomalyDetector()
        result = detector.detect_all()

        # Or detect specific anomaly types
        pod_anomalies = detector.detect_pod_failures()
        node_anomalies = detector.detect_node_pressure()
        resource_anomalies = detector.detect_resource_anomalies()

    Configuration via environment variables:
        HDSP_NAMESPACES: Comma-separated list of namespaces to monitor
        HDSP_EXCLUDE_PODS: Regex pattern for pods to exclude
        RESTART_THRESHOLD: Number of restarts to trigger anomaly (default: 3)
        CPU_THRESHOLD: CPU usage percentage threshold (default: 90)
        MEMORY_THRESHOLD: Memory usage percentage threshold (default: 85)
    """

    def __init__(
        self,
        prometheus_client: Optional[PrometheusClient] = None,
        namespaces: Optional[List[str]] = None,
        restart_threshold: Optional[int] = None,
        cpu_threshold: Optional[float] = None,
        memory_threshold: Optional[float] = None,
        cluster_name: Optional[str] = None,
    ):
        """
        Initialize HDSP Anomaly Detector.

        Args:
            prometheus_client: Prometheus client instance (auto-created if None)
            namespaces: List of namespaces to monitor (from env if None)
            restart_threshold: Pod restart count threshold
            cpu_threshold: CPU usage percentage threshold
            memory_threshold: Memory usage percentage threshold
            cluster_name: Cluster identifier
        """
        self.client = prometheus_client or PrometheusClient()

        # Configuration from environment or parameters
        default_namespaces = os.environ.get("HDSP_NAMESPACES", "default,hdsp,spark")
        self.namespaces = namespaces or default_namespaces.split(",")

        self.restart_threshold = restart_threshold or int(
            os.environ.get("RESTART_THRESHOLD", "3")
        )
        self.cpu_threshold = cpu_threshold or float(
            os.environ.get("CPU_THRESHOLD", "90")
        )
        self.memory_threshold = memory_threshold or float(
            os.environ.get("MEMORY_THRESHOLD", "85")
        )
        self.cluster_name = cluster_name or os.environ.get(
            "HDSP_CLUSTER_NAME", "on-prem-k8s"
        )

        self.exclude_pods_pattern = os.environ.get("HDSP_EXCLUDE_PODS", "")

    def detect_all(self) -> HDSPDetectionResult:
        """
        Run all detection methods and return combined results.

        Returns:
            HDSPDetectionResult with all detected anomalies
        """
        all_anomalies: List[HDSPAnomaly] = []

        # Run all detection methods
        try:
            all_anomalies.extend(self.detect_pod_failures())
        except Exception as e:
            logger.error(f"Pod failure detection failed: {e}")

        try:
            all_anomalies.extend(self.detect_node_pressure())
        except Exception as e:
            logger.error(f"Node pressure detection failed: {e}")

        try:
            all_anomalies.extend(self.detect_resource_anomalies())
        except Exception as e:
            logger.error(f"Resource anomaly detection failed: {e}")

        # Calculate severity counts
        critical_count = sum(
            1 for a in all_anomalies if a.severity == HDSPSeverity.CRITICAL
        )
        high_count = sum(1 for a in all_anomalies if a.severity == HDSPSeverity.HIGH)
        medium_count = sum(
            1 for a in all_anomalies if a.severity == HDSPSeverity.MEDIUM
        )
        low_count = sum(1 for a in all_anomalies if a.severity == HDSPSeverity.LOW)

        # Generate summary
        summary = self._generate_summary(
            all_anomalies, critical_count, high_count, medium_count, low_count
        )

        return HDSPDetectionResult(
            anomalies=all_anomalies,
            total_anomalies=len(all_anomalies),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            detection_timestamp=datetime.utcnow().isoformat(),
            cluster_name=self.cluster_name,
            namespaces_checked=self.namespaces,
            summary=summary,
        )

    def detect_pod_failures(self) -> List[HDSPAnomaly]:
        """
        Detect pod failure anomalies.

        Detects:
        - CrashLoopBackOff pods
        - OOMKilled pods
        - Pods with excessive restarts

        Returns:
            List of HDSPAnomaly for pod failures
        """
        anomalies: List[HDSPAnomaly] = []

        # Detect CrashLoopBackOff across all namespaces
        crash_loop_pods: List = []
        for ns in self.namespaces:
            crash_loop_pods.extend(self.client.get_crash_loop_pods(namespace=ns))
        for result in crash_loop_pods:
            if self._should_exclude_pod(result.labels.get("pod", "")):
                continue

            anomalies.append(
                HDSPAnomaly(
                    anomaly_type=HDSPAnomalyType.CRASH_LOOP,
                    severity=HDSPSeverity.CRITICAL,
                    namespace=result.labels.get("namespace", "unknown"),
                    resource_name=result.labels.get("pod", "unknown"),
                    resource_type="pod",
                    message=f"Pod in CrashLoopBackOff state",
                    metrics={"crash_loop_status": 1},
                    labels=result.labels,
                )
            )

        # Detect OOMKilled across all namespaces
        oom_pods: List = []
        for ns in self.namespaces:
            oom_pods.extend(self.client.get_oom_killed_pods(namespace=ns))
        for result in oom_pods:
            if self._should_exclude_pod(result.labels.get("pod", "")):
                continue

            anomalies.append(
                HDSPAnomaly(
                    anomaly_type=HDSPAnomalyType.OOM_KILLED,
                    severity=HDSPSeverity.CRITICAL,
                    namespace=result.labels.get("namespace", "unknown"),
                    resource_name=result.labels.get("pod", "unknown"),
                    resource_type="pod",
                    message=f"Pod terminated due to OOMKilled",
                    metrics={"oom_killed": 1},
                    labels=result.labels,
                )
            )

        # Detect excessive restarts across all namespaces
        restart_results: List = []
        for ns in self.namespaces:
            restart_results.extend(self.client.get_pod_restarts(namespace=ns))

        # Filter by threshold
        restart_results = [r for r in restart_results if (r.latest_value or 0) >= self.restart_threshold]
        for result in restart_results:
            if self._should_exclude_pod(result.labels.get("pod", "")):
                continue

            restart_count = result.latest_value or 0
            # Skip if already detected as crash loop or OOM
            pod_name = result.labels.get("pod", "")
            if any(
                a.resource_name == pod_name
                and a.anomaly_type
                in (HDSPAnomalyType.CRASH_LOOP, HDSPAnomalyType.OOM_KILLED)
                for a in anomalies
            ):
                continue

            severity = self._calculate_restart_severity(int(restart_count))
            anomalies.append(
                HDSPAnomaly(
                    anomaly_type=HDSPAnomalyType.POD_RESTART,
                    severity=severity,
                    namespace=result.labels.get("namespace", "unknown"),
                    resource_name=pod_name,
                    resource_type="pod",
                    message=f"Pod has {int(restart_count)} restarts (threshold: {self.restart_threshold})",
                    metrics={"restart_count": restart_count},
                    labels=result.labels,
                )
            )

        return anomalies

    def detect_node_pressure(self) -> List[HDSPAnomaly]:
        """
        Detect node pressure anomalies.

        Detects:
        - MemoryPressure condition
        - DiskPressure condition
        - PIDPressure condition
        - NotReady nodes

        Returns:
            List of HDSPAnomaly for node pressure issues
        """
        anomalies: List[HDSPAnomaly] = []

        node_conditions = self.client.get_node_conditions()

        for result in node_conditions:
            condition = result.labels.get("condition", "")
            node = result.labels.get("node", "unknown")
            status = result.labels.get("status", "")

            # Skip healthy conditions
            if condition == "Ready" and status == "true":
                continue
            if condition != "Ready" and status != "true":
                continue

            # Determine severity and anomaly type
            if condition == "Ready" and status != "true":
                severity = HDSPSeverity.CRITICAL
                message = f"Node is NotReady"
            elif condition == "MemoryPressure":
                severity = HDSPSeverity.HIGH
                message = f"Node has MemoryPressure"
            elif condition == "DiskPressure":
                severity = HDSPSeverity.HIGH
                message = f"Node has DiskPressure"
            elif condition == "PIDPressure":
                severity = HDSPSeverity.MEDIUM
                message = f"Node has PIDPressure"
            else:
                severity = HDSPSeverity.MEDIUM
                message = f"Node has {condition} condition"

            anomalies.append(
                HDSPAnomaly(
                    anomaly_type=HDSPAnomalyType.NODE_PRESSURE,
                    severity=severity,
                    namespace="cluster",
                    resource_name=node,
                    resource_type="node",
                    message=message,
                    metrics={"condition": condition, "status": status},
                    labels=result.labels,
                )
            )

        return anomalies

    def detect_resource_anomalies(self) -> List[HDSPAnomaly]:
        """
        Detect resource usage anomalies.

        Detects:
        - High CPU usage (> threshold)
        - High Memory usage (> threshold)

        Returns:
            List of HDSPAnomaly for resource anomalies
        """
        anomalies: List[HDSPAnomaly] = []

        # Detect high CPU usage across all namespaces
        high_cpu_pods: List = []
        for ns in self.namespaces:
            high_cpu_pods.extend(
                self.client.get_high_cpu_pods(namespace=ns, threshold=self.cpu_threshold / 100)
            )
        for result in high_cpu_pods:
            if self._should_exclude_pod(result.labels.get("pod", "")):
                continue

            cpu_usage = (result.latest_value or 0) * 100
            severity = self._calculate_resource_severity(cpu_usage, self.cpu_threshold)

            anomalies.append(
                HDSPAnomaly(
                    anomaly_type=HDSPAnomalyType.RESOURCE_ANOMALY,
                    severity=severity,
                    namespace=result.labels.get("namespace", "unknown"),
                    resource_name=result.labels.get("pod", "unknown"),
                    resource_type="pod",
                    message=f"High CPU usage: {cpu_usage:.1f}% (threshold: {self.cpu_threshold}%)",
                    metrics={"cpu_usage_percent": cpu_usage, "threshold": self.cpu_threshold},
                    labels=result.labels,
                )
            )

        # Detect high Memory usage across all namespaces
        high_mem_pods: List = []
        for ns in self.namespaces:
            high_mem_pods.extend(
                self.client.get_high_memory_pods(namespace=ns, threshold=self.memory_threshold / 100)
            )
        for result in high_mem_pods:
            if self._should_exclude_pod(result.labels.get("pod", "")):
                continue

            mem_usage = (result.latest_value or 0) * 100
            severity = self._calculate_resource_severity(mem_usage, self.memory_threshold)

            # Skip if already detected for CPU
            pod_name = result.labels.get("pod", "")
            existing = next(
                (
                    a
                    for a in anomalies
                    if a.resource_name == pod_name
                    and a.anomaly_type == HDSPAnomalyType.RESOURCE_ANOMALY
                ),
                None,
            )

            if existing:
                # Update existing anomaly to include memory info
                existing.metrics["memory_usage_percent"] = mem_usage
                existing.metrics["memory_threshold"] = self.memory_threshold
                existing.message += f", Memory: {mem_usage:.1f}%"
                # Upgrade severity if memory is worse
                if severity.value < existing.severity.value:
                    existing.severity = severity
            else:
                anomalies.append(
                    HDSPAnomaly(
                        anomaly_type=HDSPAnomalyType.RESOURCE_ANOMALY,
                        severity=severity,
                        namespace=result.labels.get("namespace", "unknown"),
                        resource_name=pod_name,
                        resource_type="pod",
                        message=f"High Memory usage: {mem_usage:.1f}% (threshold: {self.memory_threshold}%)",
                        metrics={
                            "memory_usage_percent": mem_usage,
                            "threshold": self.memory_threshold,
                        },
                        labels=result.labels,
                    )
                )

        return anomalies

    def _should_exclude_pod(self, pod_name: str) -> bool:
        """Check if pod should be excluded from detection."""
        if not self.exclude_pods_pattern or not pod_name:
            return False

        import re

        try:
            return bool(re.match(self.exclude_pods_pattern, pod_name))
        except re.error:
            logger.warning(f"Invalid exclude pattern: {self.exclude_pods_pattern}")
            return False

    def _calculate_restart_severity(self, restart_count: int) -> HDSPSeverity:
        """Calculate severity based on restart count."""
        if restart_count >= 10:
            return HDSPSeverity.CRITICAL
        elif restart_count >= 5:
            return HDSPSeverity.HIGH
        elif restart_count >= self.restart_threshold:
            return HDSPSeverity.MEDIUM
        return HDSPSeverity.LOW

    def _calculate_resource_severity(
        self, usage: float, threshold: float
    ) -> HDSPSeverity:
        """Calculate severity based on resource usage."""
        if usage >= 95:
            return HDSPSeverity.CRITICAL
        elif usage >= threshold + 5:
            return HDSPSeverity.HIGH
        elif usage >= threshold:
            return HDSPSeverity.MEDIUM
        return HDSPSeverity.LOW

    def _generate_summary(
        self,
        anomalies: List[HDSPAnomaly],
        critical: int,
        high: int,
        medium: int,
        low: int,
    ) -> str:
        """Generate human-readable summary of detection results."""
        if not anomalies:
            return f"No anomalies detected in cluster '{self.cluster_name}' across namespaces: {', '.join(self.namespaces)}"

        parts = []
        if critical > 0:
            parts.append(f"{critical} CRITICAL")
        if high > 0:
            parts.append(f"{high} HIGH")
        if medium > 0:
            parts.append(f"{medium} MEDIUM")
        if low > 0:
            parts.append(f"{low} LOW")

        severity_summary = ", ".join(parts)

        # Group by anomaly type
        type_counts: Dict[str, int] = {}
        for a in anomalies:
            type_name = a.anomaly_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        type_summary = ", ".join(f"{count} {t}" for t, count in type_counts.items())

        return (
            f"Detected {len(anomalies)} anomalies in cluster '{self.cluster_name}': "
            f"[{severity_summary}]. Types: {type_summary}."
        )
