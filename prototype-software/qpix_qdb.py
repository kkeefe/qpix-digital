# interfacing dependcies
from qdb_interface import (AsicREG, AsicCMD, AsicEnable, AsicMask,
                           qdb_interface, QDBBadAddr, REG, SAQReg, DEFAULT_PACKET_SIZE, SAQ_BIN_FILE)
import os
import sys
import time

# PyQt GUI things
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QPushButton, QCheckBox, QSpinBox, QLabel,
                             QDoubleSpinBox, QProgressBar, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStatusBar,
                             QDialog, QDialogButtonBox, QLCDNumber)
from PyQt5.QtCore import QProcess, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction

# for output data
from array import array
import ROOT
import numpy as np
# for spawning other process to turn binary data into ROOT
import subprocess 


class dialogWindow(QDialog):
    """
    QDialog class which provides check boxes to choose to accept triggers for
    specified channels.  default is OFF, and checks indicate that the
    corresponding channel will allow a reset to trigger.
    """

    acceptedMask = pyqtSignal(int)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("SAQ Mask")
        size = 15
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self._makeMask)
        self.buttonBox.rejected.connect(self.reject)

        self.mask = 0
        self.layout = QVBoxLayout(self)

        self.layout.addStretch()
        self.checkBoxes = []
        for i in range(size):
            p = QCheckBox(f"Channel - {i+1}")
            self.checkBoxes.append(p)
            self.layout.addWidget(p)

        self.layout.addWidget(self.buttonBox)
        self.layout.addStretch()
        self.setLayout(self.layout)

    def _makeMask(self):
        mask = 0
        for i, box in enumerate(self.checkBoxes):
            if box.isChecked():
                mask += 1 << i

        self.acceptedMask.emit(mask)
        self.accept()

