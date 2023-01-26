from QpixAsic import QPByte, QPixAsic, ProcQueue, DaqNode, AsicWord, AsicState, AsicConfig, AsicDirMask
import matplotlib.pyplot as plt
import random
import math
import time
import numpy as np

## helper functions
def MakeFifoBars(qparray):
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    
    ColorWheelOfFun = ["#"+''.join([random.choice('0123456789ABCDEF') for i in range(6)])
        for j in range(qparray._nrows * qparray._ncols)]

    LocalFifoMax = np.zeros((qparray._nrows * qparray._ncols))
    Names = []
    for i, asic in enumerate(qparray):
        LocalFifoMax[i] = asic._localFifo._maxSize
        Names.append(f'({asic.row}, {asic.col})')
        if asic._localFifo._full:
            print(f'asic ({asic.row}, {asic.col}) local fifo was full')

    plt.bar(Names, LocalFifoMax, color=ColorWheelOfFun)
    plt.title('Local Fifo Maximum Sizes')
    plt.ylabel('Max Sizes')
    plt.show()

    ## remote fifo current sizes
    ColorWheelOfFun = ["#"+''.join([random.choice('0123456789ABCDEF') for i in range(6)])
        for j in range(qparray._nrows * qparray._ncols)]

    remoteFifoCur = np.zeros((qparray._nrows * qparray._ncols))
    Names = []
    for i, asic in enumerate(qparray):
        remoteFifoCur[i] = asic._remoteFifo._curSize
        Names.append(f'({asic.row}, {asic.col})')
        if asic._localFifo._full:
            print(f'asic ({asic.row}, {asic.col}) local fifo was full')

    plt.bar(Names, remoteFifoCur, color=ColorWheelOfFun)
    plt.title('Remote Fifo Current Sizes')
    plt.ylabel('Cur Sizes')
    plt.show()

    fig, ax = plt.subplots(figsize = (8,8))

    RemoteFifoMax = np.zeros(qparray._nrows * qparray._ncols)
    patches = []

    plt.xticks(
        rotation=45, 
        horizontalalignment='right',
        fontweight='light',
    )
    for i, asic in enumerate(qparray):
        locals() [f'patch{i}'] = mpatches.Patch(color=ColorWheelOfFun[i], label=f'Asic ({asic.row}, {asic.col})')
        patches.append(locals() [f'patch{i}'])
        RemoteFifoMax[i] = asic._remoteFifo._maxSize
        if asic._remoteFifo._full:
            print(f'asic ({asic.row}, {asic.col}) remote fifo full')
        Nem = f'({asic.row}, {asic.col})'        
        ax.bar(Nem, RemoteFifoMax[i], color=ColorWheelOfFun[i])
    ax.set(ylabel='Max Sizes', title='Remote Fifo Maximum Sizes')
    if len(patches) < 10:
        ax.legend(handles=[*patches])
    plt.tight_layout()
    plt.show()

def heatMap(data, rows, cols, header="", ax=None, cbarlabel="", cbar_kw={}, **kwargs):
    """
    modified heatmap function based on matplotlib docs
    """

    if ax is None:
        print("getting ax")
        ax = plt.gca()

    im = ax.imshow(data, **kwargs)

    # color bar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    ax.set_xticks(np.arange(cols))
    ax.set_yticks(np.arange(rows))

    ax.tick_params(top=True, bottom=False,
                    labeltop=True, labelbottom=False)

    # Loop over data dimensions and create text annotations.
    for i in range(rows):
        for j in range(cols):
            text = ax.text(j, i, data[i][j],
                        ha="center", va="center", color="w")

    ax.set_title(f"{header}")

    return im, cbar

