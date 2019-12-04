import asyncio
import queue
import threading


sem = threading.BoundedSemaphore()
sem1 = threading.Semaphore(1)
lock = threading.BoundedSemaphore()

def move_object(object,posx,posy):
    object.setx(object.xcor()+posx)
    object.sety(object.ycor()+posy)


BULLET_POS = []
PLAYER_POS = [(0,0,0,False)]
INVADERS_POS = []
# game constants

MAX_POSX = 280
MIN_POSX = -280
MIN_POSY = -280
MAX_POSY = 270

STEP_POSY = 20

QUEUE_SIZE = 1
ENEMY_SPEED = 3
BULLET_SEED = 20
BULLET_RATIO = 600
ENEMY_STEP_Y = 30
# log server constants
READ = 'rt'
LOG_PATH = 'logConfig.yaml'
LOG_NAME = 'log.txt'
FORMAT = '%(asctime)s - [%(levelname)8s] | [%(name)15s] - %(message)s'