class QPIX_GUI(QMainWindow):

    close = pyqtSignal()

    def __init__(self):
        super(QMainWindow, self).__init__()

        # IO interfaces
        self.qpi = qdb_interface()
        self.close.connect(self.qpi.finish)
        self._tf = ROOT.TFile("./test.root", "RECREATE")
        self._tt = ROOT.TTree("qdbData", "data_tree")
        self._saqMask = 0

        # storage tree setup words
        self._data = {
            "trgT" : array('L', [0]),
            "daqT" : array('L', [0]),
            "asicT" : array('L', [0]),
            "asicX" : array('H', [0]),
            "asicY" : array('H', [0]),
            "wordType" : array('H', [0])}
        types = ["trgT/i", "daqT/i", "asicT/i", "asicX/b", "asicY/b", "wordType/b"]
        for data, typ in zip(self._data.items(), types):
            self._tt.Branch(data[0], data[1], typ)

        # window setup
        self.setWindowTitle('QPix Viewer')

        # passive triggering
        self._clock = QTimer()
        self._clock.timeout.connect(self.trigger)
        self._lastTrig = -1

        # initialize the sub menus
        self._make_menuBar()
        self._make_statusBar()

        # create the layouts that are needed for making the GUI pretty
        self.tabW = QTabWidget()
        self.tabW.addTab(self._makeSAQlayout(), "SAQ")
        self.tabW.addTab(self._makeQDBlayout(), "QDB")
        self.setCentralWidget(self.tabW)

        # show the main window
        self.show()

    def _makeQDBlayout(self):
        """
        Wrapper function to store all of the QDB widgets into a single layout,
        and finally add it to the main window's QStackLayout
        """

        self._qdbPage = QWidget()
        layout = QGridLayout()

        # progress tracker
        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(0)
        layout.addWidget(pbar, 2, 2)
        self._progBar = pbar

        btn_init = QPushButton()
        btn_init.setText('initialize')
        btn_init.clicked.connect(self.initialize)
        layout.addWidget(btn_init, 0, 0)

        btn = QPushButton()
        btn.setText('trigger')
        btn.clicked.connect(self.trigger)
        layout.addWidget(btn, 0, 1)

        btn_readEvents = QPushButton()
        btn_readEvents.setText('get events')
        btn_readEvents.clicked.connect(self.readEvents)
        layout.addWidget(btn_readEvents, 0, 2)

        btn_trgTime = QPushButton()
        btn_trgTime.setText('get trigger time')
        btn_trgTime.clicked.connect(self.getTrigTime)
        layout.addWidget(btn_trgTime, 0, 3)

        btn_getFrq = QPushButton()
        btn_getFrq.setText('get frequency')
        btn_getFrq.clicked.connect(self.estimateFrequency)
        layout.addWidget(btn_getFrq, 0, 4)

        btn_iter = QPushButton()
        btn_iter.setText('iter trg')
        btn_iter.clicked.connect(self.begin_trig_clock)
        layout.addWidget(btn_iter, 1, 0)

        ## ASIC commands ##
        btn_rst = QPushButton()
        btn_rst.setText('reset')
        btn_rst.clicked.connect(self.resetAsic)
        layout.addWidget(btn_rst, 1, 1)

        btn_mask = QPushButton()
        btn_mask.setText('mask')
        btn_mask.clicked.connect(self.setAsicDirMask)
        layout.addWidget(btn_mask, 1, 2)

        btn_gtimeout = QPushButton()
        btn_gtimeout.setText('get timeout')
        btn_gtimeout.clicked.connect(self.getAsicTimeout)
        layout.addWidget(btn_gtimeout, 1, 3)

        btn_stimeout = QPushButton()
        btn_stimeout.setText('set timeout')
        btn_stimeout.clicked.connect(self.setAsicTimeout)
        layout.addWidget(btn_stimeout, 1, 4)

        self.chk_enable = QCheckBox()
        self.chk_enable.setText('asic enable')
        self.chk_enable.setCheckState(0)
        self.chk_enable.stateChanged.connect(self.enableAsic)
        layout.addWidget(self.chk_enable, 0, 5)

        ##  Int Containers  ###
        sBox = QSpinBox()
        sBox.setValue(1)
        sBox.setRange(1, 100)
        layout.addWidget(sBox, 3, 0)
        # lsBox = QLabel()
        # lsBox.setText("N-Integrations")

        sBox_frqStart = QSpinBox()
        sBox_frqStart.setValue(1)
        sBox_frqStart.setRange(1, 100)
        layout.addWidget(sBox_frqStart, 3, 1)
        # lsBox = QLabel()
        # lsBox.setText("Frq Start (Hz)")

        sBox_frqStop = QSpinBox()
        sBox_frqStop.move(240,80)
        sBox_frqStop.setValue(5)
        sBox_frqStop.setRange(1, 100)
        layout.addWidget(sBox_frqStop, 3, 2)
        # lsBox = QLabel()
        # lsBox.setText("Frq Stop (Hz)")
        # lsBox.move(310, 85)

        sBox_frqIter = QDoubleSpinBox()
        sBox_frqIter.move(240,120)
        sBox_frqIter.setValue(0.5)
        sBox_frqIter.setRange(0.1, 100)
        layout.addWidget(sBox_frqIter, 3, 3)
        # lsBox = QLabel()
        # lsBox.setText("Frq Iteration")
        # lsBox.move(340, 125)

        # button information for interrogation timer
        sBox_timeIter = QDoubleSpinBox()
        sBox_timeIter.move(120,200)
        sBox_timeIter.setValue(0.5)
        sBox_timeIter.setRange(0.1, 100)
        layout.addWidget(sBox_timeIter)
        self._timeValue = sBox_timeIter
        # lsBox = QLabel()
        # lsBox.setText("time Iteration")
        # lsBox.move(240, 205)

        self._qdbPage.setLayout(layout)
        return self._qdbPage

    def _makeSAQlayout(self):
        """
        Wrapper function to make the layout for all of the SAQ widgets and to store them
        into the QMainWindow's QStackedLayout
        """
        self._saqPage = QWidget()
        layout = QVBoxLayout()

        ## SAQ commands  ##
        btn_sScratch = QPushButton()
        btn_sScratch.setText('READ SAQ Scratch')
        btn_sScratch.clicked.connect(self.getSAQScratch)
        layout.addWidget(btn_sScratch)

        btn_sFifo = QPushButton()
        btn_sFifo.setText('READ SAQ Fifo')
        btn_sFifo.clicked.connect(self.getSAQFifo)
        layout.addWidget(btn_sFifo)

        btn_sDMA = QPushButton()
        btn_sDMA.setText('Print SMA Registers')
        btn_sDMA.clicked.connect(self.getDMARegisters)
        layout.addWidget(btn_sDMA)

        btn_sDMA = QPushButton()
        btn_sDMA.setText('Reset SMA Registers')
        btn_sDMA.clicked.connect(self.resetDMA)
        layout.addWidget(btn_sDMA)

        # SAQ Mask box
        hMaskLayout = QHBoxLayout()
        masklsBox = QLabel()
        masklsBox.setText("Mask (Enable High)")
        hMaskLayout.addWidget(masklsBox)

        saqMaskBox = QSpinBox()
        # maximum of 15 bits
        saqMaskBox.setRange(0, 0x7fff)
        saqMaskBox.setValue(1)
        hMaskLayout.addWidget(saqMaskBox)
        self._saqMaskBox = saqMaskBox

        btn_sMask = QPushButton()
        btn_sMask.setText('Update SAQ Mask')
        btn_sMask.clicked.connect(self.setSAQMask)
        hMaskLayout.addWidget(btn_sMask)
        layout.addLayout(hMaskLayout)

        hLengthLayout = QHBoxLayout()
        saqLengthL = QLabel()
        saqLengthL.setText("Update Packet Length")
        hLengthLayout.addWidget(saqLengthL)

        saqLength = QSpinBox()
        saqLength.setRange(0, 0x0000_3fff)
        saqLength.setValue(DEFAULT_PACKET_SIZE)
        hLengthLayout.addWidget(saqLength)
        self._saqLength = saqLength

        btn_packetL = QPushButton()
        btn_packetL.setText('Update Packet Length')
        btn_packetL.clicked.connect(self.setSAQLength)
        hLengthLayout.addWidget(btn_packetL)
        layout.addLayout(hLengthLayout)

        hLCDlabel = QHBoxLayout()
        pktLabel = QLabel("Current Packet Length")
        hitLabel = QLabel("Current Fifo Hits")
        hLCDlabel.addWidget(pktLabel)
        hLCDlabel.addWidget(hitLabel)
        layout.addLayout(hLCDlabel)

        hLCDLayout = QHBoxLayout()
        self.saq_packets = QLCDNumber()
        self.saq_packets.display(DEFAULT_PACKET_SIZE)
        hLCDLayout.addWidget(self.saq_packets)

        self.saq_hits = QLCDNumber()
        self.saq_hits.display(0)
        hLCDLayout.addWidget(self.saq_hits)
        layout.addLayout(hLCDLayout)

        self._saqPage.setLayout(layout)
        return self._saqPage

    ############################
    ## Zybo specific Commands ##
    ############################
    def initialize(self):
        """
        main working function which provides a one-click setup
        
        to initialze the array. Current implementation of the hdl
        in the lattice chips require a reset, and non-default routing
        """
        # currently only one ASIC connected to the zybo which should be
        # pointed downwards
        self.resetAsic(0,0)
        self.setAsicDirMask(0,0, AsicMask.DirDown)

    def trigger(self):
        """
        Send a basic trigger packet to the board.

        This interrogation will be sent to all ASICs in the array, and memory
        will be recorded into the BRAM within QpixDaqCtrl.vhd.
        """
        addr = REG.CMD
        val = AsicCMD.Interrogation
        self.readEvents()
        wrote = self.qpi.regWrite(addr, val)

    def readEvents(self) -> int:
        """
        Main Data Read function.

        Will read the evtSize from the Zybo and will read and fill stored TTree member.

        After all events have been read, the TFile is updated with a Write.

        NOTE: The RxByte  is a 64 bit word defined in QpixPkg.vhd where a Byte
              is formed from the record transaction. The 'getMeta' helper
              function below details how the meta-data is stored into 64 bits.
        """
        addr = REG.EVTSIZE
        evts = self.qpi.regRead(addr)
        if evts:
            print("found evts:", evts)
        else:
            print("no events recorded.")
            return

        # If we have events, we should record when a trigger went out to store them
        trigTime = self.getTrigTime()
        if trigTime == self._lastTrig:
            print("WARNING already recorded this event")
            return
        self._data["trgT"][0] = trigTime
        self._lastTrig = trigTime

        def getMeta(data):
            """
            helper function to extract useful data from middle word in event
            """
            # y pos is lowest 4 bits
            y = d & 0xf

            # x pos is bits 7 downto 4
            x = (d >> 4) & 0xf

            # chanMask is next 16 bits
            chanMask = (d >> 8) & 0xffff

            # wordType is next 24 bits
            wordType = (d >> 24) & 0xf

            return y, x, chanMask, wordType

        # keep track of the readback progress..
        self._progBar.setRange(0, evts)

        # read back all of the events now, and each event has 32*3 bits..
        for evt in range(evts):
            # read each word in the event
            asicTime = self.qpi.regRead(REG.MEM(evt, 0))
            d = self.qpi.regRead(REG.MEM(evt, 1))
            y, x, chanMask, wordType = getMeta(d)
            daqTime = self.qpi.regRead(REG.MEM(evt, 2))
            self._progBar.setValue(evt+1)

            # store and fill each event into the tree, writing when done
            self._data["daqT"][0] = daqTime
            self._data["asicT"][0] = asicTime
            self._data["asicX"][0] = x
            self._data["asicY"][0] = y
            # TODO
            # self._data["channelMask"][0] = chanMask
            self._data["wordType"][0] = wordType
            self._tt.Fill()

        self._tf.Write()
        return evts

    def getTrigTime(self) -> int:
        """
        Read in the trgTime register value.

        the trgTime value is the daqTime recorded on the zybo whenever a trigger
        is initiated.
        """
        trgTime = self.qpi.regRead(REG.TRGTIME)
        return trgTime

    def estimateFrequency(self):
        """
        Similar to Calibration method within the simulation.

        ARGS: Delay - how long to wait in seconds

        Issues two different 'Calibration' asic requests and records times from
        the Zybo and QDB arrays. print out interesting time measurements between
        the trigger to estimate a frequency: counts / time
        """

        # get the starting times
        time_start = time.time()
        asic_time_s = self.getAsicTime()
        time_trig_start = time.time()
        time_s = (time_start + time_trig_start)/2
        daq_trig_start = self.getTrigTime()

        time.sleep(0.1)

        # get the end times
        time_end = time.time()
        asic_time_e = self.getAsicTime()
        time_trig_end = time.time()
        time_e = (time_end + time_trig_end)/2
        daq_trig_end = self.getTrigTime()

        daq_cnt = daq_trig_end - daq_trig_start
        dt = time_e - time_s
        fdaq = (daq_cnt / dt)
        print(f"Daq Frq: {fdaq/1e6:0.4f} MHz")

        asic_cnt = asic_time_e - asic_time_s
        fasic = fdaq * (asic_cnt / daq_cnt)
        print(f"ASIC Frq: {fasic/1e6:0.4f} MHz")

        # calculate running differences
        # current test 7/25: Diff Frq: 0.0859 +/- 0.0038 MHz
        if not hasattr(self, "_diffFrq"):
            self._diffFrq = []
        self._diffFrq.append((fasic-fdaq)/1e6)
        print(f"Diff Frq: {np.mean(self._diffFrq):0.4f} +/- {np.std(self._diffFrq):0.4f} MHz")

    def begin_trig_clock(self):
        """
        looping interrogation triggers based on value from adjacent spinbox
        double
        """
        val = int(self._timeValue.value()*1000)
        self._clock.setInterval(val)
        print(f"setting value {val} ms")
        if self._clock.isActive():
            print("stopping clock..")
            self._clock.stop()
        else:
            print("starting clock..")
            self._clock.start()

    def loopInterrogations(self, nInts: int, lFrqs: list):
        """
        function designed to loop through a interval set to test how quickly 
        interrogations can happen and still retrieve all of the data from remote
        ASICs
        ARGS:
            nInts - number of interrogations to perform at each rate
            lFrqs - list of frequencies to perform these interrogations at
        """

        periods = [ 1/f for f in lFrqs]

        for T in periods:
            for int in range(nInts):
                tStart = time.time()
                while tStart - tFin < T:
                    tStart = time.time()
                self.trigger()
                evts = self.readEvents()
                tFin = time.time()

    ############################
    ## ASIC specific Commands ##
    ############################
    def resetAsic(self, xpos=0, ypos=0):
        """
        Reset asic at position (xpos, ypos)
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.CMD)
        val = AsicCMD.ResetAsic
        self.qpi.regWrite(addr, val)

    def enableAsic(self, state, xpos=0, ypos=0):
        """
        Use AsicReg.ENA addr to set various types of AsicEnable configurations

        state - arg capture from state change of the checkbox

        Default is all on.
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.ENA)
        if self.chk_enable.isChecked():
            val = AsicEnable.ALL
        else:
            val = AsicEnable.OFF
        self.qpi.regWrite(addr, val)

        # read back the data that we think we enabled to see if it makes sense
        x, y, wordType, addr, enabled = self._readAsicEnable()

        if x != xpos or y != ypos:
            print(f"Enable WARNING: Read ({x}, {y}) instead of ({xpos},{ypos})")
        elif val != enabled:
            print(f"Enable WARNING: did not read correct enable value")
            print(f"\t expected {val} : actual {enabled}")

    def setAsicDirMask(self, xpos=0, ypos=0, mask=AsicMask.DirDown):
        """
        Change ASIC mask at position (xpos, ypos)
        """
        if not isinstance(mask, AsicMask):
            raise QDBBadAddr("Incorrect AsicMask!")

        addr = REG.ASIC(xpos, ypos, AsicREG.DIR)
        val = mask
        self.qpi.regWrite(addr, val)

    def setAsicTimeout(self, xpos=0, ypos=0, timeout=15000):
        """
        Change ASIC timeout value at position (xpos, ypos)
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.TIMEOUT)
        val = timeout
        self.qpi.regWrite(addr, val)

    def getAsicTimeout(self, xpos=0, ypos=0):
        """
        Change ASIC timeout value at position (xpos, ypos)
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.TIMEOUT)
        read = self.qpi.regRead(addr)
        x, y, wordType, addr, asicTimeout = self._readAsicTimeout()

        if x != xpos or y != ypos:
            print(f"Timeout WARNING: Read ({x}, {y}) instead of ({xpos},{ypos})")

        return asicTimeout

    def getAsicTime(self, xpos=0, ypos=0):
        """
        wrapper function for reading clkCnt register within QDBAsic, as defined
        in QPixRegFile.vhd
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.CAL)
        read = self.qpi.regRead(addr)
        x, y, wordType, timestamp = self._readAsicTime()

        if x != xpos or y != ypos:
            print(f"CAL WARNING: Read ({x}, {y}) instead of ({xpos},{ypos})")

        return timestamp

    def _readAsicTime(self):
        """
        helper function to parse data from the asic cal as stored in RegFile.vhd.

        This method is similar to _readAsicTimeout.
        """

        # this register stores the whole stamp in the bottom 32 bits
        timestamp = self.qpi.regRead(REG.MEM(0, 0))

        # next 32 bits
        word2 = self.qpi.regRead(REG.MEM(0, 1))
        y = word2 & 0xf
        x = (word2 >> 4) & 0xf
        wordType = (word2 >> 24) & 0xf

        return x, y, wordType, timestamp

    ############################
    ## SAQ specific Commands  ##
    ############################
    def getSAQScratch(self):
        """
        Function to read register from SAQ Scratch register
        """
        addr = REG.SAQ(SAQReg.SCRATCH)
        read = self.qpi.regRead(addr)
        print(f"read the value from addr {addr:08x}.. {read:08x}")

    def setSAQMask(self):
        """
        issue register write to SAQ mask value
        """
        mask = self._saqMaskBox.value()
        assert mask < 1<<15, "total number of bits is 15"
        self._saqMask = mask
        self._saqMaskBox.setValue(self._saqMask)

        # addr = REG.SAQ(SAQReg.MASK)
        # print(f"setting mask value: {mask}")
        # wrote = self.qpi.regWrite(addr, mask)

    def setSAQLength(self):
        """
        Read from the QSpinBox and set the new length register here. This will update
        the amount of incoming works on each incoming UDP packet.
        """
        nPackets = self._saqLength.value()
        addr = REG.SAQ(SAQReg.SAQ_FIFO_LNGTH)
        self.qpi.regWrite(addr, nPackets)

    def getSAQFifo(self):
        """
        Main reading function to read the SAQ Fifo and store data where it needs
        to go.
        """
        # flag REN to update buffer
        if bool(self.qpi.regRead(REG.SAQ(SAQReg.READ_ENABLE))):
            print("no new evts")
            return

        # read the two words off of the fifo:
        print("reading evt")
        timestamp = self.qpi.regRead(REG.SAQ(SAQReg.READ1))

        saq_mask = self.qpi.regRead(REG.SAQ(SAQReg.READ2))

        saq_mask = saq_mask & 0xff # mask is only bottom 8 bits

    def enableSAQ(self):
        """
        read / write the single bit register at SaqEnable to turn on Axi Fifo streaming.
        then update the saqMask to begin allowing triggers from saq pins
        """
        addr = REG.SAQ(SAQReg.SAQ_ENABLE)
        if self.saq_enable.isChecked():
            val = 1
        else:
            val = 0
        self.qpi.regWrite(addr, val)

        # enable the SAQ, update the mask, and put that value in the spin box
        if val == 1:
            addr = REG.SAQ(SAQReg.MASK)
            wrote = self.qpi.regWrite(addr, self._saqMask)
            self._saqMaskBox.setValue(self._saqMask)

    def flushSAQ(self):
        """
        terminate SAQ reading. Main function to halt data collection and read
        in all data to this moment.
        This function performs the following:
            1. deactivate SAQMask; prevents any more incoming trigger data
            2. ensure saqEnable is high; ensure saqFifo can write to AxiDataFifo
            3. write high bit to saqForce register, so that AxiDataFifo will be emptied.
        """
        # Step 1 - Turn off all mask bits
        addr = REG.SAQ(SAQReg.MASK)
        self.qpi.regWrite(addr, 0)

        # Step 2 - ensure enable is high
        addr = REG.SAQ(SAQReg.SAQ_ENABLE)
        val = 1
        self.qpi.regWrite(addr, val)
        self.saq_enable.setChecked(1)

        # Step 3 - ping high register space to enable saqForce
        addr = REG.SAQ(SAQReg.SAQ_FORCE)
        val = 1
        self.qpi.regWrite(addr, val)

    def getSAQHits(self):
        """
        read the SAQ Hit register buffer
        """
        addr = REG.SAQ(SAQReg.SAQ_FIFO_HITS)
        hits = self.qpi.regRead(addr)
        return hits

    def getDMARegisters(self):
        """
        Print the DMA register status, connected to a button
        """
        print("printing DMA Registers:")
        self.qpi.PrintDMA()

    def resetDMA(self):
        """
        reset DMA by pinging the correct ctrl register
        """
        print("reseting the DMA!")
        self.qpi._resetDMA()

    def _readAsicTimeout(self):
        """
        special helper function to unpack ASIC request word from BRAM memory.

        Layering of ASIC data is stored within QpixPkg.vhd, fQpixRegToByte function.
        """
        # NOTE: A request data from an asic resets MEM addr,
        # and that the MEM addr goes back to zero..
        word1 = self.qpi.regRead(REG.MEM(0, 0))
        word2 = self.qpi.regRead(REG.MEM(0, 1))

        # records when byte was received, and not related to ASIC cal request
        # daqTime = self.qpi.regRead(REG.MEM(0, 2))

        # first 32 bits
        timeout = word1 & 0xffff
        addr = (word1 >> 16) & 0xffff

        # next 32 bits
        y = word2 & 0xf
        x = (word2 >> 4) & 0xf
        wordType = (word2 >> 24) & 0xf

        print(f"Read x{wordType:01x} ASIC @ {addr:04x} timeout: 0x{timeout:04x}-{timeout}")

        return x, y, wordType, addr, timeout

    def _readAsicEnable(self):
        """
        special helper function to read the register at this location, largely
        based off of read timeout function
        """
        # NOTE: A request data from an asic resets MEM addr,
        # and that the MEM addr goes back to zero..
        word1 = self.qpi.regRead(REG.MEM(0, 0))
        word2 = self.qpi.regRead(REG.MEM(0, 1))

        # records when byte was received, and not related to ASIC reg request
        # daqTime = self.qpi.regRead(REG.MEM(0, 2))

        # first 32 bits
        # data in enable is the bottom 3 bits of data
        enabled = AsicEnable(word1 & 0x0007)
        addr = (word1 >> 16) & 0xffff

        # next 32 bits
        y = word2 & 0xf
        x = (word2 >> 4) & 0xf
        wordType = (word2 >> 24) & 0xf

        return x, y, wordType, addr, enabled
        
    def launchSaqDialog(self):
        """
        Function should manage creation of QDialog box which, if accepted,
        returns a new mask value to send to SAQ trigger register bits.
        """
        self._mask = 0x0

    def closeEvent(self, event):
        found = os.path.isfile(SAQ_BIN_FILE)
        if found and hasattr(self, "_outputFile"):
            subprocess.Popen(["python", "test_root.py", SAQ_BIN_FILE, self._outputFile])
        self.close.emit()

    ###########################
    ## GUI specific Commands ##
    ###########################
    def _make_statusBar(self):
        # manage whether or not the UDP / TCP connections are valid
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        saqDialogBtn = QPushButton("Set SAQ Mask")
        saqDialogBtn.clicked.connect(self.openDialog)
        self.statusBar.addWidget(saqDialogBtn)

        self.saq_enable = QCheckBox("SAQ Enable")
        self.saq_enable.setCheckState(0)
        self.saq_enable.stateChanged.connect(self.enableSAQ)
        self.statusBar.addWidget(self.saq_enable)

        # timer to periodically check and update what the number is
        self._lcdtimer = QTimer()
        self._lcdtimer.timeout.connect(self._updateLCD)
        self._lcdtimer.setInterval(1000)

        self.saq_lcd_enable = QCheckBox("Update LCDs")
        self.saq_lcd_enable.clicked.connect(self._enableLCDUpdate)
        self.statusBar.addWidget(self.saq_lcd_enable)

        # include a stop button, which will deactivate mask (prevent any triggers) and 
        # issue a flush to the FIFO. This SHOULD NOT deactivate saqEnable, which
        # will prevent saqFifo from writing to data fifo
        self.saq_force = QPushButton("SAQ Flush")
        self.saq_force.clicked.connect(self.flushSAQ)
        self.statusBar.addWidget(self.saq_force)

    def _enableLCDUpdate(self):
        if self.saq_lcd_enable.isChecked():
            self._lcdtimer.start()
        else:
            self._lcdtimer.stop()

    def _updateLCD(self):
        """
        Update the length of the packets before a TLast is issued from the FIFO.
        This will overwrite the maximum buffer length that is acceptible before
        a UDP packet is sent to SAQ worker.
        """
        addr = REG.SAQ(SAQReg.SAQ_FIFO_LNGTH)
        nPackets = self.qpi.regRead(addr)
        self.saq_packets.display(nPackets)
        hits = self.getSAQHits()
        self.saq_hits.display(hits)

    def _make_menuBar(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        # exit action
        exitAct = QAction(QIcon('exit.png'), '&Exit', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(self.close)

        # add the actions to the menuBar
        fileMenu = menubar.addMenu('File')
        fileMenu.addAction(exitAct)

    def openDialog(self):
        """
        Function opens dialogWindow class to prompt user for a new timestamp
        trigger mask.
        """
        self.dialog = dialogWindow()
        self.dialog.acceptedMask.connect(self.accept)
        self.dialog.rejected.connect(self.reject)
        self.dialog.exec()

    def accept(self, mask):
        """
        Called only on an accepted window, and updates SAQ trigger register
        space with new mask.
        """
        print(f"dialog accepted, setting mask value: {mask:015b}")
        self._saqMask = mask
        self._saqMaskBox.setValue(self._saqMask)

    def reject(self):
        pass


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = QPIX_GUI()
    app.exec_()