"""Versioned prompts for CV generation. The candidate's full resume --
every experience, every project (with every existing bullet), all
education/certifications/achievements/research, and their entire
Technical Skills list -- is always included on a tailored CV, unfiltered
and unreworded. Tailoring to a specific job is deliberately limited to
the one thing a real candidate would actually rewrite between
applications: the summary framing. (Skill emphasis is also tailored per
job, but deterministically -- see
cv_customization_service._reorder_skills_for_job() -- rather than by an
LLM, per the user's ~95%-preservation / no-skill-invention standing
instruction.) Nothing here ever writes or rewrites a bullet, or decides
an experience/project is "not relevant enough" to include.
"""

CV_PLAN_PROMPT_V1 = """You are reading a job's requirements and a candidate's career profile to \
decide how to FRAME this candidate for this specific job -- not what content to include (their \
full profile is always included) and not any wording yet.

Rules:
- target_role should be the job's actual title/role, in the candidate's own terms where reasonable.
- priority_skills must be skills that are BOTH relevant to the job AND actually present in the \
candidate's profile (you will be told which skills are verified in the profile -- never list a \
skill that is not in the given profile skill list, no matter how relevant it would be).

Return only the structured output matching the provided schema."""


CV_SUMMARY_PROMPT_V1 = """You are writing a 2-4 sentence professional summary for a job-tailored CV.

Rules:
- Every claim must be directly supported by the candidate's career profile data you were given. \
Do not restate the job description's requirements as if they were the candidate's experience.
- Mention the target role, the candidate's genuinely relevant experience, and 2-4 relevant \
technical areas -- using only technologies/skills present in the profile data given to you.
- Do not state or imply years of experience beyond what the profile data states.
- Avoid generic AI language ("results-driven", "passionate", "dynamic professional", "proven track \
record") -- write plainly and factually, like a technical person describing their own background.
- Do not mention any technology, framework, or skill that is not in the profile data you were \
given, even if it appears in the job description."""
