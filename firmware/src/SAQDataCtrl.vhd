-------------------------------------------------------------------------------
-- Title      : SAQDataCtrl
-- Project    : ZyboQDB
-------------------------------------------------------------------------------
-- File       : SAQDataCtrl.vhd
-- Author     : Kevin Keefe <kevinpk@hawaii.edu>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-06
-- Platform   : Windows 11
-- Standard   : VHDL08
-------------------------------------------------------------------------------
-- Description: SAQ Data Ctrl, controlled via SAQNode. Primary responsibility
-- is to correctly read / timestamp incoming data from physical ports of SAQ
-------------------------------------------------------------------------------
-- Copyright (c) 2022
-------------------------------------------------------------------------------
-- Revisions  :
-- Date        Version  Author  Description
-- 2022-09-06  1.0      keefe	Created
-------------------------------------------------------------------------------

library IEEE;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_unsigned.all;

library work;
use work.QpixPkg.all;
use work.QpixProtoPkg.all;

-- fancy sl / slv alias'
use work.UtilityPkg.all;

entity SaqDataCtrl is
generic (
  N_SAQ_PORTS    : natural := 8;
  TIMESTAMP_BITS : natural := 32);      -- number of input SAQ channels to zybo
port (
  clk             : in  sl;
  rst             : in  sl;
  -- Data IO
  saqPortData     : in  slv(N_SAQ_PORTS - 1 downto 0);
  saqCtrlOut      : out slv(N_SAQ_PORTS + TIMESTAMP_BITS - 1 downto 0);
  saqCtrlOutValid : out sl;
  -- Register Config ports
  saqMask         : in  slv(N_SAQ_PORTS-1 downto 0)
  );
  
end SaqDataCtrl;

architecture Behavioral of SAQDataCtrl is

  -- timestamp on the SAQ hits
  signal counter : slv(TIMESTAMP_BITS-1 downto 0) := (others => '0');

  -- edge detector data
  signal saqPortDataE : slv(N_SAQ_PORTS-1 downto 0) := (others => '0');
  signal trigger      : sl                        := '0';

begin  -- architecture SAQDataCtrl

   -- increment counter
   process (clk, counter)
   begin
      if rising_edge(clk) then
         if rst = '1' then
            counter <= (others => '0');
         else
            counter <= counter + 1;
         end if;
      end if;
   end process;

   -- edge detector on the SAQ data
   SAQ_ANALOG_IN_GEN : for i in 0 to N_SAQ_PORTS-1 generate
      SAQ_PulseEdge_U : entity work.EdgeDetector
         port map(
            clk    => clk,
            rst    => rst,
            input  => saqPortData(i),
            output => saqPortDataE(i)
         );
   end generate SAQ_ANALOG_IN_GEN;

   ---------------------------------------------------
   -- Data Ctrl
   ---------------------------------------------------
   -- Reads input saqData ports and creates timestamps
   -- which fill events within FIFO

   -- process the edge detectors against the register mask
    process (saqPortDataE, saqMask) is
        variable trg : std_logic;
    begin
        trg := '0';
        for i in N_SAQ_PORTS - 1 downto 0 loop
            trg := trg or (saqPortDataE(i) and saqMask(i));
        end loop;
        trigger <= trg;
    end process;

   -- if we get a trigger, then we should format the data and send
   -- it to the FIFO
   process (clk, trigger, counter)
   begin
      if rising_edge(clk) then
         saqCtrlOutValid <= '0';
         if trigger = '1' then
           saqCtrlOutValid <= '1';
           saqCtrlOut      <= saqPortData & counter;
         end if;
      end if;
   end process;

end architecture Behavioral;
