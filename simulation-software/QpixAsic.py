#!/usr/bin/python3

import math
import time
from enum import Enum
from unicodedata import decimal
import numpy as np
from dataclasses import dataclass

# Endeavor config bits
N_ZER_CLK_G = 8
N_ONE_CLK_G = 24
N_GAP_CLK_G = 16
N_FIN_CLK_G = 40
N_DEFAULT_CLKS = 1700
N_FRAME_BITS = 64
N_PIXELS = 16

# helper functions
def PrintFifoInfo(asic):
    print("\033[4m" + f"asic ({asic.row},{asic.col}) Local Fifo" + "\033[0m")
    print(
        f"  data: {asic._localFifo._data} (should be empty if interrogation/calibration was successful)"
    )
    print(f"  did it reach max capacity?: {asic._localFifo._full}")
    print(f"  max size: {asic._localFifo._maxSize}")
    print(f"  total writes: {asic._localFifo._totalWrites}")

    print("\033[4m" + f"asic ({asic.row},{asic.col}) Remote Fifos (NESW)" + "\033[0m")
    print(f"  data: ", end="")
    print(f"{asic._remoteFifo._data} ", end="")
    print(f"\n  did it reach max capacity?: ", end="")
    print(f"{asic._remoteFifo._full} ", end="")
    print(f"\n  max size:", end="")
    print(f"{asic._remoteFifo._maxSize} ", end="")
    print(f"\n  total writes: ", end="")
    print(f"{asic._remoteFifo._totalWrites} ", end="")
    print("\n")


class QPException(Exception):
    pass


class AsicDirMask(Enum):
    """
    This class maintains values to represent directionality for ASIC
    connections.

    These values are implemented in QPixAsicArray constructor during _makeArray
    call.
    """
    North = 0
    East = 1
    South = 2
    West = 3


class AsicState(Enum):
    """
    Enum class based on the QpixRoute.vhd FSM states. Transitions to and from these
    states should be modeled on the inputs defined in QpixRoute.vhd.

    Formally, these states represent the possible states of the QPixAsic route FSM
    as described in QpixRoute.vhd.
    """

    Idle = 0
    TransmitLocal = 1
    TransmitRemote = 2
    TransmitReg = 3
    Finish = 4
    # Extra modified states


class AsicWord(Enum):
    """
    Enum class to represent the different types of word types that a QPByte class
    can receive.

    These word types are 4 bits and their values are defined in QPixPkg.vhd

    Formally, these types of words define the possible inputs to the parser
    which are either sent to the local register (REGREQ) or sent to the remote FIFO
    which are all other words.
    """

    DATA = 1
    REGREQ = 3
    REGRESP = 4
    EVTEND = 5


@dataclass
class AsicConfig:
    """
    Struct like class that is based on the QpixConfigType record defined in QpixPkg.vhd

    This struct manages the configuration values stored in the QpixRegFile.vhd and should
    determine enables, timeouts, and directional routing
    ARGS:
      frq - frequency of asic frequency, required to determine number of timeout clicks
      timeout    - number of ticks that an asic should undergo before leaving transmitRemote state
      pTimeout    - number of ticks that an ASIC should undergo before
                   automatically entering transmitLocal state if EnablePush == True
      DirMask    - directional mask
      ManRoute   - flag to enable manual routing, or use default routing
      EnableSnd  - enable send flag
      EnableRcv  - enable receive flag
      EnableReg  - enagle register flag
      EnablePush - Tell the ASIC to be in a "push" state, so that it sends hits immediately
    """

    DirMask: AsicDirMask
    timeout: int
    pTimeout: int = int(25e6)
    ManRoute = False
    EnableSnd = True
    EnableRcv = True
    EnableReg = True
    something = False

    # enable push, not on by default
    EnablePush = False

    # send remote will always force an ASIC to send any remote data it has, from
    # any state
    SendRemote = True


