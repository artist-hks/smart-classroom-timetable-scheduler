"""
Unit and Integration Tests for ML Room Demand Prediction Engine (SB3/US7).

Verifies:
- SB3/US7/T1: Simulated training data synthesis (day, period, department, semester, participant strength,
              session type, resource type, capacity) per FR-3.7.1, FR-3.7.2.
- SB3/US7/T2: Scikit-learn regression training, evaluation metrics (MAE, RMSE, R² per EV-5),
              data source documentation per model version (FR-3.7.3), model persistence,
              and integration with Smart Resource Allocation (Engine 2).
"""

import os
import tempfile
import pytest

from app.algorithms.cpsat_solver import CPSATScheduler, FacultySpec, ScheduledAssignment
from app.algorithms.ml_demand_predictor import (
    MLDemandDatasetGenerator,
    MLModelMetadata,
    RoomDemandPredictor,
)
from app.algorithms.resource_allocator import (
    AllocatedSession,
    ResourceSpec,
    SmartResourceAllocator,
)
from app.algorithms.session_generator import (
    CourseToSessionGenerator,
    ParticipantGroupResolver,
)
from app.algorithms.timeslot_grid import ScheduleGrid
from app.models.academic import ResourceType, SessionType


@pytest.fixture
def sample_grid():
    return ScheduleGrid.create_standard_piet_grid(days=5, periods_per_day=7, period_duration_minutes=60, lunch_period_index=4)


@pytest.fixture
def sample_resources():
    return [
        ResourceSpec(1, "CR-101", "Classroom 101", ResourceType.CLASSROOM, 70, department_id=1, building="Block-A", floor=1),
        ResourceSpec(2, "CR-102", "Classroom 102", ResourceType.CLASSROOM, 65, department_id=1, building="Block-A", floor=1),
        ResourceSpec(3, "LAB-1", "Computing Lab 1", ResourceType.LABORATORY, 30, department_id=1, building="Block-B", floor=1),
        ResourceSpec(4, "AUD-1", "Auditorium", ResourceType.AUDITORIUM, 300, department_id=None, building="Main Block", floor=1),
    ]


def test_dataset_generator_structure_and_bounds():
    """
    SB3/US7/T1: Verify synthesized historical dataset has correct feature matrix
    dimensions and target scores within [0.0, 1.0] (FR-3.7.1, FR-3.7.2).
    """
    X, y, feature_names = MLDemandDatasetGenerator.generate_simulated_dataset(n_samples=500, random_seed=42)

    assert X.shape[0] == 500
    assert X.shape[1] == len(feature_names)
    assert len(y) == 500
    # Demand scores must be bounded in [0.0, 1.0]
    assert np.all(y >= 0.0)
    assert np.all(y <= 1.0)
    assert "day" in feature_names
    assert "resource_capacity" in feature_names
    assert "is_peak_period" in feature_names


import numpy as np


def test_ml_model_training_and_evaluation_metrics():
    """
    SB3/US7/T2: Verify Random Forest regression training, MAE, RMSE, and R² metrics (EV-5),
    and documented data source (FR-3.7.3).
    """
    predictor = RoomDemandPredictor(model_version="v1.0.0-test")
    metadata = predictor.train_and_evaluate(test_size=0.20, random_seed=42)

    assert predictor.is_trained is True
    assert metadata.model_version == "v1.0.0-test"
    assert "SIMULATED_PIET_HISTORICAL_GRID" in metadata.data_source
    assert metadata.sample_count >= 2000

    metrics = metadata.metrics
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "r2_score" in metrics

    # EV-5 Quality Standards
    assert metrics["mae"] < 0.15      # Low absolute error (< 15%)
    assert metrics["rmse"] < 0.20     # Low root mean squared error (< 20%)
    assert metrics["r2_score"] > 0.70  # Strong explanatory power (> 70%)


