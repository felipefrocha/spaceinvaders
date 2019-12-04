import _thread
import logging
import random
import threading
import turtle
from time import sleep

from Disparo import Disparo
from constants import *


class Enemy(threading.Thread):
    color = 'red'
    enemies = 0
    disparo = None
    index = None
    removed = None
    log = logging.getLogger('MAIN.ENEMY')


    def __init__(self, threadId, posx=-280, posy=-250):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.__stop = threading.Event()
        self.posx = posx
        self.posy = posy
        self.speed = 2
        self.new_enemy()

    def stop(self):
        self.__stop.set()

    def stopped(self):
        return self.__stop.is_set()

    def join(self, timeout=1):
        self.destroy_enemy()
        self.log.info('Destruindo inimigo {}'.format(self.threadId))
        sleep(0.5)
        super().join(timeout)

    def run(self):
        INVADERS_POS.append((self.threadId, self.posx, self.posy, False))
        while not self.stopped():
            sleep(0.1)
            sem.acquire()
            self.move_draw()
            sem.release()

    @classmethod
    def new_enemy(self):
        self.enemies += 1

    @classmethod
    def destroy_enemy(self):
        self.enemies -= 1

    def move_draw(self):
        # Move the draw
        num = random.randint(1, 100) % 50
        if num == 0:
            self.fire_bullet()
        x = self.posx
        x += self.speed
        self.posx = x
        # Move the draw back and down
        if self.posx > MAX_POSX or self.posx < MIN_POSX:
            # Change draw direction
            self.speed *= -1
            y = self.posy
            y -= STEP_POSY
            self.posy = y
        self.update_position()

    def fire_bullet(self):
        sleep(random.random()*10)
        self.disparo = Disparo(random.randint(21, 30), self.posx, self.posy + 10)
        self.disparo.start()
        self.disparo.move_down()

    def update_position(self):
        try:
            self.log.debug('Tamanho do invaders é {}'.format(len(INVADERS_POS)))
            lock.acquire()

            self.index = (INVADERS_POS.index([item for item in INVADERS_POS if item[0] == self.threadId][0])) \
                if len(INVADERS_POS) > 0 \
                else None
            if self.index is not None:
                if INVADERS_POS[self.index][3]:
                    self.stop()
                INVADERS_POS[self.index] = (self.threadId, self.posx, self.posy, INVADERS_POS[self.index][3])
            else:
                self.log.debug('Valor de index invalido ou não encontrado')
            lock.release()

        except Exception as ex:
            self.log.info('Enemy error {}'.format(ex))
