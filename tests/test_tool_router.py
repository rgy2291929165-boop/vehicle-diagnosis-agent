import pytest

from app import tool_router


def make_call(tool_name: str, arguments: dict) -> dict:
    return {
        "tool_name": tool_name,
        "arguments": arguments,
    }


def test_router_executes_an_allowed_tool_and_records_success():
    trace = []

    result = tool_router.execute_tool_call(
        make_call(
            "lookup_dtc",
            {
                "vehicle_id": "VIN-DEMO-001",
                "dtc_code": "P0AA6",
            },
        ),
        trace,
    )

    assert result["dtc_code"] == "P0AA6"
    assert trace == [
        {
            "tool_name": "lookup_dtc",
            "status": "success",
        }
    ]


def test_router_rejects_a_tool_outside_the_allow_list():
    trace = []

    with pytest.raises(PermissionError):
        tool_router.execute_tool_call(
            make_call("delete_work_order", {}),
            trace,
        )

    assert trace == [
        {
            "tool_name": "delete_work_order",
            "status": "rejected",
            "reason": "tool_not_allowed",
        }
    ]


def test_invalid_arguments_do_not_enter_the_tool_function(monkeypatch):
    trace = []
    was_called = False

    def should_not_be_called(vehicle_id: str, dtc_code: str) -> dict:
        nonlocal was_called
        was_called = True
        return {}

    monkeypatch.setitem(
        tool_router.TOOL_REGISTRY,
        "lookup_dtc",
        should_not_be_called,
    )

    with pytest.raises(ValueError):
        tool_router.execute_tool_call(
            make_call(
                "lookup_dtc",
                {
                    "vehicle_id": "",
                    "dtc_code": "P0AA6",
                },
            ),
            trace,
        )

    assert was_called is False
    assert trace == [
        {
            "tool_name": "lookup_dtc",
            "status": "rejected",
            "reason": "invalid_arguments",
        }
    ]

@pytest.mark.parametrize(
    "arguments",
    [
        {"vehicle_id": "VIN-DEMO-001"},
        {
            "vehicle_id": "VIN-DEMO-001",
            "dtc_code": "P0AA6",
            "unexpected": "value",
        },
    ],
)
def test_router_rejects_missing_or_extra_arguments(arguments):
    trace = []

    with pytest.raises(ValueError):
        tool_router.execute_tool_call(
            make_call("lookup_dtc", arguments),
            trace,
        )

    assert trace == [
        {
            "tool_name": "lookup_dtc",
            "status": "rejected",
            "reason": "invalid_arguments",
        }
    ]