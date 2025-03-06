import pygame
import math
import time
import os

# Initialize Pygame
pygame.init()

# Constants
WIDTH, HEIGHT = 800, 500
PLAYER_SIZE = 20
BALL_SIZE = 15
BULLET_SIZE = 5
PLAYER_SPEED = 4
BULLET_SPEED = 6
MAX_BULLETS = 6
GOAL_WIDTH = 100
GOAL_HEIGHT = 120
HEALTH = 100
BALL_SPEED = 3
BULLET_LIFETIME = 50
WINNING_SCORE = 5

# Colors
WHITE = (255, 255, 255)
GREEN = (0, 128, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)

# Pygame setup
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Web Soccer Shooter")
clock = pygame.time.Clock()

# Player Class
class Player:
    def __init__(self, x, y, color, controls):
        self.x, self.y = x, y
        self.color = color
        self.bullets = []
        self.controls = controls
        self.health = HEALTH
        self.angle = 0
        self.reload = 0
        self.score = 0

    def move(self, keys):
        if keys[self.controls['up']] and self.y > 0:
            self.y -= PLAYER_SPEED
        if keys[self.controls['down']] and self.y < HEIGHT:
            self.y += PLAYER_SPEED
        if keys[self.controls['left']] and self.x > 0:
            self.x -= PLAYER_SPEED
        if keys[self.controls['right']] and self.x < WIDTH:
            self.x += PLAYER_SPEED

    def auto_aim(self, target):
        dx = target.x - self.x
        dy = target.y - self.y
        self.angle = math.degrees(math.atan2(dy, dx))

    def shoot(self):
        if len(self.bullets) < MAX_BULLETS and self.reload == 0:
            rad = math.radians(self.angle)
            vx = BULLET_SPEED * math.cos(rad)
            vy = BULLET_SPEED * math.sin(rad)
            self.bullets.append([self.x, self.y, vx, vy, BULLET_LIFETIME])
            self.reload = 20

    def update_bullets(self):
        for bullet in self.bullets[:]:
            bullet[0] += bullet[2]
            bullet[1] += bullet[3]
            bullet[4] -= 1
            if bullet[0] < 0 or bullet[0] > WIDTH or bullet[1] < 0 or bullet[1] > HEIGHT or bullet[4] <= 0:
                self.bullets.remove(bullet)

    def update_reload(self):
        if self.reload > 0:
            self.reload -= 1

# Ball Class
class Ball:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x, self.y = WIDTH // 2, HEIGHT // 2
        self.vx, self.vy = 0, 0

    def move(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.98
        self.vy *= 0.98
        if self.x - BALL_SIZE < 0 or self.x + BALL_SIZE > WIDTH:
            self.vx *= -1
        if self.y - BALL_SIZE < 0 or self.y + BALL_SIZE > HEIGHT:
            self.vy *= -1

    def check_collision(self, player):
        distance = math.hypot(self.x - player.x, self.y - player.y)
        if distance < PLAYER_SIZE + BALL_SIZE and distance != 0:
            self.vx = (self.x - player.x) / distance * BALL_SPEED
            self.vy = (self.y - player.y) / distance * BALL_SPEED

# Initialize objects
player1 = Player(100, HEIGHT // 2, RED, {'up': pygame.K_w, 'down': pygame.K_s, 'left': pygame.K_a, 'right': pygame.K_d, 'shoot': pygame.K_f})
player2 = Player(700, HEIGHT // 2, BLUE, {'up': pygame.K_UP, 'down': pygame.K_DOWN, 'left': pygame.K_LEFT, 'right': pygame.K_RIGHT, 'shoot': pygame.K_RSHIFT})
ball = Ball()

# Game loop
running = True
while running:
    screen.fill(GREEN)
    keys = pygame.key.get_pressed()
    player1.move(keys)
    player2.move(keys)
    player1.auto_aim(player2)
    player2.auto_aim(player1)
    player1.update_reload()
    player2.update_reload()
    player1.update_bullets()
    player2.update_bullets()
    if keys[player1.controls['shoot']]:
        player1.shoot()
    if keys[player2.controls['shoot']]:
        player2.shoot()
    ball.move()
    ball.check_collision(player1)
    ball.check_collision(player2)
    
    # Draw objects
    pygame.draw.circle(screen, RED, (player1.x, player1.y), PLAYER_SIZE)
    pygame.draw.circle(screen, BLUE, (player2.x, player2.y), PLAYER_SIZE)
    pygame.draw.circle(screen, WHITE, (int(ball.x), int(ball.y)), BALL_SIZE)
    for bullet in player1.bullets:
        pygame.draw.circle(screen, RED, (int(bullet[0]), int(bullet[1])), BULLET_SIZE)
    for bullet in player2.bullets:
        pygame.draw.circle(screen, BLUE, (int(bullet[0]), int(bullet[1])), BULLET_SIZE)

    pygame.display.flip()
    clock.tick(60)
