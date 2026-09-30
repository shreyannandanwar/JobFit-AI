# Contributing to JobFit AI

Thank you for your interest in contributing. Contributions are welcome for bug fixes, tests, documentation, accessibility, and improvements to the resume and job-analysis workflows.

## 1. Fork the repository

Open the [JobFit AI repository](https://github.com/shreyannandanwar/JobFit-AI) on GitHub and select **Fork**. This creates a copy under your GitHub account.

## 2. Clone your fork

Replace `YOUR-USERNAME` with your GitHub username:

```bash
git clone https://github.com/YOUR-USERNAME/JobFir-AI.git
cd JobFir-AI
```

Add the original repository as `upstream` so you can bring in future changes:

```bash
git remote add upstream https://github.com/shreyannandanwar/JobFir-AI.git
```

## 3. Create a branch

Start from the latest default branch and create a focused feature or fix branch:

```bash
git switch main
git pull upstream main
git switch -c type/short-description
```

For example: `fix/project-export-path` or `docs/contributor-setup`.

## 4. Install dependencies

JobFit AI supports Python 3.11 or newer. From the repository root, create and activate a virtual environment, then install the pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 5. Configure environment variables

Copy the example file and add credentials only for the provider you intend to use:

```bash
cp .env.example .env
```

Available settings include `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENROUTER_API_KEY`, `GITHUB_TOKEN`, and `API_URL`. The LLM credentials are optional; generation has deterministic fallbacks. `API_URL` defaults to `http://localhost:8000`.

The application reads values from the process environment; it does not automatically load `.env`. In macOS/Linux, load the file into the current shell before starting the backend or Streamlit:

```bash
set -a
source .env
set +a
```

Alternatively, set variables in your shell or configure Streamlit secrets. Never commit `.env`, API keys, uploaded resumes, generated documents, or local databases.

## 6. Run the backend

With the virtual environment activated and environment variables configured:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The FastAPI service is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`.

## 7. Run Streamlit

Open a second terminal, activate the same virtual environment, load environment variables if needed, and run:

```bash
streamlit run streamlit_app.py
```

Streamlit uses `API_URL` to locate the backend and defaults to `http://localhost:8000`.

## 8. Run tests

The development requirements include pytest. From the repository root with the virtual environment activated, run:

```bash
python -m pytest -q
```

Add or update tests for changes to parsing, workflows, persistence, or document generation. If you change Docker or deployment configuration, validate the relevant configuration as well.

## 9. Make changes

- Keep changes focused and consistent with the existing module boundaries.
- Preserve deterministic fallbacks when adding optional LLM behavior.
- Update tests and relevant documentation alongside behavior changes.
- Do not commit credentials, uploaded resumes, generated files, local databases, or unrelated changes.
- Check your changes before committing:

  ```bash
  git status
  git diff --check
  git diff
  ```

Commit with a clear, imperative message:

```bash
git add path/to/changed/files
git commit -m "Fix project export path"
```

## 10. Submit a pull request

Push your branch to your fork:

```bash
git push -u origin type/short-description
```

On GitHub, open a pull request from your branch to the `main` branch of `shreyannandanwar/JobFir-AI`. Include:

- A concise description of the problem and solution.
- Tests run and their results.
- Any configuration, migration, or compatibility impact.
- Screenshots or example output for user-interface changes, where useful.

Respond to review feedback with focused follow-up commits.

## Reporting security issues

Do not disclose security vulnerabilities in a public issue. Contact the repository maintainer privately through GitHub with reproduction steps and impact details.

## License

By contributing, you agree that your contributions will be licensed under the repository's [MIT License](./LICENSE).
