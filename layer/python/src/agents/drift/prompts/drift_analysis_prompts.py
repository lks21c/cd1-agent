"""
Drift Analysis Prompts for LLM-based Root Cause Analysis.

Prompts for analyzing configuration drifts and determining root causes.
"""

import json
from typing import Any, Dict, List, Optional


DRIFT_ANALYSIS_SYSTEM_PROMPT = """You are an expert AWS infrastructure engineer specializing in configuration drift analysis.
Your role is to analyze configuration drifts between expected baselines and current AWS resource states.

When analyzing drifts:
1. Identify the most likely cause (manual change, auto-scaling, deployment drift, etc.)
2. Determine who/what likely made the change (user, automation, AWS maintenance)
3. Assess the impact severity and blast radius
4. Recommend specific remediation actions
5. Consider compliance and security implications

Categories of drift causes:
- MANUAL_CHANGE: Someone modified via Console, CLI, or SDK directly
- AUTO_SCALING: ASG, HPA, or similar scaling mechanism
- MAINTENANCE_WINDOW: AWS automatic maintenance or patching
- DEPLOYMENT_DRIFT: IaC (Terraform/CDK) state vs actual mismatch
- SECURITY_PATCH: Automatic security updates
- OPERATOR_ERROR: Misconfiguration by operator
- UNKNOWN: Insufficient evidence to determine

Confidence scoring guidelines:
- 0.85+: Clear evidence of cause with corroborating signals
- 0.70-0.84: Strong hypothesis with some supporting evidence
- 0.50-0.69: Reasonable hypothesis but needs investigation
- Below 0.50: Insufficient evidence, recommend manual review

Always provide actionable remediation steps with specific commands when possible.
Respond ONLY with valid JSON matching the requested schema."""