def viewAsicState(qparray, time_begin=-100e-9, time_end=300e-6):
    """
    viewing function to take in a processed QpixArray class.

    This function will plot all of the ASIC states in a broken_barh graph
    with different colors based on AsicState enum class.

    The inspection range of times are controlled with time_begin and time_end.
    """

    color_mapping = {}
    for state in AsicState:
        color_mapping[state] = f"C{state.value}"

    asics = []
    for asic in qparray:
        asics.append(asic)

    # unpack the data into arrays of states and times
    states = [[] for i in range(len(asics))]
    relTimes = [[] for i in range(len(asics))]
    for i, asic in enumerate(asics):
        for (state, relTime, _) in asic.state_times:
            states[i].append(state)
            relTimes[i].append(relTime)

    # make the graph 
    fig, ax = plt.subplots()
    ax.set_ylim(0.5, len(asics)+3)

    # repack the data into a viewable format for barh
    i = 1
    for asic_states, asic_relTimes in zip(states[:], relTimes[:]):
        asic_state_widths = []
        state_colors = []
        cur_state = asic_states[0]
        cur_time = asic_relTimes[0]
        for state, time in zip(asic_states, asic_relTimes):
            # we've moved to a new state at this time
            if state != cur_state:
                asic_state_widths.append((cur_time, time-cur_time))
                state_colors.append(color_mapping[cur_state])
                cur_state = state
                cur_time = time
        ax.broken_barh(asic_state_widths, (i, 0.50),
                        facecolors=state_colors)
        i += 1

    ax.grid(True)
    ax.set_yticks([i+1.15 for i in range(len(asics))], labels=[f"({asic.row}, {asic.col})" for asic in asics])
    ax.set_xlim(time_begin, time_end)
    plt.tight_layout()

    # fake legend points
    markers = [plt.Line2D([0,0],[0,0],color=color, marker='o', linestyle='') for color in color_mapping.values()]
    plt.legend(markers, color_mapping.keys(), numpoints=1)
    plt.show()

