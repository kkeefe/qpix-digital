----------------------------------------------------------------------------------
-- QPix communication with neighbour ASICs
----------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_misc.all;

use work.QpixPkg.all;


entity QpixComm is
   generic (
      NUM_BITS_G     : natural := 64;
      GATE_DELAY_G   : time    := 1 ns;
      TXRX_TYPE      : string  := "ENDEAVOR"; -- "DUMMY"/"UART"/"ENDEAVOR"

      N_ZER_CLK_G    : natural :=  8;  --2;
      N_ONE_CLK_G    : natural :=  24; --5;
      N_GAP_CLK_G    : natural :=  16; --4;
      N_FIN_CLK_G    : natural :=  40; --7;
                                       --  
      N_ZER_MIN_G    : natural :=  4;  --1;
      RAM_TYPE       : string  := "Lattice"; -- lattice hardcodes BRAM for lattice, or distributed / block
      N_ZER_MAX_G    : natural :=  12; --3;
      N_ONE_MIN_G    : natural :=  16; --4;
      N_ONE_MAX_G    : natural :=  32; --6;
      N_GAP_MIN_G    : natural :=  8;  --3;
      N_GAP_MAX_G    : natural :=  32; --5;
      N_FIN_MIN_G    : natural :=  32  --6 


   );
   port (
      clk            : in std_logic;
      rst            : in std_logic;

      EndeavorScale  : in std_logic_vector(2 downto 0);
      fifoFull       : in std_logic;

      -- external ASIC ports
      TxPortsArr     : out std_logic_vector(3 downto 0);
      RxPortsArr     : in  std_logic_vector(3 downto 0);
      
      -- tx/rx data to QpixRoute
      parseDataRx    : in  QpixDataFormatType; -- Tx from QpixRoute
      parseDataTx    : out QpixDataFormatType; -- Rx to QpixRoute
      parseDataReady : out std_logic;          -- Tx-ready to QpixRoute

      -- Debug
      TxByteValidArr_out : out std_logic_vector(3 downto 0);
      RxByteValidArr_out : out std_logic_vector(3 downto 0);
      RxFifoEmptyArr_out : out std_logic_vector(3 downto 0);
      RxFifoFullArr_out  : out std_logic_vector(3 downto 0);

      -- register from  QpixRegFile
      qpixConf       : in QpixConfigType;

      -- register information to QpixRegFile
      regData        : out QpixRegDataType;
      regResp        : in QpixRegDataType
   );
end entity QpixComm;

architecture behav of QpixComm is

   ------------------------------------------------------------
   -- Type defenitions
   ------------------------------------------------------------
   type QpixDataArrType is array (0 to 3) of QpixDataFormatType;

   ------------------------------------------------------------
   -- Signals
   ------------------------------------------------------------
   signal TxByteArr      : QpixByteArrType              := (others => (others => '0'));
   signal TxByteValidArr : std_logic_vector(3 downto 0) := (others => '0');
   signal TxByteReadyArr : std_logic_vector(3 downto 0) := (others => '0');

   signal RxByteArr        : QpixByteArrType      := (others => (others => '0'));

   signal RxBytesAck       : std_logic_vector(3 downto 0);
   signal RxBytesValid     : std_logic_vector(3 downto 0);
   signal RxBusyArr        : std_logic_vector(3 downto 0);
   signal RxErrorArr       : std_logic_vector(3 downto 0);

   signal TxReadyMask        : std_logic;

   --signal parseDataTx           : QpixDataFormatType := QpixDataZero_C;

