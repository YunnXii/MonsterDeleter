import os
from pathlib import Path

import pytest

import app.desktop_paths as desktop_paths
import app.target_resolver as target_resolver
from app.target_resolver import (
    PhysicalTarget,
    ResolveStatus,
    _Candidate,
    _candidate_names,
    _choose_candidate,
)


def _target(name: str, *, selected: bool = False) -> PhysicalTarget:
    return PhysicalTarget(
        left=100,
        top=100,
        right=160,
        bottom=170,
        accessible_name=name,
        selected=selected,
        root_class="CabinetWClass",
    )


def test_candidate_names_support_hidden_extensions() -> None:
    names = _candidate_names(Path(r"C:\Users\test\Desktop\report.final.docx"))
    assert names == ("report.final.docx", "report.final")


@pytest.mark.skipif(os.name != "nt", reason="Windows Known Folder API")
def test_windows_known_folder_api_returns_current_desktop() -> None:
    desktop = desktop_paths._known_folder_path(desktop_paths.FOLDERID_DESKTOP)
    assert desktop is not None
    assert str(desktop).strip()


def test_desktop_roots_prefer_windows_known_folder_redirect(monkeypatch) -> None:
    redirected = Path("D:/MovedDesktop")
    public = Path("C:/Users/Public/Desktop")
    legacy = Path("C:/Users/test/Desktop")

    def fake_known_folder(folder_id):
        if folder_id == desktop_paths.FOLDERID_DESKTOP:
            return redirected
        if folder_id == desktop_paths.FOLDERID_PUBLIC_DESKTOP:
            return public
        return None

    monkeypatch.setattr(desktop_paths, "_known_folder_path", fake_known_folder)
    monkeypatch.setattr(desktop_paths, "_registry_user_desktop", lambda: legacy)
    monkeypatch.setattr(desktop_paths, "_fallback_paths", lambda: (legacy,))

    roots = desktop_paths.desktop_roots()
    assert roots == (redirected, public, legacy)


def test_redirected_desktop_target_is_recognized(monkeypatch) -> None:
    redirected = Path("D:/MovedDesktop")
    monkeypatch.setattr(target_resolver, "desktop_roots", lambda: (redirected,))

    assert target_resolver._is_desktop_target(redirected / "report.docx") is True
    assert target_resolver._is_desktop_target(Path("C:/Temp/report.docx")) is False


def test_selected_candidate_wins_over_unselected_duplicate() -> None:
    selected = _Candidate(
        target=_target("report.docx", selected=True),
        score=1000,
        exact_name=True,
        foreground_root=False,
        desktop_root=False,
    )
    other = _Candidate(
        target=_target("report.docx", selected=False),
        score=9999,
        exact_name=True,
        foreground_root=True,
        desktop_root=False,
    )

    result = _choose_candidate([other, selected])
    assert result.status is ResolveStatus.FOUND
    assert result.target is selected.target


def test_ambiguous_duplicates_are_not_guessed() -> None:
    first = _Candidate(
        target=_target("same.docx"),
        score=100,
        exact_name=True,
        foreground_root=False,
        desktop_root=False,
    )
    second = _Candidate(
        target=_target("same.docx"),
        score=100,
        exact_name=True,
        foreground_root=False,
        desktop_root=False,
    )

    result = _choose_candidate([first, second])
    assert result.status is ResolveStatus.AMBIGUOUS
    assert result.target is None


def test_single_visible_candidate_is_accepted() -> None:
    candidate = _Candidate(
        target=_target("only.txt"),
        score=90,
        exact_name=True,
        foreground_root=False,
        desktop_root=False,
    )

    result = _choose_candidate([candidate])
    assert result.status is ResolveStatus.FOUND
    assert result.target is candidate.target
