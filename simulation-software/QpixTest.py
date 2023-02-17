import pytest
import QpixAsic
import QpixAsicArray
import numpy as np
import warnings
import random

random.seed(3)
np.random.seed(2)

from QpixAsic import AsicWord, AsicDirMask, AsicState, AsicConfig

# make testing default input parameters to QpixAsicArray
tRows = 2
tCols = 2
nPix = 16
fNominal = 30e6
pctSpread = 0.05
deltaT = 1e-5
timeEpsilon = 1e-6
timeout = 15e4
hitsPerSec = 20./1.
debug = 0.0
tiledf = None
nTicks = 1700
debug = 0
pTimeout = fNominal/2
## test arguments
dTime = 1e-3
MAX_TIME = 10


## fixtures
@pytest.fixture(params=[(2,2),(2,3), (4,4)])
def qpix_array(request):
    """
    Creates the default QpixAsicArray for the test bed.
    """
    return QpixAsicArray.QpixAsicArray(
                nrows=request.param[0], ncols=request.param[1], nPixs=nPix,
                fNominal=fNominal, pctSpread=pctSpread, deltaT=deltaT,
                timeEpsilon=timeEpsilon, timeout=timeout,
                hitsPerSec=hitsPerSec, debug=debug, tiledf=tiledf)

@pytest.fixture
def qpix_asic():
    """
    Create a default, isolated ASIC
    """
    return QpixAsic.QPixAsic(fOsc=fNominal, nPixels=nPix, randomRate=hitsPerSec, 
                             timeout=timeout, row=None, col=None, isDaqNode=False,
                            transferTicks=nTicks, debugLevel=debug, pTimeout=pTimeout)

@pytest.fixture
def qpix_hits(qpix_array):
    """
    Generate a set of random hits to be created based on the qpix_array that is shared
    """
    hits = []
    for asic in qpix_array:
        nHits = np.random.randint(13)
        hits.append(sorted(np.random.uniform(1e-8, MAX_TIME, nHits)))
    return hits

@pytest.fixture
def tProcRegReq(qpix_array):
    """
    Create a default register request based on the default asic array
    """
    tAsic = qpix_array[0][0]
    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    tProcRegReq = QpixAsic.ProcItem(tAsic, 0, tRegReqByte, 0)
    tProcRegReq.dir = QpixAsic.AsicDirMask.West
    return tProcRegReq

@pytest.fixture
def tRegReqByte():
    """
    Create a interogation packet to send to a specific asic
    """
    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    return tRegReqByte

@pytest.fixture
def qpix_filled_array():
    """
    Create an asic array filled with hits
    """
    qpa = QpixAsicArray.QpixAsicArray(
                    nrows=tRows, ncols=tCols, nPixs=nPix,
                    fNominal=fNominal, pctSpread=pctSpread, deltaT=deltaT,
                    timeEpsilon=timeEpsilon, timeout=timeout,
                    hitsPerSec=hitsPerSec, debug=debug, tiledf=tiledf)

    for asic in qpa:
        asic.InjectHits(np.sort(np.random.uniform(1e-9, MAX_TIME, size=10)))

    return qpa


######################
##  Test Functions  ##
######################
def test_count_array_connections(qpix_array):
    """
    sum up the connections to ensure they make sense
    """
    nConnections, nTrue = 0,0
    for i in range(qpix_array._nrows):
        for j in range(qpix_array._ncols):
            nConnections += qpix_array[i][j].CountConnections()

            # how many horizontal connections there should be
            if i == 0 or i == qpix_array._nrows - 1:
                nTrue += 1
            else:
                nTrue += 2

            # how many vertical connections there should be
            if j == 0 or j == qpix_array._ncols - 1:
                nTrue += 1
            else:
                nTrue += 2

    # include daqnode connection
    assert nConnections == nTrue+1, \
        f"{nConnections} qpa of {qpix_array._nrows},{qpix_array._ncols} mismatch"

def test_asic_receiveByte(qpix_array, tProcRegReq):
    """
    test basic receiveByte condition
    """
    tAsic = qpix_array[0][0]
    tProcRegReq.dir = AsicDirMask.West
    assert tAsic.state == AsicState.Idle, "should begin in idle state"
    b = tAsic.ReceiveByte(tProcRegReq)
    # _ = tAsic.Process(tAsic._absTimeNow)
    assert len(b) == 2, f"{len(b)}, should create two transactions at base-node during interrogation"
    assert tAsic.state == AsicState.Idle, f"{tAsic.state} not in idle after recv @ time {tAsic.relTimeNow}"
    assert tAsic.relTimeNow != tAsic._startTime, f"ASIC did not move forward time during broadcast."

