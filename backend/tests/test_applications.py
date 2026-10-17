import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import auth, main
from app.db import get_session
from app.settings import Settings
from app.tables import Application

PASSWORD = "correct horse battery staple"

KEPT = {
    "company": "Air Canada",
    "role": "Front End Developer",
    "jd_text": "We are looking for...",
    "jd_parsed": {"required_skills": [{"name": "Kubernetes", "importance": 3}]},
    "fit_score": 5,
    "fit_reasoning": "Strong React overlap, no orchestration.",
    "gaps": ["Kubernetes", "Terraform"],
    "status": "skipped",
}


@pytest.fixture
def client(monkeypatch):
    settings = Settings(secret_key="t", password_hash=auth.hash_password(PASSWORD))
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    auth.reset_gate()

    from app.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"password": PASSWORD})
        client.engine = engine  # for the tests that need to plant a PDF
        yield client
    app.dependency_overrides.clear()
    auth.reset_gate()


def attach_pdf(client, application_id, data=b"%PDF-1.4 pretend"):
    with Session(client.engine) as session:
        row = session.get(Application, application_id)
        row.pdf, row.filename = data, "Maya_AirCanada.pdf"
        session.add(row)
        session.commit()


# ---------- saving without a CV ----------


def test_a_posting_can_be_kept_with_no_cv_at_all(client):
    created = client.post("/api/applications", json=KEPT)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "skipped"
    assert body["has_pdf"] is False
    assert body["filename"] is None
    assert body["title_variant"] is None and body["summary_text"] is None
    assert body["gaps"] == ["Kubernetes", "Terraform"]
    assert body["applied_at"] is None


