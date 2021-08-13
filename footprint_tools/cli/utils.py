"""
Argument validation functions
"""
import click

def tuple_args(value_type=int):
    def _parse_tuple(ctx, params, value):
        """Function to parse a tuple from command line"""
        try:
            items = tuple(map(value_type, value.split(',')))
            assert len(items) == 2
        except:
            raise click.BadOptionUsage(f'needs to be a comma-delimited tuple of type {value_type.__name__}')
        return items
    return _parse_tuple

def list_args(value_type=int):
    def _parse_list(ctx, params, value):
        """Function to parse a list from command line"""
        try:
            items = list(map(value_type, value.split(',')))
        except:
            raise click.BadOptionUsage(f'needs to be a comma-delimited list of type {value_type.__name__}')
        return items
    return _parse_list

def get_kwargs(keys, kwargs):
    return {k:kwargs[k] for k in keys if k in kwargs}

"""
File validation functions
"""
import pysam

def verify_bam_file(fn):
    """Tries to open a file, raises IOError with problems"""
    try:
        pysam.AlignmentFile(fn).close()
    except IOError:
        raise IOError(f"No such file: {fn}")
    except ValueError:
        raise IOError(f"BAM-index not found for {fn}")

def verify_tabix_file(fn):
    """Tries to open a file, raises IOError with problems"""
    try:
        pysam.TabixFile(fn).close()
    except IOError:
        raise IOError(f"No such file: {fn}")
    except ValueError:
        raise IOError(f"TABIX-index not found for {fn}")

def verify_fasta_file(fn):
    """Tries to open a file, raises IOError with problems"""
    try:
        pysam.FastaFile(fn).close()
    except IOError:
        raise IOError(f"No such file: {fn}")
    except ValueError:
        raise IOError(f"FASTA-index not found for {fn}")

"""
Writer functions
"""
import sys
import numpy as np

from footprint_tools
from footprint_tools.stats import utils

def write_output_header(columns, file=sys.stdout, delim='\t', include_name=True, extra=None):
    """Write header to ouptput file
    
    Parameters
    ----------
    columns : list
        Columns in file (apart from standard chrom, start, end)
    file : filehandle
        Filehandle to write header to
    delim : str
        Delimiter to use when printing output
    include_name : bool

    """
    file.write(f"# generated by {footprint_tools.__name__} version {footprint_tools.__version__}\n")
    file.write(f"# chrom{delim}start{delim}end")
    if include_name:
        file.write(f"{delim}name")
    file.write(delim + delim.join(columns)+'\n')
    if extra:
        file.write('# '+extra+'\n')


def write_stats_to_output(interval, stats, file=sys.stdout, delim='\t', filter_fn=None, fmt_string='0.4f'):
    """Write per-nucleotide statistics to file
    
    The input stats array can be of any width the function just writes all
    columns

    Parameters
    ----------
    interval : genomic_interval
        Genomic regions corresponding to stats
    stats : ndarray
        2-D array
    file : filehandle
        File handle to write output
    delim : str
        Delimiter to use when printing output
    filter_fn: callable
        Function to apply that determines which positions get
        written to file
    fmt_string: str
        Format string to apply when writing scores

    Notes
    -----
    The filter_fn is a function that returns an boolean array of same length of stats
    specifying whether a position should be written. For example:

        lambda x: np.max(x, axis=1) >= 0.2

    If filter_fn is not specified all rows are outputted
    """    
    chrom = interval.chrom
    start = interval.start

    idxs = np.nonzero(filter_fn(stats)) if filter_fn else range(stats.shape[0])

    for i in idxs:
        out = f'{chrom}{delim}{start+i}{delim}{start+i+1}{delim}'
        out += delim.join([('{0:'+fmt_string+'}').format(val) for val in stats[i,:]])
        file.write(out+'\n')

def write_segments_to_output(interval, stats, threshold, name='.', file=sys.stdout,
                            delim='\t', score_fn=np.min, decreasing=False, fmt_string='0.4f'):
    """Write footprints to file
    
    Parameters
    ----------
    interval : genomic_interval
        Genomic regions corresponding to stats
    stats : ndarray
        1D array
    threshold : int or float
        Threshold to use when performing segmentations
    file : filehandle
        File handle to write output
    delim : str
        Delimiter to use when printing output
    score_fn: callable
        Function to apply when computing score within the segments
    decreasing: bool
        Values below threshold are outputted
    name: str
        Name for BED entry
    fmt_string: str
        Format string to apply when writing scores
    """
    chrom = interval.chrom
    start = interval.start

    segments = utils.segment(
                -stats if decreasing else stats
                -threshold if decreasing else threshold, 3)

    for s, e in segments:
        score = score_fn(stats[s:e])        
        out = f"{chrom}{delim}{start+s}{delim}{start+e}{delim}{name}{delim}"
        out += ('{0:'+fmt_string+'}').format(score)
        file.write(out+'\n')
