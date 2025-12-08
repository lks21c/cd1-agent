"""
Reflection Engine for BDP Agent.

이 모듈은 LLM 분석 결과의 품질을 평가하고 신뢰도 점수를 계산합니다.
hdsp_agent의 Reflection 패턴을 따릅니다.

신뢰도 기반 자동화:
- 0.85+: 자동 실행
- 0.5-0.85: 승인 요청
- <0.5: 재분석 필요
"""
from dataclasses import dataclass
from typing import Dict, List, Any
import structlog

logger = structlog.get_logger()


@dataclass
class ReflectionResult:
    """Reflection 평가 결과."""
    confidence: float
    reasoning: str
    breakdown: Dict[str, float]
    suggestions: List[str]
    requires_replan: bool


class ReflectionEngine:
    """분석 품질 평가 및 신뢰도 계산 엔진."""

    # 신뢰도 임계값
    AUTO_EXECUTE_THRESHOLD = 0.85
    APPROVAL_THRESHOLD = 0.5

    def __init__(self):
        self.logger = logger.bind(service="reflection_engine")

    def evaluate(
        self,
        analysis: Dict[str, Any],
        evidence: Dict[str, Any],
        context: List[Dict]
    ) -> ReflectionResult:
        """
        분석 품질 평가 및 신뢰도 점수 계산.

        Args:
            analysis: LLM 분석 결과
            evidence: 로그 요약 증거
            context: 이전 시도 컨텍스트

        Returns:
            ReflectionResult: 평가 결과
        """
        # 1. 증거 충분성 평가 (0.0-1.0)
        evidence_score = self._evaluate_evidence_sufficiency(analysis, evidence)

        # 2. 논리적 일관성 평가 (0.0-1.0)
        logic_score = self._evaluate_logical_consistency(analysis)

        # 3. 실행 가능성 평가 (0.0-1.0)
        actionability_score = self._evaluate_actionability(analysis)

        # 4. 이전 시도와의 일관성 (0.0-1.0)
        consistency_score = self._evaluate_consistency(analysis, context)

        # 가중 평균 계산
        weights = {
            'evidence': 0.35,
            'logic': 0.25,
            'actionability': 0.25,
            'consistency': 0.15
        }

        overall_confidence = (
            evidence_score * weights['evidence'] +
            logic_score * weights['logic'] +
            actionability_score * weights['actionability'] +
            consistency_score * weights['consistency']
        )

        breakdown = {
            'evidence_sufficiency': evidence_score,
            'logical_consistency': logic_score,
            'actionability': actionability_score,
            'consistency': consistency_score
        }

        suggestions = self._generate_suggestions(breakdown)
        requires_replan = overall_confidence < self.APPROVAL_THRESHOLD
        reasoning = self._generate_reasoning(breakdown, overall_confidence)

        self.logger.info(
            "reflection_complete",
            confidence=overall_confidence,
            breakdown=breakdown,
            requires_replan=requires_replan
        )

        return ReflectionResult(
            confidence=round(overall_confidence, 3),
            reasoning=reasoning,
            breakdown=breakdown,
            suggestions=suggestions,
            requires_replan=requires_replan
        )

    def _evaluate_evidence_sufficiency(
        self,
        analysis: Dict,
        evidence: Dict
    ) -> float:
        """증거 충분성 평가."""
        score = 0.0

        evidence_list = analysis.get('evidence', [])
        if evidence_list:
            score += 0.3

        if len(evidence_list) >= 3:
            score += 0.2
        elif len(evidence_list) >= 1:
            score += 0.1

        sample_count = evidence.get('total_anomalies', 0)
        if sample_count > 0 and evidence_list:
            score += 0.3

        root_cause = analysis.get('root_cause', '')
        specific_indicators = ['timestamp', 'id', 'request', 'trace']
        if any(ind in root_cause.lower() for ind in specific_indicators):
            score += 0.2

        return min(1.0, score)

    def _evaluate_logical_consistency(self, analysis: Dict) -> float:
        """논리적 일관성 평가."""
        score = 0.5

        root_cause = analysis.get('root_cause', '')
        actions = analysis.get('actions', [])
        evidence = analysis.get('evidence', [])

        # 근본 원인과 액션의 연관성
        if root_cause and actions:
            root_cause_words = set(root_cause.lower().split())
            for action in actions:
                action_desc = action.get('description', '').lower()
                if any(word in action_desc for word in root_cause_words if len(word) > 4):
                    score += 0.1

        # 증거가 결론을 지지하는지
        if evidence and root_cause:
            evidence_text = ' '.join(str(e) for e in evidence).lower()
            root_words = [w for w in root_cause.lower().split() if len(w) > 4]
            if any(word in evidence_text for word in root_words):
                score += 0.2

        # 액션에 구체적인 파라미터가 있는지
        for action in actions:
            if action.get('parameters') and len(action.get('parameters', {})) > 0:
                score += 0.1
                break

        return min(1.0, score)

    def _evaluate_actionability(self, analysis: Dict) -> float:
        """실행 가능성 평가."""
        score = 0.0
        actions = analysis.get('actions', [])

        if not actions:
            return 0.0

        valid_action_types = {
            'lambda_restart', 'rds_parameter', 'auto_scaling',
            'eventbridge_event', 'notify', 'investigate'
        }

        for action in actions:
            action_type = action.get('type', '')

            if action_type in valid_action_types:
                score += 0.3

            params = action.get('parameters', {})
            if params:
                score += 0.2

                param_values = [str(v) for v in params.values()]
                placeholders = ['placeholder', 'xxx', 'todo', 'tbd']
                if not any(p in v.lower() for v in param_values for p in placeholders):
                    score += 0.2

        return min(1.0, score / max(1, len(actions)))

    def _evaluate_consistency(
        self,
        analysis: Dict,
        context: List[Dict]
    ) -> float:
        """이전 시도와의 일관성 평가."""
        if not context:
            return 0.9

        current_actions = set(
            action.get('type', '')
            for action in analysis.get('actions', [])
        )

        for prev in context:
            if prev.get('status') == 'failed':
                failed_actions = set(
                    action.get('type', '')
                    for action in prev.get('actions', [])
                )
                overlap = current_actions & failed_actions
                if overlap:
                    return 0.3

        return 0.9

    def _generate_suggestions(self, breakdown: Dict[str, float]) -> List[str]:
        """개선 제안 생성."""
        suggestions = []

        if breakdown['evidence_sufficiency'] < 0.6:
            suggestions.append(
                "Collect more specific log entries related to the anomaly"
            )
            suggestions.append("Include timestamps and request IDs in evidence")

        if breakdown['logical_consistency'] < 0.6:
            suggestions.append(
                "Ensure recommended actions directly address root cause"
            )
            suggestions.append("Verify evidence supports the stated conclusions")

        if breakdown['actionability'] < 0.6:
            suggestions.append(
                "Provide specific parameters for each recommended action"
            )
            suggestions.append(
                "Use supported action types (lambda_restart, rds_parameter, etc.)"
            )

        if breakdown['consistency'] < 0.6:
            suggestions.append("Avoid recommending previously failed actions")
            suggestions.append(
                "Consider alternative approaches if previous attempts failed"
            )

        return suggestions

    def _generate_reasoning(
        self,
        breakdown: Dict[str, float],
        overall: float
    ) -> str:
        """신뢰도 점수에 대한 reasoning 생성."""
        parts = [f"Overall confidence: {overall:.1%}", ""]

        for factor, score in breakdown.items():
            if score >= 0.8:
                status = "Strong"
            elif score >= 0.5:
                status = "Moderate"
            else:
                status = "Weak"
            parts.append(f"- {factor.replace('_', ' ').title()}: {status} ({score:.1%})")

        parts.append("")

        if overall >= self.AUTO_EXECUTE_THRESHOLD:
            parts.append("Recommendation: Safe for automatic execution")
        elif overall >= self.APPROVAL_THRESHOLD:
            parts.append("Recommendation: Requires human approval before execution")
        else:
            parts.append("Recommendation: Replan with additional context needed")

        return '\n'.join(parts)


# 사용 예시
if __name__ == "__main__":
    engine = ReflectionEngine()

    # 테스트 분석 결과
    test_analysis = {
        "root_cause": "Database connection pool exhausted due to connection leak",
        "evidence": [
            "RDS connection count exceeded 80% threshold at 14:32:00",
            "user-service logs show 'connection timeout' errors"
        ],
        "actions": [
            {
                "type": "rds_parameter",
                "description": "Increase max_connections",
                "parameters": {"parameter_name": "max_connections", "new_value": "200"}
            }
        ]
    }

    test_evidence = {
        "total_anomalies": 3,
        "representative_samples": []
    }

    result = engine.evaluate(test_analysis, test_evidence, [])

    print(f"Confidence: {result.confidence}")
    print(f"Requires Replan: {result.requires_replan}")
    print(f"\nReasoning:\n{result.reasoning}")
    print(f"\nSuggestions: {result.suggestions}")
