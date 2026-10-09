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
        "selected_bullet_ids": ["ledgerline-frontend-scratch"],
        "selected_bullets": [{"id": "ledgerline-frontend-scratch", "text": "Built..."}],
        "pdf": b"%PDF-1.4 not really",
        "filename": "Maya_AirCanada.pdf",
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
    assert saved.selected_bullets[0]["id"] == "ledgerline-frontend-scratch"
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
    assert saved.selected_bullet_ids == ["ledgerline-frontend-scratch"]


def test_profile_source_keeps_every_version(session: Session):
    session.add(ProfileSource(text="# Identity\nname: Test"))
    session.add(ProfileSource(text="# Identity\nname: Someone Else"))
    session.commit()

    rows = session.exec(select(ProfileSource).order_by(ProfileSource.id)).all()
    assert [r.text.splitlines()[1] for r in rows] == ["name: Test", "name: Someone Else"]


def test_a_version_id_is_never_reused(session: Session):
    """SQLite reuses a deleted rowid unless the table uses AUTOINCREMENT."""
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


# ---------- demo mode ----------


def test_demo_mode_refuses_a_real_database(monkeypatch):
    """
    Seeding invented applications over real ones cannot be undone, so the check
    lives in settings rather than only in the launcher, which can be bypassed.
    """
    from app.settings import Settings, get_settings

    monkeypatch.setenv("HIRED_DEMO", "1")
    monkeypatch.setenv("HIRED_DATABASE_URL", "sqlite:///./hired.db")
    monkeypatch.setenv("HIRED_SECRET_KEY", "t")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit) as exit:
            get_settings()
        assert "cannot touch real data" in str(exit.value)
    finally:
        get_settings.cache_clear()


def test_demo_mode_allows_memory(monkeypatch):
    from app.settings import get_settings

    monkeypatch.setenv("HIRED_DEMO", "1")
    monkeypatch.setenv("HIRED_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("HIRED_SECRET_KEY", "t")
    get_settings.cache_clear()
    try:
        assert get_settings().demo is True
    finally:
        get_settings.cache_clear()


def test_demo_answers_without_a_model(monkeypatch):
    """A demo must not spend a rationed call, and must work with no network."""
    from app import model
    from app.settings import Settings

    monkeypatch.setattr(model, "get_settings", lambda: Settings(secret_key="t", demo=True))

    def explode(*args, **kwargs):
        raise AssertionError("demo mode reached the network")

    monkeypatch.setattr(model._CLIENT, "post", explode)

    fit = model.generate_json("anything", {"properties": {"parsed_jd": {}}})
    assert fit["parsed_jd"]["company"] == "Fernhill"
    cv = model.generate_json("anything", {"properties": {"title_id": {}}})
    assert cv["title_id"] == "frontend"
