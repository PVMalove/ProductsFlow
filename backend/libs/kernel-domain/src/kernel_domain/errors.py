from dataclasses import dataclass
from enum import Enum


class ErrorType(Enum):
    VALIDATION = "VALIDATION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    UNAUTHORIZED = "UNAUTHORIZED"
    PROBLEM = "PROBLEM"
    FAILURE = "FAILURE"


@dataclass(frozen=True)
class Error:
    code: str
    description: str
    type: ErrorType