class QPByte:
    """
    This struct-style class stores no more than the 64 bit information transfered
    on a 64 bit Tx/Rx Endeavor protocol.

    ARGS:
      wordType    : 4 bit regWord type
      originRow   : 4 bit value representing x position of sending ASIC
      originCol   : 4 bit value representing y position of sending ASIC
      # if wordtype == AsicWord.REGREQ
        Dest    : bool, true if writing to individual ASIC, false if broadcast
        OpWrite : bool, true if writing an ASIC
        OpRead  : bool, true if reading an ASIC (not OpWrite)
        ReqID   : int, keep track of last request-ID received from DaqNode at ASICs
        SrcDaq  : bool, true if coming from DAQNode
        config  : AsicConfig, struct containing ASIC configuration
      # else this is a data word
        timeStamp   : 32 bit time stamp, should only accept return value of QpixAsic.CalcTicks()
        channelList : 16 bit channel map
      data        : extra value for simulation

    NOTE: refactored PixelHit object! Data that are transferred are Bytes~ NOT
    'hits'. A hit is always a time stamp, but what is transferred is a more
    generic packet.

    NOTE: 2 bits are currently reserved, and formating is defined in QpixPkg.vhd

    NOTE: This dataclass should match the implemention of `QpixDataFormatType`
    """

    def __init__(
        self,
        wordType,
        originRow,
        originCol,
        timeStamp=None,
        channelList=None,
        data=None,
        XDest=None,
        YDest=None,
        Dest=False,
        ReqID=-1,
        OpRead=False,
        OpWrite=False,
        config=AsicConfig(AsicDirMask.North, 1.5e4),
    ):

        if not isinstance(wordType, AsicWord):
            print("WARNING!! undefined word type in current byte!")

        self.wordType = wordType
        self.originRow = originRow
        self.originCol = originCol
        self.SrcDaq = bool(originCol is None and originRow is None)
        self.data = data
        self.timeStamp = timeStamp
        self.channelMask = None

        # if the wordType is a reg request, then build destination members
        if self.wordType == AsicWord.REGREQ:
            self.Dest = Dest
            self.OpWrite = OpWrite
            self.OpRead = OpRead
            self.XDest = XDest
            self.YDest = YDest
            self.ReqID = ReqID
            self.config = config
        elif self.wordType == AsicWord.REGRESP:
            self.config = config
        elif self.wordType == AsicWord.EVTEND:
            self.ReqID = ReqID
        else:
            self.channelMask = 0
            if channelList is not None:
                for ch in channelList:
                    self.channelMask |= 0x1 << ch

        # calculate the transfer ticks we need at the creation of the byte
        self.transferTicks = self._TransferTicks()

    def __repr__(self):
        """
        how to represent a Byte when print out
        """
        msg = f"({self.originRow},{self.originCol}): {self.wordType}  - {self.data}"
        return msg

    def AddChannel(self, channel):
        self.channelMask |= 0x1 << channel

    def _TransferTicks(self):
        """
        Function returns number of transfer ticks (based on Endeavor protocol)
        that should be held to send this byte across
        """
        if self.channelMask is None or self.timeStamp is None:
            return N_DEFAULT_CLKS
        else:

            highBits = bin(int(self.channelMask)).count("1")
            highBits += bin(int(self.timeStamp)).count("1")
            highBits += bin(int(self.originCol)).count("1")
            highBits += bin(int(self.originRow)).count("1")
            highBits += bin(int(self.wordType.value)).count("1")

            N_BITS = N_FRAME_BITS
            lowBits = N_BITS - highBits
            num_gap = (N_BITS - 1) * N_GAP_CLK_G

            num_ones = highBits * N_ONE_CLK_G
            num_zeros = lowBits * N_ZER_CLK_G
            num_data = num_ones + num_zeros
            return num_data + num_gap + N_FIN_CLK_G


class QPFifo:
    """
    FIFO class to store and manage incoming QPByte data between ASIC connections

    A FIFO can only do two things: Read and Write. Therefore, there should only
    be two implemented public functions for this class: Read and Write.
    """

    def __init__(self, maxDepth=256):
        self._data = []
        self._maxSize = 0
        self._curSize = 0
        self._maxDepth = maxDepth
        self._full = False
        self._totalWrites = 0

    def Write(self, data: QPByte) -> int:
        """
        Implements a write feature to the Fifo
        ARGS:
          Ensure that the data being stored in the FIFO matches the QPByte
        Returns:
          current number of events stored in the FIFO
        """

        if not isinstance(data, QPByte):
            raise QPException("Can not add this data-type to a QPFifo!")

        self._data.append(data)
        self._curSize += 1
        self._totalWrites += 1

        if self._curSize > self._maxSize:
            self._maxSize = self._curSize

        if self._curSize > self._maxDepth:
            self._full = True

        return self._curSize

    def Read(self) -> QPByte:
        """
        Implements a Readout feature for the FIFO.
        ARGS:
          None
        Returns:
          oldest stored event (First In, First Out)
        """
        if self._curSize > 0:
            self._curSize -= 1
            return self._data.pop(0)
        else:
            return None


class ProcItem:
    """
    Process item controlled by ProcQueue.
    asic, the ASIC being pushed to
    dir, where the data came from
    QPByte, a QPByte object
    inTime, time that the data would be received, or that the sending asic completes sending QPByte
    command, flag to determine how individual ASIC receiving data should behave
    """

    def __init__(self, asic, dir, QPByte, inTime, command=None):
        self.asic = asic
        self.dir = dir
        self.QPByte = QPByte
        self.inTime = inTime
        self.command = command
        self._nextItem = None

    def __gt__(self, otherItem):
        """
        define that comparing process items based on what inTime the item should be
        processed
        """
        if isinstance(otherItem, ProcItem):
            return self.inTime > otherItem.inTime
        else:
            return NotImplementedError


class ProcQueue:
    """
    ProcQueue class is the main class which defines the simulation flow.

    It is designed to store ProcItem class objects, which are the basic unit of an ASIC transaction.
    """

    def __init__(self, procItem=None):
        self._curItem = procItem
        self._entries = 0
        # keep track of how many items this has queue has processed
        self.processed = 0

    def AddQueueItem(self, asic, dir, QPByte, inTime, command=None):
        """
        refactor
        """
        assert asic is not None, "ERROR: can't send data to a None node!"
        procItem = ProcItem(asic, dir, QPByte, inTime, command)
        self._AddQueueItem(procItem)

    def _AddQueueItem(self, procItem):
        """
        include a new process item, inserting into list at appropriate time
        """
        newItem = procItem
        curItem = self._curItem
        self._entries += 1

        if curItem is None:
            self._curItem = newItem
        elif curItem > newItem:
            h = self._curItem
            self._curItem = newItem
            self._curItem._nextItem = h
        else:
            while newItem > curItem and curItem._nextItem is not None:
                curItem = curItem._nextItem
            newItem._nextItem = curItem._nextItem
            curItem._nextItem = newItem

        return self._entries

    def PopQueue(self):
        if self._curItem is None:
            return None
        self.processed += 1
        self._entries -= 1
        data = self._curItem
        self._curItem = self._curItem._nextItem
        return data

    def SortQueue(self):
        """
        deprecated
        """
        pass

    def Length(self):
        return self._entries


