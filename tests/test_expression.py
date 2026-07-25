"""UCEL v2.1 testleri."""
import json
import pytest
from contracts.expression import (
    Expression, Constant, Variable, Comparison, LogicalAnd,
    LogicalOr, LogicalNot, BinaryOp, FunctionCall, OpType,
    MissingVariableError, Value, EvaluationStep, EvaluationResult,
)

def test_simple_comparison():
    expr = Expression(
        name="RSI_oversold",
        root=Comparison(op=OpType.LT, left=Variable(name="RSI"), right=Constant(value=30)),
    )
    result = expr.evaluate({"RSI": 25})
    assert result.value.is_true() is True
    result2 = expr.evaluate({"RSI": 50})
    assert result2.value.is_true() is False

def test_logical_and():
    expr = Expression(
        root=LogicalAnd(children=[
            Comparison(op=OpType.LT, left=Variable(name="RSI"), right=Constant(value=30)),
            Comparison(op=OpType.GT, left=Variable(name="ATR"), right=Constant(value=2)),
        ])
    )
    assert expr.evaluate({"RSI": 25, "ATR": 3}).value.is_true() is True
    assert expr.evaluate({"RSI": 25, "ATR": 1}).value.is_true() is False

def test_logical_not():
    expr = Expression(
        root=LogicalNot(child=Comparison(op=OpType.GT, left=Variable(name="RSI"), right=Constant(value=70)))
    )
    assert expr.evaluate({"RSI": 80}).value.is_true() is False
    assert expr.evaluate({"RSI": 60}).value.is_true() is True

def test_binary_operation():
    expr = Expression(
        root=Comparison(
            op=OpType.GT,
            left=BinaryOp(op=OpType.DIV, left=Variable(name="ATR"), right=Variable(name="PRICE")),
            right=Constant(value=0.02),
        )
    )
    result = expr.evaluate({"ATR": 1000, "PRICE": 50000})
    assert result.value.is_true() is False

def test_missing_variable():
    expr = Expression(
        root=Comparison(op=OpType.LT, left=Variable(name="BTC_VOLATILITY"), right=Constant(value=0.3))
    )
    result = expr.evaluate({"BTC_PRICE": 50000})
    assert result.confidence == 0.0
    assert "Eksik" in result.explanation

def test_function_call():
    expr = Expression(
        root=Comparison(
            op=OpType.LT,
            left=FunctionCall(name="RSI", arguments=[Constant(value=14)]),
            right=Constant(value=30),
        )
    )
    assert "RSI(14.0)" in expr.explain()

def test_to_dict_roundtrip():
    expr = Expression(
        name="test",
        root=Comparison(op=OpType.LT, left=Variable(name="RSI"), right=Constant(value=30)),
    )
    d = expr.to_dict()
    assert d["root"]["node_type"] == "comparison"
    json_str = json.dumps(d)
    data = json.loads(json_str)
    restored = Expression.from_dict(data)
    assert restored.root.explain() == "RSI < 30.0"

def test_evaluation_trace():
    expr = Expression(
        root=LogicalAnd(children=[
            Comparison(op=OpType.LT, left=Variable(name="RSI"), right=Constant(value=30)),
            Comparison(op=OpType.GT, left=Variable(name="ATR"), right=Constant(value=2)),
        ])
    )
    result = expr.evaluate({"RSI": 25, "ATR": 3})
    assert len(result.trace) >= 2
    assert any("RSI" in step.expression for step in result.trace)

def test_numeric_is_true_raises():
    with pytest.raises(TypeError):
        Value.from_numeric(-0.5).is_true()
