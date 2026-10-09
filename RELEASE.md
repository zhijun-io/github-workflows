# Zhijun IO Release Management

This repository provides shared infrastructure for releasing Zhijun IO projects to Maven Central.

## Overview

The Zhijun IO maintains several related projects that can benefit from shared release infrastructure:

| Project | Description | Status |
|---------|-------------|--------|
| agent-client | Process execution and workspace management | Active |

## Integration Tiers

Projects can adopt all, some, or none of the shared tooling:

| Tier | Reusable Workflows | Parent POM | PR-based Releases | Release Script |
|------|-------------------|------------|-------------------|----------------|
| **Full** | Yes | Yes | Yes | Yes |
| **Partial** | Yes | No | Optional | Yes |
| **Independent** | No | No | No | Manual only |

## Reusable Workflows

### CI Build (`ci-build.yml`)

Standard CI workflow for building and testing.

**Usage:**
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

**Inputs:**
- `java-version` (default: `17`) - Java version to use
- `java-distribution` (default: `temurin`) - Java distribution
- `maven-goals` (default: `clean verify -B -ntp`) - Maven goals to run
- `skip-tests` (default: `false`) - Skip running tests
- `upload-test-results` (default: `true`) - Upload test results as artifact

### Publish Snapshot (`publish-snapshot.yml`)

Publishes SNAPSHOT versions to Maven Central.

**Usage:**
```yaml
name: Publish Snapshot

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  publish:
    uses: zhijun-io/github-workflows/.github/workflows/publish-snapshot.yml@main
    secrets:
      MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
      MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
```

**Inputs:**
- `java-version` (default: `17`) - Java version to use
- `skip-tests` (default: `false`) - Skip tests before publish
- `verify-first` (default: `true`) - Run verify before deploy

**Secrets Required:**
- `MAVEN_USERNAME` - Sonatype Portal username
- `MAVEN_PASSWORD` - Sonatype Portal token

### Maven Central Release (`maven-central-release.yml`)

Full release workflow with GPG signing and tagging.

**Usage:**
```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version (e.g., 0.1.0)'
        required: true
        type: string

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

**Inputs:**
- `version` (required) - Release version (e.g., `0.1.0`)
- `java-version` (default: `17`) - Java version to use
- `skip-tests` (default: `false`) - Skip tests
- `create-tag` (default: `true`) - Create and push Git tag
- `tag-prefix` (default: `v`) - Tag prefix (e.g., `v` for `v0.1.0`)

**Secrets Required:**
- `MAVEN_USERNAME` - Sonatype Portal username
- `MAVEN_PASSWORD` - Sonatype Portal token
- `GPG_SECRET_KEY` - ASCII-armored GPG private key
- `GPG_PASSPHRASE` - GPG passphrase

## Release Script

The `zhijun-io-release.py` script provides interactive command-line releases with the same experience as the Spring AI release scripts.

### Installation

The script requires Python 3.8+ with no additional dependencies.

### Usage

```bash
# Release agent-client 0.1.0
python3 zhijun-io-release.py agent-client 0.1.0

# Dry run (preview without making changes)
python3 zhijun-io-release.py agent-client 0.1.0 --dry-run

# Release with specific GitHub org
python3 zhijun-io-release.py agent-client 0.1.0 --org zhijun-io
```

### What the Script Does

1. **Clone** - Fresh checkout to isolated workspace
2. **Set Version** - Update POM versions via `mvn versions:set`
3. **Verify** - Check no SNAPSHOT dependencies remain
4. **Build** - Fast compile (skip tests for speed)
5. **Commit** - Commit release version
6. **Tag** - Create Git tag (e.g., `v0.1.0`)
7. **Push** - Push tag to GitHub
8. **Trigger** - Optionally trigger GitHub Actions release workflow

### Features

- Interactive step-by-step confirmation
- Dry-run mode for previewing changes
- State persistence for resuming interrupted releases
- Colored console output for readability

## Organization Secrets

Set these secrets at the organization level for all repositories to use:

| Secret | Description |
|--------|-------------|
| `MAVEN_USERNAME` | Sonatype Portal username |
| `MAVEN_PASSWORD` | Sonatype Portal token |
| `GPG_SECRET_KEY` | ASCII-armored GPG private key |
| `GPG_PASSPHRASE` | GPG passphrase |

Individual repositories can override with their own secrets if maintainers prefer using personal credentials.

## Project Registry

The `community-projects.yml` file lists all participating projects with their dependencies. This enables:

- Coordinated multi-project releases in dependency order
- Consistent configuration across projects
- Documentation of the community ecosystem

## Migration Guide

### Migrating to Reusable Workflows

1. Add workflow files that call the reusable workflows:

```yaml
# .github/workflows/ci.yml
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

2. Ensure your repository has the required secrets configured

3. Test with a dry-run or SNAPSHOT publish first

### Requirements for Projects

Projects using these workflows must have:

1. Maven wrapper (`./mvnw`) in repository root
2. Standard Maven project structure
3. `release` profile in POM with:
   - `central-publishing-maven-plugin` with `autoPublish=true`
   - `maven-gpg-plugin` with loopback pinentry
   - `maven-source-plugin` and `maven-javadoc-plugin`

Example release profile:
```xml
<profile>
    <id>release</id>
    <build>
        <plugins>
            <plugin>
                <groupId>org.sonatype.central</groupId>
                <artifactId>central-publishing-maven-plugin</artifactId>
                <version>0.9.0</version>
                <extensions>true</extensions>
                <configuration>
                    <publishingServerId>central</publishingServerId>
                    <autoPublish>true</autoPublish>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-gpg-plugin</artifactId>
                <version>3.2.7</version>
                <executions>
                    <execution>
                        <id>sign-artifacts</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>sign</goal>
                        </goals>
                        <configuration>
                            <gpgArguments>
                                <arg>--pinentry-mode</arg>
                                <arg>loopback</arg>
                            </gpgArguments>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</profile>
```
