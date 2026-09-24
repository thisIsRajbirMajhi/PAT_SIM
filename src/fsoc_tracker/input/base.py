from abc import ABC, abstractmethod
from ..common.types import Frame, GroundTruth

class FrameSource(ABC):
    @abstractmethod
    def read(self) -> tuple[Frame | None, GroundTruth | None]:
        pass
    @abstractmethod
    def reset(self):
        pass
    @abstractmethod
    def is_opened(self) -> bool:
        pass
    @abstractmethod
    def release(self):
        pass
    @property
    @abstractmethod
    def fps(self) -> float:
        pass
    @property
    @abstractmethod
    def resolution(self) -> tuple[int,int]:
        pass
