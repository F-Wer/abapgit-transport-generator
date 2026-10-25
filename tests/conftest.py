"""Skip template-backed tests when no template directory is available.

Templates are exports of real systems and are never shipped, so a fresh
checkout has none. Tests marked ``templates`` run only when
``ABAPGIT_TRANSPORT_TEMPLATES`` (or the bundled default directory) holds a
valid ``templates.json``; everything else always runs.
"""

import pytest

from transport_templates import ENV_VAR, TemplateError, load_manifest, template_dir


def _templates_available() -> bool:
    try:
        load_manifest(template_dir())
    except TemplateError:
        return False
    return True


def pytest_collection_modifyitems(config, items):
    if _templates_available():
        return
    skip = pytest.mark.skip(
        reason=f"needs templates: no templates.json in {template_dir()}; set {ENV_VAR}")
    for item in items:
        if "templates" in item.keywords:
            item.add_marker(skip)
