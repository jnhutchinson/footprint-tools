import sys

from argh.decorators import named, arg

import numpy as np
import scipy as sp
import pandas as pd
import pysam

from footprint_tools.data.process import process

from genome_tools import bed, genomic_interval

from footprint_tools import cutcounts
from footprint_tools.modeling import bias, predict, dispersion
from footprint_tools.stats import fdr, windowing, utils

from footprint_tools.cli.utils import list_args, tuple_args, get_kwargs, fstr

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import logging
logger = logging.getLogger(__name__)

# kill numpy warnings
np.seterr(all="ignore")

class deviation_stats(process):
    """Class that computes per-nucleotide cleavage
    deviation statistics
    """
    def __init__(self, interval_file, bam_file, fasta_file, bm, dm, **kwargs):

        self.intervals = pd.read_table(interval_file, header=None)

        logger.info(f"BED file contains {len(self.intervals):,} regions")

        self.bam_file = bam_file
        self.fasta_file = fasta_file
        self.bm = bm
        self.dm = dm

        # kwargs for cutcounts.bamfile
        self.counts_reader_kwargs = get_kwargs(
            [
                'min_qual',
                'remove_dups',
                'remove_qcfail',
                'offset'
            ], 
            kwargs)

        self.fasta_reader_kwargs = {}

        self.counts_predictor_kwargs = get_kwargs(
            [
                'half_win_width',
                'smoothing_half_win_width',
                'smoothing_clip'
            ],
            kwargs)

        self.fdr_shuffle_n = kwargs['fdr_shuffle_n']
        self.seed = kwargs['seed']

        self.counts_reader = None
        self.fasta_reader = None
        self.count_predictor = None

        self.win_pval_fn = lambda z: windowing.stouffers_z(np.ascontiguousarray(z), 3)

    def __len__(self):
        return len(self.intervals)

    def __getitem__(self, index):
        """Process data for a single interval"""
        
        # Open file handlers on first call. This avoids problems when
        # parallel processing data with non-thread safe code (i.e., pysam)
        if not self.counts_reader:
            self.counts_reader = cutcounts.bamfile(self.bam_file, **self.counts_reader_kwargs)
            self.fasta_reader = pysam.FastaFile(self.fasta_file, **self.fasta_reader_kwargs)
            self.count_predictor = predict.prediction(self.counts_reader, self.fasta_reader, 
                                                        self.bm, **self.counts_predictor_kwargs)

        chrom, start, end = (self.intervals.iat[index, 0], 
                             self.intervals.iat[index, 1], 
                             self.intervals.iat[index, 2])

        interval = genomic_interval(chrom, start, end)

        obs, exp, _ = self.count_predictor.compute(interval)
        obs = obs['+'][1:] + obs['-'][:-1]
        exp = exp['+'][1:] + exp['-'][:-1]

        assert len(obs) == len(exp)
        n = len(obs)

        if self.dm:
            try:
                pvals = self.dm.p_values(exp, obs)
                win_pvals = self.win_pval_fn(pvals)

                _, pvals_null = self.dm.sample(exp, self.fdr_shuffle_n)
                win_pvals_null = np.apply_along_axis(self.win_pval_fn, 0, pvals_null)

                efdr = fdr.emperical_fdr(win_pvals_null, win_pvals)
            except Exception as e:
                logger.warning(f"Error computing stats for '{interval.chrom}:{interval.start}-{interval.end}'")
                pvals = win_pvals = efdr = np.ones(n) # should change to return 'nan'
            finally:
                stats = np.column_stack((exp, obs, -np.log(pvals), -np.log(win_pvals), efdr))
        else:
            stats = np.column_stack((exp, obs))

        return {
                    "interval": interval,
                    "stats": stats
                }

def write_stats_to_output(interval, stats, file=sys.stdout):
    chrom = interval.chrom
    start = interval.start
    for i in range(stats.shape[0]):
        out = f'{chrom}\t{start+i}\t{start+i+1}\t'
        out += '\t'.join(['{:0.4f}'.format(val) for val in stats[i,:]])
        file.write(out+'\n')

def write_segments_to_output(interval, segments, file=sys.stdout):
    pass

@named('detect')
@arg('interval_file', 
    help='File path to BED file contain regions to analyzed')
@arg('bam_file', 
    help='Path to BAM-format tag alignment file')
@arg('fasta_file',
    help='Path to genome FASTA file (requires associated FASTA '
        'index in same folder; see documentation on how to create '
        'an index)')
@arg('--bias_model_file',
    type=str,
    default=None,
    help='Use a k-mer model for sequence bias (supplied by file). '
        'If argument is not provided the model defaults to uniform '
        'sequence bias.')
@arg('--dispersion_model_file',
    type=str,
    default=None,
    help='Dispersion model for negative binomial tests. If argument '
        'is not provided then no stastical output is provided. File is in '
        'JSON format and generated using the command learn_dm')
