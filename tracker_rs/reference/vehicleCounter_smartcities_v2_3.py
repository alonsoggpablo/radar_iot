# coding=utf-8
import json
import struct
from datetime import datetime
from threading import Thread
from time import sleep, time, altzone
import numpy as np
import requests
import serial
import traceback

###################################################################################################################

### MODE SELECTION ###
HIGHWAY_SCENARIO = False                     # If true the radar operates in high-speed scenario.

#### COMMUNICATION INTERFACE ####
USB_COMMUNICATION = False                    # If true communicates over USB (specify ports name below in 'Ports names' section), if false over UART (Raspberry Pi)

#### CONFIGURATION PARAMETERS ####
USB_CONNECTOR_UPWARD = False                 # Define the radar orientation by means of the position of the USB connector
pitch_angle = 3                             # Tilt angle with the vertical in the mounting (in degrees)
yaw_angle = 0                                # Yaw angle relative to the road in the mounting (in degrees)
VELOCITY_POSITIVE = True                     # Counting vehicles driving away from the radar 
VELOCITY_NEGATIVE = True                     # Counting vehicles approaching to the radar

X_MINIMUM_NEGATIVE_VELOCITY = 0              # Minimum x range for negative velocity lanes
X_MAXIMUM_NEGATIVE_VELOCITY = 4            # Maximum x range for negative velocity lanes

X_MINIMUM_POSITIVE_VELOCITY = 4              # Minimum x range for positive velocity lanes
X_MAXIMUM_POSITIVE_VELOCITY = 8              # Maximum x range for positive velocity lanes

#### OUTPUT RESULTS ####
SAVE_RESULTS = True                          # Save counting results (Vehicle_results.txt)
SAVE_RAW_DATA = False                         # Save the full point cloud (PointCloud.txt) and time statistic (stats.txt) for uRAD debuggin and tracking algorithm enhancement
OUTPUT_DATE_TIME_FORMAT = 1                   # 0 for datetime (yyyy/mm/dd HH:MM:SS in local time), 1 for timestamp (UNIX)

# files name
FOLDERNAME = 'Results'                      # Folder where output files will be saved
OUTPUT_FILENAME = 'Vehicle_results.txt'     # Name of counting results file
POINTCLOUD_FILENAME = 'PointCloud.txt'      # Name of radar pointCloud file (for uRAD debugging)

###################################################################################################################

DEBUG_VEHICLES_DEF = True                     # Set to True to print a message when a new vehicle is detected
USE_FAN = False                               # Only if communicates over UART (Raspberry Pi) and a PWM FAN connected to pin 12 

# Ports names
if (USB_COMMUNICATION):
    # Specify serial port names (Enhanced and Standard)
    CONFIG_PORT_NAME = 'COM1'
    DATA_PORT_NAME = 'COM2'
    # When connected to PC you have not acess to reset pin, unless you configure it manually
    reset = False
else: 
    import RPi.GPIO as GPIO
    # Name of serial port (/dev/serial0 in Raspberry Pi)
    PORT_NAME = '/dev/serial0'
    reset = True
    if (USE_FAN):
        fanpin = 12
        GPIO.cleanup()
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(fanpin,GPIO.OUT)
        fan = GPIO.PWM(fanpin,50)
        fan.start(0)
        fan.ChangeDutyCycle(0)
        max_temperature = 75
        duty_cycle = 0
        cnt_temp = 0
        lastFanTimePacket = 0
        checkFanThreshold = 2*60
        
# Reset section (GPIO6 in Raspberry Pi)
if reset:
    RESET_PIN_NUMBER = 6
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RESET_PIN_NUMBER, GPIO.OUT)
    GPIO.output(RESET_PIN_NUMBER, GPIO.HIGH)

# scenario
if not HIGHWAY_SCENARIO:
    from uRAD_Tracking_v2_3 import do_tracking,rotate_points,read_header, get_commands
    MIN_VEL_POSITIVE = 0.5
    MIN_VEL_NEGATIVE = -0.5
    fs = 20
else:
    from uRAD_Tracking_highway_v2_3 import do_tracking,rotate_points,read_header, get_commands
    MIN_VEL_POSITIVE = 3
    MIN_VEL_NEGATIVE = 3
    fs = 25

Y_MAX = 20
get_angles_error = True
z_value = -20
if pitch_angle>10:
    z_max = 0
else:
    z_max = 2

if not VELOCITY_POSITIVE:
    X_MINIMUM_POSITIVE_VELOCITY,X_MAXIMUM_POSITIVE_VELOCITY = 0,0
