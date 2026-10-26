"""
simulation/schema.py
Data contracts and schema definitions for the GenoTrack Virtual Breeding Program simulator.
Defines:
  1. LedgerRow and LedgerSchema for tracking continuous simulation ticks.
  2. ScenarioConfig, ScenarioEvent, and EventType for storyline event execution.
"""
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class EventType(str, Enum):
    COVARIATE_SHIFT = "covariate_shift"
    GENOTYPE_SHIFT = "genotype_shift"
    CONCEPT_DRIFT = "concept_drift"
    DATA_QUALITY = "data_quality"


class ScenarioEvent(BaseModel):
    tick: int = Field(..., ge=0, description="Virtual season tick at which the event occurs")
    type: EventType = Field(..., description="Categorized event type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Event-specific parameters")

    @field_validator("type", mode="before")
    @classmethod
    def validate_event_type(cls, v: Any) -> EventType:
        if isinstance(v, EventType):
            return v
        if isinstance(v, str):
            try:
                return EventType(v.lower())
            except ValueError:
                valid_types = [e.value for e in EventType]
                raise ValueError(f"Unknown event type '{v}'. Allowed types: {valid_types}")
        raise ValueError(f"Invalid type format for event: {v}")


class ScenarioConfig(BaseModel):
    seed: int = Field(default=42, description="Random seed for deterministic simulation")
    ticks: int = Field(default=16, ge=1, description="Total number of virtual seasons to simulate")
    label_lag: int = Field(default=1, ge=0, description="Season delay before harvest ground-truth labels arrive")
    cohort_size: int = Field(default=300, ge=10, description="Number of plant accessions generated per cohort")
    parent_policy: Literal["random", "top_predicted"] = Field(
        default="top_predicted",
        description="Breeding selection policy for generating progeny"
    )
    events: List[ScenarioEvent] = Field(default_factory=list, description="Storyline sequence of injected events")

    @model_validator(mode="after")
    def validate_event_ticks(self) -> "ScenarioConfig":
        for event in self.events:
            if event.tick >= self.ticks:
                raise ValueError(
                    f"Event at tick {event.tick} exceeds total scenario ticks ({self.ticks})."
                )
        return self

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "ScenarioConfig":
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found at: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid scenario YAML structure at {path}")
        return cls(**data)


class LedgerRow(BaseModel):
    tick: int = Field(..., ge=0)
    scenario_event: Optional[str] = Field(default=None)
    n_lines: int = Field(..., ge=0)
    covariate_drift_score: float = Field(default=0.0)
    genotype_drift_score: float = Field(default=0.0)
    prediction_drift_score: float = Field(default=0.0)
    labels_arrived_for_tick: Optional[int] = Field(default=None)
    realized_rmse: Optional[float] = Field(default=None)
    realized_r: Optional[float] = Field(default=None)
    trigger_fired: bool = Field(default=False)
    trigger_reason: Optional[str] = Field(default=None)
    retrain_run_id: Optional[str] = Field(default=None)
    champion_version: str = Field(default="1")
    challenger_version: Optional[str] = Field(default=None)
    gate_result: Optional[str] = Field(default=None)
    promoted: bool = Field(default=False)
    frozen_baseline_rmse: Optional[float] = Field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


LEDGER_COLUMNS = [
    "tick",
    "scenario_event",
    "n_lines",
    "covariate_drift_score",
    "genotype_drift_score",
    "prediction_drift_score",
    "labels_arrived_for_tick",
    "realized_rmse",
    "realized_r",
    "trigger_fired",
    "trigger_reason",
    "retrain_run_id",
    "champion_version",
    "challenger_version",
    "gate_result",
    "promoted",
    "frozen_baseline_rmse",
]
