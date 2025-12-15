"""
Data Models for Insurance Claims Analysis System
================================================

This module contains all data classes and structures used throughout the system.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ClaimData:
    """Structure for claim information"""

    claim_id: str
    policy_number: str
    claimant_name: str
    incident_date: str
    incident_type: str
    description: str
    estimated_damage: float
    documents: List[str]
    location: str

    def __post_init__(self):
        """Validate that evidence documents are provided"""
        if not self.documents:
            raise ValueError("Evidence documents are required for claim submission")


@dataclass
class ContentBlock:
    """Content block for multimodal input to agents"""

    text: Optional[str] = None
    image: Optional[Dict[str, Any]] = None

    @classmethod
    def from_text(cls, text: str) -> "ContentBlock":
        """Create a text content block"""
        return cls(text=text)

    @classmethod
    def from_image_file(cls, image_path: str) -> "ContentBlock":
        """Create an image content block from file path"""
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # Determine format from file extension
            format_map = {
                ".png": "png",
                ".jpg": "jpeg",
                ".jpeg": "jpeg",
                ".gif": "gif",
                ".webp": "webp",
            }

            _, ext = os.path.splitext(image_path.lower())
            image_format = format_map.get(ext, "png")

            return cls(image={"format": image_format, "source": {"bytes": image_bytes}})
        except Exception as e:
            print(f"WARNING: Could not load image {image_path}: {e}")
            return cls(text=f"[Image file not accessible: {image_path}]")

    @classmethod
    def from_image_bytes(cls, image_bytes: bytes, img_format: str = "png") -> "ContentBlock":
        """Create an image content block from bytes"""
        return cls(image={"format": img_format, "source": {"bytes": image_bytes}})


@dataclass
class ProcessingResult:
    """Structure for analysis results"""

    claim_id: str
    status: str
    extracted_data: Dict[str, Any] = None
    damage_assessment: Dict[str, Any] = None
    fraud_analysis: str = ""
    claim_summary: str = ""
    executive_summary: str = ""
    claimant_info: Dict[str, Any] = None
    recommended_next_steps: List[str] = None
    analysis_notes: List[str] = None

    def __post_init__(self):
        """Initialize empty lists if None"""
        if self.analysis_notes is None:
            self.analysis_notes = []
        if self.extracted_data is None:
            self.extracted_data = {}
        if self.damage_assessment is None:
            self.damage_assessment = {}
        if self.claimant_info is None:
            self.claimant_info = {}
        if self.recommended_next_steps is None:
            self.recommended_next_steps = []
