import serial
import struct
import threading
import time
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import requests

app = Flask(__name__)
socketio = SocketIO(app)

def calculate_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 0x0001) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

class CarController:
    def __init__(self, port):
        self.port = port
        self.running = False
        self.direction = None
        self.thread = None
        self.command_queue = []
        self.lock = threading.Lock()

    def send_modbus_command(self, command):
        data_without_crc = command[:-5]
        crc = calculate_crc(bytes.fromhex(data_without_crc))
        crc_bytes = struct.pack('<H', crc)
        command_with_crc = data_without_crc + f" {crc_bytes[0]:02X} {crc_bytes[1]:02X}"

        try:
            with serial.Serial(self.port, baudrate=57600, timeout=1) as ser:
                request = bytes.fromhex(command_with_crc)
                ser.write(request)
        except (serial.SerialException, OSError) as e:
            print(f"Unable to open serial port {self.port}: {e}")

    def control_car(self):
        while self.running:
            with self.lock:
                if self.command_queue:
                    command = self.command_queue.pop(0)
                    self.send_modbus_command(command)
                    time.sleep(0.05) 

    def start(self, direction):
        with self.lock:
            if not self.running:
                self.send_modbus_command("05 44 21 00 31 00 00 01 00 01 75 34")  # 使能电机
                self.running = True
                self.thread = threading.Thread(target=self.control_car)
                self.thread.start()

            # 清空缓冲区
            self.command_queue.clear()
            command = get_command(direction)
            if command:
                self.command_queue.append(command)

    def stop(self):
        with self.lock:
            self.running = False
            if self.thread:
                self.thread.join()
            self.command_queue.clear() 
            self.send_modbus_command("05 44 21 00 31 00 00 00 00 00 E5 34")

    def disable(self):
        with self.lock:
            self.command_queue.clear()
            self.send_modbus_command("05 44 21 00 31 00 00 00 00 00 E5 34")  # 失能电机

def get_command(direction):
    commands = {
        'up': "05 44 23 18 33 18 FF 9C FF 9C 9D 38",  # 前进
        'down': "05 44 23 18 33 18 00 64 00 64 9D 38",  # 后退
        'left': "05 44 23 18 33 18 00 64 FF 9C 9D 38",  # 左转
        'right': "05 44 23 18 33 18 FF 9C 00 64 9D 38"  # 右转
    }
    return commands.get(direction)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('control')
def handle_control(data):
    direction = data.get('direction')
    if direction in ['up', 'down', 'left', 'right']:
        car_controller.start(direction)
        emit('response', {'status': 'Moving ' + direction})
    else:
        car_controller.stop()
        emit('response', {'status': 'Stopped'})

@socketio.on('disable')
def handle_disable():
    car_controller.disable() 
    emit('response', {'status': 'Disabled'})

if __name__ == "__main__":
    port_name = '/dev/ttyUSB0'  # 串口名称，根据实际情况修改
    car_controller = CarController(port_name)

    # 在启动 Flask 服务器之前，向 HTTP 服务器发送一次数据
    http_server_url = 'http://****'  # HTTP 服务器地址，根据实际情况修改
    status_data = {
        "status": "Ready",
        "message": "Car control system is ready."
    }
    try:
        response = requests.post(http_server_url, json=status_data)
        if response.status_code == 200:
            print("Data sent successfully to the HTTP server.")
        else:
            print(f"Failed to send data to the HTTP server: {response.status_code}, {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to the HTTP server: {e}")

    socketio.run(app, host='0.0.0.0', port=5000)

