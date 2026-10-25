"""Small metadata-object regeneration helpers."""

from collections.abc import Callable

from sap_transport_records import Record


_helpers: dict[str, Callable] = {}


def configure_metadata_helpers(**helpers: Callable) -> None:
    """Provide shared record helpers owned by the compatibility facade."""
    _helpers.update(helpers)


def _helper(name: str) -> Callable:
    try:
        return _helpers[name]
    except KeyError as exc:
        raise RuntimeError(f"metadata helper {name!r} has not been configured") from exc


def _parse_nametabs(*args, **kwargs):
    return _helper("parse_nametabs")(*args, **kwargs)


def _make_description(*args, **kwargs):
    return _helper("make_description")(*args, **kwargs)


def _write_field_by_name(*args, **kwargs):
    return _helper("write_field_by_name")(*args, **kwargs)

def _find_block_by_action(*args, **kwargs):
    return _helper("find_block_by_action")(*args, **kwargs)

def _blank_row(*args, **kwargs):
    return _helper("blank_row")(*args, **kwargs)

def _replace_rows_in_block(*args, **kwargs):
    return _helper("replace_rows_in_block")(*args, **kwargs)

def _write_raw_field_by_name(*args, **kwargs):
    return _helper("write_raw_field_by_name")(*args, **kwargs)


def regenerate_acid_rows(records: list, obj_name: str,
                          acid_meta: dict) -> list:
    """Write abapGit's ACID description to every transported text row."""
    fields = _parse_nametabs(records).get("AAB_ID_PROPT")
    description = acid_meta.get("description") or _make_description(obj_name)
    if not fields:
        print("  WARNING: template has no AAB_ID_PROPT REPC block -- "
              "checkpoint-group description cannot be regenerated")
        return records
    row_indexes = []
    for index, record in enumerate(records):
        if (record.rtype == "H" and record.payload[8:38].decode(
                "latin-1").rstrip() == "AAB_ID_PROPT" and
                record.payload[38:44].decode("latin-1") == "00REPC"):
            end = index + 1
            while end < len(records) and records[end].rtype != "E":
                if records[end].rtype == " ":
                    row_indexes.append(end)
                end += 1
    if not row_indexes:
        print("  WARNING: template has no AAB_ID_PROPT REPC block -- "
              "checkpoint-group description cannot be regenerated")
        return records
    for row_index in row_indexes:
        records[row_index] = _write_field_by_name(records[row_index], fields,
                                                   "DESCRIPT", description)
    print(f"  ACID description for {obj_name}: {description!r} "
          f"({len(row_indexes)} transported language row(s))")
    return records


def regenerate_apis_rows(records: list, obj_name: str, apis_meta: dict) -> list:
    """Regenerate the APIS header and arbitrary release-state row set."""
    nametabs = _parse_nametabs(records)
    header = apis_meta.get("header") or {}
    states = apis_meta.get("states") or []
    api_fields = nametabs.get("ARS_W_API") or []
    api_block = _find_block_by_action(records, "ARS_W_API", "00REP ")
    if api_block and api_fields:
        for index in api_block[1]:
            row = records[index]
            for field, value in header.items():
                row = _write_field_by_name(row, api_fields, field, value)
            records[index] = row
    state_fields = nametabs.get("ARS_W_API_STATE") or []
    state_block = _find_block_by_action(records, "ARS_W_API_STATE", "00REPC")
    if state_block and state_fields:
        donor = records[state_block[1][0]] if state_block[1] else _blank_row(state_fields)
        rows = []
        for state in states:
            row = Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
            for field, value in state.items():
                row = _write_field_by_name(row, state_fields, field, value)
            rows.append(row)
        _replace_rows_in_block(records, state_block, rows)
        print(f"  APIS release states for {obj_name}: {len(rows)}")
    return records


def regenerate_aplo_rows(records: list, aplo_meta: dict) -> list:
    """Regenerate AFF application-log metadata using each table's nametab."""
    tabs = _parse_nametabs(records)
    for table in ("BALOBJ", "BALOBJT", "BALSUB", "BALSUBT"):
        rows_meta = aplo_meta.get(table) or []
        if not rows_meta:
            continue
        block = _find_block_by_action(records, table, "00REPC")
        if block is None:
            block = _find_block_by_action(records, table, "00REP ")
        fields = tabs.get(table) or []
        if block is None or not fields:
            continue
        donor = records[block[1][0]] if block[1] else _blank_row(fields)
        rows = []
        for meta in rows_meta:
            row = Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
            for name, value in meta.items():
                row = _write_field_by_name(row, fields, name, value)
            rows.append(row)
        _replace_rows_in_block(records, block, rows)
    return records


def regenerate_amsd_rows(records: list, amsd_meta: dict) -> list:
    """Apply explicitly serialized AMSD fields to its captured tables."""
    tabs = _parse_nametabs(records)
    for table, action in (("AMDP_SCHEMA_DEF", "00REP "),
                          ("AMDP_SCHEMA_DEFT", "00REPC")):
        block = _find_block_by_action(records, table, action)
        fields = tabs.get(table) or []
        if not block or not fields:
            continue
        for index in block[1]:
            row = records[index]
            for name, value in amsd_meta.items():
                target = "DESCRIPTION" if name == "DESCRIPT" else name
                row = _write_field_by_name(row, fields, target, value)
            records[index] = row
    return records



