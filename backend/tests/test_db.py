"""
The schema's two claims worth checking: the JSON columns survive a round trip
with their types intact, and the CHECK constraints that keep the data honest
actually fire rather than sitting in the DDL as decoration.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.tables import Application, ProfileSource


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def make_application(**overrides) -> Application:
    fields = {
        "company": "Air Canada",
        "role": "Front End Developer",
        "jd_text": "We are looking for...",
        "jd_parsed": {"required_skills": [{"name": "React", "importance": 3}]},
        "fit_score": 8,
        "fit_reasoning": "Strong React overlap.",
        "gaps": ["Kubernetes"],
        "selected_bullet_ids": ["dedicate-frontend-scratch"],
        "selected_bullets": [{"id": "dedicate-frontend-scratch", "text": "Built..."}],
        "pdf": b"%PDF-1.4 not really",
        "filename": "Shehzar_AirCanada.pdf",
        "title_variant": "frontend",
        "summary_text": "Front-end engineer...",
    }
    return Application(**{**fields, **overrides})


def test_json_columns_round_trip(session: Session):
    session.add(make_application())
    session.commit()

    saved = session.exec(select(Application)).one()
    assert saved.gaps == ["Kubernetes"]
    assert saved.jd_parsed["required_skills"][0]["importance"] == 3
    assert saved.selected_bullets[0]["id"] == "dedicate-frontend-scratch"
    assert saved.pdf == b"%PDF-1.4 not really"
    assert saved.status == "saved"
    assert saved.applied_at is None


def test_status_is_constrained(session: Session):
    session.add(make_application(status="ghosted"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_kept_posting_needs_no_cv(session: Session):
    """Nullable on purpose: a posting kept for its gaps never had one."""
    session.add(make_application(pdf=None, filename=None, title_variant=None, summary_text=None))
    session.commit()

    saved = session.exec(select(Application)).one()
    assert saved.pdf is None and saved.filename is None
    assert saved.selected_bullet_ids == ["dedicate-frontend-scratch"]


def test_profile_source_is_a_single_row(session: Session):
    session.add(ProfileSource(text="# Identity\nname: Test"))
    session.commit()

    # A second profile would make "the profile" ambiguous everywhere downstream.
    session.add(ProfileSource(id=2, text="# Identity\nname: Someone Else"))
    with pytest.raises(IntegrityError):
        session.commit()
