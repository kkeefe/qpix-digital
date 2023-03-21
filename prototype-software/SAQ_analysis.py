#!/usr/bin/env python3

import os
import sys
import ROOT
import numpy as np

from SAQ_DAQ import N_SAQ_CHANNELS

def filter_saq(resets, SAQ_DIV, ZYBO_FRQ, min_time=10e-6):
    """
    Ensure that resets time differences exclude impossible minimum time from
    length of reset pulse.
    ARGS:
       resets   : list of 32bit timestamp values from Zybo
       SAQ_DIV  : clock division register on the zybo. This should be read in from metadata
       ZYBO_FRQ : zybo norminal frequecy in hertz. This should be read in from metadata
       min_time : time in seconds of reset pulse width, default is 10us from SAQ
    RETURNS:
       rtds : parsed list of reset time differences
    """
    assert isinstance(resets, list), "expect a list of resets to act on"

    # build the reset list with RTDs
    rtds = []
    iLastReset = 0
    for i, r in enumerate(resets[:-1]):
        rtd = resets[i+1] - resets[iLastReset]
        if rtd < 0:
            rtd += 2**32
        if (rtd * SAQ_DIV) / ZYBO_FRQ  > min_time:
            rtds.append(rtd)
            iLastReset = i+1

    return rtds

def hist_rtd(rtd, ch=0):
    """
    Helper function which can take in a list of an RTD (usually output of
    filter_saq method) and return a filled TH1F with an applied gaus fit.

    This histogram method is intended to find the mean of the fit for drift
    current, therefore the algorithm we use will be to find the mean of the list
    of rtd, the std of the values, and we will supply bins of of sqrt(len(rtd))
    with a bin width of 3 sigma before applying a fit. This helps the fitter
    find the region of interest (ROI).
    ARGS:
       rtd : list of RTD in purely timestamp format, conversion into *time*
             should be *last* step
       ch  : number of channel for histogram, which stores histogram name
    RETURNS:
       h   : TH1F histogram
       mu  : mean value of gaus fit
       sig : sigma value of returned gaus fit
    """
    mu, sig = 0, 0

    # build parameters of TH1F
    mean, std = np.mean(rtd), np.std(rtd)
    nbins = int(np.sqrt(len(rtd))) + 1
    h = ROOT.TH1F(f"h_{ch}", "hist", nbins, mean-3*std, mean+3*std)
    for r in rtd:
        h.Fill(r)

    h.Fit("gaus", "RQ")
    mu = h.GetFunction("gaus").GetParameter("Mean")
    sig = h.GetFunction("gaus").GetParameter("Sigma")

    return h, mu, sig

def main(input_file, use_multithread=True):
    """
    Test script for running a simple analysis on ROOT files generated from
    qdb_interface based GUIs like SAQ_DAQ.py

    Supply input file to read, then this script should be able to parse that
    data and supply desired graphics
    """
    if use_multithread:
        ROOT.EnableImplicitMT() # gotta go fast

    # open up ttree into an rdataframe, which is easy to convert to a list
    rdf = ROOT.RDataFrame("tt", input_file)

    # rip everything immediately into a dictionary, where the keys are
    # the branch names
    data = rdf.AsNumpy()

    # numpy arrays of the data we need
    ts = data["Timestamp"]
    masks = data["ChMask"]

    # snag the meta data from the tfile
    # these values are defined in make_root.py script when ROOT file is created
    # from binary
    tf = ROOT.TFile(input_file, "READ")
    meta_data = tf.mt
    SAQ_DIV = -1
    ZYBO_FRQ = -1
    version = 0
    for evt in meta_data:
        SAQ_DIV = evt.SAQ_DIV
        version = evt.Version
        ZYBO_FRQ = evt.Zybo_FRQ
    assert version >= 0x3f, f"version of root file is too old! 0x{version:02x} <= 0x3f"
    assert SAQ_DIV >= 1, f"SAQ_DIV not properly defined: {SAQ_DIV} not >= 1"
    assert ZYBO_FRQ >= 30e6, f"ZYBO_FRQ not properly defined: {ZYBO_FRQ} not >= 30 MHz"

    # make a quick way to ensure the channel we want is in the mask
    m = lambda ch, mask: 1 << ch & mask

    # create a list of the channels and all of their resets
    chResets = [[t for t, mask in zip(ts, masks) if m(ch, mask)] for ch in range(N_SAQ_CHANNELS)]

    # inspect the resets to ensure they make sense
    for ch, resets in enumerate(chResets):
        print(f"ch: {ch+1} has {len(resets)} resets.")

    # chRTD is a list of a list where the first index is the channel number -1
    # (lists are zero counted), which contain the sequential time since last
    # reset data
    chRTD = [filter_saq(r, SAQ_DIV, ZYBO_FRQ) for r in chResets]

    ###################################
    # extra analysis can proceed here #
    ###################################

    # let's make some gaussian histograms of all of the RTDs we have
    outf = ROOT.TFile("saqAna.root", "RECREATE")
    for ch, rtd in enumerate(chRTD):
        h, mean, sig = hist_rtd(rtd, ch)

        # time conversion lambda
        t = lambda x : x*SAQ_DIV/ZYBO_FRQ

        # print and save results
        print(f"Channel-{ch} has mean={t(mean):2e} and sigma={t(sig):2e}")
        h.Write()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("ERROR user must supply input file name")
    else:
        input_file = sys.argv[1]
        if not os.path.isfile(input_file) or os.path.getsize(input_file) == 0:
            print("empty or non-existent input ROOT file", input_file)
            sys.exit(-1)
        main(input_file)
