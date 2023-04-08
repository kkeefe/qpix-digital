import multiprocessing as mp
import QpixAsicArray as qparray
from QpixAsicArray import PrintTransactMap
from QpixAsic import QPFifo
import pandas as pd

## This Script reads in the output of radiogenicNB.ipynb (which reads in output
## from radiogenic ROOT data) and then executes a parameter space search
## utilizing multiprocessing to speed things up

MAXTIME = 10 # time to integrate for, or time radiogenic data is based on

DAQ_KEY = "DaqData"
INPUT_FILE = "tiledf05_10x14.json"

def makeData(tile, r, t, int_prd, nHardInt):
    """
    Helper function which will extrct relevant data from a processed tile to a
    serialized, useful format to put onto the mp.queue

    This function must be useful to extract for comparative analysis based 
    on either a push or a pull architecture.
    """

    # memoize lists to input serialized data
    daqBytes = list([daqbyte for daqbyte in tile._daqNode._localFifo._data])
    asics = list([asic for asic in tile])

    data = {
        "Architecture":[tile.push_state for asic in asics],
        "Route":[tile.RouteState for asic in asics],
        # Flatten all run control variables
        "IntPeriod":[int_prd for asic in asics],
        "Timeout":[t for asic in asics],
        "nHardInt":[nHardInt for asic in asics],
        # asic data
        "AsicX":[asic.col for asic in asics],
        "AsicY":[asic.row for asic in asics],
        "Frq":[asic.fOsc for asic in asics],
        "Start Time":[asic._startTime for asic in asics],
        "Rel Time":[asic.relTimeNow for asic in asics],
        "Rel Tick":[asic.relTicksNow for asic in asics],
        # local data
        "Local Hits":[asic._localFifo._totalWrites for asic in asics],
        "Local Max":[asic._localFifo._maxSize for asic in asics],
        "Local Remain":[asic._localFifo._curSize for asic in asics],
        # remote data
        "Remote Transactions":[asic._remoteFifo._totalWrites for asic in asics],
        "Remote Max":[asic._remoteFifo._maxSize for asic in asics],
        "Remote Remain":[asic._remoteFifo._curSize for asic in asics],

        # daq data to be stored its own 
        DAQ_KEY: 
        {   
            "Route":[r for d in daqBytes],
            "Timeout":[t for d in daqBytes],
            "Int_period":[int_prd for d in daqBytes],
            "nHardInt":[nHardInt for d in daqBytes],
            "AsicX":[daqbyte.row for daqbyte in daqBytes],
            "AsicY":[daqbyte.col for daqbyte in daqBytes],
            "WordType":[daqbyte.wordType for daqbyte in daqBytes],
            "DaqTime":[daqbyte.daqT for daqbyte in daqBytes],
            "Timestamp":[daqbyte.qbyte.timeStamp for daqbyte in daqBytes],
            "SimTime":[daqbyte.qbyte.data for daqbyte in daqBytes],
            "channels":[daqbyte.qbyte.channelMask for daqbyte in daqBytes]
        }
    }

    return data

def pushTile(queue, r, int_time=MAXTIME):
    """
    Push script to run. should be based on QpixTest format
    """
    import numpy as np
    np.random.seed(2)

    inFile = INPUT_FILE

    import codecs, json
    obj_text = codecs.open(inFile, 'r').read()
    readDF = json.loads(obj_text)
    tile = qparray.QpixAsicArray(0, 0, tiledf=readDF, deltaT=20e-6)

    tile.Route(r, transact=False)
    tile.SetPushState(enabled=True, transact=False)

    curT = 0
    while curT < MAXTIME + 1:
        curT += tile._deltaT
        tile.Process(curT)

    queue.put(makeData(tile, r, t=0, int_prd=0, nHardInt=0))

