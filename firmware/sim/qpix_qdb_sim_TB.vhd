----------------------------------------------------------------------------------
-- Company: 
-- Engineer: 
-- 
-- Create Date: 04/05/2022 05:37:43 PM
-- Design Name: 
-- Module Name: qpix_qdb_sim_TB - Behavioral
-- Project Name: 
-- Target Devices: 
-- Tool Versions: 
-- Description: 
-- 
-- Dependencies: 
-- 
-- Revision:
-- Revision 0.01 - File Created
-- Additional Comments:
-- 
----------------------------------------------------------------------------------


library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
-- use IEEE.NUMERIC_STD.ALL;

library work;
use work.UtilityPkg.all;
use work.QpixPkg.all;
use work.QpixProtoPkg.all;

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
--use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

entity qpix_qdb_sim_TB is
end qpix_qdb_sim_TB;

architecture Behavioral of qpix_qdb_sim_TB is

  -- constants for clocks and simulation
   constant CLK_PERIOD_NOMINAL_C           : time := 20833.0 ps; -- 48 MHz
   constant Zynq_CLK_PERIOD_NOMINAL_C      : time := 8000.0 ps;  -- 125 MHz
   constant Asic_CLK_PERIOD_NOMINAL_C      : time := 83333.0 ps; -- 12 MHz
   constant CLK_PERIOD_SPREAD_FRACTIONAL_C : real := 0.05;
   constant GATE_DELAY_C : time := 1 ns;
   constant MEM_DEPTH : natural := 12;

   -- ZyboRegisters
   signal clk48          : std_logic;
   signal rst            : std_logic;
   signal addr           : std_logic_vector(31 downto 0);
   signal rdata          : std_logic_vector(31 downto 0);
   signal wdata          : std_logic_vector(31 downto 0);
   signal req            : std_logic;
   signal wen            : std_logic;
   signal ack            : std_logic;
   signal asic_mask      : std_logic_vector(15 downto 0) := (others => '1');
   signal evtSize        : std_logic_vector(31 downto 0);
   signal status         : std_logic_vector(31 downto 0);
   signal daqFrameErrCnt : std_logic_vector(31 downto 0);
   signal daqBreakErrCnt : std_logic_vector(31 downto 0);
   signal extFifoMax     : Slv4b2DArray;
   signal trgTime        : std_logic_vector(31 downto 0);
   -- signal hitMask        : Sl2DArray(0 to X_NUM_G-1, 0 to Y_NUM_G-1);
   signal hitMask        : Sl2DArray; -- simulation
   signal timestamp      : std_logic_vector(31 downto 0);
   signal chanMask       : std_logic_vector(G_N_ANALOG_CHAN-1 downto 0) := (others => '1');
   signal trg            : std_logic;
   signal asicAddr       : std_logic_vector(31 downto 0);
   signal asicOpWrite    : std_logic;
   signal asicData       : std_logic_vector(15 downto 0);
   signal asicReq        : std_logic;
   signal memRdReq       : std_logic;
   signal memRdAck       : std_logic;
   signal memData        : std_logic_vector(31 downto 0);
   signal memAddr        : std_logic_vector(G_QPIX_PROTO_MEM_DEPTH-1+2 downto 0);

   -- ZybDaq Node
   signal clk12        : std_logic;
   signal DaqTx        : QpixTxRxPortType;
   signal DaqRx        : QpixTxRxPortType;
   signal evt_fin      : std_logic;
--   signal uartBreakCnt : std_logic_vector(31 downto 0);
--   signal uartFrameCnt : std_logic_vector(31 downto 0);
   signal memAddrRst   : std_logic;
   -- signal memRdAddr    : std_logic_vector(9-1+2 downto 0);
   -- signal memDataOut   : std_logic_vector(31 downto 0);

  -- QDBAsic signals
  --signal clk     : std_logic;
  signal asicClk : std_logic;
  signal red_led : std_logic_vector(3 downto 0);
  signal blu_led : std_logic_vector(3 downto 0);
  signal gre_led : std_logic_vector(3 downto 0);
--  type IOports is array (0 to 3) of std_logic_vector(3 downto 0);
--  signal IO : IOports;

  constant fake_trg_cnt : natural := 200*12;-- try to get ~200 us fake trigger rate;
   -- all ASIC TxRx ports
--  signal A_Tx1 : std_logic;
--  signal A_Rx1 : std_logic;
--  signal A_Tx2 : std_logic;
--  signal A_Rx2 : std_logic;
--  signal A_Tx3 : std_logic;
--  signal A_Rx3 : std_logic;
--  signal A_Tx4 : std_logic;
--  signal A_Rx4 : std_logic;

