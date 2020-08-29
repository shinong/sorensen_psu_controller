import serial
import serial.tools.list_ports
import io
import time
import paho.mqtt.client as mqtt
import os
import tkinter as tk
from tkinter import ttk
import threading


class Psu():
    def __init__(self, port= None, Q_set= 20):
        if port:
            print("the port is" + port)
            self.port = port
            self.Q_set = Q_set
            self.status_log_check()
            self.serial_connection_start()
            self.psu_init()
            self.mqtt_config()
            self.running_status = False
            self.curr = "0.00"
            self.volt = "0.00"
        else:
            print("please define a serial port first")

    def serial_connection_start(self):
        self.ser = serial.Serial(self.port, 9600, timeout= 1)
        self.sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser, 1), newline= "\r", line_buffering= True)
        self.sio.write("*ADR 1\n")
        time.sleep(0.1)
        self.sio.write(str("*IDN?\n"))
        result = self.sio.readline()
        print(result)

    def serial_connection_stop(self):
        print("I am tryting to stop")
        self.sio.write(":OUTP:STAT OFF\n")
        self.ser.close()
        self.record_file.seek(0)
        self.record_file.truncate()
        self.record_file.write("-1")
        self.record_file.close()

    def mqtt_config(self):
        broker_address = "shinong.ddns.net"
        self.client = mqtt.Client("pow_server")
        self.client.username_pw_set("shinong_laptop_server",password="19921023")
        self.client.on_log = self.on_log
        self.client.connect(broker_address,keepalive=60)
        self.client.loop_start()
    
    def mqtt_stop(self):
        print("mqtt disconnected")
        self.client.loop_stop()

    def on_log(self,client, userdata, level, buf):
        print("log: ", buf)

    def status_log_check(self):
        temp_file = open("record.txt", "r")
        previous_Q = float(temp_file.read())
        if previous_Q < 0:
            print("fresh start mode")
            self.Q_factor = 0
        else:
            self.Q_factor = previous_Q
    
    def psu_init(self):
        time.sleep(0.1)
        self.sio.write(":OUTP:STAT OFF\n")

    def data_fetch(self,command):
         self.sio.write(command)
         return self.sio.readline()

    def running(self):
        self.sio.write(":SOUR:CURR 0.2\n")
        time.sleep(0.1)
        self.sio.write(":OUTP:STAT ON\n")
        self.record_file = open("record.txt","w")
        start = time.time()
        while (self.Q_factor <= self.Q_set):
            self.curr = self.data_fetch(":MEAS:CURR?\n")
            time.sleep(0.1)
            self.volt = self.data_fetch(":MEAS:VOLT?\n")
            time.sleep(0.1)
            print("running voltage:{}".format(self.volt))
            print("running current:{}".format(self.curr))
            try:
                curr_num = float(self.curr)
            except ValueError:
                curr_num = 0
            end = time.time()
            self.Q_factor += curr_num*(end-start)/3600
            print(self.Q_factor)
            start = time.time()
            self.client.publish("lab/pow","voltage:{},current:{},ampHour:{}".format(self.volt,self.curr,self.Q_factor))
            self.record_file.seek(0)
            self.record_file.truncate()
            self.record_file.write(str(self.Q_factor))
            self.record_file.flush()
            os.fsync(self.record_file.fileno())
            if not self.running_status:
                self.serial_connection_stop()
                self.mqtt_stop()
                break
class App(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack()
        self.search_serial_ports()
        self.create_widgets()
        self.started = False
    
    def create_widgets(self):
        #buttons
        self.start_button = tk.Button(self, text= "Start", bg= "green", command= lambda:threading.Thread(target=self.start_command).start())
        self.start_button.pack()
        self.stop_button = tk.Button(self, text= "Force Stop", bg= "red", command= self.stop_command)
        self.stop_button.pack()
        #combobox
        self.port_select = ttk.Combobox(self,values= self.comport_list)
        self.port_select.current(0)
        self.port_select.pack()
        #labels
        self.voltage_label = tk.Label(self,text = "0.00")
        self.voltage_label.pack()
        self.current_label = tk.Label(self,text = "0.00")
        self.current_label.pack()

    def search_serial_ports(self):
        self.comport_list = [p.device for p in serial.tools.list_ports.comports()]


    def start_command(self):
        if not self.started:
            self.power_control = Psu(self.port_select.get())
            self.power_control.running_status = True
            self.started = True
            self.current_label.after(1000, self.update_label)
            self.power_control.running()
        else:
            print("already running")

    def stop_command(self):
        self.power_control.running_status = False
        self.started = False
        
    def update_label(self):
        if self.started:
            self.voltage_label["text"] = self.power_control.volt
            self.current_label["text"] = self.power_control.curr
            self.current_label.after(10000,self.update_label)
        else:
            self.voltage_label["text"] = "OFF"
            self.current_label["text"] = "OFF"


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x480")
    myapp = App(master=root)
    myapp.mainloop()
