#!/usr/bin/env python3
"""
Test script for HDSP Alert Monitoring HTML Report.

Generate mock alert data and open report in Chrome.
"""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    ProcessedAlert,
    AlertSeverity,
    AlertStatus,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.html_report_generator import (
    AlertHTMLReportGenerator,
)


def create_mock_alerts() -> list[ProcessedAlert]:
    """Create mock alerts for testing.

    V2 Changes:
    - Pod Level / Node Level 분리
    - Node alerts have 'node_group' label for grouping
    - Multi-day alerts for date+time format testing
    - Severity-based sorting within groups
    """
    now = datetime.utcnow()

    alerts = [
        # ═══════════════════════════════════════════════════════════════
        # NODE LEVEL ALERTS (resource_type="Node")
        # Grouped by node_group label
        # ═══════════════════════════════════════════════════════════════

        # --- worker-group ---
        ProcessedAlert(
            fingerprint="node123fail",
            alert_name="KubeNodeNotReady",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.FIRING,
            namespace="kube-system",
            resource_type="Node",
            resource_name="worker-node-03",
            cluster_name="hdsp-prod-01",
            summary="노드 준비 안됨",
            description="노드 worker-node-03이 15분 이상 NotReady 상태입니다.",
            first_seen=now - timedelta(minutes=25),
            last_seen=now,
            occurrence_count=8,
            labels={"node": "worker-node-03", "node_group": "worker-group"},
        ),
        ProcessedAlert(
            fingerprint="mem456high",
            alert_name="KubeNodeMemoryPressure",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.FIRING,
            namespace="kube-system",
            resource_type="Node",
            resource_name="worker-node-01",
            cluster_name="hdsp-prod-01",
            summary="노드 메모리 압박",
            description="노드 worker-node-01에 MemoryPressure 상태 발생. 가용 메모리: 512Mi.",
            first_seen=now - timedelta(minutes=55),
            last_seen=now,
            occurrence_count=18,
            labels={"node": "worker-node-01", "node_group": "worker-group"},
        ),
        ProcessedAlert(
            fingerprint="disk789pressure",
            alert_name="KubeNodeDiskPressure",
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.FIRING,
            namespace="kube-system",
            resource_type="Node",
            resource_name="worker-node-02",
            cluster_name="hdsp-prod-01",
            summary="노드 디스크 압박",
            description="노드 worker-node-02에 DiskPressure 상태 발생. 가용 디스크: 5%.",
            first_seen=now - timedelta(minutes=30),
            last_seen=now,
            occurrence_count=10,
            labels={"node": "worker-node-02", "node_group": "worker-group"},
        ),

        # --- infra-group ---
        ProcessedAlert(
            fingerprint="cpu567high",
            alert_name="KubeCPUOvercommit",
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.FIRING,
            namespace="kube-system",
            resource_type="Node",
            resource_name="infra-node-01",
            cluster_name="hdsp-prod-01",
            summary="클러스터 CPU 초과 할당",
            description="클러스터 CPU 리소스 요청량이 초과 할당됨. 초과 비율: 120%.",
            first_seen=now - timedelta(hours=36),  # 36시간 전 (날짜+시간 형식 테스트)
            last_seen=now,
            occurrence_count=30,
            labels={"node": "infra-node-01", "node_group": "infra-group"},
        ),

        # --- gpu-group ---
        ProcessedAlert(
            fingerprint="gpu001temp",
            alert_name="NodeGPUTemperatureHigh",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.FIRING,
            namespace="kube-system",
            resource_type="Node",
            resource_name="gpu-node-01",
            cluster_name="hdsp-prod-01",
            summary="GPU 온도 높음",
            description="gpu-node-01 GPU 온도 85°C, 임계값 80°C 초과.",
            first_seen=now - timedelta(minutes=15),
            last_seen=now,
            occurrence_count=5,
            labels={"node": "gpu-node-01", "node_group": "gpu-group"},
        ),

        # ═══════════════════════════════════════════════════════════════
        # POD LEVEL ALERTS (resource_type != "Node")
        # Grouped by namespace
        # ═══════════════════════════════════════════════════════════════

        # --- production namespace ---
        ProcessedAlert(
            fingerprint="xyz789ghi012",
            alert_name="KubePodOOMKilled",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.FIRING,
            namespace="production",
            resource_type="Pod",
            resource_name="ml-inference-5c7d8e9f0-p3q2r",
            cluster_name="hdsp-prod-01",
            summary="Pod OOM 종료됨",
            description="Pod production/ml-inference-5c7d8e9f0-p3q2r이 OOMKilled 되었습니다.",
            first_seen=now - timedelta(minutes=40),
            last_seen=now,
            occurrence_count=5,
            labels={"pod": "ml-inference-5c7d8e9f0-p3q2r", "container": "inference"},
        ),
        ProcessedAlert(
            fingerprint="abc123def456",
            alert_name="KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.FIRING,
            namespace="production",
            resource_type="Pod",
            resource_name="api-server-7d9f8b6c5-x2k4m",
            cluster_name="hdsp-prod-01",
            summary="Pod 크래시 루프 발생",
            description="Pod production/api-server-7d9f8b6c5-x2k4m이 CrashLoopBackOff 상태입니다.",
            first_seen=now - timedelta(minutes=35),
            last_seen=now,
            occurrence_count=15,
            labels={"pod": "api-server-7d9f8b6c5-x2k4m", "container": "api-server"},
        ),
        ProcessedAlert(
            fingerprint="hpa345scale",
            alert_name="KubeHpaMaxedOut",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.FIRING,
            namespace="production",
            resource_type="Deployment",
            resource_name="order-service",
            cluster_name="hdsp-prod-01",
            summary="HPA 최대 용량 도달",
            description="HPA production/order-service가 최대 레플리카(20개)로 운영 중입니다.",
            first_seen=now - timedelta(minutes=45),
            last_seen=now,
            occurrence_count=15,
            labels={"hpa": "order-service"},
        ),

        # --- staging namespace ---
        ProcessedAlert(
            fingerprint="deploy012avail",
            alert_name="KubeDeploymentReplicasMismatch",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.FIRING,
            namespace="staging",
            resource_type="Deployment",
            resource_name="web-frontend",
            cluster_name="hdsp-staging-01",
            summary="Deployment 레플리카 불일치",
            description="Deployment staging/web-frontend: 요청 5개, 현재 3개, 가용 2개.",
            first_seen=now - timedelta(minutes=18),
            last_seen=now,
            occurrence_count=6,
            labels={"deployment": "web-frontend"},
        ),
        ProcessedAlert(
            fingerprint="quota789staging",
            alert_name="KubeQuotaAlmostFull",
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.FIRING,
            namespace="staging",
            resource_type="Pod",
            resource_name="staging-quota",
            cluster_name="hdsp-staging-01",
            summary="리소스 쿼터 임계치 도달",
            description="네임스페이스 staging이 CPU 쿼터의 85%를 사용 중입니다.",
            first_seen=now - timedelta(hours=2),
            last_seen=now,
            occurrence_count=20,
            labels={"quota": "staging-quota"},
        ),

        # --- data-pipeline namespace ---
        ProcessedAlert(
            fingerprint="pvc789pending",
            alert_name="KubePersistentVolumeClaimPending",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.FIRING,
            namespace="data-pipeline",
            resource_type="PersistentVolumeClaim",
            resource_name="etl-data-pvc",
            cluster_name="hdsp-prod-01",
            summary="PVC 대기 상태",
            description="PVC data-pipeline/etl-data-pvc가 15분 이상 Pending 상태입니다.",
            first_seen=now - timedelta(minutes=22),
            last_seen=now,
            occurrence_count=8,
            labels={"persistentvolumeclaim": "etl-data-pvc"},
        ),

        # --- batch-jobs namespace ---
        ProcessedAlert(
            fingerprint="job678fail",
            alert_name="KubeJobFailed",
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.FIRING,
            namespace="batch-jobs",
            resource_type="Job",
            resource_name="nightly-etl-20250125",
            cluster_name="hdsp-prod-01",
            summary="Job 실패",
            description="Job batch-jobs/nightly-etl-20250125가 3회 시도 후 실패했습니다.",
            first_seen=now - timedelta(hours=26),  # 26시간 전 (날짜+시간 형식 테스트)
            last_seen=now,
            occurrence_count=3,
            labels={"job-name": "nightly-etl-20250125"},
        ),

        # --- cert-manager namespace ---
        ProcessedAlert(
            fingerprint="cert012expire",
            alert_name="CertificateExpiringSoon",
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.FIRING,
            namespace="cert-manager",
            resource_type="Service",
            resource_name="api.hdsp.example.com",
            cluster_name="hdsp-prod-01",
            summary="인증서 곧 만료",
            description="api.hdsp.example.com 인증서가 7일 후 만료됩니다.",
            first_seen=now - timedelta(days=2),  # 2일 전 (날짜+시간 형식 테스트)
            last_seen=now,
            occurrence_count=48,
            labels={"certificate": "api-hdsp-cert"},
        ),
    ]

    return alerts


