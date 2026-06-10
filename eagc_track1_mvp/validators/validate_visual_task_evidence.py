from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


VALID_STATUSES = {"complete", "uncertain", "failed"}
EVIDENCE_FIELDS = ("type", "source", "content", "frame_ids", "confidence")


def validate(result_path: Path, audit_path: Path | None = None) -> List[str]:
    errors: List[str] = []
    result = _read_json(result_path, errors, "visual_task_result")
    audit = _read_json(audit_path, errors, "run_audit") if audit_path else {}
    if errors:
        return errors

    status = result.get("status")
    if status not in VALID_STATUSES:
        errors.append(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}.")
    if not str(result.get("answer") or "").strip():
        errors.append("answer field cannot be empty.")
    if not str(result.get("evidence_summary") or "").strip():
        errors.append("evidence_summary field cannot be empty.")

    supporting = _evidence_list(result, "supporting_evidence", errors)
    contradicting = _evidence_list(result, "contradicting_evidence", errors)
    missing = _evidence_list(result, "missing_evidence", errors)
    confidence = _number(result.get("confidence"), "confidence", errors)

    if status == "complete" and not supporting:
        errors.append("complete visual task result requires supporting_evidence_count > 0.")
    if status == "uncertain" and not missing and confidence >= 0.6:
        errors.append("uncertain visual task result requires missing_evidence_count > 0 or confidence < 0.6.")
    if status == "complete" and contradicting:
        errors.append("complete visual task result cannot include contradicting_evidence without an explicit resolution.")

    if audit:
        expected_path = str(audit.get("visual_task_result_path") or "")
        if expected_path:
            try:
                if not Path(expected_path).resolve().exists():
                    errors.append("run_audit.visual_task_result_path does not exist.")
            except OSError:
                errors.append("run_audit.visual_task_result_path cannot be resolved.")
        _compare_count(audit, "supporting_evidence_count", len(supporting), errors)
        _compare_count(audit, "contradicting_evidence_count", len(contradicting), errors)
        _compare_count(audit, "missing_evidence_count", len(missing), errors)
        if audit.get("visual_task_confidence") is not None:
            audit_confidence = _number(audit.get("visual_task_confidence"), "run_audit.visual_task_confidence", errors)
            if abs(audit_confidence - confidence) > 0.0001:
                errors.append("run_audit.visual_task_confidence does not match visual_task_result.confidence.")

    return errors


def _read_json(path: Path | None, errors: List[str], label: str) -> Dict[str, Any]:
    if path is None:
        errors.append(f"Missing {label} path.")
        return {}
    if not path.exists():
        errors.append(f"Missing {label}: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label} JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object.")
        return {}
    return data


def _evidence_list(result: Dict[str, Any], field: str, errors: List[str]) -> List[Dict[str, Any]]:
    value = result.get(field)
    if not isinstance(value, list):
        errors.append(f"{field} must be a list.")
        return []
    valid_items = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{field}[{index}] must be an object.")
            continue
        for required in EVIDENCE_FIELDS:
            if required not in item:
                errors.append(f"{field}[{index}] missing field: {required}")
        if not isinstance(item.get("content"), dict):
            errors.append(f"{field}[{index}].content must be an object.")
        if not isinstance(item.get("frame_ids"), list):
            errors.append(f"{field}[{index}].frame_ids must be a list.")
        _number(item.get("confidence"), f"{field}[{index}].confidence", errors)
        valid_items.append(item)
    return valid_items


def _number(value: Any, label: str, errors: List[str]) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric.")
        return 0.0
    if numeric < 0.0 or numeric > 1.0:
        errors.append(f"{label} must be between 0.0 and 1.0.")
    return numeric


def _compare_count(audit: Dict[str, Any], field: str, expected: int, errors: List[str]) -> None:
    try:
        actual = int(audit.get(field, -1))
    except (TypeError, ValueError):
        errors.append(f"run_audit.{field} must be an integer.")
        return
    if actual != expected:
        errors.append(f"run_audit.{field}={actual} does not match visual_task_result count {expected}.")


def main() -> int:
    result_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/visual_task_result.json")
    audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/run_audit.json")
    errors = validate(result_path, audit_path)
    if errors:
        print("Visual task evidence validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Visual task evidence validation passed: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
