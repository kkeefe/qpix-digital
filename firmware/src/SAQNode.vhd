-------------------------------------------------------------------------------
-- Title      : SAQNode
-- Project    : ZyboQDB
-------------------------------------------------------------------------------
-- File       : SAQNode.vhd
-- Author     : Kevin Keefe <kevinpk@hawaii.edu>
-- Company    :
-- Created    : 2022-09-06
-- Last update: 2022-09-19
-- Platform   : Windows 11
-- Standard   : VHDL08
-------------------------------------------------------------------------------
-- Description: SAQ Node impletemented on Zybo board with Vivado 2020.2, windows
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


entity SAQNode is
generic (
  N_SAQ_PORTS    : natural := 8;
  TIMESTAMP_BITS : natural := 32);      -- number of input SAQ channels to zybo
port (
  clk        : in  sl;
  rst        : in  sl;
  -- Data IO
  saqPortData : in  slv(N_SAQ_PORTS - 1 downto 0);
  saqDataOut  : out slv(63 downto 0);
  saqReadEn   : in  sl;
  valid       : out sl;
  empty       : out sl;
  full        : out sl;
  -- AXI-Stream IO
  S_AXI_0_tdata   : out STD_LOGIC_VECTOR (31 downto 0);
  S_AXI_0_tready  : in  STD_LOGIC;
  S_AXI_0_tlast   : out STD_LOGIC;
  S_AXI_0_tvalid  : out STD_LOGIC;

  -- Register Pins
  saqHits         : out slv(31 downto 0);
  saqMask         : in  slv(N_SAQ_PORTS - 1 downto 0);
  saqPacketLength : in  slv(31 downto 0);
  saqForce        : in  sl;
  saqEnable       : in  sl
  );
end SAQNode;

architecture Behavioral of SAQNode is

  -- SAQ Ctrl signals
  signal saqCtrlOutValid : sl := '0';
  signal saqCtrlDataOut : slv(N_SAQ_PORTS + TIMESTAMP_BITS - 1 downto 0);
  constant emtpy_bits    : slv(64 - N_SAQ_PORTS - TIMESTAMP_BITS - 1 downto 0) := (others => '0');

  -- FIFO connection signals
  signal fifo_valid : sl;
  signal fifo_empty : sl;
  signal fifo_full  : sl;

  signal fifo_din  : slv(63 downto 0);
  signal fifo_dout : slv(63 downto 0);

  signal fifo_rd_en  : sl;
  signal fifo_wr_en  : sl;

  signal saq_fifo_ren : sl;
  signal n_saq_hits : unsigned(31 downto 0);
  
  -- s_axi signals
  signal s_axis_tvalid : sl;
  signal s_axis_tready : sl;
  signal s_axis_tdata : slv(31 downto 0);
  signal m_axis_tvalid : sl;
  signal m_axis_tready : sl;
  signal m_axis_tdata : slv(31 downto 0);
  signal almost_full : sl;

begin  -- architecture SAQNode

  -- connections to entity
  valid      <= fifo_valid;
  empty      <= fifo_empty;
  full       <= fifo_full;
  saqDataOut <= fifo_dout;
  saqHits    <= std_logic_vector(n_saq_hits);
  
  -- keep track of how many hits we've received
  process(clk, n_saq_hits) begin
    if rising_edge(clk) then
        if fifo_valid = '1' then
            n_saq_hits <= n_saq_hits + 1;
        end if;
    end if;
  end process;

   ---------------------------------------------------
   -- Data Ctrl
   ---------------------------------------------------
   -- Reads input saqData ports and creates timestamps
   -- which fill events within FIFO
  SAQDataCtrl_U : entity work.SAQDataCtrl
    generic map(
      N_SAQ_PORTS    => N_SAQ_PORTS,
      TIMESTAMP_BITS => TIMESTAMP_BITS)
    port map(
      clk => clk,
      rst => rst,
      -- SAQ data
      saqPortData     => saqPortData,
      saqCtrlOut      => saqCtrlDataOut,
      saqCtrlOutValid => saqCtrlOutValid, -- SAQ trigger
      -- Register Config ports
      saqMask         => saqMask
    );

  fifo_wr_en <= saqCtrlOutValid;
  fifo_din   <= emtpy_bits & saqCtrlDataOut;

  -- mux the read enable flag based on register transaction
  with saqEnable select fifo_rd_en <=
    saqReadEn    when '0',
    saq_fifo_ren when others;

   ---------------------------------------------------
   -- FIFO
   ---------------------------------------------------
   -- FIFO data which is fill fromed FSM and sent as
   -- output to the register config in regmap
  SAQFifo_U : entity work.fifo_generator_0
  port map(
    clk    => clk,
    rst    => rst,
    din    => fifo_din,
    wr_en  => fifo_wr_en,
    rd_en  => fifo_rd_en,
    dout   => fifo_dout,
    -- status signals
    valid  => fifo_valid,
    empty  => fifo_empty,
    full   => fifo_full
   );

   ---------------------------------------------------
   -- AXI-Stream Logic connect FIFO
   ---------------------------------------------------
   -- output of this fifo should configurably connect to PS
   -- this should allow independent broadcasting of SAQ resets
   -- this implementation is inspired from AxiLiteSlaveSimple.vhd
  AXIS_SAQFifo_U : entity work.SAQAxiFifo
  port map(
    clk => clk,

    -- Fifo Connections
    fifo_dout  => fifo_dout,
    fifo_wr_en => fifo_wr_en,
    saq_fifo_ren => saq_fifo_ren,
    fifo_valid => fifo_valid,
    fifo_empty => fifo_empty,
    fifo_full  => fifo_full,

    -- register connections
    saqEnable       => saqEnable,
    saqForce        => saqForce,
    saqPacketLength => saqPacketLength,

    -- direct AXI Data Fifo Connections
    -- AXI IO
    S_AXI_0_tdata   => S_AXI_0_tdata,
    S_AXI_0_tready  => S_AXI_0_tready,
    S_AXI_0_tlast   => S_AXI_0_tlast,
    S_AXI_0_tvalid  => S_AXI_0_tvalid

   );


end architecture Behavioral;
