import pytest

from app.ai.structured_outputs import ApplicationAnswerOutput
from app.models.application_question import ApplicationQuestion
from app.models.enums import ApplicationQuestionType
from app.services import application_answer_service as svc


REQUIREMENTS = [
    dict(requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch"),
]


def _make_question(db_session, job_id, question, **kwargs):
    q = ApplicationQuestion(job_id=job_id, question=question, **kwargs)
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    return q


# --- 9: application question creation ---------------------------------------


def test_create_application_question_via_api(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    resp = client.post(f"/jobs/{job.id}/application-questions", json={
        "question": "Why do you want to work for this company?", "character_limit": 500,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["question_type"] == "company"
    assert body["character_limit"] == 500


@pytest.mark.parametrize("question,expected_type", [
    ("Why do you want to work for this company?", "company"),
    ("Why are you interested in this position?", "motivation"),
    ("Tell us about yourself.", "general"),
    ("Why should we hire you?", "motivation"),
    ("What are your strengths?", "behavioral"),
    ("Describe a challenging project you worked on.", "behavioral"),
    ("Describe your experience with Python.", "technical"),
    ("What is your salary expectation?", "salary"),
    ("Are you authorized to work in this country?", "authorization"),
    ("Are you willing to relocate?", "relocation"),
    ("What is your availability to start?", "availability"),
])
def test_classify_question_type(question, expected_type):
    assert svc.classify_question_type(question).value == expected_type


# --- 10, 11: answer generation & validation ---------------------------------


def test_generate_answer_creates_validated_answer(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Describe your experience with PyTorch.")

    output = ApplicationAnswerOutput(answer="I developed deep learning models for medical image segmentation using PyTorch at Acme AI.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(output))

    answer = svc.generate_answer(db_session, question, job)
    assert answer.status.value == "validated"
    assert answer.word_count > 0
    assert answer.evidence


def test_answer_with_unsupported_skill_is_rejected(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=[
        dict(requirement_text="AWS", category="technical_skill", importance="medium", required=False, skill_name="AWS"),
    ])
    question = _make_question(db_session, job.id, "Describe your experience with AWS.")

    bad = ApplicationAnswerOutput(answer="I have deployed production systems on AWS extensively.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(bad, bad))

    answer = svc.generate_answer(db_session, question, job)
    assert answer.status.value == "rejected"
    assert any("AWS" in w for w in answer.warnings)


# --- 12: character limit enforcement ----------------------------------------


def test_character_limit_enforced_with_shortening(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Why are you interested in this role?", character_limit=50)

    long_answer = ApplicationAnswerOutput(answer="I am very interested in this role because of my extensive PyTorch experience and background. " * 3)
    shortened = ApplicationAnswerOutput(answer="Interested due to my PyTorch background.")
    client_mock = fake_ollama_client(long_answer, shortened)
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=client_mock)

    answer = svc.generate_answer(db_session, question, job)
    assert len(answer.answer) <= 50
    assert answer.status.value == "validated"


def test_character_limit_still_exceeded_after_shortening_needs_manual_edit(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Why are you interested in this role?", character_limit=10)

    long_answer = ApplicationAnswerOutput(answer="This is a long answer that will never fit in ten characters no matter what.")
    # shortening attempts also fail to get under 10 chars
    still_long_1 = ApplicationAnswerOutput(answer="Still too long to fit the limit.")
    still_long_2 = ApplicationAnswerOutput(answer="Still too long.")
    client_mock = fake_ollama_client(long_answer, still_long_1, still_long_2)
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=client_mock)

    answer = svc.generate_answer(db_session, question, job)
    assert len(answer.answer) > 10
    assert any("Unable to fit" in w for w in answer.warnings)
    assert answer.status.value == "draft"


# --- 13: word limit enforcement ---------------------------------------------


def test_word_limit_enforced(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Tell us about yourself.", word_limit=5)

    long_answer = ApplicationAnswerOutput(answer="I am a machine learning engineer with PyTorch experience and more words here.")
    shortened = ApplicationAnswerOutput(answer="ML engineer, PyTorch experience.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(long_answer, shortened))

    answer = svc.generate_answer(db_session, question, job)
    assert len(answer.answer.split()) <= 5


# --- 14, 15, 16, 17: salary / authorization / relocation / availability -----


def test_salary_question_without_profile_data_needs_manual_input(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "What is your expected salary?")

    with pytest.raises(svc.ManualInputRequiredError) as exc_info:
        svc.generate_answer(db_session, question, job)
    assert exc_info.value.question_type == ApplicationQuestionType.SALARY


def test_authorization_question_without_profile_data_needs_manual_input(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Are you authorized to work in this country?")
    with pytest.raises(svc.ManualInputRequiredError) as exc_info:
        svc.generate_answer(db_session, question, job)
    assert exc_info.value.question_type == ApplicationQuestionType.AUTHORIZATION


def test_relocation_question_without_profile_data_needs_manual_input(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Are you willing to relocate?")
    with pytest.raises(svc.ManualInputRequiredError) as exc_info:
        svc.generate_answer(db_session, question, job)
    assert exc_info.value.question_type == ApplicationQuestionType.RELOCATION


def test_availability_question_without_profile_data_needs_manual_input(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "When are you available to start?")
    with pytest.raises(svc.ManualInputRequiredError) as exc_info:
        svc.generate_answer(db_session, question, job)
    assert exc_info.value.question_type == ApplicationQuestionType.AVAILABILITY


def test_salary_question_endpoint_returns_manual_input_required(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    q_resp = client.post(f"/jobs/{job.id}/application-questions", json={"question": "What is your expected salary?"})
    question_id = q_resp.json()["id"]

    resp = client.post(f"/jobs/{job.id}/application-questions/{question_id}/answer")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "manual_input_required"
    assert body["question_type"] == "salary"


def test_salary_question_generates_once_profile_configured(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    client.put("/profile", json={"salary_expectation": "$120,000 - $140,000 USD"})
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "What is your expected salary?")

    output = ApplicationAnswerOutput(answer="My salary expectation is $120,000 - $140,000 USD.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(output))

    answer = svc.generate_answer(db_session, question, job)
    assert answer.status.value == "validated"


# --- approval workflow -------------------------------------------------


def test_answer_approval_workflow_via_api(client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    question = _make_question(db_session, job.id, "Describe your experience with PyTorch.")

    output = ApplicationAnswerOutput(answer="I developed deep learning models for medical image segmentation using PyTorch.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(output))

    resp = client.post(f"/jobs/{job.id}/application-questions/{question.id}/answer")
    answer_id = resp.json()["id"]

    approve = client.patch(f"/application-answers/{answer_id}/status", json={"status": "approved"})
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"


# --- 21: application material package ---------------------------------------


def test_application_materials_package_reflects_readiness(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    from app.ai.structured_outputs import CoverLetterOutput

    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    # not ready yet: no cover letter, no answers
    package = client.get(f"/jobs/{job.id}/application-materials").json()
    assert package["cv"]["status"] == "approved"
    assert package["cover_letter"] is None
    assert package["ready_for_application"] is False

    cl_output = CoverLetterOutput(
        opening="x", role_alignment="x", experience_alignment="x", company_alignment="x", closing="x",
        full_text="I developed deep learning models for medical image segmentation using PyTorch at Acme AI. " * 5,
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(cl_output))
    cl_resp = client.post(f"/jobs/{job.id}/cover-letter/generate")
    cl_id = cl_resp.json()["id"]
    client.patch(f"/cover-letters/{cl_id}/status", json={"status": "approved"})

    q_resp = client.post(f"/jobs/{job.id}/application-questions", json={
        "question": "Describe your experience with PyTorch.", "required": True,
    })
    question_id = q_resp.json()["id"]

    ans_output = ApplicationAnswerOutput(answer="I developed deep learning models using PyTorch at Acme AI.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(ans_output))
    ans_resp = client.post(f"/jobs/{job.id}/application-questions/{question_id}/answer")
    answer_id = ans_resp.json()["id"]
    client.patch(f"/application-answers/{answer_id}/status", json={"status": "approved"})

    final_package = client.get(f"/jobs/{job.id}/application-materials").json()
    assert final_package["cover_letter"]["status"] == "approved"
    assert final_package["answers"][0]["status"] == "approved"
    assert final_package["ready_for_application"] is True


# --- 41: end-to-end workflow -------------------------------------------------


def test_end_to_end_application_materials_workflow(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    """Career Profile -> Job -> Approved CV -> Cover Letter -> Application
    Questions -> Answers -> Validation -> Human Approval -> Materials
    Package, mirroring spec section 41's end-to-end scenario."""

    from app.ai.structured_outputs import CoverLetterOutput

    job = make_analyzed_job(title="Machine Learning Engineer", company="Example Company", requirements=REQUIREMENTS)
    make_approved_cv(job.id, rich_profile["profile"]["id"])

    cl_output = CoverLetterOutput(
        opening="x", role_alignment="x", experience_alignment="x", company_alignment="x", closing="x",
        full_text="I developed deep learning models for medical image segmentation using PyTorch at Acme AI. " * 6,
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(cl_output))
    cl_id = client.post(f"/jobs/{job.id}/cover-letter/generate").json()["id"]
    client.patch(f"/cover-letters/{cl_id}/status", json={"status": "validated"})
    client.patch(f"/cover-letters/{cl_id}/status", json={"status": "approved"})

    questions = [
        ("Why are you interested in this role?", 500),
        ("Describe your experience with PyTorch.", 500),
    ]
    answer_outputs = [
        ApplicationAnswerOutput(answer="This role's computer vision focus matches my PyTorch-based project work."),
        ApplicationAnswerOutput(answer="I developed deep learning models for medical image segmentation using PyTorch at Acme AI."),
    ]
    mocker.patch("app.services.application_answer_service.get_ollama_client", side_effect=[fake_ollama_client(o) for o in answer_outputs])

    for (question_text, char_limit), _ in zip(questions, answer_outputs):
        q_id = client.post(f"/jobs/{job.id}/application-questions", json={"question": question_text, "character_limit": char_limit}).json()["id"]
        ans_resp = client.post(f"/jobs/{job.id}/application-questions/{q_id}/answer")
        assert ans_resp.status_code == 200
        answer_id = ans_resp.json()["id"]
        client.patch(f"/application-answers/{answer_id}/status", json={"status": "approved"})

    package = client.get(f"/jobs/{job.id}/application-materials").json()
    assert package["job"]["title"] == "Machine Learning Engineer"
    assert package["job"]["company"] == "Example Company"
    assert package["cv"]["status"] == "approved"
    assert package["cover_letter"]["status"] == "approved"
    assert len(package["answers"]) == 2
    assert all(a["status"] == "approved" for a in package["answers"])
    assert package["ready_for_application"] is True
