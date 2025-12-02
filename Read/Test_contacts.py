import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
GPIO.setup(14, GPIO.IN)
GPIO.setup(15, GPIO.IN)

try:
    while True:
        print("LO+:", GPIO.input(14), "LO-:", GPIO.input(15))
        time.sleep(0.1)
finally:
    GPIO.cleanup()
