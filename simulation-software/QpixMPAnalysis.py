import multiprocessing as mp
import QpixAsicArray as qparray
from QpixAsicArray import PrintTransactMap
from QpixAsic import QPFifo
import pandas as pd

## This Script reads in the output of radiogenicNB.ipynb (which reads in output from radiogenic ROOT data)
## and then executes a parameter space search utilizing multiprocessing to speed things up

MAXTIME = 10 # time to integrate for, or time radiogenic data is based on

def runTile(queue, r, t, int_prd, int_time=MAXTIME):
    """
    basic function to run a tile with an integration period, over a specified time

    store processed tile on output queue to send back to main thread.
    """
    
    import numpy as np
    np.random.seed(2)

    # set up the input data / tile information
    inFile = "tiledf05.json"
    # inFile = "tiledf05_10x14.json"

    import codecs, json
    obj_text = codecs.open(inFile, 'r').read()
    readDF = json.loads(obj_text)
    nrows = readDF["nrows"]
    ncols = readDF["ncols"]
    tile = qparray.QpixAsicArray(0, 0, tiledf=readDF, timeout=t, deltaT=20e-6)
    tile.Route(r, transact=False)

    dT = 0
    while dT < int_time:
        dT += int_prd
        tile.Interrogate(dT)

    data = {
        "Architecture":[tile.push_state for asic in tile],
        "Route":[tile.RouteState for asic in tile],
        # different architectures use different parameters
        # a pull architecture requires (integration frequency, timeout)
        # a push architecture requires (wait time?)
        "Params":[(int_prd, t) for asic in tile],
        "AsicX":[asic.col for asic in tile],
        "AsicY":[asic.row for asic in tile],
        # asic data
        "Frq":[asic.fOsc for asic in tile],
        "Start Time":[asic._startTime for asic in tile],
        "Rel Time":[asic.relTimeNow for asic in tile],
        "Rel Tick":[asic.relTicksNow for asic in tile],
        # local data
        "Local Hits":[asic._localFifo._totalWrites for asic in tile],
        "Local Max":[asic._localFifo._maxSize for asic in tile],
        "Local Remain":[asic._localFifo._curSize for asic in tile],
        # remote data
        "Remote Transactions":[asic._remoteFifo._totalWrites for asic in tile],
        "Remote Max":[asic._remoteFifo._maxSize for asic in tile],
        "Remote Remain":[asic._remoteFifo._curSize for asic in tile],
    }

    queue.put(data)


def main(seed=2):
    """
    This script should be called and run as an executable.
    """

    # define the ranges of parameters to test
    # int_periods = np.linspace(0.1,2,10)
    # routes = ["left", "snake"]
    # timeouts = [15e3, 30e3, 15e4, 30e4, 15e5, 30e5]
    int_periods = [0.2, 0.5, 0.75, 1, 2]
    routes = ["left", "snake"]
    timeouts = [15e3, 15e4, 15e5]
    ncpu = 20

    # place holder for the completed tiles
    tile_queue = mp.Queue()

    # create a list of all of the processes that need to run.
    args = [(i, j, k) for i in routes for j in timeouts for k in int_periods]
    procs = [mp.Process(target=runTile, args=(tile_queue, *arg)) for arg in args]
    nProcs = len(procs)
    print(f"begginning processing of {nProcs} tiles.")

    completeProcs = 0
    runningProcs, pTiles = [], []
    while completeProcs < nProcs:

        # fill running procs until we use all cpu threads
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
    data = {}
    for tile in pTiles:
        for k,v in tile.items():
            if data.get(k) is not None:
                data[k].extend(v) 
            else:
                data[k] = v

    # create the dataframe from from these dictionaries
    df = pd.DataFrame.from_dict(data)

    # save the dataframe into a json for safe keeping
    df.to_csv("output_df.csv")


if __name__ == "__main__":
    main()