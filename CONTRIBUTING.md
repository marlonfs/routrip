# Contributing Guidelines

Thank you for your interest in contributing to **RouTrip**! We welcome
contributions from everyone. To ensure a smooth and collaborative experience,
please follow the guidelines below.

## Code of Conduct

We expect all contributors to be respectful and inclusive in every interaction.
Issues, pull requests, and discussions alike. Please keep the conversation
constructive and welcoming to newcomers.

## Getting Started

1. **Fork** the repository and **clone** your fork locally:
   ```bash
   git clone https://github.com/<your-user>/routrip
   cd routrip
   ```
2. Install the dependencies:
   ```bash
   pip install -r Comparison/requirements.txt
   ```
   > RouTrip requires **Python 3.11+**.
3. Create a new branch for your changes:
   ```bash
   git checkout -b feat/short-description
   ```

## Making Changes

1. Before starting, check the [issue tracker](https://github.com/marlonfs/routrip/issues)
   to see whether the task is already assigned or under discussion.
2. Work on a dedicated branch using a descriptive name
   (e.g. `feat/...`, `fix/...`, `docs/...`).
3. Write clear and concise commit messages.
4. Keep your code consistent with the surrounding style
   (we follow [PEP 8](https://peps.python.org/pep-0008/) for Python).
5. Test your changes and make sure they do not introduce regressions — run the
   relevant comparison script (e.g. `NewTSPs.py`) and confirm it completes.
6. Update the documentation (this file, the main `README.md`, or the folder-level
   READMEs) whenever your change affects usage or behavior.

## Submitting a Pull Request

1. Push your branch to your forked repository.
2. Open a pull request against the `main` branch of this repository.
3. Provide a clear description of **what** you changed and **why**, linking any
   related issue.
4. Be responsive to review feedback and address requested changes promptly.

## Reporting Issues

If you encounter a bug or have a suggestion, please
[open an issue](https://github.com/marlonfs/routrip/issues). Include as much
detail as possible — steps to reproduce, expected vs. actual behavior, and your
environment (OS and Python version) — so we can understand and reproduce it.

## Thank You

By following these guidelines you help us keep RouTrip a high-quality,
approachable codebase. We appreciate your contribution!
