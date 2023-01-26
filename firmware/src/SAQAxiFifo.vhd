-------------------------------------------------------------------------------
-- Title      : SAQAxiFifo
-- Project    :
-------------------------------------------------------------------------------
-- File       : SAQAxiFifo.vhd
-- Author     : Kevin Kevin  <kevinpk@hawaii.edu>
-- Company    :
-- Created    : 2022-09-08
-- Last update: 2022-09-19
-- Platform   :
-- Standard   : VHDL'93/02
-------------------------------------------------------------------------------
-- Description: connect output of FIFO, which stores SAQ fifo and convert
-- its logic into a AXI Stream master config. This file is largely inspired
-- by the write register of AxiLiteSlaveSimple.vhd
-------------------------------------------------------------------------------
-- Copyright (c) 2022
-------------------------------------------------------------------------------
-- Revisions  :
-- Date        Version  Author  Description
-- 2022-09-08  1.0      keefe	Created
-------------------------------------------------------------------------------

library IEEE;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_unsigned.all;

library work;

use work.UtilityPkg.all;

entity SAQAxiFifo is

  port (
    clk : in sl;
    -- Fifo Generator Ports
    fifo_dout    : in  slv(63 downto 0);
    fifo_wr_en   : in  sl;
    saq_fifo_ren : out sl;
    fifo_valid   : in  sl;
    fifo_empty   : in  sl;
    fifo_full    : in  sl;

    -- register connections
    saqEnable       : in sl;
    saqForce        : in sl;
    saqPacketLength : in slv(31 downto 0);

    -- AXI4-Stream Data Fifo Ports
    -- write data channel
    S_AXI_0_tdata   : out STD_LOGIC_VECTOR (31 downto 0);
    S_AXI_0_tlast   : out STD_LOGIC;
    S_AXI_0_tready  : in  STD_LOGIC;
    S_AXI_0_tvalid  : out STD_LOGIC

);

end entity SAQAxiFifo;


architecture Behavioral of SAQAxiFifo is

    -- user added
    signal axi_aresetn : std_logic;
    constant AXI_ADDR_WIDTH : integer := 32;

    signal s_fifo_ren : std_logic;
    signal uPacketLength : unsigned(31 downto 0) := (others => '0');

    -- Constants
    constant AXI_OKAY     : std_logic_vector(1 downto 0)  := "00";
    constant AXI_DECERR   : std_logic_vector(1 downto 0)  := "11";
    constant FORCE_PACKET : std_logic_vector(31 downto 0) := x"a7007e51";


    -- write data channel
    signal s_axi_tdata       : std_logic_vector(31 downto 0);
    signal s_axi_tvalid      : std_logic;
    signal s_axi_tready_r    : std_logic;
    signal s_axi_tlast_r     : std_logic;

    type t_state is (IDLE, WRITE_DATA_S, DONE_S);
    signal s_state_r    : t_state;

    -- sim view
    signal sNPackets : unsigned(31 downto 0);


begin  -- architecture Behavioral

    -- assign write output ports
    saq_fifo_ren <= s_fifo_ren;

    -- write channel IO
    S_AXI_0_tdata  <= s_axi_tdata;
    s_axi_tready_r <= S_AXI_0_tready;
    S_AXI_0_tlast  <= s_axi_tlast_r;
    S_AXI_0_tvalid <= s_axi_tvalid;

    -- keep track of the packet length
    uPacketLength <= unsigned(saqPacketLength);



    ----------------------------------------------------------------------------
    -- Write-transaction FSM
    write_fsm : process(clk, axi_aresetn, s_state_r, fifo_valid, s_axi_tready_r,
                        saqEnable, fifo_empty) is
        variable v_word_phase : std_logic;
        variable newWord      : std_logic             := '0';
        variable forceLast    : std_logic             := '0';
        variable nPackets     : unsigned(31 downto 0) := (others => '0');
    begin

        if rising_edge(clk) then
            -- Default values:
            s_fifo_ren    <= '0';
            s_axi_tvalid  <= '0';
            s_axi_tlast_r <= '0';
            sNPackets <= nPackets;

            -- an incoming force pulse should send a last when the fifo is empty
            if saqForce = '1' then
                forceLast := '1';
            end if;

            case s_state_r is

                -- Ready for FIFO write data
                -- initiated by the following conditions:
                --   * assertion of saqEnable
                --   * assertion of not fifo_empty
                when IDLE =>

                  v_word_phase := '0';

                  if fifo_empty /= '1' and saqEnable = '1' then
                    s_state_r          <= WRITE_DATA_S;
                    s_fifo_ren         <= '1';  -- update the fifo to read from 
                    newWord            := '0';
                  -- if we've received a force last with no data, still send a fake packet
                  elsif saqEnable = '1' and forceLast = '1' and s_axi_tready_r = '1' then
                    s_axi_tdata   <= x"beefcafe";
                    s_axi_tlast_r <= '1';
                    s_axi_tvalid  <= '1';
                    forceLast     := '0';
                  end if;

                -- Write data words to addr
                when WRITE_DATA_S =>

                  -- wait for the first valid word from the FIFO
                  if fifo_valid = '1' then
                    newWord := '1';
                  end if;
               
                  -- try reading until we get the newWord from the FIFO            
                  if newWord = '0' then        
                     s_fifo_ren <= '1';
                  end if;
                                 
                  -- take two clk cycles to send out the new word
                  if s_axi_tready_r = '1' and newWord = '1' then
                    s_axi_tvalid  <= '1';
                    -- write the first 32 bit word
                    if v_word_phase = '0' then
                        s_axi_tdata <= fifo_dout(31 downto 0);
                        v_word_phase := '1';
                    -- write the second 32 bit word
                    else
                        s_axi_tdata  <= fifo_dout(63 downto 32);
                        v_word_phase := '0';
                        nPackets     := nPackets + 1;

                        if nPackets >= uPacketLength then
                           s_axi_tlast_r <= '1';
                           nPackets      := (others => '0');
                        end if;
                        
                        -- if the fifo is empty, we're out of the write/read phase
                        if fifo_empty = '1' then
                            s_state_r     <= DONE_S;
                            if forceLast = '1' then
                                s_axi_tlast_r <= '1';
                                forceLast     := '0';
                                nPackets      := (others => '0');
                            end if;
                        else
                            s_fifo_ren   <= '1';  -- move to the next word in the fifo
                            newWord      := '0';
                        end if;
                    end if;
                  end if;

                -- Write transaction completed, wait for Okay FIFO Write
                when DONE_S =>

                  if s_axi_tready_r = '1' then
                    s_state_r <= IDLE;
                  end if;
                  
                when OTHERS =>
                   s_state_r <= IDLE;

            end case;


        end if;
    end process write_fsm;

    ----------------------------------------------------------------------------

end architecture Behavioral;
