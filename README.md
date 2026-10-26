# Rick's LineSkip email alerts

Checks the public [Rick's venue page](https://tickets.lineleap.com/venues/T5WY8MCdL8qFulAAOIdv)
in Ann Arbor and emails you when a new LineSkip product/date combination appears.
The first run remembers existing listings without alerting. Price changes and a
previously seen listing returning do not trigger another email. Restocks cannot
be detected reliably from the available page data.

## Status

Implemented locally, **not deployed or enabled**. Live page fetching is verified;
email delivery requires your Gmail setup and a real test. Future releases must
appear on the public page before we can detect them. This coding session does not
provide an always-running service.

## Free hosting

The optional GitHub Actions workflow checks roughly every five minutes on standard
Linux runners. Public repositories have free standard runners, subject to GitHub's
terms and usage limits. Private repositories have limited free minutes; this
frequency can exceed them. Do not enable it in a private repository without checking
your allowance and billing controls. Do not change repository visibility without
reviewing its files and history.

Scheduled runs can be delayed or dropped, so this cannot guarantee catching cheap
tickets. Public repository schedules may stop after 60 days without activity.
Email may also be delayed. Gmail's sending limits still apply.

## Connect Gmail and enable alerts

1. Put these files on the repository's default branch in GitHub. Publishing the
   coding environment alone does not deploy this workflow.
2. Confirm the free hosting conditions above fit your repository.
3. In your Google account, enable two-step verification and create an
   [app password](https://myaccount.google.com/apppasswords) named `Rick's alerts`.
   Some managed or restricted accounts do not support app passwords. Never share
   your normal Gmail password or paste an app password into chat or code.
4. In GitHub, open the repository's **Settings → Secrets and variables → Actions**.
   Add repository **secrets**:
   - `SMTP_USERNAME`: your sending Gmail address.
   - `SMTP_PASSWORD`: the Google app password.
   - `ALERT_TO`: the email address where you want alerts (can be the same Gmail).
5. Add repository **variables**:
   - `SMTP_HOST`: optional; defaults to `smtp.gmail.com`.
   - `ENABLE_EMAIL_MONITOR`: `true` once ready.
6. Open **Actions → Rick's LineSkip email monitor → Run workflow**, and check
   **test_email**. Check your inbox and spam folder. This sends a real test email
   independently of LineLeap and leaves notification history alone. This verifies
   Gmail delivery only; a successful normal run is also needed to verify monitoring.
7. Run it again with **test_email unchecked** to save the initial baseline.
   Future scheduled checks email newly listed passes.

History is stored on a separate `monitor-state` branch, containing only public
ticket information and timestamps. The workflow needs permission to write that
branch. Do not delete it: deletion resets the baseline and could miss a release.
Set `ENABLE_EMAIL_MONITOR` to `false` to pause checks. Enable GitHub notifications
for failed workflows and check the Actions page periodically.

SMTP acceptance does not guarantee inbox delivery. An email accepted immediately
before history-saving fails may be sent again on the next run.

## Local development

Use the existing checkout; no additional Git worktree is needed. Requires Python
3.12+ and curl; no Python package installation. From the repository directory:

```sh
python -m unittest discover -s tests -v
python monitor.py --dry-run
```

Dry runs fetch real listings without sending email or changing history. Real runs
need `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `ALERT_TO` supplied securely
in the process environment; run `python monitor.py` after configuring those. Do not
put credentials in shell commands saved in history. Local history is ignored by Git.

The parser fails visibly if page data is absent, malformed, or for another venue.
HTTP or email failures do not advance history. TLS verification stays enabled.