--  signal B_Tx1 : std_logic;
--  signal B_Rx1 : std_logic;
--  signal B_Tx2 : std_logic;
--  signal B_Rx2 : std_logic;
--  signal B_Tx3 : std_logic;
--  signal B_Rx3 : std_logic;
--  signal B_Tx4 : std_logic;
--  signal B_Rx4 : std_logic;

--  signal C_Tx1 : std_logic;
--  signal C_Rx1 : std_logic;
--  signal C_Tx2 : std_logic;
--  signal C_Rx2 : std_logic;
  signal C_Tx3 : std_logic;
  signal C_Rx3 : std_logic;
--  signal C_Tx4 : std_logic;
--  signal C_Rx4 : std_logic;

--  signal D_Tx1 : std_logic;
--  signal D_Rx1 : std_logic;
--  signal D_Tx2 : std_logic;
--  signal D_Rx2 : std_logic;
--  signal D_Tx3 : std_logic;
--  signal D_Rx3 : std_logic;
--  signal D_Tx4 : std_logic;
--  signal D_Rx4 : std_logic;

begin

  ----------------------
  -- ASIC Connections --
  ----------------------
  -- DaqNode
  DaqRx <= C_Tx3;
  C_Rx3 <= DaqTx;
  -- East West
  -- AB
--  B_Rx4 <= A_Tx2;
--  A_Rx2 <= B_Tx4;
--  -- CD
--  D_Rx4 <= C_Tx2;
--  C_Rx2 <= D_Tx4;
--  -- North South
--  -- AC
--  A_Rx3 <= C_Tx1;
--  C_Rx1 <= A_Tx3;
--  -- BD
--  B_Rx3 <= D_Tx1;
--  D_Rx1 <= B_Tx3;


    -- instantiate a portion of the top level here
    U_QpixProtoRegMap : entity work.QpixProtoRegMap
      generic map(
        X_NUM_G => 1,
        Y_NUM_G => 1)
      port map(
        clk            => clk12,
        rst            => rst,
        -- axi protocol information
        addr           => addr,
        rdata          => rdata,
        wdata          => wdata,
        req            => req,
        wen            => wen,
        ack            => ack,
        -- register information
        asic_mask      => asic_mask,
        evtSize        => evtSize,
        status         => status,
        daqFrameErrCnt => daqFrameErrCnt,
        daqBreakErrCnt => daqBreakErrCnt,
        extFifoMax     => extFifoMax,
        trgTime        => trgTime,
        hitMask        => hitMask,
        timestamp      => timestamp,
        chanMask       => chanMask,
        trg            => trg, -- trg
        -- asic outputs to QpixDaqCtrl
        asicReq        => asicReq,
        asicOpWrite    => asicOpWrite,
        asicData       => asicData,
        asicAddr       => asicAddr,
        -- memory fifo within QpixDaqCtrl
        memRdReq       => memRdReq,
        memRdAck       => memRdAck,
        memData        => memData,
        memAddr        => memAddr
      );

    U_QpixDaqCtrl : entity work.QpixDaqCtrl
      generic map(
        MEM_DEPTH => MEM_DEPTH,
        TXRX_TYPE => "ENDEAVOR" -- "DUMMY"/"UART"/"ENDEAVOR"
      )
      port map(
        clk          => clk12,
        rst          => rst,
        daqTx        => daqTx,
        daqRx        => daqRx,
        -- trg in and status signals
        trg          => trg,
        trgTime      => trgTime,
        evt_fin      => evt_fin,
        uartBreakCnt => daqBreakErrCnt,
        uartFrameCnt => daqFrameErrCnt,
        -- asic inputs from QpixProtoRegMap
        asicReq      => asicReq,
        asicOpWrite  => asicOpWrite,
        asicData     => asicData,
        asicAddr     => asicAddr,
        asic_mask    => asic_mask,
        -- memory data stored in fifo
        memRdReq     => memRdReq,
        memRdAck     => memRdAck,
        memDataOut   => memData,
        memEvtSize   => evtSize,
        memAddrRst   => memAddrRst,
        memRdAddr    => memAddr,
        memFullErr   => open
      );
      memAddrRst <= trg or asicReq;

