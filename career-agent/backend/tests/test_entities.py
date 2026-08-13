def test_add_skill(client, profile):
    resp = client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL",
        "proficiency": "advanced", "years_used": 2, "verified": True,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "PyTorch"
    assert body["verified"] is True

    listed = client.get(f"/skills?profile_id={profile['id']}").json()
    assert len(listed) == 1


def test_add_experience_with_bullets(client, profile):
    resp = client.post("/experience", json={
        "profile_id": profile["id"], "company": "YOUR_COMPANY", "role": "ML Engineer",
        "employment_type": "full_time", "start_date": "2023-01-01", "currently_working": True,
        "bullets": [
            {
                "bullet": "Developed deep learning models for medical image segmentation using PyTorch.",
                "skills": ["PyTorch", "Deep Learning", "Medical Imaging"],
            }
        ],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["company"] == "YOUR_COMPANY"
    assert len(body["bullets"]) == 1
    assert body["bullets"][0]["bullet"].startswith("Developed deep learning models")


def test_experience_rejects_end_date_when_currently_working(client, profile):
    resp = client.post("/experience", json={
        "profile_id": profile["id"], "company": "X", "role": "Y",
        "currently_working": True, "end_date": "2024-01-01",
    })
    assert resp.status_code == 422


def test_add_project_with_results(client, profile):
    resp = client.post("/projects", json={
        "profile_id": profile["id"], "name": "Hirschsprung Disease Segmentation and Classification",
        "technologies": ["PyTorch", "Mask2Former", "Swin Transformer", "ResNet"],
        "skills": ["Computer Vision", "Medical Imaging"],
        "results": [{"description": "Improved segmentation accuracy", "metric": "+6.2% Dice score"}],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Hirschsprung Disease Segmentation and Classification"
    assert len(body["results"]) == 1
    assert body["results"][0]["metric"] == "+6.2% Dice score"


def test_add_education(client, profile):
    resp = client.post("/education", json={
        "profile_id": profile["id"], "institution": "YOUR_UNIVERSITY", "degree": "BSc Computer Science",
        "field": "Computer Science", "start_date": "2019-09-01", "end_date": "2023-06-01",
    })
    assert resp.status_code == 201
    assert resp.json()["institution"] == "YOUR_UNIVERSITY"


def test_add_research(client, profile):
    resp = client.post("/research", json={
        "profile_id": profile["id"], "title": "YOUR_RESEARCH_TITLE",
        "research_area": "Computer Vision", "technologies": ["PyTorch", "Swin Transformer"],
        "datasets": ["YOUR_DATASET"], "results": ["Improved F1 by 4 points"],
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "YOUR_RESEARCH_TITLE"


def test_add_certification(client, profile):
    resp = client.post("/certifications", json={
        "profile_id": profile["id"], "name": "YOUR_CERTIFICATION", "issuer": "YOUR_ISSUER",
        "issue_date": "2024-01-01",
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "YOUR_CERTIFICATION"


def test_add_achievement(client, profile):
    resp = client.post("/achievements", json={
        "profile_id": profile["id"], "title": "YOUR_ACHIEVEMENT", "category": "award",
        "date": "2024-05-01", "metric": "1st place",
    })
    assert resp.status_code == 201
    assert resp.json()["category"] == "award"


def test_add_evidence_with_link(client, profile):
    skill_id = client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL",
    }).json()["id"]

    resp = client.post("/evidence", json={
        "profile_id": profile["id"], "source_type": "GitHub", "source_name": "github.com/example/repo",
        "links": [{"entity_type": "skill", "entity_id": skill_id}],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_type"] == "GitHub"
    assert body["links"][0]["entity_id"] == skill_id

    skill = client.get(f"/skills?profile_id={profile['id']}").json()[0]
    assert skill["evidence_ids"] == [body["id"]]
