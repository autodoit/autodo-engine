"""状态机测试。"""

from __future__ import annotations

import unittest

from autodoengine.core.enums import TaskStatus
from autodoengine.core.errors import TaskTransitionError
from autodoengine.taskdb.state_machine import (
    can_complete_task,
    can_resume_task,
    can_split_task,
    validate_transition,
)


class TestStateMachine(unittest.TestCase):
    """任务状态机测试用例。"""

    def test_validate_transition_success(self) -> None:
        """测试合法状态迁移。"""

        validate_transition(TaskStatus.READY, TaskStatus.RUNNING)
        validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)

    def test_validate_transition_fail(self) -> None:
        """测试非法状态迁移。"""

        with self.assertRaises(TaskTransitionError):
            validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    def test_can_resume_task(self) -> None:
        """测试父任务恢复条件。"""

        self.assertTrue(
            can_resume_task(
                TaskStatus.SUSPENDED,
                [TaskStatus.COMPLETED, TaskStatus.CANCELLED],
            )
        )
        self.assertFalse(can_resume_task(TaskStatus.RUNNING, [TaskStatus.COMPLETED]))

    def test_can_split_and_complete(self) -> None:
        """测试分裂与完成判定。"""

        self.assertTrue(can_split_task(TaskStatus.RUNNING))
        self.assertFalse(can_split_task(TaskStatus.BLOCKED))
        self.assertTrue(can_complete_task(TaskStatus.RUNNING))
        self.assertFalse(can_complete_task(TaskStatus.SUSPENDED))


if __name__ == "__main__":
    unittest.main()

