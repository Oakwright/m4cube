# m4 and generic imports
import board
import gc
import digitalio
import neopixel
import busio
import analogio
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import asyncio
import time
# generic display imports
import displayio
import adafruit_displayio_sh1107
import adafruit_bme680
import keypad
import DisplayTable
from secrets import secrets
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import fire_leds
import rainbowio
import audioio
import audiocore
from audiocore import RawSample
import array
import math
import adafruit_lis3dh


# clear anything leftover from previous runs
displayio.release_displays()

TEXT_URL = "https://oakwright.gay"

# Feeds #

gas_feed = secrets["aio_username"] + "/feeds/bme688.gas"
hum_feed = secrets["aio_username"] + "/feeds/bme688.hum"
tmp_feed = secrets["aio_username"] + "/feeds/bme688.tmp"
prs_feed = secrets["aio_username"] + "/feeds/bme688.prs"
controller_feed = secrets["aio_username"] + "/feeds/controller.controller"


# m4 feather express specific functions
def setup_neo_pixel():
    m4pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=1,
                                auto_write=False)
    m4pixel.fill((0, 0, 0))
    m4pixel.show()
    return m4pixel


def get_voltage(pin):
    return (pin.value * 3.3) / 65536 * 2


def getdisplayscreen(inner_display_bus):
    width = 128
    height = 64
    return adafruit_displayio_sh1107.SH1107(
        inner_display_bus, width=width, height=height, rotation=180
    )


def setup_wifi(spi):
    esp32_cs = DigitalInOut(board.D13)
    esp32_ready = DigitalInOut(board.D11)
    esp32_reset = DigitalInOut(board.D12)

    inner_esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

    # if inner_esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    #     print("ESP32 found and in idle mode")
    # print("Firmware vers.", inner_esp.firmware_version)
    # print("MAC addr:", [hex(i) for i in inner_esp.MAC_address])

    # for ap in inner_esp.scan_networks():
    #     print("\t%s\t\tRSSI: %d" % (str(ap['ssid'], 'utf-8'), ap['rssi']))

    return inner_esp


# Define callback methods which are called when events occur
# pylint: disable=unused-argument, redefined-outer-name
def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to Adafruit IO!")
    # Subscribe to all changes on the onoff_feed.
    client.subscribe(controller_feed)


def disconnected(client, userdata, rc):
    # This method is called when the client is disconnected
    print("Disconnected from Adafruit IO!")


def message(client, topic, inner_message):
    # This method is called when a topic the client is subscribed to
    # has a new message.
    print("New message on topic {0}: {1}".format(topic, inner_message))


# initialize global m4 feather express objects
pixel: neopixel.NeoPixel = setup_neo_pixel()

spibus = busio.SPI(board.SCK, board.MOSI, board.MISO)
i2cbus = None
try:
    i2cbus = busio.I2C(board.SCL, board.SDA)
except RuntimeError:
    print("I2C not initialized")

# figure out what's plugged in
displayscreen = None
display_bus = None
BME688_PLUGGED_IN = False
PROP_PLUGGED_IN = False
if i2cbus:
    while not i2cbus.try_lock():
        time.sleep(0)
    try:
        print(
            "I2C addresses found:",
            [hex(device_address) for device_address in i2cbus.scan()],
        )
        i2c_device_addresses = i2cbus.scan()

        if int('0x3c') in i2c_device_addresses:
            print("OLED found")
            display_bus = displayio.I2CDisplay(i2cbus, device_address=0x3C)
        else:
            print("No OLED detected")
        if int('0x77') in i2c_device_addresses:
            print("BME 688 found")
            BME688_PLUGGED_IN = True
        else:
            print("No BME688 found")
        if int('0x18') in i2c_device_addresses:
            print("Prop Maker found")
            PROP_PLUGGED_IN = True
        else:
            print("No Prop Maker found")

    finally:  # unlock the i2c bus when ctrl-c'ing out of the loop
        i2cbus.unlock()

bme680 = None
temperature_offset = -4
if BME688_PLUGGED_IN:
    bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2cbus)

    bme680.seaLevelhPa = 1029.2
    temperature_offset = -4

    print("\nTemperature: %0.1f C" % (bme680.temperature + temperature_offset))
    print("Gas: %d ohm" % bme680.gas)
    print("Humidity: %0.1f %%" % bme680.relative_humidity)
    print("Pressure: %0.3f hPa" % bme680.pressure)
    print("Altitude = %0.2f meters" % bme680.altitude)

