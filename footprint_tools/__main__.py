import sys

import argh

# Set up console logging from package file
# This configure root logger which is inherited 
# by all modules/submodules
import pkg_resources
import logging, logging.config
logging.config.fileConfig(pkg_resources.resource_filename(__name__, "logging.conf"))

logger = logging.getLogger(__name__)

import footprint_tools
import footprint_tools.cli.learn_dm as learn_dm
import footprint_tools.cli.detect as detect
import footprint_tools.cli.learn_beta as learn_beta
import footprint_tools.cli.plot_dm as plot_dm
import footprint_tools.cli.posterior as posterior
import footprint_tools.cli.meta_profile as meta_profile

epilog = """Written by Jeff Vierstra (jvierstra@altius.org) (2015-2021). 

See http://github.com/jvierstra/footprint-tools for extended documentation.

Software licensed under GNU General Public License version 3."""

def main():
    parser = argh.ArghParser(epilog=epilog)
    parser.add_commands([
        learn_dm.run,
        detect.run,
        learn_beta.run,
        plot_dm.run,
        posterior.run,
        meta_profile.run,
    ])
    parser.add_argument('--version',
            action='version',
            version='%(prog)s ' + footprint_tools.__version__)
    
    return argh.dispatch(parser, output_file=None)
