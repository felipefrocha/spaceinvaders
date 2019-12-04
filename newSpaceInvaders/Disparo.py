
import threading
import turtle
from time import sleep

from constants import *

class Disparo(threading.Thread):
    def __init__(self, threadId, posx, posy):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.__stop = threading.Event()
        self.speed = 10
        self.posy = posy
        self.posx = posx


    def move_up(self):
        while self.posy < MAX_POSY and not self.is_colision((self.threadId,self.posx,self.posy)):
            self.posy = self.posy+self.speed

    def stop(self):
        self.__stop.set()

    def stopped(self):
        return self.__stop.is_set()

    def move_down(self):
        while self.posy > MIN_POSY and not self.is_colision_enemy((self.threadId, self.posx, self.posy)):
            sleep(0.3)
            self.posy = self.posy-self.speed

    def is_colision(self, point):
        for enemy in INVADERS_POS:
            if abs(enemy[1]-point[1]) < 10 and abs(enemy[2] - point[2]) < 10:
                enemy = (enemy[0], enemy[1], enemy[2], True)
                return True
        return False

    def is_colision_enemy(self, point):
        if abs(PLAYER_POS[0][1] - point[1]) < 20 and abs(PLAYER_POS[0][2] - point[2]) < 20:
            PLAYER_POS[0] = (PLAYER_POS[0][0],PLAYER_POS[0][1],PLAYER_POS[0][2],True)
            return True
        return False

