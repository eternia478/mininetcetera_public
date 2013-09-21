"Logging functions for CMSnet."

from mininet.log import error, info, output, warn, debug
import traceback
import cmsnet.cms_comp

def _add_name_to_msg (comp, log_msg=None):
    "Return new log message marked with component name."
    if isinstance(comp, cmsnet.cms_comp.CMSComponent):
        return "%s: %s" % (comp.name, log_msg)
    elif comp is not None:
        return "%s: %s" % (comp.__class__.__name__, log_msg)
    else:
        return str(comp) # Work-around now in case comp not set.

def error (comp, error_msg=None ):
    "Log message to error and include component name."
    error("%s\n" % _add_name_to_msg(comp, error_msg))

def info (comp, info_msg=None ):
    "Log message to info and include component name."
    info("%s\n" % _add_name_to_msg(comp, info_msg))

def output (comp, output_msg=None ):
    "Log message to output and include component name."
    output("%s\n" % _add_name_to_msg(comp, output_msg))

def warn (comp, warn_msg=None ):
    "Log message to warning and include component name."
    warn("%s\n" % _add_name_to_msg(comp, warn_msg))

def debug (comp, debug_msg=None ):
    "Log message to debug and include component name."
    debug("%s\n" % _add_name_to_msg(comp, debug_msg))

def config_error (comp, error_msg, config=None, config_raw=None):
    "Output error messages for config handling."
    tb_str = traceback.format_exc()
    tabbed_tb_str = "\t"+"\n\t".join(tb_str.rstrip().split("\n"))
    error_msg = _add_name_to_msg(comp, error_msg)
    error_info = [error_msg, tabbed_tb_str]

    config_info = []
    if config is not None:
        config_info.append("\tconfig = %s" % config)
    if config_raw is not None:
        config_info.append("\tconfig_raw = %s" % config_raw)

    error("\n".join([""] + error_info + config_info + [""]))
