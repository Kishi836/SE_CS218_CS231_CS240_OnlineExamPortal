"""NFR-001 / NFR-003 load test: seeded Students sign in, take the exam, and submit.

Install Locust:
    python -m pip install locust

Quick test:
    python manage.py seed_bank --questions 500 --students 20
    $env:LOAD_EXAM_ID = "1"
    python manage.py runserver 127.0.0.1:8001 --insecure
    python -m locust -f loadtest/locustfile.py --host http://127.0.0.1:8001 --headless -u 5 -r 2 -t 30s --html loadtest/report-smoke.html

Full run: under Gunicorn as deployed (SAD 5), not runserver, whose 5-connection backlog refuses
connections at 200 users. Gunicorn needs Linux; on Windows run the server in WSL with the project on
the Linux filesystem (SQLite's WAL does not work over /mnt/c):
    python manage.py seed_bank
    gunicorn portal.wsgi:application -b 0.0.0.0:8001 --workers 25        # 2 x cores + 1
    python -m locust -f loadtest/locustfile.py --host http://127.0.0.1:8001 --headless -u 200 -r 20 -t 5m --reset-stats --html loadtest/report.html

Pass: the aggregate 95th percentile is 2 s or less (NFR-001) with the 50,000-question bank seeded (NFR-003).
--reset-stats starts counting once all 200 users are in, i.e. "while 200 attempts are active".
Keep HTML reports out of Git; put the full-run report in the PR description.
"""
import itertools
import os
import random
import re

from locust import HttpUser, between, task

EXAM_ID = os.environ.get("LOAD_EXAM_ID", "1")
PASSWORD = "LoadTest!2026"
student_numbers = itertools.count(1)


class Student(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Log in a seeded Student and start the exam."""
        self.email = f"load.student{next(student_numbers)}@pesu.pes.edu"
        self.attempt_url = None
        self.paper_html = ""
        self.csrf_token = None

        # Fetch login page and its CSRF cookie.
        self.client.get("/login/", name="login page")
        self.csrf_token = self.client.cookies.get("csrftoken")

        if not self.csrf_token:
            raise RuntimeError("CSRF cookie missing from login page")

        # Log in. The response may redirect to the student's dashboard.
        login_response = self.client.post(
            "/login/",
            data={
                "email": self.email,
                "password": PASSWORD,
                "csrfmiddlewaretoken": self.csrf_token,
            },
            headers={"X-CSRFToken": self.csrf_token},
            name="login",
            allow_redirects=True,
        )

        if login_response.status_code >= 400:
            raise RuntimeError(
                f"Login failed for {self.email}: HTTP {login_response.status_code}"
            )

        # Django can rotate the CSRF token during authentication.
        self.csrf_token = self.client.cookies.get(
            "csrftoken") or self.csrf_token

        # Start the exam. The POST normally redirects to /attempts/<id>/.
        response = self.client.post(
            "/api/attempts",
            data={
                "exam": EXAM_ID,
                "csrfmiddlewaretoken": self.csrf_token,
            },
            headers={"X-CSRFToken": self.csrf_token},
            name="start attempt",
            allow_redirects=True,
        )

        self.attempt_url = response.url
        self.paper_html = response.text

        if response.status_code >= 400:
            raise RuntimeError(
                f"Starting exam failed for {self.email}: HTTP "
                f"{response.status_code}; URL {self.attempt_url}"
            )

        if not re.search(r'data-question="\d+"', self.paper_html):
            raise RuntimeError(
                f"Exam paper not found for {self.email}; "
                f"final URL was {self.attempt_url}. Check exam ID and enrollment."
            )

        # Refresh the token from the rendered paper form if available.
        token_match = re.search(
            r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
            self.paper_html,
        )
        if token_match:
            self.csrf_token = token_match.group(1)

    def get_attempt_id(self):
        """Extract the attempt ID from the final paper URL."""
        if not self.attempt_url:
            return None

        match = re.search(r"/attempts/(\d+)/?", self.attempt_url)
        return match.group(1) if match else None

    @task(5)
    def answer(self):
        """Open a random question page from the palette (FR-018), then answer it."""
        attempt_id = self.get_attempt_id()
        if not attempt_id:
            return

        total = len(set(re.findall(rf"/attempts/{attempt_id}/q/(\d+)/", self.paper_html)))
        if total:
            page = self.client.get(
                f"/attempts/{attempt_id}/q/{random.randint(1, total)}/",
                name="question page",
            )
            if page.ok:
                self.paper_html = page.text

        matches = re.findall(
            r'<input\b(?=[^>]*\bdata-question="(\d+)")'
            r'(?=[^>]*\bvalue="(\d+)")[^>]*>',
            self.paper_html,
        )
        if not matches:
            return

        question_id, option_id = random.choice(matches)

        self.client.post(
            f"/api/attempts/{attempt_id}/answers",
            data={
                "question": question_id,
                "option": option_id,
                "csrfmiddlewaretoken": self.csrf_token,
            },
            headers={"X-CSRFToken": self.csrf_token},
            name="answer",
        )

    @task(1)
    def check_timer(self):
        """Fetch remaining time for the current attempt."""
        attempt_id = self.get_attempt_id()
        if not attempt_id:
            return

        self.client.get(
            f"/api/attempts/{attempt_id}/remaining",
            name="remaining",
        )

    def on_stop(self):
        """Submit the attempt when the simulated user stops."""
        attempt_id = self.get_attempt_id()
        if not attempt_id or not self.csrf_token:
            return

        self.client.post(
            f"/attempts/{attempt_id}/submit",
            data={"csrfmiddlewaretoken": self.csrf_token},
            headers={"X-CSRFToken": self.csrf_token},
            name="submit",
        )
