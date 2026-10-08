"""
The schema's two claims worth checking: JSON columns survive a round trip with
their types, and the CHECK constraints fire rather than sitting in the DDL.
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
    session.add(make_application(pdf=None, filename=None, title_variant=None, summary_text=None))
    session.commit()

    saved = session.exec(select(Application)).one()
    assert saved.pdf is None and saved.filename is None
    assert saved.selected_bullet_ids == ["dedicate-frontend-scratch"]


def test_profile_source_keeps_every_version(session: Session):
    """Append-only: the old row stays as the version you can go back to."""
    session.add(ProfileSource(text="# Identity\nname: Test"))
    session.add(ProfileSource(text="# Identity\nname: Someone Else"))
    session.commit()

    rows = session.exec(select(ProfileSource).order_by(ProfileSource.id)).all()
    assert [r.text.splitlines()[1] for r in rows] == ["name: Test", "name: Someone Else"]


def test_a_version_id_is_never_reused(session: Session):
    """
    SQLite hands a deleted rowid to the next insert. A version id crosses to the
    browser and comes back on restore, so one that changes meaning restores the
    wrong file. AUTOINCREMENT is what stops it.
    """
    for n in range(3):
        session.add(ProfileSource(text=f"# Identity\nname: v{n}"))
    session.commit()
    top = session.exec(select(ProfileSource).order_by(ProfileSource.id.desc())).first()
    freed = top.id
    session.delete(top)
    session.commit()

    session.add(ProfileSource(text="# Identity\nname: after the delete"))
    session.commit()
    fresh = session.exec(select(ProfileSource).order_by(ProfileSource.id.desc())).first()
    assert fresh.id > freed
