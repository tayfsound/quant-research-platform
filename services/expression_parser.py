"""UCEL Parser v2 — string → AST."""
from contracts.expression import (
    Comparison,
    Constant,
    Expression,
    LogicalAnd,
    LogicalOr,
    Node,
    OpType,
    Variable,
)


def parse_expression(expression_str: str, name: str = "") -> Expression:
    parts = expression_str.replace("(", " ( ").replace(")", " ) ").split()
    node, _ = _parse_parts(parts, 0)
    return Expression(name=name, description=expression_str, root=node)


def _parse_parts(parts: list[str], pos: int) -> tuple[Node, int]:
    if pos >= len(parts):
        return Constant(value=0), pos

    token = parts[pos]

    if token == "NOT":
        child, new_pos = _parse_parts(parts, pos + 1)
        from contracts.expression import LogicalNot
        return LogicalNot(child=child), new_pos

    if token == "(":
        depth = 1
        end = pos + 1
        while end < len(parts) and depth > 0:
            if parts[end] == "(":
                depth += 1
            elif parts[end] == ")":
                depth -= 1
            end += 1
        inner = parts[pos + 1:end - 1]
        inner_node, _ = _parse_parts(inner, 0)
        if end < len(parts) and parts[end] in ("AND", "OR"):
            op = parts[end]
            right, _ = _parse_parts(parts, end + 1)
            if op == "AND":
                return LogicalAnd(children=[inner_node, right]), len(parts)
            else:
                return LogicalOr(children=[inner_node, right]), len(parts)
        return inner_node, end

    if pos + 2 < len(parts) and parts[pos + 1] in (">", "<", ">=", "<=", "==", "!="):
        var_name = token
        op_str = parts[pos + 1]
        val = float(parts[pos + 2])
        op_map = {">": OpType.GT, "<": OpType.LT, ">=": OpType.GTE,
                  "<=": OpType.LTE, "==": OpType.EQ, "!=": OpType.NEQ}
        node = Comparison(op=op_map[op_str], left=Variable(name=var_name), right=Constant(value=val))
        if pos + 3 < len(parts) and parts[pos + 3] in ("AND", "OR"):
            op = parts[pos + 3]
            right, _ = _parse_parts(parts, pos + 4)
            if op == "AND":
                return LogicalAnd(children=[node, right]), len(parts)
            else:
                return LogicalOr(children=[node, right]), len(parts)
        return node, pos + 3

    try:
        return Constant(value=float(token)), pos + 1
    except ValueError:
        return Variable(name=token), pos + 1
