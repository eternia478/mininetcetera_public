"Logging functions for CMSnet."

from mininet.log import info, error, warn, debug
import traceback

def config_error(error_msg, config=None, config_raw=None):
    "Output error messages for config handling."
    tb_str = traceback.format_exc()
    tabbed_tb_str = "\t"+"\n\t".join(tb_str.rstrip().split("\n"))
    error_info = [error_msg, tabbed_tb_str]

    config_info = []
    if config is not None:
        config_info.append("\tconfig = %s" % config)
    if config_raw is not None:
        config_info.append("\tconfig_raw = %s" % config_raw)

    error("\n".join([""] + error_info + config_info + [""]))
