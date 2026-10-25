"""Template-record orchestration for generated SAP transports.

Dependencies remain injected by the compatibility facade while the existing
object-specific regenerators are extracted incrementally.
"""

from __future__ import annotations

import struct

from sap_transport_records import Record
from transport_record_renames import RenameRule


def configure_engine_helpers(**helpers) -> None:
    """Inject the existing helper boundary without importing the facade."""
    globals().update(helpers)




def _msag_metadata(sources) -> dict:
    return {
        "masterlang": getattr(sources, "msag_masterlang", "") or "",
        "stext": getattr(sources, "msag_stext", "") or "",
        "messages": list(getattr(sources, "msag_messages", None) or []),
    }


OBJECT_REGENERATORS = {
    "MSAG": lambda records, name, rule, sources, meta: _regenerate_msag_rows(records, name, _msag_metadata(sources)),
    "TABL": lambda records, name, rule, sources, meta: _regenerate_tabl_rows(records, name, meta["tabl_meta"]),
    "TRAN": lambda records, name, rule, sources, meta: _regenerate_tran_tstcp(records, name, meta["tran_fields"].get("TSTCP")),
    "TOBJ": lambda records, name, rule, sources, meta: _regenerate_tobj_rows(records, name, meta["tobj_meta"]),
    "ENHO": lambda records, name, rule, sources, meta: (_regenerate_enho_badi_data_blob(records, name, rule, meta["enho_meta"]) if meta["enho_meta"].get("tool") == "BADI_IMPL" else _regenerate_enho_data_blob(records, name, rule, meta["enho_meta"])),
    "VIEW": lambda records, name, rule, sources, meta: _regenerate_view_rows(records, name, meta["view_meta"]),
    "DOMA": lambda records, name, rule, sources, meta: _regenerate_doma_rows(records, name, meta["doma_meta"]),
    "ENQU": lambda records, name, rule, sources, meta: _regenerate_enqu_rows(records, name, meta["enqu_meta"]),
    "SHLP": lambda records, name, rule, sources, meta: _regenerate_shlp_rows(records, name, meta["shlp_meta"]),
    "XSLT": lambda records, name, rule, sources, meta: _regenerate_xslt_rows(records, name, meta["xslt_meta"]),
    "SICF": lambda records, name, rule, sources, meta: _regenerate_sicf_rows(records, name, meta["sicf_meta"]),
    "DEVC": lambda records, name, rule, sources, meta: regenerate_devc_rows(records, name, meta["devc_meta"]),
    "ACID": lambda records, name, rule, sources, meta: _regenerate_acid_rows(records, name, meta["acid_meta"]),
    "APIS": lambda records, name, rule, sources, meta: _regenerate_apis_rows(records, name, meta["apis_meta"]),
    "AMSD": lambda records, name, rule, sources, meta: _regenerate_amsd_rows(records, meta["amsd_meta"]),
    "APLO": lambda records, name, rule, sources, meta: _regenerate_aplo_rows(records, meta["aplo_meta"]),
    "AQBG": lambda records, name, rule, sources, meta: _regenerate_aqbg_rows(records, meta["aqbg_meta"]),
    "AQQU": lambda records, name, rule, sources, meta: _regenerate_aqqu_rows(records, meta["aqqu_meta"]),
    "AQSG": lambda records, name, rule, sources, meta: _regenerate_aqsg_rows(records, meta["aqsg_meta"]),
    "ASFC": lambda records, name, rule, sources, meta: _regenerate_asfc_rows(records, meta["asfc_meta"]),
    "AUTH": lambda records, name, rule, sources, meta: _regenerate_auth_rows(records, meta["auth_meta"]),
    "AVAR": lambda records, name, rule, sources, meta: _regenerate_avar_rows(records, name, meta["avar_meta"]),
    "AVAS": lambda records, name, rule, sources, meta: _regenerate_avas_rows(records, name, meta["avas_meta"]),
    "CHAR": lambda records, name, rule, sources, meta: _regenerate_char_rows(records, meta["char_meta"]),
}


def apply_object_regenerator(obj_type, records, obj_name, rule, sources, metadata):
    handler = OBJECT_REGENERATORS.get(obj_type)
    return handler(records, obj_name, rule, sources, metadata) if handler else records


