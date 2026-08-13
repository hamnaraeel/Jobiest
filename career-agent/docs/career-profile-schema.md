# Career Profile Schema

This document describes the data model behind the career knowledge base:
every entity, every field, how entities relate to each other, and — most
importantly — how the verification system works and how it is meant to be
used by the CV/cover-letter generation agent that will be built in a later
step.

## Guiding principle

This system is the **single source of truth** for a person's career facts.
Every future feature (job matching, CV tailoring, cover letter generation)
must read from here and must never introduce a fact that doesn't exist in
this store. Concretely:

- Every fact-bearing entity carries a `verified: bool` column, defaulting
  to `False`.
- Verification is meant to be backed by an `Evidence` record (a CV, a
  GitHub repo, a certificate, etc.) linked via `EvidenceLink` — it is a
  claim with a paper trail, not just a checkbox.
- If a job description requires a skill that isn't in the profile at all,
  the correct downstream behavior is to report it as **missing**, never to
  add it to a generated CV.

## Entities

### CareerProfile (`career_profiles`)

The root entity. One row per person (this is a single-user system; the API
works against the first profile row unless you extend it for multi-user).

**Personal information**: `full_name`, `professional_title`, `email`
(unique), `phone`, `city`, `country`, `linkedin_url`, `github_url`,
`portfolio_url`. No password field exists or is stored anywhere.

**Professional summary**: `current_summary` (free text), `target_roles`
(list of strings, e.g. `["Machine Learning Engineer", "AI Engineer"]`),
`preferred_industries`, `preferred_locations`, `remote_preference`
(`remote` / `hybrid` / `onsite` / `flexible`), `years_of_experience`.

Relationships: has many `Education`, `Experience`, `Project`, `Skill`,
`Certification`, `Achievement`, `Research`, `Evidence`.

### Skill (`skills`)

`name`, `category` (`Programming`, `ML/DL`, `NLP`, `Computer Vision`,
`LLM`, `MLOps`, `Cloud`, `Databases`, `Framework`, `Tool`, `Other`),
`proficiency` (`beginner`/`intermediate`/`advanced`/`expert`),
`years_used`, `verified`. Unique per `(profile_id, name)`.

`evidence_ids` is **not a column** — it's computed at read time by looking
up `EvidenceLink` rows where `entity_type = "skill"` and `entity_id` is
this skill's id. See "Evidence system" below.

### Education (`educations`)

`institution`, `degree`, `field`, `start_date`, `end_date`, `location`,
`grade`, `relevant_coursework` (list), `thesis`, `description`, `verified`.

### Experience (`experiences`) and ExperienceBullet (`experience_bullets`)

`Experience` holds the job-level facts: `company`, `role`,
`employment_type` (`full_time`/`part_time`/`contract`/`internship`/
`freelance`/`self_employed`), `location`, `start_date`, `end_date`,
`currently_working`, `description`, `technologies`, `skills`,
`achievements`, `verified`.

Each `ExperienceBullet` (`bullet`, `skills`, `verified`) is its own row,
one-to-many under `Experience`, specifically so that a future CV agent can
select individual bullets relevant to a specific job instead of dumping an
entire role's description onto every CV.

### Project (`projects`) and ProjectResult (`project_results`)

`Project` holds `name`, `description`, `problem`, `solution`,
`technologies`, `skills`, `github_url`, `demo_url`, `start_date`,
`end_date`, `verified`.

Quantified outcomes live in their own `ProjectResult` rows (`description`,
`metric`, `verified`) rather than being embedded in free text, so a CV
agent can pick a specific, verifiable metric ("+6.2% Dice score") instead
of paraphrasing a number out of a paragraph — paraphrasing numbers is
exactly the kind of drift the truth rules forbid.

### Research (`research_items`)

For research work that isn't traditional employment: `title`,
`description`, `methodology`, `datasets`, `models`, `results`,
`publications`, `research_area`, `technologies`, `verified`.

### Certification (`certifications`)

`name`, `issuer`, `issue_date`, `expiry_date`, `credential_id`,
`credential_url`, `verified`.

### Achievement (`achievements`)

`title`, `description`, `date`, `category` (`research`/`competition`/
`award`/`publication`/`academic`/`professional`), `metric`, `verified`.

## Evidence system

### Evidence (`evidence`)

A verifiable source: `source_type` (`CV`, `Resume`, `GitHub`,
`Research Paper`, `Project`, `Certificate`, `Employment Record`,
`User Provided`, `Other`), `source_name`, `source_url`, `description`,
`verified`.

### EvidenceLink (`evidence_links`)

A generic many-to-many join: `evidence_id`, `entity_type` (one of `skill`,
`education`, `experience`, `experience_bullet`, `project`,
`project_result`, `research`, `certification`, `achievement`),
`entity_id`.

Rather than putting an `evidence_ids` array column on every table (which
would need to be kept in sync in nine places), every entity is linked to
its evidence through this single join table. `GET` endpoints compute
`evidence_ids` for a given row by querying `EvidenceLink` at read time
(see `app/services/validation_service.py::get_evidence_ids` and
`to_read_schema`).

## Verification rules (`app/services/validation_service.py`)

These are the rules the future CV/cover-letter generation agent must
follow. They exist here as code and data-layer guarantees, not just as
prompt instructions, because prompts can be ignored and data structures
can't:

1. Never invent a skill, employment record, project, job title, degree,
   certification, metric, achievement, or responsibility that isn't a row
   in this database.
2. Never change a numeric result — `ProjectResult.metric` is stored
   verbatim and must be quoted verbatim.
3. Never claim years of experience or familiarity with a technology
   beyond what `Skill.years_used` / `Experience` / `Project.technologies`
   actually support.
4. `classify_skill_for_job(db, profile_id, skill_name)` gives the CV agent
   a mechanical way to check a job's required skill against the profile:
   - `SkillStatus.VERIFIED` — the skill exists and is verified. Safe to
     use in a tailored CV.
   - `SkillStatus.UNVERIFIED` — the skill exists but has no evidence yet.
     The CV agent should treat this cautiously (e.g. surface it to the
     user for confirmation rather than asserting it outright).
   - `SkillStatus.MISSING` — the skill does not exist in the profile at
     all. The CV agent must report this as a gap, never fabricate it.
5. `require_evidence_for_verification(db, entity_type, entity_id)` is a
   guard available for any future "mark as verified" workflow: it raises
   unless at least one `Evidence` row is already linked to that entity.

## How the future CV/cover-letter agent will consume this

1. Given a job description, extract the required skills/technologies.
2. For each requirement, call `classify_skill_for_job` against the active
   profile.
3. Pull the subset of `ExperienceBullet` / `ProjectResult` / `Research`
   rows whose `skills`/`technologies` overlap the job's requirements
   (this is what the `embedding` columns on those tables are reserved
   for — nearest-neighbor retrieval via pgvector, not yet implemented).
4. Compose a CV / cover letter strictly from the retrieved, verified rows.
   Anything classified `MISSING` is reported to the user as a gap, never
   silently added.
5. Present the draft to the user for approval before any submission step
   (a later build step — not implemented here).

## Vector-readiness

`ExperienceBullet.embedding`, `Project.embedding`, `Research.embedding`,
`Skill.embedding`, and `Education.embedding` are nullable
`pgvector` `Vector(1536)` columns (`pgvector-python`, `CREATE EXTENSION
vector` in the initial Alembic migration). They exist so a later step can
embed and retrieve career facts by semantic similarity to a job
description, without a schema migration at that point. No embedding or
retrieval logic exists yet — these columns are simply reserved.
