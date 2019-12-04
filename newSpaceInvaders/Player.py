import _thread
import logging
import random
import threading
import turtle
from time import sleep

from Disparo import Disparo
from constants import *


class Player(threading.Thread):
    disparo = None
    def __init__(self, threadId, posx=0, posy=MIN_POSY):
        threading.Thread.__init__(self)
        self.__stop = threading.Event()
        self.threadId = threadId
        self.draw = turtle.Turtle()
        self.draw.shape('triangle')
        self.draw.color("blue")
        self.draw.penup()
        self.draw.speed(0)
        self.draw.setposition(posx, posy)
        self.draw.setheading(90)
        self.speed = 15
        self.share_position()

    def stop(self):
        self.draw.hideturtle()
        self.__stop.set()

    def stopped(self):
        return self.__stop.is_set()

    def join(self, timeout=1):
        log = logging.getLogger('MAIN.PLAYER')
        log.info('Jogador foi destruído: HA! LOSER rs')
        sleep(1)
        super().join(timeout)

    def move_left(self):
        x = self.draw.xcor()
        x -= self.speed
        if x < MIN_POSX:
            x = MIN_POSX
        self.share_position()
        self.draw.setx(x)

    def share_position(self):
        if PLAYER_POS[0][3]:
            self.stop()
        PLAYER_POS.clear()
        PLAYER_POS.append((1, self.draw.xcor(), self.draw.ycor(),False))

    def move_right(self):
        x = self.draw.xcor()
        x += self.speed
        if x > MAX_POSX:
            x = MAX_POSX
        self.share_position()
        self.draw.setx(x)

    def fire_bullet(self):
        self.disparo = Disparo(random.randint(21, 30), self.draw.xcor(), self.draw.ycor() + 10)
        self.disparo.start()
        self.disparo.move_up()



