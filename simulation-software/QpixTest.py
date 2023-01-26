import pytest
import QpixAsic
import QpixAsicArray
import numpy as np
import warnings
np.random.seed(2)

from QpixAsic import AsicWord
from QpixAsic import AsicDirMask
from QpixAsic import AsicState
from QpixAsic import AsicConfig

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


## fixtures
@pytest.fixture(params=[(2,2),(2,3)])
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
        hits.append(np.random.uniform(0,10,nHits))
    return hits

@pytest.fixture
def tProcRegReq(qpix_array):
    """
    Create a default register request based on the default asic array
    """
    tAsic = qpix_array[0][0]
    tRegReqByte = QpixAsic.QPByte(AsicWord.REGREQ, None, None, ReqID=2)
    tProcRegReq = QpixAsic.ProcItem(tAsic, 0, tRegReqByte, 0)
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
        asic.InjectHits(np.sort(np.random.uniform(1e-9, 10, size=10)))

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
    assert len(b) == 2, f"{len(b)}, should create two transactions"
    assert tAsic.state == AsicState.TransmitRemote, "should transmit remote after receiving byte from DAQ node"

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
    tAsic = qpix_array[0][0]
    endTime = deltaT*1000
    hits = np.arange(0, endTime, endTime/100.)
    tAsic.InjectHits(hits)
    assert len(tAsic._times) == len(hits), "all hits did not get injected"
    nHits = 0
    curT = deltaT

    # push should allow all of the hits to come through
    tAsic.config.EnablePush = True
    while curT < endTime + deltaT*5 or tAsic._localFifo._curSize > 0:
        nHits += len(tAsic.Process(curT))
        curT += deltaT
    assert tAsic._localFifo._curSize == 0, f"Local FIFO should be empty of hits, total hits {len(hits)}"
    size = len(hits)
    assert tAsic._localFifo._totalWrites == size, f"each hit not in local FIFO, remaining: {len(tAsic._times)}"

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

def test_asic_full_readout(qpix_array):
    """
    Full readout test of a remote ASIC within qpix_array, this asserts
    that different ASIC states are as they should be, and that the 
    time elapsed from each state makes sense
    """
    nHits = 10
    inTime = qpix_array[0][0].transferTime + qpix_array[0][1].transferTime
    hits = np.arange(1e-9, inTime, inTime/nHits) # don't start at 0 time

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
    tAsic.Process(tAsic._absTimeNow)

    # transmit local
    prevState = tAsic.state
    eT = inTime + tAsic.transferTime
    dT = tAsic._absTimeNow
    assert prevState == AsicState.TransmitLocal, "should begin transmitting local data after receiving an Interrogate"
    fifoHits = tAsic._localFifo._curSize
    while fifoHits > 0:
        dT += deltaT
        _ = tAsic.Process(dT)
        fifoHits = tAsic._localFifo._curSize

    # transmit finish word
    eT += tAsic.transferTime * nHits
    prevState = tAsic.state
    assert prevState == AsicState.Finish, "finish state should follow sending all local data"
    nFinish, procs = 0, 0
    while tAsic.state == prevState:
        dT = tAsic._absTimeNow + deltaT
        nFinish += len(tAsic.Process(dT))
        procs += 1
    eT += tAsic.transferTime * 1

    # transmit remote state, should be length of timeout
    prevState = tAsic.state
    assert prevState == AsicState.TransmitRemote, "Remote state should follow end word"
    nRemote, procs = 0, 0
    while tAsic.state == prevState:
        dT = tAsic._absTimeNow + deltaT
        nRemote += len(tAsic.Process(dT))
        procs += 1

    # back to IDLE state
    eT += tAsic.tOsc * tAsic.config.timeout
    prevState = tAsic.state
    assert prevState == AsicState.Idle, "Finished state should be back in IDLE"
    assert round(eT, 6) == round(tAsic._absTimeNow, 6), "Different expected process times during Final step of full readout"

