#!/usr/bin/env python

import os
import socket
import struct
import sys
import glob
from enum import Enum
import time
import datetime

# Qt5 dependencies
import PyQt5
from PyQt5.QtCore import QObject, QByteArray, pyqtSignal, QThread, QEventLoop
from PyQt5.QtNetwork import QTcpSocket, QHostAddress, QUdpSocket

# global defualts to configure connection to socket
QP_IP      = '192.169.1.27'
QP_PORT    = 42069
BUFFER_SIZE = 1024

# global of Zybo Frq which is used to calculate time value from timestamps
ZYBO_FRQ = 30303030

# UDP Info
QP_UDP_IP   = '192.169.1.17'
QP_UDP_PORT = 1337
EXIT_PACKET = bytes("ZaiJian", encoding="utf-8")
PACKET_HEADER = bytes("HEADER", encoding="utf-8")
DEFAULT_PACKET_SIZE = 1
SAQ_TMP_FILE = "./bin/saqTmp.bin"

# DMA_REG NOTES
# CTRL NOTE: only lowest bit enables and begins DMA, bit 2 is always high, bit 16 is
# interupt threshold which has a minimum of 1, and 1000 part is interrupt on complete enable

# DMA_CONTROL constant globals that should ensure DMA registers
# each register stores 32b, but not all bits are used at certain registers..
DMA_CTRL = 0x0001_1003
DMA_STATUS = 0x0000_0000
DMA_LENGTH = 0x0000_3fff
DMA_DEST_MSB = 0x0000_0000


class DMA_STATUS_BIT(Enum):
    """
    bits to be AND with of the status register, if the status register, which
    should be all blank, returns a certain value.
    """
    HALT = (1 << 0)
    IDLE = (1 << 1)
    SGEN = (1 << 3)
    INT_ERR = (1 << 4)
    SLAV_ERR = (1 << 5)
    DEC_ERR = (1 << 6)
    SG_INT_ERR = (1 << 8)
    SG_SLAV_ERR = (1 << 9)
    SG_DEC_ERR = (1 << 10)
    IOC_IRQ = (1 << 12)
    DLY_IRQ = (1 << 13)
    ERR_IRQ = (1 << 14)
    IRQ_THRESH = (0x1 << 16)
    IRQ_DELAY_STATUS = (0xff << 24)


class QDBBadAddr(Exception):
    pass


class AsicREG(Enum):
    """
    Represents Addresses.

    Simple Enum to highlight remote addresses of QpixAsic.

    These address spaces are defined in QpixRegFile.vhd, within case selection.
    """
    CMD = 1
    TIMESTAMP = 2
    DIRMASK = 3
    CHMASK = 4
    COORDINATE = 5
    TXRX_DISABLE = 6
    LOC_DISABLE = 7
    INT_NUMBER = 8
    SCRATCH = 9


class SAQReg(Enum):
    """
    Enum style class to keep a hold of used registers in protoregmap for SAQ
    reading.
    """
    SCRATCH = 0x5f
    MASK = 0x50
    READ1 = 0x51
    READ2 = 0x52
    READ_ENABLE = 0x53
    SAQ_ENABLE = 0x54
    SAQ_FIFO_LNGTH = 0x55
    SAQ_FIFO_HITS = 0x56
    SAQ_FORCE = 0x57
    SAQ_RST = 0x58
    SAQ_DIV = 0x59


def MemAddr(evt, pos):
    """
    Return address space for the event at a specific memory location.
    ARGS:
       evt - number of event
       pos - which 32 bit word within the event
    NOTE:
       Values are stored in BRAM located within DaqCtrl.vhd. only 32*3 bits are
       used (highest 32 are trimmed.)

       Readout procedure is also defined within DaqCtrl, where bottom two bits
       of the MemAddr is used to mux the word.
    """
    if pos not in [0,1,2]:
        raise QDBBadAddr("Incorrect Memory Read address! not acceptible word position!")
    if evt > 4095:
        raise QDBBadAddr("Incorrect Memory Read address! Evt too high!")

    # defined in ProtoRegMap
    evtMask = 1 << 16

    # defined as offset above addr for location in bram
    event = evt << 2

    # full address here
    return evtMask + event + pos