--    -- ASIC-A, "main" ASIC that speaks with DaqNode
--    U_QDBAsicA : entity work.QDBAsicTop
--    generic map(
--       X_POS_G      => 0,
--       Y_POS_G      => 1,
--       pulse_time  => 2,
--       fake_trg_cnt => fake_trg_cnt,
--       TXRX_TYPE    => "ENDEAVOR"       -- "DUMMY"/"UART"/"ENDEAVOR"
--    )
--    port map(
--        -- internal clock
--        clk     => clk12,
--        --rst : in STD_LOGIC;
--        Tx1     => A_Tx1,
--        Rx1     => A_Rx1,
--        Tx2     => A_Tx2,
--        Rx2     => A_Rx2,
--        Tx3     => A_Tx3,
--        Rx3     => A_Rx3,
--        Tx4     => A_Tx4,
--        Rx4     => A_Rx4,
--        -- outputs
--        red_led => red_led(0),
--        blu_led => blu_led(0),
--        gre_led => gre_led(0)
--    );

--    -- ASIC-B
--    U_QDBAsicB : entity work.QDBAsicTop
--    generic map(
--       X_POS_G      => 1,
--       Y_POS_G      => 1,
--       pulse_time  => 2,
--       fake_trg_cnt => fake_trg_cnt,
--       TXRX_TYPE    => "ENDEAVOR"       -- "DUMMY"/"UART"/"ENDEAVOR"
--    )
--    port map(
--        -- internal clock
--        clk => clk12,
--        --rst : in STD_LOGIC;
--        Tx1 => B_Tx1,
--        Rx1 => B_Rx1,
--        Tx2 => B_Tx2,
--        Rx2 => B_Rx2,
--        Tx3 => B_Tx3,
--        Rx3 => B_Rx3,
--        Tx4 => B_Tx4,
--        Rx4 => B_Rx4,
--        -- outputs
--        red_led => red_led(1),
--        blu_led => blu_led(1),
--        gre_led => gre_led(1)
--    );

    -- ASIC-C, "main" ASIC that speaks with DaqNode
    U_QDBAsicC : entity work.QDBAsicTop
    generic map(
        X_POS_G      => 0,
        Y_POS_G      => 0,
        pulse_time   => 2,
        fake_trg_cnt => fake_trg_cnt,
        RAM_TYPE => "distributed",
        TXRX_TYPE => "ENDEAVOR" -- "DUMMY"/"UART"/"ENDEAVOR"
    )
    port map(
        -- internal clock
        clk => clk12,
        rst => rst,
        --rst : in STD_LOGIC;
--        Tx1 => C_Tx1,
--        Rx1 => C_Rx1,
--        Tx2 => C_Tx2,
--        Rx2 => C_Rx2,
        Tx3 => C_Tx3,
        Rx3 => C_Rx3,
--        Tx4 => C_Tx4,
--        Rx4 => C_Rx4,
        -- outputs
        red_led => red_led(2),
        blu_led => blu_led(2),
        gre_led => gre_led(2)
    );

--    -- ASIC-D
--    U_QDBAsicD : entity work.QDBAsicTop
--    generic map(
--        X_POS_G   => 1,
--        Y_POS_G   => 0,
--        pulse_time  => 2,
--        fake_trg_cnt => fake_trg_cnt,
--        TXRX_TYPE => "ENDEAVOR" -- "DUMMY"/"UART"/"ENDEAVOR"
--    )
--    port map(
--        -- internal clock
--        clk => clk12,
--        --rst : in STD_LOGIC;
--        Tx1 => D_Tx1,
--        Rx1 => D_Rx1,
--        Tx2 => D_Tx2,
--        Rx2 => D_Rx2,
--        Tx3 => D_Tx3,
--        Rx3 => D_Rx3,
--        Tx4 => D_Tx4,
--        Rx4 => D_Rx4,
--        -- outputs
--        red_led => red_led(3),
--        blu_led => blu_led(3),
--        gre_led => gre_led(3)
--    );

   --
   -- Simulation clocks for signals
   --
   U_QDBAsicClk : entity work.ClkRst
      generic map (
         RST_HOLD_TIME_G   => 1 us -- : time    := 6 us;  -- Hold reset for this long
      )
      port map (
         CLK_PERIOD_G => CLK_PERIOD_NOMINAL_C, -- : time    := 10 ns;
         CLK_DELAY_G  => 1 ns,   -- : time    := 1 ns;  -- Wait this long into simulation before asserting reset
         clkP         => clk48, -- : out sl := '0';
         rst          => open  -- : out sl := '1';
      );

    U_QDBAsicClk12 : entity work.ClkRst
      generic map (
         RST_HOLD_TIME_G   => 1 us -- : time    := 6 us;  -- Hold reset for this long
      )
      port map (
         CLK_PERIOD_G => Asic_CLK_PERIOD_NOMINAL_C, -- : time    := 10 ns;
         CLK_DELAY_G  => 1 ns,   -- : time    := 1 ns;  -- Wait this long into simulation before asserting reset
         clkP         => clk12, -- : out sl := '0';
         rst          => open  -- : out sl := '1';
      );

   ----------------------------
   -- Generate random resets --
   ----------------------------
   stim_proc : process

   begin
      -- TODO
      -------------------------------------------------
      -- Initialize the clock phases and frequencies --
      -------------------------------------------------

      --------------------------
      -- Stimulus begins here --
      --------------------------
      wait for 2.0 ns;
        status   <= x"beefcafe";
        addr     <= (others => '0');
        wdata    <= 0x"1234abcd";
        rst <= '0';
        -- turn off reception from un-connected directions