class QPixAsic:
    """
    A Q-Pix ASIC fundamentally consists of:
    An oscillator of nominal frequency (~50 MHz)
    A number of channels (nominally 16 or 32)
      - When a given channel is "hit", a timestamp is generated

    -- ARGS/params:
    fOsc          - Oscillator Frequency in Hz
    tOsc          - clock period in seconds
    nPixels       - number of analog channels
    config        - AsicConfig struct class containing configuration members
    randomRate    - Poisson Rate of random background hits
    row           - x position within array
    col           - y position within array
    transferTicks - number of clock cycles governed in a transaction, which is determined by Endeavor protocol parameters
    debugLevel    - float flag which has print statements, > 0 values will cause prints
    ## AsicConfig members
    timeout       - clock cycles that ASIC will remote in transmit remote state
    pTimeout      - clock cycles that ASIC will collect before entering transmit local state
    ## tracking params
    state         - AsicState Enum class, based on QpixRoute.vhd FSM states
    state_times   - list of tuples that store transition times of ASIC states based on the
    ## Buffers
    _localFifo   - QPFifo class to manage Read and Write of local data
    _remoteFifo  - QPFifo list of four QPFifo class' to manage write of remote ASIC data / transactions
    _rxFifos     - QPFifo list of four QPFifo class' to manage read of adjacent ASIC transactions
    connections  - list of pointers to adjacent asics
    """

    def __init__(
        self,
        fOsc=50e6,
        nPixels=16,
        randomRate=20.0 / 1.0,
        timeout=15000,
        row=None,
        col=None,
        isDaqNode=False,
        transferTicks=1700,
        debugLevel=0,
        pTimeout=25e6,
    ):
        # basic asic parameters
        self.fOsc = fOsc
        self.tOsc = 1.0 / fOsc
        self.nPixels = 16
        self.randomRate = randomRate
        self.row = row
        self.col = col

        # timing, absolute and relative with random starting phase
        self.config = AsicConfig(AsicDirMask.North, timeout, pTimeout)
        self.transferTicks = transferTicks
        self.transferTime = self.transferTicks * self.tOsc
        self.lastAbsHitTime = [0] * self.nPixels
        self._absTimeNow = 0
        self.relTimeNow = (np.random.uniform() - 0.5) * self.tOsc
        self.timeoutStart = self.relTimeNow
        self._startTime = self.relTimeNow
        self.relTicksNow = 0

        # state tracking variables
        self.state = AsicState.Idle
        self.state_times = [(self.state, self.relTimeNow, self._absTimeNow)]
        self._broadT = []

        # daq node Configuration
        self.isDaqNode = isDaqNode
        self._reqID = -1
        self._intID = -1
        self._intTick = -1

        # Queues / FIFOs
        self.connections = self.AsicConnections(self.transferTime)
        self._localFifo = QPFifo(maxDepth=512)
        self._remoteFifo = QPFifo(maxDepth=512)

        # additional / debug
        self._debugLevel = debugLevel
        self._hitReceptions = 0
        self._measuredTime = []

        # useful members for InjectHits
        self._times = []
        self._channels = []
        self.totalInjected = 0

    def __repr__(self):
        self.PrintStatus()
        return f"QPA-({self.row},{self.col})"

    def __gt__(self, other):
        """
        compare ASICs based on Frq
        """
        if isinstance(other, QPixAsic):
            return self.fOsc > other.fOsc
        else:
            return NotImplementedError

    def __eq__(self, other):
        """
        compare ASICs based on Frq
        """
        if isinstance(other, QPixAsic):
            return self.fOsc == other.fOsc
        else:
            return NotImplementedError

    def _changeState(self, newState: AsicState):
        """
        function manages when the ASIC transitions from one state to another.

        This function records relative and absolute times of when the FSM in the
        QpixRoute.vhd state transition occurs.

        The purpose of recording state transitions is for testing verification to
        ensure that the ASIC's state transitions match with what is expected.

        NOTE: State changes should be called after UpdateTime, as state changes
        after transactions are complete!
        """
        assert isinstance(newState, AsicState), "Incorrect state transition!"
        if newState == AsicState.TransmitRemote and (self.state == AsicState.Finish or self.state == AsicState.Idle):
            if not self.config.SendRemote:
                self.timeoutStart = self.relTimeNow
        if self.state != newState:
            self.state = newState
            self.state_times.append((self.state, self.relTimeNow, self._absTimeNow))

    def PrintStatus(self):
        if self._debugLevel > 0:
            print("ASIC (" + str(self.row) + "," + str(self.col) + ") ", end="")
            print("STATE:" + str(self.state), end=" ")
            print(f"locFifoSize: {self._localFifo._curSize}")
            print("Remote Sizes (N,E,S,W):", end=" ")
            print(str(self._remoteFifo._curSize) + ",", end=" ")
            print(f"absTime = {self._absTimeNow:0.2e}, trel = {self.relTimeNow:0.2e}")
            print(f"ticks = {self.relTicksNow}")

    def CountConnections(self):
        return self.connections.CountConnections()

    def HasConnection(self, dir):
        return self.connections.HasConnection(dir)

    def ReceiveByte(self, queueItem: ProcItem):
        """
        Receive data from a neighbor
        queueItem - tuple of (QPixAsic, AsicDirMask, QPByte, inTime)

        The QPByte that's received in this function should simulate the behavior of
        the logic found in QpixParser.vhd

        NOTE: Formally, this method is the precbehaves as the FSM's transition
        function which handles the maping of inputs (the QPByte) and the current
        ASIC state.

        NOTE: Possible to update ASIC time beyond inTime in the event
        of a broadcast. it will move time to inTime+transferTime.
        """
        assert isinstance(
            queueItem.dir, AsicDirMask
        ), "not a valid direction to send as a queue item"
        inDir = queueItem.dir.value
        inByte = queueItem.QPByte
        inTime = queueItem.inTime
        inCommand = queueItem.command

        if not self.connections[inDir]:
            print(f"WARNING ({self.row},{self.col}) receiving data from non-existent connection! {inDir}")
            return []

        # ASIC has received this request already and should do nothing
        if inByte.wordType == AsicWord.REGREQ and self._reqID == inByte.ReqID:
            return []

        # all data that is not a register request gets stored on remote fifos
        # These data are usually dataframe packets from remote ASICs heading to DAQNode
        if inByte.wordType != AsicWord.REGREQ:
            self._remoteFifo.Write(inByte)
            return []

        # if the incomming word is a register request, it's from the DAQNODE
        self._reqID = inByte.ReqID

        # dynamic routing if manual routing not enabled
        if not self.config.ManRoute:
            self.config.DirMask = AsicDirMask(inDir)

        # currently ALL register requests are broadcast..
        isBroadcast = not inByte.Dest
        if isBroadcast:
            outList =  self.Broadcast(queueItem)
        else:
            outList = []

        # is this word relevant to this asic?
        toThisAsic = inByte.XDest == self.row and inByte.YDest == self.col
        if toThisAsic or isBroadcast:

            if inByte.OpWrite:
                self.config = inByte.config

            elif inByte.OpRead:
                byteOut = QPByte(
                    AsicWord.REGRESP, self.row, self.col, config=self.config
                )
                self._remoteFifo.Write(byteOut)
                self._changeState(AsicState.TransmitReg)

            # if it's not a read or a write, it's a command interrogation
            else:
                if inCommand == "Interrogate" or inCommand == "HardInterrogate":
                    # self._GeneratePoissonHits(inTime)
                    self._ReadHits(inTime)
                    # used for keeping track of when this request was received here
                    self._intID = inByte.ReqID
                    self._intTick = self.CalcTicks(inTime)
                elif inCommand == "Calibrate":
                    self._localFifo.Write(
                        QPByte(
                            AsicWord.REGRESP,
                            self.row,
                            self.col,
                            ReqID = inByte.ReqID,
                            timeStamp = self.CalcTicks(inTime),
                            data=inTime,
                        )
                    )
                if self._localFifo._curSize > 0 or inCommand == "HardInterrogate":
                    self._changeState(AsicState.TransmitLocal)
                # else:
                #     self._changeState(AsicState.TransmitRemote)
                self._measuredTime.append(self.relTimeNow)

        return outList

    def Broadcast(self, queueItem: ProcItem) -> list:
        """
        Simulate behavior of what an ASIC should do for the broadcast command.

        This algorithm must search all possible edges within the array.
        """
        inDir = queueItem.dir.value
        inByte = queueItem.QPByte
        inTime = queueItem.inTime
        inCommand = queueItem.command
        outList = []
        for i, connection in enumerate(self.connections):
            if i != inDir and connection:
                self.transferTime = inByte.transferTicks * self.tOsc
                transactionCompleteTime = inTime + self.transferTime
                sendT = self.UpdateTime(transactionCompleteTime, i, isTx=True)
                self._broadT.append(sendT)
                outList.append(
                    (
                        connection.asic,
                        AsicDirMask((i + 2) % 4),
                        inByte,
                        sendT,
                        inCommand,
                    )
                )
        return outList

    def _GeneratePoissonHits(self, targetTime):
        """
        Generate Poisson hits for the time step ##
        Distribution of inter-arrival times can be modeled by throwing
        p = Uniform(0,1) and feeding it to -ln(1.0 - p)/aveRate
        General strategy for moving forward to some timestep is:
          for each channel:
            currentTime = now
            while currentTime < targetTime:
              generate nextHitTime from distribution above
              if currentTime + nextHitTime < targetTime:
                Calculate number of ticks for timestamp and add it to the current queue
              else:
                this is last hit for this pixel, add the next time to the alternate queue
          Sort the overall list by timestamp
          foreach unique entry in the timestamp list, create a hit with proper parameters,
          add it to the queue (A or B)
        """
        # print(f'Generating Poisson Hits for ({self.row}, {self.col}) at target time {targetTime}')
        newHits = []

        for ch in range(self.nPixels):
            currentTime = self.lastAbsHitTime[ch]
            while currentTime < targetTime:

                # generate a posion distribution of absolute / reletive times
                p = np.random.uniform()  # prints random real between 0 and 1
                nextAbsHitTime = currentTime + (
                    -math.log(1.0 - p) / self.randomRate
                )  # math.log is the natural log
                nextRelHitTime = int(math.floor(nextAbsHitTime / self.tOsc))

                # if hit happens before target time, add a new hit to the list
                if nextAbsHitTime < targetTime:
                    newHits.append([ch, nextRelHitTime])
                    currentTime = nextAbsHitTime
                    self.lastAbsHitTime[ch] = currentTime
                elif nextAbsHitTime > targetTime:
                    currentTime = targetTime
                    self.lastAbsHitTime[ch] = targetTime

        if not newHits:
            return 0

        # sort the new hits by time, group the channels with the same hit time, then add
        # them into the FIFO
        newHits.sort(key=lambda x: x[1], reverse=False)
        prevByte = QPByte(
            AsicWord.DATA, self.row, self.col, newHits[0][1], [newHits[0][0]]
        )

        # check to see if the hit time of the every new hit after the first is
        # the same as the first hit time, then check with second hit, then third ...
        for ch, timestamp in newHits[1:]:
            if timestamp == prevByte.timestamp:
                prevByte.AddChannel(ch)
            else:
                self._localFifo.Write(prevByte)
                prevByte = QPByte(AsicWord.DATA, self.row, self.col, timestamp, [ch])

        # write in the last byte
        self._localFifo.Write(prevByte)
        return len(newHits)

    def InjectHits(self, times, channels=None):
        """
        user function to place all injected times and channels into asic specific
        time and channel arrays

        then sort each according to time
        """
        if self._debugLevel > 0:
            print(f"injecting {len(times)} hits for ({self.row}, {self.col})")

        # don't try to extend anything if there are no times
        if len(times) == 0:
            return

        # place all of the injected times and channels into self._times and self._channels
        if not isinstance(self._times, list):
            self._times = list(self._times)
        self._times.extend(times)

        # include default channels
        if channels is None:
            channels = [[1, 3, 8]] * len(times)

        msg =  "Injected Times and Channels must be same length"
        assert len(channels) == len(times), msg

        if not isinstance(self._channels, list):
            self._channels = list(self._channels)
        self._channels.extend(channels)

        # sort the times and channels, which allow O(1) access for read during push
        times, channels = zip(*sorted(zip(self._times, self._channels)))
        times = list(times)

        # construct the channel byte here in one pass
        # else condition handles output of pyNotebooks
        if isinstance(channels[0], list):
            self._channels = np.array([np.sum([0x1 << ch for ch in c]) for c in channels])
        else:
            channels = [0x1 << c for c in channels]

            # we want to make sure that we combine hits of multiple channels
            # that would happen within one clock cycle
            combineIndex = []
            goodIndex = 0
            for i in range(len(times)-1):
                if times[i+1] - times[goodIndex] < self.tOsc:
                    combineIndex.append(i+1)
                else:
                    goodIndex = i+1

            for k in reversed(combineIndex):
                times.pop(k)
                channels[k-1] |= channels.pop(k)

            self._channels = np.array(channels)

        self._times = np.array(times)
        self.totalInjected += len(times)


    def _ReadHits(self, targetTime):
        """
        make times and channels arrays to contain all hits within the last asic hit
        time and the target time

        read all of the hits in the times/channels arrays, with times before
        targetTime

        then write hits to local fifos
        """
        if len(self._times) > 0 and targetTime > self._times[0]:

            # index times and channels such that they are within last asic hit time and target time
            TimesIndex = np.less_equal(self._times, targetTime)
            readTimes = self._times[TimesIndex]
            readChannels = self._channels[TimesIndex]

            newhitcount = 0
            for inTime, ch in zip(readTimes, readChannels):
                prevByte = QPByte(AsicWord.DATA, self.row, self.col, self.CalcTicks(inTime), data=inTime)
                prevByte.channelMask = ch
                self._localFifo.Write(prevByte)
                newhitcount += 1

            # the times and channels we have are everything else that's left
            self._times = self._times[~TimesIndex]
            self._channels = self._channels[~TimesIndex]

            return newhitcount

        else:
            # print(f'there are no hits for asic ({self.row}, {self.col})')
            return 0

    def Process(self, targetTime):
        """
        This function simulates the FSM within QpixRoute.vhd.
        ARGS:
          targetTime - time to push the FSM foward.
        """
        # nothing to process if DAQ or if target time is in past
        if self.isDaqNode or self._absTimeNow >= targetTime:
            return []

        ## QPixRoute State machine ##
        if self.state == AsicState.Idle:

            # if the ASIC is in a push state enter transmit local on any
            # depth in the local fifo
            if self.config.EnablePush and self._localFifo._curSize > 0:
                self._changeState(AsicState.TransmitLocal)

            elif self.config.SendRemote and self._remoteFifo._curSize > 0:
                self._changeState(AsicState.TransmitRemote)

            else:
                return self._processMeasuringState(targetTime)

        if self.state == AsicState.TransmitLocal:
            return self._processTransmitLocalState(targetTime)

        if self.state == AsicState.Finish:
            return self._processFinishState(targetTime)

        if self.state == AsicState.TransmitRemote:
            return self._processTransmitRemoteState(targetTime)

        if self.state == AsicState.TransmitReg:
            return self._processRegisterResponse(targetTime)

        # undefined state
        print("WARNING! ASIC in undefined state")
        self._changeState(AsicState.Idle)
        return []

    def _processMeasuringState(self, targetTime):
        """
        Function simulates the IDLE state with QpixRoute.vhd. In this case the only
        thing to be done is to update the time.
        """
        self.UpdateTime(targetTime)
        return []

    def _processRegisterResponse(self, targetTime):
        """
        This function simulates the register response state within QpixRoute.vhd

        This state sends a REGRESP word back to the local fifo and then returns to
        the IDLE/measuring state.

        NOTE: this state is ONLY entered from the IDLE state, where during the IDLE
        state, if remoteFifo is NOT empty and the received word is a RegReq.
        """
        respByte = self._remoteFifo.Read()
        self.transferTime = self.tOsc * respByte.transferTicks
        transactionCompleteTime = self._absTimeNow + self.transferTime
        sendT = self.UpdateTime(transactionCompleteTime, self.config.DirMask.value, isTx=True)
        self._changeState(AsicState.Idle)
        return [(
                self.connections[self.config.DirMask.value].asic,
                (self.config.DirMask.value + 2) % 4,
                respByte,
                sendT,
            )]

    def _processTransmitLocalState(self, targetTime):
        """
        helper function for sending local data where it needs to go
        sends a single local state queue item into the outlist
        """

        localTransfers = []
        while self._absTimeNow < targetTime and self._localFifo._curSize > 0:
            hit = self._localFifo.Read()
            self.transferTime = self.tOsc * hit.transferTicks
            transactionCompleteTime = self._absTimeNow + self.transferTime
            i = self.config.DirMask.value
            sendT = self.UpdateTime(transactionCompleteTime, i, isTx=True)
            localTransfers.append((
                    self.connections[i].asic,
                    AsicDirMask((i + 2) % 4),
                    hit,
                    sendT,
                ))

        if self._localFifo._curSize == 0:
            self._changeState(AsicState.Finish)
        return localTransfers

    def _processFinishState(self, targetTime):
        """
        Finish state based on QpixRoute.vhd state. Should pack a single word into
        the event fifo, send it, and proceed to the transmit remote state.

        NOTE: the timing only works in this state since the it's guarunteed
        to be entered form transmitLocal state and to leave after a single
        transaction.
        """
        # send the finish packet word
        finishByte = QPByte(AsicWord.EVTEND, self.row, self.col, self._intTick, ReqID=self._intID)
        self.transferTime = self.tOsc * finishByte.transferTicks
        transactionCompleteTime = self._absTimeNow + self.transferTime
        sendT = self.UpdateTime(transactionCompleteTime, self.config.DirMask.value, isTx=True)

        # after sending the word we go to the Transmit remote state
        self._changeState(AsicState.TransmitRemote)

        return [(
                self.connections[self.config.DirMask.value].asic,
                AsicDirMask((self.config.DirMask.value + 2) % 4),
                finishByte,
                sendT,
            )]

    def _processTransmitRemoteState(self, targetTime):
        """
        process state is based on QpixRoute.vhd REP_REMOTE_S state. This state should always
        bring the asic back to the idle state after a timeout
        """

        # If we're timed out, immediately go to IDLE and then update time
        if self.timeout():
            self._changeState(AsicState.Idle)
            self.UpdateTime(targetTime)
            return []

        # If there's nothing to forward, bring us up to requested time
        if self._remoteFifo._curSize == 0:
            # transition to idle first, if timeout happens before targetTime
            if targetTime > self.timeoutStart + self.config.timeout * self.tOsc:
                self.UpdateTime(self.timeoutStart + self.config.timeout * self.tOsc)
                self._changeState(AsicState.Idle)
                if self.config.SendRemote:
                    raise QPException("should not enter this block during sendremote")
            else:
                self.UpdateTime(targetTime)
            return []


        # here we process hits from the non-empty remote fifo.
        # This block should ensure that hits are sent up until
        # this ASICs time reaches targetTime, or until the remote
        # FIFO is empty, and the FIFO has not timed out
        hitlist = []
        while (
                self._remoteFifo._curSize > 0 and
                not self.timeout() and
                self._absTimeNow < targetTime
        ):

            hit = self._remoteFifo.Read()
            self.transferTime = hit.transferTicks * self.tOsc
            transactionCompleteTime = self._absTimeNow + self.transferTime
            i = self.config.DirMask.value
            sendT = self.UpdateTime(transactionCompleteTime, i, isTx=True)
            hitlist.append((
                    self.connections[i].asic,
                    AsicDirMask((i + 2) % 4),
                    hit,
                    sendT,
                ))
        # here we need to check why we left the while loop.
        # If we've timedout for any reason, we're back to IDLE
        # otherwise we continue on in the Transmit remote state
        if self.timeout():
            self._changeState(AsicState.Idle)
        else:
            self._changeState(AsicState.TransmitRemote)

        return hitlist

    def timeout(self):
        """
        Function describes whether or not the ASIC has timed out.

        This is the control logic for when an ASIC should leave the
        TransmitRemote state. If SendRemote is enabled, leave when empty.
        Otherwise, leave after time defined by  self.config.timeout.
        """
        if self.config.SendRemote == True:
            return self._remoteFifo._curSize == 0
        else:
            return bool(self.relTimeNow - self.timeoutStart > self.config.timeout * self.tOsc)

    def CalcTicks(self, absTime):
        """
        Calculate the number of transfer ticks beginning from self._starttime
        until abstime. This is used to calculate an accurate timestamp 
        for an arbitrary read call

        NOTE: _startTime is defined as some random starting phase within one
        clock cycle of zero at the beginning of the simulation, defined by
        np.random.uniform, or the np.random seed.
        """

        tdiff = absTime - self._startTime
        cycles = int(tdiff / self.tOsc) + 1
        return cycles

    def UpdateTime(self, absTime, dir=None, isTx=None):
        """
        How an ASIC keeps track of its relative times.
        ARGS:
            absTime - absolute time of the simulation, that an ASIC is asked to process up to
        Optional:
            Dir  - Asic Connection dir, selects the connection to mark as busy until abstime
            isTx - bool, used to select whether to mark the Tx or Rx as busy.

        NOTE:
        should only move forward in time and update if the ASIC is not already this
        far forward in time.
        """

        if self.config.EnablePush:
            self._ReadHits(absTime)

        transT = absTime
        if dir is not None:
            assert isTx is not None, "must select Tx or Rx when updating connection"

            # the connection has a transfertime which depends on this particular
            # QPByte, and therefore must be updated
            self.connections[dir].transTime = self.transferTime

            # if Tx is busy send at the next time interval
            if isTx and self.connections[dir].send(absTime):
                transT = self.connections[dir].txBusy + self.transferTime + self.tOsc
                if self.connections[dir].send(transT):
                    raise QPException()
            else:
                self.connections[dir].recv(absTime)

        # only update the time in the forward direction if the asic needs to
        if absTime > self._absTimeNow:

            # update the absolute time and relative times / ticks
            self._absTimeNow = transT
            self.relTicksNow = self.CalcTicks(self._absTimeNow)
            self.relTimeNow = self.relTicksNow * self.tOsc + self._startTime

        return transT

    class AsicConnections():
        """
        This class stores the edges for the each ASIC and creates pointers to
        connected ASICs within an array

        It stores its connections which flag during which times the connection
        is busy, and should prevent multiple writes along a path at the same
        time.
        """

        def __init__(self, tt):
            self.connections = [self.connection(i, tt) for i in range(4)]

        def __getitem__(self, n):
            if n >= len(self.connections):
                raise IndexError
            return self.connections[n]

        def CountConnections(self):
            nConn = 0
            for i in self:
                if i:
                    nConn += 1
            return nConn

        def HasConnection(self, dir):
            return bool(self[dir])

        # nested class for each TxRx connection pair
        @dataclass
        class connection():
            dir: int
            transTime: float
            asic = None

            # time values to hold when a Tx and Rx line are busy
            txBusy = -1
            rxBusy = -1

            def __repr__(self):
                if self.asic is not None:
                    return f"{self.dir} is connected to ASIC {self.asic}"
                else:
                    return f"{self.dir} is NOT connected"

            def __bool__(self):
                return self.asic is not None

            def send(self, T):
                """
                Connection sends a transaction that finished at time T.
                Return bool stating whether or not Tx line is busy
                """
                if self.txBusy > T - self.transTime:
                    if self.asic is not None:
                        return True
                    else:
                        print("WARNING sending on busy none asic")
                else:
                    self.txBusy = T
                return False

            def recv(self, T):
                """
                Connection receives a transaction that finished at time T
                """
                if self.rxBusy > T:
                    print("WARNING receiving on busy connection")
                else:
                    self.rxBusy = T


