from stmpy import Driver, Machine

from threading import Thread

from globals import *

from ChargePark import *

import paho.mqtt.client as mqtt

class ElectricCar:
    MACHINE_ID = "electric_car" 

    mqtt_client: mqtt.Client

    stm: Machine

    CONNECT_TRIGGER = "connect"
    DISCONNECT_TRIGGER = "disconnect"

    transitions = [
        {
            "source": "initial",
            "target": "s_standby",
            "effect": "on_init()"
        },
        {
            "trigger": CONNECT_TRIGGER,
            "source": "s_standby",
            "target": "s_standby",
            "effect": "connect_plug()"
        },
        {
            "trigger": DISCONNECT_TRIGGER,
            "source": "s_standby",
            "target": "s_standby",
            "effect": "disconnect_plug()"
        },
    ]


    def on_init(self):
        print("Init!")
    
    def connect_plug(self):
        print("Connect!")
        self.mqtt_client.publish(MQTT_CHARGER_INPUT_TOPIC, ElectricCharger.CONNECT_PLUG_TRIGGER)
    
    def disconnect_plug(self):
        print("Disconnect!")
        self.mqtt_client.publish(MQTT_CHARGER_INPUT_TOPIC, ElectricCharger.DISCONNECT_PLUG_TRIGGER)


class ElectricCarClient:

    stm_driver: Driver
    MQTT_TOPIC_OUTPUT = 'ttm4115/team_04/car'

    def __init__(self):
        self.count = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print("on_connect(): {}".format(mqtt.connack_string(rc)))



    def on_message(self, client, userdata, msg):
        msg.payload.decode("utf-8")
        trigger : str = msg.topic[msg.topic.index("/")+1:]
        print("Subtopic:", trigger)
        self.stm_driver.send(trigger, ElectricCar.MACHINE_ID, msg.payload.decode("utf-8") if msg.payload else None)

    def start(self, broker, port):

        print("Connecting to {}:{}".format(broker, port))
        self.client.connect(broker, port)
        # self.client.subscribe("buzzers/+")

        try:
            thread = Thread(target=self.client.loop_forever)
            thread.start()
        except KeyboardInterrupt:
            self.client.disconnect()
            thread.join()





if __name__ == "__main__":
    broker, port = 'test.mosquitto.org', 1883
    
    electric_car = ElectricCar()
    electric_car_stm = Machine(transitions=ElectricCar.transitions, obj=electric_car, name=electric_car.MACHINE_ID)
    electric_car.stm = electric_car_stm


    driver = Driver()
    driver.add_machine(electric_car_stm)
    myclient = ElectricCarClient()

    electric_car.mqtt_client = myclient.client
    myclient.stm_driver = driver

    driver.start()
    myclient.start(broker, port)

    toggle = True

    while True:
        if (toggle):
            input('Press enter to connect"\n')
            myclient.stm_driver.send(ElectricCar.CONNECT_TRIGGER, ElectricCar.MACHINE_ID)
        else:
            input('Press enter to disconnect"\n')
            myclient.stm_driver.send(ElectricCar.DISCONNECT_TRIGGER, ElectricCar.MACHINE_ID)

        toggle = not toggle

