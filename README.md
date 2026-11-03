# Online Examination Portal

**Online examination system with multiple-choice questions and automatic evaluation.**
UE24CS341A Software Engineering mini-project, PES University.

Faculty author multiple-choice questions into a tagged question bank, assemble them into an
examination and schedule it for a fixed window. Enrolled Students attempt it under a
server-enforced timer with autosave and resume. Every submission is evaluated automatically against
the stored answer key, and results are released when Faculty publishes them.

## Team

| Member | Role |
|---|---|
| Kshitij G Shettigar | Backend & Data · repository owner |
| Kartik Basavaraj Meti | Frontend & UX |
| Komal S Sajja | QA & Documentation |

## Documents (`docs/`)

| Document | Contents |
|---|---|
| [`docs/SRS.pdf`](docs/SRS.pdf) | **Software Requirements Specification** (IEEE 830) — overall description, use case diagram, 30 functional and 14 non-functional requirements in the course template, security objectives and requirements |
| [`docs/Use_Case_Diagram.pdf`](docs/Use_Case_Diagram.pdf) | **Use Case Diagram** — UML diagram of the 4 actors and 13 use cases, their «include» / «extend» relationships, and the requirements and test cases behind each use case |
| [`docs/Use_Case_Flow.pdf`](docs/Use_Case_Flow.pdf) | **Use Case Flow** — main success scenario, alternate and exception flows and business rules for UC-01 … UC-13, and the end-to-end examination lifecycle |
| [`docs/SAD.pdf`](docs/SAD.pdf) | **Software Architecture Document** — layered architecture and why, UML component diagram, traceability, security architecture, sequence diagrams, API design, error handling, deployment |
| [`docs/Test_Plan.pdf`](docs/Test_Plan.pdf) | **Test Plan** — methodology, deliverables, environment, security validation plan, and 119 unit, integration and system test cases with their results |
| [`docs/Sprint_Plan.pdf`](docs/Sprint_Plan.pdf) | **Sprint Plan** — backlog, story points, owners, Sprint 1 (19–23 Oct) and Sprint 2 (26 Oct – 1 Nov) |
| [`docs/Deviations.pdf`](docs/Deviations.pdf) | **Deviations register** — every departure from the SRS, SAD, Test Plan or Sprint Plan, and why |

### Test reports

| Report | Contents |
|---|---|
| [`docs/Unit_Test_Report.pdf`](docs/Unit_Test_Report.pdf) | The 68 unit test cases, run with `manage.py test -v 2` |
| [`docs/System_Validation_Report.pdf`](docs/System_Validation_Report.pdf) | ST_001–ST_013 and the NFR checks against the running system in Chrome, Edge and Firefox; screenshots in [`docs/validation/`](docs/validation/) |
| [`docs/Code_Coverage_Report.pdf`](docs/Code_Coverage_Report.pdf) | Statement coverage of the whole suite |
| [`docs/Branch_Coverage_Report.pdf`](docs/Branch_Coverage_Report.pdf) | Branch coverage of the whole suite |

### Sprint outcome videos

| Video | Shows |
|---|---|
| [`docs/videos/Sprint1_Outcome.mp4`](docs/videos/Sprint1_Outcome.mp4) (1 min) | Sprint 1 goal: register, course and enrollment, MCQ authoring, exam build, publish and schedule, a timed attempt, automatic scoring |
| [`docs/videos/Sprint2_Outcome.mp4`](docs/videos/Sprint2_Outcome.mp4) (2 min) | Sprint 2 goal: dashboard groups, one question at a time with the palette, autosave and resume, question versioning, results publication and scorecard, focus-loss events, audit trail, lockout, 360 px |

## Backlog

GitHub Project **Online Exam Portal - Backlog**: one issue per SRS requirement (`FR-001` … `FR-030`,
`NFR-001` … `NFR-014`) with story points, assignee, priority and sprint.

## Run locally

Python 3.10+ (CI uses 3.12). From the repository root, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:DJANGO_SECRET_KEY = "dev-only"   # required: the app will not start without it (NFR-014)
$env:DJANGO_DEBUG = "1"
python manage.py migrate
python manage.py createsuperuser      # creates an Administrator
python manage.py runserver
```

Sign in at <http://127.0.0.1:8000/login/>. Django's admin site is at `/django-admin/`, because `/admin/` is reserved for the Administrator role's pages.
Run the tests with `python manage.py test`.

### Where code goes

| App | SAD component | Requirements |
|---|---|---|
| `repository` | Exam Repository: **every model lives here** | — |
| `identity` | Identity & Enrollment Manager | FR-001 – FR-006, FR-015 |
| `questionbank` | Question Bank Manager | FR-007 – FR-009 |
| `examsetup` | Exam Setup Manager | FR-010 – FR-013 |
| `attempts` | Attempt Session Manager | FR-015 – FR-021, FR-029 |
| `evaluation` | Evaluation Engine | FR-022 – FR-024 |

**Every view must declare who may use it** (FR-003). Access is denied by default, so a view without a decorator returns 403 to everyone:

```python
from identity.access import roles, public
from repository.models import Role

@roles(Role.FACULTY)
def question_list(request): ...
```

Use `@public` only for sign-in, sign-out and registration.

## Workflow

Work happens on feature branches. The member who owns a backlog item raises the pull request that
closes it, another member reviews it, and only then is it merged into `main` (NFR-006).
