import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 1
chan = AnalogIn(ads, 2)

while True:
    print(f"Raw: {chan.value} | Voltage: {chan.voltage:.4f}V")
    time.sleep(0.1)  # slower to avoid I2C glitches

