"""Shared marketplace contract for safe preparation-only publishing."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class PublisherBase(ABC):
    key: str
    label: str

    @abstractmethod
    def validate(self, book: dict) -> list[str]:
        """Return plain-English reasons this marketplace is not ready."""

    @abstractmethod
    def prepare(self, book: dict, target: Path) -> list[Path]:
        """Create a marketplace handoff package; never publish through a browser."""

    def publish(self, book: dict) -> None:
        raise NotImplementedError(f"{self.label} publishing is not connected yet. Use Prepare, then upload through the official platform.")

    def prepared_status(self, book: dict) -> str:
        """Return the honest state after this adapter has made its files.

        Most adapters make the actual upload files, so their established
        ``Ready`` state remains compatible with the catalog.  Printer
        adapters that still need a platform-sized cover override this instead
        of calling a reference file ready to upload.
        """
        return "Ready"

    @staticmethod
    def blocking_issues(issues: list[str]) -> list[str]:
        """Keep printer-template guidance visible without treating it as missing data."""
        advisory_hints = ("reference-only", "template")
        return [issue for issue in issues if not any(hint in issue.casefold() for hint in advisory_hints)]