if display_bus:
    displayscreen = getdisplayscreen(display_bus)
    table = DisplayTable.DisplayTable(displayscreen)

    batterypin = analogio.AnalogIn(board.VOLTAGE_MONITOR)
    voltage_text, voltage_bar = table.add_line(
        "Bat: %0.3f volts" % get_voltage(batterypin), 2, 6, get_voltage(batterypin))

    start_mem = gc.mem_free()
    memory_text, memory_bar = table.add_line("Mem: %0i bytes" % start_mem, 0,
                                             start_mem * 1.5, start_mem)

    if bme680:
        temperature_text, temperature_bar = table.add_line("Tmp:", -40, 85, 0)
        gas_text, gas_bar = table.add_line("Gas:", 0, 20000, 0)
        humidity_text, humidity_bar = table.add_line("Hum:", 0, 100, 0)
        pressure_text, pressure_bar = table.add_line("Prs:", 900, 1200, 900)

# initialize global wifi object from airlift featherwing
WIFI_PLUGGED_IN = False
mqtt_client = None
try:
    esp = setup_wifi(spibus)
    wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets, pixel)
    MQTT.set_socket(socket, esp)
    # Set up a MiniMQTT Client
    mqtt_client = MQTT.MQTT(
        broker="io.adafruit.com",
        username=secrets["aio_username"],
        password=secrets["aio_key"],
    )
    # Setup the callback methods above
    mqtt_client.on_connect = connected
    mqtt_client.on_disconnect = disconnected
    mqtt_client.on_message = message
    # Connect the client to the MQTT broker.
    # try:
    #     esp.connect(secrets)
    #     mqtt_client.connect()
    # except OSError as error:
    #     print("Failed to connect, try again later")
except TimeoutError:
    pass

prop_high_power_enable = digitalio.DigitalInOut(board.D10)
prop_high_power_enable.direction = digitalio.Direction.OUTPUT
prop_high_power_enable.value = True

if PROP_PLUGGED_IN:
    int1 = digitalio.DigitalInOut(board.D6)
    accel = adafruit_lis3dh.LIS3DH_I2C(i2cbus, int1=int1)
    accel.range = adafruit_lis3dh.RANGE_4_G
    accel.set_tap(1, 100)


async def update_neopixel_strip(num_pixels, interval, triplet):
    animated_leds = None
    # fire_color = 0xff5500
    if PROP_PLUGGED_IN:
        # num_pixels = 30  # NeoPixel strip length (in pixels)

        # fire_color = 0xff5500
        fire_fade = (-2, -2, -2)  # how much to fade R,G,B each udpate
        strip = neopixel.NeoPixel(board.D5, num_pixels, brightness=.1)
        animated_leds = fire_leds.FireLEDs(leds=strip, fade_by=fire_fade, update_rate=.01, fire_rate=.2)

    while PROP_PLUGGED_IN:
        # for i in range(255):
        #    print(triplet[2])
        #    strip.fill(triplet)
        #    strip[k] = colorwheel(i)
        animated_leds.update(rainbowio.colorwheel(time.monotonic()*40), 3)  # rainbow fire
        # animated_leds.update(fire_color, 3)  # standard fire effect
        animated_leds.show()
        await asyncio.sleep(interval)


async def play_sound():
    print("Playing sound")
    wav_file_name = "StreetChicken.wav"
    wave_file = open(wav_file_name, "rb")
    wave = audiocore.WaveFile(wave_file)
    with audioio.AudioOut(board.A0) as audio:
        audio.play(wave)
        while audio.playing:
            await asyncio.sleep(30)
            pass