def test_asic_injectHits(qpix_array, tRegReqByte):
    """
    Make sure that asic receives a interogation command, fills the local fifo
    with all of the hits it should.
    """
    # hits to inject
    nHits = 10
    inTime = 1e-4
    hits = np.arange(1e-9, inTime, inTime/nHits)
    # select asic to test
    tAsic = qpix_array[1][1]
    tAsic.InjectHits(hits)
    proc = QpixAsic.ProcItem(tAsic, QpixAsic.AsicDirMask.North, tRegReqByte, inTime, command="Interrogate")
    b = tAsic.ReceiveByte(proc)
    fifoHits = tAsic._localFifo._curSize
    assert fifoHits == nHits, f"inject hits {len(hits)} failed to put all hits within local FIFO {fifoHits} for interrogate"

def test_asic_process_push(qpix_array):
    """
    TODO: test various injectHits and process conditions
    """
    qpix_array.Route("Left", transact=False)
    qpix_array.SetPushState(enabled=True, transact=False)
    endtime, nHits = 1, 10

    # ensure push state
    for asic in qpix_array:
        assert asic.config.EnablePush, "Asic not in push state"
        assert asic.config.SendRemote, "Asic not sending remote"

    # inject
    for asic in qpix_array:
        inHits = sorted(np.random.uniform(1e-10, endtime, nHits))
        asic.InjectHits(inHits)

    # process
    curT, steps = 0, 0
    while curT < endtime + 1e-4 * qpix_array._nrows * qpix_array._ncols:
        curT += qpix_array._deltaT
        qpix_array.Process(curT)
        steps += 1

    for asic in qpix_array:
        assert asic._localFifo._curSize == 0, f"pushed Local FIFO should be empty of hits"
        assert asic.state == AsicState.Idle, f"{asic.state} != IDLE state"

    remote = 0
    for asic in qpix_array:
        remote += len([w for w in asic._remoteFifo._data if w.wordType == AsicWord.DATA])

    words = [word for word in qpix_array._daqNode._localFifo._data]
    nDataWords = [word for word in words if word.wordType == AsicWord.DATA]

    r, c = qpix_array._ncols, qpix_array._nrows
    tHits = r * c * nHits
    msg = f"DaqNode {steps} steps, remote({remote}) still missing hits {len(nDataWords)}/{tHits} at time {qpix_array._timeNow}:{qpix_array._tickNow}"
    assert len(nDataWords) + remote == tHits, msg

    # only a mild warning if there data hasn't made it to the array yet
    if remote > 0:
        warn(f"Push data still has waiting remote data: {remote} at time {qpix_array._timeNow}")


def test_asic_updateTime(qpix_array):
    tAsic = qpix_array[0][0]
    tAsic.UpdateTime(dTime)
    tAsic.UpdateTime(dTime)
    tAsic.UpdateTime(dTime)
    assert tAsic._absTimeNow == dTime, "updating time incorrect. abstime should update to current time"
    assert tAsic.relTimeNow - tAsic.tOsc <= dTime, f"rel time not within one clk cycle of dest time"
    assert isinstance(tAsic.relTicksNow, int), "updating time incorrect. ticks are int"

## test constructors last to ensure that basic construction hasn't changed from
#previous implementations
def test_array_constructor(tRows=2, tCols=3):
    qpa = QpixAsicArray.QpixAsicArray(
                    nrows=tRows, ncols=tCols, nPixs=nPix,
                    fNominal=fNominal, pctSpread=pctSpread, deltaT=deltaT,
                    timeEpsilon=timeEpsilon, timeout=timeout,
                    hitsPerSec=hitsPerSec, debug=debug, tiledf=tiledf)

    assert qpa._nrows == tRows, "Asic Array not creating appropriate amount of rows"
    assert qpa._ncols == tCols, "Asic Array not creating appropriate amount of cols"
    assert qpa._nPixs == nPix, "Asic Array not creating correct amount of pixels"
    assert isinstance(qpa._queue, QpixAsic.ProcQueue), "Array requires processing queue"