def build_drift_analysis_prompt(
    drift_result: Dict[str, Any],
    baseline_config: Dict[str, Any],
    current_config: Dict[str, Any],
    resource_context: Optional[Dict[str, Any]] = None,
    iteration: int = 1,
    previous_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the main drift analysis prompt.

    Args:
        drift_result: Detected drift information
        baseline_config: Expected baseline configuration
        current_config: Current AWS configuration
        resource_context: Additional context (ARN, tags, etc.)
        iteration: Current ReAct iteration number
        previous_analysis: Previous analysis attempt (for replanning)

    Returns:
        Formatted prompt string
    """
    # Format drifted fields
    drifted_fields_str = ""
    if "drifted_fields" in drift_result:
        for field in drift_result.get("drifted_fields", []):
            if isinstance(field, dict):
                drifted_fields_str += f"""
- **{field.get('field_path', 'unknown')}**
  - Type: {field.get('drift_type', 'MODIFIED')}
  - Baseline: {field.get('baseline_value', 'N/A')}
  - Current: {field.get('current_value', 'N/A')}
  - Severity: {field.get('severity', 'MEDIUM')}
"""

    # Build context section
    context_str = ""
    if resource_context:
        context_str = f"""
## Resource Context
- ARN: {resource_context.get('resource_arn', 'N/A')}
- Baseline Version: {resource_context.get('baseline_version', 'N/A')}
- Region: {resource_context.get('region', 'N/A')}
- Tags: {json.dumps(resource_context.get('tags', {}), indent=2)}
"""

    # Build iteration context
    iteration_str = ""
    if iteration > 1 and previous_analysis:
        iteration_str = f"""
## Previous Analysis Attempt (Iteration {iteration - 1})
The previous analysis had low confidence or quality issues:
- Previous confidence: {previous_analysis.get('confidence_score', 0.0)}
- Issues: {previous_analysis.get('concerns', [])}

Please provide a more thorough analysis with better evidence.
"""

    prompt = f"""# Configuration Drift Analysis Request

## Resource Information
- Resource Type: {drift_result.get('resource_type', 'unknown')}
- Resource ID: {drift_result.get('resource_id', 'unknown')}
- Detection Time: {drift_result.get('detection_timestamp', 'N/A')}
- Max Severity: {drift_result.get('max_severity', 'MEDIUM')}
{context_str}

## Detected Drifts
{drifted_fields_str if drifted_fields_str else 'No specific fields provided'}

## Baseline Configuration (Expected)
```json
{json.dumps(baseline_config, indent=2, default=str)}
```

## Current Configuration (Actual)
```json
{json.dumps(current_config, indent=2, default=str)}
```
{iteration_str}

## Analysis Task

Analyze this configuration drift and determine:

1. **Root Cause Category**: What type of change caused this drift?
2. **Root Cause Explanation**: Detailed explanation of why this happened
3. **Likely Actor**: Who or what made this change (user/system/automation/aws)
4. **Evidence**: List specific evidence supporting your conclusion
5. **Impact Assessment**: What is the impact of this drift?
6. **Blast Radius**: What other systems might be affected?
7. **Urgency**: How urgent is remediation (0.0-1.0)?
8. **Confidence**: How confident are you in this analysis (0.0-1.0)?
9. **Remediation Actions**: Specific steps to resolve this drift

Consider:
- Is this a security-critical change (encryption, public access)?
- Could this be intentional (auto-scaling, maintenance)?
- What IaC tools might be managing this resource?
- Are there compliance implications?

Respond with a JSON object matching the DriftAnalysisResult schema."""

    return prompt


def build_drift_reflection_prompt(
    analysis: Dict[str, Any],
    drift_result: Dict[str, Any],
    iteration: int,
    max_iterations: int = 3,
) -> str:
    """
    Build the reflection prompt to evaluate analysis quality.

    Args:
        analysis: The analysis result to evaluate
        drift_result: Original drift detection result
        iteration: Current iteration number
        max_iterations: Maximum allowed iterations

    Returns:
        Formatted reflection prompt
    """
    prompt = f"""# Drift Analysis Quality Evaluation

## Analysis to Evaluate
- Resource: {drift_result.get('resource_type', 'unknown')}:{drift_result.get('resource_id', 'unknown')}
- Detected Severity: {drift_result.get('max_severity', 'MEDIUM')}
- Analysis Confidence: {analysis.get('confidence_score', 0.0)}

### Cause Analysis
- Category: {analysis.get('cause_analysis', {}).get('category', 'unknown')}
- Root Cause: {analysis.get('cause_analysis', {}).get('root_cause', 'N/A')}
- Evidence: {analysis.get('cause_analysis', {}).get('evidence', [])}

### Remediation Plan
{json.dumps(analysis.get('remediations', []), indent=2)}

## Evaluation Criteria

Rate each criterion from 0.0 to 1.0:

1. **Cause Plausibility** (cause_plausibility):
   - Is the identified cause realistic given the evidence?
   - Does the category match the drift pattern?
   - Is the actor identification reasonable?

2. **Evidence Quality** (evidence_quality):
   - Is there sufficient evidence for the conclusion?
   - Are the evidence points specific and relevant?
   - Could the evidence support alternative causes?

3. **Remediation Practicality** (remediation_practicality):
   - Are the remediation steps specific and actionable?
   - Are commands/procedures provided where applicable?
   - Is the rollback plan reasonable?

4. **Risk Assessment** (risk_assessment):
   - Is the impact assessment accurate?
   - Is the blast radius correctly identified?
   - Are security implications considered?

## Decision Rules

- **needs_replan = True** if:
  - Any score < 0.6
  - Critical gaps in reasoning
  - Evidence contradicts conclusion
  - Security implications not addressed for security drifts

- **needs_human_review = True** if:
  - Confidence < 0.7
  - Security-related drift
  - Multiple possible causes
  - Remediation has high risk

## Iteration Context
- Current Iteration: {iteration}/{max_iterations}
- Iterations Remaining: {max_iterations - iteration}

If this is the last iteration, focus on providing the best assessment even with lower confidence.

Respond with a JSON object matching the DriftReflectionResult schema."""

    return prompt


def build_drift_plan_prompt(
    drift_result: Dict[str, Any],
    baseline_config: Dict[str, Any],
    current_config: Dict[str, Any],
    iteration: int = 1,
    previous_concerns: Optional[List[str]] = None,
) -> str:
    """
    Build the planning prompt for drift investigation.

    Args:
        drift_result: Detected drift information
        baseline_config: Expected baseline configuration
        current_config: Current AWS configuration
        iteration: Current iteration number
        previous_concerns: Concerns from previous reflection

    Returns:
        Formatted planning prompt
    """
    concerns_str = ""
    if previous_concerns and iteration > 1:
        concerns_str = f"""
## Previous Analysis Issues
The previous analysis had the following concerns:
{chr(10).join(f'- {c}' for c in previous_concerns)}

Focus on addressing these issues in the next analysis.
"""

    prompt = f"""# Drift Analysis Planning

## Drift Summary
- Resource: {drift_result.get('resource_type', 'unknown')}:{drift_result.get('resource_id', 'unknown')}
- Drift Count: {len(drift_result.get('drifted_fields', []))}
- Max Severity: {drift_result.get('max_severity', 'MEDIUM')}
{concerns_str}

## Investigation Plan

Based on the drift details, create an analysis plan:

1. **Primary Hypothesis**: What is the most likely cause?
2. **Evidence to Look For**: What signals support this hypothesis?
3. **Alternative Causes**: What other causes should be considered?
4. **Key Questions**: What questions need answers?
5. **Analysis Focus**: What aspects need the most attention?

Consider:
- Field names that changed (scaling_config → auto-scaling, encryption → security)
- Severity level (CRITICAL/HIGH → security focus)
- Resource type patterns (EKS node groups → scaling, S3 public_access → security)

Respond with a brief analysis plan (2-3 sentences per point)."""

    return prompt