def test_process_array(qpix_array):
    """
    Ensure that the Hidden ProcessArray method for qpix_array behaves as expected
    """
    time_end = 1
    qpix_array._Process(time_end)
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


def ensure_hits(hits, array):
    """
    Helper function that is used on test_daq_read methods to ensure that
    all of the FIFOs and Daq FIFO's make sense.
    """

    def warn(logic, msg):
        if logic == False:
            warnings.warn(msg, UserWarning)
        return 1

    # make sure that all of the ASIC FIFOs are empty
    for hit, asic in zip(hits, array):
        msg = f"({asic.row},{asic.col})"
        warn(asic._localFifo._curSize == 0, f"Asic {msg} local fifo not empty!")
        warn(asic._remoteFifo._curSize == 0, f"Asic {msg} remote fifo not empty!")
        warn(len(asic._localFifo._data) == 0, f"Asic {msg} local fifo not counting reads correctly")
        warn(len(asic._remoteFifo._data) == 0, f"Asic {msg} remote fifo not counting reads correctly")
        warn(len(asic._times) == 0, f"some ASIC {msg} times have NOT been read!")
        warn(asic._localFifo._totalWrites == len(hit), f"{msg} not all hits counted as writes")

    maxTime, nHits = 0, 0
    for hit in hits:
        if len(hit) > 0:
            nHits += len(hit)
            maxTime = np.max(hit) if np.max(hit) > maxTime else maxTime
    daqHits = array._daqNode._localFifo._dataWords
    warn(daqHits == nHits, f"DaqNode did not receive all hits before {maxTime}: {daqHits}/{nHits}")
    evt_end_words = 0
    for asic in array:
        for (state, _, _) in asic.state_times:
            if state == AsicState.Finish:
                evt_end_words += 1
    daq_evt_ends = 0
    for data in array._daqNode._localFifo._data:
        if data.wordType == AsicWord.EVTEND:
            daq_evt_ends += 1
    assert daq_evt_ends == evt_end_words, f"mismatch on total event end words on daq node"

    return 1

def run_array_interrogate(array, maxTime, int_prd):
    """
    Helper function to provide easily tracked debug variables and wrapper for
    interrogate procedure of a QpixArray.
    """
    dT = 0
    t_remote, t_local = 0, 0
    tr_remote, tr_local = 0, 0
    while dT <= maxTime+int_prd*50:
        dT += int_prd
        array.Interrogate(int_prd)
        t_remote, t_local = 0, 0
        tr_remote, tr_local = 0, 0
        for asic in array:
            t_remote += asic._remoteFifo._curSize
            t_local += asic._localFifo._curSize
            tr_remote += asic._remoteFifo._totalWrites
            tr_local += asic._localFifo._totalWrites

    return array

