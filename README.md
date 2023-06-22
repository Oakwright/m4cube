## Poetry

```
poetry add circup
poetry add circuitpython-stubs
```

```shell
ls /dev/ttyACM*
```

```shell
screen /dev/ttyACM0 115200
```

if it doesn't work, may need to sudo

to exit screen: ctrl+a+d

### On Linux

```shell
sudo apt-get install libusb-1.0 libudev-dev
```

Use a text editor to create and edit the file /etc/udev/rules.d/99-mcp2221.rules and add the following contents.

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="04d8", ATTR{idProduct}=="00dd", MODE="0666"
```

```shell
sudo rmmod hid_mcp2221
```

```shell
sudo update-initramfs -u
```

```shell
export BLINKA_MCP2221=1
```