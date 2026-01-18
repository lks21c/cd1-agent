"""
Drift Analysis Tools - Config Drift Detection & Analysis for Chat.

Provides drift detection and LLM-based root cause analysis capabilities
for the interactive chat agent with Human-in-the-Loop (HITL) support.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.agents.drift.services import (
    ConfigDriftDetector,
    DriftAnalyzer,
    DriftResult,
    DriftSeverity,
    AggregatedDriftResult,
)
from src.agents.drift.models import (
    DriftAnalysisResult,
    DriftCauseCategory,
)
from src.common.services.llm_client import LLMClient, LLMProvider

logger = logging.getLogger(__name__)


def analyze_config_drift(
    baseline_config: Dict[str, Any],
    current_config: Dict[str, Any],
    resource_type: str,
    resource_id: str,
    resource_arn: str = "",
    baseline_version: str = "",
    llm_client: Optional[LLMClient] = None,
    include_analysis: bool = True,
) -> Dict[str, Any]:
    """
    설정 드리프트 감지 및 LLM 기반 원인 분석.

    Args:
        baseline_config: 기준 설정 (GitLab/Terraform)
        current_config: 현재 AWS 설정
        resource_type: 리소스 유형 (EKS, MSK, MWAA 등)
        resource_id: 리소스 식별자
        resource_arn: 리소스 ARN
        baseline_version: 기준 버전 (Git SHA)
        llm_client: LLM 클라이언트 (없으면 Mock 사용)
        include_analysis: LLM 분석 포함 여부

    Returns:
        드리프트 감지 및 분석 결과
    """
    logger.info(f"드리프트 분석 시작: {resource_type}/{resource_id}")

    try:
        # Step 1: 드리프트 감지
        detector = ConfigDriftDetector()
        drift_result = detector.detect(
            baseline=baseline_config,
            current=current_config,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_arn=resource_arn,
            baseline_version=baseline_version,
        )

        result = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_arn": resource_arn,
            "has_drift": drift_result.has_drift,
            "drift_summary": {
                "total_drifts": len(drift_result.drifted_fields),
                "max_severity": drift_result.max_severity.value if drift_result.max_severity else None,
                "added_count": drift_result.added_count,
                "modified_count": drift_result.modified_count,
                "removed_count": drift_result.removed_count,
                "critical_count": drift_result.critical_count,
                "high_count": drift_result.high_count,
            },
            "drifted_fields": [f.to_dict() for f in drift_result.drifted_fields],
            "detection_timestamp": drift_result.detection_timestamp,
            "success": True,
        }

        # Step 2: LLM 기반 원인 분석 (CRITICAL/HIGH 드리프트에 대해)
        if include_analysis and drift_result.has_drift:
            should_analyze = (
                drift_result.max_severity in [DriftSeverity.CRITICAL, DriftSeverity.HIGH]
                or drift_result.critical_count > 0
                or drift_result.high_count > 0
            )

            if should_analyze:
                analyzer = DriftAnalyzer(llm_client=llm_client)
                analysis = analyzer.analyze_drift(
                    drift_result=drift_result,
                    baseline_config=baseline_config,
                    current_config=current_config,
                )

                result["analysis"] = {
                    "drift_id": analysis.drift_id,
                    "cause_category": analysis.cause_analysis.category.value,
                    "root_cause": analysis.cause_analysis.root_cause,
                    "likely_actor": analysis.cause_analysis.likely_actor,
                    "evidence": analysis.cause_analysis.evidence,
                    "impact_assessment": analysis.impact_assessment,
                    "blast_radius": analysis.blast_radius,
                    "confidence_score": analysis.confidence_score,
                    "urgency_score": analysis.urgency_score,
                    "requires_human_review": analysis.requires_human_review,
                    "review_reason": analysis.review_reason,
                    "remediations": [
                        {
                            "action_type": r.action_type,
                            "priority": r.priority,
                            "description": r.description,
                            "command_hint": r.command_hint,
                            "requires_approval": r.requires_approval,
                            "rollback_steps": r.rollback_steps,
                            "expected_outcome": r.expected_outcome,
                        }
                        for r in (analysis.remediations or [])
                    ],
                }

                # HITL 플래그 설정
                result["requires_approval"] = analysis.requires_human_review
                result["approval_context"] = {
                    "reason": analysis.review_reason,
                    "confidence": analysis.confidence_score,
                    "urgency": analysis.urgency_score,
                    "remediations_pending": len(analysis.remediations or []),
                }

        return result

    except Exception as e:
        logger.error(f"드리프트 분석 실패: {e}")
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "error": str(e),
            "success": False,
        }


def check_drift_status(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    severity_filter: Optional[str] = None,
    include_resolved: bool = False,
) -> Dict[str, Any]:
    """
    드리프트 상태 조회.

    Args:
        resource_type: 리소스 유형 필터 (EKS, MSK 등)
        resource_id: 리소스 ID 필터
        severity_filter: 심각도 필터 (CRITICAL, HIGH, MEDIUM, LOW)
        include_resolved: 해결된 드리프트 포함 여부

    Returns:
        드리프트 상태 목록
    """
    logger.info(f"드리프트 상태 조회: type={resource_type}, id={resource_id}")

    # NOTE: 실제 구현에서는 DynamoDB나 다른 저장소에서 조회
    # 현재는 Mock 응답 반환
    mock_drifts = [
        {
            "drift_id": "EKS:production-cluster",
            "resource_type": "EKS",
            "resource_id": "production-cluster",
            "severity": "HIGH",
            "status": "PENDING_REVIEW",
            "detected_at": datetime.utcnow().isoformat(),
            "cause_category": "MANUAL_CHANGE",
            "requires_approval": True,
        },
        {
            "drift_id": "MSK:data-pipeline",
            "resource_type": "MSK",
            "resource_id": "data-pipeline",
            "severity": "MEDIUM",
            "status": "AUTO_RESOLVED",
            "detected_at": datetime.utcnow().isoformat(),
            "cause_category": "AUTO_SCALING",
            "requires_approval": False,
        },
    ]

    # 필터 적용
    filtered_drifts = mock_drifts

    if resource_type:
        filtered_drifts = [d for d in filtered_drifts if d["resource_type"] == resource_type]

    if resource_id:
        filtered_drifts = [d for d in filtered_drifts if d["resource_id"] == resource_id]

    if severity_filter:
        filtered_drifts = [d for d in filtered_drifts if d["severity"] == severity_filter]

    if not include_resolved:
        filtered_drifts = [d for d in filtered_drifts if d["status"] != "AUTO_RESOLVED"]

    return {
        "drifts": filtered_drifts,
        "total_count": len(filtered_drifts),
        "pending_approval_count": sum(1 for d in filtered_drifts if d.get("requires_approval")),
        "filters_applied": {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "severity": severity_filter,
            "include_resolved": include_resolved,
        },
        "success": True,
    }


def get_remediation_plan(
    drift_id: str,
    auto_approve: bool = False,
) -> Dict[str, Any]:
    """
    드리프트 복구 계획 조회 및 실행 준비.

    Args:
        drift_id: 드리프트 ID (resource_type:resource_id)
        auto_approve: 자동 승인 여부 (False면 HITL 필요)

    Returns:
        복구 계획 및 승인 상태
    """
    logger.info(f"복구 계획 조회: drift_id={drift_id}")

    # NOTE: 실제 구현에서는 저장된 분석 결과에서 조회
    # Mock 응답
    mock_plan = {
        "drift_id": drift_id,
        "remediations": [
            {
                "action_type": "revert_to_baseline",
                "priority": 1,
                "description": "Terraform을 사용하여 기준 설정으로 복원",
                "command_hint": "terraform apply -target=module.eks",
                "requires_approval": True,
                "rollback_steps": ["terraform plan으로 변경 사항 확인"],
                "expected_outcome": "설정이 기준 상태로 복원됨",
            },
            {
                "action_type": "update_baseline",
                "priority": 2,
                "description": "현재 설정을 새 기준으로 승인",
                "command_hint": "git commit -m 'Update baseline config'",
                "requires_approval": True,
                "rollback_steps": ["git revert로 이전 기준 복원"],
                "expected_outcome": "현재 설정이 새 기준으로 등록됨",
            },
        ],
        "approval_status": "PENDING" if not auto_approve else "AUTO_APPROVED",
        "requires_human_review": not auto_approve,
        "review_context": {
            "reason": "보안 관련 설정 변경이므로 수동 검토 필요",
            "risk_level": "HIGH",
            "impact_scope": ["production-eks", "dependent-services"],
        },
        "success": True,
    }

    return mock_plan


def approve_remediation(
    drift_id: str,
    action_type: str,
    approval_status: str = "APPROVED",
    user_feedback: Optional[str] = None,
    modified_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    복구 작업 승인 처리 (HITL).

    Args:
        drift_id: 드리프트 ID
        action_type: 승인할 작업 유형
        approval_status: 승인 상태 (APPROVED, MODIFIED, REJECTED)
        user_feedback: 사용자 피드백
        modified_parameters: 수정된 파라미터 (MODIFIED 시)

    Returns:
        승인 처리 결과
    """
    logger.info(f"복구 승인 처리: drift_id={drift_id}, action={action_type}, status={approval_status}")

    valid_statuses = ["APPROVED", "MODIFIED", "REJECTED"]
    if approval_status not in valid_statuses:
        return {
            "drift_id": drift_id,
            "error": f"Invalid approval status. Must be one of: {valid_statuses}",
            "success": False,
        }

    result = {
        "drift_id": drift_id,
        "action_type": action_type,
        "approval_status": approval_status,
        "processed_at": datetime.utcnow().isoformat(),
        "user_feedback": user_feedback,
        "success": True,
    }

    if approval_status == "APPROVED":
        result["next_step"] = "execute_remediation"
        result["message"] = "복구 작업이 승인되었습니다. 실행을 진행합니다."
    elif approval_status == "MODIFIED":
        result["modified_parameters"] = modified_parameters
        result["next_step"] = "review_modifications"
        result["message"] = "수정된 파라미터로 복구를 진행합니다."
    else:  # REJECTED
        result["next_step"] = "archive_drift"
        result["message"] = "복구 작업이 거부되었습니다. 드리프트가 의도적 변경으로 처리됩니다."

    return result


def create_drift_tools(
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Callable]:
    """
    Drift Tool 세트 생성.

    Args:
        llm_client: LLM 클라이언트 (선택)

    Returns:
        Tool 딕셔너리
    """

    def _analyze_drift(**kwargs) -> Dict[str, Any]:
        return analyze_config_drift(llm_client=llm_client, **kwargs)

    def _check_status(**kwargs) -> Dict[str, Any]:
        return check_drift_status(**kwargs)

    def _get_plan(**kwargs) -> Dict[str, Any]:
        return get_remediation_plan(**kwargs)

    def _approve(**kwargs) -> Dict[str, Any]:
        return approve_remediation(**kwargs)

    return {
        "analyze_config_drift": _analyze_drift,
        "check_drift_status": _check_status,
        "get_remediation_plan": _get_plan,
        "approve_remediation": _approve,
    }
