"""外部 v1 标准错误响应（API.md §4）。"""

from typing import Any

ERROR_CODE_MAP = {
    "E1001": "AUTH_USERNAME_CONFLICT",
    "E1002": "AUTH_INVALID_CREDENTIALS",
    "E1003": "AUTH_TOKEN_EXPIRED",
    "E1004": "AUTH_TOKEN_INVALID",
    "E1005": "AUTH_FORBIDDEN",
    "E1006": "AUTH_REFRESH_EXPIRED",
    "E1007": "AUTH_REFRESH_REVOKED",
    "E1008": "AUTH_REFRESH_INVALID",
    "E1009": "AUTH_REFRESH_REPLAY",
    "E1010": "AUTH_USER_DISABLED",
    "E1011": "AUTH_PASSWORD_REUSED",
    "E2001": "RS_TASK_NOT_FOUND",
    "E2002": "RS_TASK_FORBIDDEN",
    "E2003": "RS_TASK_STATE_CONFLICT",
    "E2004": "RS_TASK_CANCELED",
    "E2005": "RS_TOPIC_TOO_LONG",
    "E2006": "RS_TASK_TYPE_INVALID",
    "E2007": "RS_DEPTH_INVALID",
    "E2008": "RS_REQUIREMENTS_INVALID",
    "E2009": "RS_IDEMPOTENCY_CONFLICT",
    "E3101": "RS_PLANNING_FAILED",
    "E3102": "RS_SEARCH_FAILED",
    "E3103": "RS_INSUFFICIENT_EVIDENCE",
    "E3104": "RS_SYNTHESIS_FAILED",
    "E3105": "RS_RERANK_FAILED",
    "E3106": "RS_EVIDENCE_GRAPH_FAILED",
    "E3107": "REPORT_RENDER_FAILED",
    "E3108": "RS_LLM_TIMEOUT",
    "E3109": "RS_LLM_RATE_LIMIT",
    "E3110": "RS_LLM_AUTH_FAILED",
    "E3111": "RS_LLM_UPSTREAM",
    "E3112": "RS_WORKER_LOST",
    "E3113": "RS_WORKER_NOT_PICKED_UP",
    "E3114": "RS_KNOWLEDGE_BASES_MISSING",
    "E3115": "RS_INTERNAL_KNOWLEDGE_FORBIDDEN",
    "E3116": "RS_INTERNAL_RETRIEVAL_UNAVAILABLE",
    "E3117": "RS_INTERNAL_RETRIEVAL_CONTRACT",
    "E3999": "RS_UNKNOWN_INTERNAL",
    "E9001": "SYSTEM_INTERNAL_ERROR",
    "E9002": "SYSTEM_UNAVAILABLE",
    "E9003": "SYSTEM_VALIDATION_FAILED",
    "E9004": "SYSTEM_RATE_LIMIT",
}


def canonical_error_code(code: str) -> str:
    return ERROR_CODE_MAP.get(code, code)


def error_envelope(
    *,
    code: str,
    message: str,
    request_id: str,
    status_code: int,
    details: dict[str, Any] | None = None,
    retryable: bool | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "error_code": canonical_error_code(code),
            "message": message,
            "request_id": request_id,
            "retryable": status_code in {429, 502, 503, 504} if retryable is None else retryable,
            "details": details or {},
        }
    }
