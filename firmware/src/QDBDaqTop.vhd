library IEEE;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_unsigned.all;

library work;
use work.QpixPkg.all;
use work.QpixProtoPkg.all;

library UNISIM;
use UNISIM.VComponents.all;

entity QDBDaqTop is
   generic (
   BOARD_G   : string  := "ZYBO";       -- ZYBO, MINIZED
   TXRX_TYPE : string  := "ENDEAVOR";   -- "DUMMY"/"UART"/"ENDEAVOR"
   X_NUM_G   : natural := 3;
   Y_NUM_G   : natural := 3
);
port (    
   sysClk    : in std_logic;
   led       : out std_logic_vector(3 downto 0);
   sw        : in std_logic_vector(3 downto 0);

   -- led_5
   led5_r : out std_logic;
   led5_b : out std_logic;
   led5_g : out std_logic;

   -- led_6
   led6_r : out std_logic;
   led6_b : out std_logic;
   led6_g : out std_logic;

   -- I/O ports
   je    : out STD_LOGIC_VECTOR(3 downto 0);
   DaqTx : out STD_LOGIC;
   DaqRx : in  STD_LOGIC;
   -- SAQ I/O
   jd : in std_logic_vector(7 downto 0);
   jc : in std_logic_vector(7 downto 0);
--   Saq : in STD_LOGIC;

   -- PS ports
   DDR_addr          : inout STD_LOGIC_VECTOR (14 downto 0);
   DDR_ba            : inout STD_LOGIC_VECTOR (2 downto 0);
   DDR_cas_n         : inout STD_LOGIC;
   DDR_ck_n          : inout STD_LOGIC;
   DDR_ck_p          : inout STD_LOGIC;
   DDR_cke           : inout STD_LOGIC;
   DDR_cs_n          : inout STD_LOGIC;
   DDR_dm            : inout STD_LOGIC_VECTOR (3 downto 0);
   DDR_dq            : inout STD_LOGIC_VECTOR (31 downto 0);
   DDR_dqs_n         : inout STD_LOGIC_VECTOR (3 downto 0);
   DDR_dqs_p         : inout STD_LOGIC_VECTOR (3 downto 0);
   DDR_odt           : inout STD_LOGIC;
   DDR_ras_n         : inout STD_LOGIC;
   DDR_reset_n       : inout STD_LOGIC;
   DDR_we_n          : inout STD_LOGIC;
   FIXED_IO_ddr_vrn  : inout STD_LOGIC;
   FIXED_IO_ddr_vrp  : inout STD_LOGIC;
   FIXED_IO_mio      : inout STD_LOGIC_VECTOR (53 downto 0);
   FIXED_IO_ps_clk   : inout STD_LOGIC;
   FIXED_IO_ps_porb  : inout STD_LOGIC;
   FIXED_IO_ps_srstb : inout STD_LOGIC
);
end QDBDaqTop;

