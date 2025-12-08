"""
Analysis Prompts for BDP Agent.

이 모듈은 LLM(vLLM/Gemini) 호출을 위한 프롬프트 템플릿을 제공합니다.
hdsp_agent 패턴을 따라 프롬프트를 로직에서 분리합니다.

주요 프롬프트:
- ANALYSIS_TEMPLATE: 근본 원인 분석
- REPLAN_TEMPLATE: 실패 후 재분석
- REFLECTION_TEMPLATE: 분석 품질 평가
"""
from typing import Dict, List, Any, Optional
import json


class AnalysisPrompts:
    """분석 작업을 위한 프롬프트 템플릿."""

    ANALYSIS_SYSTEM_PROMPT = """You are an expert DevOps engineer specialized in:
- AWS infrastructure troubleshooting
- Log analysis and anomaly detection
- Root cause analysis
- Automated remediation strategies

You analyze system anomalies and provide actionable remediation recommendations.
Always respond in valid JSON format."""

    ANALYSIS_TEMPLATE = """## Task
Analyze the following system anomalies and provide root cause analysis with remediation recommendations.

## Anomaly Summary
{anomaly_summary}

## Log Samples
{log_samples}

## Relevant Knowledge
{knowledge_context}

{previous_attempts_section}

## Response Format
Respond with a JSON object containing:
```json
{{
    "root_cause": "Clear description of the identified root cause",
    "evidence": [
        "Evidence point 1 with specific log reference",
        "Evidence point 2 with metric correlation"
    ],
    "actions": [
        {{
            "type": "action_type",
            "description": "What this action does",
            "parameters": {{}},
            "priority": "high|medium|low",
            "estimated_impact": "Description of expected outcome"
        }}
    ],
    "confidence_factors": {{
        "evidence_strength": "strong|moderate|weak",
        "pattern_match": "exact|partial|inferred",
        "risk_level": "low|medium|high"
    }},
    "alternative_hypotheses": [
        "Alternative explanation 1",
        "Alternative explanation 2"
    ]
}}
```

## Supported Action Types
- lambda_restart: Restart a Lambda function
- rds_parameter: Modify RDS parameter
- auto_scaling: Adjust Auto Scaling settings
- eventbridge_event: Publish event for notification
- investigate: Request more information

## Important Guidelines
1. Base conclusions on provided evidence only
2. Prefer less invasive actions when confidence is moderate
3. Always include rollback considerations for destructive actions
4. If evidence is insufficient, use "investigate" action type"""

    REPLAN_TEMPLATE = """## Task
The previous remediation attempt did not fully resolve the issue. Reanalyze with new information.

## Original Analysis
{original_analysis}

## Previous Actions Taken
{previous_actions}

## Current Status
{current_status}

## New Observations
{new_observations}

## Instructions
1. Identify why the previous approach may have failed
2. Consider alternative root causes
3. Propose modified or new remediation actions
4. Avoid repeating failed approaches

Respond in the same JSON format as the original analysis."""

    REFLECTION_TEMPLATE = """## Task
Evaluate the quality of the following analysis.

## Analysis to Evaluate
{analysis}

## Available Evidence
{evidence}

## Evaluation Criteria
1. Evidence Sufficiency: Are conclusions supported by concrete evidence?
2. Logical Consistency: Do actions address the identified root cause?
3. Actionability: Are recommended actions specific and executable?
4. Risk Assessment: Are potential risks properly considered?

## Response Format
```json
{{
    "evaluation": {{
        "evidence_sufficiency": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "logical_consistency": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "actionability": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "risk_assessment": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }}
    }},
    "overall_confidence": 0.0-1.0,
    "improvement_suggestions": [
        "Suggestion 1",
        "Suggestion 2"
    ],
    "proceed_recommendation": "auto_execute|request_approval|replan"
}}
```"""

    def format_analysis_prompt(
        self,
        anomalies: List[Dict],
        log_summary: Dict,
        knowledge: str = "",
        previous_attempts: Optional[List[Dict]] = None
    ) -> str:
        """분석 프롬프트 포맷팅."""

        anomaly_summary = self._format_anomaly_summary(anomalies)
        log_samples = self._format_log_samples(log_summary)
        previous_section = ""

        if previous_attempts:
            previous_section = self._format_previous_attempts(previous_attempts)

        return self.ANALYSIS_TEMPLATE.format(
            anomaly_summary=anomaly_summary,
            log_samples=log_samples,
            knowledge_context=knowledge or "No specific knowledge base entries found.",
            previous_attempts_section=previous_section
        )

    def _format_anomaly_summary(self, anomalies: List[Dict]) -> str:
        """Anomaly 데이터 포맷팅."""
        lines = [f"Total anomalies detected: {len(anomalies)}"]

        by_type = {}
        for a in anomalies:
            atype = a.get('anomaly_type', 'unknown')
            if atype not in by_type:
                by_type[atype] = []
            by_type[atype].append(a)

        for atype, items in by_type.items():
            lines.append(f"\n### {atype}")
            lines.append(f"- Count: {len(items)}")
            if items:
                services = set(i.get('service_name', 'unknown') for i in items)
                lines.append(f"- Services affected: {', '.join(services)}")

        return '\n'.join(lines)

    def _format_log_samples(self, log_summary: Dict) -> str:
        """로그 요약 포맷팅."""
        if not log_summary:
            return "No log samples available."

        lines = []
        samples = log_summary.get('representative_samples', [])

        if samples:
            lines.append("### Representative Log Samples")
            for sample in samples[:5]:
                lines.append(f"\n**Type: {sample.get('type')}**")
                s = sample.get('sample', {})
                lines.append(f"- Service: {s.get('service')}")
                lines.append(f"- Level: {s.get('level')}")
                lines.append(f"- Message: {s.get('message', '')[:300]}")
                if s.get('key_metadata'):
                    lines.append(f"- Metadata: {json.dumps(s.get('key_metadata'))}")

        return '\n'.join(lines)

    def _format_previous_attempts(self, attempts: List[Dict]) -> str:
        """이전 시도 이력 포맷팅."""
        if not attempts:
            return ""

        lines = ["\n## Previous Attempts"]

        for i, attempt in enumerate(attempts, 1):
            lines.append(f"\n### Attempt {i}")
            lines.append(f"- Status: {attempt.get('status', 'unknown')}")
            lines.append(
                f"- Root Cause Identified: {attempt.get('root_cause', 'N/A')[:200]}"
            )

            actions = attempt.get('actions', [])
            if actions:
                lines.append("- Actions Taken:")
                for action in actions:
                    desc = action.get('description', '')[:100]
                    lines.append(f"  - {action.get('type')}: {desc}")

            if attempt.get('failure_reason'):
                lines.append(f"- Failure Reason: {attempt.get('failure_reason')}")

        return '\n'.join(lines)

    def format_replan_prompt(
        self,
        original_analysis: Dict,
        previous_actions: List[Dict],
        current_status: str,
        new_observations: str
    ) -> str:
        """Replan 프롬프트 포맷팅."""
        return self.REPLAN_TEMPLATE.format(
            original_analysis=json.dumps(original_analysis, indent=2),
            previous_actions=json.dumps(previous_actions, indent=2),
            current_status=current_status,
            new_observations=new_observations
        )

    def format_reflection_prompt(
        self,
        analysis: Dict,
        evidence: Dict
    ) -> str:
        """Reflection 프롬프트 포맷팅."""
        return self.REFLECTION_TEMPLATE.format(
            analysis=json.dumps(analysis, indent=2),
            evidence=json.dumps(evidence, indent=2)
        )


# 사용 예시
if __name__ == "__main__":
    prompts = AnalysisPrompts()

    # 테스트 데이터
    test_anomalies = [
        {
            "anomaly_type": "metric_anomaly",
            "service_name": "user-service",
            "sample_logs": [
                {"log_level": "ERROR", "message": "Connection timeout"}
            ]
        }
    ]

    test_log_summary = {
        "total_anomalies": 1,
        "representative_samples": [
            {
                "type": "metric_anomaly",
                "sample": {
                    "level": "ERROR",
                    "service": "user-service",
                    "message": "Connection timeout to database"
                }
            }
        ]
    }

    formatted = prompts.format_analysis_prompt(
        anomalies=test_anomalies,
        log_summary=test_log_summary
    )
    print(formatted)
