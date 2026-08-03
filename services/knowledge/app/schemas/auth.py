"""认证相关请求/响应模型"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username_not_numeric(cls, v: str) -> str:
        """拒绝纯数字/纯空格用户名"""
        stripped = v.strip()
        if not stripped:
            raise ValueError("用户名不能为空")
        if re.match(r"^\d+$", stripped):
            raise ValueError("用户名不能为纯数字，请包含文字或字母")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """外部身份摘要 — id 为 Platform User UUID（对齐 API.md §3.1）。"""

    id: uuid.UUID
    username: str
    role: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class LoginV1Response(BaseModel):
    """v1 登录响应 — 对齐 API.md §5 POST /api/v1/auth/login（ADR-006）。

    Refresh Token 经 HttpOnly Cookie 下发，响应体绝不含 refresh_token 明文；
    user 为外部身份摘要 UserSummary（id 为 Platform User UUID）。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒
    user: UserSummary


class RefreshV1Response(BaseModel):
    """v1 刷新响应 — 对齐 API.md §5 POST /api/v1/auth/refresh（ADR-006）。

    新 Refresh Token 经 HttpOnly Cookie 轮换下发，响应体只返回 Access Token。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)
