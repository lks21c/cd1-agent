"""
Drift Analyzer with ReAct Pattern.

LLM-based root cause analysis for configuration drifts using
PLAN → ANALYZE → REFLECT → {REPLAN | COMPLETE} loop.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.agents.drift.models import (
    DriftAnalysisResult,
    DriftCauseAnalysis,
    DriftCauseCategory,
    DriftReflectionResult,
    DriftRemediationAction,
)
from src.agents.drift.prompts import (
    DRIFT_ANALYSIS_SYSTEM_PROMPT,
    build_drift_analysis_prompt,
    build_drift_plan_prompt,
    build_drift_reflection_prompt,
)
from src.agents.drift.services.drift_detector import DriftResult
from src.common.services.llm_client import LLMClient, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class AnalysisState:
    """State maintained during ReAct analysis loop."""

    drift_result: DriftResult
    baseline_config: Dict[str, Any]
    current_config: Dict[str, Any]
    resource_context: Optional[Dict[str, Any]] = None
    iteration: int = 1
    plan: Optional[str] = None
    analysis: Optional[DriftAnalysisResult] = None
    reflection: Optional[DriftReflectionResult] = None
    concerns: List[str] = None

    def __post_init__(self):
        if self.concerns is None:
            self.concerns = []


class BaseDriftAnalyzerProvider(ABC):
    """Abstract base class for drift analyzer providers."""

    @abstractmethod
    def plan(self, state: AnalysisState) -> str:
        """Create analysis plan based on drift context."""
        pass

    @abstractmethod
    def analyze(self, state: AnalysisState) -> DriftAnalysisResult:
        """Perform drift analysis using LLM."""
        pass

    @abstractmethod
    def reflect(self, state: AnalysisState) -> DriftReflectionResult:
        """Evaluate analysis quality and determine next steps."""
        pass


class RealDriftAnalyzerProvider(BaseDriftAnalyzerProvider):
    """Real implementation using LLM for drift analysis."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def plan(self, state: AnalysisState) -> str:
        """Generate investigation plan for drift analysis."""
        prompt = build_drift_plan_prompt(
            drift_result=state.drift_result.to_dict(),
            baseline_config=state.baseline_config,
            current_config=state.current_config,
            iteration=state.iteration,
            previous_concerns=state.concerns if state.iteration > 1 else None,
        )

        plan = self.llm_client.generate(
            prompt=prompt,
            system_prompt=DRIFT_ANALYSIS_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=1024,
        )

        logger.debug(f"Generated plan for iteration {state.iteration}: {plan[:200]}...")
        return plan

    def analyze(self, state: AnalysisState) -> DriftAnalysisResult:
        """Perform LLM-based drift analysis."""
        prompt = build_drift_analysis_prompt(
            drift_result=state.drift_result.to_dict(),
            baseline_config=state.baseline_config,
            current_config=state.current_config,
            resource_context=state.resource_context,
            iteration=state.iteration,
            previous_analysis=state.analysis.to_dict() if state.analysis else None,
        )

        result = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=DriftAnalysisResult,
            system_prompt=DRIFT_ANALYSIS_SYSTEM_PROMPT,
            temperature=0.3,
        )

        # Populate identifiers from drift result
        result.drift_id = f"{state.drift_result.resource_type}:{state.drift_result.resource_id}"
        result.resource_type = state.drift_result.resource_type
        result.resource_id = state.drift_result.resource_id

        logger.info(
            f"Analysis result: category={result.cause_analysis.category}, "
            f"confidence={result.confidence_score:.2f}"
        )
        return result

    def reflect(self, state: AnalysisState) -> DriftReflectionResult:
        """Evaluate analysis quality."""
        if not state.analysis:
            raise ValueError("No analysis to reflect on")

        prompt = build_drift_reflection_prompt(
            analysis=state.analysis.to_dict(),
            drift_result=state.drift_result.to_dict(),
            iteration=state.iteration,
            max_iterations=3,
        )

        result = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=DriftReflectionResult,
            system_prompt=DRIFT_ANALYSIS_SYSTEM_PROMPT,
            temperature=0.2,
        )

        logger.info(
            f"Reflection result: confidence={result.overall_confidence:.2f}, "
            f"needs_replan={result.needs_replan}"
        )
        return result


