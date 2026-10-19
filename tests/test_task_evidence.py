"""本地审核资料集成检查；损坏清单均为临时模拟 fixture。"""

from copy import deepcopy
import hashlib
import json

import pytest

from app import task_evidence
from app.task_contracts import EvidencePack, TaskRequest, TaskResult, validate_result_evidence


@pytest.mark.parametrize("topic, source_id, document_id, url_part", [
    ("charge_port_RED", "w5-red", "w2-tesla-charge-status", "GUID-BEE08D47"),
    ("CP_a054", "w5-cp_a054", "w2-tesla-charge-alerts", "GUID-9A3F0F72"),
])
def test_real_local_reviewed_sources_preserve_provenance_limits_and_file_bytes(
    topic, source_id, document_id, url_part,
):
    inventory_path = task_evidence.SOURCE_INVENTORY_PATH
    before = hashlib.sha256(inventory_path.read_bytes()).hexdigest()

    pack = task_evidence.lookup_charge_reference(topic, task_id="task_existing")

    assert pack.task_id == "task_existing"
    assert len(pack.items) == 1
    item = pack.items[0]
    assert item.chunk_id == f"{source_id}:reviewed:0"
    assert item.document_id == document_id
    assert url_part in item.source
    assert item.source.startswith("https://www.tesla.com/ownersmanual/model3/en_us/")
    assert item.material_kind == "reviewed_summary"
    assert "经人工复核的中文摘要，非完整原文" in item.limitations
    assert "个性化车辆适用性未核实" in item.limitations
    for field in (
        "model_year_range", "manual_revision",
        "applicable_vehicle_software_version", "publication_or_revision_date",
    ):
        assert f"资料适用性未知：{field}" in item.limitations
    assert hashlib.sha256(inventory_path.read_bytes()).hexdigest() == before


def test_cp_a054_can_be_looked_up_without_a_standard_dtc_or_cp_a053_content():
    request = TaskRequest(question="请解释 CP_a054", alert_code="CP_a054")

    pack = task_evidence.lookup_charge_reference(request.alert_code, task_id="task_existing")

    assert request.dtc_codes == []
    assert pack.items[0].text.splitlines() == [
        "充电口锁扣未能锁住充电线",
        "锁扣未扣合时交流充电限至 16A",
        "同一条件下直流快充/超充不可用",
    ]
    assert "CP_a053" not in pack.items[0].text


def test_reviewed_pack_round_trip_and_explicit_result_reference_check():
    pack = task_evidence.lookup_charge_reference("charge_port_RED", task_id="task_existing")
    restored = EvidencePack.model_validate_json(pack.model_dump_json())
    result = TaskResult(
        task_id="task_existing", status="answer",
        message="合成结果，仅验证本地资料与引用关联，不代表模型已作答。",
        citations=[restored.items[0].chunk_id],
    )

    assert restored == pack
    assert validate_result_evidence(result, restored) is None
    wrong = TaskResult(
        task_id="task_existing", status="answer", message="合成错误引用",
        citations=["unavailable:0"],
    )
    with pytest.raises(ValueError, match="引用不在当前任务证据包中"):
        validate_result_evidence(wrong, restored)


@pytest.mark.parametrize("topic", ["CP_a053", "CP_a999", "", None, [], True])
def test_unsupported_topics_fail_before_reading_any_inventory(topic, tmp_path, monkeypatch):
    monkeypatch.setattr(task_evidence, "SOURCE_INVENTORY_PATH", tmp_path / "absent.json")

    with pytest.raises(ValueError, match="不支持的资料主题"):
        task_evidence.lookup_charge_reference(topic, task_id="task_existing")


def test_caller_cannot_supply_a_source_path():
    with pytest.raises(TypeError, match="source_path"):
        task_evidence.lookup_charge_reference(
            "CP_a054", task_id="task_existing", source_path="/tmp/untrusted.json",
        )


def test_task_identifier_must_be_supplied_as_a_server_side_keyword():
    with pytest.raises(TypeError):
        task_evidence.lookup_charge_reference("CP_a054", "task_existing")


@pytest.fixture
def temporary_inventory(tmp_path, monkeypatch):
    """复制实际清单为临时故障注入样例，绝不修改主项目来源。"""
    payload = json.loads(task_evidence.SOURCE_INVENTORY_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "simulated-inventory.json"
    monkeypatch.setattr(task_evidence, "SOURCE_INVENTORY_PATH", path)

    def write(updated):
        path.write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")

    write(payload)
    return deepcopy(payload), write


@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_missing_or_ambiguous_source_is_rejected(temporary_inventory, mode):
    payload, write = temporary_inventory
    target = next(row for row in payload["sources"] if row["source_id"] == "w5-cp_a054")
    if mode == "missing":
        payload["sources"].remove(target)
    else:
        payload["sources"].append(deepcopy(target))
    write(payload)

    with pytest.raises(ValueError, match="目标来源必须存在且只能有一条记录"):
        task_evidence.lookup_charge_reference("CP_a054", task_id="task_existing")


@pytest.mark.parametrize("claims", [[], "并非列表", [" \t "], [123], None])
def test_invalid_reviewed_claims_are_rejected_without_inventing_text(temporary_inventory, claims):
    payload, write = temporary_inventory
    payload["sources"][0]["verified_claims"] = claims
    write(payload)

    with pytest.raises(ValueError, match="verified_claims"):
        task_evidence.lookup_charge_reference("charge_port_RED", task_id="task_existing")


@pytest.mark.parametrize("field, value", [
    ("official_url", " \t "),
    ("local_document_id", None),
    ("material_kind", "mock"),
    ("unknown_scope", "unknown"),
])
def test_incomplete_or_mislabeled_source_cannot_be_promoted_to_evidence(
    temporary_inventory, field, value,
):
    payload, write = temporary_inventory
    payload["sources"][0][field] = value
    write(payload)

    with pytest.raises(ValueError):
        task_evidence.lookup_charge_reference("charge_port_RED", task_id="task_existing")


@pytest.mark.parametrize("payload", [[], {}, {"sources": "bad"}, {"sources": [None]}])
def test_invalid_inventory_structure_is_rejected(temporary_inventory, payload):
    _, write = temporary_inventory
    write(payload)

    with pytest.raises(ValueError, match="sources"):
        task_evidence.lookup_charge_reference("CP_a054", task_id="task_existing")


def test_missing_inventory_is_an_error_instead_of_an_empty_success(tmp_path, monkeypatch):
    monkeypatch.setattr(task_evidence, "SOURCE_INVENTORY_PATH", tmp_path / "absent.json")

    with pytest.raises(ValueError, match="无法读取资料清单"):
        task_evidence.lookup_charge_reference("CP_a054", task_id="task_existing")


def test_invalid_json_inventory_is_reported_explicitly(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    monkeypatch.setattr(task_evidence, "SOURCE_INVENTORY_PATH", path)

    with pytest.raises(ValueError, match="无法读取资料清单"):
        task_evidence.lookup_charge_reference("CP_a054", task_id="task_existing")


def test_task_id_is_validated_before_inventory_access(tmp_path, monkeypatch):
    monkeypatch.setattr(task_evidence, "SOURCE_INVENTORY_PATH", tmp_path / "absent.json")

    with pytest.raises(ValueError, match="task_id"):
        task_evidence.lookup_charge_reference("CP_a054", task_id=" \t ")
