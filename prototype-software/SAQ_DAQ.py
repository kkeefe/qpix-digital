# interfacing dependcies
from qdb_interface import (AsicREG, AsicCMD, AsicMask, ZYBO_FRQ,
                           qdb_interface, QDBBadAddr, REG, SAQReg, DEFAULT_PACKET_SIZE)
import os
import sys
import time
import struct

# PyQt GUI things
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QPushButton, QCheckBox, QSpinBox, QLabel,
                             QDoubleSpinBox, QProgressBar, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStatusBar,
                             QDialog, QDialogButtonBox, QLCDNumber, QFileDialog,
                             QSpacerItem, QSizePolicy)
from PyQt5.QtCore import QProcess, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction

import pyqtgraph as pg

# for output data
from array import array
import ROOT
import numpy as np
import datetime
# for spawning other process to turn binary data into ROOT
import subprocess 

N_SAQ_CHANNELS = 16

class QPIX_GUI(QMainWindow):

    close_udp = pyqtSignal()
    
    def __init__(self):
        super(QMainWindow, self).__init__()

        # IO interfaces
        self.qpi = qdb_interface()
        self.close_udp.connect(self.qpi.finish) # closes udp worker thread
        self.qpi.worker.new_data.connect(self.on_new_data)
        self._saqMask = 0xffff

        # SAQ meta data information
        self._start_hits = 0
        self._stop_hits = 0
        self.version = self.qpi.version

        # Data for on-line plots
        self._plotUpdateCadence = 1000 # milliseconds
        self._init_online_data()
            
        # window setup
        self.setWindowTitle('SAQ DAQ')

        self.cbChannels = []
        self.lcdChannels = []
        
        # passive triggering
        self._graphTimer = QTimer()
        self._graphTimer.timeout.connect(self._update_online_graphs)

        # initialize the sub menus
        self._make_menuBar()
        self._make_statusBar()

        # create the layouts that are needed for making the GUI pretty
        self.tabW = QTabWidget()
        self.tabW.addTab(self._makeGeneralLayout(),  "General")
        self.tabW.addTab(self._makeAdvancedLayout(), "Advanced")
        self.tabW.addTab(self._makeChannelsLayout(), "Channels")
        self.setCentralWidget(self.tabW)

        # show the main window
        self.show()
        self.saq_clear()


    def saq_clear(self):
        """
        should be used at the beginning and closing of the program to put the Zybo
        and FIFOs into disabled and empty states.
        """
        self.setSAQDiv()
        self.updateChannelMaskOnZybo()
        self.enableSAQ(False)
        self.SaqRst()

    def _init_online_data(self):
        self._online_data = {}
        self._online_data['averageResetRates'] = {}
        self._online_data['totalResets'] = N_SAQ_CHANNELS * [0]
        self._clear_online_data()
        
    def _clear_online_data(self):
        self._online_data['averageResetRates_time'] = [self._plotUpdateCadence*0.001]
        for ii in range(N_SAQ_CHANNELS):
            chan = ii+1
            self._online_data['averageResetRates'][chan] = [0]
        self._online_data['totalResets'] = N_SAQ_CHANNELS * [0]

    def parse_data(self, data):
        nwords = int(len(data)/8)

        ii = 0
        for __ in range(nwords):
            # timestamp
            tt = struct.unpack("<I", data[ii:ii+4])[0]
            ii += 4
            # channel hit list (1-16)
            cc = struct.unpack("<H", data[ii:ii+2])[0]
            ii += 2
            # metadata
            mm = struct.unpack("<H", data[ii:ii+2])[0]
            ii += 2
            if self.dbg_packet.isChecked():
                print(f"    {tt}, {cc}, {mm}")
            
            # update online data stats
            chans = self.chans_with_resets(cc)
            for chan in chans:
                self._online_data['averageResetRates'][chan][-1] += 1./(self._plotUpdateCadence*0.001)
                self._online_data['totalResets'][chan-1] += 1

        pid = struct.unpack("<H", data[-2:])[0]
        if self.dbg_packet.isChecked():
            print(f"    {pid}")

    def chans_with_resets(self, mask):
        """
        List comprehension to convert 16 bit mask word into a list with all active channels.
        input: 16b unsigned value
        output: list of channels, starting from 1
        """
        chans = [x+1 for x in range(N_SAQ_CHANNELS) if 2**x & mask]
        return chans
        
    def on_new_data(self, data):
        self.parse_data(data)

    def _makeChannelsLayout(self):
        self._channelsPage = QWidget()
        layout = QVBoxLayout()
        label = QLabel()
        label.setText("Channels page")
        layout.addWidget(label)

        hDivLayout = QHBoxLayout()
        saqLengthL = QLabel()
        saqLengthL.setText("Update Packet Length")
        hDivLayout.addWidget(saqLengthL)

        saqLength = QSpinBox()
        saqLength.setRange(0, 0x0000_3fff)
        saqLength.setValue(DEFAULT_PACKET_SIZE)
        hDivLayout.addWidget(saqLength)
        self._saqLength = saqLength

        maskDiv = QLabel()
        maskDiv.setText("Clk Div")
        hDivLayout.addWidget(maskDiv)

        saqDiv = QSpinBox()
        saqDiv.setRange(1, 0xffff)
        saqDiv.setValue(1)
        saqDiv.valueChanged.connect(self.setSAQDiv)
        hDivLayout.addWidget(saqDiv)
        self._saqDivBox = saqDiv

        self._saqDivLCD = QLCDNumber()
        self._saqDivLCD.display(1)
        hDivLayout.addWidget(self._saqDivLCD)
        layout.addLayout(hDivLayout)
        
        ##Add graphs
        #graph = pg.GraphicsLayoutWidget(show = True, title = "Channels 1 - 16")
        #graph.setBackground('w')
        #for i in range(16):
        #    ch = graph.addPlot(title = "Channel " + str(i+1))
        #    if (i+1)%4 == 0:
        #        graph.nextRow()
        #layout.addWidget(graph)

        self._channelsPage.setLayout(layout)
        return self._channelsPage
        
    def _makeAdvancedLayout(self):
        self._advancedPage = QWidget()
        layout = QHBoxLayout()
        label = QLabel()
        label.setText("Advanced page")
        layout.addWidget(label)
        self._advancedPage.setLayout(layout)
        return self._advancedPage
    
    def _makeGeneralLayout(self):
        """
        Wrapper function to make the layout for the main tab for the SAQ DAQ
        into the QMainWindow's QStackedLayout
        """
        self._generalPage = QWidget()
        
        layout = QHBoxLayout()

        ctrlLayout = QVBoxLayout()
        plotLayout = QHBoxLayout()
        
        layout.addLayout(ctrlLayout)
        layout.addLayout(plotLayout)
        
        topLayout = QHBoxLayout()
        bottomLayout = QHBoxLayout()
        ctrlLayout.addLayout(topLayout)
        ctrlLayout.addLayout(bottomLayout)
        
        cbLayout = QGridLayout() # channel checkboxes
        btnLayout = QVBoxLayout() # start/stop buttons
        chLayout   = QGridLayout()
        topLayout.addLayout(cbLayout)
        topLayout.addLayout(btnLayout)
        bottomLayout.addLayout(chLayout)
        
        self._generalPage.setLayout(layout)

        # checkboxes
        nrows = 8
        ncols = 2
        for col in range(ncols):
            for row in range(nrows):
                chan = (col*nrows)+row+1
                cb = QCheckBox(f"Ch. {chan}")
                cb.setChecked(True)
                cb.stateChanged.connect(self.updateChannelMaskOnZybo)

                self.cbChannels.append(cb)
                cbLayout.addWidget(cb, row, col, QtCore.Qt.AlignTop)

