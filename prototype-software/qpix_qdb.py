# interfacing dependcies
from qdb_interface import (AsicREG, AsicCMD, AsicMask,
                           qdb_interface, QDBBadAddr, REG, SAQReg, DEFAULT_PACKET_SIZE, ZYBO_FRQ)
import os
import sys
import time

# PyQt GUI things
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QPushButton, QCheckBox, QComboBox, QSpinBox, QLabel,
                             QDoubleSpinBox, QProgressBar, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStatusBar,
                             QDialog, QDialogButtonBox, QLCDNumber, QFileDialog)
from PyQt5.QtCore import QProcess, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction

# for output data
from array import array
import ROOT
import numpy as np
import datetime
# for spawning other process to turn binary data into ROOT
import subprocess 


class dialogWindow(QDialog):
    """
    QDialog class which provides check boxes to choose to accept triggers for
    specified channels.  default is ON, and checks indicate that the
    corresponding channel will allow a reset to trigger.
    """

    acceptedMask = pyqtSignal(int)

    def __init__(self, mask):
        super().__init__()

        self.setWindowTitle("SAQ Mask")
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self._makeMask)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout(self)

        self.layout.addStretch()
        self.checkBoxes = []
        for i in range(16): # assume 16 channels in SAQ
            p = QCheckBox(f"Channel - {i+1}")
            p.setChecked(bool((1<<i) & mask))
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

    close_udp = pyqtSignal()

    def __init__(self):
        super(QMainWindow, self).__init__()

        # IO interfaces
        self.qpi = qdb_interface()
        self.close_udp.connect(self.qpi.finish) # closes udp worker thread

        self._tf = ROOT.TFile("./test.root", "RECREATE")
        self._tt = ROOT.TTree("qdbData", "data_tree")
        self._saqMask = 0xffff # default everything is on

        # SAQ meta data information
        self._start_hits = 0
        self._stop_hits = 0
        self.version = self.qpi.version

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
        self.tabW.addTab(self._makeQDBlayout(), "QDB")
        self.tabW.addTab(self._makeSAQlayout(), "SAQ")
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
        # pbar = QProgressBar()
        # pbar.setRange(0, 100)
        # pbar.setValue(0)
        # layout.addWidget(pbar, 2, 2)
        # self._progBar = pbar

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
        btn_iter.setText('get fifo cnt')
        btn_iter.clicked.connect(self.get_fifo_cnt)
        layout.addWidget(btn_iter, 1, 0)

        ## ASIC commands ##
        btn_rst = QPushButton()
        btn_rst.setText('reset state')
        btn_rst.clicked.connect(self.resetAsicState)
        layout.addWidget(btn_rst, 1, 1)

        btn_mask = QPushButton()
        btn_mask.setText('mask')
        btn_mask.clicked.connect(self.setAsicDirMask)
        layout.addWidget(btn_mask, 1, 2)

        btn_gtimeout = QPushButton()
        btn_gtimeout.setText('read reg')
        btn_gtimeout.clicked.connect(self.readReg)
        layout.addWidget(btn_gtimeout, 1, 3)

        btn_writeReg = QPushButton()
        btn_writeReg.setText('write reg')
        btn_writeReg.clicked.connect(self.writeReg)
        layout.addWidget(btn_writeReg, 1, 4)

        self.s_boxASICcol = QSpinBox()
        self.s_boxASICcol.setRange(0, 4)
        self.s_boxASICcol.setValue(0)
        layout.addWidget(self.s_boxASICcol, 2, 0)

        self.s_boxASICrow = QSpinBox()
        self.s_boxASICrow.setRange(0, 4)
        self.s_boxASICrow.setValue(0)
        layout.addWidget(self.s_boxASICrow, 2, 1)

        self.cBox = QCheckBox("Broadcast")
        layout.addWidget(self.cBox, 2, 2)

        sBox = QComboBox()
        sBox.addItems([asic.name for asic in AsicREG])
        self.sBox = sBox
        self.sBox.setCurrentIndex(2)
        layout.addWidget(sBox, 2, 3)

        # val to write
        self.s_boxWrite = QSpinBox()
        self.s_boxWrite.move(240,120)
        self.s_boxWrite.setValue(18)
        self.s_boxWrite.setRange(0, 100)
        layout.addWidget(self.s_boxWrite, 2, 4)

        # event memory probes
        self.cBoxProbe = QCheckBox("Probe")
        layout.addWidget(self.cBoxProbe, 3, 2)
        self.cBoxProbe.clicked.connect(self.probe_evtMem)
        self._probeTimer = QTimer()
        self._probeTimer.setInterval(250)
        self._probeTimer.timeout.connect(self.probe_evt)
        self.nProbes = 0
        self.nErrors = 0

        btn_readEvtMem = QPushButton()
        btn_readEvtMem.setText('read evt mem')
        btn_readEvtMem.clicked.connect(self.readEvtMem)
        layout.addWidget(btn_readEvtMem, 3, 4)

        self.s_boxEvtMem = QSpinBox()
        self.s_boxEvtMem.setValue(0)
        self.s_boxEvtMem.setRange(0, 100)
        layout.addWidget(self.s_boxEvtMem, 3, 3)

        self._qdbPage.setLayout(layout)
        return self._qdbPage

    def probe_evt(self):
        """
        write random mask to the channel mask of the adjacent node.
        read this number back.
        keep track of any errors
        """
        self.nProbes += 1
        addr = 0x30204
        randMask = np.random.randint(0xffff)
        xdest = self.s_boxASICcol.value()
        ydest = self.s_boxASICrow.value()
        addr = addr + (xdest << 6) + (ydest << 3)
        self.qpi.regWrite(addr, randMask)
        time.sleep(0.025)
        self.qpi.regRead(addr)
        time.sleep(0.025)
        word0 = self.qpi.regRead(REG.MEM(0, 0))
        word1 = self.qpi.regRead(REG.MEM(0, 1))

        data = word0 & 0xffff
        wordType = (word1>>24) & 0xf
        if wordType != 4:
            print(f"word type error: {wordType} != 4")
            self.nErrors += 1
        elif data != randMask:
            print(f"mask error: {data} != {randMask}")
            self.nErrors += 1

    def probe_evtMem(self):
        if self.cBoxProbe.isChecked():
            print("running probe")
            self._probeTimer.start()
        else:
            print("probe complete")
            print(f"probe encountered {self.nErrors} errors out of {self.nProbes} probes.")
            self._probeTimer.stop()
            self.nErrors = 0
            self.nProbes = 0

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
        # maximum of 16 bits
        saqMaskBox.setRange(0, 0xffff)
        saqMaskBox.setValue(0xffff)
        hMaskLayout.addWidget(saqMaskBox)
        self._saqMaskBox = saqMaskBox

        btn_sMask = QPushButton()
        btn_sMask.setText('Update SAQ Mask')
        btn_sMask.clicked.connect(self.setSAQMask)
        # btn_sMask.setEnabled(False)
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

        hDivLayout = QHBoxLayout()
        maskDiv = QLabel()
        maskDiv.setText("Clk Div")
        hDivLayout.addWidget(maskDiv)

        saqDiv = QSpinBox()
        saqDiv.setRange(1, 0xffff)
        saqDiv.setValue(1)
        saqDiv.valueChanged.connect(self.setSAQDiv)
        hDivLayout.addWidget(saqDiv)
        self._saqDivReg = -1
        self._saqDivBox = saqDiv


        self._saqDivLCD = QLCDNumber()
        self._saqDivLCD.display(1)
        hDivLayout.addWidget(self._saqDivLCD)
        layout.addLayout(hDivLayout)

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

        initialization should cause an ResetRoute on all asics,
        assign the correct manual routing for all ASICs in the tile
        and properly configure the xpos on all ASICs as well.
        """
        # currently only one ASIC connected to the zybo which should be
        # pointed downwards
        self.cBox.setChecked(True)
        self.resetAsicState()
        self.setAsicDirMask(0,0, AsicMask.DirRight)

    def readReg(self):
        """
        read a specific asic reg
        """
        dest_flag = 1 << 9 if not self.cBox.isChecked() else 0
        addr = self.sBox.currentIndex() + 1
        offset = 3 << 16
        addr += offset
        addr += dest_flag
        if dest_flag != 0:
            xdest = self.s_boxASICcol.value()
            ydest = self.s_boxASICrow.value()
            addr = addr + (xdest << 6) + (ydest << 3)
            print(f"reading ASIC ({xdest},{ydest}) reg: 0x{addr:06x}")
        else:
            print(f"reading reg: 0x{addr:06x}")
        readVal = self.qpi.regRead(addr)

    def writeReg(self):
        """
        write a specific asic reg
        """
        dest_flag = 1 << 9 if not self.cBox.isChecked() else 0
        addr = self.sBox.currentIndex() + 1
        offset = 3 << 16
        addr += offset
        addr += dest_flag
        if dest_flag != 0:
            xdest = self.s_boxASICcol.value()
            ydest = self.s_boxASICrow.value()
            addr = addr + (xdest << 6) + (ydest << 3)
            print(f"writing ASIC ({xdest},{ydest}) reg: 0x{addr:06x}")
        else:
            print(f"writing reg: 0x{addr:08x}")
        val = self.s_boxWrite.value()
        self.qpi.regWrite(addr, val)

    def trigger(self):
        """
        Send a basic trigger packet to the board.

        This interrogation will be sent to all ASICs in the array, and memory
        will be recorded into the BRAM within QpixDaqCtrl.vhd.
        """
        val = AsicCMD.HardInterrogation
        addr = 0x30001
        wrote = self.qpi.regWrite(addr, val)
        time.sleep(0.025)
        self.readEvents()

    def readEvtMem(self) -> int:
        """
        probe read event for debugging read a specific memory location pointed
        to by the spin box.
        print all 3 32 bit words in hex to console
        """
        evt = self.s_boxEvtMem.value()
        word0 = self.qpi.regRead(REG.MEM(evt, 0))
        word1 = self.qpi.regRead(REG.MEM(evt, 1))
        word2 = self.qpi.regRead(REG.MEM(evt, 2))

        # word one parts

        # word two parts
        wordType = (word1>>24) & 0xf
        if wordType == 4: # regresp
            data = word0 & 0xffff
            addr = (word0 >> 16) & 0xffff
            ydest    = word1 & 0xf
            xdest    = (word1>>4) & 0xf
            yhops    = (word1>>8) & 0xf
            xhops    = (word1>>12) & 0xf
            srcDaq   = (word1>>16) & 0x1
            reqID    = (word1>>17) & 0xf
            dest     = (word1>>21) & 0x1
            opRead   = (word1>>22) & 0x1
            opWrite  = (word1>>23) & 0x1
            print(f"REG_RESP: 0x{word0:08x}: data=0x{data:04x}, addr=0x{addr:04x}")
            print(f"ydest: {ydest}", end=" ")
            print(f"xdest: {xdest}", end=" ")
            print(f"yhops: {yhops}", end=" ")
            print(f"xhops: {xhops}", end=" ")
            print(f"srcDaq: {srcDaq}", end=" ")
            print(f"reqID: {reqID}", end=" ")
            print(f"dest: {dest}", end=" ")
            print(f"opRead: {opRead}", end=" ")
            print(f"opWrite: {opWrite}", end=" ")
            print(f"wordType: {wordType}")

        else: # datawords
            timestamp = word0 & 0xffff_ffff
            ypos = (word1) & 0xf
            xpos = (word1>>4) & 0xf
            chanMask = (word1>>8) & 0xffff
            intrNum = chanMask & 0x01ff
            locFull = bool(chanMask & 0x4000)
            extFull = bool(chanMask & 0x2000)
            reqID = (chanMask >> 9) & 0xf
            daq_timestamp = word2 & 0xffff_ffff
            if wordType == 5:
                print(f"EVT_END @ 0x{timestamp:08x}: ({xpos},{ypos})", end="" )
                print(f" - 0x{daq_timestamp:08x}, locFull={locFull}, extFull={extFull}", end=" ")
                print(f", reqID={reqID}")
            elif wordType != 0:
                print(f"word type={wordType} recv: {timestamp}, ({xpos},{ypos})")
            else:
                print(f"null word:: 0x{word0:08x} | 0x{word1:08x}")

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
        if evts is not None or evts > 0:
            print("found evts:", evts)
        else:
            print("no events recorded.")
            return

        # If we have events, we should record when a trigger went out to store them
        trigTime = self.getTrigTime()
        if trigTime == self._lastTrig:
            print("WARNING already recorded this event")
            return
        if trigTime is None:
            print("WARNING: received Nonetype in a trigger read")
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
        # self._progBar.setRange(0, evts)

        # read back all of the events now, and each event has 32*3 bits..
        for evt in range(evts):
            # read each word in the event
            asicTime = self.qpi.regRead(REG.MEM(evt, 0))
            d = self.qpi.regRead(REG.MEM(evt, 1))
            y, x, chanMask, wordType = getMeta(d)
            daqTime = self.qpi.regRead(REG.MEM(evt, 2))
            # self._progBar.setValue(evt+1)

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
        print("trgTime: ", trgTime)
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
        print(f"Daq Frq: {fdaq/1e6:0.4f} MHz, cnts: {daq_trig_end:08x} - {daq_trig_start:08x}")

        asic_cnt = asic_time_e - asic_time_s
        fasic = fdaq * (asic_cnt / daq_cnt)
        print(f"ASIC Frq: {fasic/1e6:0.4f} MHz, cnts: {asic_time_e:08x} - {asic_time_s:08x}")

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

    def get_fifo_cnt(self, ix=0, iy=0):
        addr = REG.FIFO(ix, iy)
        self.qpi.regRead(addr)
        print("reading fifo evt")
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
    def resetAsicState(self, xpos=0, ypos=0):
        """
        Reset asic at position (xpos, ypos)
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.CMD, broadcast=not self.cBox.isChecked())
        val = AsicCMD.ResetState
        self.qpi.regWrite(addr, val)


    def setAsicDirMask(self, xpos=0, ypos=0, mask=AsicMask.DirDown):
        """
        Change ASIC mask at position (xpos, ypos)
        """
        if not isinstance(mask, AsicMask):
            raise QDBBadAddr("Incorrect AsicMask!")

        addr = REG.ASIC(xpos, ypos, AsicREG.DIRMASK, broadcast=not self.cBox.isChecked())
        val = mask.value
        print(f"writing reg: 0x{addr:06x} with val: 0x{val:02x}")
        self.qpi.regWrite(addr, val)

    def getAsicTime(self, xpos=0, ypos=0):
        """
        wrapper function for reading clkCnt register within QDBAsic, as defined
        in QPixRegFile.vhd
        """
        addr = REG.ASIC(xpos, ypos, AsicREG.TIMESTAMP, broadcast=not self.cBox.isChecked())
        read = self.qpi.regRead(addr)
        x, y, wordType, timestamp = self._readAsicTime()

        if x != xpos or y != ypos:
            print(f"CAL WARNING: Read ({x}, {y}) instead of ({xpos},{ypos}) type: {wordType}")

        return timestamp

    def _readAsicTime(self):
        """
        helper function to parse data from the asic word as stored in RegFile.vhd.
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
        assert mask < 1<<16, "total number of bits is 16"
        self._saqMask = mask
        self._saqMaskBox.setValue(self._saqMask)

        addr = REG.SAQ(SAQReg.MASK)
        self.qpi.regWrite(addr, mask)

        # verify mask
        readMask = self.qpi.regRead(addr)
        if readMask != mask:
            print(f"warning did not write correct mask: {readMask:04x} != 0x{mask:04x}")
        else:
            print(f"mask correctly value set to: {mask:04x}")

    def setSAQDiv(self):
        """
        Sets the divisor to the local clock. This value lengthens the amount of
        time for a timestamp to increase. This register works as an integer
        divisor of the remote clock.
        """
        nDiv = self._saqDivBox.value()
        addr = REG.SAQ(SAQReg.SAQ_DIV)
        self.qpi.regWrite(addr, nDiv)
        setDiv = self.getSAQDiv()
        if setDiv != nDiv:
            print("warning! did not set correct values", setDiv," != ", nDiv)
            self._saqDivReg = -1
        else:
            self._saqDivReg = setDiv
            self._saqDivLCD.display(int(ZYBO_FRQ/setDiv))

    def getSAQDiv(self):
        """
        Read the value from the SAQDiv register. See setSAQDiv for description
        of use of register.
        """
        addr = REG.SAQ(SAQReg.SAQ_DIV)
        val = self.qpi.regRead(addr)
        print("read reg value:", val)
        return val

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
        Toggle function to turn ON or OFF data collection.

        saqEnable value is read from a QCheckBox of the main GUI.
        This function should enable the saqMask and update the packetLength
        registers when the box is CHECKED or ON.

        This function similarly should turn OFF or set a value of 0 to the SAQMask.

        Any non-zero SaqMask value will record triggers regardless of the value
        of saqEnable which can cause continuous UDP data streams in firmware
        version 0xe.
        """
        addr = REG.SAQ(SAQReg.SAQ_ENABLE)
        if self.saq_enable.isChecked():
            # reset all data at the beginning of a run
            self.SaqRst()

            val = 1

            # update the packet length at the beginning of a run
            self.setSAQLength()

            # restart the thread if we haven't started it yet
            if not self.qpi.thread.isRunning():
                print("restarting udp collection thread")
                self.qpi.thread.start()
        else:
            val = 0
            self._stop_hits = self.getSAQHits()
        self.qpi.regWrite(addr, val)

        # enable the SAQ, update the mask, and put that value in the spin box
        addr = REG.SAQ(SAQReg.MASK)
        sndMask = self._saqMask if val == 1 else 0
        self.qpi.regWrite(addr, sndMask)
        self._saqMaskBox.setValue(sndMask)
        if val == 1:
            print("Saq Enabled")

    def SaqRst(self):
        """
        Saq Reset is called to reset the FIFO and AXI-Stream FIFOs
        which store reset data on the Zynq FPGA.
        This reset will DELETE all currently stored reset data on the Zybo board.
        """
        print("reseting SAQ data")
        addr = REG.SAQ(SAQReg.SAQ_RST)
        # writing value doesn't matter for this register
        self.qpi.regWrite(addr, 0)

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


    def launchSaqDialog(self):
        """
        Function should manage creation of QDialog box which, if accepted,
        returns a new mask value to send to SAQ trigger register bits.
        """
        self._mask = 0x0


    def SaveData(self, output_file=None):
        """
        NOTE: This function is called by default when the GUI closes

        This function handles storing a recorded run at a destination output file.

        This should be the only controlling / call function that uses
        make_root.py to store output data and the metadata tree for SAQ on the
        Zybo.
        """
        if output_file is None:
            output_file = datetime.datetime.now().strftime('./%m_%d_%Y_%H_%M_%S.root')
            print("saving default file", output_file)

        input_file = self.qpi.worker.output_file
        if self.qpi.thread.isRunning():
            self.close_udp.emit()

        found = os.path.isfile(input_file)
        if not found:
            return
        else:
            args = [input_file, output_file, self.version, self._start_hits, self._stop_hits, self._saqDivReg]
            args = [str(arg) for arg in args]
            subprocess.Popen(["python", "make_root.py", *args])

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
        exitAct = QAction(QIcon(), '&Exit', self)
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(self.close)

        # create a way to save the data collected
        saveAct = QAction(QIcon(), '&Save', self)
        saveAct.setShortcut('Ctrl+S')
        saveAct.setStatusTip('Save Data')
        saveAct.triggered.connect(self.SaveAs)

        # add the actions to the menuBar
        fileMenu = menubar.addMenu('File')
        fileMenu.addAction(exitAct)
        fileMenu.addAction(saveAct)

    def closeEvent(self, event):
        print("closing the main gui")
        self.SaveData()

    def SaveAs(self):
        """
        This function is called when the user selects the save option
        from the file under the menu bar.

        a dialog window should appear and the user can select the name
        and location of the output root file to be created.
        """
        fileName = QFileDialog.getSaveFileName(self, "Save Data File",
                                       os.getcwd(),
                                       ".root")

        # don't double up the root extension
        if fileName[0][-5:] == ".root":
            out_file = fileName[0]
        else:
            out_file = fileName[0]+".root"
        self.SaveData(out_file)

    def openDialog(self):
        """
        Function opens dialogWindow class to prompt user for a new timestamp
        trigger mask.
        """
        self.dialog = dialogWindow(self._saqMask)
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
