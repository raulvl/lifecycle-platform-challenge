"""DAG structure tests — verify shape without running tasks."""
import importlib
import sys
from datetime import timedelta


def _load_dag():
    # Ensure a fresh import each call
    if "dags.sms_reactivation_dag" in sys.modules:
        del sys.modules["dags.sms_reactivation_dag"]
    mod = importlib.import_module("dags.sms_reactivation_dag")
    return mod.dag


def test_dag_loads():
    dag = _load_dag()
    assert dag is not None


def test_dag_schedule():
    dag = _load_dag()
    assert dag.schedule == "0 5 * * *"


def test_dag_has_four_tasks():
    dag = _load_dag()
    assert len(dag.task_ids) == 4


def test_dag_task_ids():
    dag = _load_dag()
    assert set(dag.task_ids) == {
        "run_audience_query",
        "validate_audience",
        "execute_send",
        "log_and_notify",
    }


def test_dag_retries_and_retry_delay():
    dag = _load_dag()
    for task in dag.tasks:
        assert task.retries == 2, f"{task.task_id} retries should be 2"
        assert task.retry_delay == timedelta(minutes=5), f"{task.task_id} retry_delay should be 5m"


def test_dag_no_catchup():
    # catchup=True on a DAG with start_date=2024-01-01 would trigger hundreds of
    # backfill runs on first deploy, sending SMS to the full audience for each missed day.
    dag = _load_dag()
    assert dag.catchup is False


def test_dag_linear_dependencies():
    dag = _load_dag()
    task_map = {t.task_id: t for t in dag.tasks}

    assert task_map["run_audience_query"].downstream_task_ids == {"validate_audience"}
    assert task_map["validate_audience"].downstream_task_ids == {"execute_send"}
    assert task_map["execute_send"].downstream_task_ids == {"log_and_notify"}
    assert task_map["log_and_notify"].downstream_task_ids == set()