def test_asic_constructor(qpix_array):
    tAsic = qpix_array[0][0]
    assert tAsic.nPixels == nPix, "incorrect amount of pixels on ASIC"
    assert isinstance(tAsic.config, QpixAsic.AsicConfig), "asic config, incorrect type"

def test_asic_time_update(qpix_asic):
    tAsic = qpix_asic
    dT = 2e-6
    tAsic.UpdateTime(dT)
    tAsic.UpdateTime(dT/2)
    assert tAsic._absTimeNow == dT, "update time function not working"

def test_transaction_width(qpix_array):
    """
    ensure that the default QPByte has a reasonable transaction length
    """
    byte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    for asic in qpix_array:
        assert asic.tOsc * byte.transferTicks < 1e-4, "Transaction time too long!"

def test_asic_full_readout(qpix_array):
    """
    Full readout test of a remote ASIC within qpix_array, this asserts
    that different ASIC states are as they should be, and that the 
    time elapsed from each state makes sense

    NOTE: this method currently depends on a deprecated timeout method
    for calculating the time in the final step to transition back to the idle state
    """
    nHits = 10

    qpix_array.SetSendRemote(enabled=False, transact=False)

    inTime = qpix_array[0][0].transferTime + qpix_array[0][1].transferTime
    hits = np.arange(1e-9, inTime, inTime/nHits) # don't start at 0 time
    # ensure sendremote == false

    # select asic to test
    tAsic = qpix_array[1][1]
    prevState = tAsic.state
    assert prevState == AsicState.Idle, "Initial state of ASIC should be IDLE"
    tAsic.InjectHits(hits)
    prevState = tAsic.state
    assert prevState == AsicState.Idle, "pull ASIC should remain in IDLE until receiving an interrogate"

    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    proc = QpixAsic.ProcItem(tAsic, QpixAsic.AsicDirMask.North, tRegReqByte, inTime, command="Interrogate")
    _ = tAsic.ReceiveByte(proc)
    h = tAsic.Process(inTime)

    # transmit local
    prevState = tAsic.state
    eT = tAsic._absTimeNow
    dT = tAsic._absTimeNow
    assert prevState == AsicState.TransmitLocal, "should begin transmitting local data after receiving an Interrogate"
    fifoHits = tAsic._localFifo._curSize
    hs = []
    while fifoHits > 0:
        dT += deltaT
        h = tAsic.Process(dT)
        hs.extend(h)
        fifoHits = tAsic._localFifo._curSize

    # transmit finish word
    eT += sum([tAsic.tOsc * h[2].transferTicks for h in hs])
    prevState = tAsic.state
    assert prevState == AsicState.Finish, "finish state should follow sending all local data"
    nFinish, procs = 0, 0
    hits = []
    while tAsic.state == prevState:
        dT = tAsic._absTimeNow + deltaT
        l = tAsic.Process(dT)
        nFinish += len(l)
        hits.extend(l)
        procs += 1
    times = [tAsic.tOsc * hit[2].transferTicks for hit in hits]
    eT += sum(times)
    assert round(eT, 6) == round(tAsic._absTimeNow, 6), "Incorrect expected time during finish word"

    # transmit remote state, should be length of timeout
    prevState = tAsic.state
    assert prevState == AsicState.TransmitRemote, "Remote state should follow end word"
    nRemote = 0
    while tAsic.state == prevState:
        dT = tAsic._absTimeNow + deltaT
        nRemote += len(tAsic.Process(dT))

    # back to IDLE state
    eT += tAsic.tOsc * tAsic.config.timeout
    prevState = tAsic.state
    assert prevState == AsicState.Idle, "Finished state should be back in IDLE"
    if tAsic._remoteFifo._totalWrites > 0:
        assert round(eT, 6) <= round(tAsic._absTimeNow, 6), "Different expected process times during Final step of full readout"
    else:
        assert round(eT, 6) == round(tAsic._absTimeNow, 6), "Different expected process times during Final step of full readout"

def test_process_array(qpix_array):
    """
    Ensure that the Hidden ProcessArray method for qpix_array behaves as expected
    """
    time_end = 1
    qpix_array.Process(time_end)
    assert qpix_array._timeNow - qpix_array._deltaT < time_end, "Process array too far forward in time"
    assert qpix_array._alert != 1, "alert thrown during normal process"