def PrintTsMap(qparray):
    """
    boiler plate code for printing interesting data about each asic
    """
    for i, asic in enumerate(qparray):
        print(asic.lastTsDir, end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintTimeMap(qparray):
    for i, asic in enumerate(qparray):
        print(asic.relTimeNow, end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintTicksMap(qparray):
    print("Total Ticks")
    for i, asic in enumerate(qparray):
        print(asic.relTicksNow, end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintMeasureMap(qparray):
    print("Measured Transmissions:")
    for i, asic in enumerate(qparray):
        print(asic._measurements, end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintReceiveMap(qparray):
    print("Received Transmissions:")
    for i, asic in enumerate(qparray):
        print(asic._hitReceptions, end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintTimes(qparray):
    print("Tick Values :")
    for i, asic in enumerate(qparray):
        print(f"{asic.relTicksNow:1.2E}", end=" ")
        if (i+1)%qparray._nrows == 0:
            print()
    print("Rel Time Values (us):")
    for i, asic in enumerate(qparray):
        print(f"{(asic.relTimeNow)*1e6:1.2E}", end=" ")
        if (i+1)%qparray._nrows == 0:
            print()
    print("Abs Time Values (us):")
    for i, asic in enumerate(qparray):
        print(f"{(asic._absTimeNow - qparray[0][0]._absTimeNow)*1e6:1.2E}", end=" ")
        if (i+1)%qparray._nrows == 0:
            print()
    print("Measured Time Values (us):")
    for i, asic in enumerate(qparray):
        print(f"{(asic._measuredTime[-1] - qparray[0][0]._measuredTime[-1])*1e6:3.2f}", end=" ")
        if (i+1)%qparray._nrows == 0:
            print()

def PrintTransactMap(qparray, silent=False):
    """
    Helper function which iterates through a QPixArray and returns a dictionary of information
    for the QPFifos for each asic within the Array.
    """
    dMap = {}
    localT, remoteT, remoteMax = [], [], []

    if not silent:
        print(f"tile with route {qparray.RouteState} Transmission map:")
        print("Local Transmissions:")
    for i, asic in enumerate(qparray):
        localWrites = asic._localFifo._totalWrites
        localT.append((asic.row, asic.col, localWrites))
        if not silent:
            print(localWrites, end=" ")
            if (i+1)%qparray._nrows == 0:
                print()
    dMap["LocalT"] = localT

    if not silent:
        print("Remote Transmissions:")
    for i, asic in enumerate(qparray):
        remoteTransacts = asic._remoteFifo._totalWrites
        remoteT.append((asic.row, asic.col, remoteTransacts))
        if not silent:
            print(remoteTransacts, end=" ")
            if (i+1)%qparray._nrows == 0:
                print()
    dMap["RemoteT"] = remoteT

    if not silent:
        print("Remote Max Sizes:")
    for i, asic in enumerate(qparray):
        rMax = asic._remoteFifo._maxSize
        remoteMax.append((asic.row, asic.col, rMax))
        if not silent:
            print(rMax, end=" ")
            if (i+1)%qparray._nrows == 0:
                print()
    dMap["RemoteMax"] = remoteMax

    return dMap

## end helper functions

class QpixAsicArray():
    """
    Class purpose is to streamline creation of a digital asic array tile for the
    QPix project. Controls main sequencing of spread of asic clock cycles
    VARS:
      nrows       - rows within the array
      ncols       - columns within the array
      nPixs=16    - number of channels for each ASIC
      fNominal    - Default clock frequency (default ~50 MHz)
      pctSpread   - std distribution of ASIC clocks (default 5%)
      deltaT      - stepping interval for the simulation
      timeEpsilon - stepping time interval for simulation (default 1e-6)
      debug       - debug level, values >= 0 produce text output (default 0)
      tiledf      - tuple of asic hits to load into the array, tile dataframe is created from radiogenicNB
      RouteState  - string or None type member to define current routing method of Array
      push_state  - enable flag that is sent to ASICs within the array enabling push
    """
    def __init__(self, nrows, ncols, nPixs=16, fNominal=30e6, pctSpread=0.05, deltaT=1e-5, timeEpsilon=1e-6,
                timeout=1.5e4, hitsPerSec = 20./1., debug=0.0, tiledf=None):

        # if we have a tiledf to construct an array, then the size is determined by the tile
        if tiledf is not None:
            self._nrows = tiledf["nrows"]
            self._ncols = tiledf["ncols"]
        else:
            self._nrows = nrows
            self._ncols = ncols

        # array parameters
        self._tickNow = 0
        self._timeNow = 0
        self._debugLevel = debug
        self._nPixs = nPixs
        self.fNominal = fNominal
        self.pctSpread = pctSpread
        self.RouteState = None
        self.push_state = False

        # the array also manages all of the processing queue times to use
        self._queue = ProcQueue()
        self._timeEpsilon = timeEpsilon
        self._deltaT = deltaT
        self._deltaTick = self.fNominal * self._deltaT

         # Make the array and connections
        self._asics = self._makeArray(timeout=timeout, randomRate=hitsPerSec)
        self._daqNode = DaqNode(fOsc = self.fNominal, nPixels = 0, debugLevel=self._debugLevel, timeout=timeout, randomRate=hitsPerSec)

        self._asics[0][0].connections[AsicDirMask.West.value].asic = self._daqNode

        self._alert = 0

        # load in hits if we're creating an array based on tiledf data
        if tiledf is not None:
            self._InjectHits(tiledf["hits"])
   
    def __iter__(self):
        '''returns iterable through the asics within the array'''
        for asic_row in self._asics:
            for asic in asic_row:
                yield asic

    def __getitem__(self, row):
        '''
        make the array subscriptable to get whichever item we want
        '''
        assert row <= self._nrows - 1, "not enough rows in that array" 
        return self._asics[int(row)]

    def _makeArray(self, timeout, randomRate):
        """
        helper function designed to construct QPix asic values within array type
        """
        matrix = [[] for j in range(self._nrows)]

        for i in range(self._nrows):
            for j in range(self._ncols):
                frq = random.gauss(self.fNominal,self.fNominal*self.pctSpread)
                matrix[i].append(QPixAsic(frq, self._nPixs, row=i, col=j, debugLevel=self._debugLevel, timeout=timeout, randomRate=randomRate))
                
                if self._debugLevel > 0:
                    print(f"Created ASIC at row {i} col {j} with frq: {frq:.2f}")

        # connect the asics within the array
        for i in range(self._nrows):
            for j in range(self._ncols):
                if i > 0:
                    matrix[i][j].connections[AsicDirMask.North.value].asic = matrix[i-1][j]
                if i < self._nrows-1:
                    matrix[i][j].connections[AsicDirMask.South.value].asic = matrix[i+1][j]
                if j > 0:
                    matrix[i][j].connections[AsicDirMask.West.value].asic = matrix[i][j-1]
                if j < self._ncols-1:
                    matrix[i][j].connections[AsicDirMask.East.value].asic = matrix[i][j+1]    

        return matrix

    def readData(self):
        """
        function call to issue a command to read data from the full array
        """
        data = []
        readTime = time.perf_counter()

        for asic in self:
            data += asic.Process(readTime)

        stopTime = time.perf_counter()
        self._processTime = stopTime - readTime

        if self._debugLevel >= 5:
            print(f"processing time was: {self._processTime:.4f}")

        return data

    def Calibrate(self, interval=1.0):
        """
        function used to calibrate timing interval of all underlying asics, assuiming
        no current knowledge of underlying times / frequencies
        ARGS:
            interval - time in seconds to issue two different commands and to read time value pairs back from asics
        """
        self._alert = 0
        t1 = self._timeNow + interval
        calibrateSteps = self._Command(t1, command="Calibrate")

        t2 = self._timeNow + interval
        calibrateSteps = self._Command(t2, command="Calibrate")

    def Interrogate(self, interval=0.1):
        """
        Function for issueing command to base node from daq node, and beginning
        a full readout sequence of timestamp data.
        The ratio duration/interval gives the number of interrogations
        VARS:
            interval - how often the daq interrogates the asics
            duration - how long the simulation will run for
        """
        
        self._alert=0
        time = self._timeNow + interval
        readoutSteps = self._Command(time, command="Interrogate")

    def WriteAsicRegister(self, row, col, config, timeEnd=1e-3):
        """
        Function sends a destination register read or write to the located asic

        ARGS:
            row    - XDest
            col    - YDest
            config - configuration type to be written to specific ASIC
            timeEnd - how long to process the array forward till, default ~1 ms
        """
        assert isinstance(config, AsicConfig), "unsuitable configuration type to write to register"
        assert row < self._nrows and row >= 0, f"row {row} unable for this array"
        assert col < self._ncols and col >= 0, f"col {col} unable for this array"

        # build the DaqNode request
        ReqID = self._daqNode._reqID
        byte = QPByte(AsicWord.REGREQ, None, None, Dest=1, XDest=row, YDest=col, ReqID=ReqID, OpWrite=True, config=config)
        self._daqNode._reqID += 1

        # issue the byte command, and move forward in time
        timeProc = self._timeNow + timeEnd
        self._Command(timeProc, byte=byte)

    def _Command(self, timeEnd, command=None, byte=None):
        """
        Function for issueing command to base node from daq node, and beginning
        a full readout sequence
        VARS:
            timeEnd - how long the array should be processed until
            command - string argument that the asics receive to tell them what readout is coming in from DAQnode

        NOTE Basic Unit of simulation:
            ASIC      - receiving data
            Direction - source direction of incoming data
            QPByte    - source data, 64 bit word
            hitTime   - transaction complete time from source ASIC
            Command   - optional argument passed to receive data to tell receiving
                        ASIC to behave differently
        """

        # add the initial broadcast to the queue
        if byte is None:
            ReqID = self._daqNode._reqID
            request = QPByte(AsicWord.REGREQ, None, None, timeStamp=self._tickNow, ReqID=ReqID)
            self._daqNode._reqID += 1
        else:
            request = byte
        self._queue.AddQueueItem(self[0][0], AsicDirMask(3), request, self._timeNow, command=command)

        # move the Array forward in time
        self._Process(timeEnd)

        return self._queue.processed

    def _ProcessArray(self, nextTime):
        """
        move all processing of the array up to absTime
        """
        processed = 0
        somethingToDo = True
        while somethingToDo:
            somethingToDo = False
            for asic in self:
                newProcessItems = asic.Process(nextTime)
                if newProcessItems:
                    somethingToDo = True
                    for item in newProcessItems:
                        processed += 1
                        self._queue.AddQueueItem(*item)
        return processed

    def _Process(self, timeEnd):
        """
        Main logic function to move the all ASICs within the Array forward in
        time to timeEnd.

        ARGS:
        timeEnd - 'absolute' time to move Array to. If Array is already at this
                   time, this function will do nothing
        """
        steps = 0
        PROCITEM = 0
        while(self._timeNow < timeEnd):

            # for asic in self:
            #     newProcessItems = asic.Process(self._timeNow - self._timeEpsilon)
            #     if newProcessItems:
            #         self._alert = 1
            #         for item in newProcessItems:
            #             self._queue.AddQueueItem(*item)

            # process transactions
            while(self._queue.Length() > 0):

                if self._debugLevel > 0:
                    print(f"step-{steps} | time-{self._timeNow} | process size-{self._queue.Length()}")
                    for asic in self:
                        print(f"\t({asic.row}, {asic.col}): {asic.state} - {asic.relTicksNow}")

                # pop the next simulation unit
                steps += 1
                nextItem = self._queue.PopQueue()
                asic = nextItem.asic
                hitTime = nextItem.inTime

                # ASICs to catch up to this time, and to send data
                p1 = self._ProcessArray(hitTime)

                # ASIC to receive data
                newProcessItems = asic.ReceiveByte(nextItem)
                if newProcessItems:
                    for item in newProcessItems:
                        self._queue.AddQueueItem(*item)

                # p2 = self._ProcessArray(hitTime)

            self._timeNow += self._deltaT
            self._tickNow += self._deltaTick

    def SetPushState(self, enabled=True, transact=False):
        """
        This function will send a ASIC configuration write to all ASICs
        enabling the PushState
        """
        assert isinstance(enabled, bool), "must supply boolean state to enable to ASICs"

        self.push_state = enabled

        for asic in self:
            config = asic.config
            config.EnablePush = enabled
            if transact:
                self.WriteAsicRegister(asic.row, asic.col, config)
            else:
                asic.config = config

    def IdleFor(self, interval=0.5):
        """
        Function will move the array forward by this time. This is meant
        to be a replacement for the Interrogate method while the ASICs are
        in a push state.

        ARGS:
        interval - time in seconds to move the array forward
        """
        timeEnd = self._timeNow + interval
        self._Process(timeEnd)

    def Route(self, route=None, timeout=None, transact=True):
        '''
        Defines the routing of the asics manually
        ARGS:
        -- 
        Route: string->
            left  - routes all of the remote information to the left most asics
                    then moves all data to (0,0)
            snake - serpentine style, snakes through all asics before
                    remote data origin until (0,0)
        --
        transact: bool, if true (default) will simulate daq node transactions
                        if false, will automagically update asic configs
        '''
        self.RouteState = route
        if timeout is None:
            timeout = self[0][0].config.timeout
        if route == None:
            return
        elif route.lower() == 'left':
            for asic in self:
                if asic.row == 0: 
                    config = AsicConfig(AsicDirMask.West, timeout)
                elif not(asic.col == 0):
                    config = AsicConfig(AsicDirMask.West, timeout)
                else:
                    config = AsicConfig(AsicDirMask.North, timeout)
                config.ManRoute = True
                if transact:
                    self.WriteAsicRegister(asic.row, asic.col, config)
                else:
                    asic.config = config
        elif route.lower() == 'snake':
            for asic in self:
                if not(asic.row%2 == 0) and asic.col == self._ncols-1:
                    config = AsicConfig(AsicDirMask.North, timeout)
                elif asic.row%2 == 0:
                    if asic.col == 0 and not(asic.row == 0):
                        config = AsicConfig(AsicDirMask.North, timeout)
                    else:
                        config = AsicConfig(AsicDirMask.West, timeout)
                else:
                    config = AsicConfig(AsicDirMask.East, timeout)
                config.ManRoute = True
                if transact:
                    self.WriteAsicRegister(asic.row, asic.col, config)
                else:
                    asic.config = config
        else:
            print("WARNING: unknown route state passed!", self.RouteState)

    def _InjectHits(self, dataframeHits):
        """
        InjectHits reads in output from tiledf created in radiogenicNB.ipynb. 
        Values that are read in

        This function should be
        ARGS:
            dataframeHits : tuple which stores (asicX :int, asicY :int, times :list)
        """
        # store the asic times into the correct asic
        for asicX, asicY, times in dataframeHits:
            times = np.asarray(times)
            self._asics[asicX][asicY].InjectHits(times)



if __name__ == "__main__":
    array = QpixAsicArray(2,2)
    array.Calibrate()
    data = array.readData()
    print("read the following data:\n", data)