def test_prediction_sensitivity_peak_vs_offpeak():
    """
    Verify model prediction sensitivity: peak periods and high-utilization classes
    predict higher demand than off-peak low-occupancy periods.
    """
    predictor = RoomDemandPredictor()
    predictor.train_and_evaluate(random_seed=42)

    # Query 1: Peak Tuesday period 2 (10:00 AM) full lecture (60 students in 70 capacity room)
    peak_demand = predictor.predict_single(
        day=2, period=2, department_id=1, semester=5,
        participant_strength=60, session_type=SessionType.LECTURE,
        resource_type=ResourceType.CLASSROOM, resource_capacity=70,
    )

    # Query 2: Off-peak Friday period 7 (4:00 PM) small tutorial in oversized room
    offpeak_demand = predictor.predict_single(
        day=5, period=7, department_id=1, semester=5,
        participant_strength=20, session_type=SessionType.LECTURE,
        resource_type=ResourceType.CLASSROOM, resource_capacity=100,
    )

    assert peak_demand > offpeak_demand
    assert 0.0 <= peak_demand <= 1.0
    assert 0.0 <= offpeak_demand <= 1.0


def test_generate_demand_matrix(sample_grid, sample_resources):
    """
    Verify generation of precomputed demand matrix for Smart Resource Allocator.
    """
    predictor = RoomDemandPredictor()
    predictor.train_and_evaluate(random_seed=42)

    matrix = predictor.generate_demand_matrix(
        grid=sample_grid,
        resources=sample_resources,
        department_id=1,
        semester=5,
    )

    assert len(matrix) > 0
    # Every operational slot for every resource must have a demand score in [0.0, 1.0]
    for (r_id, day, slot_id), score in matrix.items():
        assert r_id in [1, 2, 3, 4]
        assert 1 <= day <= 5
        assert 0.0 <= score <= 1.0


def test_model_serialization_and_reloading():
    """
    Verify model artifact persistence: saving, loading, and prediction parity.
    """
    predictor = RoomDemandPredictor(model_version="v1.0.0-piet-prod")
    predictor.train_and_evaluate(random_seed=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "room_demand_model.pkl")
        predictor.save_model(save_path)
        assert os.path.exists(save_path)

        # Load into a fresh predictor instance
        reloaded = RoomDemandPredictor()
        reloaded.load_model(save_path)

        assert reloaded.is_trained is True
        assert reloaded.metadata.model_version == "v1.0.0-piet-prod"

        # Predictions must be identical
        p1 = predictor.predict_single(2, 3, 1, 5, 60, SessionType.LECTURE, ResourceType.CLASSROOM, 70)
        p2 = reloaded.predict_single(2, 3, 1, 5, 60, SessionType.LECTURE, ResourceType.CLASSROOM, 70)
        assert p1 == p2


def test_closed_loop_ml_fed_smart_resource_allocation(sample_grid, sample_resources):
    """
    Closed-Loop System Integration:
    ML Demand Predictor generates predicted demand matrix -> Smart Resource Allocator
    uses it to inform candidate room scores (FR-3.8.2).
    """
    # 1. Train ML model and generate demand matrix
    predictor = RoomDemandPredictor()
    predictor.train_and_evaluate(random_seed=42)
    demand_matrix = predictor.generate_demand_matrix(
        grid=sample_grid,
        resources=sample_resources,
        department_id=1,
        semester=5,
    )

    # 2. Feed predicted demand matrix into Smart Resource Allocator
    allocator = SmartResourceAllocator(
        resources=sample_resources,
        predicted_demand=demand_matrix,
    )

    # Session to allocate
    session = ScheduledAssignment(
        session_id=101,
        course_id=1,
        label="CS501_Lec",
        session_type=SessionType.LECTURE.value,
        day=2,
        start_slot_id=8,
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        occupied_slot_ids=[8],
        faculty_ids=[101],
        participant_group_id=10,
        subbatch_ids=[1, 2, 3],
        department_id=1,
        required_resource_type=ResourceType.CLASSROOM,
        required_capacity=60,
    )

    result = allocator.allocate_and_validate([session])

    assert result.is_feasible is True
    assert result.validation_passed is True
    assert len(result.allocations) == 1
    alloc = result.allocations[0]
    # Verify ML demand score was factored into breakdown
    assert "ml_demand" in alloc.score_breakdown
    assert 0.0 <= alloc.score_breakdown["ml_demand"] <= 1.0
