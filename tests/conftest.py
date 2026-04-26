"""
Mocks for Airflow imports so DAG structure tests run without a full Airflow install.
In production, Airflow is installed in the worker environment.
"""
import sys
from datetime import timedelta
from types import ModuleType
from unittest.mock import MagicMock


def _make_airflow_mocks():
    """Build a minimal fake airflow.sdk so we can import and inspect DAGs."""

    # ---- task decorator ----
    class _TaskDecorator:
        """Minimal @task decorator that records task_id and retries."""

        _registered: list = []

        def __init__(self, func=None, *, task_id=None, **kwargs):
            self._func = func
            self._task_id = task_id
            self._kwargs = kwargs
            if func is not None:
                self._register()

        def _register(self):
            _TaskDecorator._registered.append(self)

        def __call__(self, *args, **kwargs):
            if self._func is None and callable(args[0]):
                # Called as @task(task_id=...) — args[0] is the decorated function
                self._func = args[0]
                if self._task_id is None:
                    self._task_id = args[0].__name__
                self._register()
                return self
            # Called as the task itself during DAG wiring
            return _XComArg(self)

        @property
        def task_id(self):
            return self._task_id or (self._func.__name__ if self._func else "unknown")

        @property
        def retries(self):
            return self._kwargs.get("retries", _FakeDAG._current_default_args.get("retries", 0))

        @property
        def retry_delay(self):
            return self._kwargs.get(
                "retry_delay",
                _FakeDAG._current_default_args.get("retry_delay", timedelta(0)),
            )

        @property
        def downstream_task_ids(self):
            return _FakeDAG._dependencies.get(self.task_id, set())

    class _XComArg:
        """Placeholder returned when a task is 'called' during DAG wiring."""

        def __init__(self, task):
            self._task = task

    # ---- DAG context manager ----
    class _FakeDAG:
        _current_default_args: dict = {}
        _dependencies: dict = {}  # task_id -> set of downstream task_ids

        def __init__(self, dag_id, schedule=None, start_date=None, catchup=False,
                     default_args=None, tags=None, **kwargs):
            self.dag_id = dag_id
            self.schedule = schedule
            self._default_args = default_args or {}
            _FakeDAG._current_default_args = self._default_args
            _TaskDecorator._registered = []
            _FakeDAG._dependencies = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def tasks(self):
            return _TaskDecorator._registered

        @property
        def task_ids(self):
            return [t.task_id for t in _TaskDecorator._registered]

    # Patch dependency tracking: XComArg passed to a task means an upstream edge
    original_task_init = _TaskDecorator.__init__

    def _patched_call(self, *args, **kwargs):
        if self._func is None and callable(args[0]):
            self._func = args[0]
            if self._task_id is None:
                self._task_id = args[0].__name__
            self._register()
            return self
        # Detect upstream XComArgs in positional args
        for arg in args:
            if isinstance(arg, _XComArg):
                upstream_id = arg._task.task_id
                current_id = self._task_id or (self._func.__name__ if self._func else "")
                _FakeDAG._dependencies.setdefault(upstream_id, set()).add(current_id)
        # Also check kwargs values
        for v in kwargs.values():
            if isinstance(v, _XComArg):
                upstream_id = v._task.task_id
                current_id = self._task_id or (self._func.__name__ if self._func else "")
                _FakeDAG._dependencies.setdefault(upstream_id, set()).add(current_id)
        return _XComArg(self)

    _TaskDecorator.__call__ = _patched_call

    # ---- Build fake module tree ----
    sdk_mod = ModuleType("airflow.sdk")
    sdk_mod.DAG = _FakeDAG
    sdk_mod.task = _TaskDecorator

    airflow_mod = ModuleType("airflow")
    airflow_mod.sdk = sdk_mod

    return airflow_mod, sdk_mod


def pytest_configure(config):
    airflow_mod, sdk_mod = _make_airflow_mocks()
    sys.modules["airflow"] = airflow_mod
    sys.modules["airflow.sdk"] = sdk_mod
    # Stub out provider packages used inside task bodies (not executed in tests)
    for sub in [
        "airflow.providers",
        "airflow.providers.slack",
        "airflow.providers.slack.notifications",
        "airflow.providers.slack.notifications.slack_webhook",
        "airflow.providers.google",
        "airflow.providers.google.cloud",
        "airflow.providers.google.cloud.sensors",
        "airflow.providers.google.cloud.sensors.bigquery",
        "google",
        "google.cloud",
        "google.cloud.bigquery",
    ]:
        sys.modules[sub] = MagicMock()
