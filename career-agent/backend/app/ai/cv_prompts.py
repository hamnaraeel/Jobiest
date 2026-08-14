"""Versioned prompts for CV generation. Each has exactly one job -- planning
(what to include), or content (how to word it). Never combined into one
do-everything prompt, even though the calling code may concatenate two of
these into a single API request for cost control (see
cv_customization_service.py) -- concatenation happens at the call site,
not by editing a prompt in place.
"""

CV_PLAN_PROMPT_V1 = """You are deciding WHAT to include in a job-tailored CV -- not writing any \
wording yet. You will be given a job's requirements and a compact list of the candidate's career \
profile (experience, projects, research, skills), each item tagged with its database id.

Rules:
- Only select ids that were actually given to you. Never invent an id.
- Prioritize, in order: (1) experience/projects that directly demonstrate the job's required \
skills, (2) experience/projects relevant to the job's responsibilities, (3) research relevant to \
the job's technical area, (4) everything else only if it strengthens the case.
- priority_skills must be skills that are BOTH relevant to the job AND actually present in the \
candidate's profile (you will be told which skills are verified/unverified in the profile -- never \
list a skill that is not in the given profile skill list, no matter how relevant it would be).
- Do not select every experience/project available -- be selective. A focused CV beats a complete \
one. Leave out items with no clear relevance to this job.
- sections should be an ordered list from: summary, skills, experience, projects, research, \
education, certifications, achievements. Only include sections that have selected content, in the \
order they should appear (most relevant first, but always keep summary first if included).

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


CV_BULLET_REWRITE_PROMPT_V1 = """You are rewriting existing CV bullet points for clarity and \
relevance to a specific job -- you are not writing new bullets.

For each experience/project you were given, you will see its existing bullets (each with an id) \
and the job's priority skills/technologies. For each bullet worth including, produce a rewritten \
version by referencing its source_bullet_id.

Rules (all mandatory):
1. The rewritten text must describe the exact same underlying fact as the original -- same \
project/company, same technology, same outcome.
2. Never introduce a number, percentage, or metric that is not already present in the original \
bullet text.
3. Never introduce a technology, tool, or skill name that is not already present in the original \
bullet text OR in that experience/project's technology list you were given.
4. You may shorten, clarify, reorder clauses, or use more precise technical terminology from the \
job description ONLY if it accurately describes what the original bullet already says (e.g. \
"worked on X" can become "developed X" only if the original evidence supports "developed").
5. Never invent an outcome, an impact, or a responsibility the original text does not state.
6. If a bullet has nothing relevant to say for this job, omit it rather than stretching it.
7. Every rewritten_text must reference a real source_bullet_id you were given -- never a bullet id \
that wasn't provided to you."""


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


CV_PROJECT_SELECTION_PROMPT_V1 = """You are judging which of the candidate's projects and research \
items are relevant enough to a specific job to include on a tailored CV.

Rules:
- Judge relevance by genuine technical/domain overlap with the job's responsibilities and required \
skills (e.g. for a computer vision role, prioritize segmentation/detection/classification/medical \
imaging/CNN/Vision-Transformer work over unrelated web development work).
- Do not include a project or research item just to fill space -- a focused CV beats a complete \
one. Recommend leaving out items with no clear relevance.
- You are selecting ids only, from the ids given to you -- you do not write any content in this \
step."""
