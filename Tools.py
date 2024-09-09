from sense_hat import SenseHat

sense = SenseHat()

sense.show_message("Hello world!")



R = [255, 0, 0]  # Red
G = [0, 255, 0]  # Green
Y = [255, 255, 0]  # Yellow
W = [255, 255, 255]  # White


question_mark = [
R, R, R, W, W, R, R, R,
R, R, W, R, R, W, R, R,
R, R, R, R, R, W, R, R,
R, R, R, R, W, R, R, R,
R, R, R, W, R, R, R, R,
R, R, R, W, R, R, R, R,
R, R, R, R, R, R, R, R,
R, R, R, W, R, R, R, R
]



sense.set_rotation(180)

# Define some colours
n = (0, 0, 0)  # closed
rsin = ((math.sin(time.time()) + 1) / 2)

def check_movement():
    acceleration = sense.get_accelerometer_raw()
    x = acceleration['x']
    y = acceleration['y']
    z = acceleration['z']

    x = abs(x)
    y = abs(y)
    z = abs(z)

    if x > 1 or y > 1 or z > 1:
        sense.show_letter("!", red)
    else:
        sense.clear()

def update_display(color):
    sense.set_pixels([color for _ in range])