"""
Prompt Utilities for JSON Parsing and Context Management.

Helper functions for working with LLM responses.
"""

import json
import re
from typing import Any, Dict, Optional


def parse_json_response(response: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, handling common issues.

    Args:
        response: Raw LLM response string

    Returns:
        Parsed JSON as dictionary

    Raises:
        ValueError: If JSON cannot be parsed
    """
    # Try direct parsing first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    extracted = extract_code_block(response, "json")
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try fixing common issues
    fixed = _fix_common_json_issues(response)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Could not parse JSON from response: {response[:200]}...")


def extract_code_block(text: str, language: Optional[str] = None) -> Optional[str]:
    """
    Extract content from markdown code blocks.

    Args:
        text: Text containing code blocks
        language: Optional language specifier to match

    Returns:
        Extracted code content or None
    """
    if language:
        pattern = rf"```{language}\s*([\s\S]*?)```"
    else:
        pattern = r"```(?:\w+)?\s*([\s\S]*?)```"

    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()

    return None


def truncate_context(
    text: str,
    max_chars: int = 4000,
    preserve_start: int = 1000,
    preserve_end: int = 1000,
) -> str:
    """
    Truncate context while preserving important parts.

    Args:
        text: Text to truncate
        max_chars: Maximum characters to return
        preserve_start: Characters to preserve from start
        preserve_end: Characters to preserve from end

    Returns:
        Truncated text with middle section removed if needed
    """
    if len(text) <= max_chars:
        return text

    if preserve_start + preserve_end >= max_chars:
        return text[:max_chars]

    start = text[:preserve_start]
    end = text[-preserve_end:]
    removed = len(text) - preserve_start - preserve_end

    return f"{start}\n\n... [{removed} characters truncated] ...\n\n{end}"


def format_log_for_prompt(
    logs: list,
    max_logs: int = 50,
    max_message_length: int = 300,
) -> str:
    """
    Format log entries for inclusion in prompts.

    Args:
        logs: List of log entries
        max_logs: Maximum number of logs to include
        max_message_length: Maximum length per log message

    Returns:
        Formatted log string
    """
    lines = []

    for log in logs[:max_logs]:
        if isinstance(log, dict):
            timestamp = log.get("timestamp", "")
            level = log.get("log_level", log.get("level", "INFO"))
            message = log.get("message", str(log))
        else:
            timestamp = ""
            level = "INFO"
            message = str(log)

        # Truncate message
        if len(message) > max_message_length:
            message = message[:max_message_length] + "..."

        if timestamp:
            lines.append(f"[{timestamp}] [{level}] {message}")
        else:
            lines.append(f"[{level}] {message}")

    if len(logs) > max_logs:
        lines.append(f"... and {len(logs) - max_logs} more entries")

    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses rough approximation of ~4 characters per token.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return len(text) // 4


def _fix_common_json_issues(text: str) -> str:
    """
    Attempt to fix common JSON formatting issues.

    Args:
        text: Potentially malformed JSON

    Returns:
        Fixed JSON string
    """
    # Remove leading/trailing whitespace
    text = text.strip()

    # Remove markdown code block markers
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Fix trailing commas before closing brackets
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    # Fix single quotes to double quotes (basic)
    # Only if no double quotes exist
    if '"' not in text and "'" in text:
        text = text.replace("'", '"')

    # Fix Python booleans/None to JSON
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)

    return text


def build_context_window(
    primary_context: str,
    secondary_contexts: Optional[Dict[str, str]] = None,
    max_total_tokens: int = 8000,
) -> str:
    """
    Build a context window with priority-based inclusion.

    Args:
        primary_context: Main context (always included)
        secondary_contexts: Additional contexts with labels
        max_total_tokens: Maximum tokens for entire context

    Returns:
        Combined context string
    """
    primary_tokens = estimate_tokens(primary_context)
    result_parts = [primary_context]
    remaining_tokens = max_total_tokens - primary_tokens

    if secondary_contexts:
        for label, context in secondary_contexts.items():
            context_tokens = estimate_tokens(context)

            if context_tokens <= remaining_tokens:
                result_parts.append(f"\n## {label}\n{context}")
                remaining_tokens -= context_tokens
            elif remaining_tokens > 500:
                # Include truncated version
                truncated = truncate_context(
                    context,
                    max_chars=remaining_tokens * 4,
                    preserve_start=remaining_tokens * 2,
                    preserve_end=remaining_tokens * 2,
                )
                result_parts.append(f"\n## {label} (truncated)\n{truncated}")
                remaining_tokens = 0
                break

    return "\n".join(result_parts)
