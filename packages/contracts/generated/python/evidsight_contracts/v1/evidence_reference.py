"""由 packages/contracts/schemas/v1/evidence-reference.schema.json 生成，请勿手工编辑业务字段。"""

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .common import (
    EvidenceId,
    InternalSourceIdentity,
    NonEmptyStr,
    NonNegativeInt,
    ScoreKind,
    Timestamp,
)


class WebSourceIdentity(BaseModel):
    """外部来源身份：规范化 URL 与获取时间。"""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, description="规范化 URL。")
    fetched_at: Timestamp = Field(description="抓取时间。")


class Display(BaseModel):
    """可公开给当前任务读者的标题与位置摘要。"""

    model_config = ConfigDict(extra="forbid")

    title: NonEmptyStr
    location_summary: NonEmptyStr | None = None


class ScoreSummary(BaseModel):
    """生成时的受控评分摘要；不作为当前权限或有效性证明。"""

    model_config = ConfigDict(extra="forbid")

    best_score: float
    score_kind: ScoreKind
    rank: NonNegativeInt = Field(ge=0)


class EvidenceReference(BaseModel):
    """跨内部/外部来源的可持久化最小引用；结构上禁止正文、Embedding、Prompt 或存储路径。"""

    model_config = ConfigDict(extra="forbid")

    evidence_id: EvidenceId
    source_type: Literal["internal", "web"]
    source_identity: Union[InternalSourceIdentity, WebSourceIdentity]
    display: Display
    captured_at: Timestamp = Field(description="Evidence 创建时间。")
    source_observed_at: Timestamp = Field(description="检索或抓取时观察到的来源时间。")
    score_summary: ScoreSummary
    validity: Literal["available", "restricted", "missing", "stale"]
