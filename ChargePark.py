from http.server import BaseHTTPRequestHandler, HTTPServer
from stmpy import Driver, Machine

from threading import Thread

import paho.mqtt.client as mqtt

from globals import *

import requests


import json

import gpiozero


# State machines for the LED on top of the electric charger
class ElectricChargerSignalLED:
    MACHINE_ID = "signal_LED"

    stm: Machine

    def on_init(self):
        print(f"Init {self.MACHINE_ID}")

    SIGNAL_AVAILABLE_TRIGGER = "signal_available"
    SIGNAL_OCCUPIED_TRIGGER = "signal_occupied"
    SIGNAL_FACTORY_ERROR_TRIGGER = "signal_factory_error"
    SIGNAL_SOON_AVAILABLE_TRIGGER = "signal_soon_available"

    green = gpiozero.LED(20)
    yellow = gpiozero.LED(21)
    red = gpiozero.LED(2)

    transitions = [
        {
            "source": "initial",
            "target": "s_available_green",
        },
        {
            "trigger": SIGNAL_AVAILABLE_TRIGGER,
            "source": "s_initial_off",
            "target": "s_available_green",
        },
        {
            "trigger": SIGNAL_OCCUPIED_TRIGGER,
            "source": "s_available_green",
            "target": "s_occupied_red",
        },
        {
            "trigger": SIGNAL_SOON_AVAILABLE_TRIGGER,
            "source": "s_occupied_red",
            "target": "s_soon_available_pulsating_yellow",
        },
        {
            "trigger": SIGNAL_AVAILABLE_TRIGGER,
            "source": "s_soon_available_pulsating_yellow",
            "target": "s_available_green",
        },
        # Missing transition for disconnecting/becoming available while in different states, as these were not part of the demo

    ]

    states = [
        {"name": "s_initial_off", "entry": "set_led('off')"},
        {"name": "s_available_green", "entry": "set_led('green')"},
        {"name": "s_occupied_red", "entry": "set_led('red')"},
        {
            "name": "s_soon_available_pulsating_yellow",
            "entry": "set_led('pulsating_yellow')",
        },
    ]

    def set_led(self, color):

        match color:
            case "off":
                self.red.off()
                self.green.off()
                self.yellow.off()
                print("LED off")
            case "green":
                self.set_led("off")
                self.green.on()
                print("LED green")
            case "red":
                self.set_led("off")
                self.red.on()
                print("LED red")
            case "pulsating_yellow":
                self.set_led("off")
                self.yellow.on()
                print("LED pulsating yellow")
            case _:
                raise ValueError("Invalid color")

# State machine for the monitor which listens to all chargers, and sends updates to the web API
class ElectricChargerMonitor:
    MACHINE_ID = "electric_charger_monitor"

    mqtt_client: mqtt.Client
    stm: Machine

    CHARGER_CONNECT_TRIGGER = "charger_connect"
    CHARGER_DISCONNECT_TRIGGER = "charger_disconnect"
    CHARGER_STATUS_TRIGGER = "charger_status"
    CHARGER_FINISHED_TRIGGER = "charger_finished"

    transitions = [
        {
            "source": "initial",
            "target": "s_monitor",
        },
    ]

    states = [
        {
            "name": "s_monitor",
            CHARGER_CONNECT_TRIGGER: "connect_plug()",
            CHARGER_DISCONNECT_TRIGGER: "disconnect_plug()",
            CHARGER_STATUS_TRIGGER: "status(*)",
            CHARGER_FINISHED_TRIGGER: "finished()",
        },
    ]

    def on_init(self):
        print(f"Init {self.MACHINE_ID}")

    def connect_plug(self):
        x = requests.post(WEB_SERVER_URL, json={"state": "connected_setup"})
        if not x.ok:
            print("Error sending connect")

    def status(self, *args):

        percentage = args[0]
        goal = args[1]

        x = requests.post(
            WEB_SERVER_URL,
            json={
                "state": "connected_charging",
                "chargingPercentage": percentage,
                "chargingGoal": goal,
            },
        )
        if not x.ok:
            print("Error sending connect")

    def disconnect_plug(self):
        x = requests.post(
            WEB_SERVER_URL,
            json={
                "state": "disconnected",
            },
        )
        if not x.ok:
            print("Error sending connect")

    def finished(self):
        x = requests.post(
            WEB_SERVER_URL,
            json={
                "state": "connected_finished",
            },
        )
        if not x.ok:
            print("Error sending connect")