--        A_Rx1 <= '0';
--        A_Rx4 <= '0';
--        -- B
--        B_Rx1 <= '0';
--        B_Rx2 <= '0';
--        -- C only doesn't connect WEST
--        C_Rx4 <= '0';
--        -- D - Doesn't  east / south
--        D_Rx2 <= '0';
--        D_Rx3 <= '0';
        wen <= '0';
        req <= '0';
        
      -- unused now 
      -- RegMapping Read 0, should be able to read beef_cafe  
      -- initial proto reg map request to set ack, read STATUS (check)
--      wait for 200 us;   
--        -- everything is bit shit 2..
--        addr <= x"000" & x"0" & x"0004";
--        wen  <= '1';
--        req  <= '1';
--      wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
--        req <= '0';
--        wen <= '0';    
       
      -- unused now  
      -- Asic_Reg_Request Read 3, look for DaqNode to receive something back          
      -- initial ASIC request, read aaaa_bbbb (check)
--      wait for 200 us;
--        addr <= x"000" & x"c" & x"0000"; -- unused & asic reg-request & asicAddr
--        req  <= '1';   -- required to set ack ..
--      wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
--        req <= '0';

      -- manually route ASICs to tell the "furthest left" to send down
      -- send asic dir mask!
      wait for 200 us; -- (sets C manual routing, successfully)
        req   <= '1';
        wdata <= x"0000001" & b"0100";    -- set ManRoute '1' and DirMask "DirDown" from QPixPkg.vhd 
        wen <= '1';                       -- opWrite
        addr  <= x"000" & x"c" & x"080c"; -- C for remote, 100 for dest & X/Y, c=3<<2 for dir mask
      wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
        req <= '0';
      wait for 500 us; -- (sets A manual routing, successfully)
--          req   <= '1';
--          wdata <= x"0000001" & b"0100";    -- set ManRoute '1' and DirMask "DirDown" from QPixPkg.vhd 
--          wen <= '1';                       -- opWrite
--          addr  <= x"000" & x"c" & x"082c"; -- C for remote, 002 for X/Y, c=3<<2 for dir mask
--        wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
--          req <= '0';
   
      -- interrogate fifos after setting the dirMask with trigger
      wait for 500 us;
              req   <= '1';
              wdata <= x"00000001";             -- set interrogation
              wen <= '1';                       -- opRead
              addr  <= x"000" & x"0" & x"0028"; -- default trigger here
            wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
              req <= '0';
              wen <= '0';
      -- equivalent to trigger above
      -- local fifo interrogations, (successfully sends all data back along C_Tx3
--      wait for 500 us;
--        req   <= '1';
--        wdata <= x"00000001";             -- set interrogation
--        wen <= '0';                       -- opRead
--        addr  <= x"000" & x"c" & x"0004"; -- C for remote, 000 for X/Y, 4=1<<2 for interrogation
--      wait for Asic_CLK_PERIOD_NOMINAL_C * 2;
--        trg <= '0';
--        req <= '0';

      -- Fifo_Counters Read 2
      -- Read EvtSize -> Should get 8 since that's how many events are in DaqCtrl BRAM
      wait for 5 ms;
        addr  <= x"00000010"; -- read the event size from the DAQ buffer
        req   <= '1';
      wait for Asic_CLK_PERIOD_NOMINAL_C * 2; 
        req <= '0';

      -- Event_Memory Read 1
      -- try to read in from the event memory 
--      wait for 1 ms;
--      ----------   unused & evtMmem &  addr  & mux  & unused
--          addr  <= x"000" &   x"4"  & x"003" & "00" & "00";
--          req   <= '1';
--      wait for Asic_CLK_PERIOD_NOMINAL_C * 10;              
--          req <= '0';
     
      -- End simulation stimulus by waiting forever
      wait;
   end process;
end Behavioral;
