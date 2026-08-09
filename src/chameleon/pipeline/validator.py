"""提取结果校验：标准 JSON Schema → 动态 Pydantic 模型校验（方案 5.3）。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError, create_model

_PY_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool, "null": type(None), "any": Any}


def _build_model(name: str, schema: dict[str, Any]) -> Any:
    fields: dict[str, Any] = {}
    for fname, prop in (schema.get("properties") or {}).items():
        ptype = prop.get("type", "string")
        required = fname in schema.get("required", [])
        if ptype == "object":
            sub = _build_model(f"{name}_{fname}", prop)
            fields[fname] = (sub, ... if required else None)
        elif ptype == "array":
            fields[fname] = (list, ... if required else None)
        else:
            fields[fname] = (_PY_TYPES.get(ptype, str), ... if required else None)
    return create_model(name, **fields)


class ExtractionValidator:
    """用 JSON Schema 校验提取结果，返回字段级缺失报告。"""

    def validate(self, data: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
        """返回 (是否通过, 问题列表)。"""
        if not schema:
            return True, []
        errors: list[str] = []

        for field in schema.get("required", []):
            if data.get(field) in (None, ""):
                errors.append(f"missing_required:{field}")

        try:
            model = _build_model("Extraction", schema)
            model.model_validate(data)
        except ValidationError as exc:
            errors.extend(f"type_error:{'.'.join(str(e) for e in err['loc'])}" for err in exc.errors())
        except Exception as exc:
            errors.append(f"schema_error:{exc}")

        return len(errors) == 0, errors