# State machine for the electric charger, states for connecting to car, charging, and finished charging
class ElectricCharger:
    MACHINE_ID = "electric_charger"

    mqtt_client: mqtt.Client
    stm: Machine
    driver: Driver

    CONNECT_PLUG_TRIGGER = "connect_plug"
    DISCONNECT_PLUG_TRIGGER = "disconnect_plug"
    SETUP_SUCCESS_TRIGGER = "setup_success"
    CHARGING_FINISHED_TRIGGER = "charging_finished"
    WEBSERVER_CHARGER_CONFIG_TRIGGER = "webserver_charger_config"

    # These are changed by charger_config once the user sets the desired values on the application
    initial_charging_percentage = 20
    charging_percentage = 20
    charging_goal = 20

    transitions = [
        {
            "source": "initial",
            "target": "s_available",
            "effect": "on_init()",
        },
        {
            "trigger": CONNECT_PLUG_TRIGGER,
            "source": "s_available",
            "target": "s_connected_setup_in_progress",
        },
        {
            "trigger": SETUP_SUCCESS_TRIGGER,
            "source": "s_connected_setup_in_progress",
            "target": "s_connected_charging",
        },
        {
            "trigger": CHARGING_FINISHED_TRIGGER,
            "source": "s_connected_charging",
            "target": "s_connected_finished_charging",
        },
        {
            "trigger": DISCONNECT_PLUG_TRIGGER,
            "source": "s_connected_setup_in_progress",
            "target": "s_available",
            "effect": "disconnect_plug()",
        },
        {
            "trigger": DISCONNECT_PLUG_TRIGGER,
            "source": "s_connected_finished_charging",
            "target": "s_available",
            "effect": "disconnect_plug()",
        },
        # Missing transition for disconnecting while in different states, as these were not part of the demo
    ]
    states = [
        {"name": "s_available"},
        {
            "name": "s_connected_setup_in_progress",
            "entry": "connect_plug()",
            WEBSERVER_CHARGER_CONFIG_TRIGGER: "charger_config(*)",
        },
        {
            "name": "s_connected_charging",
            "entry": 'start_timer("status", 1000)',
            "status": 'start_timer("status", 1000); status()',
            "exit": 'stop_timer("status")',
        },
        {"name": "s_connected_finished_charging", "entry": "finished_charging()"},
    ]

    def on_init(self):
        print(f"Init {self.MACHINE_ID}")

    def connect_plug(self):
        self.mqtt_client.publish(
            MQTT_CHARGER_MONITOR_INPUT_TOPIC,
            ElectricChargerMonitor.CHARGER_CONNECT_TRIGGER,
        )
        driver.send(
            ElectricChargerSignalLED.SIGNAL_OCCUPIED_TRIGGER,
            ElectricChargerSignalLED.MACHINE_ID,
        )

    def disconnect_plug(self):
        self.mqtt_client.publish(
            MQTT_CHARGER_MONITOR_INPUT_TOPIC,
            ElectricChargerMonitor.CHARGER_DISCONNECT_TRIGGER,
        )
        driver.send(
            ElectricChargerSignalLED.SIGNAL_AVAILABLE_TRIGGER,
            ElectricChargerSignalLED.MACHINE_ID,
        )

    def charger_config(self, *args):
        (
            self.initial_charging_percentage,
            self.charging_percentage,
            self.charging_goal,
        ) = (int(args[0]), int(args[0]), int(args[1]))

        self.mqtt_client.publish(
            MQTT_CHARGER_INPUT_TOPIC, ElectricCharger.SETUP_SUCCESS_TRIGGER
        )

    def status(self):
        increment = 5
        self.charging_percentage = (
            self.charging_percentage + increment
            if self.charging_percentage + increment <= self.charging_goal
            else self.charging_goal
        )
        self.mqtt_client.publish(
            MQTT_CHARGER_MONITOR_INPUT_TOPIC,
            ElectricChargerMonitor.CHARGER_STATUS_TRIGGER
            + ","
            + str(self.charging_percentage)
            + ","
            + str(self.charging_goal),
        )
        print("Charging status:", self.charging_percentage)

        if self.charging_percentage == self.charging_goal:
            self.mqtt_client.publish(
                MQTT_CHARGER_INPUT_TOPIC, ElectricCharger.CHARGING_FINISHED_TRIGGER
            )

        # Change color of LED once the charging is almost done
        progress_delta = self.charging_percentage - self.initial_charging_percentage
        progress = (progress_delta) / (
            self.charging_goal / self.initial_charging_percentage
        )

        if progress > 0.7:
            driver.send(
                ElectricChargerSignalLED.SIGNAL_SOON_AVAILABLE_TRIGGER,
                ElectricChargerSignalLED.MACHINE_ID,
            )

    def finished_charging(self):
        self.mqtt_client.publish(
            MQTT_CHARGER_MONITOR_INPUT_TOPIC,
            ElectricChargerMonitor.CHARGER_FINISHED_TRIGGER,
        )

