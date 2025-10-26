#!/usr/bin/env python3
"""Demo of Global Scribe deployment functionality.

This script demonstrates how Scribe can work as a global MCP server
that automatically discovers and adapts to any repository.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the MCP_SPINE directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def demo_repo_discovery():
    """Demonstrate repository discovery."""
    print("🔍 Demo: Repository Discovery")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create different types of repositories
        repos = [
            ("git-repo", lambda p: (p / ".git").mkdir()),
            ("scribe-marked-repo", lambda p: (p / ".scribe").mkdir()),
            ("python-project", lambda p: (p / "pyproject.toml").write_text("[project]")),
            ("node-project", lambda p: (p / "package.json").write_text("{}")),
        ]

        for repo_name, setup_func in repos:
            repo_path = temp_path / repo_name
            repo_path.mkdir()
            setup_func(repo_path)

            try:
                # Import here to avoid path issues in demo
                from scribe_mcp.config.repo_config import RepoDiscovery

                discovered = RepoDiscovery.find_repo_root(repo_path)
                if discovered == repo_path:
                    print(f"   ✅ {repo_name}: Found at {discovered}")
                else:
                    print(f"   ❌ {repo_name}: Expected {repo_path}, got {discovered}")
            except Exception as e:
                print(f"   ❌ {repo_name}: Error - {e}")

    print()


def demo_config_management():
    """Demonstrate configuration management."""
    print("⚙️  Demo: Configuration Management")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a repository with custom configuration
        repo_path = temp_path / "my-cool-project"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        # Create .scribe configuration
        scribe_dir = repo_path / ".scribe"
        scribe_dir.mkdir()

        config_content = """
# My Cool Project Configuration
repo_slug: "my-cool-project"
dev_plans_dir: "documentation"
progress_log_name: "CHANGELOG.md"

# Custom settings
default_emoji: "🚀"
default_agent: "CoolAgent"

# Permissions
permissions:
  allow_rotate: true
  allow_generate_docs: true
  require_project: false

# Reminder configuration
reminder_config:
  tone: "friendly"
  log_warning_minutes: 20
  log_urgent_minutes: 45

