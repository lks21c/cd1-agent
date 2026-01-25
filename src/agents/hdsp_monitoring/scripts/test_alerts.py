#!/usr/bin/env python3
"""
Test Alerts Script for HDSP Monitoring.

Manual testing utility for alert processing and notification.
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))))

# Set mock mode by default for testing
os.environ.setdefault("PROMETHEUS_MOCK", "true")
os.environ.setdefault("NOTIFICATION_MOCK", "true")
os.environ.setdefault("KAKAO_ENABLED", "false")


def test_basic_flow():
    """Test basic alert processing flow."""
    print("=" * 60)
    print("Test 1: Basic Alert Processing Flow")
    print("=" * 60)

    from src.agents.hdsp_monitoring.handler import handler

    event = {
        "publish_notifications": False,
        "min_severity": "medium",
    }

    result = handler(event, None)
    body = json.loads(result["body"]) if isinstance(result.get("body"), str) else result

    print(f"Status: {result.get('statusCode', 'N/A')}")
    print(f"Alerts fetched: {body.get('data', {}).get('alerts_fetched', 0)}")
    print(f"Alerts processed: {body.get('data', {}).get('alerts_processed', 0)}")
    print(f"Summary: {body.get('data', {}).get('summary', 'N/A')}")
    print()


def test_severity_mapping():
    """Test severity mapping."""
    print("=" * 60)
    print("Test 2: Severity Mapping")
    print("=" * 60)

    from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
        SeverityMapper,
    )
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
        PrometheusAlert,
        AlertStatus,
    )

    mapper = SeverityMapper()

    test_alerts = [
        ("KubePodCrashLooping", "critical", "CRITICAL"),
        ("KubeContainerOOMKilled", "error", "CRITICAL"),
        ("KubeNodeMemoryPressure", "warning", "HIGH"),
        ("KubeQuotaAlmostFull", "info", "MEDIUM"),
        ("CustomAlert", "warning", "HIGH"),  # Label-based
        ("SomethingDown", "warning", "CRITICAL"),  # Keyword-based
    ]

    for alert_name, label_severity, expected in test_alerts:
        alert = PrometheusAlert(
            alert_name=alert_name,
            status=AlertStatus.FIRING,
            labels={"alertname": alert_name, "severity": label_severity},
            annotations={},
        )
        result = mapper.map_severity(alert)
        status = "PASS" if result.value.upper() == expected else "FAIL"
        print(f"  [{status}] {alert_name} (label={label_severity}) -> {result.value.upper()} (expected={expected})")
    print()


def test_summary_generation():
    """Test Korean summary generation."""
    print("=" * 60)
    print("Test 3: Korean Summary Generation")
    print("=" * 60)

    from src.agents.hdsp_monitoring.hdsp_monitoring.services.summary_generator import (
        AlertSummaryGenerator,
    )
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
        ProcessedAlert,
        AlertSeverity,
    )
    from datetime import datetime, timedelta

    generator = AlertSummaryGenerator()

    alert = ProcessedAlert(
        fingerprint="abc123",
        alert_name="KubePodCrashLooping",
        severity=AlertSeverity.CRITICAL,
        namespace="spark",
        resource_type="Pod",
        resource_name="spark-executor-abc123",
        cluster_name="on-prem-k8s",
        summary="Pod spark/spark-executor-abc123 is crash looping",
        description="Pod has restarted 5 times in the last 10 minutes",
        first_seen=datetime.utcnow() - timedelta(minutes=25),
    )

    summary = generator.generate(alert)

    print(f"Title: {summary.title}")
    print(f"Message:\n{summary.message}")
    print()


def test_notification_routing():
    """Test notification routing."""
    print("=" * 60)
    print("Test 4: Notification Routing")
    print("=" * 60)

    from src.agents.hdsp_monitoring.hdsp_monitoring.services.notification_router import (
        NotificationRouter,
    )
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
        ProcessedAlert,
        AlertSeverity,
    )
    from datetime import datetime

    router = NotificationRouter(use_mock=True)

    # Create test alerts
    alerts = [
        ProcessedAlert(
            fingerprint="critical1",
            alert_name="KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            namespace="spark",
            resource_type="Pod",
            resource_name="spark-executor-1",
            cluster_name="on-prem-k8s",
            summary="Critical alert",
            description="",
            first_seen=datetime.utcnow(),
        ),
        ProcessedAlert(
            fingerprint="high1",
            alert_name="KubeNodeMemoryPressure",
            severity=AlertSeverity.HIGH,
            namespace="kube-system",
            resource_type="Node",
            resource_name="worker-1",
            cluster_name="on-prem-k8s",
            summary="High alert",
            description="",
            first_seen=datetime.utcnow(),
        ),
        ProcessedAlert(
            fingerprint="medium1",
            alert_name="KubeQuotaAlmostFull",
            severity=AlertSeverity.MEDIUM,
            namespace="default",
            resource_type="Namespace",
            resource_name="default",
            cluster_name="on-prem-k8s",
            summary="Medium alert",
            description="",
            first_seen=datetime.utcnow(),
        ),
    ]

    results = router.route_alerts(alerts)

    print(f"Routing results:")
    for r in results:
        print(f"  - Channel: {r.channel}, Success: {r.success}, Count: {r.alert_count}")
    print()


def test_full_handler():
    """Test full handler with notifications."""
    print("=" * 60)
    print("Test 5: Full Handler with Mock Notifications")
    print("=" * 60)

    from src.agents.hdsp_monitoring.handler import handler

    event = {
        "publish_notifications": True,
        "min_severity": "medium",
        "group_alerts": True,
    }

    result = handler(event, None)
    body = json.loads(result["body"]) if isinstance(result.get("body"), str) else result
    data = body.get("data", {})

    print(f"Alerts processed: {data.get('alerts_processed', 0)}")
    print(f"Alerts notified: {data.get('alerts_notified', 0)}")
    print(f"Severity breakdown: {data.get('severity_breakdown', {})}")
    print(f"Notification results:")
    for nr in data.get("notification_results", []):
        print(f"  - {nr.get('channel')}: success={nr.get('success')}, count={nr.get('alert_count')}")
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("HDSP Monitoring Test Suite")
    print("=" * 60 + "\n")

    test_basic_flow()
    test_severity_mapping()
    test_summary_generation()
    test_notification_routing()
    test_full_handler()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
