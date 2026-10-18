"""
Machine Learning Room Demand Prediction Engine (SB3/US7).

Implements:
- SB3/US7/T1: Generate and prepare simulated historical room demand & occupancy training data
              (day, period, department, semester, participant strength, session type,
              resource type, resource capacity) per FR-3.7.1, FR-3.7.2.
- SB3/US7/T2: Train, evaluate, and serialize scikit-learn regression model (MAE, RMSE, R²),
              document data source per model version (FR-3.7.3, EV-5), and generate
              predicted demand matrices to feed the Smart Resource Allocation Engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import math
import os
import pickle
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from app.algorithms.resource_allocator import ResourceSpec
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.models.academic import ResourceType, SessionType


@dataclass
class MLModelMetadata:
    """Documents model provenance, data source, and performance evaluation (FR-3.7.3, EV-5)."""
    model_version: str
    data_source: str  # e.g. "SIMULATED_PIET_HISTORICAL_GRID" or "INSTITUTIONAL_ACTUAL"
    sample_count: int
    train_samples: int
    test_samples: int
    trained_at: str
    metrics: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)


class MLDemandDatasetGenerator:
    """
    Generates realistic historical academic room demand and occupancy records (FR-3.7.1, FR-3.7.2).
    Captures temporal, departmental, cohort, and architectural patterns:
    - Peak lecture periods (10:00 - 13:00) exhibit higher campus-wide occupancy
    - Lab sessions require high computer-to-student density
    - Large student strength exerts non-linear demand on higher-capacity auditoriums/classrooms
    - Friday late afternoons and Monday early mornings exhibit lower demand
    """

    FEATURE_NAMES = [
        "day",                     # 1 = Mon ... 5 = Fri
        "period",                  # 1 = 09:00, 2 = 10:00 ... 7 = 16:30
        "department_id",           # Department identifier
        "semester",                # 1 to 8
        "participant_strength",    # Number of attending students
        "session_type_encoded",    # 1=Lecture, 2=Practical, 3=Seminar, 4=Event
        "resource_type_encoded",   # 1=Classroom, 2=Laboratory, 3=Seminar Hall, 4=Auditorium
        "resource_capacity",       # Maximum seating capacity of room
        "is_peak_period",          # 1 if period in {2, 3, 5, 6}, else 0
        "capacity_headroom",       # resource_capacity - participant_strength
    ]

    @classmethod
    def generate_simulated_dataset(
        cls,
        n_samples: int = 2000,
        random_seed: int = 42,
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """
        Synthesizes realistic training dataset modeled after PIET academic semesters.
        Returns:
            X (features matrix), y (target demand score in [0.0, 1.0]), feature_names
        """
        rng = np.random.default_rng(random_seed)

        days = rng.integers(1, 6, size=n_samples)               # Days 1 to 5
        periods = rng.integers(1, 8, size=n_samples)            # Periods 1 to 7
        dept_ids = rng.choice([1, 2, 3, 4], size=n_samples)    # 1=CSE, 2=ECE, 3=MECH, 4=CIVIL
        semesters = rng.choice([1, 3, 5, 7], size=n_samples)   # Odd semesters (Fall)

        # Session Types: 60% Lecture, 30% Practical, 10% Seminar
        stype_choices = [1, 2, 3]
        stype_weights = [0.60, 0.30, 0.10]
        stypes = rng.choice(stype_choices, p=stype_weights, size=n_samples)

        # Participant strengths: 20 for lab sub-batch, 60 for full section, 120 for combined lecture
        strengths = np.zeros(n_samples, dtype=int)
        for i in range(n_samples):
            if stypes[i] == 2:  # Practical
                strengths[i] = rng.choice([20, 25, 30])
            elif stypes[i] == 3:  # Seminar
                strengths[i] = rng.choice([60, 120, 180])
            else:  # Lecture
                strengths[i] = rng.choice([55, 60, 65])

        # Resource types: match session requirements mostly
        rtypes = np.zeros(n_samples, dtype=int)
        capacities = np.zeros(n_samples, dtype=int)

        for i in range(n_samples):
            if stypes[i] == 2:
                rtypes[i] = 2  # Laboratory
                capacities[i] = rng.choice([30, 35, 40])
            elif stypes[i] == 3 and strengths[i] > 100:
                rtypes[i] = 4  # Auditorium
                capacities[i] = rng.choice([250, 300])
            else:
                rtypes[i] = 1  # Classroom
                capacities[i] = rng.choice([65, 70, 80, 100])

        # Peak periods: Periods 2, 3 (10:00-12:00) and Periods 5, 6 (13:00-15:00)
        is_peak = np.isin(periods, [2, 3, 5, 6]).astype(int)
        capacity_headroom = capacities - strengths

        # Construct feature matrix X
        X = np.column_stack([
            days,
            periods,
            dept_ids,
            semesters,
            strengths,
            stypes,
            rtypes,
            capacities,
            is_peak,
            capacity_headroom,
        ])

        # Generate realistic target: Room Demand Score in [0.0, 1.0]
        # Base demand: utilization ratio (strengths / capacities)
        utilization = np.clip(strengths / capacities, 0.1, 1.0)

        # Peak hour surge (+0.15)
        peak_surge = is_peak * 0.15

        # Tuesday/Wednesday/Thursday academic density (+0.08)
        midweek_surge = np.isin(days, [2, 3, 4]).astype(float) * 0.08

        # Friday late period drop (-0.12)
        friday_drop = ((days == 5) & (periods >= 6)).astype(float) * 0.12

        # Lab demand premium (labs are high-demand scarce resources)
        lab_premium = (rtypes == 2).astype(float) * 0.10

        # Noise
        noise = rng.normal(0.0, 0.03, size=n_samples)

        y = np.clip(
            utilization * 0.60 + peak_surge + midweek_surge - friday_drop + lab_premium + noise,
            0.05,
            0.98,
        )

        return X, y, cls.FEATURE_NAMES


class RoomDemandPredictor:
    """
    Supervised Machine Learning Regression Engine for academic room demand forecasting.
    Feeds predicted demand into Smart Resource Allocation (Engine 2).
    """

    def __init__(self, model_version: str = "v1.0.0-piet-simulated"):
        self.model_version = model_version
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=12,
            min_samples_split=4,
            random_state=42,
            n_jobs=-1,
        )
        self.is_trained = False
        self.metadata: MLModelMetadata | None = None

    def train_and_evaluate(
        self,
        X: np.ndarray | None = None,
        y: np.ndarray | None = None,
        test_size: float = 0.20,
        random_seed: int = 42,
    ) -> MLModelMetadata:
        """
        Trains the Random Forest Regressor and evaluates against MAE, RMSE, and R² (EV-5).
        If X and y are not provided, automatically synthesizes the training dataset.
        """
        if X is None or y is None:
            X, y, feature_names = MLDemandDatasetGenerator.generate_simulated_dataset(
                n_samples=2500, random_seed=random_seed
            )
            data_source = "SIMULATED_PIET_HISTORICAL_GRID (FR-3.7.2)"
        else:
            feature_names = MLDemandDatasetGenerator.FEATURE_NAMES
            data_source = "INSTITUTIONAL_OR_CUSTOM_SUPPLIED (FR-3.7.2)"

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_seed
        )

        # Train model
        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Evaluate performance (EV-5)
        y_pred = self.model.predict(X_test)
        mae = float(mean_absolute_error(y_test, y_pred))
        rmse = float(math.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = float(r2_score(y_test, y_pred))

        self.metadata = MLModelMetadata(
            model_version=self.model_version,
            data_source=data_source,
            sample_count=len(X),
            train_samples=len(X_train),
            test_samples=len(X_test),
            trained_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            metrics={
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "r2_score": round(r2, 4),
            },
            feature_names=feature_names,
        )

        return self.metadata

    def predict_single(
        self,
        day: int,
        period: int,
        department_id: int,
        semester: int,
        participant_strength: int,
        session_type: SessionType,
        resource_type: ResourceType,
        resource_capacity: int,
    ) -> float:
        """
        Predicts demand score in [0.0, 1.0] for a single session/resource/time query.
        """
        if not self.is_trained:
            self.train_and_evaluate()

        stype_enc = 2 if session_type == SessionType.PRACTICAL else (
            3 if session_type == SessionType.SEMINAR else 1
        )
        rtype_enc = 2 if resource_type == ResourceType.LABORATORY else (
            4 if resource_type == ResourceType.AUDITORIUM else (
                3 if resource_type == ResourceType.SEMINAR_HALL else 1
            )
        )
        is_peak = 1 if period in (2, 3, 5, 6) else 0
        headroom = resource_capacity - participant_strength

        feat = np.array([[
            day,
            period,
            department_id,
            semester,
            participant_strength,
            stype_enc,
            rtype_enc,
            resource_capacity,
            is_peak,
            headroom,
        ]], dtype=float)

        pred = float(self.model.predict(feat)[0])
        return round(max(0.0, min(1.0, pred)), 4)

    def generate_demand_matrix(
        self,
        grid: ScheduleGrid,
        resources: Sequence[ResourceSpec],
        department_id: int = 1,
        semester: int = 5,
        default_strength: int = 60,
    ) -> dict[tuple[int, int, int], float]:
        """
        Precomputes the full predicted demand matrix:
            (resource_id, day, slot_id) -> demand_score [0.0 - 1.0]
        Directly consumable by SmartResourceAllocator.
        """
        if not self.is_trained:
            self.train_and_evaluate()

        demand_matrix: dict[tuple[int, int, int], float] = {}

        for r in resources:
            for slot in grid.slots:
                if slot.is_break:
                    continue

                stype = SessionType.PRACTICAL if r.resource_type == ResourceType.LABORATORY else SessionType.LECTURE
                strength = 20 if r.resource_type == ResourceType.LABORATORY else min(r.capacity, default_strength)

                d_score = self.predict_single(
                    day=slot.day,
                    period=slot.period,
                    department_id=r.department_id or department_id,
                    semester=semester,
                    participant_strength=strength,
                    session_type=stype,
                    resource_type=r.resource_type,
                    resource_capacity=r.capacity,
                )
                demand_matrix[(r.resource_id, slot.day, slot.slot_id)] = d_score

        return demand_matrix

    def save_model(self, filepath: str) -> None:
        """Serializes the trained model and its metadata to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "wb") as f:
            pickle.dump({"model": self.model, "metadata": self.metadata}, f)

    def load_model(self, filepath: str) -> None:
        """Loads a serialized model and its metadata from disk."""
        with open(filepath, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.metadata = data["metadata"]
            self.is_trained = True
