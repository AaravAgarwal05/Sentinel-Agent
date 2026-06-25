"""Detector implementations for common Kubernetes failure modes."""
from agent.detection.detectors.base import Detector, DetectorRegistry
from agent.detection.detectors.crashloop import CrashLoopBackOffDetector
from agent.detection.detectors.imagepull import ImagePullBackOffDetector
from agent.detection.detectors.oomkilled import OOMKilledDetector

__all__ = [
    "Detector",
    "DetectorRegistry",
    "CrashLoopBackOffDetector",
    "OOMKilledDetector",
    "ImagePullBackOffDetector",
]