if not VELOCITY_NEGATIVE:
    X_MINIMUM_NEGATIVE_VELOCITY,X_MAXIMUM_NEGATIVE_VELOCITY = 0,0

def resetRadar():

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RESET_PIN_NUMBER, GPIO.OUT)
    GPIO.output(RESET_PIN_NUMBER, GPIO.LOW)
    sleep(10e-3)
    GPIO.output(RESET_PIN_NUMBER, GPIO.HIGH)
    sleep(1)

def initializeRadar(config_port, commands):

    for i in range(len(commands)):
        config_port.write(bytearray(commands[i].encode()))
        sleep(20e-3)

def check_temperature(tx_temperature):
    global max_temperature, duty_cycle, cnt_temp
    if tx_temperature>max_temperature:
        # mantain the duty cycle if we dont have 
        if tx_temperature <max_temperature + 2:
            duty_cycle = duty_cycle
        else:
            duty_cycle = 25 + 5*cnt_temp
            cnt_temp +=1
        if duty_cycle > 100:
            duty_cycle =100                                        
    else: 
        # set duty cycle to 0 and restart cont
        duty_cycle = 0
        cnt_temp = 0

PRINT_POINT_CLOUD = False

if not DEBUG_VEHICLES_DEF:
    # Wait time becuase pm2 is faster than NTP (Network Time Protocol)
    sleep(60)


# Frequency channel within the 60-64 GHz band. From 1 to 5.
FREQUENCY_CHANNEL = 3

if (FREQUENCY_CHANNEL == 2):
    freq_start = 60.75
elif (FREQUENCY_CHANNEL == 3):
    freq_start = 61.5
elif (FREQUENCY_CHANNEL == 4):
    freq_start = 62.25
elif (FREQUENCY_CHANNEL == 5):
    freq_start = 63.00
else:
    freq_start = 60.00

commands = get_commands(USB_CONNECTOR_UPWARD,freq_start,fs,X_MINIMUM_NEGATIVE_VELOCITY,X_MAXIMUM_NEGATIVE_VELOCITY,X_MINIMUM_POSITIVE_VELOCITY,X_MAXIMUM_POSITIVE_VELOCITY,yaw_angle)

offset_cpu_time = 0
overflows_cpu_time = 0
FREQUENCY_SYS_CLOCK = 200e6
MARGIN_CPU_CYCLES = FREQUENCY_SYS_CLOCK*1
time_cpu_cycles_prev = 0
frame_number_prev = 0

if (reset):
    resetRadar()

if (USB_COMMUNICATION):
    config_port = serial.Serial(CONFIG_PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)
    data_port = serial.Serial(DATA_PORT_NAME, 921600, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.5)
    initializeRadar(config_port, commands)
else:
    config_port = serial.Serial(PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)
    initializeRadar(config_port, commands)
    config_port.close()
    data_port = serial.Serial(PORT_NAME, 921600, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.5)

data_port.reset_output_buffer()

packet_header = bytearray([])

TLV_HEADER_LEN = 8
HEADER_LEN = 40
negative_velocity_list = []
positive_velocity_list = []
trackings_pos_vel = []
def_trackings_pos_vel  = []
trackings_neg_vel = []
def_trackings_neg_vel  = []
pitch_error_list = []
yaw_error_list = []
pos_velocity_track = 10
neg_velocity_track = -10
defined_time_packet_0 = False
time_packet_0 = time()
time_restart_packet_0 = 60*60

print('Radar working')
error_counter = 0

