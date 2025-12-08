"""
Analysis Handler for BDP Agent.

이 핸들러는 LLM(vLLM/Gemini)을 사용하여 근본 원인 분석을 수행합니다.
- 계층적 로그 요약 (토큰 최적화)
- Knowledge Base 로딩
- Reflection을 통한 신뢰도 평가
"""
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .base_handler import BaseHandler, lambda_handler_wrapper
from ..services.llm_client import LLMClient
from ..services.reflection_engine import ReflectionEngine
from ..prompts.analysis_prompts import AnalysisPrompts


class AnalysisInput(BaseModel):
    """Analysis Lambda 입력 모델."""
    anomalies: List[Dict]
    workflow_id: str
    previous_attempts: List[Dict] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """분석 결과 모델."""
    root_cause: str
    evidence: List[str]
    recommended_actions: List[Dict]
    confidence: float
    reasoning: str
    requires_approval: bool


class AnalysisHandler(BaseHandler[AnalysisInput]):
    """LLM(vLLM/Gemini)을 사용한 근본 원인 분석 핸들러."""

    def __init__(self):
        super().__init__(AnalysisInput)
        self.llm = LLMClient()
        self.reflection = ReflectionEngine()
        self.prompts = AnalysisPrompts()

    def process(self, input_data: AnalysisInput, context: Any) -> Dict:
        """메인 분석 프로세스."""

        # 1. 로그 계층적 요약 (토큰 80-90% 절감)
        summarized_logs = self._hierarchical_summarize(input_data.anomalies)

        # 2. Knowledge Base 로딩 (Mini RAG)
        knowledge_context = self._load_knowledge_base(input_data.anomalies)

        # 3. 분석 프롬프트 포맷팅
        prompt = self.prompts.format_analysis_prompt(
            anomalies=input_data.anomalies,
            log_summary=summarized_logs,
            knowledge=knowledge_context,
            previous_attempts=input_data.previous_attempts
        )

        # 4. LLM 호출 (vLLM 또는 Gemini)
        raw_analysis = self.llm.invoke(prompt)

        # 5. Reflection을 통한 신뢰도 평가
        reflection_result = self.reflection.evaluate(
            analysis=raw_analysis,
            evidence=summarized_logs,
            context=input_data.anomalies
        )

        # 6. 결과 구조화
        result = AnalysisResult(
            root_cause=raw_analysis.get('root_cause', ''),
            evidence=raw_analysis.get('evidence', []),
            recommended_actions=raw_analysis.get('actions', []),
            confidence=reflection_result.confidence,
            reasoning=reflection_result.reasoning,
            requires_approval=reflection_result.confidence < 0.85
        )

        return {
            "analysis": result.model_dump(),
            "workflow_id": input_data.workflow_id,
            "auto_execute": not result.requires_approval,
            "reflection_details": {
                "confidence_breakdown": reflection_result.breakdown,
                "improvement_suggestions": reflection_result.suggestions
            }
        }

    def _hierarchical_summarize(self, anomalies: List[Dict]) -> Dict:
        """
        계층적 로그 요약으로 토큰 최적화.

        원본 로그 대비 80-90% 토큰 절감.
        """
        summary = {
            "total_anomalies": len(anomalies),
            "by_type": {},
            "by_service": {},
            "representative_samples": []
        }

        # 타입별 그룹화
        for anomaly in anomalies:
            atype = anomaly.get('anomaly_type', 'unknown')
            if atype not in summary['by_type']:
                summary['by_type'][atype] = {'count': 0, 'samples': []}
            summary['by_type'][atype]['count'] += 1

            # 샘플 로그 제한 (타입당 최대 3개)
            if len(summary['by_type'][atype]['samples']) < 3:
                sample_logs = anomaly.get('sample_logs', [])[:2]
                compressed_logs = [
                    {
                        'level': log.get('log_level'),
                        'service': log.get('service_name'),
                        'message': log.get('message', '')[:200],
                        'key_metadata': self._extract_key_metadata(
                            log.get('metadata', {})
                        )
                    }
                    for log in sample_logs
                ]
                summary['by_type'][atype]['samples'].extend(compressed_logs)

        # 서비스별 집계
        for anomaly in anomalies:
            service = anomaly.get('service_name', 'unknown')
            if service not in summary['by_service']:
                summary['by_service'][service] = 0
            summary['by_service'][service] += 1

        # 대표 샘플 선택 (전체에서 최대 5개)
        for atype, data in summary['by_type'].items():
            if data['samples']:
                summary['representative_samples'].append({
                    'type': atype,
                    'sample': data['samples'][0]
                })
                if len(summary['representative_samples']) >= 5:
                    break

        return summary

    def _extract_key_metadata(self, metadata: Dict) -> Dict:
        """핵심 메타데이터 필드만 추출."""
        key_fields = ['request_id', 'user_id', 'error_code', 'trace_id', 'status_code']
        return {k: v for k, v in metadata.items() if k in key_fields}

    def _load_knowledge_base(self, anomalies: List[Dict]) -> str:
        """로컬 Knowledge Base에서 관련 지식 로딩."""
        detected_patterns = set()

        for anomaly in anomalies:
            for log in anomaly.get('sample_logs', []):
                message = log.get('message', '').lower()
                # 패턴 매칭
                if 'timeout' in message:
                    detected_patterns.add('timeout')
                if 'connection' in message:
                    detected_patterns.add('connection')
                if 'memory' in message:
                    detected_patterns.add('memory')
                if 'lambda' in message:
                    detected_patterns.add('lambda')

        # 관련 playbook 로딩
        knowledge_parts = []
        knowledge_base_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'knowledge', 'playbooks'
        )

        for pattern in detected_patterns:
            playbook_path = os.path.join(knowledge_base_path, f'{pattern}.md')
            if os.path.exists(playbook_path):
                with open(playbook_path, 'r') as f:
                    knowledge_parts.append(f.read())

        return '\n---\n'.join(knowledge_parts) if knowledge_parts else ''


# Lambda 진입점
handler_instance = AnalysisHandler()


@lambda_handler_wrapper
def lambda_handler(event: Dict, context: Any, log) -> Dict:
    return handler_instance.handle(event, context)
