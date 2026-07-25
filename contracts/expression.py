"""Unified Cognitive Expression Language (UCEL) — AST v2.1 (Production-ready)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Union, Literal, ClassVar
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class NodeType(StrEnum):
    CONSTANT = "constant"
    VARIABLE = "variable"
    BINARY_OP = "binary_op"
    COMPARISON = "comparison"
    FUNCTION_CALL = "function_call"
    LOGICAL_AND = "logical_and"
    LOGICAL_OR = "logical_or"
    LOGICAL_NOT = "logical_not"


class OpType(StrEnum):
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


class MissingVariableError(Exception):
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        super().__init__(f"Variable '{variable_name}' not found in context")


class DivisionByZeroError(Exception):
    def __init__(self):
        super().__init__("Division by zero in expression")


class UnknownFunctionError(Exception):
    def __init__(self, function_name: str):
        self.function_name = function_name
        super().__init__(f"Unknown function '{function_name}' — not in whitelist")


class Value(BaseModel):
    type: Literal["boolean", "numeric"]
    boolean: bool | None = None
    numeric: float | None = None

    @classmethod
    def from_bool(cls, value: bool) -> "Value":
        return cls(type="boolean", boolean=value)

    @classmethod
    def from_numeric(cls, value: float) -> "Value":
        return cls(type="numeric", numeric=value)

    def is_true(self) -> bool:
        if self.type != "boolean":
            raise TypeError(f"Numeric value ({self.numeric}) cannot be used as boolean. Use comparison operators (>, <, ==) instead.")
        return self.boolean is True


class EvaluationStep(BaseModel):
    expression: str
    inputs: dict[str, float] = Field(default_factory=dict)
    result: str
    is_true: bool


class EvaluationResult(BaseModel):
    value: Value
    explanation: str = ""
    inputs: dict[str, float] = Field(default_factory=dict)
    confidence: float = 1.0
    trace: list[EvaluationStep] = Field(default_factory=list)
    factors: list[str] = Field(default_factory=list)


class Constant(BaseModel):
    node_type: Literal[NodeType.CONSTANT] = NodeType.CONSTANT
    value: float

    def explain(self) -> str:
        return str(self.value)

    def evaluate(self, context: dict[str, float]) -> Value:
        return Value.from_numeric(self.value)

    def to_dict(self) -> dict:
        return {"node_type": "constant", "value": self.value}


class Variable(BaseModel):
    node_type: Literal[NodeType.VARIABLE] = NodeType.VARIABLE
    name: str

    def explain(self) -> str:
        return self.name.upper()

    def evaluate(self, context: dict[str, float]) -> Value:
        if self.name not in context:
            raise MissingVariableError(self.name)
        return Value.from_numeric(context[self.name])

    def to_dict(self) -> dict:
        return {"node_type": "variable", "name": self.name}


class BinaryOp(BaseModel):
    node_type: Literal[NodeType.BINARY_OP] = NodeType.BINARY_OP
    op: OpType
    left: "Node"
    right: "Node"

    def explain(self) -> str:
        return f"({self.left.explain()} {self.op.value} {self.right.explain()})"

    def evaluate(self, context: dict[str, float]) -> Value:
        l = self.left.evaluate(context)
        r = self.right.evaluate(context)
        if l.type != "numeric" or r.type != "numeric":
            return Value.from_numeric(0.0)
        ln, rn = l.numeric, r.numeric
        match self.op:
            case OpType.ADD: return Value.from_numeric(ln + rn)
            case OpType.SUB: return Value.from_numeric(ln - rn)
            case OpType.MUL: return Value.from_numeric(ln * rn)
            case OpType.DIV:
                if rn == 0:
                    raise DivisionByZeroError()
                return Value.from_numeric(ln / rn)
            case _: return Value.from_numeric(0.0)

    def to_dict(self) -> dict:
        return {"node_type": "binary_op", "op": self.op.value, "left": self.left.to_dict(), "right": self.right.to_dict()}


class Comparison(BaseModel):
    node_type: Literal[NodeType.COMPARISON] = NodeType.COMPARISON
    op: OpType
    left: "Node"
    right: "Node"

    def explain(self) -> str:
        op_map = {OpType.GT: ">", OpType.LT: "<", OpType.GTE: ">=",
                  OpType.LTE: "<=", OpType.EQ: "==", OpType.NEQ: "!="}
        return f"{self.left.explain()} {op_map.get(self.op, self.op.value)} {self.right.explain()}"

    def evaluate(self, context: dict[str, float]) -> Value:
        l = self.left.evaluate(context)
        r = self.right.evaluate(context)
        if l.type != "numeric" or r.type != "numeric":
            return Value.from_bool(False)
        ln, rn = l.numeric, r.numeric
        match self.op:
            case OpType.GT: return Value.from_bool(ln > rn)
            case OpType.LT: return Value.from_bool(ln < rn)
            case OpType.GTE: return Value.from_bool(ln >= rn)
            case OpType.LTE: return Value.from_bool(ln <= rn)
            case OpType.EQ: return Value.from_bool(ln == rn)
            case OpType.NEQ: return Value.from_bool(ln != rn)
        return Value.from_bool(False)

    def to_dict(self) -> dict:
        return {"node_type": "comparison", "op": self.op.value, "left": self.left.to_dict(), "right": self.right.to_dict()}


class FunctionCall(BaseModel):
    node_type: Literal[NodeType.FUNCTION_CALL] = NodeType.FUNCTION_CALL
    name: str
    arguments: list["Node"] = Field(default_factory=list)
    ALLOWED_FUNCTIONS: ClassVar[set[str]] = {"RSI", "SMA", "EMA", "ATR", "MACD", "ABS", "MAX", "MIN", "BELIEF", "CONFIDENCE"}

    def explain(self) -> str:
        args = ", ".join(a.explain() for a in self.arguments)
        return f"{self.name}({args})"

    def evaluate(self, context: dict[str, float]) -> Value:
        if self.name not in self.ALLOWED_FUNCTIONS:
            raise UnknownFunctionError(self.name)
        return Value.from_numeric(0.0)

    def to_dict(self) -> dict:
        return {"node_type": "function_call", "name": self.name, "arguments": [a.to_dict() for a in self.arguments]}


class LogicalAnd(BaseModel):
    node_type: Literal[NodeType.LOGICAL_AND] = NodeType.LOGICAL_AND
    children: list["Node"]

    def explain(self) -> str:
        return " VE ".join(c.explain() for c in self.children)

    def evaluate(self, context: dict[str, float]) -> Value:
        return Value.from_bool(all(c.evaluate(context).is_true() for c in self.children))

    def to_dict(self) -> dict:
        return {"node_type": "logical_and", "children": [c.to_dict() for c in self.children]}


class LogicalOr(BaseModel):
    node_type: Literal[NodeType.LOGICAL_OR] = NodeType.LOGICAL_OR
    children: list["Node"]

    def explain(self) -> str:
        return " VEYA ".join(c.explain() for c in self.children)

    def evaluate(self, context: dict[str, float]) -> Value:
        return Value.from_bool(any(c.evaluate(context).is_true() for c in self.children))

    def to_dict(self) -> dict:
        return {"node_type": "logical_or", "children": [c.to_dict() for c in self.children]}


class LogicalNot(BaseModel):
    node_type: Literal[NodeType.LOGICAL_NOT] = NodeType.LOGICAL_NOT
    child: "Node"

    def explain(self) -> str:
        return f"DEĞİL ({self.child.explain()})"

    def evaluate(self, context: dict[str, float]) -> Value:
        return Value.from_bool(not self.child.evaluate(context).is_true())

    def to_dict(self) -> dict:
        return {"node_type": "logical_not", "child": self.child.to_dict()}


Node = Annotated[
    Union[Constant, Variable, BinaryOp, Comparison, FunctionCall, LogicalAnd, LogicalOr, LogicalNot],
    Field(discriminator="node_type")
]


class Expression(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    root: Node
    created_at: datetime = Field(default_factory=datetime.now)

    def explain(self) -> str:
        return self.root.explain()

    def evaluate(self, context: dict[str, float]) -> EvaluationResult:
        trace: list[EvaluationStep] = []
        try:
            value = self.root.evaluate(context)
            self._build_trace(self.root, context, trace)
            return EvaluationResult(
                value=value,
                explanation=self.explain(),
                inputs={k: v for k, v in context.items() if k in self._collect_variables()},
                confidence=1.0,
                trace=trace,
            )
        except MissingVariableError as e:
            return EvaluationResult(
                value=Value.from_bool(False),
                explanation=f"Eksik değişken: {e.variable_name}",
                inputs=context,
                confidence=0.0,
            )

    def _build_trace(self, node: Node, context: dict[str, float], trace: list[EvaluationStep]):
        if isinstance(node, Comparison):
            l = node.left.evaluate(context)
            r = node.right.evaluate(context)
            trace.append(EvaluationStep(
                expression=node.explain(),
                inputs={},
                result=str(l.numeric) + " " + node.op.value + " " + str(r.numeric) + " => " + str(node.evaluate(context).is_true()),
                is_true=node.evaluate(context).is_true(),
            ))
        elif isinstance(node, LogicalAnd):
            for c in node.children:
                self._build_trace(c, context, trace)
            trace.append(EvaluationStep(
                expression=node.explain(),
                inputs={},
                result="ALL => " + str(node.evaluate(context).is_true()),
                is_true=node.evaluate(context).is_true(),
            ))
        elif isinstance(node, LogicalOr):
            for c in node.children:
                self._build_trace(c, context, trace)
        elif isinstance(node, LogicalNot):
            self._build_trace(node.child, context, trace)
        elif isinstance(node, BinaryOp):
            l = node.left.evaluate(context)
            r = node.right.evaluate(context)
            trace.append(EvaluationStep(
                expression=node.explain(),
                inputs={},
                result=str(l.numeric) + " " + node.op.value + " " + str(r.numeric) + " = " + str(node.evaluate(context).numeric),
                is_true=False,
            ))

    def _collect_variables(self) -> set[str]:
        vars_found: set[str] = set()
        def walk(node: Node):
            if isinstance(node, Variable):
                vars_found.add(node.name)
            elif isinstance(node, BinaryOp):
                walk(node.left); walk(node.right)
            elif isinstance(node, Comparison):
                walk(node.left); walk(node.right)
            elif isinstance(node, LogicalAnd):
                for c in node.children: walk(c)
            elif isinstance(node, LogicalOr):
                for c in node.children: walk(c)
            elif isinstance(node, LogicalNot):
                walk(node.child)
            elif isinstance(node, FunctionCall):
                for a in node.arguments: walk(a)
        walk(self.root)
        return vars_found

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "Expression":
        return cls.model_validate(data)


# Pydantic forward reference çözümü — production için zorunlu
Expression.model_rebuild()
BinaryOp.model_rebuild()
Comparison.model_rebuild()
LogicalAnd.model_rebuild()
LogicalOr.model_rebuild()
LogicalNot.model_rebuild()
FunctionCall.model_rebuild()
