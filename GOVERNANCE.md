# Governance

SciView is a small open-source project. This note says who decides what, so that contributors know how
their work gets in and the project does not depend on one person.

## Roles

* **Maintainers** review and merge pull requests, publish releases and decide on the roadmap. Today:
  Oriol Sans Planell ([@OriolSansPlanell](https://github.com/OriolSansPlanell)).
* **Contributors** are everyone who opens an issue, a pull request, a plugin or a template.

Anyone who has contributed regularly for a few months (code, documentation, templates, plugins or reviews) can
be invited to become a maintainer by the existing maintainers. The project aims for at least two maintainers
from different institutions.

## Decisions

* Day-to-day changes are decided in pull requests: one maintainer's approval is enough, after CI passes.
* Changes to the file format, the plugin API or anything listed in [Stability](docs/stability.md) are
  discussed in an issue first and need the agreement of all active maintainers.
* Disagreements are settled by discussion in the issue; if that fails, the maintainers decide by majority,
  and the original author of the project breaks ties.
* The roadmap is public (issues and the upgrade plan) and anyone can propose changes to it.

## Scope

SciView is for explaining science: a new feature should make a method or a result clearer than a static
slide. General-purpose motion graphics belong in plugins or in other tools.

## Releases

Releases follow [semantic versioning](https://semver.org/). A maintainer tags `vX.Y.Z` on `main` after CI
passes on all platforms; the release workflow publishes to PyPI, and conda-forge and Zenodo follow from there.

## Conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
