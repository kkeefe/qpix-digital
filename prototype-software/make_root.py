import ROOT
import sys
import os

import numpy as np
import struct
import datetime
import argparse
from array import array

from qdb_interface import PACKET_HEADER, EXIT_PACKET, ZYBO_FRQ

def main(input_file, output_file, version, start_hits, triggers, saqDiv=0):
    """
    this script should be run from a selection within the GUI
    """
    if not os.path.isfile(input_file) or os.path.getsize(input_file) == 0:
        # print("empty or non-existent binary input file")
        return

    # create dest ROOT file
    tf = ROOT.TFile(output_file, "RECREATE")

    # use this to store the relevant meta tree information about the run
    meta_tt = ROOT.TTree("mt", "metaTree")
    date = array('I', [0])
    version = array('I', [version])
    start_hits = array('I', [start_hits])
    triggers = array('I', [triggers])
    zFrq = array('I', [ZYBO_FRQ])
    sDiv =  array('I', [saqDiv])

    timestamp = os.path.getmtime(input_file)
    time = datetime.date.fromtimestamp(timestamp).strftime('%m-%d-%Y %H:%M:%S')
    date = ROOT.std.string(time)
    meta_tt.Branch("Date", date)
    meta_tt.Branch("Version", version, "version/I")
    meta_tt.Branch("start_hits", start_hits, "start_hits/I")
    meta_tt.Branch("Triggers", triggers, "triggers/I")
    meta_tt.Branch("Zybo_FRQ", zFrq, "ZyboFrq/I")
    meta_tt.Branch("SAQ_DIV", sDiv, "SaqDiv/I")

    # assign meta variables and fill before save
    meta_tt.Fill()

    # create and build the data tree
    tt = ROOT.TTree("tt", "dataTree")
    timestamp = array('I', [0])
    chmask = array('H', [0])
    meta = array('H', [0])
    pid = array('H', [0])

    tt.Branch("Timestamp", timestamp, "timestamp/i")
    tt.Branch("ChMask", chmask, "chan/s")
    tt.Branch("Meta", meta, "meta/s")
    tt.Branch("pid", pid, "pid/s")
    hddr_size = len(PACKET_HEADER)

    # open binary file
    with open(input_file, "rb") as f:
        data = f.read()

    fail = False
    i = 0
    while i < len(data):
        hddr = data[i:hddr_size+i]
        i += hddr_size

        found = hddr==PACKET_HEADER
        if not found:
            print("WARNING unable to find packet hddr:", hddr)
            fail = True
            break
        size = struct.unpack("I", data[i:i+4])[0]
        i += 4
        pid[0] = struct.unpack("<H", data[i+size-2:i+size])[0]

        words = int(size/8)
        for j in range(words):
            timestamp[0] = struct.unpack("<I", data[i:i+4])[0]
            i += 4
            chmask[0] = struct.unpack("<H", data[i:i+2])[0]
            i += 2
            meta[0] = struct.unpack("<H", data[i:i+2])[0]
            i += 2
            tt.Fill()
        # packet_id
        i += 2

    tf.Write()

    # if we read the full binary file correctly, delete it
    # if not fail:
    #     os.remove(input_file)

if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("ERROR should only run by qpix_qdb with required arguments")
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        version = int(sys.argv[3])
        start_hits = int(sys.argv[4])
        stop_hits = int(sys.argv[5])
        saq_div = int(sys.argv[6])
        main(input_file, output_file, version, start_hits, stop_hits, saq_div)
