import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
GPIO.setup(23, GPIO.IN)
GPIO.setup(24, GPIO.IN)

try:
    while True:
        print("LO+:", GPIO.input(23), "LO-:", GPIO.input(24))
        time.sleep(0.1)
finally:
    GPIO.cleanup()
