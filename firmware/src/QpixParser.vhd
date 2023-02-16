---------------------------------------------------------------------------------
-- QPix data parser
----------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.std_logic_misc.all;

use work.QpixPkg.all;


entity QpixParser is
   port (
      clk                 : in std_logic;
      rst                 : in std_logic;
      fifoFull            : in std_logic;
      
      -- input data from ASICs / output data to route
      inBytesArr          : in  QpixByteArrType; -- array(3 downto 0) of slv(63 downto 0)
      inBytesValid        : in  std_logic_vector(3 downto 0); 
      inBytesAck          : out std_logic_vector(3 downto 0);
      parseDataTx         : out QpixDataFormatType;
      
      -- input from QpixRoute, to send to ASIC
      parseDataRx         : in  QpixDataFormatType;
      outBytesArr         : out QpixByteArrType; -- array(3 downto 0) of slv(63 downto 0)
      outBytesValidArr    : out std_logic_vector(3 downto 0);
      txReady             : in  std_logic;

      -- RefFile configuration
      qpixConf            : in QpixConfigType;

      -- Comm communication register data
      regData             : out QpixRegDataType;
      regResp             : in QpixRegDataType
   );
end entity QpixParser;


architecture behav of QpixParser is

   signal regDataR         : QpixRegDataType    := QpixRegDataZero_C;
   signal inDataR          : QpixDataFormatType := QpixDataZero_C;

   signal thisReqID        : std_logic_vector(regDataR.ReqID'range) := (others => '0');

   signal inBytesMux       : std_logic_vector(G_DATA_BITS+1 downto 0) := (others => '0'); -- two LSB for Rx line index
   signal inBytesMuxValidOr : std_logic                    := '0';
   signal inBytesMuxValid  : std_logic_vector(3 downto 0) := (others => '0');
   signal inBytesMuxValidR : std_logic_vector(3 downto 0) := (others => '0');

   signal regDirResp       : std_logic_vector(3 downto 0) := (others => '0');
   signal fifoRen          : std_logic_vector(3 downto 0) := (others => '0');

   signal RxDisable        : std_logic_vector(3 downto 0) := (others => '0');



begin

   ----------------------------
   -- mux for input channels --
   ----------------------------
   process (clk)
      variable imux : natural := 0;
   begin
      if rising_edge (clk) then

         inBytesMuxValidR <= inBytesMuxValid;

         inBytesMuxValid   <= (others => '0');
         inBytesMuxValidOr <= '0';
         fifoRen          <= (others => '0');
         for i in 0 to 3 loop
            ------- Rewrite this entire block!!!! FIXME
            if inBytesValid(i) = '1' and fifoRen = b"0000" then
               inBytesMux          <= std_logic_vector(to_unsigned(i,2)) & inBytesArr(i);
               inBytesMuxValid     <= (others => '0');
               inBytesMuxValid(i)  <= '1';
               inBytesMuxValidOr   <= '1';
               fifoRen <= (others => '0');
               fifoRen(i)   <= '1';
            end if;
         end loop;
         
      end if;
   end process;
   ------------------------------------------------------------

   inBytesAck <= fifoRen;

   regDirResp <= qpixConf.DirMask; 

   process (clk)
      variable reg : QpixRegDataType := QpixRegDataZero_C;
      variable rx_ind : std_logic_vector(1 downto 0);
   begin
      if rising_edge (clk) then
         if rst = '1' then 
            inDataR  <= QpixDataZero_C;
            regDataR <= QpixRegDataZero_C;
            thisReqID <= (others => '0');
            RxDisable <= (others => '0');
         else
            inDataR.DataValid <= '0';
            regDataR.Valid <= '0';
            RxDisable <= qpixConf.RxDisable;

            rx_ind := inBytesMux(65 downto 64);

            if inBytesMuxValidOr = '1'  then
               if fQpixGetWordType(inBytesMux) = REGREQ_W then
                  reg         := fQpixByteToReg(inBytesMux(63 downto 0));
                  regDataR    <= reg;

                  if reg.reqID > thisReqID or (reg.reqID = x"0" and reg.reqID /= thisReqID) then
                     thisReqID       <= reg.ReqID;
                     regDataR.Valid  <= '1';
                  end if;

                  if reg.SrcDaq = '0' then
                     -- increment X-Y position depending on where the data came from
                     case rx_ind is
                        when b"00" => regDataR.YHops <= std_logic_vector(unsigned(reg.YHops) + 1); 
                        when b"01" => regDataR.XHops <= std_logic_vector(unsigned(reg.XHops) - 1); 
                        when b"10" => regDataR.YHops <= std_logic_vector(unsigned(reg.YHops) - 1); 
                        when b"11" => regDataR.XHops <= std_logic_vector(unsigned(reg.XHops) + 1); 
                        when others =>
                     end case;
                  end if;
                  regDataR.SrcDaq <= '0';

               else
                  if RxDisable(to_integer(unsigned(rx_ind))) = '0' then
                     inDataR           <= fQpixByteToRecord(inBytesMux(63 downto 0));
                     inDataR.Data      <= inBytesMux(inDataR.Data'range);
                     inDataR.DataValid <= not fifoFull;
                  end if;
               end if;
            end if;
         end if;
      end if;
   end process;

   regData <= regDataR;
   parseDataTx  <= inDataR;

   ------------------------------------------------------------
   -- TX
   ------------------------------------------------------------
         
   TX_GEN : for i in 0 to 3 generate
      process (clk)
      begin
         if rising_edge (clk) then

            outBytesValidArr(i)  <= '0';

            if parseDataRx.DataValid = '1' then
              -- construction of DirMask happens here and why it must be four bits
               if parseDataRx.DirMask(i) = '1' then
                  -- temporary send either d.Data of convert record FIXME
                  if parseDataRx.WordType = G_WORD_TYPE_REGRSP then
                     outBytesArr(i) <= parseDataRx.Data;
                  else
                     outBytesArr(i) <= fQpixRecordToByte(parseDataRx);
                  end if;
                  outBytesValidArr(i)  <= '1'; 
               end if;

            -- broadcast the register request
            elsif regDataR.Valid = '1'  then 
               outBytesArr(i)      <= fQpixRegToByte(regDataR);
               outBytesValidArr(i) <= not inBytesMuxValidR(i);

            elsif regResp.Valid = '1' and TxReady = '1' then
               outBytesArr(i)      <= fQpixRegToByte(regResp);
               outBytesValidArr(i) <= regDirResp(i);
            end if;
         end if;
      end process;
   end generate;
   ------------------------------------------------------------

end behav;
