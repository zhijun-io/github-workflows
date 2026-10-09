# GitHub Workflows

Shared infrastructure for GitHub projects including reusable GitHub Actions workflows, release scripts, and project configuration templates.

## Repository Structure

```
github-workflows/
├── .github/
│   ├── workflows/
│   │   ├── ci-build.yml                    # Reusable CI workflow (simple projects)
│   │   ├── ci-build-with-cli.yml           # CI with CLI tools support
│   │   ├── publish-snapshot.yml            # Snapshot publishing (simple projects)
│   │   ├── publish-snapshot-with-cli.yml   # Snapshot with CLI tools support
│   │   ├── maven-central-release.yml       # Release workflow (simple projects)
│   │   └── maven-central-release-with-cli.yml # Release with CLI tools support
│   ├── community-projects.yml              # Project registry
│   └── project.yml.template                # Template for project config
├── examples/                               # Example configurations
├── zhijun-io-release.py                    # Release script
├── RELEASE.md                              # Detailed release documentation
└── README.md                               # This file
```

## Quick Start

### For New Projects

1. **Add CI workflow** (`.github/workflows/ci.yml`):
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
```

2. **Add snapshot publishing** (`.github/workflows/publish-snapshot.yml`):
```yaml
name: Publish Snapshot
on:
  push:
    branches: [main]

jobs:
  publish:
    uses: zhijun-io/github-workflows/.github/workflows/publish-snapshot.yml@main
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
```

3. **Add release workflow** (`.github/workflows/release.yml`):
```yaml
name: Release
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version'
        required: true

jobs:
  release:
    uses: zhijun-io/github-workflows/.github/workflows/maven-central-release.yml@main
    with:
      version: ${{ inputs.version }}
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
      GPG_SECRET_KEY: ${{ secrets.GPG_SECRET_KEY }}
      GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
```

### For Projects Requiring CLI Tools (agent-client, etc.)

Projects that need CLI tools (Claude, Gemini, Vendir) for integration tests should use the `-with-cli` variants:

1. **CI with CLI tools** (`.github/workflows/ci.yml`):
```yaml
name: CI Build
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    uses: zhijun-io/github-workflows/.github/workflows/ci-build-with-cli.yml@main
    with:
      install-claude-cli: true
      install-gemini-cli: true
      install-vendir-cli: true
      validate-commits: true
    secrets:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

2. **Snapshot publishing with CLI tools**:
```yaml
name: Publish Snapshot
on:
  push:
    branches: [main]

jobs:
  publish:
    uses: zhijun-io/github-workflows/.github/workflows/publish-snapshot-with-cli.yml@main
    with:
      install-claude-cli: true
      install-gemini-cli: true
      validate-commits: true
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

3. **Release with CLI tools**:
```yaml
name: Release
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version'
        required: true

jobs:
  release:
    uses: zhijun-io/github-workflows/.github/workflows/maven-central-release-with-cli.yml@main
    with:
      version: ${{ inputs.version }}
      install-claude-cli: true
      install-gemini-cli: true
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
      GPG_SECRET_KEY: ${{ secrets.GPG_SECRET_KEY }}
      GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

### Release Script

```bash
# Dry run
python3 zhijun-io-release.py agent-sandbox 0.1.0 --dry-run

# Actual release
python3 zhijun-io-release.py agent-sandbox 0.1.0
```

## Setting Up Secrets

### Organization-Level Secrets (Shared)

Set these at the GitHub organization level (Settings > Secrets and variables > Actions):

| Secret | Description |
|--------|-------------|
| `MAVEN_USERNAME` | Sonatype Central Portal username |
| `MAVEN_PASSWORD` | Sonatype Central Portal token |
| `GPG_SECRET_KEY` | ASCII-armored GPG private key |
| `GPG_PASSPHRASE` | GPG key passphrase |

### Repository-Specific Secrets (API Keys)

API keys for CLI tools should be set at the **repository level**, not organization level. This ensures:
- Each maintainer uses their own API keys
- Keys are not shared across all org repositories
- Billing and usage tracking is per-project

Set these at the repository level (Repository Settings > Secrets and variables > Actions):

| Secret | Description | Required By |
|--------|-------------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude CLI | Projects using Claude CLI |
| `GEMINI_API_KEY` | Google API key for Gemini CLI | Projects using Gemini CLI |

### Verifying Maven Central Credentials

1. **Web Portal**: Log in at https://central.sonatype.com with your credentials
2. **Test Deploy**: Try publishing a SNAPSHOT version to verify credentials work

### Getting GPG Key in ASCII Armor Format

```bash
# List your keys
gpg --list-secret-keys --keyid-format LONG

# Export private key (replace KEY_ID with your key ID)
gpg --armor --export-secret-keys KEY_ID > private-key.asc

# The contents of private-key.asc go into GPG_SECRET_KEY secret
```

## Projects

| Project | Description | Workflow Type |
|---------|-------------|---------------|
| agent-client | Agent client for Spring AI (renamed from spring-ai-agents) | With CLI |

## Documentation

See [RELEASE.md](RELEASE.md) for detailed documentation on:
- Reusable workflow inputs and secrets
- Release script features
- Migration guides
- POM requirements
