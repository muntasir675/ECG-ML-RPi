import time
import board
import busio
import RPi.GPIO as GPIO
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

ALERT_PIN = 17
LO_PLUS_PIN = 14
LO_MINUS_PIN = 15
DATA_RATE = 250

GPIO.setmode(GPIO.BCM)
GPIO.setup(LO_PLUS_PIN, GPIO.IN)
GPIO.setup(LO_MINUS_PIN, GPIO.IN)
GPIO.setup(ALERT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)

chan = AnalogIn(ads, ADS.P0)

ads.i2c_device.write(bytes([0x02, 0x00, 0x00]))
ads.i2c_device.write(bytes([0x03, 0x80, 0x00]))

ads.data_rate = DATA_RATE
ads.mode = 0
_ = chan.value

print(f"Acquiring data at {DATA_RATE} SPS using hardware interrupt (GPIO {ALERT_PIN})...")

def data_ready_callback(channel):
    if GPIO.input(ALERT_PIN) == 0:
        adc_val = chan.value
        volts = chan.voltage
        
        lo_p = GPIO.input(LO_PLUS_PIN)
        lo_m = GPIO.input(LO_MINUS_PIN)
        
        print(f"LO+: {lo_p} | LO-: {lo_m} | ADC: {adc_val} ({volts:.3f}V)")

GPIO.add_event_detect(ALERT_PIN, GPIO.FALLING, callback=data_ready_callback)

try:
    while True:
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\nStopping...")

finally:
    GPIO.cleanup()
