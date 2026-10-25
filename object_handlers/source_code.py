"""Registry for source-code object collectors."""

from object_handlers.clas import collect_clas_sources
from object_handlers.intf import collect_intf_sources
from object_handlers.prog import collect_prog_sources


SOURCE_COLLECTORS = {
    "PROG": collect_prog_sources,
    "CLAS": collect_clas_sources,
    "INTF": collect_intf_sources,
}
