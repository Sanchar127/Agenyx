from app.tools.calculator import calculator
from app.tools.registry import Tool, ToolRegistry


def create_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="calculator",
            description="Calculate a mathematical expression.",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "A mathematical expression such as "
                            "25 * 17"
                        ),
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
            execute=calculator,
        )
    )

    return registry