def test_asic_fromDir():
    """
    Test AsicDirMask possibilities
    """
    for i, mask in enumerate(AsicDirMask):
        dirmask = mask
        fromdir = AsicDirMask((i+2)%4)

        msg = f"Dir Mask Error at {dirmask}"
        if dirmask == AsicDirMask.East:
            assert fromdir == AsicDirMask.West, msg
        if dirmask == AsicDirMask.West:
            assert fromdir == AsicDirMask.East, msg
        if dirmask == AsicDirMask.North:
            assert fromdir == AsicDirMask.South, msg
        if dirmask == AsicDirMask.South:
            assert fromdir == AsicDirMask.North, msg


def test_asic_route_snake(qpix_array):
    """
    Make sure that the snake routing provides the expected connections
    """
    r="Snake"
    qpix_array.Route(r, transact=False)
    assert qpix_array.RouteState is not None, "did not set any route state"

    # test config and routing
    for asic in qpix_array:
        assert isinstance(asic.config, AsicConfig), "Did not enable correct config type to ASIC.config"
        assert asic.config.ManRoute is True, "Route state did not enable manual routing"

    # test connection directions
    rows = qpix_array._nrows
    cols = qpix_array._ncols
    for i in range(rows):
        for j in range(cols):
            asic = qpix_array._asics[i][j]
            assert asic.row == i, "Asic Row not aligned"
            assert asic.col == j, "Asic Col not aligned"
            # top row should all be west to DaqNode
            if i == 0:
                assert asic.config.DirMask == AsicDirMask.West, "Top Row misaligned"
            # odd rows are all east, except for last column
            elif i%2 == 1 and j != cols-1:
                assert asic.config.DirMask == AsicDirMask.East, f"{i} Row misaligned, should be East"
            # even rows are all west, except for first column
            elif i%2 == 0 and j != 0:
                assert asic.config.DirMask == AsicDirMask.West, f"{i} Row misaligned, should be West"
            # final edge column asics should be north to get to next row
            elif j == cols-1 or j == 0:
                assert asic.config.DirMask == AsicDirMask.North, f"({i},{j}) ASIC misaligned, should be North"
            else:
                assert False, "WARNING, uncaught condition of testing asign alignment"

def test_asic_route_left(qpix_array):
    """
    Make sure that the snake routing provides the expected connections
    """
    r="Left"

    qpix_array.Route(r, transact=False)
    assert qpix_array.RouteState is not None, "Left did not set any route state"

    # test config and routing
    for asic in qpix_array:
        assert isinstance(asic.config, AsicConfig), "Left Did not enable correct config type to ASIC.config"
        assert asic.config.ManRoute is True, "Route state did not enable manual routing"

    # test connection directions
    rows = qpix_array._nrows
    cols = qpix_array._ncols
    for i in range(rows):
        for j in range(cols):
            asic = qpix_array._asics[i][j]
            assert asic.row == i, "Asic Row not aligned"
            assert asic.col == j, "Asic Col not aligned"
            # left column, except 0,0 should be north
            if j == 0 and i != 0:
                assert asic.config.DirMask == AsicDirMask.North, f"({i},{j}) ASIC in Column misaligned, should be north"
            else:
                assert asic.config.DirMask == AsicDirMask.West, f"Row misaligned, should be West"

def warn(msg):
    """
    user warning method
    """
    warnings.warn(UserWarning(msg))
    return 1


def ensure_hits(hits, array):
    """
    Helper function that is used on test_daq_read methods to ensure that
    all of the FIFOs and Daq FIFO's make sense.

    This functinon will raise any logical warnings on FIFOs within the ASIC
    based on the hits array.

    A successfully processed array is one where all FIFOs are empty, and
    all of this data has been sent to and received by the DAQNode.
    """

    b = 0

    # make sure that all of the ASIC FIFOs are empty
    for hit, asic in zip(hits, array):
        hddr = f"ASIC ({asic.row},{asic.col}) "
        if asic._localFifo._curSize != 0:
            msg = hddr + f" local fifo not empty!"
            b = warn(msg)
        if asic._remoteFifo._curSize != 0:
            msg = hddr + f" remote fifo not empty!"
            b = warn(msg)
        if len(asic._times) != 0:
            msg = hddr + f" times have NOT been read!"
            b = warn(msg)
        assert asic._localFifo._totalWrites == len(hit), f"{msg} not all hits counted as writes"

    # Build up the amount of data words and event end words that should have
    # been received
    maxTime, nHits = 0, 0
    for hit in hits:
        if len(hit) > 0:
            nHits += len(hit)
            maxTime = np.max(hit) if np.max(hit) > maxTime else maxTime
    daqHits = array._daqNode._localFifo._dataWords
    evt_end_words = 0
    for asic in array:
        for (state, _, _) in asic.state_times:
            if state == AsicState.Finish:
                evt_end_words += 1
    daq_evt_ends = 0
    for data in array._daqNode._localFifo._data:
        if data.wordType == AsicWord.EVTEND:
            daq_evt_ends += 1

    hddr = "DaqNode warning, "
    bWarn = False
    if daqHits != nHits:
        msg = hddr + f"DaqNode did not receive all hits before {maxTime:0.2f}: {daqHits}/{nHits}"
        b = warn(msg)
    if daq_evt_ends != evt_end_words:
        msg = hddr + f"mismatch on event end words, recv {daq_evt_ends} : sent {evt_end_words}"
        b = warn(msg)

    # a succesful ensure_hits is one where no warnings are raised: b = 0
    return b == 0

