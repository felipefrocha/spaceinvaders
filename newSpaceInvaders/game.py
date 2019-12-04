import multiprocessing
import time
import turtle
import logging
import logging.handlers

import random

from turtle import Screen, Turtle
from random import randint
from threading import Thread, active_count
from queue import Queue

from constants import *

import logServer
from Player import Player, Disparo
from Score import Score
from Enemy import Enemy


#
# def game():
#     global number_of_enemies
#     global player_bullet
#     global game_over
#
#     log = logging.getLogger('MAIN.GAME')
#     log.info('Inicializando definições do jogo')
#     game_definitions()
#     log.info('Inicializando definições da tela')
#     screen_definitions()
#     log.info('Inicializando placar')
#     score = Score()
#     log.info('Inicializando player')
#     player = Player(1000)
#     player_bullet = None
#
#     enemies = []
#     number_of_enemies = 1
#
#     player.start()
#
#     def move_left():
#         player.move_left()
#
#     def move_right():
#         player.move_right()
#
#     def fire_bullet():
#         global player_bullet
#         if not player_bullet:
#             player_bullet = create_disparo(player.draw.xcor(), player.draw.ycor())
#             player_bullet.shapesize(0.1, 0.3)
#         player.fire_bullet()
#
#     # Create keyboard bindings
#     turtle.listen()
#     turtle.onkey(move_left, "Left")
#     turtle.onkey(move_right, "Right")
#     turtle.onkey(fire_bullet, "space")
#
#     try:
#         threading.main_thread()
#         # Main game loop
#         while game_over:
#             for i in range(number_of_enemies - len(enemies)):
#                 enemy = create_enemy(log, number_of_enemies)
#                 draw = create_draw('circle', 'red', enemy.posx, enemy.posy)
#                 enemies.append((enemy, draw))
#             for enemy in enemies:
#                 enemy[1].setx(enemy[0].posx)
#                 enemy[1].sety(enemy[0].posy)
#             if player.disparo:
#                 player_bullet.setx(player.disparo.posx)
#                 player_bullet.sety(MIN_POSY + 20)
#         turtle.mainloop()
#
#     except Exception as ex:
#         log.error('wrong closure: {}'.format(ex))
#     finally:
#         del score
#         player.join(1)
#         del player
#         for enemy in enemies:
#             enemy[0].stop()
#             enemy[0].join(1)
#             del enemy
#

def create_enemy(log, number_of_enemies, ):
    log.info('Inicializando enemy {}'.format(number_of_enemies))
    enemy = Enemy(number_of_enemies, MIN_POSX + (random.randint(20, 50)), MAX_POSY - random.randint(20, 50))
    enemy.daemon = True
    enemy.start()
    return enemy


def destroy_enemy(enemy):
    global number_of_enemies
    enemy.stop()
    enemy.join(1)
    number_of_enemies += 1 if number_of_enemies < 20 else 20


def detroy_player(player):
    global game_over
    player.stop()
    player.join(1)
    game_over = False


def screen_definitions():
    # Draw border
    border_pen = turtle.Turtle()
    border_pen.speed(0)
    border_pen.color("white")
    border_pen.penup()
    border_pen.setposition(-300, -300)
    border_pen.pendown()
    border_pen.pensize(3)
    for side in range(4):
        border_pen.fd(600)
        border_pen.lt(90)
    border_pen.hideturtle()


def game_definitions():
    global game_over
    # Set up the screen
    wn = turtle.Screen()
    wn.bgcolor("black")
    wn.title("Space Invaders")
    game_over = True


def init_logger():
    log_server_process = multiprocessing.Process(target=logServer.main)
    log_server_process.start()
    time.sleep(5)

    root_logger = logging.getLogger('')
    root_logger.setLevel(logging.DEBUG)
    socket_handler = logging.handlers \
        .DatagramHandler(
        'localhost',
        logging.handlers.DEFAULT_UDP_LOGGING_PORT
    )

    root_logger.addHandler(socket_handler)

    return log_server_process


def process_queue():
    # events of thread control  single queue to control all updates
    while not actions.empty():
        new_action = actions.get()
        if isinstance(new_action, type((1, 1))):
            action, argument = new_action
            if isinstance(argument, type((1, 1))):
                a_argument, b_argument = argument
                action(a_argument, b_argument)
            else:
                action(argument)
        else:
            new_action()
    if active_count() > 1:
        # Update screen every 100 ms
        screen.ontimer(process_queue, 100)


# function to become thread and control movements, colisions and bullets
def fire_enemy_bullet(bullet, posy):
    global game_over
    actions.put(bullet.showturtle)
    y = posy
    x = bullet.xcor()
    while True:
        if y > MIN_POSY and not is_colision(x,y):
            y -= BULLET_SEED
            actions.put((bullet.sety, y))
        else:
            actions.put(bullet.hideturtle)
            if is_colision(x,y):
                player.stop()
                player.join(1)
                game_over = True
            return


