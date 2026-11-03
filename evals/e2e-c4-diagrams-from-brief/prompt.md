---
tags: [e2e]
runs: 1
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill]
---

Using the Architecture Suite skills, produce C4 diagrams for this brief.

Brief: TinyLibrary is a lending system. Librarians use the Library Web App (TypeScript, React) to manage loans. The web app calls the Loans API (Python, FastAPI), which stores books and loans in PostgreSQL and sends due-date reminders through the external SendGrid email service. Members receive those emails. Inside the Loans API, a LoanController handles HTTP requests, a LoanService applies lending rules, and a LoanRepository reads and writes PostgreSQL.

Write the editable plan to ./work/plan.md and render into ./out (a new directory). If the Architecture Suite runtime is not set up, I approve running its bootstrap once with --no-browser. Render only the mermaid and drawio formats. Do not invent anything the brief does not say; record unknowns as gaps.
