"""由 packages/contracts/schemas/v1/common.schema.json 生成，请勿手工编辑业务字段。"""
from pydantic import Field

# SemVer：^\\d+\\.\\d+\\.\\d+(-[\\w\\.]+)?(\\+[\\w\\.]+)?$
SemVerStr = str

# UUIDv4：format=uuid
PlatformUserId = str

# NonNegativeInteger：minimum=0
NonNegativeInt = int

# NonEmptyString：minLength=1
NonEmptyStr = str

# RequestId：minLength=1
RequestId = str
