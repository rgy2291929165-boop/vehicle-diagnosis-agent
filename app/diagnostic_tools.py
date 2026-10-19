"""第三周 Day 3：只读模拟诊断工具。"""

DTC_CATALOG = {
    "P0AA6": {
        "description": "高压系统绝缘电阻低",
        "severity": "high",
        "recommended_check": "先读取冻结帧和绝缘相关数据。",
    }
}

VEHICLE_HISTORY = {
    "VIN-DEMO-001": {
        "recent_visits": [
            {
                "date": "2026-08-15",
                "summary": "完成高压系统例行检查",
            }
        ],
        "open_campaigns": [],
        "last_mileage_km": 42350,
    }
}

INVENTORY = {
    "HV-ISO-SENSOR-01": {
        "description": "高压绝缘监测传感器",
        "available_quantity": 2,
        "warehouse": "CQ-01",
        "status": "in_stock",
    }
}

def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空")
    return value.strip()


def lookup_dtc(vehicle_id: str, dtc_code: str) -> dict:
    """按车辆标识和 DTC 查询固定模拟数据；此函数不写入任何状态。"""

    normalized_vehicle_id = _require_text(vehicle_id, "vehicle_id")
    normalized_dtc_code = _require_text(dtc_code, "dtc_code").upper()

    record = DTC_CATALOG.get(normalized_dtc_code)
    if record is None:
        raise LookupError(f"DTC 未找到：{normalized_dtc_code}")

    return {
        "vehicle_id": normalized_vehicle_id,
        "dtc_code": normalized_dtc_code,
        **record,
    }

def lookup_vehicle_history(vehicle_id: str) -> dict:
    """按车辆标识查询固定模拟历史；此函数不写入任何状态。"""

    normalized_vehicle_id = _require_text(vehicle_id, "vehicle_id")
    record = VEHICLE_HISTORY.get(normalized_vehicle_id)

    if record is None:
        raise LookupError(f"车辆历史未找到：{normalized_vehicle_id}")

    return {
        "vehicle_id": normalized_vehicle_id,
        "recent_visits": [
            {
                "date": visit["date"],
                "summary": visit["summary"],
            }
            for visit in record["recent_visits"]
        ],
        "open_campaigns": list(record["open_campaigns"]),
        "last_mileage_km": record["last_mileage_km"],
    }

def lookup_inventory(part_number: str) -> dict:
    """按零件号查询固定模拟库存；此函数不写入任何状态。"""

    normalized_part_number = _require_text(part_number, "part_number").upper()
    item = INVENTORY.get(normalized_part_number)

    if item is None:
        raise LookupError(f"库存未找到：{normalized_part_number}")

    return {
        "part_number": normalized_part_number,
        **item,
    }