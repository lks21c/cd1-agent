"""
HDSP Monitoring Handler.

Lambda/FastAPI handler for Prometheus Alertmanager-based monitoring.
Catches alerts by severity and sends KakaoTalk notifications.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.handlers.base_handler import BaseHandler

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    NotificationResult,
    ProcessedAlert,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.prometheus_alert_fetcher import (
    PrometheusAlertFetcher,
    create_alert_fetcher,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.alert_processor import (
    AlertProcessor,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.notification_router import (
    NotificationRouter,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.summary_generator import (
    AlertSummaryGenerator,
)


class HDSPMonitoringHandler(BaseHandler):
    """
    HDSP Monitoring Handler.

    Fetches alerts from Prometheus Alertmanager, processes them,
    and sends notifications via KakaoTalk and EventBridge.

    Features:
    - Prometheus Alertmanager integration
    - 3-tier severity classification (CRITICAL, HIGH, MEDIUM)
    - Korean language alert summaries
    - KakaoTalk notifications for CRITICAL/HIGH
    - EventBridge events for all severities
    - Alert deduplication and rate limiting
    """

    def __init__(self):
        super().__init__("HDSPMonitoringHandler")
        self._init_services()

    def _init_services(self) -> None:
        """Initialize service components."""
        # Alert fetcher (Alertmanager client)
        use_mock = os.environ.get("PROMETHEUS_MOCK", "").lower() == "true"
        alertmanager_url = os.environ.get("ALERTMANAGER_URL", "http://localhost:9093")
        self.alert_fetcher = create_alert_fetcher(
            alertmanager_url=alertmanager_url,
            use_mock=use_mock,
        )

        # Alert processor
        cluster_name = os.environ.get("HDSP_CLUSTER_NAME", "on-prem-k8s")
        include_ns = os.environ.get("HDSP_INCLUDE_NAMESPACES", "").split(",")
        include_ns = [ns.strip() for ns in include_ns if ns.strip()] or None
        exclude_ns = os.environ.get("HDSP_EXCLUDE_NAMESPACES", "test-*,dev-*").split(",")
        exclude_ns = [ns.strip() for ns in exclude_ns if ns.strip()]

        self.alert_processor = AlertProcessor(
            cluster_name=cluster_name,
            include_namespaces=include_ns,
            exclude_namespaces=exclude_ns,
        )

        # Summary generator
        self.summary_generator = AlertSummaryGenerator()

        # Notification router
        kakao_enabled = os.environ.get("KAKAO_ENABLED", "true").lower() == "true"
        notification_mock = os.environ.get("NOTIFICATION_MOCK", "").lower() == "true"
        self.notification_router = NotificationRouter(
            kakao_enabled=kakao_enabled,
            use_mock=notification_mock or use_mock,
        )

        self.logger.info(
            f"HDSPMonitoringHandler initialized: "
            f"alertmanager={alertmanager_url}, cluster={cluster_name}, "
            f"mock={use_mock}, kakao={kakao_enabled}"
        )

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate input event."""
        # All parameters are optional
        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process monitoring request.

        Args:
            event: Lambda event or API request
            context: Lambda context

        Returns:
            Processing result
        """
        body = self._parse_body(event)

        # Extract parameters
        publish_notifications = body.get(
            "publish_notifications",
            event.get("publish_notifications", True),
        )
        min_severity = body.get(
            "min_severity",
            event.get("min_severity", "medium"),
        )
        group_alerts = body.get(
            "group_alerts",
            event.get("group_alerts", True),
        )

        self.logger.info(
            f"HDSP Monitoring started: min_severity={min_severity}, "
            f"group={group_alerts}, publish={publish_notifications}"
        )

        # 1. Fetch firing alerts from Alertmanager
        raw_alerts = self.alert_fetcher.fetch_firing_alerts()
        self.logger.info(f"Fetched {len(raw_alerts)} firing alerts")

        # 2. Process alerts (severity mapping, deduplication, filtering)
        all_processed, to_notify = self.alert_processor.process_alerts(raw_alerts)

        # 3. Filter by minimum severity
        min_sev = AlertSeverity(min_severity.lower())
        to_notify = self.alert_processor.filter_by_severity(to_notify, min_sev)

        # 4. Group alerts if requested
        notification_results: List[NotificationResult] = []
        if to_notify and publish_notifications:
            if group_alerts:
                groups = self.alert_processor.group_alerts(to_notify)
                notification_results = self.notification_router.route_alert_groups(groups)
            else:
                notification_results = self.notification_router.route_alerts(to_notify)

        # 5. Count by severity
        severity_breakdown = self._count_by_severity(all_processed)

        # 6. Build result summary
        result_summary = self._generate_result_summary(all_processed, notification_results)

        self.logger.info(
            f"Monitoring complete: {len(all_processed)} alerts processed, "
            f"{len(to_notify)} notified"
        )

        return {
            "detection_type": "k8s_monitoring",
            "cluster_name": self.alert_processor.cluster_name,
            "alerts_fetched": len(raw_alerts),
            "alerts_processed": len(all_processed),
            "alerts_notified": len(to_notify),
            "severity_breakdown": severity_breakdown,
            "notification_results": [r.to_dict() for r in notification_results],
            "summary": result_summary,
            "alerts": [a.to_dict() for a in all_processed[:20]],
            "detection_timestamp": datetime.utcnow().isoformat(),
        }

    def _count_by_severity(
        self,
        alerts: List[ProcessedAlert],
    ) -> Dict[str, int]:
        """Count alerts by severity."""
        return {
            "critical": sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL),
            "high": sum(1 for a in alerts if a.severity == AlertSeverity.HIGH),
            "medium": sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM),
        }

    def _generate_result_summary(
        self,
        alerts: List[ProcessedAlert],
        notification_results: List[NotificationResult],
    ) -> str:
        """Generate result summary string."""
        if not alerts:
            return "현재 발생 중인 알림이 없습니다."

        severity_counts = self._count_by_severity(alerts)

        # Count successful notifications
        success_count = sum(1 for r in notification_results if r.success)
        total_notified = sum(r.alert_count for r in notification_results if r.success)

        return (
            f"총 {len(alerts)}건의 알림이 탐지되었습니다. "
            f"[심각: {severity_counts['critical']}, "
            f"높음: {severity_counts['high']}, "
            f"보통: {severity_counts['medium']}] "
            f"알림 발송: {success_count}회 ({total_notified}건)"
        )


# Lambda entry point
handler_instance = HDSPMonitoringHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)


# FastAPI integration (optional)
def create_app():
    """Create FastAPI application."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except ImportError:
        return None

    app = FastAPI(
        title="HDSP Monitoring API",
        description="Prometheus Alertmanager-based K8s monitoring",
        version="0.1.0",
    )

    @app.post("/monitor")
    async def monitor(request: Request):
        """Run monitoring check."""
        body = await request.json() if await request.body() else {}
        result = handler_instance.handle({"body": body}, None)
        return JSONResponse(content=result.get("body", result))

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "hdsp-monitoring"}

    @app.get("/stats")
    async def stats():
        """Get processing statistics."""
        return {
            "processor_stats": handler_instance.alert_processor.get_stats(),
            "fetcher_is_mock": handler_instance.alert_fetcher.is_mock,
        }

    return app


if __name__ == "__main__":
    # Test run
    import json

    test_event = {
        "publish_notifications": False,
        "min_severity": "medium",
    }

    result = handler(test_event, None)
    print(json.dumps(result, indent=2, ensure_ascii=False))
