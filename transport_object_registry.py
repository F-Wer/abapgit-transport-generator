"""Object type registry for abapGit transport generation.

This module is intentionally small for now: it centralizes object type names and
filename detection rules. Future object-specific handlers (SXCI, CMOD, SMOD,
etc.) should extend from this registry rather than adding more branches to the
main generator.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectFileRule:
    suffix: str
    object_type: str
    namespace_mangling: bool = True
    skip_class_testclasses: bool = False


# ENHO is deliberately not registered until its framework rows and both
# administrative RAW blobs are regenerated.  Generating it from a template
# currently attaches the enhancement to that template's class.
OBJECT_FILE_RULES = (
    ObjectFileRule(".acid.xml", "ACID"),
    ObjectFileRule(".apis.xml", "APIS"),
    ObjectFileRule(".aplo.xml", "APLO"),
    ObjectFileRule(".aqbg.xml", "AQBG"),
    ObjectFileRule(".aqqu.xml", "AQQU"),
    ObjectFileRule(".aqsg.xml", "AQSG"),
    ObjectFileRule(".asfc.xml", "ASFC"),
    ObjectFileRule(".auth.xml", "AUTH"),
    ObjectFileRule(".avar.xml", "AVAR"),
    ObjectFileRule(".avas.xml", "AVAS"),
    ObjectFileRule(".char.xml", "CHAR"),
    ObjectFileRule(".prag.xml", "PRAG"),
    ObjectFileRule(".otgr.xml", "OTGR"),
    # PINF generation remains available internally for experiments, but a real import
    # excludes it from the normal import phase (ETW677); do not advertise it.
    ObjectFileRule(".nrob.xml", "NROB"),
    ObjectFileRule(".para.xml", "PARA"),
    ObjectFileRule(".susc.xml", "SUSC"),
    ObjectFileRule(".sucu.xml", "SUCU"),
    ObjectFileRule(".sppf.xml", "SPPF"),
    ObjectFileRule(".splo.xml", "SPLO"),
    ObjectFileRule(".suso.xml", "SUSO"),
    ObjectFileRule(".cus0.xml", "CUS0"),
    ObjectFileRule(".cus2.xml", "CUS2"),
    ObjectFileRule(".cus1.xml", "CUS1"),
    ObjectFileRule(".pers.xml", "PERS"),
    ObjectFileRule(".scvi.xml", "SCVI"),
    ObjectFileRule(".devc.xml", "DEVC"),
    ObjectFileRule(".amsd.xml", "AMSD"),
    ObjectFileRule(".clas.xml", "CLAS", skip_class_testclasses=True),
    ObjectFileRule(".intf.xml", "INTF"),
    ObjectFileRule(".fugr.xml", "FUGR"),
    ObjectFileRule(".dtel.xml", "DTEL"),
    ObjectFileRule(".msag.xml", "MSAG"),
    ObjectFileRule(".tabl.xml", "TABL"),
    ObjectFileRule(".ttyp.xml", "TTYP"),
    ObjectFileRule(".tran.xml", "TRAN"),
    ObjectFileRule(".tobj.xml", "TOBJ"),
    ObjectFileRule(".view.xml", "VIEW"),
    ObjectFileRule(".doma.xml", "DOMA"),
    ObjectFileRule(".type.xml", "TYPE"),
    ObjectFileRule(".enqu.xml", "ENQU"),
    ObjectFileRule(".shlp.xml", "SHLP"),
    ObjectFileRule(".xslt.xml", "XSLT"),
    ObjectFileRule(".sicf.xml", "SICF", namespace_mangling=False),
    ObjectFileRule(".sfpf.xml", "SFPF"),
    ObjectFileRule(".sfpi.xml", "SFPI"),
)
