#from datetime import datetime
import datetime
from io import TextIOBase
from os import terminal_size
import serial
import serial.tools.list_ports
import io
import time
import paho.mqtt.client as mqtt
import os
import tkinter as tk
from tkinter import ttk
import threading
import json


class Psu():
    def __init__(self, port= None):
        if port:
            print("the port is" + port)
            self.port = port
            self.status_log_check()
            self.load_config()
            self.serial_connection_start()
            self.psu_init()
            self.mqtt_config()
            self.running_status = False
            self.curr = "0.00"
            self.volt = "0.00"
            self.message = {"current":0, "voltage":0, "amphour":0}
        else:
            print("please define a serial port first")

    def serial_connection_start(self):
        try:
            self.ser = serial.Serial(self.port, 9600, timeout= 1)
            self.sio = io.TextIOWrapper(io.BufferedRWPair(self.ser, self.ser, 1), newline= "\r", line_buffering= True)
            self.sio.write("*ADR 1\n")
            time.sleep(0.1)
            self.sio.write(str("*IDN?\n"))
            result = self.sio.readline()
            print(result)
        except IOError:
            print("Serial connection failed")
        

    def load_config(self):
        config = Config_handler()
        self.Amp_set = config.Amp_set
        self.Q_set = config.Q_set
        self.broker_address = config.broker_address
        self.mqtt_username = config.mqtt_username
        self.mqtt_password = config.mqtt_password

    def serial_connection_stop(self):
        print("I am tryting to stop")
        self.sio.write(":OUTP:STAT OFF\n")
        self.ser.close()
        self.record_file.seek(0)
        self.record_file.truncate()
        self.record_file.write("-1")
        self.record_file.close()
        self.running_status = False

    def mqtt_config(self):
        self.client = mqtt.Client("pow_server")
        self.client.username_pw_set(self.mqtt_username,password=self.mqtt_password)
        self.client.on_log = self.on_log
        self.client.connect(self.broker_address,keepalive=60)
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
        self.sio.write(":SOUR:CURR {}\n".format(self.Amp_set))
        time.sleep(0.1)
        self.sio.write(":OUTP:STAT ON\n")
        self.record_file = open("record.txt","w")
        start = time.time()
        while (True):
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
            self.message["voltage"] = self.volt.replace("\r","")
            self.message["current"] = self.curr.replace("\r","")
            self.message["amphour"] = self.Q_factor
            #self.client.publish("shinongmao@gmail.com/lab/pow","voltage:{},current:{},ampHour:{}".format(self.volt,self.curr,self.Q_factor))
            self.client.publish("shinongmao@gmail.com/lab/pow",json.dumps(self.message))
            self.record_file.seek(0)  
            self.record_file.truncate()
            self.record_file.write(str(self.Q_factor))
            self.record_file.flush()
            os.fsync(self.record_file.fileno())
            if (not self.running_status) or (self.Q_factor > self.Q_set):
                self.serial_connection_stop()
                self.mqtt_stop()
                break


