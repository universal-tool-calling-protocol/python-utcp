from typing import List


class UtcpProtocolCloseError(Exception):
    """REQUIRED
    Raised when one or more of a client's own protocol instances failed to close.

    Every instance is still asked to close before this is raised, so nothing is
    left half-torn-down behind it; `failures` carries what each failing close raised.
    """

    def __init__(self, failures: List[BaseException], total: int):
        self.failures = failures
        self.total = total
        super().__init__(f"{len(failures)} of {total} owned communication protocol(s) failed to close: "
                         + "; ".join(f"{type(f).__name__}: {f}" for f in failures))
