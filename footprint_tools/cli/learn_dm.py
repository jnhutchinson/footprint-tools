import sys

import argh
from argh.decorators import named, arg

import numpy as np
import scipy as sp
import pandas as pd
import pysam

from footprint_tools.data.process import process
from footprint_tools.data.utils import numpy_collate_concat

from genome_tools import bed, genomic_interval

from footprint_tools import cutcounts
from footprint_tools.modeling import bias, predict, dispersion

from footprint_tools.cli.utils import tuple_ints, get_kwargs

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import logging
logger = logging.getLogger(__name__)

# kill numpy warnings
np.seterr(all="ignore")

class expected_counts(process):
    """
    """
    def __init__(self, interval_file, bam_file, fasta_file, bm, **kwargs):
       
        self.intervals = pd.read_table(interval_file, header=None)

        logger.info(f"BED file contains {len(self.intervals):,} regions")

        self.bam_file = bam_file
        self.fasta_file = fasta_file
        self.bm = bm

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
            ],
            kwargs)

        self.counts_reader = None
        self.fasta_reader = None
        self.count_predictor = None

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

        return np.column_stack(exp, obs))

@named('learn_dm')
@arg('interval_file', 
    help='File path to BED file')
@arg('bam_file', 
    help='Path to BAM-format tag alignment file')
@arg('fasta_file',
    help='Path to genome FASTA file (requires associated FASTA index in same folder; see documentation on how to create an index)')
@arg('--bias_model_file',
    help='Use a k-mer model for local bias (supplied by file). If argument is not provided the model defaults to uniform sequence bias.')
@arg('--min_qual',
    help='Ignore reads with mapping quality lower than this threshold',
    default=1)
@arg('--remove_dups',
    help='Remove duplicate reads',
    default=False)
@arg('--keep_qcfail',
    help='Keep QC-failed reads',
    default=False)
@arg('--bam_offset',
    help='BAM file offset (enables support for other datatypes -- e.g. Tn5/ATAC)',
    default=(0,-1),
    type=tuple_ints)
@arg('--half_win_width',
    help='Half window width to apply bias model',
    default=5)
@arg('--n_threads',
    help='Number of processors to use',
    default=16)
@arg('--batch_size',
    help='Batch size of intervals to process',
    default=100)
@arg('--outfile',
    dest='output_file',
    default='out.bedgraph',
    help='Output file path')
def run(interval_file,
        bam_file,
        fasta_file,
        bias_model_file=None,
        min_qual=1,
        remove_dups=False,
        keep_qcfail=False,
        bam_offset=(0, -1),
        half_win_width=5,
        n_threads=8,
        batch_size=100,
        output_file='dm.json'):
    """Learn a negative binomial dispersion model from data corrected for intrinsic sequence preference.
    
    Output:
        dm.json - a serialized model in JSON format to file in current working directory
    """

    proc_kwargs = {
        "min_qual": min_qual,
        "remove_dups": remove_dups,
        "remove_qcfail": ~keep_qcfail,
        "offset": bam_offset,
        "half_win_width": half_win_width,
    }

    # Load bias model (if specified), otherwise use the uniform model
    if bias_model_file:
        logger.info(f"Loading bias model from file {bias_model_file}")
        bm = bias.kmer_model(bias_model_file)
    else:
        logger.info(f"No bias model file specified -- using uniform model")
        bm = bias.uniform_model()

    dp = expected_counts(interval_file, bam_file, fasta_file, bm, **proc_kwargs)
    dp_iter = dp.batch_iter(batch_size=batch_size, collate_fn=numpy_collate_concat, num_workers=n_threads)

    hist_size = (200, 1000)
    hist = np.zeros(hist_size, dtype=int)

    with logging_redirect_tqdm():
        for cnts in tqdm(dp_iter, colour='#cc951d'):
            for i in range(cnts.shape[0]):
                try:
                    # expected, observed
                    hist[int(cnts[i,0]),int(cnts[i, 1])] += 1
                # ignore counts bigger than histogram bounds
                except IndexError:
                    pass

    print(hist)