class App(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack()
        self.search_serial_ports()
        self.config = Config_handler()
        self.create_widgets()
        self.started = False
    
    def create_widgets(self):
        #right buttons
        self.start_button_right = tk.Button(self, text= "Start", bg= "green", command= lambda:threading.Thread(target=self.start_command).start())
        self.start_button_right.grid(row = 5, column = 2)
        self.stop_button_right = tk.Button(self, text= "Force Stop", bg= "red", command= self.stop_command)
        self.stop_button_right.grid(row = 6, column = 2)
        #left buttons
        self.start_button_left = tk.Button(self, text= "Start", bg= "grey")
        self.start_button_left.grid(row=5, column= 0)
        self.stop_button_left = tk.Button(self, text= "Force Stop", bg= "grey")
        self.stop_button_left.grid(row= 6, column= 0)
        #shared bottoms
        self.port_refresh_button = tk.Button(self, text= "Refresh", bg = "yellow", command= self.update_serial_ports)
        self.port_refresh_button.grid(row= 4, column= 1)
        #right combobox
        self.port_select_right = ttk.Combobox(self,values= self.comport_list)
        self.port_select_right.current(0)
        self.port_select_right.grid(row = 4, column = 2)
        #left combobox
        self.port_select_left = ttk.Combobox(self, values = self.comport_list)
        self.port_select_left.current(0)
        self.port_select_left.grid(row= 4, column= 0)
        #left labels
        self.current_label_left = tk.Label(self, text= "N/A")
        self.current_label_left.grid(row=2, column= 0)
        self.voltage_label_left = tk.Label(self, text= "N/A")
        self.voltage_label_left.grid(row=3, column= 0)
        self.est_label_left = tk.Label(self, text= "Estimated finished time:")
        self.est_label_left.grid(row=7, column= 0)
        self.est_time_left = ttk.Label(self, text= "N/A")
        self.est_time_left.grid(row=8, column= 0)
        self.set_current_label_left = tk.Label(self, text = "Set current left {}".format(self.config.Amp_set))
        self.set_current_label_left.grid(row = 0, column = 0)
        self.set_Q_label_left = tk.Label(self, text = "Q left is set to {}".format(self.config.Q_set))
        self.set_Q_label_left.grid(row = 1, column = 0)
        #right labels
        self.voltage_label_right = tk.Label(self,text = "0.00")
        self.voltage_label_right.grid(row = 2, column = 2)
        self.current_label_right = tk.Label(self,text = "0.00")
        self.current_label_right.grid(row = 3, column = 2)
        self.est_label_right = tk.Label(self, text= "Estimated finished time:")
        self.est_label_right.grid(row=7, column= 2)
        self.est_time_right = tk.Label(self, text= "N/A")
        self.est_time_right.grid(row=8, column= 2)
        self.set_current_label_right = tk.Label(self, text = "Set current right {}".format(self.config.Amp_set))
        self.set_current_label_right.grid(row = 0, column = 2)
        self.set_Q_label_right = tk.Label(self, text = "Q right is set to {}".format(self.config.Q_set))
        self.set_Q_label_right.grid(row = 1, column = 2)

    def search_serial_ports(self):
        self.comport_list = [p.device for p in serial.tools.list_ports.comports()]

    def update_serial_ports(self):
        available_serial_ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_select_left["values"] = available_serial_ports
        self.port_select_right["values"] = available_serial_ports

    def start_command(self):
        if not self.started:
            self.power_control = Psu(self.port_select_right.get())
            self.power_control.running_status = True
            self.started = True
            self.current_label_right.after(1000, self.update_label)
            self.update_est_time_label()
            #   power_control.running() func contains a while loop inside, any other starter code should be 
            #   placed above this
            self.power_control.running()
        else:
            print("already running")

    def stop_command(self):
        self.power_control.running_status = False
        self.started = False
        
    def update_label(self):
        if self.started:
            self.voltage_label_right["text"] = self.power_control.volt
            self.current_label_right["text"] = self.power_control.curr
            self.current_label_right.after(10000,self.update_label)
            try:
                if not self.power_control.running_status:
                    self.started = False
            except NameError:
                pass
        else:
            self.voltage_label_right["text"] = "OFF"
            self.current_label_right["text"] = "OFF"
    
    def est_time_cal(self):
        amp_hour = self.config.Q_set
        amp = self.config.Amp_set
        hours = int(amp_hour/amp)
        minutes = (amp_hour%amp)/4.8*60
        start_time = datetime.datetime.now()
        return str(start_time + datetime.timedelta(hours = hours, minutes= minutes))
    
    def update_est_time_label(self):
        #self.est_time_left["text"] = self.est_time_cal()
        self.est_time_right["text"] = self.est_time_cal()
        

class Config_handler():
    def __init__(self):
        f = open("config.txt","r")
        config = f.read().splitlines()
        self.Amp_set = float(config[0].split(":")[1])
        self.Q_set = float(config[1].split(":")[1])
        self.broker_address = config[2].split(":")[1]
        self.mqtt_username = config[3].split(":")[1]
        self.mqtt_password = config[4].split(":")[1]
        f.close()


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x480")
    myapp = App(master=root)
    myapp.mainloop()
