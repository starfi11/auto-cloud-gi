import unittest

from src.kernel.resource_arbiter import ResourceArbiter


class ResourceArbiterTest(unittest.TestCase):
    def test_acquire_and_release(self) -> None:
        arbiter = ResourceArbiter()
        lease1 = arbiter.acquire("r1", ["mouse", "keyboard"], timeout_seconds=0.1)
        self.assertIsNotNone(lease1)

        lease2 = arbiter.acquire("r2", ["mouse"], timeout_seconds=0.05)
        self.assertIsNone(lease2)

        arbiter.release(lease1)
        lease3 = arbiter.acquire("r2", ["mouse"], timeout_seconds=0.1)
        self.assertIsNotNone(lease3)


if __name__ == "__main__":
    unittest.main()