def run_array_interrogate(array, maxTime, int_prd):
    """
    Helper function to provide easily tracked debug variables and wrapper for
    interrogate procedure of a QpixArray.
    """
    dT = 0
    while dT <= maxTime+int_prd:
        dT += int_prd
        array.Interrogate(int_prd)

    # continue processing array until all data should be
    # readout based on routing
    if array.RouteState.lower() == 'snake':
        procT = array._ncols * array._nrows * 1e-3
    else:
        procT = (array._ncols + array._nrows) * 1e-3
    while dT <= 10*procT + maxTime + int_prd:
        dT += array._deltaT
        array.Process(dT)

    # debuger can check variables after an interrogate here
    t_remote, t_local = 0, 0
    tr_remote, tr_local = 0, 0
    tr_end = 0
    tr_end_l = []
    for asic in array:
        t_remote += asic._remoteFifo._curSize
        t_local += asic._localFifo._curSize
        tr_remote += asic._remoteFifo._totalWrites
        tr_local += asic._localFifo._totalWrites
        for(state, _, time) in asic.state_times:
            if state == AsicState.Finish:
                tr_end += 1
                tr_end_l.append((asic.row, asic.col, time, asic._localFifo._totalWrites))

    tr_end_l.sort(key=lambda x: x[2], reverse=False)
    for asic in array:
        if asic.state != AsicState.Idle:
            print("WARNING, asic not in IDLE state after finish processing")

    assert array._queue.Length() == 0, "Still processing to happen.."

    return array


## Main Simulation Procedsures for an array based on routing
def test_daq_read_data_snake(qpix_array, qpix_hits, int_prd=0.5):
    """
    Ensure that all of the injected hits make it to be read at the DaqNode with
    the procedure of normal interrogation methods to qpix_array.

    This test will count all of the transactions at the local and
    remote FIFOs in the array to ensure tha the number of transactions make
    sense.
    """
    rows, cols = qpix_array._nrows, qpix_array._ncols
    r = "Snake"
    qpix_array.Route(r, transact=False)
    assert len(qpix_hits) == rows * cols, "number of injected hits doesn't match array size"

    maxTime = 0
    for hit, asic in zip(qpix_hits, qpix_array):
        if len(hit) > 0:
            maxTime = np.max(hit) if maxTime < np.max(hit) else maxTime 
            asic.InjectHits(hit)

    # run the interrogate procedure
    qpix_array = run_array_interrogate(qpix_array, maxTime, 0.5)

    # compare fifos with expected input hits
    good_hits = ensure_hits(qpix_hits, qpix_array)
    
    # snake means every ASIC is connected in a long line and should see every # other ASIC
    if rows%2 == 0:
        cur_asic = qpix_array[rows-1][0]
    else:
        cur_asic = qpix_array[rows-1][cols-1]

    asicCnt, transactions = 1, 0
    while asicCnt < rows*cols:

        next_asic = cur_asic.connections[cur_asic.config.DirMask.value].asic
        if next_asic.isDaqNode:
            break

        # Count the number of remote transactions this ASIC sent to its neighbor
        for (state, _, _) in cur_asic.state_times:
            if state == AsicState.Finish:
                transactions += 1
        transactions -= cur_asic._remoteFifo._curSize
        transactions += (cur_asic._localFifo._totalWrites - cur_asic._localFifo._curSize)

        remote_writes = next_asic._remoteFifo._totalWrites
        msg = f"snake trans. cnt error @ ({next_asic.row},{next_asic.col}) {transactions}/{remote_writes}"
        assert remote_writes == transactions, msg

        asicCnt += 1
        cur_asic = next_asic

    assert asicCnt == rows*cols, f"didnt count all ASICs. cnt: {asicCnt} != size: {rows*cols}"

    # in the event that no FIFOs are spitting warnings, we test
    # the received DAQ data for validity
    if good_hits:
        pass