while True:

    try:

        time_packet = time()
        date_time_packet = datetime.now()

        correct_header, total_packet_len, frame_number, time_cpu_cycles, num_detected_obj, num_tlvs = read_header(data_port, HEADER_LEN)
        reset_and_initialize = False
        corrupted_packet = False

        if (correct_header):

            if (SAVE_RAW_DATA):
                file_stats = open('./%s/%04d-%02d-%02d_%s' % (FOLDERNAME, date_time_packet.year, date_time_packet.month, date_time_packet.day, POINTCLOUD_FILENAME), 'a')
                file_stats.write('%d %d %1.3f ' % (time_cpu_cycles, frame_number, time_packet))
                file_stats.close()

            if (time_packet - time_packet_0 >= time_restart_packet_0):
                defined_time_packet_0 = False

            if (not defined_time_packet_0 and frame_number >= 10):

                time_packet_0 = time_packet
                overflows_cpu_time = 0
                offset_cpu_time = time_cpu_cycles/FREQUENCY_SYS_CLOCK
                defined_time_packet_0 = True
                time_cpu_cycles_prev = time_cpu_cycles
            
            if (defined_time_packet_0):

                if (frame_number < frame_number_prev):

                    defined_time_packet_0 = False
                    overflows_cpu_time = 0
                
                else:

                    if (abs(time_cpu_cycles-time_cpu_cycles_prev) > (2**32 - MARGIN_CPU_CYCLES)):
                        overflows_cpu_time += 1
                    time_cpu_cycles_prev = time_cpu_cycles
                    timestamp_cpu_cycles = time_cpu_cycles + overflows_cpu_time*(2**32)
                    timestamp_cpu_cycles /= FREQUENCY_SYS_CLOCK
                    
                    ti = time_packet_0 + timestamp_cpu_cycles - offset_cpu_time

            frame_number_prev = frame_number

            packet_header = bytearray([])
            if (num_detected_obj <= 400 and total_packet_len < 12000 and num_tlvs < 10):
                packet_payload = data_port.read(total_packet_len-HEADER_LEN)

                if (len(packet_payload) == total_packet_len-HEADER_LEN):

                    detected_objects = np.zeros((num_detected_obj, 6))
                    if (PRINT_POINT_CLOUD):
                        print('num_detected_obj: %d' % num_detected_obj)

                    for i in range(num_tlvs):

                        tlv_type, tlv_length = struct.unpack('2I', packet_payload[:TLV_HEADER_LEN])

                        if (tlv_type > 20 or tlv_length > 10000):
                            packet_header = bytearray([])
                            corrupted_packet = True
                            break

                        packet_payload = packet_payload[TLV_HEADER_LEN:]

                        if (tlv_type == 1):

                            for j in range(num_detected_obj):

                                x, y, z, v = struct.unpack('4f', packet_payload[:16])
                                
                                detected_objects[j, 0] = x
                                detected_objects[j, 1] = y
                                detected_objects[j, 2] = z
                                detected_objects[j, 3] = v

                                packet_payload = packet_payload[16:]

                        elif (tlv_type == 7):

                            for j in range(num_detected_obj):

                                snr, noise = struct.unpack('2H', packet_payload[:4])

                                detected_objects[j, 4] = snr
                                detected_objects[j, 5] = noise

                                if (PRINT_POINT_CLOUD):
                                    print('x: %1.3f m, y: %1.3f m, z: %1.3f m, v: %1.3f m/s, snr: %d, noise: %d' % (detected_objects[j, 0], detected_objects[j, 1], detected_objects[j, 2], detected_objects[j, 3], detected_objects[j, 4], detected_objects[j, 5]))

                                packet_payload = packet_payload[4:]

                        elif (tlv_type == 6):

                                    interFrameProcessingTime, transmitOutputTime, interFrameProcessingMargin, interChirpProcessingMargin, activeFrameCPULoad, interFrameCPULoad = struct.unpack('6I', packet_payload[:24])
                                    packet_payload = packet_payload[tlv_length:]
                                
                        elif (tlv_type == 9):

                            tempReportValid, tempDataTime, tmpRx0Sens, tmpRx1Sens, tmpRx2Sens, tmpRx3Sens, tmpTx0Sens, tmpTx1Sens, tmpTx2Sens, tmpPmSens, tmpDig0Sens, tmpDig1Sens = struct.unpack('iI10h', packet_payload[:28])
                            packet_payload = packet_payload[tlv_length:]

                            if (not USB_COMMUNICATION and USE_FAN and (time_packet - lastFanTimePacket > checkFanThreshold)):
                                lastFanTimePacket = time_packet

                                rx_temperature = np.mean(np.array([tmpRx0Sens, tmpRx1Sens, tmpRx2Sens, tmpRx3Sens]))
                                tx_temperature = np.mean(np.array([tmpTx0Sens, tmpTx1Sens, tmpTx2Sens]))

                                check_temperature(tx_temperature)
                                
                            if (not USB_COMMUNICATION and USE_FAN):
                                # Set fan duty cycle
                                fan.ChangeDutyCycle(duty_cycle)


                    if (not corrupted_packet):
                        if (SAVE_RAW_DATA):
                            results_string = ''
                            for j in range(num_detected_obj):
                                results_string += ' %1.3f %1.3f %1.3f %1.3f %d %d' % (detected_objects[j, 0], detected_objects[j, 1], detected_objects[j, 2], detected_objects[j, 3], detected_objects[j, 4], detected_objects[j, 5])
                            file_points = open('./%s/%04d-%02d-%02d_%s' % (FOLDERNAME, date_time_packet.year, date_time_packet.month, date_time_packet.day, POINTCLOUD_FILENAME), 'a')
                            file_points.write('1' + results_string + ' \n')
                            file_points.close()
                        
                        if (defined_time_packet_0):
                        
                            x = detected_objects[:num_detected_obj, 0]
                            y = detected_objects[:num_detected_obj, 1]
                            z = detected_objects[:num_detected_obj, 2]
                            if (not USB_CONNECTOR_UPWARD):
                                x = -x
                                z = -z
                            x, y, z = rotate_points(-(2*pitch_angle)*np.pi/180, -(yaw_angle)*np.pi/180, x, y, z)
                            Range = np.sqrt(x**2+y**2+z**2)
                            Azimuth = np.arctan(x/y)
                            Elevation = np.arccos(z/Range)
                            Velocity = detected_objects[:num_detected_obj, 3]
                            Amplitude = (detected_objects[:num_detected_obj, 4] + detected_objects[:num_detected_obj, 5])/10
                            Snr = detected_objects[:num_detected_obj, 4]/10
                            pointCloud_actual = np.zeros((num_detected_obj, 9))
                            pointCloud_actual[:, 0] = Range
                            pointCloud_actual[:, 1] = Velocity
                            pointCloud_actual[:, 2] = Amplitude
                            pointCloud_actual[:, 3] = Snr
                            pointCloud_actual[:, 4] = Azimuth
                            pointCloud_actual[:, 5] = Elevation
                            pointCloud_actual[:, 6] = x
                            pointCloud_actual[:, 7] = y
                            pointCloud_actual[:, 8] = z

                            _output_filename = './%s/%04d-%02d-%02d_%s' % (FOLDERNAME, date_time_packet.year, date_time_packet.month, date_time_packet.day, OUTPUT_FILENAME)
                            
                            if VELOCITY_NEGATIVE:

                                condition_neg_vel = np.logical_and.reduce((y<Y_MAX,x>X_MINIMUM_NEGATIVE_VELOCITY,x<X_MAXIMUM_NEGATIVE_VELOCITY,Velocity<MIN_VEL_NEGATIVE,z>z_value,z<z_max)) 
                                
                                if len(negative_velocity_list)>20:
                                    neg_velocity_track = np.mean(np.array(negative_velocity_list))
                                    negative_velocity_list[:-1] = negative_velocity_list[1:]
                                
                                negative_trackings, _,trackings_neg_vel,pitch_error_list,yaw_error_list, negative_velocity_list, z_value = do_tracking(def_trackings_neg_vel,trackings_neg_vel,pointCloud_actual[condition_neg_vel],ti, neg_velocity_track,pitch_angle,yaw_angle,X_MINIMUM_NEGATIVE_VELOCITY,X_MAXIMUM_NEGATIVE_VELOCITY,_output_filename,False,get_angles_error,pitch_error_list,yaw_error_list,negative_velocity_list, z_value,DEBUG_VEHICLES_DEF,False,OUTPUT_DATE_TIME_FORMAT)
                            
                            if VELOCITY_POSITIVE:
                                condition_pos_vel = np.logical_and.reduce((y<Y_MAX,x>X_MINIMUM_POSITIVE_VELOCITY,x<X_MAXIMUM_POSITIVE_VELOCITY,Velocity>MIN_VEL_POSITIVE,z>z_value,z<z_max))

                                if len(positive_velocity_list)>20:
                                    pos_velocity_track = np.mean(np.array(positive_velocity_list))
                                    positive_velocity_list[:-1] = positive_velocity_list[1:]
                                
                                positive_trackings, _,trackings_pos_vel,pitch_error_list,yaw_error_list, positive_velocity_list, z_value = do_tracking(def_trackings_pos_vel,trackings_pos_vel,pointCloud_actual[condition_pos_vel],ti, pos_velocity_track,pitch_angle,yaw_angle,X_MINIMUM_POSITIVE_VELOCITY,X_MAXIMUM_POSITIVE_VELOCITY,_output_filename,True,get_angles_error,pitch_error_list,yaw_error_list,positive_velocity_list, z_value,DEBUG_VEHICLES_DEF,False,OUTPUT_DATE_TIME_FORMAT)
                            
                            if get_angles_error and len(pitch_error_list)>100:     

                                pitch_angle += np.mean(np.array(pitch_error_list))
                                yaw_angle -= np.mean(np.array(yaw_error_list))
                                if pitch_angle>10:
                                    z_max = 0
                                pitch_error_list, yaw_error_list = [], []


                            ### SAVE TRACKINGS RESULTS ###
                            all_trackings = []
                            if VELOCITY_NEGATIVE:
                                for track in negative_trackings:
                                    all_trackings.append(track)
                            if VELOCITY_POSITIVE:
                                for track in positive_trackings:
                                    all_trackings.append(track)
                            if len(all_trackings)>0 and SAVE_RESULTS:
                                timestamp_to_order = []
                                for track in all_trackings:

                                    timestamp_to_order.append(track.final_timestamp)
                                timestamp_ordered = np.argsort(timestamp_to_order)
                                for timestamp in timestamp_ordered:
                                    track = all_trackings[timestamp]
                                    if OUTPUT_DATE_TIME_FORMAT == 0:
                                        local_dt = datetime.utcfromtimestamp(track.final_timestamp-altzone)
                                        datetime_str = '%04d/%02d/%02d %02d:%02d:%02d' % (local_dt.year, local_dt.month, local_dt.day, local_dt.hour, local_dt.minute, local_dt.second)
                                        output_file = open(_output_filename,'a')
                                        output_file.write('%s %1.2f %1.2f %1.0f %s\n' % (datetime_str,track.velocity*3.6, track.x_value,track.type,track.uuid) )
                                        output_file.close()
                                    elif OUTPUT_DATE_TIME_FORMAT == 1:
                                        output_file = open(_output_filename,'a')
                                        output_file.write('%1.0f %1.2f %1.2f %1.0f %s\n' % (track.final_timestamp,track.velocity*3.6, track.x_value,track.type,track.uuid) )
                                        output_file.close()

                            error_counter = 0
                            
                        if (PRINT_POINT_CLOUD and num_tlvs > 0):
                            print(' ')

                else:
                    if (SAVE_RAW_DATA):
                        file_points = open('./%s/%04d-%02d-%02d_%s' % (FOLDERNAME, date_time_packet.year, date_time_packet.month, date_time_packet.day, POINTCLOUD_FILENAME), 'a')
                        file_points.write('0\n')
                        file_points.close()
                    reset_and_initialize = True
            
            else:
                if (SAVE_RAW_DATA):
                    file_points = open('./%s/%04d-%02d-%02d_%s' % (FOLDERNAME, date_time_packet.year, date_time_packet.month, date_time_packet.day, POINTCLOUD_FILENAME), 'a')
                    file_points.write('0\n')
                    file_points.close()
                reset_and_initialize = True
        
        else:
            reset_and_initialize = True
        
        if (reset_and_initialize):
            
            data_port.close()

            if reset:

                print('Restarting radar')

                resetRadar()

                if not USB_COMMUNICATION:
                    
                    config_port = serial.Serial(PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)

                    initializeRadar(config_port, commands)

                    config_port.close()
                    data_port = serial.Serial(PORT_NAME, 921600, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.5)

                else:
                    initializeRadar(config_port, commands)

                data_port.reset_output_buffer()

                defined_time_packet_0 = False
                time_packet_0 = time()

            else:
                
                print('Closing ports')

                if not USB_COMMUNICATION:
                    config_port = serial.Serial(PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)

                config_port.write(bytearray('sensorStop\n'.encode()))
                config_port.close()
                break

    except KeyboardInterrupt:

        print('Closing ports')
        data_port.close()
        
        if not USB_COMMUNICATION:
            config_port = serial.Serial(PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)

        config_port.write(bytearray('sensorStop\n'.encode()))
        config_port.close()
        if (reset):
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(RESET_PIN_NUMBER, GPIO.OUT)
            GPIO.output(RESET_PIN_NUMBER, GPIO.LOW)

        if (not USB_COMMUNICATION and USE_FAN):
            sleep(0.1)
            fan.stop()
            sleep(0.1)
            
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(fanpin, GPIO.OUT)
            GPIO.output(fanpin, GPIO.LOW)
            
        import sys
        sys.exit()

    except:

        print('Radar error')
        print(traceback.format_exc())
        data_port.close()

        if reset:

            print('Restarting radar')

            resetRadar()

            if not USB_COMMUNICATION:
                
                config_port = serial.Serial(PORT_NAME, 115200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.3)

                initializeRadar(config_port, commands)

                config_port.close()
                data_port = serial.Serial(PORT_NAME, 921600, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.5)

            else:
                initializeRadar(config_port, commands)

            data_port.reset_output_buffer()
            
            defined_time_packet_0 = False
            time_packet_0 = time()
        else:

            error_counter += 1
            if (error_counter >= 10):
                break
            if (not USB_COMMUNICATION and USE_FAN):
                sleep(0.1)
                fan.stop()
                sleep(0.1)
                GPIO.cleanup()
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(fanpin, GPIO.OUT)
                GPIO.output(fanpin, GPIO.LOW)
