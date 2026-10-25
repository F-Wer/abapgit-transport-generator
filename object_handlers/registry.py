"""Dispatch registry for object-specific source/metadata collectors."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Type

from object_handlers.acid import collect_acid_sources
from object_handlers.apis import collect_apis_sources
from object_handlers.aplo import collect_aplo_sources
from object_handlers.aqbg import collect_aqbg_sources
from object_handlers.aqqu import collect_aqqu_sources
from object_handlers.aqsg import collect_aqsg_sources
from object_handlers.asfc import collect_asfc_sources
from object_handlers.auth import collect_auth_sources
from object_handlers.avar import collect_avar_sources
from object_handlers.avas import collect_avas_sources
from object_handlers.char import collect_char_sources
from object_handlers.amsd import collect_amsd_sources
from object_handlers.clas import collect_clas_sources
from object_handlers.devc import collect_devc_sources
from object_handlers.doma import collect_doma_sources
from object_handlers.dtel import collect_dtel_sources
from object_handlers.enho import collect_enho_sources
from object_handlers.enqu import collect_enqu_sources
from object_handlers.fugr import collect_fugr_sources
from object_handlers.intf import collect_intf_sources
from object_handlers.msag import collect_msag_sources
from object_handlers.nrob import collect_nrob_sources
from object_handlers.para import collect_para_sources
from object_handlers.susc import collect_susc_sources
from object_handlers.sucu import collect_sucu_sources
from object_handlers.sppf import collect_sppf_sources
from object_handlers.splo import collect_splo_sources
from object_handlers.suso import collect_suso_sources
from object_handlers.cus0 import collect_cus0_sources
from object_handlers.cus2 import collect_cus2_sources
from object_handlers.cus1 import collect_cus1_sources
from object_handlers.pers import collect_pers_sources
from object_handlers.scvi import collect_scvi_sources
from object_handlers.prog import collect_prog_sources
from object_handlers.otgr import collect_otgr_sources
from object_handlers.pinf import collect_pinf_sources
from object_handlers.prag import collect_prag_sources
from object_handlers.sfpf import collect_sfpf_sources
from object_handlers.sfpi import collect_sfpi_sources
from object_handlers.shlp import collect_shlp_sources
from object_handlers.sicf import collect_sicf_sources
from object_handlers.tabl import collect_tabl_sources
from object_handlers.tobj import collect_tobj_sources
from object_handlers.tran import collect_tran_sources
from object_handlers.type import collect_type_sources
from object_handlers.ttyp import collect_ttyp_sources
from object_handlers.view import collect_view_sources
from object_handlers.xslt import collect_xslt_sources


@dataclass(frozen=True)
class CollectorContext:
    acid_source_set_type: Type[dict]
    apis_source_set_type: Type[dict]
    aplo_source_set_type: Type[dict]
    aqbg_source_set_type: Type[dict]
    aqqu_source_set_type: Type[dict]
    aqsg_source_set_type: Type[dict]
    asfc_source_set_type: Type[dict]
    auth_source_set_type: Type[dict]
    avar_source_set_type: Type[dict]
    avas_source_set_type: Type[dict]
    char_source_set_type: Type[dict]
    amsd_source_set_type: Type[dict]
    build_repos_key: Callable[[str, str, str], str]
    make_enho_master_include_source: Callable[[str, dict], str]
    make_type_pool_boilerplate: Callable[[str], str]
    devc_source_set_type: Type[dict]
    enqu_source_set_type: Type[dict]
    msag_source_set_type: Type[dict]
    sicf_source_set_type: Type[dict]
    source_set_type: Type[dict]
    tabl_source_set_type: Type[dict]
    view_source_set_type: Type[dict]


def collect_object_sources(src_dir: Path, obj_type: str, obj_name: str,
                           context: CollectorContext) -> dict[str, str]:
    """Dispatch source/metadata collection to the handler for `obj_type`."""
    safe = obj_name.replace("/", "#").lower()

    source_collectors = {
        "PROG": collect_prog_sources,
        "CLAS": collect_clas_sources,
        "INTF": collect_intf_sources,
    }
    source_collector = source_collectors.get(obj_type)
    if source_collector is not None:
        return source_collector(src_dir, obj_name, safe, context.build_repos_key)

    if obj_type == "FUGR":
        return collect_fugr_sources(
            src_dir, obj_name, safe, context.build_repos_key,
            context.source_set_type)
    if obj_type == "ACID":
        return collect_acid_sources(
            src_dir, obj_name, safe, context.acid_source_set_type)
    if obj_type == "APIS":
        return collect_apis_sources(
            src_dir, obj_name, safe, context.apis_source_set_type)
    if obj_type == "APLO":
        return collect_aplo_sources(src_dir, obj_name, safe, context.aplo_source_set_type)
    if obj_type == "AQBG":
        return collect_aqbg_sources(src_dir, obj_name, safe, context.aqbg_source_set_type)
    if obj_type == "AQQU":
        return collect_aqqu_sources(src_dir, obj_name, safe, context.aqqu_source_set_type)
    if obj_type == "AQSG":
        return collect_aqsg_sources(src_dir, obj_name, safe, context.aqsg_source_set_type)
    if obj_type == "ASFC":
        return collect_asfc_sources(src_dir, obj_name, safe, context.asfc_source_set_type)
    if obj_type == "AUTH":
        return collect_auth_sources(src_dir, obj_name, safe, context.auth_source_set_type)
    if obj_type == "AVAR":
        return collect_avar_sources(src_dir, obj_name, safe, context.avar_source_set_type)
    if obj_type == "AVAS":
        return collect_avas_sources(src_dir, obj_name, safe, context.avas_source_set_type)
    if obj_type == "CHAR":
        return collect_char_sources(src_dir, obj_name, safe, context.char_source_set_type)
    if obj_type == "AMSD":
        return collect_amsd_sources(src_dir, obj_name, safe, context.amsd_source_set_type)
    if obj_type == "MSAG":
        return collect_msag_sources(
            src_dir, obj_name, safe, context.msag_source_set_type)
    if obj_type == "DTEL":
        return collect_dtel_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "TABL":
        return collect_tabl_sources(
            src_dir, obj_name, safe, context.tabl_source_set_type)
    if obj_type == "TTYP":
        return collect_ttyp_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "DOMA":
        return collect_doma_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "TRAN":
        return collect_tran_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "TOBJ":
        return collect_tobj_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "VIEW":
        return collect_view_sources(
            src_dir, obj_name, safe, context.view_source_set_type)
    if obj_type == "SHLP":
        return collect_shlp_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SICF":
        return collect_sicf_sources(
            src_dir, obj_name, safe, context.sicf_source_set_type)
    if obj_type == "XSLT":
        return collect_xslt_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "ENQU":
        return collect_enqu_sources(
            src_dir, obj_name, safe, context.enqu_source_set_type)
    if obj_type == "TYPE":
        return collect_type_sources(
            src_dir, obj_name, safe, context.build_repos_key,
            context.make_type_pool_boilerplate, context.source_set_type)
    if obj_type == "SFPF":
        return collect_sfpf_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SFPI":
        return collect_sfpi_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "PRAG":
        return collect_prag_sources(
            src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "OTGR":
        return collect_otgr_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "PINF":
        return collect_pinf_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "NROB":
        return collect_nrob_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "PARA":
        return collect_para_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SUSC":
        return collect_susc_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SUCU":
        return collect_sucu_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SPPF":
        return collect_sppf_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SPLO":
        return collect_splo_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SUSO":
        return collect_suso_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "CUS0":
        return collect_cus0_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "CUS2":
        return collect_cus2_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "CUS1":
        return collect_cus1_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "PERS":
        return collect_pers_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "SCVI":
        return collect_scvi_sources(src_dir, obj_name, safe, context.source_set_type)
    if obj_type == "DEVC":
        return collect_devc_sources(
            src_dir, obj_name, safe, context.devc_source_set_type)
    if obj_type == "ENHO":
        return collect_enho_sources(
            src_dir, obj_name, safe, context.build_repos_key,
            context.make_enho_master_include_source,
            context.source_set_type)

    return {}