@dataclass
class DaqTimestamp:
    """
    struct object to store measured Timestamps accumulated by the DaqNode.

    This class should be used to extract relevant data from the DAQNode FIFO for analysis.

    Members:
        ReqID - Integer: Request ID sent from the DAQNode which identifies when this was requested
        Clock - Integer: Records the current clock cycle when this timestamp was measured.
        Time  - Float: value for the 'true' time that this was recorded
        Row - Integer: Remote integer value for the ASIC which
        Col - Integer: Remote integer value for the ASIC which
        AsicClock - Integer: Records the clock cycle of the remote ASIC when the interrogation was received
        AsicTime  - Float: value for the 'true' time that this was recorded at the remote ASIC
    """
    ReqID = int
    Clock = int
    Time = float
    Row = int
    Col = int
    AsicClock = int
    AsicTime = float


@dataclass
class DaqData:
    """
    DaqNode stores data in this format once it's received via ReceiveByte
    as a QPByte. DaqNode stores a list (FIFO buffer equiv.) of this data.
    Params:
    daqT - DaqNode's 32 bit reference timestamp
    wordtype - Type of the QPByte received
    row - Source Asic Row
    col - Source Asic Col
    QPByte - misc data class container which can store RegResp / RegData and all AsicWord type
    in QpixPkg.vhd
    """
    daqT: int
    wordType: AsicWord
    row: int
    col: int
    qbyte: QPByte

    def T(self):
        return self.qbyte.timeStamp