begin

   -- debug
   TxByteValidArr_out <= TxByteValidArr;
   RxByteValidArr_out <= RxByteValidArr;
   RxFifoEmptyArr_out <= RxFifoEmptyArr;
   RxFifoFullArr_out <= RxFifoFullArr;
   
   ------------------------------------------------------------
   -- Transcievers
   ------------------------------------------------------------
   GEN_TXRX : for i in 0 to 3 generate

      UART_GEN : if TXRX_TYPE = "UART" generate 
         QpixTxRx_U : entity work.UartTop
         generic map (
            NUM_BITS_G => NUM_BITS_G
         )
         port map (
            clk         => clk,
            sRst        => rst,

            --txValid     => TxPortsArr(i).Valid,
            txByte      => TxByteArr(i), 
            txByteValid => TxByteValidArr(i), 
            txByteReady => TxByteReadyArr(i),

            --rxValid     => RxPortsArr(i).Valid,
            rxByte      => RxByteArr(i),
            rxByteValid => RxBytesValid(i),
            rxFrameErr  => open,
            rxBreakErr  => open,

            uartRx      => RxPortsArr(i),
            uartTx      => TxPortsArr(i)
            
         );
      end generate UART_GEN;

      ENDEAROV_GEN : if TXRX_TYPE = "ENDEAVOR" generate
            QpixTXRx_U : entity work.QpixEndeavorTop
            generic map (
               NUM_BITS_G    => NUM_BITS_G,
               N_ZER_CLK_G   => N_ZER_CLK_G,
               N_ONE_CLK_G   => N_ONE_CLK_G,
               N_GAP_CLK_G   => N_GAP_CLK_G,
               N_FIN_CLK_G   => N_FIN_CLK_G,
                                         
               N_ZER_MIN_G   => N_ZER_MIN_G,
               N_ZER_MAX_G   => N_ZER_MAX_G,
               N_ONE_MIN_G   => N_ONE_MIN_G,
               N_ONE_MAX_G   => N_ONE_MAX_G,
               N_GAP_MIN_G   => N_GAP_MIN_G,
               N_GAP_MAX_G   => N_GAP_MAX_G,
               N_FIN_MIN_G   => N_FIN_MIN_G
            )
            port map (
               clk          => clk,
               sRst         => rst,

               scale        => EndeavorScale,
               TxRxDisable  => TxRxDisable(i),
                            
               txByte       => TxByteArr(i), 
               txByteValid  => TxByteValidArr(i), 
               txByteReady  => TxByteReadyArr(i),

               rxByte       => RxByteArr(i),
               rxByteValid  => RxBytesValid(i),
               RxByteAck    => RxBytesAck(i),
               rxBusy       => RxBusyArr(i),
               rxError      => RxErrorArr(i),

               Rx           => RxPortsArr(i),
               Tx           => TxPortsArr(i)
            );
      end generate ENDEAROV_GEN;
   end generate GEN_TXRX;
   ------------------------------------------------------------

   process (clk)
   begin
      if rising_edge(clk) then
         if RxBytesValid /= b"0000" then
            RxValidDbg <= '1';
         else
            RxValidDbg <= '0';
         end if;
      end if;
   end process;

   RxBusy  <= '0' when RxBusyArr  = b"0000" else '1';
   RxError <= '0' when RxErrorArr = b"0000" else '1';

   process (qpixConf.DirMask, TxByteReadyArr)
   begin
         if (qpixConf.DirMask and TxByteReadyArr) = qpixConf.DirMask then
            TxReadyMask <= '1';
         else
            TxReadyMask <= '0';
         end if;
   end process;
   TxReady <= TxReadyMask;

   ------------------------------------------------------------
   -- Parser
   ------------------------------------------------------------
   QpixParser_U : entity work.QpixParser
   port map(
      clk          => clk,
      rst          => rst,

      qpixConf          => qpixConf,
      fifoFull          => fifoFull,

      -- Rx connections from Phys Layer
      inBytesArr        => RxByteArr,
      inBytesValid      => RxBytesValid,
      inBytesAck        => RxBytesAck,
      inData            => inData,

      -- Tx connections to Phys Layer
      outData           => outData_i,
      outBytesArr       => TxByteArr,
      outBytesValidArr  => TxByteValidArr,
      txReady           => TxReadyMask,

      -- data to route
      parseDataTx => parseDataTx,           -- output
      parseDataRx => parseDataRx,           -- input

      -- regFile configurations
      qpixConf => qpixConf,             -- input
      regData => regData,               -- output
      regResp => regResp                -- input
   );
   ------------------------------------------------------------

end behav;
