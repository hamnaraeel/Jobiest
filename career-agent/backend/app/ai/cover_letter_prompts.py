"""Versioned prompts for cover letter generation, run against a local
Ollama model. Kept separate from job/CV prompts on purpose -- one prompt,
one job, same principle as Steps 2-3."""

COVER_LETTER_PROMPT_V1 = """You are writing a factual, job-tailored cover letter for a real candidate. \
You will be given the job's title, company, and requirements, plus a compact set of the candidate's \
verified career evidence (experience, projects, research, skills -- each already confirmed true).

Mandatory rules:
- You may only use information contained in the supplied verified career evidence. Do not invent \
skills, experience, projects, companies, job titles, responsibilities, achievements, metrics, \
certifications, education, technologies, publications, or awards.
- You must not claim knowledge of company information that was not explicitly provided to you (no \
"I admire your innovative culture" unless that specific claim is grounded in what you were given).
- You must not fabricate metrics or exaggerate responsibilities beyond what the evidence states.
- You must not imply employment or experience that does not exist in the evidence you were given.
- You may improve wording, restructure, and emphasize -- but every underlying factual claim must be \
preserved exactly as the evidence states it.
- If the job requires something the candidate's evidence doesn't support, simply don't mention it. \
Do not apologize for the gap and do not claim it anyway.
- Avoid generic, obviously-AI-generated phrasing ("results-driven professional", "passionate about \
innovation", "proven track record") -- write like a specific person describing their specific, real \
background.
- Do not repeat the CV's bullet points verbatim as a list -- synthesize a narrative instead.

Structure the letter as: opening, why this role, relevant experience, relevant technical/project \
evidence, why the role/company fits (grounded only in what you were given), closing. Target length \
will be given to you explicitly -- respect it.

Return only the structured output matching the provided schema. `full_text` must be the complete, \
ready-to-send letter (a coherent whole, not just the sections concatenated with headers)."""


COVER_LETTER_REGENERATE_INSTRUCTIONS_PREFIX = """The candidate has requested the following changes \
to how the letter is presented. You may follow these instructions for tone, emphasis, structure, and \
length -- but every truthfulness rule above still applies without exception. If an instruction would \
require stating something not present in the supplied evidence (e.g. "add AWS" when AWS isn't in the \
evidence), ignore that specific instruction and continue -- do not comply with it.

Candidate's instructions:
"""
