#!/usr/bin/env python3
"""
ZhiJun IO Release Script - Unified Release Automation

Automates releases for ZhiJun IO projects with interactive
step-by-step confirmation and dry-run support.

The release itself (version set, commit, tag, deploy, next development version)
is owned by the reusable workflow in the target repository. This script only
runs a local preflight and then triggers that workflow.

Projects Supported:
- rose-parent
- spring-boot-skills
Usage:
    python3 zhijun-io-release.py rose-parent 0.1.0 --dry-run
    python3 zhijun-io-release.py rose-parent 0.1.0
"""

import sys
import subprocess
import argparse
import json
import shutil
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


# Release workflow file inside the target repository
RELEASE_WORKFLOW = "release.yml"

# Tag prefix must match the `tag-prefix` input of the release workflow
TAG_PREFIX = "v"

# Project configuration
#
# A project can be listed here only if it has .github/workflows/release.yml
# calling maven-release.yml (see examples/rose-parent/release.yml).
PROJECTS = {
    "rose-parent": {
        "repo": "zhijun-io/rose-parent",
        "description": "Parent POM for Rose projects (Java 17, Maven Central publishing)",
    },
    "spring-boot-skills": {
        "repo": "zhijun-io/spring-boot-skills",
        "description": "SkillsJars for Spring Boot applications",
    },
}

VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$')


@dataclass
class ReleaseConfig:
    """Configuration for the release workflow"""
    script_dir: Path
    project_name: str
    target_version: str
    dry_run: bool = False
    trigger_workflow: bool = True

    def __post_init__(self):
        """Post-initialization validation"""
        if self.project_name not in PROJECTS:
            raise ValueError(f"Unknown project: {self.project_name}. Valid projects: {', '.join(PROJECTS.keys())}")

        if not self.validate_version():
            raise ValueError(f"Invalid version format: {self.target_version}")

    @property
    def project_config(self) -> Dict[str, str]:
        return PROJECTS[self.project_name]

    @property
    def repo(self) -> str:
        return self.project_config["repo"]

    @property
    def workspace_dir(self) -> Path:
        return self.script_dir / f"{self.project_name}-release"

    @property
    def state_dir(self) -> Path:
        return self.script_dir / "state"

    @property
    def release_state_file(self) -> Path:
        return self.state_dir / f"release-{self.project_name}-{self.target_version}.json"

    @property
    def tag_name(self) -> str:
        return f"{TAG_PREFIX}{self.target_version}"

    @property
    def next_dev_version(self) -> str:
        """Next development version, passed to the workflow as `next-version`"""
        parts = self.target_version.split('.')
        if len(parts) != 3:
            return f"{self.target_version}-SNAPSHOT"
        major, minor, patch = parts
        patch = patch.split('-', 1)[0]
        next_patch = str(int(patch) + 1)
        return f"{major}.{minor}.{next_patch}-SNAPSHOT"

    def validate_version(self) -> bool:
        """Validate version format: X.Y.Z or X.Y.Z-suffix"""
        return bool(VERSION_PATTERN.match(self.target_version))


