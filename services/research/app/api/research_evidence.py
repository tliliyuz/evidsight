"""Evidence 与 Report 读取 API — /api/v1/*

对齐 API.md §9（task READ 权限）：
- GET /api/v1/research/tasks/{task_id}/evidence
- GET /api/v1/evidence/{evidence_id}
- GET /api/v1/evidence/{evidence_id}/relations
- GET /api/v1/reports/{report_id}
- GET /api/v1/reports/{report_id}/sections/{section_id}

信封沿用全平台 {"code","message","data"}（API.md §8.2 迁移态）。
内部 Evidence 不返回正文（ADR-003）；内部原文展开由 Knowledge 来源访问 API 实时鉴权。
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    PermissionDeniedException,
    TaskNotFoundException,
)
from app.dependencies import get_current_user, get_db, require_task_accessible
from app.models.research_task import ResearchTask
from app.services import report_reader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Evidence 与 Report"])


def _ok(data: dict) -> dict:
    return {"code": "0", "message": "ok", "data": data}


async def _require_evidence_accessible(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按对外 UUID 加载 Evidence，并校验其 Task 归属与 owner 访问权。"""
    ev = await report_reader._load_evidence_by_external_id(db, evidence_id)
    if ev is None:
        raise TaskNotFoundException(evidence_id)
    task = await db.get(ResearchTask, ev.task_id)
    if task is None:
        raise TaskNotFoundException(ev.task_id)
    if task.user_id != current_user["user_id"]:
        raise PermissionDeniedException()
    return ev


@router.get("/research/tasks/{task_id}/evidence")
async def list_task_evidence(
    task: ResearchTask = Depends(require_task_accessible),
    db: AsyncSession = Depends(get_db),
):
    """任务证据列表（task READ）。"""
    data = await report_reader.list_task_evidence(db, task)
    return _ok(data)


@router.get("/evidence/{evidence_id}")
async def get_evidence_detail(
    ev=Depends(_require_evidence_accessible),
    db: AsyncSession = Depends(get_db),
):
    """单条证据（task READ，按对外 UUID）。"""
    data = await report_reader.get_evidence_detail(db, ev.external_id)
    if data is None:
        raise TaskNotFoundException(ev.external_id)
    return _ok(data)


@router.get("/evidence/{evidence_id}/relations")
async def get_evidence_relations(
    ev=Depends(_require_evidence_accessible),
    db: AsyncSession = Depends(get_db),
):
    """证据关系（supports/contradicts/context）。"""
    data = await report_reader.list_evidence_relations(db, ev.external_id)
    if data is None:
        raise TaskNotFoundException(ev.external_id)
    return _ok(data)


async def _require_report_accessible(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按报告 UUID 加载 Report，并校验其 Task 归属与 owner 访问权。"""
    from app.models.report import Report

    report = await db.get(Report, report_id)
    if report is None:
        raise TaskNotFoundException(report_id)
    task = await db.get(ResearchTask, report.task_id)
    if task is None:
        raise TaskNotFoundException(report.task_id)
    if task.user_id != current_user["user_id"]:
        raise PermissionDeniedException()
    return report


@router.get("/reports/{report_id}")
async def get_report_detail(
    report=Depends(_require_report_accessible),
    db: AsyncSession = Depends(get_db),
):
    """报告详情（task READ）。"""
    data = await report_reader.get_report_detail(db, report.id)
    if data is None:
        raise TaskNotFoundException(report.id)
    return _ok(data)


@router.get("/reports/{report_id}/sections/{section_id}")
async def get_report_section(
    report=Depends(_require_report_accessible),
    section_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    """报告单章节（task READ）。"""
    data = await report_reader.get_report_section(db, report.id, section_id)
    if data is None:
        raise TaskNotFoundException(section_id)
    return _ok(data)
