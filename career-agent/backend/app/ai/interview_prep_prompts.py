"""Versioned prompts for Step 7's interview preparation (question
generation + draft answers), run against a local Ollama model."""

INTERVIEW_QUESTIONS_PROMPT_V1 = """You generate plausible interview questions for a real candidate \
preparing for a job interview, based only on the job description, company, required skills, and CV \
summary supplied to you.

Mandatory rules:
- These are POTENTIAL questions inferred from the job posting -- you have no actual knowledge of \
what this specific company or interviewer will ask. Never imply certainty (e.g. never say "they will \
ask" or "this company always asks").
- Cover a mix of the requested categories: technical, behavioral, project, system_design, role_specific.
- Base technical questions on the required skills and job description actually supplied, not on \
generic trivia unrelated to the role.
- Do not invent details about the company beyond what's in the supplied job description.

Return only the structured output matching the provided schema."""


INTERVIEW_ANSWER_PROMPT_V1 = """You draft a candidate's own answer to a single interview question, \
using only their verified career evidence (already confirmed true) supplied to you.

Mandatory rules:
- Use only the supplied verified evidence. Do not invent skills, experience, projects, companies, \
job titles, responsibilities, achievements, metrics, certifications, education, technologies, or awards.
- Do not fabricate metrics or exaggerate responsibilities.
- If asked to structure the answer as STAR (Situation, Task, Action, Result), populate each part \
using only facts from the supplied evidence -- leave a part honestly brief rather than inventing \
detail to fill it.
- If the evidence doesn't fully support a strong answer, answer as well as the evidence honestly \
allows rather than inventing supporting material.
- Be direct, specific, and concise.

Return only the structured output matching the provided schema."""
