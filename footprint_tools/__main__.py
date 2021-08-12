import sys

import click

# Set up console logging from package file
# This configure root logger which is inherited 
# by all modules/submodules
import pkg_resources
import logging, logging.config
logging.config.fileConfig(pkg_resources.resource_filename(__name__, "logging.conf"))

logger = logging.getLogger(__name__)

import footprint_tools
import footprint_tools.cli.learn_dm as learn_dm
# import footprint_tools.cli.detect as detect
# import footprint_tools.cli.learn_beta as learn_beta
# import footprint_tools.cli.plot_dm as plot_dm
# import footprint_tools.cli.posterior as posterior

epilog = """Written by Jeff Vierstra (jvierstra@altius.org) (2015-2021). 

See http://github.com/jvierstra/footprint-tools for extended documentation.

Software licensed under GNU General Public License version 3."""

@click.group()
def main():
    pass

main.add_command(learn_dm.run)