def FIFOAddr(ix, iy):
    """
    read from the 2<<16 addr for testing
    """
    ix = (ix & 0b1111) << 2
    iy = (iy & 0b1111) << 6
    fifo_addr = 2 << 16

    val = ix + iy + fifo_addr

    return val << 2

def AsicAddr(xpos=0, ypos=0, remote_addr=AsicREG.CMD, broadcast=True):
    """
    return address space for remote ASIC.

    NOTE: remote_addr is the subaddr space at the remote ASIC definedin QpixRegFile.vhd

    This protocol is implemented in QpixDaqCtrl.vhd
    """
    if not isinstance(remote_addr, AsicREG):
        raise QDBBadAddr("Incorrect Remote ASIC ADDR!")
    else:
        # QpixDaqCtrl.vhd selects these address spaces:
        xp = ((xpos & 0b111)<<6)
        yp = ((ypos & 0b111)<<3)
        dest_flag = 1 << 9 if broadcast else 0

        # this address flag is defined within QpixProtoRegMap.vhd
        asic_addr_flag = 3 << 16

        # combine and return net addr space
        addr = asic_addr_flag + dest_flag + xp + yp + remote_addr.value
        return addr


def SaqAddr(addr=SAQReg.SCRATCH):
    """
    List of address spaces available to read for the SAQ addr.

    This implementation is derived from AsicAddr.
    """
    if not isinstance(addr, SAQReg):
        raise QDBBadAddr("Incorrect SAQ ADDR!")
    else:
        saq_addr_flag = 0 << 16
        addr = saq_addr_flag + addr.value

        return addr


class AsicMask(Enum):
    """
    Represents Values.

    Simple Enum class to simplify remote ASIC direction values and enable manual routing.

    The mask values (1,2,4,8) are defined in QPixPkg.vhd.

    The 0x10 bit sets the manual routing bit, as defined in QpixRegFile.vhd.

    the (1 << 4) is the dirMask enable bit
    """
    DirUp = 1 + (1 << 4)
    DirRight = 2 + (1 << 4)
    DirDown = 4 + (1 << 4)
    DirLeft = 8 + (1 << 4)


class AsicCMD(Enum):
    """
    Represents Values.

    Simple Enum class to simplify remote ASIC individual commands.

    These values should only be used at the specfic addr REG.ASIC(x, y, AsicREG.CMD).
    """
    HardInterrogation = 0x1
    SoftInterrogation = 0x2
    ResetAsic = 0x4
    ResetState = 0x8


class REG(Enum):
    """
    REG is an Enum class which returns a register address space for both the Zybo board
    and all of the remote ASICs in an array.

    There are two sets of addresses: Zybo address and remote ASIC address.

    A Zybo address is treated as a normal Enum member, i.e. REG.CMD.value

    A remote ASIC address is retrieved with REG.ASIC(xpos, ypos, AsicREG) method, i.e.
    REG.ASIC(0, 0) returns the ASIC at x=0, y=0 position.

    NOTE: There are two types of register transactions, either a read or a write; some
    addresses only support one type.

    specific register mappings are found in vhd files:
    QpixProtoPkg.vhd
    QpixRegFile.vhd
    """

    # all of these addresses are defined in QpixProtoPkg.vhd
    # and are registers local to the Zybo/Aggregator
    SCRATCH   = 0x00
    CMD       = 0x0A
    STATUS    = 0x01
    HITMASK   = 0x02
    TIMESTAMP = 0x03
    EVTSIZE   = 0x04
    TRGTIME   = 0x05
    CHANMASK  = 0x06
    ASICMASK  = 0x07
    FRAMEERR  = 0x08
    BREAKERR  = 0x09
    TESTOUT_H = 0x0b
    TESTOUT_L = 0x0c
    TESTIN_H  = 0x0d
    TESTIN_L  = 0x0e

    # event memory slots
    MEM = MemAddr

    # fifo addr
    FIFO = FIFOAddr

    # remote Asic Callable address class
    ASIC = AsicAddr

    # keep track of SAQ addrs
    SAQ = SaqAddr