# function to become thread and control movements, colisions and bullets
def fire_player_bullet(bullet, posy):
    global player_bullet_state
    actions.put(bullet.showturtle)
    y = posy
    while True:
        if y < MAX_POSY:
            y += BULLET_SEED
            actions.put((bullet.sety, y))
        else:
            actions.put(bullet.hideturtle)
            player_bullet_state = False
            return


def move_enemy_horizontally(enemy, direction, bullet):
    global game_over
    bullets = None
    x, y = enemy.position()
    while True:
        while direction == "right":
            if (randint(0, 1000)%BULLET_RATIO) == 0 and y > (MIN_POSY + 30):
                actions.put((bullet.setposition, (x, y)))
                bullets = Thread(target=fire_enemy_bullet,
                                 args=(bullet, y),
                                 daemon=True).start()
            if x > MAX_POSX:
                y -= ENEMY_STEP_Y
                actions.put((enemy.sety, y))
                direction = "left"
            else:
                x += ENEMY_SPEED
                actions.put((enemy.setx, x))
            if y < MIN_POSY or is_colision(x, y):
                actions.put(enemy.hideturtle)
                if is_colision_player_bullet(x, y):
                    score.add_point(10)
                if is_colision(x, y):
                    player.stop()
                    player.join(1)
                    game_over = True
                direction = 'exit'

        while direction == "left":
            if (randint(0, 1000)%BULLET_RATIO) == 0 and y > (MIN_POSY + 30):
                actions.put((bullet.setposition, (x, y)))
                bullets = Thread(target=fire_enemy_bullet,
                                 args=(bullet, enemy.ycor()),
                                 daemon=True).start()
            if x < MIN_POSX:
                y -= ENEMY_STEP_Y
                actions.put((enemy.sety, y))
                direction = "right"
            else:
                x -= ENEMY_SPEED
                actions.put((enemy.setx, x))
            if y < MIN_POSY or is_colision(x, y) or is_colision_player_bullet(x, y):
                actions.put(enemy.hideturtle)
                if is_colision_player_bullet(x, y):
                     score.add_point(10)
                if is_colision(x, y):
                    player.stop()
                    player.join(1)
                    game_over = True
                direction = 'exit'
        if direction == 'exit':
            break
    if bullets and bullets.isAlive():
        bullets.join(1)
        return



def is_colision(x, y):
    return (abs(y - player.draw.ycor()) < 15 and abs(x - player.draw.xcor()) < 15)


def is_colision_player_bullet(x, y):
    return (abs(y - player_bullet.ycor()) < 15 and abs(x - player_bullet.xcor()) < 15)


if __name__ == '__main__':
    log_process = init_logger()
    log = logging.getLogger('')
    log.info('O jogo foi inicializado')

    global number_of_enemies
    global player_bullet_state
    global game_over

    log = logging.getLogger('MAIN.GAME')
    log.info('Inicializando definições do jogo')
    game_definitions()
    log.info('Inicializando definições da tela')
    screen_definitions()
    log.info('Inicializando placar')
    score = Score()
    log.info('Inicializando player')
    player = Player(1000)

    player.start()
    player_bullet_state = False



    def move_left():
        player.move_left()


    def move_right():
        player.move_right()


    def fire_bullet():
        global player_bullet_state
        if not player_bullet_state:
            x,y = player.draw.position()
            player_bullet.setposition(x,y)
            player_bullet_state = True
            Thread(target=fire_player_bullet,
                   args=(player_bullet, y),
                   daemon=True).start()


    # Create keyboard bindings
    turtle.listen()
    turtle.onkey(move_left, "Left")
    turtle.onkey(move_right, "Right")
    turtle.onkey(fire_bullet, "space")

    actions = Queue(QUEUE_SIZE)

    x, y = MIN_POSX, MAX_POSY

    direction = "right"

    enemies = []
    player_bullet = Turtle('square', visible=False)
    player_bullet.speed(0)
    player_bullet.color('yellow')
    player_bullet.setheading(270)
    player_bullet.penup()
    player_bullet.shapesize(0.2, 0.3)

    turno = 1
    linhas = 1 if turno < 10 else 2
    for dy in range(linhas):
        for dx in range((turno % 10) + 1):
            enemy = Turtle("turtle", visible=False)
            enemy.speed(0)
            enemy.color('red')
            enemy.setheading(270)
            enemy.penup()
            enemy.setposition(x + dx * 40, y - dy * 40)
            enemy.showturtle()

            bullet = Turtle("turtle", visible=False)
            bullet.shape('square')
            bullet.shapesize(0.3, 0.5)
            bullet.speed(0)
            bullet.color('yellow')
            bullet.setheading(270)
            bullet.penup()
            bullet.setposition(enemy.xcor(), enemy.ycor())
            bullet.hideturtle()

            enemies.append(Thread(
                target=move_enemy_horizontally,
                args=(enemy, direction, bullet),
                daemon=True).start())

        direction = ["left", "right"][direction == "left"]

    screen = Screen()
    process_queue()
    screen.mainloop()

    log.info('O jogo foi encerrado!')
    time.sleep(1)
    log_process.terminate()
    log_process.join(5)
    exit()