def test_the_pdf_bytes_never_appear_in_json(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    attach_pdf(client, application_id)

    for body in [
        client.get(f"/api/applications/{application_id}").json(),
        client.get("/api/applications").json()[0],
    ]:
        assert "pdf" not in body
        assert body["has_pdf"] is True


def test_asking_for_a_pdf_that_was_never_made(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    assert client.get(f"/api/applications/{application_id}/pdf").status_code == 404


def test_the_pdf_comes_back_as_a_pdf(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    attach_pdf(client, application_id)

    response = client.get(f"/api/applications/{application_id}/pdf")
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 pretend"
    # Inline, so the in-app viewer renders it.
    assert response.headers["content-disposition"].startswith("inline;")
    assert "Maya_AirCanada.pdf" in response.headers["content-disposition"]


def test_a_hostile_filename_cannot_write_headers(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    with Session(client.engine) as session:
        row = session.get(Application, application_id)
        row.pdf, row.filename = b"x", 'a"\r\nX-Injected: yes'
        session.add(row)
        session.commit()

    response = client.get(f"/api/applications/{application_id}/pdf")
    assert "x-injected" not in response.headers
    assert "\n" not in response.headers["content-disposition"]


# ---------- the pipeline ----------


def test_applied_at_is_stamped_when_it_goes_out(client):
    application_id = client.post("/api/applications", json={**KEPT, "status": "saved"}).json()["id"]
    assert client.get(f"/api/applications/{application_id}").json()["applied_at"] is None

    sent = client.patch(f"/api/applications/{application_id}", json={"status": "applied"}).json()
    assert sent["applied_at"] is not None
    assert sent["applied_at"].endswith("+00:00")


def test_applied_at_is_not_rewritten_by_later_stages(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    first = client.patch(f"/api/applications/{application_id}", json={"status": "applied"}).json()
    later = client.patch(f"/api/applications/{application_id}", json={"status": "interview"}).json()
    assert later["applied_at"] == first["applied_at"]


def test_skipping_is_not_applying(client):
    application_id = client.post("/api/applications", json={**KEPT, "status": "saved"}).json()["id"]
    body = client.patch(f"/api/applications/{application_id}", json={"status": "skipped"}).json()
    assert body["applied_at"] is None


def test_created_straight_into_the_pipeline_is_stamped(client):
    body = client.post("/api/applications", json={**KEPT, "status": "applied"}).json()
    assert body["applied_at"] is not None


def test_an_unknown_status_is_refused(client):
    assert client.post("/api/applications", json={**KEPT, "status": "ghosted"}).status_code == 422
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    assert client.patch(f"/api/applications/{application_id}", json={"status": "x"}).status_code == 422


# ---------- what patch may not touch ----------


def test_patch_ignores_everything_but_status_and_notes(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    body = client.patch(
        f"/api/applications/{application_id}",
        json={"company": "Someone Else", "fit_score": 10, "gaps": [], "notes": "called them"},
    ).json()
    assert body["company"] == "Air Canada"
    assert body["fit_score"] == 5
    assert body["gaps"] == ["Kubernetes", "Terraform"]
    assert body["notes"] == "called them"


def test_notes_can_be_cleared_but_are_not_cleared_by_a_status_change(client):
    application_id = client.post("/api/applications", json={**KEPT, "notes": "keep me"}).json()["id"]
    assert client.patch(
        f"/api/applications/{application_id}", json={"status": "applied"}
    ).json()["notes"] == "keep me"
    assert client.patch(
        f"/api/applications/{application_id}", json={"notes": None}
    ).json()["notes"] is None


# ---------- listing ----------


def test_the_list_is_newest_first(client):
    for company in ["First", "Second", "Third"]:
        client.post("/api/applications", json={**KEPT, "company": company})
    assert [row["company"] for row in client.get("/api/applications").json()] == [
        "Third", "Second", "First"
    ]


def test_timestamps_are_marked_utc(client):
    created = client.post("/api/applications", json=KEPT).json()
    assert created["created_at"].endswith("+00:00")


def test_missing_is_missing(client):
    assert client.get("/api/applications/999").status_code == 404
    assert client.patch("/api/applications/999", json={"status": "applied"}).status_code == 404
    assert client.get("/api/applications/999/pdf").status_code == 404


def test_all_of_it_needs_a_session(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    client.post("/api/auth/logout")
    assert client.get("/api/applications").status_code == 401
    assert client.post("/api/applications", json=KEPT).status_code == 401
    assert client.get(f"/api/applications/{application_id}").status_code == 401
    assert client.patch(f"/api/applications/{application_id}", json={"status": "applied"}).status_code == 401
    assert client.get(f"/api/applications/{application_id}/pdf").status_code == 401
    assert client.delete(f"/api/applications/{application_id}").status_code == 401


def test_deleting_an_application_takes_its_pdf_with_it(client):
    application_id = client.post("/api/applications", json=KEPT).json()["id"]
    attach_pdf(client, application_id)

    assert client.delete(f"/api/applications/{application_id}").status_code == 204
    assert client.get(f"/api/applications/{application_id}").status_code == 404
    assert client.get(f"/api/applications/{application_id}/pdf").status_code == 404
    assert client.get("/api/applications").json() == []


def test_deleting_something_that_is_not_there(client):
    assert client.delete("/api/applications/999").status_code == 404


def test_health_needs_no_session():
    from app.main import app

    with TestClient(app) as anyone:
        response = anyone.get("/api/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_where_you_found_it_is_kept(client):
    body = client.post(
        "/api/applications",
        json={
            "company": "Acme", "role": "Dev", "jd_text": "x" * 100,
            "fit_score": 7, "source": "LinkedIn",
            "url": "https://example.com/jobs/1",
        },
    ).json()
    assert (body["source"], body["url"]) == ("LinkedIn", "https://example.com/jobs/1")
    assert client.get(f"/api/applications/{body['id']}").json()["url"] == body["url"]


# ---------- serving the built front end ----------


@pytest.mark.skipif(not main.BUNDLE.is_dir(), reason="no frontend build to serve")
class TestBundle:
    def test_a_deep_link_reaches_the_router_not_a_404(self, client):
        response = client.get("/applications")
        assert response.status_code == 200 and "<html" in response.text

    def test_the_api_is_not_shadowed_by_the_catch_all(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}
        client.post("/api/auth/logout")
        assert client.get("/api/profile").status_code == 401

    def test_a_path_climbing_out_of_the_bundle_gets_index_html(self, client):
        for attempt in ("../../backend/.env", "../../../etc/passwd", "..%2f..%2f.env"):
            response = client.get(f"/{attempt}")
            assert "HIRED_" not in response.text and "root:" not in response.text


def test_a_row_remembers_both_models(client):
    """
    The score and the CV can come from different models, and a number is worth
    nothing months later without knowing which one produced it.
    """
    made = client.post(
        "/api/applications",
        json={
            "company": "Acme",
            "role": "Dev",
            "jd_text": "x" * 100,
            "fit_score": 8,
            "fit_model": "granite3.3:8b",
        },
    ).json()

    row = client.get(f"/api/applications/{made['id']}").json()
    assert row["fit_model"] == "granite3.3:8b"
    assert row["model"] == ""  # stamped separately, at export
