"""外部 v1 标准错误响应（API.md §4）。"""

from typing import Any

ERROR_CODE_MAP = {
    "E1001": "KB_NOT_FOUND",
    "E1002": "KB_NAME_CONFLICT",
    "E2001": "DOC_NOT_FOUND",
    "E2002": "DOC_UNSUPPORTED_MEDIA_TYPE",
    "E2003": "DOC_FILE_TOO_LARGE",
    "E2004": "DOC_PARSE_FAILED",
    "E2005": "DOC_INGEST_FAILED",
    "E2006": "DOC_STORAGE_ERROR",
    "E2007": "DOC_VECTOR_STORE_ERROR",
    "E2008": "DOC_EMBEDDING_UPSTREAM",
    "E2009": "DOC_PARSER_INVALID",
    "E2010": "DOC_RETRY_FAILED",
    "E2011": "DOC_PROCESSING_CONFLICT",
    "E2012": "DOC_OVERRIDE_CONFLICT",
    "E2013": "DOC_NAME_CONFLICT",
    "E2014": "DOC_BATCH_LIMIT",
    "E2015": "EVIDENCE_SOURCE_UNAVAILABLE",
    "E3001": "CHAT_CONVERSATION_NOT_FOUND",
    "E3002": "CHAT_CONVERSATION_FORBIDDEN",
    "E4001": "CHAT_KB_EMPTY",
    "E4002": "CHAT_LLM_UPSTREAM",
    "E4003": "CHAT_RETRIEVAL_FAILED",
    "E4004": "CHAT_RATE_LIMIT",
    "E4005": "CHAT_QUESTION_EMPTY",
    "E5001": "AUTH_USERNAME_CONFLICT",
    "E5002": "AUTH_INVALID_CREDENTIALS",
    "E5003": "AUTH_TOKEN_EXPIRED",
    "E5004": "AUTH_TOKEN_INVALID",
    "E5005": "AUTH_FORBIDDEN",
    "E5006": "AUTH_REFRESH_EXPIRED",
    "E5007": "AUTH_REFRESH_REVOKED",
    "E5008": "AUTH_REFRESH_INVALID",
    "E5009": "AUTH_REFRESH_REPLAY",
    "E5010": "AUTH_USER_DISABLED",
    "E5011": "AUTH_REFRESH_CONCURRENT",
    "E7001": "SYSTEM_TRACE_NOT_FOUND",
    "E7002": "AUTH_USER_NOT_FOUND",
    "E7003": "AUTH_ADMIN_SELF_MODIFY",
    "E7004": "AUTH_PASSWORD_REUSED",
    "E9001": "SYSTEM_INTERNAL_ERROR",
    "E9002": "SYSTEM_UNAVAILABLE",
    "E9003": "SYSTEM_VALIDATION_FAILED",
    "E9004": "SYSTEM_RATE_LIMIT",
}


def canonical_error_code(code: str) -> str:
    """迁移旧 E 码为 v1 命名空间；已是语义码时原样返回。"""
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
    """构建 API.md §4 标准 error 信封。"""
    return {
        "error": {
            "error_code": canonical_error_code(code),
            "message": message,
            "request_id": request_id,
            "retryable": status_code in {429, 502, 503, 504} if retryable is None else retryable,
            "details": details or {},
        }
    }
