from pathlib import Path

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