# Clients handle the MQTT communcation and sends it to the drivers
class ElectricChargerClient:

    stm_driver: Driver

    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print(f"on_connect(): {mqtt.connack_string(rc)}")

    def on_message(self, client, userdata, msg):

        payload_str = msg.payload.decode("utf-8") if msg.payload else None

        # Some messages have arguments, so we split them
        if "," in payload_str:
            trigger, *message_str = payload_str.split(",")
        else:
            trigger, message_str = payload_str, None

        self.stm_driver.send(
            trigger,
            ElectricCharger.MACHINE_ID,
            message_str,
        )

        print(f"charger: on_message(): topic: {msg.topic}, args: {message_str}")

    def start(self, broker, port):

        print("Connecting to {}:{}".format(broker, port))
        self.client.connect(broker, port)

        self.client.subscribe(MQTT_CHARGER_INPUT_TOPIC)

        try:
            thread = Thread(target=self.client.loop_forever)
            thread.start()
        except KeyboardInterrupt:
            print("Interrupted")
            self.client.disconnect()


# Clients handle the MQTT communcation and sends it to the drivers
class ElectricChargerMonitorClient:

    stm_driver: Driver

    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print("on_connect(): {}".format(mqtt.connack_string(rc)))

    def on_message(self, client, userdata, msg):

        payload_str = msg.payload.decode("utf-8") if msg.payload else None

        if "," in payload_str:
            trigger, *message_str = payload_str.split(",")
        else:
            trigger, message_str = payload_str, None

        print(f"charger_monitor: on_message(): topic: {msg.topic}, args: {message_str}")
        self.stm_driver.send(
            trigger,
            ElectricChargerMonitor.MACHINE_ID,
            message_str,
        )

    def start(self, broker, port):

        print("Connecting to {}:{}".format(broker, port))
        self.client.connect(broker, port)

        self.client.subscribe(MQTT_CHARGER_MONITOR_INPUT_TOPIC)

        try:
            # line below should not have the () after the function!
            thread = Thread(target=self.client.loop_forever)
            thread.start()
        except KeyboardInterrupt:
            print("Interrupted")
            self.client.disconnect()


if __name__ == "__main__":
    broker, port = "test.mosquitto.org", 1883

    # Initialize business logic
    electric_charger_monitor_obj = ElectricChargerMonitor()
    electric_charger_obj = ElectricCharger()
    electric_charger_signal_led_obj = ElectricChargerSignalLED()

    # Initialize and assign state machines
    electric_charger_monitor_stm = Machine(
        transitions=ElectricChargerMonitor.transitions,
        states=ElectricChargerMonitor.states,
        obj=electric_charger_monitor_obj,
        name=ElectricChargerMonitor.MACHINE_ID,
    )
    electric_charger_monitor_obj.stm = electric_charger_monitor_stm

    electric_charger_signal_led_stm = Machine(
        transitions=ElectricChargerSignalLED.transitions,
        states=ElectricChargerSignalLED.states,
        obj=electric_charger_signal_led_obj,
        name=ElectricChargerSignalLED.MACHINE_ID,
    )
    electric_charger_signal_led_obj.stm = electric_charger_signal_led_stm

    electric_charger_stm = Machine(
        transitions=ElectricCharger.transitions,
        states=ElectricCharger.states,
        obj=electric_charger_obj,
        name=ElectricCharger.MACHINE_ID,
    )
    electric_charger_obj.stm = electric_charger_stm

    # Initialize and configure driver
    driver = Driver()
    driver.add_machine(electric_charger_monitor_stm)
    driver.add_machine(electric_charger_stm)
    driver.add_machine(electric_charger_signal_led_stm)

    # Initialize and assign clients
    monitor_client = ElectricChargerMonitorClient()
    electric_charger_monitor_obj.mqtt_client = monitor_client.client
    monitor_client.stm_driver = driver

    charger_client = ElectricChargerClient()
    electric_charger_obj.mqtt_client = charger_client.client
    charger_client.stm_driver = driver
    electric_charger_obj.driver = driver

    # Start driver and clients
    driver.start()
    monitor_client.start(broker, port)
    charger_client.start(broker, port)

    # https://stackoverflow.com/questions/66514500/how-do-i-configure-a-python-server-for-post
    class handler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data_str = post_data.decode("utf-8")

            print("Received request:", data_str)

            data = json.loads(data_str)

            monitor_client.client.publish(
                MQTT_CHARGER_INPUT_TOPIC,
                ElectricCharger.WEBSERVER_CHARGER_CONFIG_TRIGGER
                + ","
                + str(data["percentage"])
                + ","
                + str(data["goal"]),
            )

            self.send_response(200)
            self.send_header("Content-type", "text")
            self.end_headers()

            message = "Ok"
            self.wfile.write(bytes(message, "utf8"))

    with HTTPServer(("", 8000), handler) as server:
        server.serve_forever()
