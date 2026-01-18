# Cost Agent Separation Notice

## Overview

The Cost Agent functionality has been separated from the BDP Agent as of this update.

## Changes Made

1. **BDP Agent (`src/agents/bdp/handler.py`)**
   - Removed `CostAnomalyDetector` and `CostExplorerClient` imports
   - Removed `cost_detector` and `cost_client` initialization
   - Removed `_detect_cost_anomalies()` method
   - Removed `_create_cost_anomaly_record()` method
   - Removed `cost_anomaly` from valid detection types
   - Updated `_run_scheduled_detection()` to exclude cost detection

2. **Cost Agent (Standalone)**
   - Located at `src/agents/cost/`
   - Contains independent cost anomaly detection functionality
   - Uses Luminol-based anomaly detection
   - Integrates with AWS Cost Explorer API

## Rationale

- **Separation of Concerns**: Cost monitoring has different operational requirements
- **Independent Scaling**: Cost analysis can run on different schedules
- **Cleaner Architecture**: Each agent focuses on a single domain
- **Easier Maintenance**: Updates to cost detection don't affect BDP agent

## Usage

### BDP Agent
```python
# Now focuses on log, metric, and pattern-based detection
from src.agents.bdp.handler import handler

event = {
    "detection_type": "log_anomaly",  # or "metric_anomaly", "pattern_anomaly"
    "service_name": "my-service"
}
```

### Cost Agent (Standalone)
```python
from src.agents.cost.handler import handler

event = {
    "detection_type": "cost_anomaly",
    "days": 30
}
```

## Migration Notes

If you were previously using `detection_type: "cost_anomaly"` with BDP Agent:
- Use the standalone Cost Agent instead
- Deploy as a separate Lambda function
- Configure separate triggers (EventBridge schedule, MWAA DAG)

## Files Preserved

- `src/agents/cost/services/anomaly_detector.py` - Luminol-based detection
- `src/agents/cost/services/cost_explorer_client.py` - AWS Cost Explorer integration
- `src/agents/cost/handler.py` - Standalone Lambda handler