class DaqNode(QPixAsic):
    """
    Simulated aggregator node which will receive all of the QPByte data from the
    asics within an array/tile.

    This node should should provide a method for writing out data collected from
    the QPixAsicArray.

    NOTE:
    The calibration procedure: regardless of the push or pull architecture should
    be based on a response to a broadcast from the daqnode, which stores tick ID
    and timestamp within the event end word.
    """
    def __init__(
        self,
        fOsc=30e6,
        nPixels=N_PIXELS,
        randomRate=20.0 / 1.0,
        timeout=1000,
        row=None,
        col=None,
        transferTicks=N_DEFAULT_CLKS,
        debugLevel=0,
    ):
        # makes itself basically like a qpixasic
        super().__init__(
            fOsc, nPixels, randomRate, timeout, row, col, transferTicks, debugLevel
        )

        # new members here
        self.isDaqNode = True
        self._localFifo = self.DaqFifo()

        # create a running list of timestamps accumulated from the evtEnd words
        # during writes here
        self.nTimestamps = 0
        self.TimestampIDs = set()
        self.TimestampData = []

        # make sure that the starting daqNode ID is different from the ASIC default
        self._reqID += 1
        self.received_asics = set()


    def ReceiveByte(self, queueItem: ProcItem):
        """
        Records Byte to daq.
        This overloads the normal receive byte method from a QPixAsic as the DAQNode ultimately will send
        data to disc, and thus performs a different function.
        """

        inDir = queueItem.dir
        inByte = queueItem.QPByte
        inTime = queueItem.inTime
        inCommand = queueItem.command
        self.UpdateTime(inTime)

        # store byte data into DaqNode local FIFO
        wordType = inByte.wordType
        row = inByte.originRow
        col = inByte.originCol
        d = DaqData(self.relTicksNow, wordType, row, col, inByte)
        self._localFifo.Write(d)
        self.received_asics.add((row, col)) 

        if self._debugLevel > 0:
            print(f"DAQ-{self.relTicksNow} ", end=" ")
            print(f"from: ({inByte.originRow},{inByte.originCol})", end="\n\t")
            print(
                f"Hit Time: {inByte.timestamp} " + format(inByte.channelMask, "016b"),
                end="\n\t",
            )
            print(f"absT: {inTime}", end="\n\t")
            print(f"tDiff (ns): {(self.relTimeNow-inTime)*1e9:2.2f}")

        return []

    def GetTimestamp(self) -> QPByte:
        """
        Generate the QPByte which asks for an interrogation from the rest of the array.

        The packet returned here should, if sent to the base-node, create a hard-interrogate
        packet from all of the ASICs within the array.
        """
        ReqID = self._reqID
        request = QPByte(AsicWord.REGREQ, None, None, timeStamp=self.relTicksNow, ReqID=ReqID)

        # record this reqID and time to measure time
        self.nTimestamps += 1
        self.TimestampIDs.add(ReqID)

        # update and create request
        self._reqID += 1
        return request

    def RegWrite(self, row, col, config) -> QPByte:
        """
        Helper function which issues a register request to a single ASIC-node.
        """
        byte = QPByte(AsicWord.REGREQ, None, None, Dest=1, XDest=row, YDest=col,
                      ReqID=self._reqID, OpWrite=True, config=config)
        self._reqID += 1
        return byte

    def Calibrate(self):
        """
        Use all of the stored FIFO data and their timestamps to
        create a calibration for all of the recorded ASICs.
        """
        pass

    class DaqFifo(QPFifo):
        """
        DaqFifo works like normal QPFifo but stores different state variables.

        The main difference is the overloaded Write method which needs to parse
        different incoming word types to ensure that the DAQNode is receiving what
        it thinks it should.
        """
        def __init__(self):
            super().__init__()
            self._dataWords = 0
            self._endWords = 0
            self._reqWords = 0
            self._respWords = 0

            # easy access for calibration TODO refactor
            self.evtWords = []

        def Write(self, data:DaqData) -> int:
            if not isinstance(data, DaqData):
                raise QPException(f"Can not add this data-type to the DaqNode local FIFO! {type(data)}")

            self._data.append(data)
            self._curSize += 1
            self._totalWrites += 1

            if data.wordType == AsicWord.DATA:
                self._dataWords += 1
            elif data.wordType == AsicWord.EVTEND:
                self._endWords += 1
                self.evtWords.append((data.row, data.col, data.daqT, data.qbyte.timeStamp))
            elif data.wordType == AsicWord.REGREQ:
                self._reqWords += 1
            elif data.wordType == AsicWord.REGRESP:
                self._respWords += 1

            if self._curSize > self._maxSize:
                self._maxSize = self._curSize

            if self._curSize > self._maxDepth:
                self._full = True

            return self._curSize

        def Read(self) -> DaqData:
            if self._curSize > 0:
                self._curSize -= 1
                return self._data.pop(0)
            else:
                return None
