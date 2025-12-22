"""
HDSP Detection DAG - On-Prem Kubernetes Anomaly Detection.

This DAG triggers the HDSP Agent Lambda function every 5 minutes
to detect anomalies in On-Prem Kubernetes clusters via Prometheus metrics.
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


def check_k8s_anomalies_found(**context):
    """Check if K8s anomalies were found in detection result."""
    ti = context["ti"]
    detection_result = ti.xcom_pull(task_ids="detect_hdsp_anomalies")

    if detection_result:
        # Parse Lambda response
        response_payload = json.loads(detection_result.get("Payload", "{}"))
        body = json.loads(response_payload.get("body", "{}"))
        data = body.get("data", {})

        if data.get("anomalies_detected", False):
            severity = data.get("severity_breakdown", {})
            if severity.get("critical", 0) > 0 or severity.get("high", 0) > 0:
                return "start_hdsp_workflow"

    return "skip_hdsp_workflow"


with DAG(
    dag_id="bdp_hdsp_detection_dag",
    default_args=default_args,
    description="HDSP Agent - On-Prem K8s Prometheus Anomaly Detection",
    schedule_interval="*/5 * * * *",  # Every 5 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["cd1-agent", "hdsp", "kubernetes", "prometheus"],
    max_active_runs=1,
) as dag:

    # Task 1: Detect K8s anomalies via Prometheus
    detect_anomalies = LambdaInvokeFunctionOperator(
        task_id="detect_hdsp_anomalies",
        function_name="bdp-hdsp-detection",
        payload=json.dumps({
            "detection_type": "all",
        }),
        aws_conn_id="aws_default",
    )

    # Task 2: Branch based on detection result
    check_result = BranchPythonOperator(
        task_id="check_k8s_anomalies",
        python_callable=check_k8s_anomalies_found,
        provide_context=True,
    )

    # Task 3a: Start HDSP Step Functions workflow if anomalies found
    start_workflow = StepFunctionStartExecutionOperator(
        task_id="start_hdsp_workflow",
        state_machine_arn="{{ var.value.bdp_hdsp_workflow_arn }}",
        input=json.dumps({
            "source": "mwaa",
            "dag_id": "bdp_hdsp_detection_dag",
            "execution_date": "{{ ds }}",
        }),
        aws_conn_id="aws_default",
    )

    # Task 3b: Skip workflow if no critical/high anomalies
    skip_workflow = EmptyOperator(
        task_id="skip_hdsp_workflow",
    )

    # Task 4: End
    end = EmptyOperator(
        task_id="end",
        trigger_rule="none_failed_min_one_success",
    )

    # Define task dependencies
    detect_anomalies >> check_result
    check_result >> [start_workflow, skip_workflow]
    [start_workflow, skip_workflow] >> end
