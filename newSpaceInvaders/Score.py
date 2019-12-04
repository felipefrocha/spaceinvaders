import logging
import turtle
import threading
import _thread
from concurrent.futures import thread
from time import sleep


class Score:

    def __init__(self,points = 0,posx = -290,posy = 280,color = 'white'):
        self.points = points
        self.score_pen = turtle.Turtle()
        self.__posx = posx
        self.__posy = posy
        self.color = color
        self.score_draw()
        self.turn_log_off = False
        self.logger = _thread.start_new_thread(self.score_log, ())
    # Draw the score
    def score_draw(self):
        self.score_pen.speed(0)
        self.score_pen.color(self.color)
        self.score_pen.penup()
        self.score_pen.setposition(self.__posx,self.__posy)
        self.update_score()
        self.score_display()
        self.score_pen.hideturtle()

    def __del__(self):
        self.turn_log_off = True
        self.logger.join()

    def clear(self):
        self.score_pen.clear()

    def score_display(self):
        self.score_pen.write(self.scorestring, False, align="left", font=("Arial", 14, "normal"))

    def add_point(self,point):
        self.points += point
        self.update_score()

    def update_score(self):
        self.scorestring = "Score: %s" % self.points
        self.score_pen.write(self.scorestring, False, align="left", font=("Arial", 14, "normal"))

    def score_log(self):
        log = logging.getLogger('GAME.SCORE')
        while not self.turn_log_off:
            log.info('O placar atual é: {}'.format(self.points))
            sleep(5)