#        vspacer = QSpacerItem(40, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
#        cbLayout.addItem(vspacer, 8, 0, QtCore.Qt.AlignTop)
        
        # start/stop buttons
        btnStart = QPushButton("Start")
        btnStart.clicked.connect(self.startRun)
        btnLayout.addWidget(btnStart)
        
        btnStop = QPushButton("Stop")
        btnStop.clicked.connect(self.stopRun)
        btnLayout.addWidget(btnStop)

        # btnClear = QPushButton("Clear Data")
        # btnClear.clicked.connect(self.clearData)
        # btnLayout.addWidget(btnClear)

        # btnSave = QPushButton("Save Data")
        # btnSave.clicked.connect(self.saveData)
        # btnLayout.addWidget(btnSave)

        btnLayout.addStretch() # vfill at the bottom

        #channel reset displays
        ncols = 4
        nrows = 8
        for col in range(ncols):
            for row in range(nrows):
                if (col+1)%2 == 0:
                    cb = QLCDNumber()
                    self.lcdChannels.append(cb)
                    chLayout.addWidget(cb, row, col, QtCore.Qt.AlignBottom)
                else:
                    chan = (int((col/2)*nrows))+row + 1
                    label = QLabel("Ch." + f"{chan}")
                    chLayout.addWidget(label, row, col, QtCore.Qt.AlignBottom)

        
        self.graph = pg.PlotWidget()
        self.graph.addLegend()
        #color = self.palette().color(QPalette.Window)
        #graph.setBackground(color)
        self.graph.setBackground('w')
        self.graph.setTitle("Average reset rate per channel")
        self.graph.setLabel("left", "y-axis label")
        self.graph.setLabel("bottom", "x-axis label")
        width = 3
        self.plotLines = []
        for ichan in range(N_SAQ_CHANNELS):
            color = (0,0,ichan*256/N_SAQ_CHANNELS)
            #self.plotLines.append(self.graph.plot([], pen=pg.mkPen(color=color, width=width), name=f'Ch. {ichan+1}'))
            self.plotLines.append(self.graph.plot([], pen=None, name=f'Ch. {ichan+1}',
                                                  symbol='o', symbolPen=pg.mkPen(color=color),
                                                  symbolBrush=pg.mkBrush(color=color)
                                                  ))
                                             
        plotLayout.addWidget(self.graph)

        return self._generalPage

    def startRun(self):
        self.enableSAQ(True)

    def stopRun(self):
        self.enableSAQ(False)

    def clearData(self):
        pass
        
    def saveData(self):
        pass
        
    def enableSAQ(self, enable):
        """
        Toggle function to turn ON or OFF data collection.

        saqEnable takes enable as boolean.
        This function should enable the saqMask and update the packetLength.

        This function similarly should turn OFF or set a value of 0 to the SAQMask.

        Any non-zero SaqMask value will record triggers regardless of the value
        of saqEnable which can cause continuous UDP data streams in firmware
        version 0xe.
        """

        # enable the SAQ and update the mask
        addr = REG.SAQ(SAQReg.MASK)
        sndMask = self._saqMask if enable else 0
        self.qpi.regWrite(addr, sndMask)

        addr = REG.SAQ(SAQReg.SAQ_ENABLE)

        if enable:
            # reset all data at the beginning of a run
            self.SaqRst()

            # update the packet length at the beginning of a run
            self.setSAQLength()

            # restart the thread if we haven't started it yet
            if not self.qpi.thread.isRunning():
                print("starting udp collection thread")
                self.qpi.start()

            # enable the Zybo
            self.qpi.regWrite(addr, 1)

            # start the graph update timer
            self._graphTimer.start(self._plotUpdateCadence) # milliseconds
        else:
            self._stop_hits = self.getSAQHits()
            self._graphTimer.stop()

            # disable the Zybo
            self.qpi.regWrite(addr, 0)
            self.SaqRst()

            if self.qpi.thread.isRunning():
                print("stopping udp collection thread")
                self.close_udp.emit()

        #self._graphTimer.timeout.connect(self._update_online_graphs)
        # reset the statistics (?)
        self._graph_reset()

    def setSAQDiv(self):
        """
        Sets the divisor to the local clock. This value lengthens the amount of
        time for a timestamp to increase. This register works as an integer
        divisor of the remote clock.
        """
        nDiv = self._saqDivBox.value()
        addr = REG.SAQ(SAQReg.SAQ_DIV)
        self.qpi.regWrite(addr, nDiv)
        self._saqDivReg = nDiv
        self._saqDivLCD.display(int(ZYBO_FRQ/nDiv))
        div = self.getSAQDiv()
        if div != nDiv:
            print("WARNING! mismatch between SAQ-DIV!")
            self._saqDivReg = -1

    def getSAQDiv(self):
        """
        Read the value from the SAQDiv register. See setSAQDiv for description
        of use of register.
        0x2f version has bug!
        """
        addr = REG.SAQ(SAQReg.SAQ_DIV)
        val = self.qpi.regRead(addr)
        return val

    def SaqRst(self):
        """
        Saq Reset is called to reset the FIFO and AXI-Stream FIFOs
        which store reset data on the Zynq FPGA.
        This reset will DELETE all currently stored reset data on the Zybo board.
        """
        addr = REG.SAQ(SAQReg.SAQ_RST)
        # writing value doesn't matter for this register
        self.qpi.regWrite(addr, 0)

    def setSAQLength(self):
        """
        Read from the QSpinBox and set the new length register here. This will update
        the amount of incoming works on each incoming UDP packet.
        """
        nPackets = self._saqLength.value()
        addr = REG.SAQ(SAQReg.SAQ_FIFO_LNGTH)
        self.qpi.regWrite(addr, nPackets)

    def _update_online_graphs(self):
        # update plot data
        print("...", end=" ")
        for ii in range(N_SAQ_CHANNELS):
            chan = ii+1
            self.plotLines[ii].setData(self._online_data['averageResetRates_time'],
                                       self._online_data['averageResetRates'][chan],
                                       )
        # autoscale
        self.graph.autoRange()

        #Update LCD display
        for ii in range(N_SAQ_CHANNELS):
            chan = ii + 1
            if self.lcd_toggle.isChecked():
                self.lcdChannels[ii].display(self._online_data['totalResets'][chan-1])
            else:
                self.lcdChannels[ii].display(self._online_data['averageResetRates'][chan][-1])

        # prep for next plot point
        self._online_data['averageResetRates_time'].append(self._online_data['averageResetRates_time'][-1] +
                                                           self._plotUpdateCadence*0.001)
        for ii in range(N_SAQ_CHANNELS):
            chan = ii+1
            self._online_data['averageResetRates'][chan].append(0)
        
    def _graph_reset(self):
        self._clear_online_data()
        self._update_online_graphs()
        
    def getChannelMaskFromGUI(self):
        self._saqMask = 0
        for ii, cb in enumerate(self.cbChannels):
            if cb.isChecked():
                self._saqMask += 1 << ii

    def updateChannelMaskOnZybo(self):
        # read the mask value from GUI checkboxes
        self.getChannelMaskFromGUI()
        # send that value to the FPGA
        addr = REG.SAQ(SAQReg.MASK)
        wrote = self.qpi.regWrite(addr, self._saqMask)
        
    def getSAQHits(self):
        """
        read the SAQ Hit register buffer
        """
        addr = REG.SAQ(SAQReg.SAQ_FIFO_HITS)
        hits = self.qpi.regRead(addr)
        return hits

    def SaveData(self, output_file=None):
        """
        NOTE: This function is called by default when the GUI closes

        This function handles storing a recorded run at a destination output file.

        This should be the only controlling / call function that uses
        make_root.py to store output data and the metadata tree for SAQ on the
        Zybo.
        """
        input_file = self.qpi.worker.output_file
        if input_file is None:
            print("no output file.. no run started.. closing.")
            return
        print("input file is: ", input_file)
        if self.qpi.thread.isRunning():
            self.close_udp.emit()

        # get the base name of the file from ./bin/basename.bin
        # and make it a root file
        if output_file is None:
            output_file = input_file.split("/")[-1].split(".")[0] + ".root"

        found = os.path.isfile(input_file)
        if not found:
            return
        else:
            args = [input_file, output_file, self.version, self._start_hits, self._stop_hits, self._saqDivReg]
            args = [str(arg) for arg in args]
            print(f"Creating output data file: {output_file}")
            subprocess.Popen(["python", "make_root.py", *args])

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

    def _make_statusBar(self):
        """
        Configurable options for the front tab of the window.
        Mostly used to update QLCDs, if they show total resets or recent average
        """

        # manage whether or not the UDP / TCP connections are valid
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.lcd_toggle = QCheckBox("Display Reset Totals")
        self.lcd_toggle.clicked.connect(self.toggleLCD)
        self.statusBar.addWidget(self.lcd_toggle)

        self.lcd_label = QLabel("Displaying Average..")
        self.statusBar.addWidget(self.lcd_label)

        self.dbg_packet = QCheckBox("Packet Debug")
        self.statusBar.addWidget(self.dbg_packet)

    def toggleLCD(self):
        """
        Toggle which values should be displayed in the QLCD Values
        """
        if self.lcd_toggle.isChecked():
            self.lcd_label.setText("Displaying Total Resets")
        else:
            self.lcd_label.setText("Displaying Average Resets")


    def closeEvent(self, event):
        print("closing up the SAQ's DAQ..", end=" ")
        self.saq_clear()
        print("cleared.")

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

if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = QPIX_GUI()
    app.exec_()