class MockDriftAnalyzerProvider(BaseDriftAnalyzerProvider):
    """Mock provider for testing."""

    def __init__(
        self,
        mock_category: DriftCauseCategory = DriftCauseCategory.MANUAL_CHANGE,
        mock_confidence: float = 0.85,
        mock_needs_replan: bool = False,
    ):
        self.mock_category = mock_category
        self.mock_confidence = mock_confidence
        self.mock_needs_replan = mock_needs_replan
        self.call_history: List[Dict[str, Any]] = []

    def plan(self, state: AnalysisState) -> str:
        """Return mock plan."""
        self.call_history.append({
            "method": "plan",
            "iteration": state.iteration,
        })
        return f"Mock investigation plan for iteration {state.iteration}"

    def analyze(self, state: AnalysisState) -> DriftAnalysisResult:
        """Return mock analysis result."""
        self.call_history.append({
            "method": "analyze",
            "iteration": state.iteration,
            "drift_id": f"{state.drift_result.resource_type}:{state.drift_result.resource_id}",
        })

        return DriftAnalysisResult(
            drift_id=f"{state.drift_result.resource_type}:{state.drift_result.resource_id}",
            resource_type=state.drift_result.resource_type,
            resource_id=state.drift_result.resource_id,
            cause_analysis=DriftCauseAnalysis(
                category=self.mock_category,
                root_cause="Mock root cause: Configuration was manually modified via AWS Console",
                likely_actor="user",
                evidence=[
                    "Field modification pattern suggests manual change",
                    "No recent IaC deployment detected",
                ],
            ),
            impact_assessment="Medium impact - affects resource scaling behavior",
            blast_radius=["downstream-service-a", "monitoring-alerts"],
            confidence_score=self.mock_confidence,
            urgency_score=0.6,
            remediations=[
                DriftRemediationAction(
                    action_type="revert_to_baseline",
                    priority=1,
                    description="Apply Terraform to restore baseline configuration",
                    command_hint="terraform apply -target=module.resource",
                    requires_approval=True,
                    rollback_steps=["terraform plan to verify changes"],
                    expected_outcome="Configuration restored to baseline state",
                ),
            ],
            requires_human_review=True,
            review_reason="Manual change detected - verify intention",
            reasoning="Mock analysis reasoning",
        )

    def reflect(self, state: AnalysisState) -> DriftReflectionResult:
        """Return mock reflection result."""
        self.call_history.append({
            "method": "reflect",
            "iteration": state.iteration,
        })

        return DriftReflectionResult(
            cause_plausibility=0.8,
            evidence_quality=0.75,
            remediation_practicality=0.85,
            risk_assessment=0.8,
            overall_confidence=self.mock_confidence,
            needs_replan=self.mock_needs_replan and state.iteration < 3,
            needs_human_review=True,
            concerns=["Verify with CloudTrail logs"] if self.mock_needs_replan else [],
            reasoning="Mock reflection reasoning",
        )


