from turtle import Screen, Turtle
from random import randint
from threading import Thread, active_count
from queue import Queue

QUEUE_SIZE = 2
ENEMY_SPEED = 3

def move_enemy_horizontally(enemy, direction):
    x, y = enemy.position()

    while True:
        while direction == "right":

            if x > 288:
                y -= 50
                actions.put((enemy.sety, y))
                direction = "left"
            else:
                x += ENEMY_SPEED
                actions.put((enemy.setx, x))

        while direction == "left":
            if x < -288:
                y -= 50
                actions.put((enemy.sety, y))
                direction = "right"
            else:
                x -= ENEMY_SPEED
                actions.put((enemy.setx, x))

def process_queue():
    while not actions.empty():
        action, argument = actions.get()
        action(argument)

    if active_count() > 1:
        screen.ontimer(process_queue, 100)

actions = Queue(QUEUE_SIZE)

x, y = randint(-200, 200), randint(100, 200)

direction = "right"

for dy in range(2):
    for dx in range(2):
        enemy = Turtle("turtle", visible=False)
        enemy.speed(0)
        enemy.setheading(270)
        enemy.penup()
        enemy.setposition(x + dx * 60, y + dy * 100)
        enemy.showturtle()

        Thread(target=move_enemy_horizontally, args=(enemy, direction), daemon=True).start()

    direction = ["left", "right"][direction == "left"]

screen = Screen()

process_queue()

screen.mainloop()