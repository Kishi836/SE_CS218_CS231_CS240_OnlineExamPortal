"""NFR-004 -- after an unplanned server restart, service is back within 60 s and every in-progress attempt
resumes with its saved responses and the correct remaining time.

This runs the real server as a separate process on a throwaway SQLite file, kills it mid-attempt
(no graceful shutdown), starts it again and talks to it over HTTP like a browser would.
"""
import http.cookiejar
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from portal.testkit import PASSWORD

SEED = """
from attempts.services import save_answer
from portal.testkit import World
w = World(n_questions=5)
a = w.attempt()
for o in w.right[:3]:
    save_answer(a, o.question_id, o.pk)
print(a.pk, *[o.pk for o in w.right[:3]])
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RestartTests(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = {**os.environ, "OEP_DB_PATH": str(Path(self.dir.name) / "restart.sqlite3")}
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.manage("migrate", "--noinput")
        out = self.manage("shell", "-c", SEED).strip().splitlines()[-1].split()  # Django 5.2 prints a banner first
        self.attempt_id, self.saved = int(out[0]), {int(x) for x in out[1:]}

    def tearDown(self):
        server = getattr(self, "server", None)
        if server and server.poll() is None:
            server.kill()
            server.wait()
        self.dir.cleanup()

    def manage(self, *args):
        return subprocess.run(
            [sys.executable, "manage.py", *args], cwd=settings.BASE_DIR, env=self.env,
            capture_output=True, text=True, check=True,
        ).stdout

    def start_server(self):
        """Start the server and return how many seconds it took to answer its first request."""
        started = time.monotonic()
        self.server = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{self.port}", "--noreload"],
            cwd=settings.BASE_DIR, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        while time.monotonic() - started < 60:
            try:
                urllib.request.urlopen(f"{self.base}/login/", timeout=2)
                return time.monotonic() - started
            except OSError:
                time.sleep(0.2)
        self.fail("The server did not answer within 60 s")

    def sign_in(self):
        """A fresh browser: new cookie jar, GET the form for its CSRF token, POST the credentials."""
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        form = opener.open(f"{self.base}/login/").read().decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form).group(1)
        data = urllib.parse.urlencode({"csrfmiddlewaretoken": token, "email": "stu.a@pesu.pes.edu", "password": PASSWORD})
        opener.open(urllib.request.Request(f"{self.base}/login/", data.encode(), headers={"Referer": f"{self.base}/login/"}))
        return opener

    def paper(self, opener):
        html = opener.open(f"{self.base}/attempts/{self.attempt_id}/").read().decode()
        remaining = int(re.search(r'data-remaining="(-?\d+)"', html).group(1))
        total_match = re.search(r'Question \d+ of (\d+)', html)
        total = int(total_match.group(1)) if total_match else 1
        checked = set()
        for n in range(1, total + 1):
            q_html = opener.open(f"{self.base}/attempts/{self.attempt_id}/q/{n}/").read().decode()
            checked.update(int(v) for v in re.findall(r'value="(\d+)" data-question="\d+" checked', q_html))
        return checked, remaining

    def test_NFR_004_service_returns_within_60_s_and_the_attempt_resumes_intact(self):
        self.start_server()
        before_checked, before_remaining = self.paper(self.sign_in())
        self.assertEqual(before_checked, self.saved)

        self.server.kill()  # unplanned: no shutdown hooks run
        self.server.wait()

        recovery = self.start_server()
        self.assertLess(recovery, 60)
        after_checked, after_remaining = self.paper(self.sign_in())
        self.assertEqual(after_checked, self.saved)  # every saved response restored
        # Remaining time still counts from the original server-stamped start: it went down by the
        # outage, never back up to the full duration.
        self.assertLessEqual(after_remaining, before_remaining)
        self.assertGreater(after_remaining, before_remaining - 60 - recovery)
