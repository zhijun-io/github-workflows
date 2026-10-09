# GitHub Workflows

Reusable GitHub Actions workflows and release tooling for Zhijun IO Maven projects.

Every Maven workflow here assumes the calling repository provides a Maven wrapper (`./mvnw`).

## Repository Structure

```
github-workflows/
├── .github/
│   ├── workflows/
│   │   ├── ci-build.yml               # Reusable CI build and test workflow
│   │   ├── publish-snapshot.yml       # Reusable -SNAPSHOT publishing workflow
│   │   ├── maven-central-release.yml  # Reusable Maven Central release workflow
│   │   ├── docker-build.yml           # Reusable Docker image build and push workflow
│   │   └── renovate.yml               # Runs self-hosted Renovate on a schedule
│   ├── community-projects.yml         # Project registry (documentation only)
│   ├── project.yml.template           # Template for a future PR-based release flow
│   └── renovate.json5                 # Renovate policy: automerge, no major bumps
├── examples/rose-parent/              # Ready-to-copy caller workflows
├── zhijun-io-release.py               # Local release preflight + workflow trigger
├── LICENSE                            # Apache License 2.0
├── RELEASE.md                         # Inputs, secrets, POM requirements
└── README.md                          # This file
```

## Before You Start

1. Push this repository to `main` - callers reference `@main` in their `uses:` lines.
2. If this repository is private, the calling repository must be able to read it.
3. Grant the release job `permissions: contents: write`. Without it the workflow
   cannot push the release commit, push the tag, or create the GitHub Release.
4. Configure the account or repository secrets listed in [RELEASE.md](RELEASE.md).
5. Grant the image job `permissions: packages: write` when a workflow pushes to
   GHCR. Without it the push is rejected by the registry.

## Quick Start

Copy the three files from `examples/rose-parent/` into
`.github/workflows/` of the consuming repository (renaming them to `ci.yml`,
`publish-snapshot.yml` and `release.yml`) and adjust `java-version`.

Minimal CI caller:

```yaml
name: CI Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    uses: zhijun-io/github-workflows/.github/workflows/ci-build.yml@main
    with:
      java-version: '17'
```

Minimal release caller:

```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version (e.g., 0.1.0)'
        required: true
        type: string
      next-version:
        description: 'Next development version, empty to skip'
        required: false
        type: string

jobs:
  release:
    permissions:
      contents: write
    uses: zhijun-io/github-workflows/.github/workflows/maven-central-release.yml@main
    with:
      version: ${{ inputs.version }}
      next-version: ${{ inputs.next-version }}
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
      GPG_SECRET_KEY: ${{ secrets.GPG_SECRET_KEY }}
      GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
```

Forward `next-version`: `zhijun-io-release.py` passes it, and GitHub silently
drops inputs that the caller does not declare.

Minimal Docker caller:

```yaml
name: Container Image

on:
  workflow_dispatch:

jobs:
  image:
    permissions:
      contents: read
      packages: write
    uses: zhijun-io/github-workflows/.github/workflows/docker-build.yml@main
    with:
      push: true
      tags: 'latest,0.1.0'
```

`docker-build.yml` is the only workflow that does not run Maven, so it needs no
`./mvnw`. It builds with the `docker buildx` CLI shipped on the runner, defaults
to `ghcr.io/<owner>/<repository>` with the built-in `GITHUB_TOKEN`, and always
adds an immutable `sha-<short>` tag. Non-GHCR registries need the
`registry-username` input and the `REGISTRY_PASSWORD` secret. Single
architecture only, and no layer cache - see [RELEASE.md](RELEASE.md).

## Release Script

```bash
# Preview every command without executing anything
python3 zhijun-io-release.py rose-parent 0.0.2 --dry-run

# Preflight, then trigger the release workflow
python3 zhijun-io-release.py rose-parent 0.0.2
```

The script clones the target repository into `<project>-release/`, sets the
version, checks for SNAPSHOT references, runs a fast build and triggers
`release.yml` with `version` and `next-version`. It never commits, tags or
pushes - the workflow owns the release. Requires Python 3.8+ and `gh`
(`gh auth login`) for the trigger step; `--no-workflow` stops after the preflight.

## Version Bumps

`.github/workflows/renovate.yml` runs self-hosted Renovate weekly against
`.github/renovate.json5`, updating the `actions/*` refs and the SHA-pinned
third-party actions.

Policy: `patch`, `minor` and `pin` updates are grouped into one pull request and
**automerged**. `major` updates open a pull request but are never automerged - a
major action bump changes runtimes and behaviour, which is exactly how these
workflows fell three majors behind last time.

This repository runs no CI of its own, so there is nothing for Renovate to wait
for: an automerged action bump lands unverified, and a mistake surfaces later as
a failing workflow in a consuming repository. Keep `major` out of automerge for
that reason, and review the grouped PR before it merges if you want a say.

Setup and guardrails:

1. Create `RENOVATE_TOKEN` as a fine-grained PAT (or GitHub App installation
   token) with write access to this repository and the `workflow` scope. Renovate
   must merge with that token - a merge made with the default `GITHUB_TOKEN`
   never triggers workflows in the consuming repositories.
2. Branch protection must let that token bypass pull-request reviews, otherwise
   automerge stalls silently.

## Projects

Verified callers of these reusable workflows:

| Project | Workflows |
|---------|-----------|
| rose-parent | CI, snapshot, release |
| spring-boot-skills | CI, snapshot, release |

`rose` keeps its own standalone CI workflow and does not call into this repository.

## License

Apache License 2.0 - see [LICENSE](LICENSE). This matches the license declared by
the Maven projects that consume these workflows (for example `rose-parent` and
`rose`). Third-party actions are referenced by immutable commit SHA and kept
current by Renovate.

## Documentation

See [RELEASE.md](RELEASE.md) for the full input and secret reference, the POM
`release` profile requirements, and troubleshooting.