@arg('--min_qual',
    type=int,
    default=1,
    help='Ignore reads with mapping quality lower than this threshold')
@arg('--remove_dups',
    help='Remove duplicate reads',
    default=False)
@arg('--keep_qcfail',
    help='Retain QC-failed reads',
    default=False)
@arg('--bam_offset',
    type=tuple_args(int),
    default=(0, -1),
    help='BAM file offset (enables support for other datatypes -- e.g., Tn5/ATAC)')
@arg('--half_win_width',
    help='Half window width to apply bias model',
    default=5)
@arg('--smooth_half_win_width',
    type=int,
    help='Half window width to apply smoothing model. When set to '
        '0, no smoothing is applied.',
    default=50)
@arg('--smooth_clip',
    type=float,
    help='Fraction of bases to clip when computing trimmed mean in the smoothing window',
    default=0.01)
@arg('--fdr_shuffle_n',
    type=int,
    default=100,
    help='Number of times to shuffle data for FDR calculation')
@arg('--seed',
    default=None,
    help='Seed for random number generation')
@arg('--n_threads',
    help='Number of processors to use',
    default=8)
@arg('--batch_size',
    help='Batch size of intervals to process',
    default=100)
@arg('--prefix',
    dest='output_prefix',
    help='Output file(s) prefix')
@arg('--write_footprints',
    type=list_args(float),
    help='Output footprints at specified FDRs')
def run(interval_file,
        bam_file,
        fasta_file,
        bias_model_file=None,
        dispersion_model_file=None,
        min_qual=1,
        remove_dups=False,
        keep_qcfail=False,
        bam_offset=(0, -1),
        half_win_width=5,
        smooth_half_win_width=50,
        smooth_clip=0.01,
        fdr_shuffle_n=50,
        seed=None,
        n_threads=8,
        batch_size=100,
        write_footprints=[0.001, 0.01, 0.05],
        output_prefix='out'):
    """Compute per-nucleotide cleavage deviation statistics	

    Output:
        bedGraph file written to `prefix`.bedgraph (see arguments):
            contig start start+1 obs exp -log(pval) -log(winpval) fdr
    """
    proc_kwargs = {
        "min_qual": min_qual,
        "remove_dups": remove_dups,
        "remove_qcfail": ~keep_qcfail,
        "offset": bam_offset,
        "half_win_width": half_win_width,
        "smoothing_half_win_width": smooth_half_win_width,
        "smoothing_clip": smooth_clip,
        "fdr_shuffle_n": fdr_shuffle_n,
        "seed": seed, # not used...yet
    }

    # Load bias model (if specified), otherwise use the uniform model
    if bias_model_file:
        logger.info(f"Loading bias model from file {bias_model_file}")
        bm = bias.kmer_model(bias_model_file)
    else:
        logger.info(f"No bias model file specified -- using uniform model")
        bm = bias.uniform_model()

    # Load dispersion model (if specified)
    if dispersion_model_file:
        dm = dispersion.load_dispersion_model(dispersion_model_file)
        logger.info(f"Loading dispersion model from file {dispersion_model_file}")
    else:
        logger.info(f"No dispersion model file specified -- not be reporting base-level statistics and footprints")
        dm = None
        write_footprints = []

    # Output stats file
    output_bedgraph_file = output_prefix + '.bedgraph'
    
    logger.info(f"Writing per-nucleotide stats to {output_bedgraph_file}")
    output_bedgraph_filehandle = open(output_bedgraph_file , 'w')
    
    # Output footprints file
    output_bed_file_template = output_prefix + '.fdr{0}.bed'
    output_bed_filehandles = {}

    if len(write_footprints) > 0:
        logger.info(f"Writing footprints to {output_bed_file_template.format('{threshold}')} for threshold \u22f2 {write_footprints}")    
        output_bed_filehandles.update({t: open(output_bed_file_template.format(t), 'w') for t in write_footprints})
    
    # Create data processor and iterator
    dp = deviation_stats(interval_file, bam_file, fasta_file, bm, dm, **proc_kwargs)
    dp_iter = dp.batch_iter(batch_size=batch_size, num_workers=n_threads)

    with logging_redirect_tqdm():
        
        for batch in tqdm(dp_iter, colour='#cc951d'):
            for interval, stats in zip(batch["interval"], batch["stats"]):
                # write stats
                write_stats_to_output(interval, stats, output_bedgraph_filehandle)

                # write footprints
                for thresh, f in output_bed_filehandles.items():
                    for start, end in utils.segment(1.0-stats[:,-1], 1.0-thresh, 3):
                        print(genomic_interval(interval.chrom, interval.start+start, interval.start+end), file=f)

    output_bedgraph_filehandle.close()
    [f.close() for f in output_bed_filehandles.values()]