architecture Behavioral of QDBDaqTop is

   signal fclk : std_logic;
   signal clk  : std_logic := '0';
   signal clk_12Mhz : std_logic := '0';
   signal rst  : std_logic := '0';

    -- ps-pl axi
   signal axi_resetn  : std_logic_vector(0 downto 0) := (others => '1');
   signal axi_awaddr  : std_logic_vector (31 downto 0);
   signal axi_awprot  : std_logic_vector (2 downto 0);
   signal axi_awvalid : std_logic_vector(0 downto 0);
   signal axi_awready : std_logic_vector(0 downto 0);
   signal axi_wdata   : std_logic_vector (31 downto 0);
   signal axi_wstrb   : std_logic_vector (3 downto 0);
   signal axi_wvalid  : std_logic_vector(0 downto 0);
   signal axi_wready  : std_logic_vector(0 downto 0);
   signal axi_bresp   : std_logic_vector (1 downto 0);
   signal axi_bvalid  : std_logic_vector(0 downto 0);
   signal axi_bready  : std_logic_vector(0 downto 0);
   signal axi_araddr  : std_logic_vector (31 downto 0);
   signal axi_arprot  : std_logic_vector (2 downto 0);
   signal axi_arvalid : std_logic_vector(0 downto 0);
   signal axi_arready : std_logic_vector(0 downto 0);
   signal axi_rdata   : std_logic_vector (31 downto 0);
   signal axi_rresp   : std_logic_vector (1 downto 0);
   signal axi_rvalid  : std_logic_vector(0 downto 0);
   signal axi_rready  : std_logic_vector(0 downto 0);
   
   -- Register signals
   signal reg_addr    : std_logic_vector (31 downto 0);
   signal reg_rdata   : std_logic_vector (31 downto 0);
   signal reg_wdata   : std_logic_vector (31 downto 0);
   signal reg_req     : std_logic := '0';
   signal reg_wen     : std_logic := '0';
   signal reg_ack     : std_logic := '0';

   -- ps axi4-stream data fifo
   signal S_AXI_0_tlast   : STD_LOGIC;
   signal S_AXI_0_tdata  : STD_LOGIC_VECTOR (31 downto 0);
   signal S_AXI_0_tready : STD_LOGIC;
   signal S_AXI_0_tvalid : STD_LOGIC;

   -- signal inPortsArr  : QpixInPortsArrType(0 to X_NUM_G-1, 0 to Y_NUM_G-1);
   signal hitMask     : Sl2DArray ;

   signal trg         : std_logic                                      := '0';
   signal asicAddr    : std_logic_vector(31 downto 0)                  := (others => '0');
   signal asicOpWrite : std_logic                                      := '0';
   signal asicData    : std_logic_vector(15 downto 0);
   signal asicReq     : std_logic                                      := '0';
   --signal hitXY       : std_logic_vector (31 downto 0) := (others => '0');
   signal timestamp   : std_logic_vector (G_TIMESTAMP_BITS-1 downto 0) := (others => '0');
   signal chanMask    : std_logic_vector (G_N_ANALOG_CHAN-1 downto 0)  := (others => '0');
   signal trgTime     : std_logic_vector (31 downto 0)                 := (others => '0');
   signal evtSize     : std_logic_vector (31 downto 0)                 := (others => '0');

   signal memAddrRst  : std_logic := '0';
   signal memRdAddr   : std_logic_vector (G_QPIX_PROTO_MEM_DEPTH-1+2 downto 0) := (others => '0');
   signal memDataOut  : std_logic_vector (31 downto 0) := (others => '0');
   signal memRdAck    : std_logic := '0';
   signal memRdReq    : std_logic := '0';
   signal memEvtSize  : std_logic_vector (G_QPIX_PROTO_MEM_DEPTH-1 downto 0) := (others => '0');

   signal qpixDebugArr   : QpixDebug2DArrayType(0 to X_NUM_G-1, 0 to Y_NUM_G-1);
   signal extFifoMaxArr  : Slv4b2DArray;
   signal status         : std_logic_vector(31 downto 0)  := (others => '0');
   signal asic_mask      : std_logic_vector (15 downto 0);
   signal daqFrameErrCnt : std_logic_vector (31 downto 0) := (others => '0');
   signal daqBreakErrCnt : std_logic_vector (31 downto 0) := (others => '0');
   
   signal counter_led  : std_logic                    := '0';
   signal leds         : std_logic_vector(3 downto 0) := (others => '0');
   -- buffer daqTx / daqRx
   signal s_daqTx      : std_logic                    := '0';
   signal s_daqRx      : std_logic                    := '0';
   signal pulse_red    : std_logic                    := '0';
   signal pulse_blu    : std_logic                    := '0';
   signal pulse_gre    : std_logic                    := '0';
   constant pulse_time : integer                      := 2_999_999;  -- fclk_freq / pulse_time = pulse's width

   -- SAQ signals / Constants
   constant N_SAQ_PORTS    : natural   := 16;
   constant TIMESTAMP_BITS : natural   := 32;
   signal saqMask          : std_logic_vector(N_SAQ_PORTS - 1 downto 0);
   signal saqPacketLength  : std_logic_vector(31 downto 0);
   signal saqEnable        : std_logic := '0';
   signal saqForce         : std_logic := '0';
   signal saqPortData      : std_logic_vector(N_SAQ_PORTS - 1 downto 0);
   signal saq_fifo_data    : std_logic_vector(63 downto 0);
   signal saq_fifo_valid   : std_logic := '0';
   signal saq_fifo_empty   : std_logic := '0';
   signal saq_fifo_full    : std_logic := '0';
   signal saq_fifo_ren     : std_logic := '0';
   signal saq_fifo_hits    : std_logic_vector(31 downto 0);
   signal pulse_red6    : std_logic                    := '0';
   signal pulse_blu6    : std_logic                    := '0';
   signal pulse_gre6    : std_logic                    := '0';


   -- pulse LED procedure
   procedure pulseLED(variable flag : in boolean;
                      variable start_pulse : inout std_logic;
                      variable count_pulse : inout integer;
                      signal output : out std_logic) is
      begin
         if flag then
             start_pulse := '1';
             count_pulse := 0;
         end if;
         if start_pulse = '1' then
             count_pulse := count_pulse + 1;
             output <= '1';
             if count_pulse >= pulse_time then
                 output      <= '0';
                 count_pulse := 0;
                 start_pulse := '0';
             end if;
         end if;
      end procedure pulseLED;