class DriftAnalyzer:
    """
    ReAct-based drift analyzer for root cause analysis.

    Implements PLAN → ANALYZE → REFLECT → {REPLAN | COMPLETE} loop
    for iterative drift analysis with quality validation.

    Usage:
        # With real LLM
        llm_client = LLMClient(provider=LLMProvider.VLLM, endpoint="...")
        analyzer = DriftAnalyzer(llm_client=llm_client)

        # With mock for testing
        analyzer = DriftAnalyzer(provider=LLMProvider.MOCK)

        # Analyze drift
        result = analyzer.analyze_drift(
            drift_result=drift,
            baseline_config=baseline,
            current_config=current,
        )
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        provider: LLMProvider = LLMProvider.MOCK,
        max_iterations: int = 3,
        confidence_threshold: float = 0.7,
        mock_category: DriftCauseCategory = DriftCauseCategory.MANUAL_CHANGE,
        mock_confidence: float = 0.85,
    ):
        """
        Initialize DriftAnalyzer.

        Args:
            llm_client: Pre-configured LLM client (takes precedence over provider)
            provider: LLM provider type if llm_client not provided
            max_iterations: Maximum ReAct iterations
            confidence_threshold: Minimum confidence to complete analysis
            mock_category: Mock cause category for testing
            mock_confidence: Mock confidence score for testing
        """
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold

        if llm_client:
            self._provider = RealDriftAnalyzerProvider(llm_client)
        elif provider == LLMProvider.MOCK:
            self._provider = MockDriftAnalyzerProvider(
                mock_category=mock_category,
                mock_confidence=mock_confidence,
            )
        else:
            # Create LLM client with specified provider
            client = LLMClient(provider=provider)
            self._provider = RealDriftAnalyzerProvider(client)

    def analyze_drift(
        self,
        drift_result: DriftResult,
        baseline_config: Dict[str, Any],
        current_config: Dict[str, Any],
        resource_context: Optional[Dict[str, Any]] = None,
    ) -> DriftAnalysisResult:
        """
        Perform ReAct-based drift analysis.

        Args:
            drift_result: Drift detection result
            baseline_config: Expected baseline configuration
            current_config: Current AWS configuration
            resource_context: Additional context (ARN, tags, etc.)

        Returns:
            DriftAnalysisResult with root cause analysis
        """
        logger.info(
            f"Starting drift analysis for {drift_result.resource_type}:{drift_result.resource_id}"
        )

        # Initialize state
        state = AnalysisState(
            drift_result=drift_result,
            baseline_config=baseline_config,
            current_config=current_config,
            resource_context=resource_context,
        )

        # ReAct Loop
        while state.iteration <= self.max_iterations:
            logger.info(f"ReAct iteration {state.iteration}/{self.max_iterations}")

            # PLAN: Create investigation plan
            try:
                state.plan = self._provider.plan(state)
            except Exception as e:
                logger.warning(f"Plan generation failed: {e}, continuing with analysis")
                state.plan = None

            # ANALYZE: Perform LLM analysis
            try:
                state.analysis = self._provider.analyze(state)
            except Exception as e:
                logger.error(f"Analysis failed at iteration {state.iteration}: {e}")
                # Return partial result on analysis failure
                return self._create_fallback_result(drift_result, str(e))

            # REFLECT: Evaluate analysis quality
            try:
                state.reflection = self._provider.reflect(state)
            except Exception as e:
                logger.warning(f"Reflection failed: {e}, accepting current analysis")
                # Accept analysis without reflection
                break

            # Check completion criteria
            if self._should_complete(state):
                logger.info(
                    f"Analysis complete at iteration {state.iteration} "
                    f"with confidence {state.analysis.confidence_score:.2f}"
                )
                break

            # REPLAN: Prepare for next iteration
            if state.reflection.needs_replan:
                state.concerns = state.reflection.concerns
                state.iteration += 1
                logger.info(f"Replanning due to concerns: {state.concerns}")
            else:
                # No replan needed, accept current analysis
                break

        # Finalize result
        final_result = state.analysis
        if state.reflection:
            final_result.requires_human_review = state.reflection.needs_human_review
            if state.reflection.concerns:
                final_result.review_reason = "; ".join(state.reflection.concerns)

        return final_result

    def _should_complete(self, state: AnalysisState) -> bool:
        """Determine if analysis should complete."""
        if not state.reflection:
            return True

        # Complete if reflection says no replan needed
        if not state.reflection.needs_replan:
            return True

        # Complete if confidence threshold met
        if state.reflection.overall_confidence >= self.confidence_threshold:
            return True

        # Complete if max iterations reached
        if state.iteration >= self.max_iterations:
            logger.warning(
                f"Max iterations reached with confidence {state.reflection.overall_confidence:.2f}"
            )
            return True

        return False

    def _create_fallback_result(
        self,
        drift_result: DriftResult,
        error_message: str,
    ) -> DriftAnalysisResult:
        """Create fallback result when analysis fails."""
        return DriftAnalysisResult(
            drift_id=f"{drift_result.resource_type}:{drift_result.resource_id}",
            resource_type=drift_result.resource_type,
            resource_id=drift_result.resource_id,
            cause_analysis=DriftCauseAnalysis(
                category=DriftCauseCategory.UNKNOWN,
                root_cause=f"Analysis failed: {error_message}",
                likely_actor="unknown",
                evidence=[],
            ),
            confidence_score=0.0,
            urgency_score=0.5,
            requires_human_review=True,
            review_reason=f"Automated analysis failed: {error_message}",
            reasoning="Fallback result due to analysis error",
        )

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        """Get call history (only available for mock provider)."""
        if isinstance(self._provider, MockDriftAnalyzerProvider):
            return self._provider.call_history
        return []


# Module-level convenience function
def analyze_drift(
    drift_result: DriftResult,
    baseline_config: Dict[str, Any],
    current_config: Dict[str, Any],
    llm_client: Optional[LLMClient] = None,
    resource_context: Optional[Dict[str, Any]] = None,
) -> DriftAnalysisResult:
    """
    Analyze drift root cause using LLM.

    Args:
        drift_result: Drift detection result
        baseline_config: Expected baseline configuration
        current_config: Current AWS configuration
        llm_client: Optional LLM client (uses mock if not provided)
        resource_context: Additional context

    Returns:
        DriftAnalysisResult with root cause analysis
    """
    analyzer = DriftAnalyzer(llm_client=llm_client)
    return analyzer.analyze_drift(
        drift_result=drift_result,
        baseline_config=baseline_config,
        current_config=current_config,
        resource_context=resource_context,
    )