class saqUDPworker(QObject):
    """
    This class is sent to a new thread, and monitors
    the output of the UDP port that sends burst data.
    It should listen to and read from the UDP socket, and then dump
    all data into an output file.
    """
    finished = pyqtSignal()
    new_data = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        # create and manage the new thread once running
        self._udpsocket = QUdpSocket(self)
        self._stopped = True
        self.output_file = None

        self._first = 0

    def _udp_connect(self):
        # try to connect to the UDP socket
        print("udp connecting..", end="")
        connected = False
        try:
            bound = self._udpsocket.bind(QHostAddress(QP_UDP_IP), QP_UDP_PORT)
            print("Thread UDP..", end=" ")
            if bound:
                print("connected!")
                connected = True
            else:
                print("ERROR!! UDP unconnected!..")

        except Exception as ex:
            print(ex)

        return connected

    def on_readyRead(self):
        while self._udpsocket.hasPendingDatagrams():
            datagram = QByteArray()
            datagram.resize(self._udpsocket.pendingDatagramSize())
            datagram, host, port = self._udpsocket.readDatagram(self._udpsocket.pendingDatagramSize())
            if datagram == EXIT_PACKET:
                self.f.close()
                self.finished.emit()
                self._udpsocket.close()
                return
            else:
                self.new_data.emit(datagram)
                size = len(datagram)
                nresets = int((size-2)/8)
                self.f.write(PACKET_HEADER+size.to_bytes(4, byteorder="little")+datagram)

    def run(self):
        if self._first == 0:
            self._udpsocket.readyRead.connect(self.on_readyRead)
            self._first += 1
        if not self._udp_connect():
            self.finished.emit()
        else:
            self.output_file = datetime.datetime.now().strftime('./bin/%m_%d_%Y_%H_%M_%S.bin')
            self.f = open(self.output_file, 'wb')


class DMA_REG(Enum):
    """
    Enum class to specific DMA registers of interest to be used during
    configuration at bootup.

    This register space uses only the s2mm interface to control how the DMA
    sends axi-stream data to the DDR memory of the Zybo.
    """
    S2MM_CTRL = 0x30
    S2MM_STATUS = 0x34
    S2MM_CURDESC = 0x38
    S2MM_CURDESC_MSB = 0x3C
    S2MM_TAILDESC = 0x40
    S2MM_TAILDESC_MSB = 0x44
    S2MM_DEST_ADDR = 0x48
    S2MM_DEST_ADDR_MSB = 0x4C
    S2MM_LENGTH = 0x58


