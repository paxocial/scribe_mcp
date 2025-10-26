from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class ProjectRecord:
    id: int
    name: str
    repo_root: str
    progress_log_path: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DevPlanRecord:
    id: int
    project_id: int
    project_name: str
    plan_type: str  # 'architecture', 'phase_plan', 'checklist', 'progress_log'
    file_path: str
    version: str
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PhaseRecord:
    id: int
    project_id: int
    dev_plan_id: int
    phase_number: int
    phase_name: str
    status: str  # 'planned', 'in_progress', 'completed', 'blocked'
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    deliverables_count: int = 0
    deliverables_completed: int = 0
    confidence_score: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MilestoneRecord:
    id: int
    project_id: int
    phase_id: Optional[int]
    milestone_name: str
    description: str
    status: str  # 'pending', 'in_progress', 'completed', 'overdue'
    target_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    evidence_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BenchmarkRecord:
    id: int
    project_id: int
    benchmark_type: str  # 'hash_performance', 'throughput', 'latency', 'stress_test'
    test_name: str
    metric_name: str
    metric_value: float
    metric_unit: str
    test_parameters: Optional[Dict[str, Any]] = None
    environment_info: Optional[Dict[str, Any]] = None
    test_timestamp: datetime = None
    requirement_target: Optional[float] = None
    requirement_met: bool = False


@dataclass
class ChecklistRecord:
    id: int
    project_id: int
    phase_id: Optional[int]
    checklist_item: str
    status: str  # 'pending', 'in_progress', 'completed', 'blocked'
    acceptance_criteria: str
    proof_required: bool = True
    proof_url: Optional[str] = None
    assignee: Optional[str] = None
    priority: str = 'medium'  # 'low', 'medium', 'high', 'critical'
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PerformanceMetricsRecord:
    id: int
    project_id: int
    metric_category: str  # 'development', 'testing', 'deployment', 'operations'
    metric_name: str
    metric_value: float
    metric_unit: str
    baseline_value: Optional[float] = None
    improvement_percentage: Optional[float] = None
    collection_timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None


# Document Management 2.0 Models

@dataclass
class DocumentSectionRecord:
    id: int
    project_id: int
    document_type: str  # 'architecture', 'phase_plan', 'checklist', 'progress_log', 'doc_log', 'security_log', 'bug_log'
    section_id: str     # 'problem_statement', 'requirements_constraints', etc.
    content: str
    file_hash: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class CustomTemplateRecord:
    id: int
    project_id: int
    template_name: str
    template_content: str
    variables: Optional[Dict[str, Any]] = None
    is_global: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DocumentChangeRecord:
    id: int
    project_id: int
    document_path: str
    change_type: str  # 'create', 'edit', 'delete', 'sync'
    change_summary: str
    old_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@dataclass
class SyncStatusRecord:
    id: int
    project_id: int
    file_path: str
    last_sync_at: Optional[datetime] = None
    last_file_hash: Optional[str] = None
    last_db_hash: Optional[str] = None
    sync_status: str = 'synced'  # 'synced', 'conflict', 'pending', 'error'
    conflict_details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