async def manage_screen_buttons():
    keys = None
    key_labels = None
    if display_bus:
        key_pins = (
            board.D9,
            # board.D6,
            # board.D5
        )
        key_labels = (
            "A",
            # "B",
            # "C",
        )

        keys = keypad.Keys(key_pins, value_when_pressed=False, pull=True)
    while display_bus:

        event = keys.events.get()
        # event will be None if nothing has happened.
        if event:
            key_number = event.key_number
            # A key transition occurred.
            if event.pressed:
                print(key_labels[key_number])
                if key_labels[key_number] == 'A':
                    print("pressed A")
                    await play_sound()
                    # pixel.fill((5, 1, 15))
                    # pixel.show()
                if key_number == 1:
                    pass
                    # pixel.fill((5, 13, 13))
                    # pixel.show()

            if event.released:
                print(key_labels[key_number])
                if key_labels[key_number] == 'A':
                    print("released A")
                    # play_sound()
                # pixel.fill((0, 0, 0))
                # pixel.show()
        else:
            await asyncio.sleep(0)


async def poll_battery(interval):
    while display_bus:
        vbat_voltage = get_voltage(batterypin)
        voltage_text.text = "Bat: %0.3f volts" % vbat_voltage
        voltage_bar.value = vbat_voltage
        await asyncio.sleep(interval)


async def poll_mem(interval):
    while display_bus:
        gc.collect()
        end_mem = gc.mem_free()
        memory_text.text = "Mem: %0i bytes" % end_mem
        memory_bar.value = end_mem
        await asyncio.sleep(interval)


async def poll_bme(interval):
    while bme680:
        celsius = bme680.temperature + temperature_offset
        temperature_text.text = "Tmp: %0.1fC %0.1fF" % (celsius, (celsius * 1.8) + 32)
        temperature_bar.value = celsius
        await asyncio.sleep(interval / 4)

        gas = bme680.gas
        gas_text.text = "Gas: %d ohm" % gas
        gas_bar.value = gas
        await asyncio.sleep(interval / 4)

        humidity = bme680.relative_humidity
        humidity_text.text = "Hum: %0.1f %%" % humidity
        humidity_bar.value = humidity
        await asyncio.sleep(interval / 4)

        pressure = bme680.pressure
        pressure_text.text = "Prs: %0.3f hPa" % pressure
        pressure_bar.value = pressure
        await asyncio.sleep(interval / 4)


def attempt_send_mqtt(feed, value):
    prop_high_power_enable.value = False
    print(esp.is_connected, mqtt_client.is_connected())
    if not esp.is_connected:
        print("Reconnecting to WiFi...")
        try:
            esp.connect(secrets)
            if mqtt_client.is_connected():
                mqtt_client.disconnect()
            mqtt_client.connect()
        except OSError as inner_error:
            print("Failed to connect, try again later")
    if esp.is_connected and mqtt_client.is_connected():
        print("Sending %s to %s" % (value, feed))
        mqtt_client.publish(feed, value)
    prop_high_power_enable.value = True


async def mqtt_loop(interval):
    while mqtt_client and bme680:
        await asyncio.sleep(interval)
        attempt_send_mqtt(gas_feed, bme680.gas)
        await asyncio.sleep(interval)
        attempt_send_mqtt(hum_feed, bme680.relative_humidity)
        await asyncio.sleep(interval)
        attempt_send_mqtt(tmp_feed, bme680.temperature + temperature_offset)
        await asyncio.sleep(interval)
        attempt_send_mqtt(prs_feed, bme680.pressure)


async def update_accelerometer(interval):
    while True:
        # x, y, z = accel.acceleration
        x, y, z = [
            value / adafruit_lis3dh.STANDARD_GRAVITY for value in accel.acceleration
        ]
        # print(x, y, z)
        time.sleep(0.1)
        table.move_dot(x, y, z)
        if accel.tapped:
            print("Tapped!")
            # table.add_dot(30, 30)
        if accel.shake(shake_threshold=15):
            print("Shaken!")
        await asyncio.sleep(interval)


async def main():
    triplet = [255, 0, 255]
    button_task = asyncio.create_task(manage_screen_buttons())
    battery_task = asyncio.create_task(poll_battery(1))
    memory_task = asyncio.create_task(poll_mem(1))
    bme_task = asyncio.create_task(poll_bme(10))
    mqtt_task = asyncio.create_task(mqtt_loop(60))
    neo_task = asyncio.create_task(update_neopixel_strip(27, 0, triplet))
    accel_task = asyncio.create_task(update_accelerometer(0))

    gc.collect()

    while True:
        await asyncio.gather(button_task, memory_task, battery_task, bme_task, mqtt_task, neo_task, accel_task)


gc.collect()
asyncio.run(main())