def runTile(queue, r, t, periods, int_time=MAXTIME):
    """
    basic function to run a tile with an integration period, over a specified time

    store processed tile on output queue to send back to main thread.
    """
    
    import numpy as np
    np.random.seed(2)

    inFile = INPUT_FILE
    int_prd = periods[0]
    nHardInt = periods[1]

    import codecs, json
    obj_text = codecs.open(inFile, 'r').read()
    readDF = json.loads(obj_text)
    tile = qparray.QpixAsicArray(0, 0, tiledf=readDF, timeout=t, deltaT=20e-6)

    # configure other meta cases of the tile
    if t == 0:
        tile.SetSendRemote(enabled=True, transact=False)

    tile.Route(r, transact=False)

    dT, nInt = 0, 0
    while dT < int_time + int_prd:
        dT += int_prd
        if nInt % nHardInt == 0:
            tile.Interrogate(int_prd, hard=True)
        else:
            tile.Interrogate(int_prd, hard=False)
        nInt += 1

    queue.put(makeData(tile, r, t, int_prd, nHardInt))

def saveData(tile, daq_data=None, data=None):
    """
    Helper function to remove dictionary data from the makeData function
    and to store the relevant data into output dictionaries.

    outputs should be sent to a pd dataframe and then stored in csv.
    """

    if daq_data is None:
        daq_data = {}
    else:
        assert isinstance(daq_data, dict)

    if data is None:
        data = {}
    else:
        assert isinstance(data, dict)

    # remove the daqData key from this
    daq_tile = tile.pop(DAQ_KEY, None)
    if daq_tile is not None:
        for k,v in daq_tile.items():
            if daq_data.get(k) is not None:
                daq_data[k].extend(v)
            else:
                daq_data[k] = v

    # build the transaction csv
    for k,v in tile.items():
        if data.get(k) is not None:
            data[k].extend(v)
        else:
            data[k] = v

    return daq_data, data



def main(seed=2):
    """
    This script should be called and run as an executable.
    """

    # define the ranges of parameters to test
    int_periods = [0.2, 0.5, 0.75, 1, 2]
    nHardInt = [5, 10, 20]
    routes = ["left", "snake"]
    timeouts = [0, 15e3, 15e4, 15e5]
    periods = [(i,j) for i in int_periods for j in nHardInt]
    ncpu = 20

    # place holder for the completed tiles
    tile_queue = mp.Queue()

    # create a list of all of the processes that need to run.
    args = [(i, j, k) for i in routes for j in timeouts for k in periods]
    pull_args = [r for r in routes]

    # pull architecture procs
    procs = [mp.Process(target=runTile, args=(tile_queue, *arg)) for arg in args]

    # push archiecture procs
    procs.extend([mp.Process(target=pushTile, args=(tile_queue, arg)) for arg in pull_args])

    nProcs = len(procs)
    print(f"begginning processing of {nProcs} tiles.")

    completeProcs = 0
    runningProcs, pTiles = [], []
    while completeProcs < nProcs:

        # fill running procs until we use all cpu cores
        while len(runningProcs) <= ncpu and len(procs) > 0:
            runningProcs.append(procs.pop())

        # ensure all of the running procs have started
        for ip, p in enumerate(runningProcs):
            if p.pid is None:
                p.start()
            elif p.exitcode is not None:
                runningProcs.pop(ip)

        # wait to get anything on the queue
        pTiles.append(tile_queue.get())
        completeProcs = len(pTiles)
        print(f"Completed tile {completeProcs}, {completeProcs/nProcs*100:0.2f}%..")


    # build all of the serialized data from the MP outputs
    daq_data, data = {}, {}
    for tile in pTiles:
        daq_data, data = saveData(tile, daq_data, data)

    # create the dataframe from from these dictionaries
    df = pd.DataFrame.from_dict(data)
    daq_df = pd.DataFrame.from_dict(daq_data)

    # save the dataframe into a json for safe keeping
    df.to_csv("output_df.csv")
    daq_df.to_csv("output_daq_df.csv")


if __name__ == "__main__":
    main()
