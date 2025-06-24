import json
from dataclasses import InitVar, asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from smolagents import RunResult


@dataclass
class TaskOutput:
    """A data object to store the flattened results of a single task run."""

    # The type hint correctly allows for a string, a RunResult, or None.
    source_result: InitVar[Optional[Union[str, "RunResult", Any]]] = None

    # --- Evaluation Fields ---
    score: float = 0.0
    eval_error: Optional[str] = None
    error_log_path: Optional[str] = None

    # --- Agent Run Results (Populated by __post_init__) ---
    output: Optional[Any] = None
    state: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    total_tokens: Optional[Dict[str, int]] = None
    total_timing: Optional[Dict[str, Any]] = None

    def __post_init__(self, source_result: Optional[Union[str, "RunResult"]]):
        """
        Automatically called after __init__. It processes the source_result
        and populates the TaskOutput fields, including formatting timing data.
        """
        if source_result is None:
            return

        # This logic now works correctly for a RunResult object...
        if isinstance(source_result, RunResult):
            self.output = source_result.output
            self.state = source_result.state
            self.messages = source_result.messages
            self.total_tokens = source_result.token_usage.dict() if source_result.token_usage else None

            timing_data = source_result.timing.dict() if source_result.timing else None

            if timing_data and timing_data.get("duration") is not None:
                try:
                    timing_data["duration"] = round(float(timing_data["duration"]), 2)
                except (ValueError, TypeError):
                    pass
            self.total_timing = timing_data
        else:
            self.output = source_result


@dataclass
class TaskInput:
    """
    Defines a task's input specifications and manages its execution results
    through a contained TaskOutput object.
    """

    uid: str
    tool: str
    prompt: str
    root_dir: Path
    results_root_dir: Path
    steps: int = 6
    dependencies: List[str] = field(default_factory=list)
    config: List[Dict[str, Any]] = field(default_factory=list)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    counterpart: Optional[str] = None
    source: List[str] = field(default_factory=list)
    related_apps: List[str] = field(default_factory=list)
    output: TaskOutput = field(default_factory=TaskOutput, repr=False)

    @property
    def container_name(self) -> str:
        return f"sandbox-{self.uid[:12]}"

    @property
    def task_dir(self) -> Path:
        return self.root_dir / self.tool / self.uid

    @property
    def result_dir(self) -> Path:
        return self.results_root_dir / self.tool / self.uid

    @classmethod
    def from_file(cls, tool: str, uid: str, root: Path, results_root: Path) -> "TaskInput":
        """Factory method to load a task specification from a JSON file."""
        task_dir = root / tool / uid
        meta_path = task_dir / f"{uid}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        return cls(
            uid=uid,
            tool=tool,
            root_dir=root,
            results_root_dir=results_root,
            prompt=meta["instruction"],
            steps=meta.get("action_number", 6),
            dependencies=meta.get("dependencies", ["*"]),
            config=meta.get("config", []),
            evaluation=meta.get("evaluation", {}),
            tags=meta.get("tags", []),
            counterpart=meta.get("counterpart", None),
            source=meta.get("source", []),
            related_apps=meta.get("related_apps", []),
        )

    def save_result_summary(self):
        """Saves the final task summary to a JSON file with a unique name."""
        self.result_dir.mkdir(parents=True, exist_ok=True)

        # 1. Convert the entire TaskInput instance to a dictionary
        summary_data = asdict(self)

        # 2. The 'output' field is already a dictionary, but we want it under the key "results"
        summary_data["results"] = summary_data.pop("output")

        # 3. Remove fields that are not useful for the summary or not JSON-serializable
        summary_data.pop("root_dir", None)
        summary_data.pop("results_root_dir", None)

        # 4. Save the dictionary
        summary_path = self.result_dir / "summary.json"
        summary_path.write_text(json.dumps(summary_data, indent=2, default=str), encoding="utf-8")
