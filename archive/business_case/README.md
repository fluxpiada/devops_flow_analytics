# Archief — business case testautomatisering (incasso, 2026)

Bevroren: wordt niet meer onderhouden. De beslisrapporten en het deck staan in
`cases/incasso_2026/`; de verantwoording in `docs/technisch-ontwerp.md` hier.

Draaien vanuit de repo-root (gebruikt de eigen kopie van `jira_core.py`):

```bash
uv run --with python-pptx python archive/business_case/testauto_businesscase.py --run 26442 --deck
```

Volledig terugzetten naar de staat vóór het herontwerp: `git checkout devops_01`.
