"""Versioned prompts for CV generation. The candidate's full resume --
every experience, every project (with every existing bullet), all
education/certifications/achievements/research -- is always included on
a tailored CV, unfiltered and unreworded. Tailoring to a specific job is
deliberately limited to exactly two things a real candidate would
actually adjust between applications: which of their own (verified)
skills to foreground, and the summary framing. Nothing here ever writes
or rewrites a bullet, or decides an experience/project is "not relevant
enough" to include.
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


CV_SKILL_SELECTION_PROMPT_V1 = """You are choosing which of the candidate's VERIFIED skills to \
surface on a job-tailored CV, grouped into categories.

Rules:
- Only use skill names from the profile skill list you were given -- never add a skill because the \
job description mentions it. If the job wants a skill the candidate's profile doesn't have, that \
skill simply does not appear anywhere in your output.
- Group into clear categories (e.g. Programming, Machine Learning, Deep Learning, Computer Vision, \
NLP/LLM, Frameworks, Tools, Databases, Cloud/MLOps) -- use categories that fit the actual skills, \
don't force an empty category to exist.
- Within each category, order skills so the ones most relevant to this job's requirements come \
first.
- Do not rename a skill to something more impressive-sounding than what the profile states (e.g. \
do not turn "Docker" into "Kubernetes orchestration")."""