class Colors:
    """ANSI color codes for console output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


class Logger:
    """Logging utilities with color support"""

    @staticmethod
    def info(message: str):
        print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")

    @staticmethod
    def warn(message: str):
        print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")

    @staticmethod
    def error(message: str):
        print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")

    @staticmethod
    def success(message: str):
        print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")

    @staticmethod
    def step(message: str):
        print(f"{Colors.CYAN}[STEP]{Colors.NC} {message}")

    @staticmethod
    def bold(message: str):
        print(f"{Colors.BOLD}{message}{Colors.NC}")


class GitHelper:
    """Git operations helper for release workflow"""

    def __init__(self, repo_dir: Path, config: ReleaseConfig):
        self.repo_dir = repo_dir
        self.config = config

    def clone_repository(self) -> bool:
        """Clone the project repository"""
        try:
            if self.config.workspace_dir.exists():
                Logger.info(f"Removing existing directory: {self.config.workspace_dir}")
                if not self.config.dry_run:
                    shutil.rmtree(self.config.workspace_dir)

            clone_url = f"https://github.com/{self.config.repo}.git"
            # `gh repo clone` authenticates for private repositories when the CLI is available
            if shutil.which('gh'):
                cmd = ['gh', 'repo', 'clone', self.config.repo, str(self.config.workspace_dir)]
            else:
                cmd = ['git', 'clone', clone_url, str(self.config.workspace_dir)]

            Logger.info(f"Cloning repository: {clone_url}")

            if self.config.dry_run:
                Logger.warn("DRY RUN: Would clone repository")
                return True

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            Logger.success("Repository cloned successfully")
            return True

        except subprocess.CalledProcessError as e:
            Logger.error(f"Failed to clone repository: {e}")
            Logger.error("For private repositories run `gh auth login` so `gh repo clone` can authenticate.")
            return False

    def get_current_version(self) -> Optional[str]:
        """Get current version from main POM"""
        if self.config.dry_run:
            Logger.info("DRY RUN: Would read current version from pom.xml")
            return "X.Y.Z-SNAPSHOT (dry-run placeholder)"

        try:
            pom_path = self.repo_dir / "pom.xml"
            if not pom_path.exists():
                Logger.error("pom.xml not found")
                return None

            with open(pom_path, 'r') as f:
                content = f.read()

            # Ignore the inherited version: the first remaining <version> is the project version
            content = re.sub(r'<parent>.*?</parent>', '', content, flags=re.DOTALL)
            match = re.search(r'<version>([^<]+)</version>', content)
            if match:
                return match.group(1)

            return None
        except Exception as e:
            Logger.error(f"Failed to get current version: {e}")
            return None


class MavenHelper:
    """Maven operations helper"""

    def __init__(self, repo_dir: Path, config: ReleaseConfig):
        self.repo_dir = repo_dir
        self.config = config

    def run_maven(self, goals: List[str]) -> bool:
        """Run Maven command"""
        cmd = ['./mvnw'] + goals

        Logger.info(f"Running Maven: {' '.join(cmd)}")

        if self.config.dry_run:
            Logger.warn("DRY RUN: Would execute Maven command")
            return True

        try:
            subprocess.run(cmd, cwd=self.repo_dir, check=True)
            return True
        except subprocess.CalledProcessError as e:
            Logger.error(f"Maven command failed: {' '.join(cmd)}")
            return False

    def set_version(self, version: str) -> bool:
        """Set version using Maven versions plugin"""
        Logger.info(f"Setting project version to: {version}")
        return self.run_maven([
            "versions:set",
            f"-DnewVersion={version}",
            "-DgenerateBackupPoms=false"
        ])

    def fast_build(self) -> bool:
        """Run fast build without tests"""
        Logger.info("Running fast build (skip tests)")
        return self.run_maven([
            "clean", "package",
            "-Dmaven.javadoc.skip=true",
            "-DskipTests",
            "-B"
        ])

    def check_for_snapshots(self) -> bool:
        """Check for remaining SNAPSHOT versions in POM files

        Uses the same anchored pattern as maven-release.yml so that
        comments and <snapshots> configuration are not false positives.
        """
        if self.config.dry_run:
            Logger.info("DRY RUN: Would check for SNAPSHOT versions")
            return True

        try:
            cmd = [
                "grep", "-rnE", "--include=pom.xml", "--exclude-dir=target",
                r'<(version|[A-Za-z0-9._-]+\.version)>[^<]*SNAPSHOT', ".",
            ]
            result = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True)

            if result.returncode == 0:
                Logger.error("Found SNAPSHOT references in POM files:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        Logger.error(f"  {line}")
                return False
            else:
                Logger.info("No SNAPSHOT versions found in POM files")
                return True

        except Exception as e:
            Logger.error(f"Failed to check for SNAPSHOT versions: {e}")
            return False


class GitHubActionsHelper:
    """GitHub Actions workflow trigger helper"""

    def __init__(self, config: ReleaseConfig):
        self.config = config

    def is_gh_available(self) -> bool:
        """Check if GitHub CLI is available and authenticated"""
        try:
            subprocess.run(['gh', 'auth', 'status'],
                         capture_output=True, text=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def trigger_release_workflow(self) -> bool:
        """Trigger the release workflow on GitHub"""
        try:
            cmd = [
                'gh', 'workflow', 'run', RELEASE_WORKFLOW,
                '--repo', self.config.repo,
                '-f', f'version={self.config.target_version}',
                '-f', f'next-version={self.config.next_dev_version}'
            ]

            Logger.info(f"Triggering GitHub workflow: {' '.join(cmd)}")

            if self.config.dry_run:
                Logger.warn("DRY RUN: Would trigger GitHub workflow")
                return True

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            Logger.success("GitHub workflow triggered successfully")
            return True

        except subprocess.CalledProcessError as e:
            Logger.error(f"Failed to trigger GitHub workflow")
            if e.stderr:
                Logger.error(f"Error: {e.stderr}")
            return False


class ReleaseWorkflow:
    """Main workflow orchestrator"""

    def __init__(self, config: ReleaseConfig):
        self.config = config
        self.git_helper = None
        self.maven_helper = None
        self.github_helper = None
        self._ensure_state_dir()

    def _ensure_state_dir(self):
        """Ensure state directory exists"""
        self.config.state_dir.mkdir(exist_ok=True)

    def save_state(self, phase: str, completed_steps: List[str]):
        """Save current release state to file"""
        state = {
            "project": self.config.project_name,
            "version": self.config.target_version,
            "phase": phase,
            "completed_steps": completed_steps,
            "timestamp": datetime.now().isoformat(),
        }

        if not self.config.dry_run:
            with open(self.config.release_state_file, 'w') as f:
                json.dump(state, f, indent=2)
            Logger.info(f"State saved to {self.config.release_state_file}")

    def confirm_step(self, step_name: str, commands: List[str]) -> bool:
        """Ask user for confirmation before proceeding with a step"""
        Logger.step(f"Execute: {step_name}")

        if commands:
            mode_prefix = "DRY RUN - " if self.config.dry_run else ""
            Logger.info(f"{mode_prefix}Commands that will be executed:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {Colors.CYAN}{i}.{Colors.NC} {cmd}")
            print()

        if self.config.dry_run:
            Logger.warn(f"DRY RUN: {step_name}")
            return True

        response = input(f"{Colors.YELLOW}Proceed? (Y/n): {Colors.NC}").strip().lower()
        return response in ['', 'y', 'yes']

    def display_summary(self):
        """Display release summary"""
        project_config = self.config.project_config

        Logger.bold("\n" + "="*60)
        Logger.bold("ZhiJun IO RELEASE")
        Logger.bold("="*60)
        Logger.info(f"Project: {self.config.project_name}")
        Logger.info(f"Description: {project_config['description']}")
        Logger.info(f"Repository: {self.config.repo}")
        Logger.info(f"Target Version: {self.config.target_version}")
        Logger.info(f"Next Dev Version: {self.config.next_dev_version} (passed to the workflow)")
        Logger.info(f"Tag: {self.config.tag_name} (created by the workflow)")
        Logger.info(f"Workspace: {self.config.workspace_dir}")
        Logger.info(f"Dry Run: {self.config.dry_run}")
        Logger.bold("="*60 + "\n")

    def setup_workspace(self) -> bool:
        """Set up the workspace with fresh checkout"""
        Logger.step("Setting up workspace")

        self.git_helper = GitHelper(self.config.workspace_dir, self.config)

        if not self.git_helper.clone_repository():
            return False

        self.maven_helper = MavenHelper(self.config.workspace_dir, self.config)
        self.github_helper = GitHubActionsHelper(self.config)

        # Check GitHub CLI availability
        if not self.github_helper.is_gh_available():
            Logger.warn("GitHub CLI is not authenticated - run `gh auth login` to allow the release trigger")

        # Display current version
        current_version = self.git_helper.get_current_version()
        if current_version:
            Logger.info(f"Current version: {current_version}")

        return True

    def execute(self) -> bool:
        """Execute the release workflow"""
        self.display_summary()

        steps = [
            ("Setup workspace", self._setup_workspace, [
                f"git clone https://github.com/{self.config.repo}.git {self.config.workspace_dir}",
            ]),
            ("Set release version", self._set_version, [
                f"./mvnw versions:set -DnewVersion={self.config.target_version} -DgenerateBackupPoms=false",
            ]),
            ("Verify no SNAPSHOT dependencies", self._verify_no_snapshots, [
                "grep -rnE --include=pom.xml --exclude-dir=target '<(version|*.version)>[^<]*SNAPSHOT' .",
            ]),
            ("Build and verify", self._build, [
                "./mvnw clean package -Dmaven.javadoc.skip=true -DskipTests -B",
            ]),
        ]

        if self.config.trigger_workflow:
            steps.append(("Trigger GitHub release workflow", self._trigger_workflow, [
                f"gh workflow run {RELEASE_WORKFLOW} --repo {self.config.repo}"
                f" -f version={self.config.target_version}"
                f" -f next-version={self.config.next_dev_version}",
            ]))

        completed_steps = []

        for step_name, step_func, commands in steps:
            if not self.confirm_step(step_name, commands):
                Logger.warn("Release cancelled by user")
                return False

            try:
                if not step_func():
                    Logger.error(f"Step failed: {step_name}")
                    self.save_state("failed", completed_steps)
                    return False
                Logger.success(f"Completed: {step_name}")
                completed_steps.append(step_name)
            except Exception as e:
                Logger.error(f"Step failed with exception: {step_name} - {e}")
                self.save_state("failed", completed_steps)
                return False

        self.save_state("completed", completed_steps)

        Logger.bold(f"\n{'='*60}")
        Logger.bold("RELEASE COMPLETED SUCCESSFULLY!")
        Logger.bold(f"{'='*60}")
        Logger.info(f"Project: {self.config.project_name}")
        Logger.info(f"Version: {self.config.target_version}")

        if self.config.trigger_workflow:
            Logger.info("\nPreflight finished. GitHub Actions now owns the release:")
            Logger.info(f"  versions:set {self.config.target_version} -> deploy -> commit -> tag {self.config.tag_name}")
            Logger.info(f"Monitor at: https://github.com/{self.config.repo}/actions")
        else:
            Logger.info("\nNext steps:")
            Logger.info(f"1. Trigger {RELEASE_WORKFLOW} on GitHub with version={self.config.target_version}")
            Logger.info(f"2. Monitor Maven Central deployment")

        return True

    def _setup_workspace(self) -> bool:
        return self.setup_workspace()

    def _set_version(self) -> bool:
        return self.maven_helper.set_version(self.config.target_version)

    def _verify_no_snapshots(self) -> bool:
        return self.maven_helper.check_for_snapshots()

    def _build(self) -> bool:
        return self.maven_helper.fast_build()

    def _trigger_workflow(self) -> bool:
        if not self.github_helper.is_gh_available():
            Logger.warn("Skipping workflow trigger - GitHub CLI not available")
            return True
        return self.github_helper.trigger_release_workflow()


def main():
    parser = argparse.ArgumentParser(
        description="ZhiJun IO Release Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s rose-parent 0.0.2 --dry-run

Available Projects:
    """ + "\n    ".join(f"{name}: {config['description']}"
                        for name, config in PROJECTS.items())
    )

    parser.add_argument('project', choices=list(PROJECTS.keys()),
                       help='Project to release')
    parser.add_argument('version', help='Target version (e.g., 0.0.1)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview commands without executing')
    parser.add_argument('--no-workflow', action='store_true',
                       help='Skip triggering GitHub Actions workflow')

    args = parser.parse_args()

    try:
        config = ReleaseConfig(
            script_dir=Path(__file__).parent.resolve(),
            project_name=args.project,
            target_version=args.version,
            dry_run=args.dry_run,
            trigger_workflow=not args.no_workflow,
        )

        workflow = ReleaseWorkflow(config)
        success = workflow.execute()

        sys.exit(0 if success else 1)

    except ValueError as e:
        Logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        Logger.warn("\nRelease cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
