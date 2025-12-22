"""
Drift Detection DAG - AWS Configuration Drift Detection.

This DAG triggers the Drift Agent Lambda function every 5 minutes
to detect configuration drifts between GitLab baselines and current AWS configurations.
"""

from datetime import datetime, timedelta
import json

from airflow import DAG
from airflow.providers.amazon.aws.operators.lambda_function import LambdaInvokeFunctionOperator
from airflow.providers.amazon.aws.operators.step_function import StepFunctionStartExecutionOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator


default_args = {
    "owner": "cd1-team",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def check_drifts_found(**context):
    """Check if configuration drifts were found in detection result."""
    ti = context["ti"]
    detection_result = ti.xcom_pull(task_ids="detect_config_drifts")

    if detection_result:
        # Parse Lambda response
        response_payload = json.loads(detection_result.get("Payload", "{}"))
        body = json.loads(response_payload.get("body", "{}"))
        data = body.get("data", {})

        if data.get("drifts_detected", False):
            severity = data.get("severity_summary", {})
            if severity.get("CRITICAL", 0) > 0 or severity.get("HIGH", 0) > 0:
                return "start_drift_workflow"

    return "skip_drift_workflow"


with DAG(
    dag_id="bdp_drift_detection_dag",
    default_args=default_args,
    description="Drift Agent - AWS Configuration Drift Detection vs GitLab Baseline",
    schedule_interval="*/5 * * * *",  # Every 5 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["cd1-agent", "drift", "configuration", "gitlab"],
    max_active_runs=1,
) as dag:

    # Task 1: Detect configuration drifts
    detect_drifts = LambdaInvokeFunctionOperator(
        task_id="detect_config_drifts",
        function_name="bdp-drift-detection",
        payload=json.dumps({
            "resource_types": ["EKS", "MSK", "S3", "EMR", "MWAA"],
            "severity_threshold": "LOW",
        }),
        aws_conn_id="aws_default",
    )

    # Task 2: Branch based on detection result
    check_result = BranchPythonOperator(
        task_id="check_config_drifts",
        python_callable=check_drifts_found,
        provide_context=True,
    )

    # Task 3a: Start Drift Step Functions workflow if drifts found
    start_workflow = StepFunctionStartExecutionOperator(
        task_id="start_drift_workflow",
        state_machine_arn="{{ var.value.bdp_drift_workflow_arn }}",
        input=json.dumps({
            "source": "mwaa",
            "dag_id": "bdp_drift_detection_dag",
            "execution_date": "{{ ds }}",
        }),
        aws_conn_id="aws_default",
    )

    # Task 3b: Skip workflow if no critical/high drifts
    skip_workflow = EmptyOperator(
        task_id="skip_drift_workflow",
    )

    # Task 4: End
    end = EmptyOperator(
        task_id="end",
        trigger_rule="none_failed_min_one_success",
    )

    # Define task dependencies
    detect_drifts >> check_result
    check_result >> [start_workflow, skip_workflow]
    [start_workflow, skip_workflow] >> end