def main():
    """Generate HTML report and open in Chrome."""
    print("🚀 HDSP Alert Monitoring Report Generator Test (V2)")
    print("=" * 60)

    # 1. Create mock alerts
    print("\n📦 Creating mock alerts...")
    alerts = create_mock_alerts()
    print(f"   Created {len(alerts)} mock alerts")

    # Pod/Node level 분류
    pod_alerts = [a for a in alerts if a.resource_type != "Node"]
    node_alerts = [a for a in alerts if a.resource_type == "Node"]

    print(f"\n📊 Level Classification:")
    print(f"   🐳 Pod Level: {len(pod_alerts)} alerts")
    namespaces = set(a.namespace for a in pod_alerts)
    for ns in sorted(namespaces):
        ns_count = sum(1 for a in pod_alerts if a.namespace == ns)
        print(f"      📁 {ns}: {ns_count}")

    print(f"   🖥️ Node Level: {len(node_alerts)} alerts")
    node_groups = set(a.labels.get("node_group", "unknown") for a in node_alerts)
    for ng in sorted(node_groups):
        ng_count = sum(1 for a in node_alerts if a.labels.get("node_group", "unknown") == ng)
        print(f"      🏷️ {ng}: {ng_count}")

    # Severity counts
    critical_count = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
    high_count = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
    medium_count = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
    print(f"\n⚠️ Severity Distribution:")
    print(f"   🚨 CRITICAL: {critical_count}")
    print(f"   ⚠️ HIGH: {high_count}")
    print(f"   📊 MEDIUM: {medium_count}")

    # 2. Generate report
    print("\n📝 Generating HTML report...")
    output_dir = project_root / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "hdsp_alert_report.html"

    generator = AlertHTMLReportGenerator()
    generator.generate_report(alerts, str(output_path))
    print(f"   Report saved to: {output_path}")

    # 3. Open in Chrome (macOS)
    print("\n🌐 Opening report in Chrome...")
    try:
        subprocess.run(
            ["open", "-a", "Google Chrome", str(output_path)],
            check=True,
        )
        print("   ✅ Report opened in Chrome")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to open Chrome: {e}")
        print(f"   📁 Please manually open: {output_path}")
    except FileNotFoundError:
        print("   ⚠️ 'open' command not available (non-macOS)")
        print(f"   📁 Please manually open: {output_path}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