def process_template_records(records, obj_type: str, obj_name: str,
                              sources: dict[str, str],
                              rule: RenameRule, ldb: str = "",
                              package: str = "", author: str = "") -> list:
    """
    Apply a rename rule to a template's record list and inject the object's
    source code into its REPOS blocks. Returns the new record list.

    Template blocks we have no real content for are dropped, not shipped:
    renamed template source/text would corrupt the target object.
    """
    # Map sources to REPOS includes
    include_map, cm_methods = _map_source_to_includes(obj_type, obj_name,
                                                      sources)
    sources_by_key = {}
    for key, suffix, text in include_map:
        sources_by_key[key.upper()] = (key, suffix, text)

    # FUGR: derive the function-module mapping (template FMs -> repo FMs).
    # The FM list comes from scanning the repo's sources; the template's
    # own list comes from its TFDIR keys. See _map_function_modules for
    # the pairing rule.
    fm_pairs = []
    fm_short_texts = {}
    fm_u_numbers = {}
    mapped_tmpl_fms = set()
    cloned_fms = []
    tmpl_fms = []
    fm_blocks = {}
    fugr_areat = getattr(sources, "fugr_areat", "") or ""
    dtel_fields = getattr(sources, "dtel_fields", None) or {}
    if dtel_fields:
        print(f"  DTEL fields from .dtel.xml: {sorted(dtel_fields)}")
    tabl_meta = getattr(sources, "tabl_meta", None) or {}
    if tabl_meta.get("fields"):
        print(f"  TABL fields from .tabl.xml: "
              f"{[f['FIELDNAME'] for f in tabl_meta['fields']]}")
    ttyp_fields = getattr(sources, "ttyp_fields", None) or {}
    if ttyp_fields:
        print(f"  TTYP fields from .ttyp.xml: {sorted(ttyp_fields)}")
    tran_fields = getattr(sources, "tran_fields", None) or {}
    if tran_fields:
        print(f"  TRAN fields from .tran.xml: "
              f"{ {k: sorted(v) for k, v in tran_fields.items() if v} }")
    tobj_meta = getattr(sources, "tobj_meta", None) or {}
    if tobj_meta.get("objh"):
        print(f"  TOBJ fields from .tobj.xml: OBJH={sorted(tobj_meta['objh'])} "
              f"OBJS_rows={len(tobj_meta.get('objs_rows') or [])}")
    enho_meta = getattr(sources, "enho_meta", None) or {}
    if enho_meta.get("methods"):
        print(f"  ENHO fields from .enho.xml: TOOL={enho_meta.get('tool')!r} "
              f"CLASS={enho_meta.get('class')!r} "
              f"methods={[m['name'] for m in enho_meta['methods']]}")
    elif enho_meta.get("badi"):
        badi = enho_meta["badi"]
        print(f"  ENHO fields from .enho.xml: TOOL={enho_meta.get('tool')!r} "
              f"SPOT_NAME={badi.get('spot_name')!r} "
              f"BADI_NAME={badi.get('badi_name')!r} "
              f"filters={len(badi.get('filter_values') or [])}")
    view_meta = getattr(sources, "view_meta", None) or {}
    if view_meta.get("fields") or view_meta.get("tables"):
        print(f"  VIEW fields from .view.xml: "
              f"tables={[t.get('TABNAME') for t in view_meta.get('tables', [])]} "
              f"fields={[f.get('VIEWFIELD') for f in view_meta.get('fields', [])]}")
    doma_meta = getattr(sources, "doma_meta", None) or {}
    if doma_meta.get("header"):
        print(f"  DOMA fields from .doma.xml: {sorted(doma_meta['header'])} "
              f"values={len(doma_meta.get('values') or [])}")
    enqu_meta = getattr(sources, "enqu_meta", None) or {}
    if enqu_meta.get("fields") or enqu_meta.get("tables"):
        print(f"  ENQU fields from .enqu.xml: "
              f"tables={[t.get('TABNAME') for t in enqu_meta.get('tables', [])]} "
              f"fields={[f.get('VIEWFIELD') for f in enqu_meta.get('fields', [])]}")
    shlp_meta = getattr(sources, "shlp_meta", None) or {}
    if shlp_meta.get("header") or shlp_meta.get("fields"):
        print(f"  SHLP fields from .shlp.xml: {sorted(shlp_meta.get('header', {}))} "
              f"params={len(shlp_meta.get('fields') or [])} "
              f"submethods={len(shlp_meta.get('submethods') or [])} "
              f"mappings={len(shlp_meta.get('mappings') or [])}")
    xslt_meta = getattr(sources, "xslt_meta", None) or {}
    if xslt_meta.get("xsltdesc") or xslt_meta.get("source"):
        print(f"  XSLT fields from .xslt.xml: xsltdesc={xslt_meta.get('xsltdesc')!r} "
              f"langu={xslt_meta.get('langu')!r} "
              f"source_len={len(xslt_meta.get('source') or '')}")
    type_fields = getattr(sources, "type_meta", None) or {}
    if type_fields:
        print(f"  TYPE fields from .type.xml: {sorted(type_fields)}")
    sicf_meta = getattr(sources, "sicf_meta", None) or {}
    if sicf_meta.get("icf_name") or sicf_meta.get("handlers"):
        print(f"  SICF fields from .sicf.xml: ICF_NAME={sicf_meta.get('icf_name')!r} "
              f"URL={sicf_meta.get('url')!r} ")
    devc_meta = getattr(sources, "devc_meta", None) or {}
    if devc_meta.get("description"):
        print(f"  DEVC fields from .devc.xml: description={devc_meta.get('description')!r}")
    acid_meta = getattr(sources, "acid_meta", None) or {}
    if acid_meta.get("description"):
        print(f"  ACID fields from .acid.xml: description={acid_meta['description']!r}")
    apis_meta = getattr(sources, "apis_meta", None) or {}
    if apis_meta.get("header"):
        print(f"  APIS fields from .apis.xml: {sorted(apis_meta['header'])}")
    amsd_meta = getattr(sources, "amsd_meta", None) or {}
    aplo_meta = getattr(sources, "aplo_meta", None) or {}
    aqbg_meta = getattr(sources, "aqbg_meta", None) or {}
    aqqu_meta = getattr(sources, "aqqu_meta", None) or {}
    aqsg_meta = getattr(sources, "aqsg_meta", None) or {}
    asfc_meta = getattr(sources, "asfc_meta", None) or {}
    auth_meta = getattr(sources, "auth_meta", None) or {}
    avar_meta = getattr(sources, "avar_meta", None) or {}
    avas_meta = getattr(sources, "avas_meta", None) or {}
    char_meta = getattr(sources, "char_meta", None) or {}
    if obj_type == "FUGR":
        tmpl_fms = _template_function_modules(records)
        repo_fms = _extract_function_modules(sources)
        fugr_meta = list(getattr(sources, "fugr_functions", None) or [])
        meta_fms = [f for f, _ in fugr_meta]
        if repo_fms and meta_fms and repo_fms != meta_fms:
            print(f"  WARNING: FM list from sources {repo_fms} differs from "
                  f"the .fugr.xml FUNCTIONS list {meta_fms} "
                  f"(sources win)")
        fm_pairs, unmapped_tmpl, cloned_fms = _map_function_modules(
            tmpl_fms, repo_fms)
        mapped_tmpl_fms = {old for old, _ in fm_pairs}
        fm_short_texts = {fm: (st or _make_description(fm))
                          for fm, st in fugr_meta}
        for fm in repo_fms:
            fm_short_texts.setdefault(fm, _make_description(fm))
        for n, (fm, _) in enumerate(fugr_meta, start=1):
            fm_u_numbers[fm] = n
        for n, fm in enumerate(repo_fms, start=1):
            fm_u_numbers.setdefault(fm, n)
        if tmpl_fms:
            print(f"  Template FMs: {tmpl_fms}")
        print(f"  Repo FMs: {repo_fms}  ->  pairs {fm_pairs}"
              + (f", synthesized {cloned_fms}" if cloned_fms else ""))
        if unmapped_tmpl:
            print(f"  (dropping template FMs without repo match: "
                  f"{sorted(unmapped_tmpl)})")
        rule.fm_pairs = fm_pairs
        fm_blocks = _collect_fm_blocks(records, tmpl_fms)

    # The template's SEO member rows describe ITS members (e.g. the TEST
    # method) -- captured here so interfaces can regenerate them from the
    # real source afterwards.
    seo_templates = {}
    for table in ("SEOCOMPO", "SEOCOMPODF", "SEOCOMPOTX"):
        blk = _find_block(records, table)
        if blk and blk[1]:
            seo_templates[table] = records[blk[1][0]]
    seo_nametabs = _parse_nametabs(records)

    # Find the template's REPOS H and metadata records (as templates for
    # creating entirely new blocks if needed)
    template_repos_h = None
    template_repos_meta = None
    # FUGR: attribute row of the template's generated signature include
    # ($01, a system program) and of its function module include (U01).
    fugr_donor_meta = {}
    if obj_type == "FUGR":
        for i, rec in enumerate(records[:-1]):
            if (rec.rtype == "H" and b"ABAPREAD" in rec.payload[:20]
                    and len(records[i + 1].payload) == 628):
                key = rec.payload[48:].decode("latin-1").rstrip()
                for kind in ("$01", "U01"):
                    if key.endswith(kind):
                        fugr_donor_meta[kind[0]] = records[i + 1]
    for i, rec in enumerate(records):
        if rec.rtype == "H" and b"ABAPREAD" in rec.payload[:20]:
            template_repos_h = rec
            for j in range(i + 1, min(i + 5, len(records))):
                if (records[j].rtype == " " and
                        len(records[j].payload) == 628):
                    template_repos_meta = records[j]
                    break
            if template_repos_meta is not None:
                break

    # The template's method-include block (REPOS, action 00MMRG -- the CM001
    # of the template's TEST method). It supplies the H record + 628-byte
    # meta row shape for the generated CM### blocks.
    template_cm_h = None
    template_cm_meta = None
    for i, rec in enumerate(records):
        if (rec.rtype == "H" and b"ABAPREAD" in rec.payload[:20]
                and rec.payload[38:44] == b"00MMRG"):
            template_cm_h = rec
            if (i + 1 < len(records) and records[i + 1].rtype == " "
                    and len(records[i + 1].payload) == 628):
                template_cm_meta = records[i + 1]
            break

    # A CM### layout needs the template's method-include block shape. A
    # template without one degrades the class to the CI-only layout (the
    # whole implementation travels in CI) instead of failing.
    if (obj_type == "CLAS" and cm_methods and template_cm_h is None):
        print("  WARNING: template has no method-include block -- "
              "degrading to CI-only class layout")
        include_map, cm_methods = _map_source_to_includes(
            obj_type, obj_name, sources, mode="ci")
        sources_by_key = {}
        for key, suffix, text in include_map:
            sources_by_key[key.upper()] = (key, suffix, text)

    # Table layouts the transport carries with itself -- needed to rename
    # inside fixed-width rows without shifting the following fields.
    nametabs = _parse_nametabs(records)
    cur_fields = None   # layout of the block currently being walked

    # Build the new record list: process each record, replacing REPOS source
    # blocks where we have matching source
    new_records = []
    i = 0
    handled_keys = set()

    while i < len(records):
        rec = records[i]

        # ENHO's RAW long-value records (ENHHEADER-DATA, ENHOBJCONTRACT-
        # CONTRACTDATA, ENHLOG-TOOLLOGDATA) must NEVER go through the
        # generic per-record rename below: it is a plain, non-width-aware
        # substring replace across the WHOLE payload (fine for an ordinary
        # fixed-width row, but these are 20-70KB self-describing binary
        # records -- see ENHO_CLUSTER_FORMAT_PROGRESS.md), and it would
        # silently strip out the very content _regenerate_enho_data_blob
        # (called once, after this loop, on ENHHEADER specifically) needs to
        # find in order to do its OWN width-preserving field-level rewrite.
        # ENHOBJCONTRACT/ENHLOG are deliberately left as pristine template
        # boilerplate either way (see the same doc) -- passed through
        # completely unchanged here for exactly that reason.
        if obj_type == "ENHO" and rec.rtype == "R":
            new_records.append(rec)
            i += 1
            continue

        # ABAPREAD blocks (REPOS source, text pool, dynpro source) are only
        # kept when we have real content for the include -- otherwise the
        # whole block is dropped so renamed template content never ships.
        if rec.rtype == "H" and b"ABAPREAD" in rec.payload[:20]:
            table = rec.payload[8:38].decode("latin-1").rstrip()
            template_key = rec.payload[48:].decode("latin-1").rstrip()

            if table == "REPOS":
                renamed_key = _apply_rename_to_key(template_key, rule)
                renamed_key_upper = renamed_key.upper()
                meta_rec = None
                if (i + 1 < len(records) and records[i + 1].rtype == " "
                        and len(records[i + 1].payload) == 628):
                    meta_rec = _set_meta_ldb(
                        _replace_in_record(records[i + 1], rule), ldb)
                    if obj_type == "PROG":
                        meta_rec = _set_meta_subc(
                            meta_rec, getattr(sources, "prog_subc", "1"))

                # The template's method-include key packs
                # include+class+method behind the CM### suffix, so the
                # renamed key never equals the generated include key. Match
                # the include-name + suffix fields (first 60 chars) instead
                # -- the template's own CM001 block is then reused in place
                # for the first generated CM### include (its packed key is
                # rebuilt wholesale; see below).
                if (obj_type == "CLAS"
                        and renamed_key_upper[:60].rstrip() in cm_methods):
                    match_key = renamed_key_upper[:60].rstrip()
                else:
                    match_key = renamed_key_upper

                # A template block without the 628-byte attribute row is a
                # delete (e.g. the CLAS template's `00DEL ...CCAU`): writing
                # source rows under its DEL header ships nothing. Drop it and
                # let the include get a fresh REP block further down.
                if match_key in sources_by_key and meta_rec is not None:
                    # Replace the template block with the real source.
                    matched_key, matched_suffix, matched_source = \
                        sources_by_key[match_key]
                    handled_keys.add(match_key)
                    if obj_type == "CLAS" and match_key in cm_methods:
                        # A template method-include block (the template's
                        # own CM001) is reused for the generated CM###
                        # include. The key packs include+class+method, so
                        # it is rewritten wholesale -- the renamed template
                        # key would still claim the template's TEST method.
                        h_rec = _make_cm_h_record(
                            rec, rule, matched_suffix,
                            cm_methods[match_key])
                    else:
                        h_rec = _normalize_repos_key(
                            _replace_in_record(rec, rule))
                    if obj_type == "TYPE" and matched_source == "":
                        # A genuinely empty type-group body ships ZERO
                        # source rows (see the real type-group template: the TT
                        # include's REPOS block carries only the H record +
                        # 628-byte meta row, no source lines at all, COMMIT
                        # immediately after) -- _encode_source_lines("")
                        # would otherwise synthesize one spurious blank
                        # line.
                        i = _emit_repos_rows(new_records, records, i, h_rec,
                                             meta_rec, [])
                    else:
                        i = _emit_source_block(new_records, records, i, h_rec,
                                               meta_rec, matched_source)
                    continue

                if obj_type == "INTF" and renamed_key_upper.endswith("=IP"):
                    # Interface pool include: keep the block but regenerate
                    # the boilerplate so the include line points at the IU
                    # include under the object's real '=' padding.
                    h_rec = _normalize_repos_key(
                        _replace_in_record(rec, rule))
                    i = _emit_source_block(
                        new_records, records, i, h_rec, meta_rec,
                        _interface_pool_boilerplate(obj_name))
                    continue

                # Template include we have no source for (dummy includes,
                # method includes, ...) -- drop the whole block.
                i = _skip_block(records, i + 1)
                continue

            if table == "DOCUT%" and obj_type == "FUGR":
                # Documentation deletes -- pure 00DEL blocks, no content.
                # Group docs pack RE<SAPL<group>> (group rename handles
                # them); FM docs pack FU<FM><30>%/FX<FM><30>% (the FM
                # rename re-pads the 30-wide FM field). A template FM with
                # no repo match is dropped with its blocks (drop-unmatched).
                fm = _docut_key_fm(template_key)
                if fm is not None and fm not in mapped_tmpl_fms:
                    i = _skip_block(records, i + 1)
                    continue
                new_records.append(
                    _rename_h_key(rec, _replace_in_record(rec, rule), rule))
                i += 1
                while i < len(records) and records[i].rtype != "E":
                    new_records.append(records[i])
                    i += 1
                if i < len(records) and records[i].rtype == "E":
                    new_records.append(records[i])
                    i += 1
                continue

            # REPOTD / DYNPS / DYNPT% / DOCUT% (non-FUGR): template-specific
            # texts or dynpro source -- nothing to substitute, drop the block.
            i = _skip_block(records, i + 1)
            continue

        # TRDIRT holds program/class titles -- template text, drop the block
        # so the target keeps its own titles.
        if rec.rtype == "H" and b"TRDIRT" in rec.payload[:20]:
            i = _skip_block(records, i + 1)
            continue

        # D020T/D021T are dynpro texts. A real export ships them as 00REPC
        # WITH the screen's texts; we cannot generate dynpro data from an
        # abapGit repo, and the template's row-less delete would wipe the
        # target's existing screen texts -- so drop these blocks.
        if (rec.rtype == "H" and rec.payload[:8] == b"ATAB    "
                and rec.payload[8:38].decode("latin-1").rstrip()
                in ("D020T", "D021T")):
            i = _skip_block(records, i + 1)
            continue

        # DOKIL/DOKHL/DOKTL are long-text documentation (e.g. MSAG message
        # documentation, one triple per message number) -- not part of the
        # abapGit XML schema for any supported type and not shipped,
        # matching the project's "Documentation is not shipped" limitation.
        # Drop both the H (data) and N (nametab) records, each to its OWN
        # 'E' terminator via _skip_to_own_terminator (a nametab block has no
        # COMMIT of its own, so _skip_block would silently over-consume --
        # see that function's docstring). A dropped nametab's own 'gsr:'
        # marker was already appended to new_records by the previous loop
        # iteration ('*' records fall through to the generic pass-through
        # before this check ever sees the N record that follows them) --
        # pop it back off so it doesn't leave orphan litter in the output.
        if (rec.rtype in ("H", "N")
                and rec.payload[8:38].decode("latin-1").rstrip()
                in ("DOKIL", "DOKHL", "DOKTL")):
            if (new_records and new_records[-1].rtype == "*"
                    and new_records[-1].payload.startswith(b"gsr:")):
                new_records.pop()
            i = _skip_to_own_terminator(records, i + 1)
            continue

        # 'A' records carry the object directory attributes (package,
        # author, source system) at fixed offsets behind the name field.
        if rec.rtype == "A":
            # A package is its own TADIR DEVCLASS.  Putting it in the caller's
            # --package would turn the generated DEVC into an inconsistent
            # directory entry before TDEVC can create that package.
            a_package = obj_name if obj_type == "DEVC" else package
            new_records.append(_rename_a_record(rec, rule, a_package, author))
            i += 1
            continue

        # FUGR: per-FM blocks (TFTIT/FUNCT/TFDIR/ENLFDIR/FUPARAREF/RODIR)
        # of template FMs with no repo partner are dropped (drop-unmatched
        # rule) -- shipped renamed they would describe FMs the target does
        # not have. The DOCUT% branch above drops its own; every other
        # per-FM table is ATAB and lands here.
        if (obj_type == "FUGR" and rec.rtype == "H"):
            table = rec.payload[8:38].decode("latin-1").rstrip()
            key = rec.payload[48:].decode("latin-1").rstrip()
            fm = _fm_for_block(table, key, tmpl_fms)
            if fm is not None and fm not in mapped_tmpl_fms:
                i = _skip_block(records, i + 1)
                continue

        # Track which table's rows we are walking, so they can be renamed
        # field by field instead of by a shifting byte replacement.
        if rec.rtype == "H":
            table = rec.payload[8:38].decode("latin-1").rstrip()
            cur_table = table
            cur_fields = (nametabs.get(table)
                          if rec.payload[:8] in (b"ATAB    ", b"DLIB    ")
                          else None)
        elif rec.rtype == "E":
            cur_fields = None
            cur_table = ""

        # Data rows of a table with a known layout: field-aware rename.
        # Only for FULL rows -- '00DELW'/'00MODE' blocks carry a key pattern
        # instead of a row (shorter than the nametab), and those are renamed
        # as plain text.
        if (rec.rtype == " " and cur_fields
                and len(rec.payload) == cur_fields[-1][1] + cur_fields[-1][2]):
            row = _replace_in_row(rec, rule, cur_fields)
            if obj_type == "FUGR" and cur_table == "TFTIT":
                # FM title row (00REPC): FUNCNAME was renamed by the row
                # pass; the title comes from the repo's .fugr.xml, not from
                # the template's text.
                fm = _get_field_text(row.payload, cur_fields, "FUNCNAME")
                row = _set_fm_title(row, cur_fields, fm,
                                    fm_short_texts.get(fm, ""))
            elif obj_type == "FUGR" and cur_table == "TLIBT":
                # Function-library title (TLIBT.AREAT): group short text
                # from the repo's .fugr.xml (fallback: derived description).
                row = _write_field_by_name(
                    row, cur_fields, "AREAT",
                    fugr_areat or _make_description(obj_name))
            elif obj_type == "DTEL" and cur_table in ("DD04L", "DD04T"):
                # Domain/type reference + labels: new content per object,
                # not derivable from a renamed template value.
                row = _apply_dtel_row(row, cur_table, cur_fields, dtel_fields,
                                      obj_name)
            elif obj_type == "TTYP" and cur_table in ("DD40L", "DD40T"):
                # Row-type reference/kind/access/key + description: new
                # content per object, not derivable from a renamed template
                # value.
                row = _apply_ttyp_row(row, cur_table, cur_fields, ttyp_fields,
                                      obj_name)
            elif obj_type == "TRAN" and cur_table in ("TSTC", "TSTCC", "TSTCT"):
                # Program/screen/CINFO, GUI-availability flags, description:
                # new content per object, not derivable from a renamed
                # template value. TSTCP is handled separately after this
                # loop (see _regenerate_tran_tstcp) since it needs an
                # action-code change, not a fixed-shape overwrite.
                row = _apply_tran_row(row, cur_table, cur_fields, tran_fields,
                                      obj_name)
            elif obj_type == "TYPE" and cur_table == "DDTYPET":
                # Catalog entry (TYPEGROUP/DDLANGUAGE/DDTEXT): new content
                # per object, not derivable from a renamed template value.
                row = _apply_type_row(row, cur_fields, type_fields, obj_name)
            new_records.append(row)
            i += 1
            continue

        # Not a dropped block -- rename and pass through.
        # 'C' records carry the object name as an unpadded tail, so they may
        # change length; every other record is fixed-width.
        new_rec = _replace_in_record(rec, rule,
                                     preserve_length=(rec.rtype != "C"))
        # ATAB/DLIB H-record keys are fixed-width field patterns: re-pad the
        # name field so the trailing '*' stays in the right field.
        if rec.rtype == "H" and rec.payload[:8] in (b"ATAB    ", b"DLIB    "):
            new_rec = _rename_h_key(rec, new_rec, rule)
            if obj_type == "DTEL" and table == "DD04T":
                # The key packs ROLLNAME + DDLANGUAGE + '*'; the generic
                # rename above only touched ROLLNAME.
                new_rec = _fix_dtel_ddlanguage_key(
                    new_rec, dtel_fields.get("DDLANGUAGE", ""))
            if obj_type == "TTYP" and table == "DD40T":
                # The key packs TYPENAME + DDLANGUAGE + '*'; the generic
                # rename above only touched TYPENAME.
                new_rec = _fix_ttyp_ddlanguage_key(
                    new_rec, ttyp_fields.get("DDLANGUAGE", ""))
            if obj_type == "TYPE" and table == "DDTYPET":
                # The key packs TYPEGROUP + DDLANGUAGE + '*' (verified:
                # '<name>D*'); the generic rename above only touched
                # TYPEGROUP. DDLANGUAGE always defaults to 'D' (see
                # _parse_type_xml -- no per-object language signal exists
                # in a real .type.xml).
                new_rec = _fix_type_ddlanguage_key(
                    new_rec, type_fields.get("DDLANGUAGE") or "D")
            if obj_type == "TRAN" and table == "TSTCT":
                # The key packs SPRSL + TCODE (language FIRST, no trailing
                # '*' -- a different shape than DTEL/MSAG/TABL/TTYP's own
                # language-keyed tables, verified directly; see
                # _fix_tran_tstct_language_key). The generic rename above
                # only touched the TCODE portion.
                new_rec = _fix_tran_tstct_language_key(
                    new_rec, (tran_fields.get("TSTCT") or {}).get("SPRSL", ""))
        new_records.append(new_rec)
        i += 1

    # Add new REPOS blocks for sources not covered by template blocks
    if template_repos_h is not None and template_repos_meta is not None:
        for key_upper, (orig_key, suffix, src_text) in sources_by_key.items():
            if key_upper in handled_keys:
                continue

            print(f"  Adding new REPOS block for: {orig_key}")

            if (obj_type == "CLAS" and key_upper in cm_methods
                    and template_cm_h is not None):
                # CM### method includes beyond the template's single CM001:
                # mirror the template's method-include block (00MMRG action,
                # packed key, METHOD...ENDMETHOD content).
                new_block_recs = _make_cm_block_records(
                    obj_name, orig_key, cm_methods[key_upper], src_text,
                    template_cm_h, template_cm_meta or template_repos_meta,
                    rule)
            else:
                donor_meta = template_repos_meta
                if obj_type == "FUGR" and len(orig_key) > 3:
                    # L<grp>$nn / L<grp>Unn take the attributes of the
                    # template's own include of that kind
                    donor_meta = fugr_donor_meta.get(orig_key[-3], donor_meta)
                new_block_recs = _make_repos_block_records(
                    obj_name, orig_key, src_text,
                    template_repos_h, donor_meta
                )

            # Apply renames to the new block records, then the LDB
            new_block_recs = [_replace_in_record(r, rule)
                              for r in new_block_recs]
            if ldb:
                new_block_recs = [
                    _set_meta_ldb(r, ldb) if len(r.payload) == 628 else r
                    for r in new_block_recs]

            # Insert before the 'Z' (end-of-stream) record
            z_idx = None
            for idx in range(len(new_records) - 1, -1, -1):
                if new_records[idx].rtype == "Z":
                    z_idx = idx
                    break

            if z_idx is not None:
                new_records[z_idx:z_idx] = new_block_recs
            else:
                new_records.extend(new_block_recs)

    # Interface members: the template's SEO rows describe ITS members
    # (e.g. METHOD test); regenerate them from the real source -- constants
    # are components too -- so the modelled object matches the code.
    if obj_type == "INTF" and sources and len(seo_templates) == 3:
        src = next(iter(sources.values()))
        members = _parse_interface_members(src)
        print(f"  Interface members of {obj_name}: "
              f"{[m['name'] for m in members] or '(none)'}")
        for table, tmpl_row in seo_templates.items():
            flds = seo_nametabs.get(table)
            rows = [_build_component_row(tmpl_row, rule, m, flds)
                    for m in members]
            _replace_block_rows(new_records, table, rows)

    # Class members: same treatment for CLAS -- the template's rows describe
    # the template's TEST method, which the target class does not have. The
    # method rows are regenerated from the DEFINITION block (methods, plus
    # quoted-value constants, mirroring the INTF machinery).
    if obj_type == "CLAS" and sources and len(seo_templates) == 3:
        main_src = sources.get(obj_name)
        if main_src is None:
            main_src = next(iter(sources.values()))
        members = _parse_class_members(main_src)
        print(f"  Class members of {obj_name}: "
              f"{[m['name'] for m in members] or '(none)'}")
        for table, tmpl_row in seo_templates.items():
            flds = seo_nametabs.get(table)
            rows = [_build_class_member_row(tmpl_row, rule, m, flds, i)
                    for i, m in enumerate(members, start=1)]
            _replace_block_rows(new_records, table, rows)

    if obj_type in ("CLAS", "INTF") and sources:
        if obj_type == "CLAS":
            declaration = _extract_class_blocks(
                sources.get(obj_name) or "")[0] or ""
        else:
            declaration = next(iter(sources.values()))
        _apply_seo_header(new_records, obj_type, obj_name, declaration,
                          getattr(sources, "seo_meta", None) or {})

    # FUGR: synthesize per-FM blocks for repo FMs the template has no FM
    # for. The last mapped template FM's blocks (TFTIT/FUNCT/TFDIR/
    # ENLFDIR/FUPARAREF/RODIR/DOCUT% -- the full per-FM set) are cloned with
    # the FM name renamed; TFTIT gets the new FM's title and TFDIR its
    # U-number. The FM's SOURCE travels in the injected L<grp>U<n> REPOS
    # block (added above), not in the clone.
    if (obj_type == "FUGR" and cloned_fms and fm_blocks and tmpl_fms):
        donor = tmpl_fms[-1]                 # clone the last template FM
        ranges = fm_blocks.get(donor)
        if ranges:
            from dataclasses import replace
            for new_fm in cloned_fms:
                crule = replace(rule, fm_pairs=[(donor, new_fm)])
                recs = []
                for (start, end) in ranges:
                    cur_table = None
                    for k in range(start, end + 1):
                        rec = records[k]
                        if rec.rtype == "H":
                            cur_table = rec.payload[8:38].decode(
                                "latin-1").rstrip()
                            rr = _replace_in_record(rec, crule)
                            # Width-preserving key rename for every block
                            # type in the per-FM set: ATAB (TFTIT/FUNCT/
                            # TFDIR/ENLFDIR/FUPARAREF/RODIR) AND ABAPREAD
                            # (DOCUT% FU/FX keys pack the FM name in a
                            # 30-wide field). No-op when the key is
                            # unaffected.
                            rr = _rename_h_key(rec, rr, crule)
                        elif (rec.rtype == " " and cur_table
                              and cur_table in nametabs):
                            # FULL data rows: rename field by field -- a
                            # plain byte replacement shifts every field
                            # after the FM name (verifier finding F1).
                            flds = nametabs[cur_table]
                            if len(rec.payload) == flds[-1][1] + flds[-1][2]:
                                rr = _replace_in_row(rec, crule, flds)
                            else:
                                # key-pattern rows (FUNCT sweeps etc.)
                                rr = _replace_in_record(rec, crule)
                        else:
                            rr = _replace_in_record(rec, crule)
                        recs.append(rr)
                recs = _fix_cloned_fm_rows(recs, nametabs, new_fm,
                                           fm_short_texts, fm_u_numbers)
                z_idx = None
                for idx in range(len(new_records) - 1, -1, -1):
                    if new_records[idx].rtype == "Z":
                        z_idx = idx
                        break
                if z_idx is not None:
                    new_records[z_idx:z_idx] = recs
                else:
                    new_records.extend(recs)
                print(f"  Synthesized per-FM blocks for {new_fm} "
                      f"({len(ranges)} blocks cloned from template FM "
                      f"{donor})")

    # MSAG: regenerate the T100/T100U message rows + T100T/T100A STEXT from
    # the repo's .msag.xml message list (arbitrary count, unlike the
    # template's fixed message set) -- see the "Message class (MSAG)
    # metadata" section above.
    if obj_type == "MSAG":
        msag_meta = {
            "masterlang": getattr(sources, "msag_masterlang", "") or "",
            "stext": getattr(sources, "msag_stext", "") or "",
            "messages": list(getattr(sources, "msag_messages", None) or []),
        }
        new_records = _regenerate_msag_rows(new_records, obj_name, msag_meta)

    # TABL: regenerate DD02L/DD02T/DD03L from the repo's .tabl.xml (field
    # list is arbitrary count, like MSAG's message list) -- see the
    # "Table / structure (TABL) metadata" section above.
    if obj_type == "TABL":
        new_records = _regenerate_tabl_rows(new_records, obj_name, tabl_meta)

    # TRAN: TSTCP (parameter-transaction PARAM string) needs an action-code
    # change (delete-sweep -> single-row insert), not a fixed-shape
    # overwrite -- see the "Transaction code (TRAN) metadata" section above.
    if obj_type == "TRAN":
        new_records = _regenerate_tran_tstcp(
            new_records, obj_name, tran_fields.get("TSTCP"))

    # TOBJ: regenerate OBJH/OBJT/OBJS/TDDAT/TVDIR from the repo's .tobj.xml,
    # plus every one of these tables' H-record keys (a TOBJ-specific need,
    # not shared by any other type) -- see the "Table maintenance generator
    # (TOBJ) metadata" section above.
    if obj_type == "TOBJ":
        new_records = _regenerate_tobj_rows(new_records, obj_name, tobj_meta)

    # ENHO: rewrite ENHHEADER-DATA's RAW field in place using the field map
    # from ENHO_CLUSTER_FORMAT_PROGRESS.md -- see the "Class enhancement
    # (ENHO) metadata + binary field map" section above.
    if obj_type == "ENHO":
        if enho_meta.get("tool") == "BADI_IMPL":
            new_records = _regenerate_enho_badi_data_blob(
                new_records, obj_name, rule, enho_meta)
        else:
            new_records = _regenerate_enho_data_blob(new_records, obj_name,
                                                      rule, enho_meta)

    # VIEW: regenerate DD25L/DD25T/DD26S/DD27S from the repo's .view.xml
    # (base-table and field lists are arbitrary count, like TABL's DD03L) --
    # see the "Database view (VIEW) metadata" section above.
    if obj_type == "VIEW":
        new_records = _regenerate_view_rows(new_records, obj_name, view_meta)

    # DOMA: regenerate DD01L/DD01T/DD07L/DD07T from the repo's .doma.xml
    # (fixed-value list is arbitrary count, like MSAG's message list) -- see
    # the "Domain (DOMA) metadata" section above.
    if obj_type == "DOMA":
        new_records = _regenerate_doma_rows(new_records, obj_name, doma_meta)

    # ENQU: regenerate DD25L/DD25T/DD26S/DD27S from the repo's .enqu.xml --
    # the SAME four tables VIEW's own row above regenerates (SAP implements
    # a lock object as a special kind of DDIC view internally) -- see the
    # "Lock object (ENQU) metadata" section above.
    if obj_type == "ENQU":
        new_records = _regenerate_enqu_rows(new_records, obj_name, enqu_meta)

    # SHLP: regenerate DD30L/DD30T/DD31S/DD32S/DD33S from the repo's
    # .shlp.xml (parameter list is arbitrary count, like TABL's DD03L; the
    # sub-search-help list/mapping is either read from the XML directly or
    # synthesized for the elementary case) -- see the "Search help (SHLP)
    # metadata" section above.
    if obj_type == "SHLP":
        new_records = _regenerate_shlp_rows(new_records, obj_name, shlp_meta)

    # XSLT: regenerate O2XSLTDESC (header + the transformation source
    # packed inside CLUSTD's compressed cluster) and O2XSLTTEXT
    # (description, arbitrary count) from the repo's .xslt.xml +
    # .xslt.source.xml -- see the "ABAP Transformation (XSLT) metadata"
    # section above.
    if obj_type == "XSLT":
        new_records = _regenerate_xslt_rows(new_records, obj_name, xslt_meta)

    # SICF: regenerate ICFSERVICE/ICFDOCU/ICFHANDLER from the repo's
    # .sicf.xml (handler list is arbitrary count, like TABL's DD03L) -- see
    # the "ICF service (SICF) metadata" section above.
    if obj_type == "SICF":
        new_records = _regenerate_sicf_rows(new_records, obj_name, sicf_meta)

    # Adobe Forms: Native exports preserve abapGit's serialized XML object
    # graphs as RAW long values, so regenerate the FP* rows rather than
    # carrying a renamed (and potentially destructive) delete template.
    if obj_type == "SFPF":
        new_records = _regenerate_adobe_form_rows(
            new_records, obj_type, obj_name,
            getattr(sources, "sfpf_meta", None) or {})
    if obj_type == "SFPI":
        new_records = _regenerate_adobe_form_rows(
            new_records, obj_type, obj_name,
            getattr(sources, "sfpi_meta", None) or {})

    # DEVC: regenerate both package rows from the repo's .devc.xml, so no
    # namespace/package metadata from the native probe can leak into output.
    if obj_type == "DEVC":
        new_records = regenerate_devc_rows(new_records, obj_name, devc_meta)

    # Text pools (.prog.xml / .clas.xml <TPOOL>): the template's own text
    # pool block was dropped above; ship the repo's instead.
    textpools = getattr(sources, "textpools", None) or {}
    if textpools and template_repos_h is not None:
        program = (obj_name if obj_type == "PROG"
                   else _build_repos_key("CLAS", obj_name, "CP"))
        too_long = [e for items in textpools.values() for e in items
                    if e[3] > 255 or len(e[2]) > e[3]]
        if too_long:
            raise ValueError(f"{obj_type} {obj_name}: text pool entry "
                             f"{too_long[0][:2]} is longer than its LENGTH")
        z_idx = next(i for i in range(len(new_records) - 1, -1, -1)
                     if new_records[i].rtype == "Z")
        blocks = []
        for language, entries in sorted(textpools.items()):
            blocks += _textpool_block(template_repos_h, program, language,
                                      entries)
        new_records[z_idx:z_idx] = blocks
        print(f"  Text pool for {program}: "
              f"{ {lang: len(e) for lang, e in sorted(textpools.items())} }")

    if obj_type == "FUGR":
        _apply_fm_interfaces(new_records,
                             getattr(sources, "fugr_interfaces", None) or {})

    content = _table_content(obj_type, obj_name, sources, package)
    if content is not None:
        new_records = _regenerate_table_content(new_records, obj_name,
                                                content, rule.language)

    return _apply_author_to_metadata_rows(new_records, author)


# -- Interface / class component (SEO) regeneration ------------------------