def regenerate_asfc_rows(records: list, asfc_meta: dict) -> list:
    """Replace all captured ASFC generic-table rows from XML."""
    tabs = _parse_nametabs(records)
    actions = {"AIND_STR1": "00REP ", "AIND_STR1T": "00REPC",
               "AIND_STR3": "00REPC", "AIND_STR4": "00DELL",
               "AIND_STR6": "00REPC", "AIND_STR7": "00DELL"}
    for table, rows_meta in asfc_meta.items():
        fields = tabs.get(table) or []
        block = _find_block_by_action(records, table, actions.get(table, "00REPC"))
        if not fields or not block:
            continue
        donor = records[block[1][0]] if block[1] else _blank_row(fields)
        rows = []
        for meta in rows_meta:
            row = Record(offset=0, rtype=" ", payload=donor.payload, fragments=1)
            for name, value in meta.items():
                row = _write_field_by_name(row, fields, name, value)
            rows.append(row)
        _replace_rows_in_block(records, block, rows)
    return records




def regenerate_auth_rows(records: list, auth_meta: dict) -> list:
    """Write AUTHX fields serialized by abapGit and clear donor audit data."""
    tabs = _parse_nametabs(records)
    block = _find_block_by_action(records, "AUTHX", "00REP ")
    fields = tabs.get("AUTHX") or []
    if block and fields:
        for index in block[1]:
            row = records[index]
            for name, value in auth_meta.items():
                row = _write_field_by_name(row, fields, name, value)
            records[index] = row
    attrs = _find_block_by_action(records, "AUTHX_ATTR", "00REP ")
    attr_fields = tabs.get("AUTHX_ATTR") or []
    if attrs and attr_fields:
        for index in attrs[1]:
            row = records[index]
            for name, _off, _length, _kind in attr_fields:
                if name != "FIELDNAME":
                    row = _write_field_by_name(row, attr_fields, name, "")
            records[index] = row
    return records




def regenerate_avar_rows(records: list, obj_name: str, avar_meta: dict) -> list:
    """Rebuild AVAR property, ID and English description rows."""
    tabs=_parse_nametabs(records)
    for table, action in (("AAB_VAR_PROP","00REPC"),("AAB_VAR_PROPT","00REPC")):
        block=_find_block_by_action(records,table,action); fields=tabs.get(table) or []
        if not block or not fields: continue
        donor=records[block[1][0]] if block[1] else _blank_row(fields)
        row=Record(offset=0,rtype=" ",payload=donor.payload,fragments=1)
        row=_write_field_by_name(row,fields,"NAME",obj_name)
        row=_write_field_by_name(row,fields,"LOCAL","")
        if table == "AAB_VAR_PROP": row=_write_field_by_name(row,fields,"AUTHOR","")
        else: row=_write_field_by_name(row,fields,"DESCRIPT",avar_meta.get("description", ""))
        _replace_rows_in_block(records,block,[row])
    block=_find_block_by_action(records,"AAB_VAR_ID","00REPC"); fields=tabs.get("AAB_VAR_ID") or []
    if block and fields:
        donor=records[block[1][0]] if block[1] else _blank_row(fields); rows=[]
        for item in avar_meta.get("ids") or []:
            row=Record(offset=0,rtype=" ",payload=donor.payload,fragments=1)
            row=_write_field_by_name(row,fields,"VAR_NAME",obj_name)
            row=_write_field_by_name(row,fields,"LOCAL","")
            row=_write_field_by_name(row,fields,"ID_NAME",item.get("NAME", ""))
            row=_write_field_by_name(row,fields,"IS_PROGRAM",item.get("OBJECT", ""))
            row=_write_raw_field_by_name(row,fields,"ID_ACTMODE",bytes([int(item.get("ACTMODE", "0") or "0")]))
            rows.append(row)
        _replace_rows_in_block(records,block,rows)
    return records




def regenerate_avas_rows(records: list, obj_name: str, avas_meta: dict) -> list:
    tabs=_parse_nametabs(records); fields=tabs.get("CLS_ASSIGNMENT") or []; block=_find_block_by_action(records,"CLS_ASSIGNMENT","00REPC")
    if not fields or not block:return records
    donor=records[block[1][0]] if block[1] else _blank_row(fields); header=avas_meta.get('header') or {}; rows=[]
    for value in avas_meta.get('values') or [{}]:
        row=Record(offset=0,rtype=' ',payload=donor.payload,fragments=1)
        for field, source in (("GUID","GUID"),("TROBJTYPE","TROBJTYPE"),("SOBJ_NAME","SOBJ_NAME"),("OBJECT_TYPE","OBJECT_TYPE"),("SUB_KEY","SUB_KEY"),("ATTRIBUTE","ATTRIBUTE"),("VALUE","VALUE"),("REMARK","REMARK")):
            row=_write_field_by_name(row,fields,field,(header if source not in ('VALUE','REMARK') else value).get(source,''))
        row=_write_field_by_name(row,fields,"SET_BY","");row=_write_field_by_name(row,fields,"CHANGED_ON","");rows.append(row)
    _replace_rows_in_block(records,block,rows);return records



def regenerate_char_rows(records: list, char_meta: dict) -> list:
    tabs=_parse_nametabs(records)
    actions={"CLS_ATTRIBUTE":"00REP ","CLS_ATTRIBUTET":"00REPC","CLS_ATTR_VALUE":"00DELL","CLS_ATTR_VALUET":"00DELL"}
    for table, meta in char_meta.items():
        fields=tabs.get(table) or []; block=_find_block_by_action(records,table,actions[table])
        if not fields or not block: continue
        donor=records[block[1][0]] if block[1] else _blank_row(fields); rows=[]
        for item in meta:
            row=Record(offset=0,rtype=' ',payload=donor.payload,fragments=1)
            for name,value in item.items(): row=_write_field_by_name(row,fields,name,value)
            for audit in ('CREATED_BY','CREATED_ON','CHANGED_BY','CHANGED_ON'): row=_write_field_by_name(row,fields,audit,'')
            rows.append(row)
        _replace_rows_in_block(records,block,rows)
    return records
