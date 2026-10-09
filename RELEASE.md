# Zhijun IO Release Management

This repository provides shared release infrastructure for Zhijun IO Maven
projects publishing to Maven Central, plus a reusable Docker image build.

## Ownership

| Concern | Owner |
|---------|-------|
| versions:set, commit, tag, deploy, next development version | `maven-central-release.yml` |
| Local preflight and triggering the release | `zhijun-io-release.py` |

Keeping this split in one place is what makes the two re-runnable: the script
leaves the POM dirty in a throwaway clone, the workflow starts from a clean
checkout and owns every commit it pushes.

## Reusable Workflows

The three Maven workflows take `java-version` (default `17`), `java-distribution`
(default `temurin`) and `timeout-minutes`. They run on `ubuntu-latest` and
require `./mvnw` in the calling repository. `docker-build.yml` is the fourth
workflow: it runs no Maven and therefore needs no wrapper.

### CI Build (`ci-build.yml`)

**Inputs**
- `maven-goals` (default: `clean verify -B`) - Maven goals to run
- `skip-tests` (default: `false`) - Append `-DskipTests`
- `upload-test-results` (default: `true`) - Upload surefire and failsafe reports
- `timeout-minutes` (default: `60`)

No secrets required.

### Publish Snapshot (`publish-snapshot.yml`)

Deploys the current `-SNAPSHOT` version. The project POM (or its parent) must
declare the `central` snapshot repository in `<distributionManagement>`.

**Inputs**
- `skip-tests` (default: `false`) - Skip tests during the verify phase
- `verify-first` (default: `true`) - Run `clean verify` before `deploy`
- `timeout-minutes` (default: `60`)

**Secrets (required)**: `MAVEN_USERNAME`, `MAVEN_PASSWORD`

### Maven Central Release (`maven-central-release.yml`)

**Inputs**
- `version` (required) - Release version, `X.Y.Z` or `X.Y.Z-suffix`
- `skip-tests` (default: `false`)
- `create-tag` (default: `true`) - Commit the release version, tag and push
- `tag-prefix` (default: `v`) - `v0.1.0` for version `0.1.0`
- `next-version` (default: ``) - Development version to commit after the release;
  empty means no bump. Use a `-SNAPSHOT` version such as `0.1.1-SNAPSHOT`.
- `release-branch` (default: ``) - Branch to push to; empty resolves to the
  repository default branch
- `timeout-minutes` (default: `30`)

**Secrets (required)**: `MAVEN_USERNAME`, `MAVEN_PASSWORD`, `GPG_SECRET_KEY`, `GPG_PASSPHRASE`

The calling job must declare:

```yaml
    permissions:
      contents: write
```

If the default branch is protected, the protection rule must allow the
`github-actions[bot]` identity used by the workflow, or releases fail at the
push step after artifacts are already published.

### Docker Image (`docker-build.yml`)

Builds the image described by a `Dockerfile` with the `docker buildx` CLI that
ships on the runner, and pushes it when `push` is `true`. No third-party Docker
actions are used, so there is nothing extra to pin or keep current.

**Inputs**
- `registry` (default: `ghcr.io`) - Registry host used in every tag
- `image-owner` (default: ``) - Registry namespace; empty resolves to the
  repository owner, lowercased because registry namespaces are case-sensitive
- `image-name` (default: ``) - Image name; empty resolves to the repository name
- `registry-username` (default: ``) - Username for registries other than `ghcr.io`
- `context` (default: `.`) - Build context directory
- `dockerfile` (default: `Dockerfile`) - Dockerfile path, relative to the context
- `tags` (default: `latest`) - Comma-separated tags; an immutable `sha-<short>`
  tag is always appended
- `build-args` (default: ``) - Comma-separated `KEY=VALUE` build arguments
- `push` (default: `false`) - Push the built tags
- `timeout-minutes` (default: `30`)

**Secrets**: none required for GHCR - the workflow logs in with the built-in
`GITHUB_TOKEN`. Any other registry needs `REGISTRY_PASSWORD` plus the
`registry-username` input, and fails fast if either is missing.

The calling job must declare:

```yaml
    permissions:
      contents: read
      packages: write
```

Limitations, all deliberate:

- Comma-separated `tags` and `build-args` cannot contain spaces; spaces are
  stripped before parsing.
- The build command is echoed to the log for diagnosis, so `build-args` values
  are visible: never pass a credential as a build argument.
