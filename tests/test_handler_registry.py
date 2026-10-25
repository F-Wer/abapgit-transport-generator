from pathlib import Path

import pytest

from object_handlers.registry import CollectorContext, collect_object_sources


class SourceSet(dict):
    pass


def build_repos_key(*parts: str) -> str:
    return "|".join(parts)


def make_enho_master_include_source(*_args) -> str:
    return ""


def make_type_pool_boilerplate(*_args) -> str:
    return ""


@pytest.fixture
def context() -> CollectorContext:
    return CollectorContext(
        acid_source_set_type=SourceSet,
        apis_source_set_type=SourceSet,
        aplo_source_set_type=SourceSet,
        aqbg_source_set_type=SourceSet,
        aqqu_source_set_type=SourceSet,
        aqsg_source_set_type=SourceSet,
        asfc_source_set_type=SourceSet,
        auth_source_set_type=SourceSet,
        avar_source_set_type=SourceSet,
        avas_source_set_type=SourceSet,
        char_source_set_type=SourceSet,
        amsd_source_set_type=SourceSet,
        build_repos_key=build_repos_key,
        make_enho_master_include_source=make_enho_master_include_source,
        make_type_pool_boilerplate=make_type_pool_boilerplate,
        devc_source_set_type=SourceSet,
        enqu_source_set_type=SourceSet,
        msag_source_set_type=SourceSet,
        sicf_source_set_type=SourceSet,
        source_set_type=SourceSet,
        tabl_source_set_type=SourceSet,
        view_source_set_type=SourceSet,
    )


@pytest.mark.parametrize(
    "object_type",
    [
        "PROG", "CLAS", "INTF", "FUGR", "ACID", "APIS", "APLO", "AQBG",
        "AQQU", "AQSG", "ASFC", "AUTH", "AVAR", "AVAS", "CHAR", "AMSD",
        "MSAG", "DTEL", "TABL", "TTYP", "DOMA", "TRAN", "TOBJ", "VIEW",
        "SHLP", "SICF", "XSLT", "ENQU", "TYPE", "SFPF", "SFPI", "DEVC",
        "ENHO",
    ],
)
def test_dispatch_handles_missing_source_for_every_supported_type(
    tmp_path: Path, context: CollectorContext, object_type: str
) -> None:
    # DDTYPET limits type-pool names to five characters.
    object_name = "ZDEMO" if object_type == "TYPE" else "Z_TEST"
    result = collect_object_sources(tmp_path, object_type, object_name, context)

    assert isinstance(result, (dict, SourceSet))


def test_dispatch_returns_empty_mapping_for_unknown_type(
    tmp_path: Path, context: CollectorContext
) -> None:
    assert collect_object_sources(tmp_path, "UNKNOWN", "Z_TEST", context) == {}
