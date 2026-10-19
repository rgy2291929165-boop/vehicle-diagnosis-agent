import pytest

from app.diagnostic_tools import (
    lookup_dtc,
    lookup_inventory,
    lookup_vehicle_history,
)


def test_lookup_dtc_returns_structured_record():
    record = lookup_dtc("VIN-DEMO-001", "P0AA6")

    assert record == {
        "vehicle_id": "VIN-DEMO-001",
        "dtc_code": "P0AA6",
        "description": "高压系统绝缘电阻低",
        "severity": "high",
        "recommended_check": "先读取冻结帧和绝缘相关数据。",
    }


def test_lookup_dtc_rejects_empty_vehicle_id():
    with pytest.raises(ValueError, match="vehicle_id"):
        lookup_dtc("", "P0AA6")


def test_lookup_dtc_reports_unknown_valid_code():
    with pytest.raises(LookupError, match="DTC"):
        lookup_dtc("VIN-DEMO-001", "P9999")

def test_lookup_vehicle_history_returns_structured_record():
    history = lookup_vehicle_history("VIN-DEMO-001")

    assert history == {
        "vehicle_id": "VIN-DEMO-001",
        "recent_visits": [
            {
                "date": "2026-08-15",
                "summary": "完成高压系统例行检查",
            }
        ],
        "open_campaigns": [],
        "last_mileage_km": 42350,
    }


def test_lookup_vehicle_history_rejects_empty_vehicle_id():
    with pytest.raises(ValueError, match="vehicle_id"):
        lookup_vehicle_history("")


def test_lookup_vehicle_history_reports_unknown_vehicle():
    with pytest.raises(LookupError, match="车辆历史"):
        lookup_vehicle_history("VIN-UNKNOWN-001")

def test_lookup_inventory_returns_structured_record():
    item = lookup_inventory("HV-ISO-SENSOR-01")

    assert item == {
        "part_number": "HV-ISO-SENSOR-01",
        "description": "高压绝缘监测传感器",
        "available_quantity": 2,
        "warehouse": "CQ-01",
        "status": "in_stock",
    }


def test_lookup_inventory_rejects_empty_part_number():
    with pytest.raises(ValueError, match="part_number"):
        lookup_inventory("")


def test_lookup_inventory_reports_unknown_part():
    with pytest.raises(LookupError, match="库存"):
        lookup_inventory("PART-UNKNOWN-001")