class qdb_interface(QObject):
    """
    Generic interface class which manages the socket transactions and retrieves
    data from transactions.

    This class is responsible for handling signals and slots between the
    tcpsocket and the Zybo.

    The only public methods that should be used from this interface are reading
    and writing between registers: regRead and regWrite.

    It is up to the user to ensure that all addresses and values used in those two
    methods correspond to the above register classes.
    """
    finished = pyqtSignal()

    def __init__(self, ip=QP_IP, port=QP_PORT):
        super().__init__()
        self._QP_IP = QHostAddress(QP_IP)
        self._QP_PORT = port
        self.version = 0
        # self._BUFFER_SIZE = BUFFER_SIZE

        # storage for retrieiving tcp data
        self.data = None

        # create the tcp socket
        self._tcpsocket = QTcpSocket(self)
        self._tcpConnected = self._tcp_connect()
        if self._tcpConnected:
            # connect the write command to reading if anything comes back
            self._tcpsocket.readyRead.connect(lambda: self._readData())

            # make sure to check this works
            self._verify()

            # begin the DMA configuration cycle
            try:
                self.PrintDMA()
                self._dma_enabled = True
            except Exception as ex:
                print("unable to configure DMA engine")
                self._dma_enabled = False

        # manage the SAQ-UDP thread reader
        self.thread = QThread()
        self.worker = saqUDPworker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.udp_done)

    def regRead(self, addr=REG) -> int:
        """
        read a Zybo register or a remote ASIC register as defined in REG class.

        Returns last 32 bit word from the register readout.
        """
        # allow passing of REG enum types directly
        if not isinstance(addr, REG) and hasattr(addr, "value"):
            raise QDBBadAddr("Incorrect REG address on regRead!")
        elif hasattr(addr, "value"):
            addr = addr.value

        # form byte message
        args = ['QRR', addr]
        if isinstance(args, str): args = args.split(' ')
        hdr = args[0]+'\0'
        byte_arr = str.encode(hdr)
        for arg in args[1:]:
            if not isinstance(arg, int): arg = int(arg, 0)
            byte_arr += struct.pack('<I', arg)

        self._write(byte_arr)
        self._tcpsocket.waitForReadyRead(1000)

        # make sure there's new data to return
        if self.data is not None:
            data = self.data
            self.data = None
            return data
        else:
            print('WARNING: REG no data!')
            return None

    def regWrite(self, addr, val) -> int:
        """
        Register write command, used for either writing directly to remote ASICs
        or Zybo.
        """
        # allow passing of REG enum types directly
        if not isinstance(addr, REG) and hasattr(addr, "value"):
            raise QDBBadAddr("Incorrect REG address on regWrite!")
        elif hasattr(addr, "value"):
            addr = addr.value
        if hasattr(val, "value"):
            val = val.value

        # print(f"writing {val:02x} to addr: {addr:06x}")
        # form byte message
        args = ['QRW', addr, val]
        if isinstance(args, str): args = args.split(' ')
        hdr = args[0]+'\0'
        byte_arr = str.encode(hdr)
        for arg in args[1:]:
            if not isinstance(arg, int): arg = int(arg, 0)
            byte_arr += struct.pack('<I', arg)

        # returns number of bytes written
        cnt = self._write(byte_arr)
        self._tcpsocket.waitForReadyRead(1000)
        return cnt

    def _verify(self) -> bool:
        """
        initialization function to make sure that the interface can communicate
        with the scratch buffer.

        A correct verification performs a successful regRead and regWrite of the
        REG.SCRATCH buffer.
        """
        self.version = self.regRead(REG.SCRATCH)
        print(f"Running version: 0x{self.version:08x}.. verifying..", end=" ")

        # update and check
        checksum = 0x0a0a_a0a0
        self.regWrite(REG.SCRATCH, checksum)
        verify  = self.regRead(REG.SCRATCH)
        if checksum != verify:
            print("warning verification failed")
            print(f"0x{checksum:08x} != 0x{verify:08x}")
        else:
            print("verification passed!")
            self.regWrite(REG.SCRATCH, self.version)

        # set up SAQ register if version >= 8
        if self.version >= 0x1000_0002f:
            addr = REG.SAQ(SAQReg.SAQ_FIFO_LNGTH)
            self.regWrite(addr, DEFAULT_PACKET_SIZE) # make the length of a packet 5

        return checksum == verify

    def _readData(self) -> int:
        """
        PyQtSlot: Read data from the socket whenever something shows up.

        ARGS: opt: optional integer to fiure out which signal emitted call

        Returns the last 32 bit word from the socket, and handles tcp response
        """
        while self._tcpsocket.bytesAvailable():
            data = self._tcpsocket.read(4)
            val = struct.unpack('<I', data)[0]
            self.data = val

        return self.data

    def _write(self, data):
        wrote = self._tcpsocket.write(data)
        self._tcpsocket.waitForBytesWritten(1000)
        return wrote

    def _tcp_connect(self):
        """
        connect to the remote socket and find the zybo board.
        """
        print("tcp connecting..", end="")
        connected = False
        # try to connect to the TCP Socket
        try:
            addr = QHostAddress(self._QP_IP)
            self._tcpsocket.connectToHost(addr, self._QP_PORT)
            print("TCP..", end=" ")
            if self._tcpsocket.waitForConnected(1000):
                print("connected..")
                connected = True
            else:
                print("WARNING unconnected..")

        except Exception as ex:
            print(ex)
            print("unconnected! TCP")

        return connected

    def _WriteDMA(self, addr, val):
        """
        Write a DMA register, based on regWrite, but with special args header
        """
        # allow passing of REG enum types directly
        if not isinstance(addr, DMA_REG) and hasattr(addr, "value"):
            raise QDBBadAddr("Incorrect DMA_REG address on _WriteDMA!")
        elif hasattr(addr, "value"):
            addr = addr.value
        if hasattr(val, "value"):
            val = val.value

        # form byte message
        args = ['QDW', addr, val]
        if isinstance(args, str): args = args.split(' ')
        hdr = args[0]+'\0'
        byte_arr = str.encode(hdr)
        for arg in args[1:]:
            if not isinstance(arg, int): arg = int(arg, 0)
            byte_arr += struct.pack('<I', arg)

        # returns number of bytes written
        cnt = self._write(byte_arr)
        self._tcpsocket.waitForReadyRead(1000)
        return cnt

    def _ReadDMA(self, addr):
        """
        Read a DMA register, based on regRead, but with special args header
        """
        # allow passing of REG enum types directly
        if not isinstance(addr, DMA_REG) and hasattr(addr, "value"):
            raise QDBBadAddr("Incorrect DMA_REG address on _ReadDMA!")
        elif hasattr(addr, "value"):
            addr = addr.value

        args = ['QDR', addr]
        if isinstance(args, str): args = args.split(' ')
        hdr = args[0]+'\0'
        byte_arr = str.encode(hdr)
        for arg in args[1:]:
            if not isinstance(arg, int): arg = int(arg, 0)
            byte_arr += struct.pack('<I', arg)

        self._write(byte_arr)
        self._tcpsocket.waitForReadyRead(1000)

        # make sure there's new data to return
        if self.data is not None:
            data = self.data
            self.data = None
            return data
        else:
            print('WARNING: no DMA REG data!')
            return None

    def PrintDMA(self):
        """
        interface should automagically configure and setup DMA registers, since
        this usage uses a special register IO. this function should be used at
        start up to ensure that the DMA registers can be configured properly,
        and if not disable the DMA engine.
        """

        # initialize DMA ctrl on bootup if not running. This should be only register to ever write
        addr = DMA_REG.S2MM_CTRL
        d_ctrl = self._ReadDMA(addr)
        if d_ctrl != DMA_CTRL:
            print(f"WARNING! Initial DMA ctrl status: {d_ctrl:08x}")
            print(f"EXPECTED: {DMA_CTRL:08x}")
        self._WriteDMA(addr, DMA_CTRL)

        # check DMA destination registers, should NOT write this! Embedded software
        # and DMA control this register
        addr = DMA_REG.S2MM_DEST_ADDR
        d_dest = self._ReadDMA(addr)
        if d_dest != DMA_DEST_MSB:
            print(f"WARNING! DMA Destination Reg is: {d_dest:08x}")
            print(f"EXPECTED: {DMA_DEST_MSB:08x}")

        # update the current length buffer
        addr = DMA_REG.S2MM_LENGTH
        dma_leng = self._ReadDMA(addr)
        if dma_leng != DMA_LENGTH:
            print(f"WARNING! DMA Length Reg is: {dma_leng:08x}")
            print(f"EXPECTED: {dma_leng:08x}")

        # verify DMA status
        addr = DMA_REG.S2MM_STATUS
        dma_stat = self._ReadDMA(addr)
        if dma_stat != DMA_STATUS:
            print(f"WARNING DMA Status NOT as expected: {dma_stat:08x} NOT {DMA_STATUS:08x}")
            for r in DMA_STATUS_BIT:
                if r.value & dma_stat:
                    print(f"REG {r} has error with DMA bit")

        self._dma_enabled = True
        return self._dma_enabled

    def _resetDMA(self):
        """
        NOTE: Mostly deprecated! Embedded software should handle DMA resets
        Write a bit to the second slot of the ctrl register and read back when it's zero..
        """
        # initialize DMA ctrl
        addr = DMA_REG.S2MM_CTRL
        self._WriteDMA(addr, DMA_CTRL+(1 << 2))
        d_ctrl = self._ReadDMA(addr)
        print(f"Final DMA ctrl status: {d_ctrl:08x}")

    def udp_done(self):
        """
        signaled from the SAQ worker which manages the UDP socket
        """
        print("SAQ UDP thread worker is finished!")
        self.thread.quit()

    def start(self):
        """
        Used to start and stop the thread
        """
        self.thread.start()

    def finish(self):
        """
        slot function to emit finished signal
        """
        self.finished.emit()
        QUdpSocket().writeDatagram(EXIT_PACKET, QHostAddress(QP_UDP_IP), QP_UDP_PORT)

if __name__ == '__main__':
    qpi = qdb_interface()
    print()
    qpi.regRead(0)
