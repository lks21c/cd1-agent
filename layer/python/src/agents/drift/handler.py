"""
Drift Detection Handler for AWS Configuration Drift Detection Lambda.

Entry point for Drift Agent - detects configuration drifts between
local baseline files and current AWS resource configurations.
Includes LLM-based root cause analysis for critical/high severity drifts.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.common.handlers.base_handler import BaseHandler
from src.agents.drift.services.baseline_loader import BaselineLoader, BaselineFile
from src.agents.drift.services.config_fetcher import ConfigFetcher, ResourceType, ResourceConfig
from src.agents.drift.services.drift_detector import (
    ConfigDriftDetector,
    DriftResult,
    DriftSeverity,
    AggregatedDriftResult,
)
from src.agents.drift.services.drift_analyzer import DriftAnalyzer
from src.agents.drift.models import DriftAnalysisResult
from src.common.services.aws_client import AWSClient, AWSProvider
from src.common.services.llm_client import LLMClient, LLMProvider


# Resource mapping from string to ResourceType
RESOURCE_TYPE_MAP = {
    "EKS": ResourceType.EKS,
    "MSK": ResourceType.MSK,
    "S3": ResourceType.S3,
    "EMR": ResourceType.EMR,
    "MWAA": ResourceType.MWAA,
}

# Default resources to check per type
DEFAULT_RESOURCES = {
    "EKS": ["production-eks"],
    "MSK": ["production-kafka"],
    "S3": ["company-data-lake-prod"],
    "EMR": ["j-XXXXX"],
    "MWAA": ["bdp-airflow-prod"],
}


class DriftDetectionHandler(BaseHandler):
    """
    Lambda handler for AWS configuration drift detection.

    Compares current AWS resource configurations against local baseline files
    to detect and classify configuration drifts:
    - EKS: Cluster and node group configurations
    - MSK: Kafka cluster configurations
    - S3: Bucket security and lifecycle configurations
    - EMR: Cluster and instance group configurations
    - MWAA: Airflow environment configurations

    Triggers analysis workflow when critical/high severity drifts are detected.
    """

    def __init__(self):
        super().__init__("DriftDetectionHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients based on configuration."""
        aws_provider = AWSProvider(self.config["aws_provider"])
        self.aws_client = AWSClient(provider=aws_provider)

        # Baseline loader and Config fetcher auto-detect mock mode
        self.baseline_loader = BaselineLoader()
        self.config_fetcher = ConfigFetcher()
        self.drift_detector = ConfigDriftDetector()

        # Initialize LLM-based drift analyzer
        self._init_drift_analyzer()

    def _init_drift_analyzer(self) -> None:
        """Initialize LLM client and drift analyzer."""
        # Check if analysis is enabled
        self.analysis_enabled = os.getenv("ENABLE_DRIFT_ANALYSIS", "true").lower() == "true"

        if not self.analysis_enabled:
            self.logger.info("Drift analysis disabled via ENABLE_DRIFT_ANALYSIS")
            self.drift_analyzer = None
            return

        # Determine LLM provider
        llm_provider_name = os.getenv("LLM_PROVIDER", "mock").lower()
        provider_map = {
            "vllm": LLMProvider.VLLM,
            "gemini": LLMProvider.GEMINI,
            "mock": LLMProvider.MOCK,
        }
        llm_provider = provider_map.get(llm_provider_name, LLMProvider.MOCK)

        # Create LLM client
        llm_client = LLMClient(
            provider=llm_provider,
            endpoint=os.getenv("VLLM_ENDPOINT"),
            model_name=os.getenv("LLM_MODEL"),
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("VLLM_API_KEY"),
        )

        # Create drift analyzer
        self.drift_analyzer = DriftAnalyzer(
            llm_client=llm_client,
            max_iterations=int(os.getenv("MAX_ANALYSIS_ITERATIONS", "3")),
            confidence_threshold=float(os.getenv("ANALYSIS_CONFIDENCE_THRESHOLD", "0.7")),
        )

        self.max_drifts_to_analyze = int(os.getenv("MAX_DRIFTS_TO_ANALYZE", "5"))
        self.logger.info(f"Drift analyzer initialized with {llm_provider_name} provider")

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate drift detection event."""
        body = self._parse_body(event)

        # Validate resource_types if provided
        resource_types = body.get("resource_types", event.get("resource_types", []))
        if resource_types:
            for rt in resource_types:
                if rt.upper() not in RESOURCE_TYPE_MAP:
                    return f"Invalid resource_type: {rt}. Must be one of: {list(RESOURCE_TYPE_MAP.keys())}"

        # Validate severity_threshold if provided
        severity_threshold = body.get(
            "severity_threshold",
            event.get("severity_threshold", "LOW"),
        )
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        if severity_threshold.upper() not in valid_severities:
            return f"Invalid severity_threshold: {severity_threshold}. Must be one of: {valid_severities}"

        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process drift detection request."""
        body = self._parse_body(event)

        # Get configuration from event or body
        resource_types = body.get("resource_types", event.get("resource_types", []))
        resources = body.get("resources", event.get("resources", {}))
        severity_threshold = body.get(
            "severity_threshold",
            event.get("severity_threshold", "LOW"),
        ).upper()
        baseline_ref = body.get("baseline_ref", event.get("baseline_ref"))

        # Use defaults if no resources specified
        if not resource_types:
            resource_types = list(RESOURCE_TYPE_MAP.keys())

        self.logger.info(
            f"Processing drift detection for resource types: {resource_types}"
        )

        # Run drift detection (returns result + configs for analysis)
        result, drift_configs = self._run_drift_detection(
            resource_types=resource_types,
            resources=resources,
            baseline_ref=baseline_ref,
            severity_threshold=severity_threshold,
        )

        self.logger.info(
            f"Detection complete: {result.total_drift_count} drifts found "
            f"(critical: {result.severity_summary.get('CRITICAL', 0)}, "
            f"high: {result.severity_summary.get('HIGH', 0)})"
        )

        # Run LLM analysis on critical/high drifts
        analysis_results: List[DriftAnalysisResult] = []
        if self._should_analyze(result):
            analysis_results = self._analyze_drifts(result, drift_configs)
            self.logger.info(f"LLM analysis completed for {len(analysis_results)} drifts")

        # Store results (including analysis)
        self._store_drift_results(result, analysis_results)

        # Trigger downstream workflow
        if (
            result.severity_summary.get("CRITICAL", 0) > 0 or
            result.severity_summary.get("HIGH", 0) > 0
        ):
            self._trigger_analysis(result, analysis_results)

        # Build response
        response = result.to_dict()
        if analysis_results:
            response["analysis_results"] = [a.to_dict() for a in analysis_results]

        return response

    def _should_analyze(self, result: AggregatedDriftResult) -> bool:
        """Determine if LLM analysis should run."""
        if not self.analysis_enabled or not self.drift_analyzer:
            return False

        # Only analyze if there are critical/high drifts
        return (
            result.severity_summary.get("CRITICAL", 0) > 0 or
            result.severity_summary.get("HIGH", 0) > 0
        )

    def _analyze_drifts(
        self,
        result: AggregatedDriftResult,
        drift_configs: Dict[str, Tuple[BaselineFile, ResourceConfig]],
    ) -> List[DriftAnalysisResult]:
        """Run LLM-based root cause analysis on high-severity drifts."""
        analysis_results = []

        # Get drifts with critical/high severity
        high_severity_drifts = [
            d for d in result.drifts
            if d.has_drift and d.max_severity in (DriftSeverity.CRITICAL, DriftSeverity.HIGH)
        ]

        # Limit number of drifts to analyze
        drifts_to_analyze = high_severity_drifts[:self.max_drifts_to_analyze]

        for drift in drifts_to_analyze:
            drift_key = f"{drift.resource_type}:{drift.resource_id}"

            if drift_key not in drift_configs:
                self.logger.warning(f"No config found for drift {drift_key}")
                continue

            baseline_file, current_config = drift_configs[drift_key]

            try:
                self.logger.info(f"Analyzing drift: {drift_key}")
                analysis = self.drift_analyzer.analyze_drift(
                    drift_result=drift,
                    baseline_config=baseline_file.content,
                    current_config=current_config.config,
                    resource_context={
                        "resource_arn": drift.resource_arn,
                        "baseline_version": drift.baseline_version,
                        "region": os.getenv("AWS_REGION", "ap-northeast-2"),
                    },
                )
                analysis_results.append(analysis)

                self.logger.info(
                    f"Analysis for {drift_key}: "
                    f"cause={analysis.cause_analysis.category}, "
                    f"confidence={analysis.confidence_score:.2f}"
                )

            except Exception as e:
                self.logger.error(f"Failed to analyze drift {drift_key}: {e}")

        return analysis_results

    def _run_drift_detection(
        self,
        resource_types: List[str],
        resources: Dict[str, List[str]],
        baseline_ref: Optional[str],
        severity_threshold: str,
    ) -> Tuple[AggregatedDriftResult, Dict[str, Tuple[BaselineFile, ResourceConfig]]]:
        """
        Run drift detection across all specified resources.

        Returns:
            Tuple of (AggregatedDriftResult, dict of configs for analysis)
        """
        drifts: List[DriftResult] = []
        drift_configs: Dict[str, Tuple[BaselineFile, ResourceConfig]] = {}
        resources_analyzed = 0

        # Get baseline source info
        try:
            loader_info = self.baseline_loader.get_baseline_info()
            baseline_info = {
                "source": loader_info.get("source", "local_filesystem"),
                "baselines_dir": loader_info.get("baselines_dir", "conf/baselines"),
            }
        except Exception as e:
            self.logger.warning(f"Failed to get baseline info: {e}")
            baseline_info = {
                "source": "unknown",
                "baselines_dir": "conf/baselines",
            }

        for resource_type in resource_types:
            rt_upper = resource_type.upper()

            # Get resources to check
            resource_list = resources.get(rt_upper, DEFAULT_RESOURCES.get(rt_upper, []))

            for resource_id in resource_list:
                try:
                    drift_result, baseline_file, current_config = self._check_resource_drift(
                        resource_type=rt_upper,
                        resource_id=resource_id,
                    )

                    # Store configs for potential analysis
                    drift_key = f"{rt_upper}:{resource_id}"
                    drift_configs[drift_key] = (baseline_file, current_config)

                    # Apply severity filter
                    if self._meets_severity_threshold(drift_result, severity_threshold):
                        drifts.append(drift_result)

                    resources_analyzed += 1

                except Exception as e:
                    self.logger.error(
                        f"Failed to check drift for {rt_upper}:{resource_id}: {e}"
                    )
                    resources_analyzed += 1

        result = AggregatedDriftResult(
            drifts=drifts,
            resources_analyzed=resources_analyzed,
            detection_timestamp=datetime.utcnow().isoformat(),
            baseline_info=baseline_info,
        )

        return result, drift_configs

    def _check_resource_drift(
        self,
        resource_type: str,
        resource_id: str,
    ) -> Tuple[DriftResult, BaselineFile, ResourceConfig]:
        """
        Check drift for a single resource.

        Returns:
            Tuple of (DriftResult, BaselineFile, ResourceConfig)
        """
        self.logger.debug(f"Checking drift for {resource_type}:{resource_id}")

        # Get baseline from local files
        baseline_file = self.baseline_loader.get_resource_baseline(
            resource_type=resource_type.lower(),
            resource_name=resource_id,
        )

        # Get current config from AWS
        current_config = self.config_fetcher.get_config(
            resource_type=RESOURCE_TYPE_MAP[resource_type],
            resource_id=resource_id,
        )

        # Detect drifts
        drift_result = self.drift_detector.detect(
            baseline=baseline_file.content,
            current=current_config.config,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_arn=current_config.resource_arn,
            baseline_version=baseline_file.file_hash,
        )

        return drift_result, baseline_file, current_config

    def _meets_severity_threshold(
        self,
        drift_result: DriftResult,
        threshold: str,
    ) -> bool:
        """Check if drift result meets severity threshold."""
        if not drift_result.has_drift:
            return True  # Include resources without drifts

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        threshold_idx = severity_order.index(threshold)

        # Check if any drift meets the threshold
        for field in drift_result.drifted_fields:
            field_idx = severity_order.index(field.severity.value)
            if field_idx <= threshold_idx:
                return True

        return False

    def _store_drift_results(
        self,
        result: AggregatedDriftResult,
        analysis_results: Optional[List[DriftAnalysisResult]] = None,
    ) -> None:
        """Store drift detection and analysis results in DynamoDB."""
        try:
            # Build analysis lookup by drift_id
            analysis_by_drift: Dict[str, DriftAnalysisResult] = {}
            if analysis_results:
                for analysis in analysis_results:
                    analysis_by_drift[analysis.drift_id] = analysis

            # Store summary record
            date_str = result.detection_timestamp[:10]
            summary_item = {
                "pk": f"DRIFT#{date_str}",
                "sk": f"DETECTION#{result.detection_timestamp}",
                "type": "drift_detection",
                "drifts_detected": result.has_drifts,
                "total_drift_count": result.total_drift_count,
                "resources_analyzed": result.resources_analyzed,
                "severity_summary": json.dumps(result.severity_summary),
                "baseline_info": json.dumps(result.baseline_info),
                "timestamp": result.detection_timestamp,
                "analysis_enabled": self.analysis_enabled,
                "analysis_count": len(analysis_results) if analysis_results else 0,
            }
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item=summary_item,
            )

            # Store individual drift records for tracking
            for drift in result.drifts:
                if not drift.has_drift:
                    continue

                drift_key = f"{drift.resource_type}:{drift.resource_id}"
                analysis = analysis_by_drift.get(drift_key)

                drift_item = {
                    "pk": f"DRIFT#{drift.resource_type}#{drift.resource_id}",
                    "sk": f"DRIFT#{drift.detection_timestamp}",
                    "type": "resource_drift",
                    "resource_type": drift.resource_type,
                    "resource_id": drift.resource_id,
                    "resource_arn": drift.resource_arn,
                    "severity": drift.max_severity.value if drift.max_severity else None,
                    "drift_count": len(drift.drifted_fields),
                    "baseline_version": drift.baseline_version,
                    "drifted_fields": json.dumps([
                        f.to_dict() for f in drift.drifted_fields
                    ]),
                    "timestamp": drift.detection_timestamp,
                }

                # Add analysis results if available
                if analysis:
                    drift_item.update({
                        "analysis_cause_category": analysis.cause_analysis.category,
                        "analysis_root_cause": analysis.cause_analysis.root_cause,
                        "analysis_confidence": analysis.confidence_score,
                        "analysis_urgency": analysis.urgency_score,
                        "analysis_requires_review": analysis.requires_human_review,
                        "analysis_remediations": json.dumps([
                            r.model_dump() for r in analysis.remediations
                        ]),
                    })

                self.aws_client.put_dynamodb_item(
                    table_name=self.config["dynamodb_table"],
                    item=drift_item,
                )

            self.logger.info(
                f"Stored drift detection results: {result.total_drift_count} drifts, "
                f"{len(analysis_results) if analysis_results else 0} analyzed"
            )

        except Exception as e:
            self.logger.error(f"Failed to store drift detection results: {e}")

    def _trigger_analysis(
        self,
        result: AggregatedDriftResult,
        analysis_results: Optional[List[DriftAnalysisResult]] = None,
    ) -> None:
        """Publish drift event to EventBridge for downstream processing."""
        try:
            # Build analysis summary
            analysis_summary = []
            if analysis_results:
                for analysis in analysis_results:
                    analysis_summary.append({
                        "drift_id": analysis.drift_id,
                        "cause_category": analysis.cause_analysis.category,
                        "root_cause": analysis.cause_analysis.root_cause[:200],  # Truncate
                        "confidence": analysis.confidence_score,
                        "urgency": analysis.urgency_score,
                        "requires_review": analysis.requires_human_review,
                        "remediation_count": len(analysis.remediations),
                    })

            # Create aggregated event data
            event_data = {
                "signature": f"drift_{result.detection_timestamp[:10]}",
                "anomaly_type": "config_drift",
                "service_name": "drift-agent",
                "agent": "drift",
                "first_seen": result.detection_timestamp,
                "last_seen": result.detection_timestamp,
                "severity": self._get_highest_severity(result),
                "summary": (
                    f"Configuration drift detected: {result.total_drift_count} drifts "
                    f"across {result.resources_analyzed} resources"
                ),
                "drift_details": result.drift_details[:10],  # Limit size
                "severity_summary": result.severity_summary,
                "baseline_info": result.baseline_info,
                # Analysis results
                "analysis_enabled": self.analysis_enabled,
                "analysis_count": len(analysis_results) if analysis_results else 0,
                "analysis_summary": analysis_summary[:10],  # Limit size
            }

            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="cd1-agent.drift",
                detail_type="Configuration Drift Detected",
                detail=event_data,
            )

            self.logger.info(
                f"Event published for drift detection: {event_data['signature']}, "
                f"{len(analysis_summary)} analyses included"
            )

        except Exception as e:
            self.logger.error(f"Failed to publish drift event: {e}")

    def _get_highest_severity(self, result: AggregatedDriftResult) -> str:
        """Get the highest severity level from detection result."""
        summary = result.severity_summary
        if summary.get("CRITICAL", 0) > 0:
            return "critical"
        elif summary.get("HIGH", 0) > 0:
            return "high"
        elif summary.get("MEDIUM", 0) > 0:
            return "medium"
        return "low"


# Lambda entry point
handler_instance = DriftDetectionHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
