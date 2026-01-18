"""
Analysis Handler for Root Cause Analysis Lambda.

Entry point for LangGraph-based analysis workflow.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from src.common.handlers.base_handler import BaseHandler
from src.common.services.llm_client import LLMClient, LLMProvider
from src.common.services.aws_client import AWSClient, AWSProvider
from src.common.models.analysis_result import AnalysisResult
from src.common.prompts.analysis_prompts import build_analysis_prompt, ANALYSIS_SYSTEM_PROMPT


class AnalysisHandler(BaseHandler):
    """
    Lambda handler for root cause analysis.

    Processes anomaly detection results and performs
    LLM-based root cause analysis.
    """

    def __init__(self):
        super().__init__("AnalysisHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients."""
        llm_provider = LLMProvider(self.config["llm_provider"])
        aws_provider = AWSProvider(self.config["aws_provider"])

        self.llm_client = LLMClient(provider=llm_provider)
        self.aws_client = AWSClient(provider=aws_provider)

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate analysis event."""
        # Support both direct invocation and EventBridge
        detail = event.get("detail", event)

        if not detail.get("signature") and not detail.get("anomaly_data"):
            return "Missing required field: signature or anomaly_data"

        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process analysis request."""
        # Extract anomaly data from event
        detail = event.get("detail", event)
        anomaly_data = detail.get("anomaly_data", detail)

        self.logger.info(f"Analyzing anomaly: {anomaly_data.get('signature', 'unknown')}")

        # Get additional context
        log_summary = anomaly_data.get("summary", "")
        if not log_summary and anomaly_data.get("sample_logs"):
            log_summary = self._summarize_sample_logs(anomaly_data["sample_logs"])

        # Retrieve knowledge base context if available
        kb_context = None
        if self.config.get("knowledge_base_id"):
            kb_context = self._get_knowledge_base_context(anomaly_data)

        # Get related metrics
        metrics_data = self._get_related_metrics(anomaly_data)

        # Perform analysis
        analysis_result = self._perform_analysis(
            anomaly_data=anomaly_data,
            log_summary=log_summary,
            metrics_data=metrics_data,
            knowledge_base_context=kb_context,
        )

        # Determine action based on confidence
        action = self._determine_action(analysis_result)

        # Store result
        self._store_analysis_result(anomaly_data, analysis_result, action)

        # Trigger next step - all actions require approval
        if action == "request_approval":
            self._request_human_approval(anomaly_data, analysis_result)
        elif action == "escalate":
            self._escalate_to_human(anomaly_data, analysis_result)

        return {
            "signature": anomaly_data.get("signature"),
            "analysis": analysis_result.model_dump(),
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _perform_analysis(
        self,
        anomaly_data: Dict[str, Any],
        log_summary: str,
        metrics_data: Optional[Dict[str, Any]] = None,
        knowledge_base_context: Optional[list] = None,
    ) -> AnalysisResult:
        """Perform LLM-based root cause analysis."""
        prompt = build_analysis_prompt(
            anomaly_data=anomaly_data,
            log_summary=log_summary,
            metrics_data=metrics_data,
            knowledge_base_context=knowledge_base_context,
        )

        result = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=AnalysisResult,
            system_prompt=ANALYSIS_SYSTEM_PROMPT,
            temperature=0.3,
        )

        return result

    def _summarize_sample_logs(self, logs: list) -> str:
        """Create quick summary of sample logs."""
        if not logs:
            return "No sample logs available."

        summary_parts = []
        error_count = 0

        for log in logs[:10]:
            message = log.get("message", log.get("@message", str(log)))
            if "error" in message.lower() or "exception" in message.lower():
                error_count += 1
                summary_parts.append(f"- {message[:200]}")

        header = f"Found {error_count} error patterns in {len(logs)} sample logs:\n"
        return header + "\n".join(summary_parts[:5])

    def _get_knowledge_base_context(
        self, anomaly_data: Dict[str, Any]
    ) -> Optional[list]:
        """Retrieve relevant context from knowledge base."""
        try:
            service_name = anomaly_data.get("service_name", "")
            anomaly_type = anomaly_data.get("anomaly_type", "")

            query = f"{service_name} {anomaly_type} troubleshooting remediation"

            results = self.aws_client.retrieve_knowledge_base(
                knowledge_base_id=self.config["knowledge_base_id"],
                query=query,
                max_results=3,
            )

            return results if results else None

        except Exception as e:
            self.logger.warning(f"Knowledge base retrieval failed: {e}")
            return None

    def _get_related_metrics(
        self, anomaly_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get related CloudWatch metrics."""
        try:
            service_name = anomaly_data.get("service_name", "")
            if not service_name:
                return None

            from datetime import timedelta

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)

            metrics = {}

            # Get error metrics
            error_data = self.aws_client.get_cloudwatch_metrics(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions=[{"FunctionName": service_name}],
                start_time=start_time,
                end_time=end_time,
            )
            if error_data.get("datapoints"):
                metrics["errors"] = {
                    "namespace": "AWS/Lambda",
                    "values": [dp.get("Sum", 0) for dp in error_data["datapoints"]],
                }

            # Get duration metrics
            duration_data = self.aws_client.get_cloudwatch_metrics(
                namespace="AWS/Lambda",
                metric_name="Duration",
                dimensions=[{"FunctionName": service_name}],
                start_time=start_time,
                end_time=end_time,
            )
            if duration_data.get("datapoints"):
                metrics["duration"] = {
                    "namespace": "AWS/Lambda",
                    "values": [dp.get("Average", 0) for dp in duration_data["datapoints"]],
                }

            return metrics if metrics else None

        except Exception as e:
            self.logger.warning(f"Metrics retrieval failed: {e}")
            return None

    def _determine_action(self, result: AnalysisResult) -> str:
        """
        Determine action based on analysis result.

        Note: Auto-execute is disabled. All actions require approval.
        """
        if result.requires_approval:
            return "request_approval"
        elif result.requires_escalation:
            return "escalate"
        else:
            return "monitor"

    def _store_analysis_result(
        self,
        anomaly_data: Dict[str, Any],
        result: AnalysisResult,
        action: str,
    ) -> None:
        """Store analysis result in DynamoDB."""
        try:
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"ANOMALY#{anomaly_data.get('signature', 'unknown')}",
                    "sk": f"ANALYSIS#{datetime.utcnow().isoformat()}",
                    "type": "analysis",
                    "result": result.model_dump(),
                    "action": action,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to store analysis result: {e}")

    def _request_human_approval(
        self, anomaly_data: Dict[str, Any], result: AnalysisResult
    ) -> None:
        """Request human approval for remediation."""
        try:
            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="bdp.analysis",
                detail_type="ApprovalRequired",
                detail={
                    "anomaly_data": anomaly_data,
                    "analysis_result": result.model_dump(),
                    "reason": result.review_reason or "Confidence below threshold",
                },
            )
            self.logger.info(
                f"Approval requested for {anomaly_data.get('signature')}"
            )
        except Exception as e:
            self.logger.error(f"Failed to request approval: {e}")

    def _escalate_to_human(
        self, anomaly_data: Dict[str, Any], result: AnalysisResult
    ) -> None:
        """Escalate to human for low confidence analysis."""
        try:
            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="bdp.analysis",
                detail_type="EscalationRequired",
                detail={
                    "anomaly_data": anomaly_data,
                    "analysis_result": result.model_dump(),
                    "reason": result.review_reason or "Low confidence - requires human review",
                },
            )
            self.logger.info(
                f"Escalation triggered for {anomaly_data.get('signature')}"
            )
        except Exception as e:
            self.logger.error(f"Failed to escalate: {e}")


# Lambda entry point
handler_instance = AnalysisHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
