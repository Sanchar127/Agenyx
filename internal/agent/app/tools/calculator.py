import ast
import operator


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def calculator(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid mathematical expression") from exc

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(
            node.value,
            (int, float),
        ):
            return node.value

        if isinstance(node, ast.BinOp):
            operation = _OPERATORS.get(type(node.op))

            if operation is None:
                raise ValueError("Unsupported operator")

            return operation(
                evaluate(node.left),
                evaluate(node.right),
            )

        raise ValueError("Unsupported expression")

    return str(evaluate(tree.body))
