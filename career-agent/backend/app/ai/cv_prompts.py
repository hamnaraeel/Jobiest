"""Versioned prompts for CV generation. The candidate's full resume --
every experience, every project (with every existing bullet), all
education/certifications/achievements/research, and their entire
Technical Skills list -- is always included on a tailored CV, unfiltered.
Nothing here ever decides an experience or project is "not relevant
enough" to include, and nothing here ever writes a bullet from scratch.

What an LLM authors on a tailored CV is: the summary framing, and a
rewrite of the candidate's *existing* bullets that aligns their wording
with the target job description. Bullet rewriting is deliberately
constrained to restating facts already present in the source bullet --
every rewrite is checked deterministically afterwards
(cv_validation_service.validate_bullet_rewrite) and silently reverted to
the original text if it introduces a number, a technology, or padding
that the original did not contain. Skill emphasis is tailored per job
too, but deterministically -- see
cv_customization_service._reorder_skills_for_job() -- rather than by an
LLM, per the user's no-skill-invention standing instruction.
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


CV_BULLET_REWRITE_PROMPT_V1 = """You are an expert ATS resume writer rewriting a candidate's \
existing resume bullets so they read strongly and match a specific job description's vocabulary.

You will be given the target job (title, company, and its extracted requirements) and a list of the \
candidate's real bullets, each with an `id` and its original `text`. Return one rewritten bullet \
for every id you were given, in the same order.

HOW TO REWRITE
- Lead with a concrete action verb (Built, Designed, Shipped, Optimized, Automated, Led, Migrated, \
Instrumented, ...). Never open with "Responsible for", "Worked on", "Helped with", or "Assisted in".
- Where the original bullet already describes the outcome, scale, or performance impact of the \
work, make that outcome the point of the sentence instead of burying it at the end.
- Where the job description names the same concept as the bullet using different words, prefer the \
job description's term -- but ONLY when it genuinely denotes the same thing the candidate did. \
Matching a keyword is never worth misdescribing the work.
- Keep each bullet to one sentence, roughly the length of the original. Do not pad, and do not \
split one bullet into several.
- Write in past tense (present tense only if the original bullet is about current work), with no \
leading pronoun and no trailing period-free fragments.

WHAT YOU MAY NOT DO -- these are hard constraints, and a rewrite that breaks any of them is \
discarded and replaced with the candidate's original text:
- Do not introduce ANY number that is not in the original bullet. No invented percentages, \
latencies, throughputs, user counts, team sizes, dollar figures, or durations. If the original \
bullet has no metric, the rewrite has no metric.
- Do not introduce ANY technology, framework, library, cloud service, model name, or tool that is \
not named in the original bullet -- not even one the job description asks for.
- Do not add scope, seniority, or ownership the original does not state. "Contributed to" does not \
become "Led"; "a service" does not become "a distributed system serving millions".
- Do not merge facts from other bullets, other roles, or the job description into this bullet.
- Do not add filler adjectives ("cutting-edge", "robust", "end-to-end", "mission-critical") that \
carry no information from the original.

If a bullet is already strong and well-aligned with the job, return it unchanged. Returning the \
original text is always an acceptable answer and is strongly preferred over any rewrite you are \
not certain is faithful."""
