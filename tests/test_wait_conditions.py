import unittest

from src.kernel.event_contract import Event
from src.kernel.wait_conditions import ConditionOp, EventPredicate, WaitCondition


class WaitConditionTest(unittest.TestCase):
    def test_any_condition_matches(self) -> None:
        events = [Event(type="A", source="test"), Event(type="B", source="test")]
        cond = WaitCondition(op=ConditionOp.ANY, predicates=[EventPredicate("X"), EventPredicate("B")])
        self.assertTrue(cond.matched(events))

    def test_all_condition_matches(self) -> None:
        events = [Event(type="A", source="test"), Event(type="B", source="test")]
        cond = WaitCondition(op=ConditionOp.ALL, predicates=[EventPredicate("A"), EventPredicate("B")])
        self.assertTrue(cond.matched(events))

    def test_sequence_condition_matches(self) -> None:
        events = [Event(type="A", source="test"), Event(type="C", source="test"), Event(type="B", source="test")]
        cond = WaitCondition(op=ConditionOp.SEQUENCE, predicates=[EventPredicate("A"), EventPredicate("B")])
        self.assertTrue(cond.matched(events))


if __name__ == "__main__":
    unittest.main()
