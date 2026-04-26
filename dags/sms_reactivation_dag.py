"""
SMS Reactivation Campaign DAG
Schedule: daily at 05:00 UTC
SLA:      must complete by 08:00 UTC (3-hour window)
Retries:  2 per task, 5-minute delay
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pendulum
from airflow.sdk import DAG, task

logger = logging.getLogger(__name__)

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "sla": timedelta(hours=3),  # 5 AM start + 3 h = 8 AM SLA deadline
}

with DAG(
    dag_id="sms_reactivation",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=default_args,
    tags=["lifecycle", "sms"],
) as dag:

    @task(task_id="run_audience_query")
    def run_audience_query(**context) -> dict:
        """Run audience segmentation query and export to a date-stamped staging table."""
        from google.cloud import bigquery

        run_date = context["ds"]  # YYYY-MM-DD — stable, ensures idempotency on re-runs
        staging_table = f"lifecycle.sms_reactivation_audience_{run_date.replace('-', '')}"

        client = bigquery.Client()
        with open("sql/audience_segmentation.sql") as f:
            query = f.read()

        # CREATE OR REPLACE makes this task safely re-runnable
        job = client.query(f"CREATE OR REPLACE TABLE `{staging_table}` AS\n{query}")
        job.result()

        row_count = next(
            client.query(f"SELECT COUNT(*) AS n FROM `{staging_table}`").result()
        )["n"]

        logger.info("run_audience_query staging_table=%s row_count=%d", staging_table, row_count)
        return {"staging_table": staging_table, "row_count": row_count}

    @task(task_id="validate_audience")
    def validate_audience(query_result: dict) -> dict:
        """Abort if audience is empty or exceeds 2× the 7-day rolling average (data anomaly guard)."""
        from google.cloud import bigquery

        row_count = query_result["row_count"]
        if row_count == 0:
            raise ValueError("Audience is empty — aborting send to avoid a no-op campaign run")

        client = bigquery.Client()
        rows = list(
            client.query(
                """
                SELECT AVG(audience_size) AS avg_size
                FROM lifecycle.campaign_runs
                WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                  AND campaign_type = 'sms_reactivation'
                """
            ).result()
        )
        if rows and rows[0]["avg_size"]:
            avg = rows[0]["avg_size"]
            if row_count > avg * 2:
                raise ValueError(
                    f"Audience size {row_count} is >2× the 7-day avg ({avg:.0f}). "
                    "Possible data pipeline issue — halting before send."
                )

        logger.info("validate_audience row_count=%d passed", row_count)
        return query_result

    @task(task_id="execute_send")
    def execute_send(validated: dict) -> dict:
        """Fetch audience from staging and execute batched ESP send."""
        from google.cloud import bigquery

        from pipeline.campaign_sender import execute_campaign_send
        from pipeline.esp_client import ESPClient

        client = bigquery.Client()
        staging_table = validated["staging_table"]
        rows = list(client.query(f"SELECT * FROM `{staging_table}`").result())
        audience = [dict(row) for row in rows]

        # campaign_id encodes the run date so dedup keys are stable across retries
        run_date = staging_table.split("_")[-1]
        campaign_id = f"sms_reactivation_{run_date}"

        metrics = execute_campaign_send(
            campaign_id=campaign_id,
            audience=audience,
            esp_client=ESPClient(),
        )
        logger.info("execute_send metrics=%s", metrics)
        return metrics

    @task(task_id="log_and_notify")
    def log_and_notify(send_metrics: dict, **context) -> None:
        """Write results to reporting table and post Slack summary."""
        from google.cloud import bigquery

        run_date = context["ds"]
        total = (
            send_metrics["total_sent"]
            + send_metrics["total_failed"]
            + send_metrics["total_skipped"]
        )

        client = bigquery.Client()
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("run_date", "DATE", run_date),
                bigquery.ScalarQueryParameter("campaign_type", "STRING", "sms_reactivation"),
                bigquery.ScalarQueryParameter("audience_size", "INT64", total),
                bigquery.ScalarQueryParameter("total_sent", "INT64", send_metrics["total_sent"]),
                bigquery.ScalarQueryParameter("total_failed", "INT64", send_metrics["total_failed"]),
                bigquery.ScalarQueryParameter("total_skipped", "INT64", send_metrics["total_skipped"]),
                bigquery.ScalarQueryParameter("elapsed_seconds", "FLOAT64", send_metrics["elapsed_seconds"]),
            ]
        )
        client.query(
            """
            INSERT INTO lifecycle.campaign_runs
                (run_date, campaign_type, audience_size,
                 total_sent, total_failed, total_skipped, elapsed_seconds)
            VALUES (
                @run_date, @campaign_type, @audience_size,
                @total_sent, @total_failed, @total_skipped, @elapsed_seconds
            )
            """,
            job_config=job_config,
        ).result()

        message = (
            f":envelope: *SMS Reactivation* — {run_date}\n"
            f"Sent: {send_metrics['total_sent']} | "
            f"Failed: {send_metrics['total_failed']} | "
            f"Skipped (deduped): {send_metrics['total_skipped']}\n"
            f"Elapsed: {send_metrics['elapsed_seconds']:.1f}s"
        )
        logger.info("log_and_notify message=%s", message)
        # Wire Slack via AIRFLOW_CONN_SLACK_WEBHOOK env var in production:
        # SlackWebhookNotifier(text=message).notify(context)

    # --- Task dependencies (linear: 1 → 2 → 3 → 4) ---
    _result = run_audience_query()
    _validated = validate_audience(_result)
    _metrics = execute_send(_validated)
    log_and_notify(_metrics)