begin

    -- connect the switches to the LEDs
    -- led <= sw;
    je <= sw;
    -- je(1) <= sw(1); -- direct pin or switch 
    DaqTx <= s_daqTx;
    s_daqRx <= DaqRx;   
    assgn: for i in 0 to 3 generate
        led(i) <= sw(i) and counter_led;
    end generate;
   -- LED-5, active high
   led5_r <= pulse_red;
   led5_b <= pulse_blu;
   led5_g <= pulse_gre;

   led6_r <= pulse_red6;
   led6_b <= pulse_blu6;
   led6_g <= pulse_gre6;
   
--   saq_assn: for i in 3 downto 0 generate
--    IBUFDS_inst : IBUFDS
--    port map (
--        O => saqPortData(i),   -- 1-bit output: Buffer output
--        I => jbp(i),   -- 1-bit input: Diff_p buffer input (connect directly to top-level port)
--        IB => jbn(i)  -- 1-bit input: Diff_n buffer input (connect directly to top-level port)
--    );
--    end generate;
--    saqPortData(N_SAQ_PORTS - 1 downto 1) <= "00000000000000"; 
--    saqPortData(0) <= Saq;
   saqPortData <= jd & jc;
    
    
    counter: process(fclk, rst) is
        constant count : natural := 12000000;
        variable hz : natural range 0 to count := 0;
    begin
        if rising_edge(fclk) then
            hz := hz + 1;
            if hz >= count - 1 then
                hz := 0;
                counter_led <= not counter_led;
            end if;
        end if; 
    end process counter;

   ---------------------------------------------------
   -- 125 MHz clock
   ---------------------------------------------------
   --bufg_u : BUFG 
      --port map ( I => sysClk, O => clk);
   --clk <= fclk;
   ---------------------------------------------------

   ---------------------------------------------------
   -- Processing system
   ---------------------------------------------------
   design_1_U : entity work.design_1_wrapper
         port map (
            -- PS ports
            DDR_addr(14 downto 0)     => DDR_addr(14 downto 0),
            DDR_ba(2 downto 0)        => DDR_ba(2 downto 0),
            DDR_cas_n                 => DDR_cas_n,
            DDR_ck_n                  => DDR_ck_n,
            DDR_ck_p                  => DDR_ck_p,
            DDR_cke                   => DDR_cke,
            DDR_cs_n                  => DDR_cs_n,
            DDR_dm(3 downto 0)        => DDR_dm(3 downto 0),
            DDR_dq(31 downto 0)       => DDR_dq(31 downto 0),
            DDR_dqs_n(3 downto 0)     => DDR_dqs_n(3 downto 0),
            DDR_dqs_p(3 downto 0)     => DDR_dqs_p(3 downto 0),
            DDR_odt                   => DDR_odt,
            DDR_ras_n                 => DDR_ras_n,
            DDR_reset_n               => DDR_reset_n,
            DDR_we_n                  => DDR_we_n,
            FIXED_IO_ddr_vrn          => FIXED_IO_ddr_vrn,
            FIXED_IO_ddr_vrp          => FIXED_IO_ddr_vrp,
            FIXED_IO_mio(53 downto 0) => FIXED_IO_mio(53 downto 0),
            FIXED_IO_ps_clk           => FIXED_IO_ps_clk,
            FIXED_IO_ps_porb          => FIXED_IO_ps_porb,
            FIXED_IO_ps_srstb         => FIXED_IO_ps_srstb,

            reset_rtl                 => '0',
            -- axi interface to PL
            M_AXI_0_awaddr            => axi_awaddr,
            M_AXI_0_awprot            => axi_awprot, 
            M_AXI_0_awvalid           => axi_awvalid,
            M_AXI_0_awready           => axi_awready,
            M_AXI_0_wdata             => axi_wdata,  
            M_AXI_0_wstrb             => axi_wstrb,  
            M_AXI_0_wvalid            => axi_wvalid, 
            M_AXI_0_wready            => axi_wready, 
            M_AXI_0_bresp             => axi_bresp,  
            M_AXI_0_bvalid            => axi_bvalid, 
            M_AXI_0_bready            => axi_bready, 
            M_AXI_0_araddr            => axi_araddr, 
            M_AXI_0_arprot            => axi_arprot, 
            M_AXI_0_arvalid           => axi_arvalid,
            M_AXI_0_arready           => axi_arready,
            M_AXI_0_rdata             => axi_rdata,  
            M_AXI_0_rresp             => axi_rresp,  
            M_AXI_0_rvalid            => axi_rvalid, 
            M_AXI_0_rready            => axi_rready, 

            -- data fifo interface for SAQ
            S_AXIS_0_tdata   => S_AXI_0_tdata,
            S_AXIS_0_tready  => S_AXI_0_tready,
            S_AXIS_0_tlast   => S_AXI_0_tlast,
            S_AXIS_0_tvalid  => S_AXI_0_tvalid,
            S_AXIS_0_tkeep   => "1111",

            -- clk + rst
            aresetn                   => axi_resetn,
            fclk                      => fclk, 

            -- CLK Wizard
            reset_rtl_0               => '0',
            sys_clock                 => sysClk,
            clk_out1_0                => clk,
            clk_out2_0                => clk_12Mhz,
            locked_0                  => open
         );


   ---------------------------------------------------
   -- AXI Lite interface
   ---------------------------------------------------
   AxiLiteSlaveSimple_U : entity work.AxiLiteSlaveSimple
      port map(
         axi_aclk              => fclk,
         axi_aresetn           => axi_resetn(0),

         axi_awaddr            => axi_awaddr,
         axi_awprot            => axi_awprot, 
         axi_awvalid           => axi_awvalid(0),
         axi_awready           => axi_awready(0),
         axi_wdata             => axi_wdata,  
         axi_wstrb             => axi_wstrb,  
         axi_wvalid            => axi_wvalid(0),
         axi_wready            => axi_wready(0),
         axi_bresp             => axi_bresp,  
         axi_bvalid            => axi_bvalid(0),
         axi_bready            => axi_bready(0),
         axi_araddr            => axi_araddr, 
         axi_arprot            => axi_arprot, 
         axi_arvalid           => axi_arvalid(0),
         axi_arready           => axi_arready(0),
         axi_rdata             => axi_rdata,  
         axi_rresp             => axi_rresp,  
         axi_rvalid            => axi_rvalid(0),
         axi_rready            => axi_rready(0),

         addr                  => reg_addr, 
         rdata                 => reg_rdata,
         wdata                 => reg_wdata,
         req                   => reg_req,
         wen                   => reg_wen,
         ack                   => reg_ack
      );

   ---------------------------------------------------
   ---------------------------------------------------
   QpixProtoRegMap_U : entity work.QpixProtoRegMap
   generic map (
      X_NUM_G        => X_NUM_G,
      Y_NUM_G        => Y_NUM_G,
      Version        => x"0000_000b",
      N_SAQ_PORTS    => N_SAQ_PORTS,
      TIMESTAMP_BITS => TIMESTAMP_BITS
   )
   port map(
      clk          => fclk,
      -- clk          => clk_12Mhz,
      rst          => rst,
                   
      addr         => reg_addr,
      rdata        => reg_rdata,
      wdata        => reg_wdata,
      req          => reg_req,
      wen          => reg_wen,
      ack          => reg_ack,

      asic_mask    => asic_mask,

      evtSize      => evtSize,
      status       => status,
      extFifoMax   => extFifoMaxArr,

      daqFrameErrCnt => daqFrameErrCnt,
      daqBreakErrCnt => daqBreakErrCnt,

      trgTime      => trgTime,
      timestamp    => timestamp,
      hitMask      => hitMask,
      chanMask     => chanMask,
                  
      trg          => trg,
      asicAddr     => asicAddr,
      asicOpWrite  => asicOpWrite,
      asicData     => asicData,
      asicReq      => asicReq,

      memRdReq     => memRdReq,
      memRdAck     => memRdAck,
      memData      => memDataOut,
      memAddr      => memRdAddr,

      -- SAQ Node interactions
      saqMask         => saqMask,
      saqPacketLength => saqPacketLength,
      saqEnable       => saqEnable,
      saqForce        => saqForce,
      saq_fifo_hits   => saq_fifo_hits,
      saq_fifo_valid  => saq_fifo_valid,
      saq_fifo_full   => saq_fifo_full,
      saq_fifo_empty  => saq_fifo_empty,
      saq_fifo_ren    => saq_fifo_ren,
      saq_fifo_data   => saq_fifo_data
   );

   ---------------------------------------------------
   -- DAQ node
   ---------------------------------------------------
   QpixDaqCtrl_U : entity work.QpixDaqCtrl
   generic map(
      TXRX_TYPE  => TXRX_TYPE,
      MEM_DEPTH  => G_QPIX_PROTO_MEM_DEPTH
   )
   port map(
      clk         => fclk,
      rst         => rst,
                  
      daqTx       => s_daqTx,
      daqRx       => s_daqRx,

      trg         => trg,
      asicReq     => asicReq,
      asicOpWrite => asicOpWrite,
      asicData    => asicData,
      asicAddr    => asicAddr,

      trgTime     => trgTime,
      evt_fin     => status(0),

      uartFrameCnt => daqFrameErrCnt,
      uartBreakCnt => daqBreakErrCnt,

      -- event memory ports
      memAddrRst  => memAddrRst,
      memRdAddr   => memRdAddr,
      memDataOut  => memDataOut, 
      memRdReq    => memRdReq,
      memRdAck    => memRdAck,
      memEvtSize  => evtSize,
      memFullErr  => open);
      
   memAddrRst <= trg or asicReq;

   ---------------------------------------------------
   -- SAQ node
   ---------------------------------------------------
  SAQNode_U : entity work.SAQNode
   generic map(
   N_SAQ_PORTS    => N_SAQ_PORTS,
   TIMESTAMP_BITS => TIMESTAMP_BITS)
   port map(
      clk         => fclk,
      rst         => rst,
      saqPortData => saqPortData,
      saqReadEn   => saq_fifo_ren,
      saqDataOut  => saq_fifo_data,

      -- AXI IO
      S_AXI_0_tdata   => S_AXI_0_tdata,
      S_AXI_0_tready  => S_AXI_0_tready,
      S_AXI_0_tlast   => S_AXI_0_tlast,
      S_AXI_0_tvalid  => S_AXI_0_tvalid,

      -- Register Pins
      valid           => saq_fifo_valid,
      empty           => saq_fifo_empty,
      full            => saq_fifo_full,
      saqHits         => saq_fifo_hits,
      saqMask         => saqMask,
      saqPacketLength => saqPacketLength,
      saqForce        => saqForce,
      saqEnable       => saqEnable
   );
 
 pulse : process (fclk, s_daqRx, s_daqTx) is
     -- variable conditions
     variable cr5 : boolean := false;
     variable cb5 : boolean := false;
     variable cg5 : boolean := false;
     variable cr6 : boolean := false;
     variable cb6 : boolean := false;
     variable cg6 : boolean := false;
     -- led5
     variable pulse_count_red : integer range 0 to pulse_time := 0;
     variable start_pulse_red : std_logic := '0';
     variable pulse_count_blu : integer range 0 to pulse_time := 0;
     variable start_pulse_blu : std_logic := '0';
     variable pulse_count_gre : integer range 0 to pulse_time := 0;
     variable start_pulse_gre : std_logic := '0';
     -- LED6
     variable pulse_count_red6 : integer range 0 to pulse_time := 0;
     variable start_pulse_red6 : std_logic := '0';
     variable pulse_count_blu6 : integer range 0 to pulse_time := 0;
     variable start_pulse_blu6 : std_logic := '0';
     variable pulse_count_gre6 : integer range 0 to pulse_time := 0;
     variable start_pulse_gre6 : std_logic := '0';
 begin
     if rising_edge(fclk) then
     
       -- LED Flashing conditions
        cr5 := s_daqRx = '1';
        cg5 := evtSize /= x"0000_0000";
        cb5 := s_daqTx = '1';
              
        cr6 := saq_fifo_full = '1';
        cg6 := saq_fifo_empty = '1';
        cb6 := saq_fifo_valid = '1';
    
        -- proc's RGB
        pulseLED(cr5, start_pulse_red, pulse_count_red, pulse_red);
        pulseLED(cb5, start_pulse_blu, pulse_count_blu, pulse_blu);
        pulseLED(cg5, start_pulse_gre, pulse_count_gre, pulse_gre);
        -- led6 RGB
        pulseLED(cr6, start_pulse_red6, pulse_count_red6, pulse_red6);
        pulseLED(cb6, start_pulse_blu6, pulse_count_blu6, pulse_blu6);
        pulseLED(cg6, start_pulse_gre6, pulse_count_gre6, pulse_gre6);

     end if;
 end process pulse;

end Behavioral;
