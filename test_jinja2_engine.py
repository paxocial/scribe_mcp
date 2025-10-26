#!/usr/bin/env python3
"""Test script for Jinja2 template engine implementation."""

import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

def test_template_engine():
    """Test the Jinja2 template engine functionality."""
    print("🧪 Testing Jinja2 Template Engine")
    print("=" * 50)

    # Test 1: Basic template rendering with custom variables
    print("\n1. Testing custom template rendering...")
    try:
        engine = Jinja2TemplateEngine(
            project_root=Path("/home/austin/projects/Scribe"),
            project_name="scribe_doc_management_1",
            security_mode="sandbox"
        )

        # Render the custom project header template
        result = engine.render_template("project_header.md")
        print("✅ Custom template rendering successful!")
        print("   Length:", len(result), "characters")
        print("   Contains project name:", "scribe_doc_management_1" in result)
        print("   Contains organization:", "Claude Code" in result)

        feature_count = len([f for f in result.split('\n') if f.strip().startswith('- ')])
        print("   Contains features:", feature_count >= 5)

    except Exception as e:
        print(f"❌ Custom template rendering failed: {e}")
        return False

    # Test 2: Built-in template rendering
    print("\n2. Testing built-in template rendering...")
    try:
        result = engine.render_template("directory_structure.md")
        print("✅ Built-in template rendering successful!")
        print("   Length:", len(result), "characters")
        print("   Contains project slug:", "scribe_doc_management_1" in result)

    except Exception as e:
        print(f"❌ Built-in template rendering failed: {e}")
        return False

    # Test 3: Template validation
    print("\n3. Testing template validation...")
    try:
        validation = engine.validate_template("project_header.md")
        if validation["valid"]:
            print("✅ Template validation passed!")
            print("   Line count:", validation["line_count"])
            print("   Size:", validation["size_bytes"], "bytes")
        else:
            print("❌ Template validation failed:")
            for error in validation["errors"]:
                print(f"   - {error}")
            return False

    except Exception as e:
        print(f"❌ Template validation failed: {e}")
        return False

    # Test 4: List available templates
    print("\n4. Testing template listing...")
    try:
        templates = engine.list_templates()
        print("✅ Template listing successful!")
        print("   Found templates:", len(templates))
        for template in templates:
            print(f"   - {template}")

    except Exception as e:
        print(f"❌ Template listing failed: {e}")
        return False

    # Test 5: Template info
    print("\n5. Testing template info...")
    try:
        info = engine.get_template_info("project_header.md")
        if info["found"]:
            print("✅ Template info retrieval successful!")
            print("   Type:", info["template_type"])
            print("   Path:", info["path"])
            print("   Size:", info["size_bytes"], "bytes")
        else:
            print("❌ Template not found")

    except Exception as e:
        print(f"❌ Template info retrieval failed: {e}")
        return False

    # Test 6: String rendering (content processing)
    print("\n6. Testing string rendering...")
    try:
        template_string = "Hello {{ project_name }}! Generated at {{ timestamp }} by {{ author }}."
        result = engine.render_string(template_string)
        print("✅ String rendering successful!")
        print("   Result:", result.strip())

    except Exception as e:
        print(f"❌ String rendering failed: {e}")
        return False

    print("\n" + "=" * 50)
    print("🎉 All Jinja2 template engine tests passed!")
    return True

if __name__ == "__main__":
    success = test_template_engine()
    sys.exit(0 if success else 1)