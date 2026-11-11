"""FR-028 / Defect 1 browser check: real focus losses are recorded, moving between questions is not.

Django's test client runs no JavaScript, so focus.js can only be checked in a browser. Needs Playwright
with Chrome and Firefox, which are not in requirements.txt, so CI does not run this file.

Usage, from the repository root: python -I integrity/browser_check_fr028.py
Prints the counts and exits non-zero if any browser records the wrong number of focus-loss events."""
import os, pathlib, subprocess, sys, tempfile, time

repo = pathlib.Path(__file__).resolve().parent.parent
db = pathlib.Path(tempfile.mkdtemp()) / "fr028.sqlite3"
env = {**os.environ, "OEP_DB_PATH": str(db), "DJANGO_SECRET_KEY": "fr028-check",
       "DJANGO_SETTINGS_MODULE": "portal.settings", "DJANGO_ALLOW_ASYNC_UNSAFE": "1"}
os.environ.update(env)
subprocess.run([sys.executable, "manage.py", "migrate", "-v", "0"], cwd=repo, env=env, check=True)
sys.path.insert(0, str(repo)); os.chdir(repo)
import django; django.setup()
from portal.testkit import PASSWORD, World
from repository.models import FocusEvent

BASE = "http://127.0.0.1:8769"
# Playwright suppresses real focus changes, so a tab switch is played as the events it fires.
BLUR = "window.dispatchEvent(new Event('blur')); window.dispatchEvent(new Event('focus'))"
HIDE = """for (const hidden of [true, false]) {
  Object.defineProperty(document, 'hidden', {value: hidden, configurable: true});
  document.dispatchEvent(new Event('visibilitychange'));
}
delete document.hidden;"""

w = World(n_questions=5); a = w.attempt()
server = subprocess.Popen([sys.executable, "manage.py", "runserver", BASE[7:], "--noreload", "--insecure"],
                          cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
from playwright.sync_api import sync_playwright

failed = False
try:
    with sync_playwright() as pw:
        for name, launch in [("Chrome", lambda: pw.chromium.launch(channel="chrome")), ("Firefox", pw.firefox.launch)]:
            FocusEvent.objects.all().delete()
            p = launch().new_page()
            p.goto(f"{BASE}/login/")
            p.fill("input[name=email]", w.stu_a.email); p.fill("input[name=password]", PASSWORD)
            p.locator("form button[type=submit]").last.click(); p.wait_for_load_state()
            p.goto(f"{BASE}/attempts/{a.pk}/q/1/"); p.wait_for_load_state()
            for script in (BLUR, BLUR, HIDE):  # three focus losses: two window blurs, one hidden tab
                with p.expect_response(lambda r: "/focus-lost" in r.url):
                    p.evaluate(script)
            for n in (2, 3, 4, 5):  # move through the palette like a Student; none of these is a focus loss
                p.click(f"nav.palette a >> nth={n - 1}"); p.wait_for_load_state(); time.sleep(1)
            got = FocusEvent.objects.filter(attempt=a).count()
            print(f"{name}: {got} focus-loss events for 3 losses and 4 question moves (expected 3)")
            failed |= got != 3
            p.context.browser.close()
finally:
    server.terminate()
sys.exit(1 if failed else 0)
