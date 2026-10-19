"""
Genetic Algorithm (GA) Optimization Engine using DEAP.

Implements:
- SB3/US3/T1: DEAP evolutionary framework setup: population, fitness, selection,
              crossover, mutation for soft constraints (SC-01 to SC-11 per SRS Section 7.3 & 7.4).
- SB3/US3/T2: Optimization metrics calculation and reporting (initial vs final fitness,
              utilization gain, student gap reduction, faculty workload balance).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
import random
import time
from typing import Any, Sequence

from deap import base, creator, tools

from app.algorithms.cpsat_solver import FacultySpec, ScheduledAssignment
from app.algorithms.resource_allocator import AllocatedSession, ResourceSpec
from app.algorithms.timeslot_grid import GridSlot, ScheduleGrid
from app.models.academic import ResourceType, SessionType


@dataclass
class SessionGene:
    """
    Atomic gene representing one scheduled session placement in the GA chromosome.
    """
    session_idx: int
    session_id: int | None
    course_id: int
    label: str
    session_type: str
    duration_minutes: int
    start_slot_id: int
    occupied_slot_ids: list[int]
    day: int
    resource_id: int
    faculty_ids: list[int]
    participant_group_id: int
    subbatch_ids: list[int]
    department_id: int
    required_capacity: int
    required_resource_type: ResourceType | None
    required_equipment: dict[str, int] = field(default_factory=dict)


@dataclass
class GAOptimizationConfig:
    """Configuration parameters for the Genetic Algorithm optimizer."""
    population_size: int = 40
    num_generations: int = 30
    crossover_probability: float = 0.75
    mutation_probability: float = 0.30
    tournament_size: int = 3
    random_seed: int | None = 42
    # Soft Constraint Objective Weights (sum = 1.0)
    weights: dict[str, float] = field(default_factory=lambda: {
        "sc01_utilization": 0.20,      # SC-01: Classroom/resource utilization
        "sc02_workload": 0.20,         # SC-02: Faculty workload balance / variance
        "sc03_gaps": 0.25,             # SC-03: Student idle gap minimization
        "sc04_distribution": 0.15,     # SC-04: Daily session distribution across days
        "sc05_faculty_preference": 0.05, # SC-05: Faculty slot preference when provided
        "sc06_suitability": 0.10,      # SC-06: Room suitability & equipment fit
        "sc07_room_switching": 0.05,    # SC-07: Minimize course room switching
        "sc08_reschedule_changes": 0.0, # SC-08: Reschedule-only objective
        "sc09_reschedule_faculty_preference": 0.0, # SC-09: Reschedule-only preference objective
        "sc10_stability": 0.10,        # SC-10: Resource stability across recurring course sessions
        "sc11_grouping_efficiency": 0.05, # SC-11: Participant grouping efficiency
    })


@dataclass
class GAMetrics:
    """Detailed performance and improvement metrics for GA optimization (SB3/US3/T2)."""
    initial_fitness: float
    final_fitness: float
    fitness_improvement_pct: float
    generations_completed: int
    wall_clock_time_seconds: float
    initial_student_gaps: int
    final_student_gaps: int
    initial_workload_variance: float
    final_workload_variance: float
    initial_utilization: float
    final_utilization: float
    fitness_history: list[float] = field(default_factory=list)
    hard_constraint_violations: int = 0


@dataclass
class GAOptimizationResult:
    """Final result produced by the Genetic Algorithm Optimization Engine."""
    is_optimized: bool
    status_label: str
    optimized_allocations: list[AllocatedSession] = field(default_factory=list)
    metrics: GAMetrics | None = None
    diagnostics: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DEAP Registration (Lazy-safe initialization)
# ---------------------------------------------------------------------------
def _init_deap():
    if not hasattr(creator, "FitnessMax"):
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    if not hasattr(creator, "Individual"):
        creator.create("Individual", list, fitness=creator.FitnessMax)


class TimetableGAOptimizer:
    """
    Engine 3 in the 4-engine scheduling pipeline.
    
    Takes a Resource-Validated Timetable (from CP-SAT + Smart Resource Allocator)
    and evolves soft-constraint objectives (SC-01 through SC-11) without violating
    any hard constraint (HC-01 through HC-16).
    """

    def __init__(
        self,
        grid: ScheduleGrid,
        resources: Sequence[ResourceSpec],
        faculty_members: dict[int, FacultySpec] | None = None,
        config: GAOptimizationConfig | None = None,
        participant_groups: dict[int, Any] | None = None,
        reserved_slot_ids: set[int] | None = None,
    ):
        _init_deap()
        self.grid = grid
        self.resources = list(resources)
        self.resources_by_id = {r.resource_id: r for r in self.resources}
        self.faculty_members = faculty_members or {}
        self.config = config or GAOptimizationConfig()
        self.participant_groups = participant_groups or {}
        self.reserved_slot_ids = reserved_slot_ids or set()
        self.rng = random.Random(self.config.random_seed)
        if self.config.population_size < 1 or self.config.num_generations < 0 or self.config.tournament_size < 1:
            raise ValueError("GA population_size and tournament_size must be positive; num_generations cannot be negative.")
        if not 0 <= self.config.crossover_probability <= 1 or not 0 <= self.config.mutation_probability <= 1:
            raise ValueError("GA probabilities must be between 0 and 1.")

        # Normalize soft-constraint weights
        default_weights = GAOptimizationConfig().weights
        raw_weights = {**default_weights, **self.config.weights}
        if set(raw_weights) != set(default_weights):
            raise ValueError(f"Unknown GA scoring weights: {sorted(set(raw_weights) - set(default_weights))}")
        if any(not math.isfinite(float(v)) or float(v) < 0 for v in raw_weights.values()):
            raise ValueError("GA weights must be finite and non-negative.")
        total_w = sum(raw_weights.values())
        if total_w <= 0:
            raise ValueError("At least one GA weight must be positive.")
        self.weights = {k: v / total_w for k, v in raw_weights.items()}

        # Precompute valid start slots for durations (60m, 120m, etc.)
        self.valid_starts_by_duration: dict[int, list[int]] = {}
        durations: set[int] = set()
        for day_slots in self.grid.slots_by_day.values():
            for start_idx, start_slot in enumerate(day_slots):
                total_minutes = 0
                for slot in day_slots[start_idx:]:
                    if slot.is_break:
                        break
                    total_minutes += slot.duration_minutes
                    durations.add(total_minutes)
        for d in durations:
            self.valid_starts_by_duration[d] = self.grid.get_valid_start_slots_for_duration(d)

        # Categorize resources by type and department
        self.resources_by_type: dict[ResourceType, list[ResourceSpec]] = {}
        for r in self.resources:
            if r.is_active:
                self.resources_by_type.setdefault(r.resource_type, []).append(r)

    # -----------------------------------------------------------------------
    # Soft Constraint Evaluators (SC-01 to SC-11)
    # -----------------------------------------------------------------------

    def evaluate_sc01_utilization(self, individual: list[SessionGene]) -> float:
        """SC-01: Resource capacity utilization. Higher is better (ratio in (0, 1.0])."""
        if not individual:
            return 1.0
        ratios: list[float] = []
        for gene in individual:
            res = self.resources_by_id.get(gene.resource_id)
            if res and res.capacity > 0:
                util = min(1.0, gene.required_capacity / res.capacity)
                ratios.append(util)
        return sum(ratios) / len(ratios) if ratios else 0.5

    def evaluate_sc02_workload_balance(self, individual: list[SessionGene]) -> tuple[float, float]:
        """
        SC-02: Faculty workload balance across days.
        Returns:
            Tuple of (score [0, 1.0], mean_daily_variance)
        """
        if not self.faculty_members:
            return 1.0, 0.0

        # Compute faculty hours per day: faculty_id -> {day -> hours}
        days_list = list(self.grid.slots_by_day.keys()) if hasattr(self.grid, "slots_by_day") else list(range(1, 6))
        fac_day_hours: dict[int, dict[int, float]] = {
            fid: {d: 0.0 for d in days_list}
            for fid in self.faculty_members
        }

        for gene in individual:
            hours = gene.duration_minutes / 60.0
            for fid in gene.faculty_ids:
                if fid in fac_day_hours:
                    fac_day_hours[fid][gene.day] = fac_day_hours[fid].get(gene.day, 0.0) + hours

        variances: list[float] = []
        for fid, day_map in fac_day_hours.items():
            vals = list(day_map.values())
            total = sum(vals)
            if total > 0:
                mean = total / len(vals)
                var = sum((v - mean) ** 2 for v in vals) / len(vals)
                variances.append(var)

        mean_var = sum(variances) / len(variances) if variances else 0.0
        # Score is inversely proportional to variance: variance 0 -> score 1.0
        score = 1.0 / (1.0 + mean_var)
        return score, mean_var

    def evaluate_sc03_student_gaps(self, individual: list[SessionGene]) -> tuple[float, int]:
        """
        SC-03: Minimize student idle gaps (unoccupied periods between classes on same day).
        Returns:
            Tuple of (score [0, 1.0], total_gap_periods)
        """
        # Map subbatch -> day -> list of occupied slot period numbers
        subbatch_schedule: dict[int, dict[int, set[int]]] = {}

        for gene in individual:
            for sbid in gene.subbatch_ids:
                sb_map = subbatch_schedule.setdefault(sbid, {})
                day_slots = sb_map.setdefault(gene.day, set())
                for sid in gene.occupied_slot_ids:
                    slot = self.grid.slot_by_id[sid]
                    if not slot.is_break:
                        day_slots.add(slot.period)

        total_gaps = 0
        for sbid, day_map in subbatch_schedule.items():
            for day, periods in day_map.items():
                if len(periods) >= 2:
                    min_p = min(periods)
                    max_p = max(periods)
                    # Check how many periods between min_p and max_p are idle (excluding lunch)
                    operational = {slot.period for slot in self.grid.slots_by_day.get(day, []) if not slot.is_break}
                    for p in range(min_p + 1, max_p):
                        if p in operational and p not in periods:
                            total_gaps += 1

        score = 1.0 / (1.0 + (total_gaps * 0.1))
        return score, total_gaps

    def evaluate_sc04_daily_distribution(self, individual: list[SessionGene]) -> float:
        """
        SC-04: Daily distribution of course sessions across days.
        Avoids scheduling multiple lectures of the same course on the same day.
        """
        course_day_counts: dict[int, dict[int, int]] = {}

        for gene in individual:
            # We focus on lectures/tutorials for daily spread
            if gene.session_type in (SessionType.LECTURE.value, SessionType.TUTE_ASSIGNMENT.value):
                c_map = course_day_counts.setdefault(gene.course_id, {})
                c_map[gene.day] = c_map.get(gene.day, 0) + 1

        total_courses = len(course_day_counts)
        if total_courses == 0:
            return 1.0

        clumped_penalty = 0
        for c_id, day_counts in course_day_counts.items():
            for day, cnt in day_counts.items():
                if cnt > 1:
                    clumped_penalty += (cnt - 1)

        score = max(0.0, 1.0 - (clumped_penalty * 0.08))
        return score

    def evaluate_sc06_room_suitability(self, individual: list[SessionGene]) -> float:
        """SC-06: Room suitability & equipment richness."""
        scores: list[float] = []
        for gene in individual:
            res = self.resources_by_id.get(gene.resource_id)
            if not res:
                scores.append(0.0)
                continue
            # Exact type match
            match = 1.0 if (gene.required_resource_type is None or res.resource_type == gene.required_resource_type) else 0.0
            # Equipment bonus
            equipment_ok = all(res.equipment.get(k.strip().lower(), 0) >= qty for k, qty in gene.required_equipment.items())
            has_aid = any(res.equipment.get(k, 0) > 0 for k in ("projector", "smart board", "display"))
            bonus = 0.2 if has_aid else 0.0
            scores.append(min(1.0, match * 0.8 + bonus) if equipment_ok else 0.0)
        return sum(scores) / len(scores) if scores else 0.8

    def evaluate_sc05_faculty_preference(self, individual: list[SessionGene]) -> float:
        applicable = [(gene, self.faculty_members[fid]) for gene in individual for fid in gene.faculty_ids
                      if fid in self.faculty_members and self.faculty_members[fid].preferred_slot_ids]
        if not applicable:
            return 1.0
        return sum(all(slot_id in faculty.preferred_slot_ids for slot_id in gene.occupied_slot_ids)
                   for gene, faculty in applicable) / len(applicable)

    def evaluate_sc07_room_switching(self, individual: list[SessionGene]) -> float:
        return self.evaluate_sc10_resource_stability(individual)

    def evaluate_sc08_reschedule_changes(self, individual: list[SessionGene]) -> float:
        return 1.0

    def evaluate_sc09_reschedule_faculty_preference(self, individual: list[SessionGene]) -> float:
        return self.evaluate_sc05_faculty_preference(individual)

    def evaluate_sc11_grouping_efficiency(self, individual: list[SessionGene]) -> float:
        if not individual:
            return 1.0
        audience_sizes = [len(set(g.subbatch_ids)) for g in individual if g.subbatch_ids]
        if not audience_sizes:
            return 0.0
        max_group_size = max(audience_sizes)
        if max_group_size <= 1:
            return 1.0
        return sum(size / max_group_size for size in audience_sizes) / len(audience_sizes)

    def evaluate_sc10_resource_stability(self, individual: list[SessionGene]) -> float:
        """
        SC-10: Resource stability.
        Lectures of the same course should ideally take place in the same classroom.
        """
        course_rooms: dict[int, set[int]] = {}
        for gene in individual:
            if gene.session_type == SessionType.LECTURE.value:
                course_rooms.setdefault(gene.course_id, set()).add(gene.resource_id)

        if not course_rooms:
            return 1.0

        # Ratio of courses that use exactly 1 classroom
        stable_count = sum(1 for c_id, r_set in course_rooms.items() if len(r_set) == 1)
        return stable_count / len(course_rooms)

    # -----------------------------------------------------------------------
    # Hard Constraint Verification (GA Safety Requirement - HC-01 to HC-16)
    # -----------------------------------------------------------------------

    def count_hard_constraint_violations(self, individual: list[SessionGene]) -> int:
        """
        Verifies zero violations of HC-01 (Faculty), HC-02 (Resource),
        HC-03/04 (Sub-batch), HC-05 (Faculty Avail), HC-06 (Resource Avail),
        and HC-07/HC-16 (Capacity).
        """
        violations = 0
        faculty_time: dict[tuple[int, int], int] = {}
        subbatch_time: dict[tuple[int, int], int] = {}
        resource_time: dict[tuple[int, int], int] = {}
        faculty_hours: dict[int, float] = {}

        for gene in individual:
            res = self.resources_by_id.get(gene.resource_id)

            if gene.start_slot_id not in self.grid.slot_by_id:
                violations += 1
                continue
            try:
                expected_slots = self.grid.get_occupied_slots(gene.start_slot_id, gene.duration_minutes)
                if expected_slots != gene.occupied_slot_ids or self.grid.slot_by_id[gene.start_slot_id].day != gene.day:
                    violations += 1
            except (KeyError, StopIteration, IndexError, ValueError):
                violations += 1
                continue
            if not gene.subbatch_ids or len(set(gene.subbatch_ids)) != len(gene.subbatch_ids):
                violations += 1
            if any(slot_id in self.reserved_slot_ids for slot_id in gene.occupied_slot_ids):
                violations += 1
            if gene.participant_group_id in self.participant_groups:
                if set(gene.subbatch_ids) != set(self.participant_groups[gene.participant_group_id].subbatch_ids):
                    violations += 1
            elif self.participant_groups:
                violations += 1

            # Capacity check (HC-07, HC-16)
            if not res or res.capacity < gene.required_capacity:
                violations += 1

            # Resource suitability (HC-08, HC-09)
            if gene.required_resource_type and res and res.resource_type != gene.required_resource_type:
                violations += 1

            # Inactive room check (HC-06)
            if res and not res.is_active:
                violations += 1
            if res and res.department_id is not None and res.department_id != gene.department_id:
                violations += 1
            if res and any(res.equipment.get(name.strip().lower(), 0) < quantity
                           for name, quantity in gene.required_equipment.items()):
                violations += 1

            for slot_id in gene.occupied_slot_ids:
                # Faculty Clash (HC-01)
                for fid in gene.faculty_ids:
                    faculty_hours[fid] = faculty_hours.get(fid, 0.0) + gene.duration_minutes / 60.0 / max(1, len(gene.occupied_slot_ids))
                    fac_key = (fid, slot_id)
                    if fac_key in faculty_time:
                        violations += 1
                    else:
                        faculty_time[fac_key] = gene.session_idx

                    # Faculty Availability (HC-05)
                    fac = self.faculty_members.get(fid)
                    if fac and slot_id in fac.unavailable_slot_ids:
                        violations += 1

                # Sub-batch Clash (HC-03, HC-04)
                for sbid in gene.subbatch_ids:
                    sb_key = (sbid, slot_id)
                    if sb_key in subbatch_time:
                        violations += 1
                    else:
                        subbatch_time[sb_key] = gene.session_idx

                # Resource Clash (HC-02)
                res_key = (gene.resource_id, slot_id)
                if res_key in resource_time:
                    violations += 1
                else:
                    resource_time[res_key] = gene.session_idx

                # Resource Availability (HC-06)
                if res and slot_id in res.unavailable_slot_ids:
                    violations += 1

        for fid, hours in faculty_hours.items():
            faculty = self.faculty_members.get(fid)
            if faculty and hours > faculty.max_weekly_hours:
                violations += 1

        return violations

    def evaluate_fitness(self, individual: list[SessionGene]) -> tuple[float]:
        """
        Composite fitness evaluation function for DEAP.
        Penalizes any hard-constraint violation heavily to satisfy the GA safety rule.
        """
        hc_violations = self.count_hard_constraint_violations(individual)
        if hc_violations > 0:
            # Heavy penalty if safety rule is breached
            fitness = max(0.0, 0.20 - (hc_violations * 0.05))
            return (fitness,)

        # Compute soft constraint sub-scores
        s_util = self.evaluate_sc01_utilization(individual)
        s_workload, _ = self.evaluate_sc02_workload_balance(individual)
        s_gaps, _ = self.evaluate_sc03_student_gaps(individual)
        s_dist = self.evaluate_sc04_daily_distribution(individual)
        s_pref = self.evaluate_sc05_faculty_preference(individual)
        s_suit = self.evaluate_sc06_room_suitability(individual)
        s_switch = self.evaluate_sc07_room_switching(individual)
        s_resched = self.evaluate_sc08_reschedule_changes(individual)
        s_resched_pref = self.evaluate_sc09_reschedule_faculty_preference(individual)
        s_stab = self.evaluate_sc10_resource_stability(individual)
        s_group = self.evaluate_sc11_grouping_efficiency(individual)

        composite_score = (
            self.weights["sc01_utilization"] * s_util
            + self.weights["sc02_workload"] * s_workload
            + self.weights["sc03_gaps"] * s_gaps
            + self.weights["sc04_distribution"] * s_dist
            + self.weights["sc05_faculty_preference"] * s_pref
            + self.weights["sc06_suitability"] * s_suit
            + self.weights["sc07_room_switching"] * s_switch
            + self.weights["sc08_reschedule_changes"] * s_resched
            + self.weights["sc09_reschedule_faculty_preference"] * s_resched_pref
            + self.weights["sc10_stability"] * s_stab
            + self.weights["sc11_grouping_efficiency"] * s_group
        )

        return (round(composite_score, 5),)

    def _select_tournament(self, individuals: list[Any], k: int, tournsize: int) -> list[Any]:
        """Tournament selection using this optimizer's seeded RNG."""
        if not individuals:
            return []
        sample_size = min(tournsize, len(individuals))
        return [
            max(self.rng.sample(individuals, sample_size), key=lambda individual: individual.fitness)
            for _ in range(k)
        ]

    # -----------------------------------------------------------------------
    # Genetic Operators: Mutation, Crossover, Repair
    # -----------------------------------------------------------------------

    def mutate_individual(self, individual: list[SessionGene]) -> tuple[list[SessionGene]]:
        """
        Safe domain-specific mutation operator:
        1. Slot Shift Mutation: shifts a session to another valid start slot on the grid.
        2. Room Swap Mutation: reassigns a session to another eligible candidate room.
        3. Local Repair: if mutation introduced a hard-constraint clash, reverts or repairs.
        """
        if not individual:
            return (individual,)

        idx = self.rng.randint(0, len(individual) - 1)
        original_gene = copy.deepcopy(individual[idx])
        gene = individual[idx]

        # Coin toss: mutate time slot or mutate room
        mutation_type = self.rng.choice(["time_slot", "room", "both"])

        if mutation_type in ("time_slot", "both"):
            valid_starts = self.grid.get_valid_start_slots_for_duration(gene.duration_minutes)
            if valid_starts:
                new_start = self.rng.choice(valid_starts)
                new_occ = self.grid.get_occupied_slots(new_start, gene.duration_minutes)
                gene.start_slot_id = new_start
                gene.occupied_slot_ids = new_occ
                gene.day = self.grid.slot_by_id[new_start].day

        if mutation_type in ("room", "both"):
            # Candidate rooms matching type & capacity
            req_type = gene.required_resource_type or ResourceType.CLASSROOM
            candidates = [
                r for r in self.resources_by_type.get(req_type, [])
                if r.capacity >= gene.required_capacity
                and (r.department_id is None or r.department_id == gene.department_id)
                and all(r.equipment.get(name.strip().lower(), 0) >= quantity for name, quantity in gene.required_equipment.items())
            ]
            if candidates:
                chosen_room = self.rng.choice(candidates)
                gene.resource_id = chosen_room.resource_id

        # Safety Check: If mutation created an unrepairable hard-constraint clash, revert!
        if self.count_hard_constraint_violations(individual) > 0:
            individual[idx] = original_gene

        return (individual,)

    def crossover_individuals(
        self, ind1: list[SessionGene], ind2: list[SessionGene]
    ) -> tuple[list[SessionGene], list[SessionGene]]:
        """
        Safe uniform crossover operator:
        Swaps genes between parent schedules. If child violates hard constraints,
        repairs by restoring parent placement.
        """
        size = min(len(ind1), len(ind2))
        for i in range(size):
            if self.rng.random() < 0.5:
                # Attempt gene swap
                orig1 = copy.deepcopy(ind1[i])
                orig2 = copy.deepcopy(ind2[i])

                ind1[i], ind2[i] = orig2, orig1

                # If ind1 broke safety rule, revert gene i in ind1
                if self.count_hard_constraint_violations(ind1) > 0:
                    ind1[i] = orig1

                # If ind2 broke safety rule, revert gene i in ind2
                if self.count_hard_constraint_violations(ind2) > 0:
                    ind2[i] = orig2

        return ind1, ind2

    # -----------------------------------------------------------------------
    # Main GA Execution Pipeline
    # -----------------------------------------------------------------------

    def optimize(
        self,
        allocations: Sequence[AllocatedSession],
        max_time_seconds: float = 15.0,
    ) -> GAOptimizationResult:
        """
        Executes Genetic Algorithm Optimization on resource-validated timetable.
        Guarantees non-decreasing fitness (Elitism) and zero hard-constraint violations.
        """
        start_time = time.perf_counter()

        # Convert input AllocatedSession list to baseline SessionGene list
        baseline_genes: list[SessionGene] = []
        if max_time_seconds <= 0:
            return GAOptimizationResult(False, "INVALID_CONFIGURATION", diagnostics=["max_time_seconds must be positive."])
        if not allocations:
            return GAOptimizationResult(True, "OPTIMIZED", optimized_allocations=[], diagnostics=[])

        for idx, a in enumerate(allocations):
            gene = SessionGene(
                session_idx=idx,
                session_id=a.session_id,
                course_id=a.course_id,
                label=a.label,
                session_type=a.session_type,
                duration_minutes=a.duration_minutes,
                start_slot_id=a.start_slot_id,
                occupied_slot_ids=list(a.occupied_slot_ids),
                day=a.day,
                resource_id=a.resource_id,
                faculty_ids=list(a.faculty_ids),
                participant_group_id=a.participant_group_id,
                subbatch_ids=list(a.subbatch_ids),
                department_id=a.department_id,
                required_capacity=a.required_capacity,
                required_resource_type=a.required_resource_type,
                required_equipment=dict(a.required_equipment),
            )
            baseline_genes.append(gene)

        # Calculate Initial Metrics
        init_violations = self.count_hard_constraint_violations(baseline_genes)
        if init_violations:
            return GAOptimizationResult(
                False,
                "SAFETY_VIOLATION",
                optimized_allocations=list(allocations),
                diagnostics=[f"Input schedule has {init_violations} hard-constraint violation(s); optimization was not run."],
            )
        init_fit = self.evaluate_fitness(baseline_genes)[0]
        init_util = self.evaluate_sc01_utilization(baseline_genes)
        _, init_var = self.evaluate_sc02_workload_balance(baseline_genes)
        _, init_gaps = self.evaluate_sc03_student_gaps(baseline_genes)

        # Setup DEAP Toolbox
        toolbox = base.Toolbox()
        toolbox.register("individual", tools.initIterate, creator.Individual, lambda: copy.deepcopy(baseline_genes))
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", self.evaluate_fitness)
        toolbox.register("mate", self.crossover_individuals)
        toolbox.register("mutate", self.mutate_individual)
        toolbox.register("select", self._select_tournament, tournsize=self.config.tournament_size)

        # Initialize Population
        pop = toolbox.population(n=self.config.population_size)

        # Seed population: Individual 0 is baseline; others receive safe exploratory mutations
        pop[0] = creator.Individual(copy.deepcopy(baseline_genes))
        for i in range(1, len(pop)):
            for _ in range(self.rng.randint(1, 4)):
                self.mutate_individual(pop[i])

        # Evaluate initial population fitnesses
        for ind in pop:
            ind.fitness.values = toolbox.evaluate(ind)

        # Track best individual across all generations (Elitism)
        best_individual = copy.deepcopy(tools.selBest(pop, 1)[0])
        best_fitness = best_individual.fitness.values[0]
        fitness_history: list[float] = [best_fitness]

        # Evolutionary Loop
        generations_run = 0
        for gen in range(1, self.config.num_generations + 1):
            if (time.perf_counter() - start_time) >= max_time_seconds:
                break

            generations_run = gen

            # Selection
            offspring = toolbox.select(pop, len(pop))
            offspring = list(map(toolbox.clone, offspring))

            # Apply Crossover
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if self.rng.random() < self.config.crossover_probability:
                    toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values

            # Apply Mutation
            for mutant in offspring:
                if self.rng.random() < self.config.mutation_probability:
                    toolbox.mutate(mutant)
                    del mutant.fitness.values

            # Evaluate invalidated offspring
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            for ind in invalid_ind:
                ind.fitness.values = toolbox.evaluate(ind)

            # Elitism: Replace weakest offspring with current best
            weakest_idx = min(range(len(offspring)), key=lambda i: offspring[i].fitness.values[0])
            offspring[weakest_idx] = copy.deepcopy(best_individual)

            pop[:] = offspring

            # Update best individual
            current_best = tools.selBest(pop, 1)[0]
            if current_best.fitness.values[0] > best_fitness:
                best_individual = copy.deepcopy(current_best)
                best_fitness = current_best.fitness.values[0]

            fitness_history.append(best_fitness)

        elapsed = time.perf_counter() - start_time

        # Calculate Final Metrics
        final_violations = self.count_hard_constraint_violations(best_individual)
        final_fit = best_fitness
        final_util = self.evaluate_sc01_utilization(best_individual)
        _, final_var = self.evaluate_sc02_workload_balance(best_individual)
        _, final_gaps = self.evaluate_sc03_student_gaps(best_individual)

        improvement_pct = 0.0
        if init_fit > 0:
            improvement_pct = round(((final_fit - init_fit) / init_fit) * 100.0, 2)

        metrics = GAMetrics(
            initial_fitness=round(init_fit, 4),
            final_fitness=round(final_fit, 4),
            fitness_improvement_pct=improvement_pct,
            generations_completed=generations_run,
            wall_clock_time_seconds=round(elapsed, 3),
            initial_student_gaps=init_gaps,
            final_student_gaps=final_gaps,
            initial_workload_variance=round(init_var, 4),
            final_workload_variance=round(final_var, 4),
            initial_utilization=round(init_util, 4),
            final_utilization=round(final_util, 4),
            fitness_history=fitness_history,
            hard_constraint_violations=final_violations,
        )

        # Convert best individual genes back to AllocatedSession
        optimized_allocations: list[AllocatedSession] = []
        for gene in best_individual:
            res = self.resources_by_id[gene.resource_id]
            start_slot = self.grid.slot_by_id[gene.start_slot_id]
            end_slot = self.grid.slot_by_id[gene.occupied_slot_ids[-1]]

            alloc = AllocatedSession(
                session_id=gene.session_id,
                course_id=gene.course_id,
                label=gene.label,
                session_type=gene.session_type,
                day=gene.day,
                start_slot_id=gene.start_slot_id,
                start_time=start_slot.start_time,
                end_time=end_slot.end_time,
                duration_minutes=gene.duration_minutes,
                occupied_slot_ids=gene.occupied_slot_ids,
                faculty_ids=gene.faculty_ids,
                participant_group_id=gene.participant_group_id,
                subbatch_ids=gene.subbatch_ids,
                department_id=gene.department_id,
                required_resource_type=gene.required_resource_type,
                required_capacity=gene.required_capacity,
                resource_id=res.resource_id,
                resource_code=res.code,
                resource_name=res.name,
                resource_type=res.resource_type,
                resource_capacity=res.capacity,
                resource_score=final_fit,
                required_equipment=dict(gene.required_equipment),
            )
            optimized_allocations.append(alloc)

        return GAOptimizationResult(
            is_optimized=(final_violations == 0),
            status_label="OPTIMIZED" if final_violations == 0 else "SAFETY_VIOLATION",
            optimized_allocations=optimized_allocations,
            metrics=metrics,
            diagnostics=[] if final_violations == 0 else [f"Hard constraint safety breaches: {final_violations}"],
        )