def test_daq_read_data_snake(qpix_array, qpix_hits, int_prd=0.5):
    """
    Ensure that all of the injected hits make it to be read at the DaqNode with
    the procedure of normal interrogation methods to qpix_array.
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
    qpix_array = run_array_interrogate(qpix_array, maxTime, int_prd)

    # compare fifos with expected input hits
    ensure_hits(qpix_hits, qpix_array)
    
    # snake means every ASIC is connected in a long line and should see every # other ASIC
    asicCnt, transactions = 0, 0
    if rows%2 == 0:
        cur_asic = qpix_array[rows-1][0]
    else:
        cur_asic = qpix_array[rows-1][cols-1]
    while asicCnt < rows*cols:
        transactions += cur_asic._localFifo._totalWrites
        evt_end_words = 0
        for (state, _, _) in cur_asic.state_times:
            if state == AsicState.Finish:
                evt_end_words += 1
        transactions += evt_end_words
        asicCnt += 1
        next_asic = cur_asic.connections[cur_asic.config.DirMask.value].asic
        if next_asic.isDaqNode:
            break
        remote_writes = next_asic._remoteFifo._totalWrites 
        msg = f"trans. cnt error @ ({next_asic.row},{next_asic.col}) ({transactions}-{evt_end_words})/{remote_writes}"
        assert remote_writes == transactions, msg
        cur_asic = next_asic
    assert asicCnt == rows*cols, "didnt count all ASICs"

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
    ensure_hits(qpix_hits, qpix_array)

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

            transactions += cur_asic._localFifo._totalWrites
            for(state, _, _) in cur_asic.state_times:
                if state == AsicState.Finish:
                    transactions += 1
            
            # test transactions for this ASIC
            if next_asic.col == 0:
                south_asic = next_asic.connections[AsicDirMask.South.value].asic
                if south_asic is not None:
                    transactions += south_asic._remoteFifo._totalWrites
                    transactions += south_asic._localFifo._totalWrites
                    for(state, _, _) in south_asic.state_times:
                        if state == AsicState.Finish:
                            transactions += 1

            frac = f"{transactions}/{next_asic._remoteFifo._totalWrites}"
            msg = f"trans. cnt error @ ({next_asic.row},{next_asic.col}) {frac}"
            assert next_asic._remoteFifo._totalWrites == transactions, msg

            col = next_asic.col

if __name__ == "__main__":
    qpix_array = QpixAsicArray.QpixAsicArray(
                nrows=tRows, ncols=tCols, nPixs=nPix,
                fNominal=fNominal, pctSpread=pctSpread, deltaT=deltaT,
                timeEpsilon=timeEpsilon, timeout=timeout,
                hitsPerSec=hitsPerSec, debug=debug, tiledf=tiledf)

    rows, cols = qpix_array._nrows, qpix_array._ncols
    r = "Left"
    qpix_array.Route(r, transact=False)
    int_prd = 0.5

    qpix_hits = []
    for asic in qpix_array:
        nHits = np.random.randint(13)
        qpix_hits.append(np.random.uniform(0,10,nHits))

    maxTime = 0
    for hit, asic in zip(qpix_hits, qpix_array):
        if len(hit) > 0:
            maxTime = np.max(hit) if maxTime < np.max(hit) else maxTime 
            asic.InjectHits(hit)

    # run the interrogate procedure
    dT = 0
    t_remote, t_local = 0, 0
    tr_remote, tr_local = 0, 0
    while dT <= maxTime+int_prd*10:
        dT += int_prd
        qpix_array.Interrogate(int_prd)
        t_remote, t_local = 0, 0
        tr_remote, tr_local = 0, 0
        for asic in qpix_array:
            t_remote += asic._remoteFifo._curSize
            t_local += asic._localFifo._curSize
            tr_remote += asic._remoteFifo._totalWrites
            tr_local += asic._localFifo._totalWrites


    # compare fifos with expected input hits
    nHits = 0
    for hit in qpix_hits:
        if len(hit) > 0:
            nHits += len(hit)

    daqHits = qpix_array._daqNode._localFifo._dataWords
    evt_end_words = 0
    for asic in qpix_array:
        for (state, _, _) in asic.state_times:
            if state == AsicState.Finish:
                evt_end_words += 1
    daq_evt_ends = 0
    for data in qpix_array._daqNode._localFifo._data:
        if data.wordType == AsicWord.EVTEND:
            daq_evt_ends += 1
    assert daq_evt_ends == evt_end_words, f"mismatch on total event end words on daq node"

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

            transactions += cur_asic._localFifo._totalWrites
            for(state, _, _) in cur_asic.state_times:
                if state == AsicState.Finish:
                    transactions += 1
            
            # test transactions for this ASIC
            if next_asic.col == 0:
                south_asic = next_asic.connections[AsicDirMask.South.value].asic
                if south_asic is not None:
                    transactions += south_asic._remoteFifo._totalWrites
                    transactions += south_asic._localFifo._totalWrites
                    for(state, _, _) in south_asic.state_times:
                        if state == AsicState.Finish:
                            transactions += 1

            frac = f"{transactions}/{next_asic._remoteFifo._totalWrites}"
            msg = f"trans. cnt error @ ({next_asic.row},{next_asic.col}) {frac}"
            assert next_asic._remoteFifo._totalWrites == transactions, msg

            col = next_asic.col

    input("test")