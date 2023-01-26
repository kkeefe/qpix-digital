-- Title      : <title string>
-- Project    :
-------------------------------------------------------------------------------
-- File       : SAQAxiFIFO.vhd
-- Author     : John Doe  <john@doe.com>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-14
-- Platform   :
-- Standard   : VHDL'93/02
-------------------------------------------------------------------------------
-- Description: <cursor>
-------------------------------------------------------------------------------
-- Copyright (c) 2022
-------------------------------------------------------------------------------
-- Revisions  :
-- Date        Version  Author  Description
-- 2022-09-06  1.0      keefe	Created
-------------------------------------------------------------------------------

-------------------------------------------------------------------------------
-- Title      : SAQAxiFIFO
-- Project    :
-------------------------------------------------------------------------------
-- File       : SAQAxiFIFO.vhd
-- Author     : Kevin Keefe  <kevinpk@hawaii.edu>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-06
-- Platform   :
-- Standard   : VHDL'93/02
-------------------------------------------------------------------------------
-- Description: Testbench for exercising the SaqAxi Fifo
-------------------------------------------------------------------------------
-- Copyright (c) 2022
-------------------------------------------------------------------------------
-- Revisions  :
-- Date        Version  Author  Description
-- 2022-09-06  1.0      keefe	Created
-------------------------------------------------------------------------------

library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

library work;
use work.UtilityPkg.all;
use work.QpixPkg.all;
use work.QpixProtoPkg.all;

entity SAQAxiFIFO_tb is
end SAQAxiFIFO_tb;

architecture Behavioral of SAQAxiFIFO_tb is

    -- constants for clocks and simulation
    constant CLK_PERIOD_NOMINAL_C           : time := 20833.0 ps; -- 48 MHz
    constant Zynq_CLK_PERIOD_NOMINAL_C      : time := 8000.0 ps;  -- 125 MHz
    constant Asic_CLK_PERIOD_NOMINAL_C      : time := 83333.0 ps; -- 12 MHz
    constant CLK_PERIOD_SPREAD_FRACTIONAL_C : real := 0.05;
    constant GATE_DELAY_C : time := 1 ns;

    -- signals for DUT
    signal clk : std_logic := '0';
    signal rst   : std_logic := '0';

    signal saq_fifo_ren : sl;
    signal saqEnable    : sl;
    signal saqForce     : sl;
    signal fifo_valid   : sl;
    signal fifo_dout    : slv(63 downto 0);
    signal fifo_empty   : sl;
    signal fifo_full    : sl;
    signal fifo_wr_en   : sl;
    signal saqPacketLength : slv(31 downto 0);

    signal S_AXI_0_tdata  : slv(31 downto 0);
    signal S_AXI_0_tlast  : sl;
    signal S_AXI_0_tready : sl;
    signal S_AXI_0_tvalid : sl;


begin

  ----------------------
  -- ASIC Connections --


    -- instantiate a portion of the top level here
    U_SAQAxiFifo : entity work.SAQAxiFifo
      port map(
        clk          => clk,
        fifo_dout    => fifo_dout,
        fifo_wr_en   => fifo_wr_en,
        saq_fifo_ren => saq_fifo_ren,
        fifo_valid   => fifo_valid,
        fifo_empty   => fifo_empty,
        fifo_full    => fifo_full,

        -- register connections
        saqEnable => saqEnable,
        saqForce  => saqForce,
        saqPacketLength => saqPacketLength,

        -- AXI4-Stream Data Fifo Ports
        -- write data channel
        S_AXI_0_tdata   => S_AXI_0_tdata,
        S_AXI_0_tlast   => S_AXI_0_tlast,
        S_AXI_0_tready  => S_AXI_0_tready,
        S_AXI_0_tvalid  => S_AXI_0_tvalid);

   --
   -- Simulation clocks for signals
   --
    U_QDBAsicClk12 : entity work.ClkRst
      generic map (
         RST_HOLD_TIME_G   => 1 us -- : time    := 6 us;  -- Hold reset for this long
      )
      port map (
         CLK_PERIOD_G => Asic_CLK_PERIOD_NOMINAL_C, -- : time    := 10 ns;
         CLK_DELAY_G  => 1 ns,   -- : time    := 1 ns;  -- Wait this long into simulation before asserting reset
         clkP         => clk, -- : out sl := '0';
         rst          => open  -- : out sl := '1';
      );

   ----------------------------
   -- Generate random resets --
   ----------------------------
   stim_proc : process

   begin

      --------------------------
      -- Stimulus begins here --
      --------------------------
      wait for 2.0 ns;

      -- assign inputs
      fifo_dout      <= x"1234567812345678";
      S_AXI_0_tready <= '1';
      saqEnable      <= '1';
      saqForce       <= '0';
      fifo_full      <= '0'; -- never should be full, really
      fifo_empty     <= '1';
      fifo_wr_en <= '0';  -- doesn't do anything in this module
      saqPacketLength <= x"00000005";
      
      -- send two sets of 5 packets, valid = '1' and empty = '0' for 20 clk cycles
      wait for Asic_CLK_PERIOD_NOMINAL_C * 5;
        fifo_empty <= '0';
        fifo_valid <= '1';
      wait for Asic_CLK_PERIOD_NOMINAL_C *15;
        fifo_valid <= '0'; -- fifo not responding, not valid test for 5 clk cycles
        fifo_empty <= '0';
     wait for Asic_CLK_PERIOD_NOMINAL_C *5;
        fifo_valid <= '1';
        fifo_empty <= '0';
     wait for Asic_CLK_PERIOD_NOMINAL_C *5;
        fifo_valid <= '1';
        fifo_empty <= '1';
        
     -- verified, sent short packet
     -- send 8 packets and a force (not empty for 8 clk cycles, all valid)    
     wait for Asic_CLK_PERIOD_NOMINAL_C *1;
        saqForce <= '1';
        fifo_valid <= '1';
        fifo_empty <= '0';
     wait for Asic_CLK_PERIOD_NOMINAL_C * 1;
        saqForce <= '0';              
     wait for Asic_CLK_PERIOD_NOMINAL_C * 6;
        fifo_valid <= '1';
        fifo_empty <= '1';


--      wait for 250 ns;
--        fifo_valid <= '1';

--      wait for 500 ns;
--        fifo_valid <= '0';

--      wait for 250 ns;
--        fifo_valid <= '1';

--      wait for 500 ns;
--        fifo_empty <= '0';
        
--      wait for 500 ns;
--        fifo_valid <= '1';
        
--      wait for 5 us;
--        fifo_empty <= '1';

--      wait for 5 us;
--        fifo_empty <= '0';

--      wait for 500 ns;
--        fifo_valid <= '0';

--      wait for 250 ns;
--        fifo_valid <= '1';

--      wait for 500 ns;
--        fifo_valid <= '0';

--      wait for 250 ns;
--        fifo_valid <= '1';

--      wait for 500 ns;
--        fifo_empty <= '0';
        
--      wait for 500 ns;
--        fifo_valid <= '1';
        
--      wait for 5 us;
--        fifo_empty <= '1';

      wait;
   end process;
end Behavioral;
