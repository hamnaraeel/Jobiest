from app.services.validation_service import SkillStatus, classify_skill_for_job


def test_rejects_invalid_email(client):
    resp = client.post("/profile", json={
        "full_name": "X", "professional_title": "Y", "email": "not-an-email",
    })
    assert resp.status_code == 422


def test_rejects_missing_required_field(client):
    resp = client.post("/profile", json={"full_name": "X"})
    assert resp.status_code == 422


def test_rejects_invalid_skill_category_enum(client, profile):
    resp = client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "NotARealCategory",
    })
    assert resp.status_code == 422


def test_rejects_education_with_end_before_start(client, profile):
    resp = client.post("/education", json={
        "profile_id": profile["id"], "institution": "X", "degree": "Y",
        "start_date": "2024-01-01", "end_date": "2020-01-01",
    })
    assert resp.status_code == 422


def test_skill_not_verified_by_default(client, profile):
    resp = client.post("/skills", json={
        "profile_id": profile["id"], "name": "Rust", "category": "Programming",
    })
    assert resp.status_code == 201
    assert resp.json()["verified"] is False


def test_experience_bullet_not_verified_by_default(client, profile):
    resp = client.post("/experience", json={
        "profile_id": profile["id"], "company": "X", "role": "Y",
        "bullets": [{"bullet": "Did a thing.", "skills": []}],
    })
    body = resp.json()
    assert body["verified"] is False
    assert body["bullets"][0]["verified"] is False


def test_classify_skill_for_job_missing(client, profile, db_session):
    status = classify_skill_for_job(db_session, profile["id"], "Kubernetes")
    assert status == SkillStatus.MISSING


def test_classify_skill_for_job_unverified(client, profile, db_session):
    client.post("/skills", json={
        "profile_id": profile["id"], "name": "Docker", "category": "Tool", "verified": False,
    })
    status = classify_skill_for_job(db_session, profile["id"], "Docker")
    assert status == SkillStatus.UNVERIFIED


def test_classify_skill_for_job_verified(client, profile, db_session):
    client.post("/skills", json={
        "profile_id": profile["id"], "name": "Kubernetes", "category": "Cloud", "verified": True,
    })
    status = classify_skill_for_job(db_session, profile["id"], "kubernetes")
    assert status == SkillStatus.VERIFIED
