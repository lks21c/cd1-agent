#!/bin/bash
# Setup EventBridge for CD1 Agent notifications
# Shared across all agents (BDP, Cost, HDSP, Drift)
# Executed automatically when LocalStack starts

set -e

echo "=== Setting up EventBridge ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"

# Create custom event bus for CD1 Agent
awslocal events create-event-bus \
    --name cd1-agent-events \
    --region "$REGION" 2>/dev/null || echo "Event bus cd1-agent-events already exists"

echo "Created event bus: cd1-agent-events"

# ============================================================================
# BDP Agent Rules
# ============================================================================

# Create rule for BDP anomaly detection events
awslocal events put-rule \
    --name cd1-bdp-anomaly-detection \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.bdp", "cd1-agent.bdp"],
        "detail-type": ["AnomalyDetected", "Anomaly Detected"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-bdp-anomaly-detection"

# Create rule for BDP critical alerts
awslocal events put-rule \
    --name cd1-bdp-critical-alerts \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.bdp", "cd1-agent.bdp"],
        "detail-type": ["CriticalAlert", "Critical Alert"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-bdp-critical-alerts"

# ============================================================================
# Cost Agent Rules
# ============================================================================

# Create rule for Cost anomaly detection events
awslocal events put-rule \
    --name cd1-cost-anomaly-detection \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.cost", "cd1-agent.cost"],
        "detail-type": ["Cost Anomaly Detected", "CostAnomalyDetected"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-cost-anomaly-detection"

# Create rule for Cost critical alerts (budget overruns)
awslocal events put-rule \
    --name cd1-cost-critical-alerts \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.cost", "cd1-agent.cost"],
        "detail-type": ["Cost Critical Alert", "BudgetExceeded"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-cost-critical-alerts"

# ============================================================================
# HDSP Agent Rules
# ============================================================================

# Create rule for HDSP anomaly detection events
awslocal events put-rule \
    --name cd1-hdsp-anomaly-detection \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.hdsp", "cd1-agent.hdsp"],
        "detail-type": ["HDSP Anomaly Detected", "K8sAnomalyDetected"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-hdsp-anomaly-detection"

# ============================================================================
# Drift Agent Rules
# ============================================================================

# Create rule for Drift detection events
awslocal events put-rule \
    --name cd1-drift-detection \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.drift", "cd1-agent.drift"],
        "detail-type": ["Drift Detected", "ConfigurationDrift"]
    }' \
    --state ENABLED \
    --region "$REGION" 2>/dev/null || true

echo "Created rule: cd1-drift-detection"

# List all rules to verify
awslocal events list-rules \
    --event-bus-name cd1-agent-events \
    --region "$REGION"

echo "=== EventBridge Setup Complete ==="
