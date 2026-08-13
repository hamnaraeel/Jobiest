def test_create_profile(client, profile_payload):
    resp = client.post("/profile", json=profile_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "YOUR_NAME"
    assert body["email"] == "test-profile@example.com"
    assert body["target_roles"] == ["Machine Learning Engineer", "AI Engineer"]
    assert "id" in body


def test_get_profile_returns_created_profile(client, profile):
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert resp.json()["id"] == profile["id"]


def test_update_profile(client, profile):
    resp = client.put("/profile", json={"current_summary": "Updated summary."})
    assert resp.status_code == 200
    assert resp.json()["current_summary"] == "Updated summary."
    # untouched fields survive a partial update
    assert resp.json()["full_name"] == "YOUR_NAME"


def test_export_profile_includes_all_sections(client, profile):
    client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL",
        "proficiency": "advanced", "years_used": 2, "verified": True,
    })

    resp = client.get("/profile/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["id"] == profile["id"]
    assert len(body["skills"]) == 1
    assert body["skills"][0]["name"] == "PyTorch"
    for section in ("educations", "experiences", "projects", "certifications", "achievements", "research_items", "evidence"):
        assert section in body


def test_import_profile_creates_new_profile_with_children_and_remapped_evidence(client, profile):
    skill_resp = client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL", "verified": True,
    })
    skill_id = skill_resp.json()["id"]
    client.post("/evidence", json={
        "profile_id": profile["id"], "source_type": "GitHub", "source_name": "github.com/example/repo",
        "links": [{"entity_type": "skill", "entity_id": skill_id}],
    })

    export = client.get("/profile/export").json()
    export["profile"]["email"] = "imported@example.com"

    resp = client.post("/profile/import", json=export)
    assert resp.status_code == 201
    new_profile_id = resp.json()["id"]
    assert new_profile_id != profile["id"]

    imported_skills = client.get(f"/skills?profile_id={new_profile_id}").json()
    assert len(imported_skills) == 1
    # evidence_ids must point at the *new* skill row, not the original one
    assert imported_skills[0]["evidence_ids"] == [
        client.get(f"/evidence?profile_id={new_profile_id}").json()[0]["id"]
    ]


def test_import_profile_rejects_duplicate_email(client, profile):
    export = client.get("/profile/export").json()
    resp = client.post("/profile/import", json=export)
    assert resp.status_code == 409
