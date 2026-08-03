"""JSON Schema 与 Fixture 加载工具。

契约测试通过 referencing.Registry 预注册全部 Schema（以 file:// 检索 URI），
使 jsonschema 的 Draft202012Validator 能解析跨文件 $ref，且不触发远程拉取。
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def _find_contracts_root() -> Path:
    """从本文件所在目录向上定位 packages/contracts 目录（兼容宿主机与容器内路径）。"""
    start = Path(__file__).resolve().parent
    for parent in [start] + list(start.parents):
        candidate = parent / "packages" / "contracts"
        if candidate.is_dir() and (candidate / "schemas" / "v1").is_dir():
            return candidate
    raise RuntimeError("无法定位 packages/contracts 目录")


_CONTRACTS_ROOT = _find_contracts_root()
REPO_ROOT = _CONTRACTS_ROOT.parent.parent
_SCHEMAS_DIR = _CONTRACTS_ROOT / "schemas" / "v1"
_FIXTURES_DIR = _CONTRACTS_ROOT / "fixtures" / "v1"


def _schema_file_uri(name: str) -> str:
    return (_SCHEMAS_DIR / f"{name}.schema.json").resolve().as_uri()


def _walk_and_rewrite_refs(node: Any, base_dir: Path) -> Any:
    """递归遍历 schema 树，把 ./xxx.schema.json#/... 相对 $ref 重写为 file:// 绝对 URI。"""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("./"):
                ref_path, _, fragment = value.partition("#")
                abs_path = (base_dir / ref_path).resolve()
                out[key] = f"{abs_path.as_uri()}#{fragment}"
            else:
                out[key] = _walk_and_rewrite_refs(value, base_dir)
        return out
    if isinstance(node, list):
        return [_walk_and_rewrite_refs(item, base_dir) for item in node]
    return node


def load_schema(name: str) -> dict:
    """从 packages/contracts/schemas/v1/{name}.schema.json 加载 Schema（$ref 已重写为 file://）。"""
    with (_SCHEMAS_DIR / f"{name}.schema.json").open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return _walk_and_rewrite_refs(raw, _SCHEMAS_DIR)


@lru_cache(maxsize=None)
def _registry() -> Registry:
    """以 file:// 检索 URI 预注册全部 Schema 的 Registry。"""
    resources: dict[str, Resource] = {}
    for path in sorted(_SCHEMAS_DIR.glob("*.schema.json")):
        name = path.name.removesuffix(".schema.json")
        resources[_schema_file_uri(name)] = Resource.from_contents(
            load_schema(name), default_specification=DRAFT202012
        )
    return Registry().with_resources(resources.items())


def validator_for(name: str) -> Draft202012Validator:
    """返回针对指定 Schema 的 Validator，跨文件 $ref 通过 Registry 解析。"""
    return Draft202012Validator(load_schema(name), registry=_registry())


def load_fixture(schema_name: str, validity: str, fixture_name: str) -> dict:
    """加载 fixture：valid/invalid/{schema_name}/{fixture_name}.json。"""
    path = _FIXTURES_DIR / validity / schema_name / f"{fixture_name}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_fixtures(schema_name: str, validity: str) -> list[str]:
    """列出某 Schema 的 valid 或 invalid fixture 文件名（不含 .json 后缀，排序稳定）。"""
    path = _FIXTURES_DIR / validity / schema_name
    if not path.exists():
        return []
    return sorted(p.stem for p in path.glob("*.json"))