def test_daq_read_data_left(qpix_array, qpix_hits, int_prd=0.5):
    """
    Ensure that all of the injected hits make it to be read at the DaqNode with
    the procedure of normal interrogation methods to qpix_array.
    """
    rows, cols = qpix_array._nrows, qpix_array._ncols
    r = "Left"
    qpix_array.Route(r, transact=False)
    assert len(qpix_hits) == rows * cols, "number of injected hits doesn't match array size"

    maxTime = 0
    for hit, asic in zip(qpix_hits, qpix_array):
        if len(hit) > 0:
            maxTime = np.max(hit) if maxTime < np.max(hit) else maxTime 
            asic.InjectHits(hit)

    # run the interrogate procedure
    qpix_array = run_array_interrogate(qpix_array, maxTime, int_prd)

    # compare fifos with expected input hits
    good_hits = ensure_hits(qpix_hits, qpix_array)

    # left means every left and not 0,0 ASIC sends data north, all others send west
    # each row should be summed individually
    for row in reversed(range(rows)):

        transactions = 0
        col = qpix_array._ncols - 1

        while col > 0:

            cur_asic = qpix_array[row][col]
            next_asic = cur_asic.connections[cur_asic.config.DirMask.value].asic

            if next_asic.isDaqNode:
                break

            transactions += (cur_asic._localFifo._totalWrites - cur_asic._localFifo._curSize)
            for(state, _, _) in cur_asic.state_times:
                if state == AsicState.Finish:
                    transactions += 1
            transactions -= cur_asic._remoteFifo._curSize
            
            # test transactions for this ASIC
            if next_asic.col == 0:
                south_asic = next_asic.connections[AsicDirMask.South.value].asic
                if south_asic is not None:
                    transactions += (south_asic._remoteFifo._totalWrites - south_asic._remoteFifo._curSize)
                    transactions += (south_asic._localFifo._totalWrites - south_asic._localFifo._curSize)
                    for(state, _, _) in south_asic.state_times:
                        if state == AsicState.Finish:
                            transactions += 1

            frac = f"{transactions}/{next_asic._remoteFifo._totalWrites}"
            msg = f"left trans. cnt error @ ({next_asic.row},{next_asic.col}) {frac}"
            assert next_asic._remoteFifo._totalWrites == transactions, msg

            col = next_asic.col

    # in the event that no FIFOs are spitting warnings, we test
    # the received DAQ data for validity
    if good_hits:
        pass

def test_asic_update_time(qpix_array):
    """
    Ensure that there are no malicious changes to UpdateTime method

    Each ASIC starts at some random phase: _startTime.
    The *only* method that should change an ASIC's time is UpdateTime()

    UpdateTime receives the "true" simulation time, which is based on the
    QPixArray / DaqNode time.

    An ASIC simply calculates the number of clocks that have transpired
    since its _startTime until this new absolute time via the CalcTicks()
    method.

    Additionally, it should only be possible to move an ASIC's time forward.

    Finally, UpdateTime() can also mark certain Tx lines as busy.
    this prevents the simulation from trying sending more than one packet
    at the same time in the same direction.
    """
    tAsic = qpix_array[0][0]

    # input hits within a transaction window
    startT = tAsic._startTime
    endT = startT + 2e-9
    nHits = 10
    inHits = sorted(np.random.uniform(startT, endT, nHits))
    tAsic.InjectHits(inHits)

    # create the broadcast byte
    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    proc = QpixAsic.ProcItem(tAsic, QpixAsic.AsicDirMask.West, tRegReqByte, endT, command="Interrogate")
    b = tAsic.ReceiveByte(proc)

    # prevent backward time traversal
    tAsic.UpdateTime(-1)
    assert tAsic.relTimeNow > 0, "UpdateTime: Bad Time, Backwards Traversal"
    assert tAsic.relTicksNow > 0, "UpdateTime: Bad Ticks, Backwards Traversal"

    # ensure correct tick calculation
    hits = tAsic.Process(tAsic.relTimeNow+qpix_array._deltaT)

