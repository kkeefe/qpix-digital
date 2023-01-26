-------------------------------------------------------------------------------
-- Title      : <title string>
-- Project    :
-------------------------------------------------------------------------------
-- File       : saq_qdb_sim_TB.vhd
-- Author     : John Doe  <john@doe.com>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-06
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
-- Title      : saq_qdb_sim_TB
-- Project    :
-------------------------------------------------------------------------------
-- File       : saq_qdb_sim_TB.vhd
-- Author     : Kevin Keefe  <kevinpk@hawaii.edu>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-06
-- Platform   :
-- Standard   : VHDL'93/02
-------------------------------------------------------------------------------
-- Description: Testbench for exercising the SAQNode + FIFO
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

entity saq_qdb_sim_TB is
end saq_qdb_sim_TB;

architecture Behavioral of saq_qdb_sim_TB is

  -- constants for clocks and simulation
   constant CLK_PERIOD_NOMINAL_C           : time := 20833.0 ps; -- 48 MHz
   constant Zynq_CLK_PERIOD_NOMINAL_C      : time := 8000.0 ps;  -- 125 MHz
   constant Asic_CLK_PERIOD_NOMINAL_C      : time := 83333.0 ps; -- 12 MHz
   constant CLK_PERIOD_SPREAD_FRACTIONAL_C : real := 0.05;
   constant GATE_DELAY_C : time := 1 ns;

   constant TIMESTAMP_BITS : natural := 32;
   constant N_SAQ_PORTS : natural := 8;

   -- signals for DUT
   signal clk12 : std_logic := '0';
   signal rst : std_logic := '0';
   signal saqPortData : slv(N_SAQ_PORTS - 1 downto 0);
   signal saqDataOut  : slv(63 downto 0) := (others => '0');
   signal saqReadEn   : sl;
   signal valid       : sl;
   signal empty       : sl;
   signal full        : sl;
   -- register mapping
   signal saqMask : slv(N_SAQ_PORTS - 1 downto 0) := (others => '0');


begin

  ----------------------
  -- ASIC Connections --


    -- instantiate a portion of the top level here
    U_SAQNode : entity work.SAQNode
      generic map(
        N_SAQ_PORTS => N_SAQ_PORTS,
        TIMESTAMP_BITS => TIMESTAMP_BITS)
      port map(
        clk            => clk12,
        rst            => rst,
        -- axi protocol information
        saqPortData => saqPortData,
        saqReadEn   => saqReadEn,
        saqDataOut  => saqDataOut,
        valid       => valid,
        empty       => empty,
        full        => full,
        saqMask     => saqMask);

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
         clkP         => clk12, -- : out sl := '0';
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
      
      
      -- 0-1-0 reset pattern required for FIFO generated in Xilinx IP
        saqReadEn <= '0';
        rst <= '0';
        saqPortData <= (others => '0');
        saqMask     <= (others => '1');
        
      wait for 500 ns;   
        rst <= '1';

      wait for 500 ns;
        rst <= '0';
        
      wait for 500 ns;   
        saqPortData <= (others => '1');        
      
      -- get a bunch of writes
      for i in 0 to 10 loop
        wait for 100 ns;
            saqPortData <= (others => '0');
        wait for 100 ns;
            saqPortData <= (others => '1');   
      end loop;
      
      -- trigger reads
      saqReadEn <= '1';


      wait;
   end process;
end Behavioral;