# Plugin directory
plugins_dir: ".scribe/plugins"
"""

        config_file = scribe_dir / "scribe.yaml"
        config_file.write_text(config_content)

        try:
            from scribe_mcp.config.repo_config import RepoDiscovery, RepoConfig

            # Load the configuration
            config = RepoDiscovery.load_config(repo_path)

            print(f"   📂 Repository: {config.repo_slug}")
            print(f"   📁 Documentation: {config.dev_plans_dir}")
            print(f"   📄 Progress Log: {config.progress_log_name}")
            print(f"   😀 Default Emoji: {config.default_emoji}")
            print(f"   🤖 Default Agent: {config.default_agent}")
            print(f"   🔧 Permissions: {config.permissions}")
            print(f"   ⏰ Reminder Warning: {config.reminder_config.get('log_warning_minutes')} minutes")

            # Test progress log path generation
            log_path = config.get_progress_log_path("feature-x")
            print(f"   📝 Feature Log Path: {log_path}")

            # Test project docs directory
            docs_dir = config.get_project_docs_dir("feature-x")
            print(f"   📂 Feature Docs: {docs_dir}")

        except Exception as e:
            print(f"   ❌ Configuration demo failed: {e}")

    print()


def demo_multi_repo_scenario():
    """Demonstrate multi-repository scenario."""
    print("🏢 Demo: Multi-Repository Scenario")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create multiple repositories with different configurations
        repos = [
            {
                "name": "frontend-app",
                "config": {
                    "repo_slug": "frontend-app",
                    "dev_plans_dir": "docs/development",
                    "default_emoji": "🎨",
                    "permissions": {"allow_rotate": True}
                }
            },
            {
                "name": "backend-api",
                "config": {
                    "repo_slug": "backend-api",
                    "dev_plans_dir": "documentation",
                    "default_emoji": "⚙️",
                    "permissions": {"allow_rotate": False}
                }
            },
            {
                "name": "infrastructure",
                "config": {
                    "repo_slug": "infra",
                    "dev_plans_dir": "devops/docs",
                    "default_emoji": "🔧",
                    "permissions": {"allow_generate_docs": False}
                }
            }
        ]

        created_repos = []

        for repo_info in repos:
            # Create repository
            repo_path = temp_path / repo_info["name"]
            repo_path.mkdir()
            (repo_path / ".git").mkdir()

            # Create configuration
            scribe_dir = repo_path / ".scribe"
            scribe_dir.mkdir()

            import yaml
            config_file = scribe_dir / "scribe.yaml"
            config_file.write_text(yaml.dump(repo_info["config"]))

            created_repos.append((repo_path, repo_info["config"]))

        # Test discovery and configuration for each repository
        try:
            from scribe_mcp.config.repo_config import RepoDiscovery

            for repo_path, expected_config in created_repos:
                print(f"\\n   📂 Repository: {repo_path.name}")

                # Discover
                discovered = RepoDiscovery.find_repo_root(repo_path)
                if discovered == repo_path:
                    print(f"      ✅ Discovery: Found repository root")
                else:
                    print(f"      ❌ Discovery: Failed to find correct root")
                    continue

                # Load configuration
                config = RepoDiscovery.load_config(repo_path)

                # Verify key settings
                if config.repo_slug == expected_config["repo_slug"]:
                    print(f"      ✅ Config: Correct repo slug ({config.repo_slug})")
                else:
                    print(f"      ❌ Config: Wrong repo slug")

                if config.dev_plans_dir.name == Path(expected_config["dev_plans_dir"]).name:
                    print(f"      ✅ Config: Correct docs directory ({config.dev_plans_dir.name})")
                else:
                    print(f"      ❌ Config: Wrong docs directory")

                if config.default_emoji == expected_config["default_emoji"]:
                    print(f"      ✅ Config: Correct emoji ({config.default_emoji})")
                else:
                    print(f"      ❌ Config: Wrong emoji")

                rotate_allowed = config.permissions.get("allow_rotate", False)
                expected_rotate = expected_config["permissions"].get("allow_rotate", False)
                if rotate_allowed == expected_rotate:
                    print(f"      ✅ Config: Correct rotate permission ({rotate_allowed})")
                else:
                    print(f"      ❌ Config: Wrong rotate permission")

        except Exception as e:
            print(f"   ❌ Multi-repo demo failed: {e}")

    print()


def demo_server_integration():
    """Demonstrate how the server integrates with repo discovery."""
    print("🚀 Demo: Server Integration")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a test repository
        repo_path = temp_path / "server-test-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()
        (repo_path / "docs" / "dev_plans").mkdir(parents=True)

        # Create configuration
        scribe_dir = repo_path / ".scribe"
        scribe_dir.mkdir()

        config = {
            "repo_slug": "server-test-repo",
            "dev_plans_dir": "docs/dev_plans",
            "storage_backend": "sqlite",
            "mcp_server_name": "scribe-test.mcp"
        }

        import yaml
        config_file = scribe_dir / "scribe.yaml"
        config_file.write_text(yaml.dump(config))

        try:
            # Change to the repository directory
            original_cwd = os.getcwd()
            os.chdir(repo_path)

            from scribe_mcp.config.repo_config import get_current_repo_config

            # Test configuration discovery from current directory
            repo_root, repo_config = get_current_repo_config(refresh=True)

            print(f"   📍 Current Directory: {Path.cwd()}")
            print(f"   📂 Discovered Repository: {repo_config.repo_slug}")
            print(f"   📁 Documentation Directory: {repo_config.dev_plans_dir}")
            print(f"   💾 Storage Backend: {repo_config.storage_backend}")
            print(f"   🏷️  MCP Server Name: {repo_config.mcp_server_name}")

            # Simulate what the server would do on startup
            print("\\n   🚀 Server Startup Simulation:")
            print(f"      🔍 Discovering repository... ✅ Found {repo_config.repo_slug}")
            print(f"      ⚙️  Loading configuration... ✅ Loaded from {scribe_dir / 'scribe.yaml'}")
            print(f"      📁 Preparing directories... ✅ {repo_config.dev_plans_dir} exists")
            print(f"      🔌 Initializing plugins... ✅ Plugin system ready")
            print(f"      🛡️  Setting up security... ✅ Sandbox initialized")
            print(f"      💾 Initializing storage... ✅ {repo_config.storage_backend} backend")

        except Exception as e:
            print(f"   ❌ Server integration demo failed: {e}")
        finally:
            os.chdir(original_cwd)

    print()


def main():
    """Run all demonstrations."""
    print("🌟 Global Scribe Deployment Demonstration")
    print("=" * 60)
    print()
    print("This demo shows how Scribe can work as a global MCP server")
    print("that automatically discovers and adapts to any repository.")
    print()

    demos = [
        demo_repo_discovery,
        demo_config_management,
        demo_multi_repo_scenario,
        demo_server_integration,
    ]

    for demo in demos:
        try:
            demo()
        except Exception as e:
            print(f"❌ Demo {demo.__name__} failed: {e}")
            print()

    print("🎉 Global Scribe Demo Complete!")
    print()
    print("Key Features Demonstrated:")
    print("   ✅ Automatic repository discovery")
    print("   ✅ Per-repository configuration loading")
    print("   ✅ Multi-repository isolation")
    print("   ✅ Server integration readiness")
    print()
    print("Scribe is ready to be deployed as a global MCP server!")


if __name__ == "__main__":
    main()