def test_asic_tick_cnt(qpix_array):
    """
    ensure that an injected hit calculates that correct time
    """

    # build the ASIC and input the hits
    tAsic = qpix_array[0][0]
    tHits, nHits = 3e-3, 1500
    inTime = tHits + qpix_array._deltaT
    inHits = sorted(np.random.uniform(1e-8, tHits, nHits))
    tAsic.InjectHits(inHits)

    # send the interrogate to the base-node
    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    proc = QpixAsic.ProcItem(tAsic, QpixAsic.AsicDirMask.West, tRegReqByte, inTime, command="Interrogate")
    b = tAsic.ReceiveByte(proc)

    # read the data back and make sure the base-node processes correctly
    procTime = tHits + 2000 * nHits * tAsic.tOsc
    outHits = tAsic.Process(procTime)
    assert len(outHits) == len(inHits), "Did not read all of the injected hits"
    for inHit, outHit in list(zip(inHits, outHits)):
        assert inHit == outHit[2].data, "input hit did not get correctly stored in out hit data"
        tick = int((inHit - tAsic._startTime)/tAsic.tOsc) + 1
        assert tick == outHit[2].timeStamp, "input timestamp was not calcuated correctly"

if __name__ == "__main__":

    # qpix_array = QpixAsicArray.QpixAsicArray(
    #             nrows=tRows, ncols=tCols, nPixs=nPix,
    #             fNominal=fNominal, pctSpread=pctSpread, deltaT=deltaT,
    #             timeEpsilon=timeEpsilon, timeout=timeout,
    #             hitsPerSec=hitsPerSec, debug=debug, tiledf=tiledf)

    import matplotlib.pyplot as plt
    rows = 2
    cols = 2
    nHits = 10
    maxTime = 1 # time to idle for

    # make nHits for each asic
    asicX = sorted([i for i in range(rows)]*cols)
    asicY = [i for i in range(cols)]*rows
    asicHits = [sorted(list(np.random.rand(nHits) * maxTime)) for i in range(rows*cols)]

    # make some 'fake' df hits to read in
    testDF = {}
    testDF["nrows"] = rows
    testDF["ncols"] = cols
    testDF["hits"] = tuple(zip(asicX, asicY, asicHits))

    testingArrays = []
    qpa = QpixAsicArray.QpixAsicArray(rows, cols, tiledf=testDF, debug=0)
    qpa.Route(route="snake", timeout=15e3, transact=False)
    qpa.SetPushState(enabled=True, transact=False)
    testingArrays.append(qpa)

    fig, axs = plt.subplots(len(testingArrays),3, figsize=(17.5,5*len(testingArrays)))

    for ti, tile in enumerate(testingArrays):

        # go for 10ms after max time to ensure all of the events make it to the daqNode
        tile.IdleFor(maxTime + 1)

        transactData = PrintTransactMap(tile, silent=True)

        # # build up 2d array of transactions to store in heat maps
        localData = np.zeros((rows,cols), dtype=np.int32)
        localT = transactData["LocalT"]
        for i, j, T in localT:
            localData[i][j] = T

        remoteDataT = np.zeros((rows,cols), dtype=np.int32)
        remoteT = transactData["RemoteT"]
        for i, j, T in remoteT:
            remoteDataT[i][j] = T

        remoteDataM = np.zeros((rows,cols), dtype=np.int32)
        remoteM = transactData["RemoteMax"]
        for i, j, T in remoteM:
            remoteDataM[i][j] = T

        # max number of transactions in this data time
        maxActivity = maxTime / (1/50e6 * 1800)

        # construct the heatmaps
        heatMap(localData, rows, cols, ax=axs[ti, 0], vmin=0, vmax=128, header="ASIC Local Hits")
        heatMap(remoteDataM, rows, cols, ax=axs[ti, 1], vmin=0, vmax=256, header="ASIC Remote MAX")
        heatMap(remoteDataT, rows, cols, ax=axs[ti, 2], vmin=0, vmax=maxActivity, header="Asic Remote Transactions")

        # look at how many calls to proc queue are made
        print(f"{ti} called proc {tile._queue.processed} times.")

        # NOTE: AsicKey deprecated!
        # for asicKey, hitData in tile._daqNode.hitData.items():
        #     print(f"Received {len(hitData)} hits from {asicKey}.")

    fig.tight_layout()
    plt.show()

    input("test")