- Single architecture only. Multi-arch output needs a buildx driver with a
  cross-architecture engine, and layer caching needs `setup-buildx-action` to
  create a `type=gha` cache - neither is worth the extra third-party dependency
  for the images these projects publish.

Published image refs are written to the job summary and to the step outputs
`image` and `tags`.

## Release Script

`zhijun-io-release.py` needs Python 3.8+, `git`, and `gh` for the trigger step.

```bash
# Preview every command without executing
python3 zhijun-io-release.py rose-parent 0.0.2 --dry-run

# Preflight and trigger
python3 zhijun-io-release.py rose-parent 0.0.2

# Preflight only
python3 zhijun-io-release.py rose-parent 0.0.2 --no-workflow
```

Steps:

1. **Clone** - fresh checkout into `<project>-release/` (`gh repo clone` when
   `gh` is available, so private repositories authenticate)
2. **Set Version** - `./mvnw versions:set`
3. **Verify** - no SNAPSHOT references remain
4. **Build** - fast compile with tests skipped
5. **Trigger** - `gh workflow run release.yml -f version=… -f next-version=…`

Projects are declared in `PROJECTS` at the top of the script; add an entry there
when onboarding a new repository - the target repository must provide
`.github/workflows/release.yml` calling `maven-central-release.yml`. Progress is
written to `state/`, and both `state/` and `<project>-release/` are git-ignored.

## Secrets

Set these once at the account level (Settings → Secrets and variables → Actions);
individual repositories can override them.

| Secret | Description |
|--------|-------------|
| `MAVEN_USERNAME` | Sonatype Central Portal username |
| `MAVEN_PASSWORD` | Sonatype Central Portal token |
| `GPG_SECRET_KEY` | ASCII-armored GPG private key |
| `GPG_PASSPHRASE` | GPG key passphrase |
| `REGISTRY_PASSWORD` | Password or access token for a Docker registry other than GHCR - optional |

## Project Registry

`.github/community-projects.yml` documents the ecosystem and dependency order.
It is **documentation only** - no workflow or script reads it, and the release
script keeps its own `PROJECTS` list. `.github/project.yml.template` and the
`pr-based-releases` flag are likewise unread by automation: no workflow triggers
on `project.yml` yet. Update all three together, or delete them if the duplication
stops paying for itself.

## Requirements for Consumer Projects

These apply to the Maven workflows. `docker-build.yml` needs only a `Dockerfile`
at the path it is given.

1. Maven wrapper (`./mvnw`) committed and executable
2. A `release` profile that publishes signed sources and javadoc through the
   Central publishing plugin:

```xml
<profile>
    <id>release</id>
    <build>
        <plugins>
            <plugin>
                <groupId>org.sonatype.central</groupId>
                <artifactId>central-publishing-maven-plugin</artifactId>
                <version>0.10.0</version>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</profile>
```

`rose-parent` already provides this profile, so inheriting from it satisfies
the requirement.

The release workflow greps the POM files for `SNAPSHOT`. To check the resolved
dependency tree instead, add maven-enforcer to the `release` profile with
`requireReleaseDeps` and `requireReleaseVersion`.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `Resource not accessible by integration` | Missing `permissions: contents: write` on the calling job |
| `process started with '/bin/bash -e {0}' failed with exit code 1` at the tag step | GPG passphrase secret missing or mismatched with the imported key |
| Release never appears on Central | `release` profile absent, or `autoPublish` disabled - check the deployment log for a publishing-portal link |
| `next-version` has no effect | The caller does not declare/forward the input; GitHub drops unmatched inputs silently |
| `gh: command not found` / auth error from the script | Run `gh auth login`, then retry with `--dry-run` first |
| SNAPSHOT check fails right after a successful release | The bump step did not run - pass `next-version` |
| Release commits and tags appear, but no CI runs afterwards | Expected - pushes made with `GITHUB_TOKEN` do not trigger workflows |
| Push rejected while branch protection is active | Allow the `github-actions[bot]` identity, or point `release-branch` at an unprotected branch |
| `denied` or `unauthorized` when pushing an image | The calling job lacks `permissions: packages: write`, or the token cannot create the package in that namespace |
| `needs the registry-username input and the REGISTRY_PASSWORD secret` | A non-GHCR `registry` was set without credentials |
| Image pushed but no architecture matches the runner | Expected - `docker-build.yml` is single-architecture, `linux/amd64` |
