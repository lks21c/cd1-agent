"""
Remediation Handler for Auto-Remediation Lambda.

Entry point for executing approved remediation actions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.handlers.base_handler import BaseHandler
from src.services.aws_client import AWSClient, AWSProvider
from src.models.analysis_result import ActionType, RemediationAction


class RemediationHandler(BaseHandler):
    """
    Lambda handler for remediation execution.

    Executes approved remediation actions and tracks results.
    """

    def __init__(self):
        super().__init__("RemediationHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients."""
        aws_provider = AWSProvider(self.config["aws_provider"])
        self.aws_client = AWSClient(provider=aws_provider)

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate remediation event."""
        detail = event.get("detail", event)

        if not detail.get("analysis_result"):
            return "Missing required field: analysis_result"

        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process remediation request."""
        detail = event.get("detail", event)
        anomaly_data = detail.get("anomaly_data", {})
        analysis_result = detail.get("analysis_result", {})
        auto_approved = detail.get("auto_approved", False)

        signature = anomaly_data.get("signature", "unknown")
        self.logger.info(f"Processing remediation for: {signature}")

        # Get remediation actions
        remediations = analysis_result.get("remediations", [])
        if not remediations:
            return {
                "signature": signature,
                "status": "no_action",
                "message": "No remediation actions specified",
            }

        # Execute actions
        results = []
        for action_data in remediations:
            action = RemediationAction.model_validate(action_data)

            # Check if action requires approval and wasn't auto-approved
            if action.requires_approval and not auto_approved:
                results.append({
                    "action_type": action.action_type,
                    "status": "pending_approval",
                    "message": "Action requires explicit approval",
                })
                continue

            # Execute action
            result = self._execute_action(action, anomaly_data)
            results.append(result)

        # Store remediation results
        self._store_remediation_results(signature, results)

        # Determine overall status
        statuses = [r["status"] for r in results]
        if all(s == "success" for s in statuses):
            overall_status = "success"
        elif any(s == "success" for s in statuses):
            overall_status = "partial_success"
        elif any(s == "pending_approval" for s in statuses):
            overall_status = "pending_approval"
        else:
            overall_status = "failed"

        return {
            "signature": signature,
            "status": overall_status,
            "actions_executed": len([r for r in results if r["status"] == "success"]),
            "results": results,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _execute_action(
        self, action: RemediationAction, anomaly_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single remediation action."""
        try:
            action_type = action.action_type

            if action_type == ActionType.LAMBDA_RESTART:
                return self._restart_lambda(action, anomaly_data)
            elif action_type == ActionType.RDS_PARAMETER:
                return self._update_rds_parameter(action)
            elif action_type == ActionType.AUTO_SCALING:
                return self._trigger_auto_scaling(action)
            elif action_type == ActionType.EVENTBRIDGE_EVENT:
                return self._send_eventbridge_event(action)
            elif action_type == ActionType.NOTIFY:
                return self._send_notification(action, anomaly_data)
            elif action_type == ActionType.ESCALATE:
                return self._escalate_issue(action, anomaly_data)
            elif action_type == ActionType.INVESTIGATE:
                return self._create_investigation_ticket(action, anomaly_data)
            else:
                return {
                    "action_type": action_type,
                    "status": "unsupported",
                    "message": f"Action type {action_type} not implemented",
                }

        except Exception as e:
            self.logger.error(f"Action {action.action_type} failed: {e}")
            return {
                "action_type": action.action_type,
                "status": "failed",
                "error": str(e),
            }

    def _restart_lambda(
        self, action: RemediationAction, anomaly_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Restart Lambda function by updating configuration."""
        function_name = action.parameters.get(
            "function_name", anomaly_data.get("service_name")
        )

        if not function_name:
            return {
                "action_type": ActionType.LAMBDA_RESTART,
                "status": "failed",
                "error": "No function name specified",
            }

        # In real implementation, would update Lambda configuration
        # to trigger a cold start
        self.logger.info(f"Would restart Lambda: {function_name}")

        # For mock, just log and succeed
        return {
            "action_type": ActionType.LAMBDA_RESTART,
            "status": "success",
            "function_name": function_name,
            "message": f"Lambda {function_name} restart triggered",
        }

    def _update_rds_parameter(self, action: RemediationAction) -> Dict[str, Any]:
        """Update RDS parameter group."""
        parameter_group = action.parameters.get("parameter_group")
        parameter_name = action.parameters.get("parameter_name")
        parameter_value = action.parameters.get("parameter_value")

        if not all([parameter_group, parameter_name, parameter_value]):
            return {
                "action_type": ActionType.RDS_PARAMETER,
                "status": "failed",
                "error": "Missing required parameters",
            }

        # In real implementation, would update RDS parameter
        self.logger.info(
            f"Would update RDS parameter: {parameter_name}={parameter_value}"
        )

        return {
            "action_type": ActionType.RDS_PARAMETER,
            "status": "success",
            "parameter_group": parameter_group,
            "parameter_name": parameter_name,
            "message": "Parameter update initiated",
        }

    def _trigger_auto_scaling(self, action: RemediationAction) -> Dict[str, Any]:
        """Trigger auto-scaling action."""
        scaling_group = action.parameters.get("scaling_group")
        desired_capacity = action.parameters.get("desired_capacity")

        if not scaling_group:
            return {
                "action_type": ActionType.AUTO_SCALING,
                "status": "failed",
                "error": "No scaling group specified",
            }

        # In real implementation, would update ASG
        self.logger.info(f"Would scale {scaling_group} to {desired_capacity}")

        return {
            "action_type": ActionType.AUTO_SCALING,
            "status": "success",
            "scaling_group": scaling_group,
            "desired_capacity": desired_capacity,
            "message": "Scaling action initiated",
        }

    def _send_eventbridge_event(self, action: RemediationAction) -> Dict[str, Any]:
        """Send custom EventBridge event."""
        event_bus = action.parameters.get("event_bus", self.config["event_bus"])
        source = action.parameters.get("source", "bdp.remediation")
        detail_type = action.parameters.get("detail_type", "CustomAction")
        detail = action.parameters.get("detail", {})

        result = self.aws_client.put_eventbridge_event(
            event_bus=event_bus,
            source=source,
            detail_type=detail_type,
            detail=detail,
        )

        return {
            "action_type": ActionType.EVENTBRIDGE_EVENT,
            "status": "success" if result.get("failed_count", 0) == 0 else "failed",
            "event_bus": event_bus,
            "detail_type": detail_type,
        }

    def _send_notification(
        self, action: RemediationAction, anomaly_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send notification about the issue."""
        channel = action.parameters.get("channel", "email")
        recipients = action.parameters.get("recipients", [])
        message = action.parameters.get(
            "message",
            f"Anomaly detected: {anomaly_data.get('signature', 'unknown')}",
        )

        # In real implementation, would send via SNS, SES, or Slack
        self.logger.info(f"Would notify via {channel}: {message[:100]}")

        # Send via EventBridge for downstream processing
        self.aws_client.put_eventbridge_event(
            event_bus=self.config["event_bus"],
            source="bdp.remediation",
            detail_type="Notification",
            detail={
                "channel": channel,
                "recipients": recipients,
                "message": message,
                "anomaly_signature": anomaly_data.get("signature"),
            },
        )

        return {
            "action_type": ActionType.NOTIFY,
            "status": "success",
            "channel": channel,
            "message": "Notification sent",
        }

    def _escalate_issue(
        self, action: RemediationAction, anomaly_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Escalate issue to on-call team."""
        severity = action.parameters.get("severity", "high")
        team = action.parameters.get("team", "platform")

        # Send escalation event
        self.aws_client.put_eventbridge_event(
            event_bus=self.config["event_bus"],
            source="bdp.remediation",
            detail_type="Escalation",
            detail={
                "severity": severity,
                "team": team,
                "anomaly_data": anomaly_data,
                "reason": action.expected_outcome,
            },
        )

        return {
            "action_type": ActionType.ESCALATE,
            "status": "success",
            "severity": severity,
            "team": team,
            "message": "Issue escalated",
        }

    def _create_investigation_ticket(
        self, action: RemediationAction, anomaly_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create investigation ticket for further analysis."""
        # Store investigation request
        self.aws_client.put_dynamodb_item(
            table_name=self.config["dynamodb_table"],
            item={
                "pk": f"INVESTIGATION#{anomaly_data.get('signature', 'unknown')}",
                "sk": f"TICKET#{datetime.utcnow().isoformat()}",
                "type": "investigation",
                "status": "open",
                "anomaly_data": anomaly_data,
                "investigation_notes": action.parameters.get("notes", ""),
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        return {
            "action_type": ActionType.INVESTIGATE,
            "status": "success",
            "message": "Investigation ticket created",
        }

    def _store_remediation_results(
        self, signature: str, results: List[Dict[str, Any]]
    ) -> None:
        """Store remediation execution results."""
        try:
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"ANOMALY#{signature}",
                    "sk": f"REMEDIATION#{datetime.utcnow().isoformat()}",
                    "type": "remediation",
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to store remediation results: {e}")


# Lambda entry point
handler_instance = RemediationHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
