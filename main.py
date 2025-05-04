import pygame
import math
import random
import sys

# Constants
WIDTH, HEIGHT = 800, 600
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
BLACK = (0, 0, 0)
FRICTION = 0.90
BALL_FRICTION = 0.97
BULLET_SPEED = 8
PLAYER_SPEED = 3
BULLET_DAMAGE = 20
FREEZE_TIME = 180
GOAL_SCORE = 5
BALL_IMPACT_MULTIPLIER = 1.2
BALL_BOUNCE = 0.8
DAMAGE_DECAY = 0.01
AUTO_AIM_PLAYER = 1
AUTO_AIM_BALL = 2
NO_AUTO_AIM = 0

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Soccer Shooter Game")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)
small_font = pygame.font.Font(None, 24)

class Player:
    def __init__(self, x, y, color, keys, auto_aim=NO_AUTO_AIM):
        self.x, self.y = x, y
        self.radius = 20
        self.color = color
        self.velocity = [0, 0]
        self.health = 100
        self.max_health = 100
        self.bullets = []
        self.score = 0
        self.frozen = 0
        self.keys = keys
        self.auto_aim = auto_aim
        self.previous_health = self.health

    def move(self):
        if self.frozen > 0:
            self.frozen -= 1
            if self.frozen == 0:
                self.health = self.max_health
            return
        
        keys = pygame.key.get_pressed()
        if keys[self.keys['left']]:
            self.velocity[0] -= PLAYER_SPEED
        if keys[self.keys['right']]:
            self.velocity[0] += PLAYER_SPEED
        if keys[self.keys['up']]:
            self.velocity[1] -= PLAYER_SPEED
        if keys[self.keys['down']]:
            self.velocity[1] += PLAYER_SPEED

        self.velocity[0] *= FRICTION
        self.velocity[1] *= FRICTION
        self.x += int(self.velocity[0])
        self.y += int(self.velocity[1])
        
        # Boundary checking
        self.x = max(self.radius, min(self.x, WIDTH - self.radius))
        self.y = max(self.radius, min(self.y, HEIGHT - self.radius))

    def shoot(self, target, ball_pos=None, players=None):
        if self.frozen > 0:
            return

        if self.auto_aim == AUTO_AIM_PLAYER and players:
            closest_player = None
            closest_dist = float('inf')
            for other_player in players:
                if other_player != self:
                    dist = math.sqrt((self.x - other_player.x)**2 + (self.y - other_player.y)**2)
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_player = other_player
            if closest_player:
                target = (closest_player.x, closest_player.y)
        elif self.auto_aim == AUTO_AIM_BALL and ball_pos:
            target = ball_pos

        self.bullets.append(Bullet(self.x, self.y, self.color, target, self.x, self.y))

    def player_collide(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance < self.radius + other.radius:
            if distance == 0:  # Avoid division by zero
                distance = 0.001
                dx, dy = 0.001, 0
            
            # Separate the players
            overlap = (self.radius + other.radius - distance) / 2
            self.x += overlap * dx / distance
            self.y += overlap * dy / distance
            other.x -= overlap * dx / distance
            other.y -= overlap * dy / distance

            # Calculate collision response
            nx, ny = dx / distance, dy / distance
            p = 2 * (self.velocity[0] * nx + self.velocity[1] * ny - 
                    other.velocity[0] * nx - other.velocity[1] * ny) / (self.radius + other.radius)
            
            self.velocity[0] = self.velocity[0] - p * other.radius * nx
            self.velocity[1] = self.velocity[1] - p * other.radius * ny
            other.velocity[0] = other.velocity[0] + p * self.radius * nx
            other.velocity[1] = other.velocity[1] + p * self.radius * ny

class Bullet:
    def __init__(self, x, y, color, target, shooter_x, shooter_y):
        self.x, self.y = x, y
        self.radius = 4
        self.color = color
        angle = pygame.math.Vector2(target[0] - x, target[1] - y).normalize()
        self.velocity = angle * BULLET_SPEED
        self.shooter_x = shooter_x
        self.shooter_y = shooter_y
        self.initial_damage = BULLET_DAMAGE

    def move(self):
        self.x += self.velocity.x
        self.y += self.velocity.y

    def get_damage(self):
        distance_from_shooter = math.sqrt((self.x - self.shooter_x)**2 + (self.y - self.shooter_y)**2)
        damage = max(1, self.initial_damage - distance_from_shooter * DAMAGE_DECAY)
        return damage

class Ball:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.color = color
        self.radius = 15
        self.velocity = [0, 0]

    def move(self):
        self.x += self.velocity[0]
        self.y += self.velocity[1]
        self.velocity[0] *= BALL_FRICTION
        self.velocity[1] *= BALL_FRICTION
        
        # Boundary checking with bounce
        if self.x <= self.radius:
            self.x = self.radius
            self.velocity[0] *= -BALL_BOUNCE
        elif self.x >= WIDTH - self.radius:
            self.x = WIDTH - self.radius
            self.velocity[0] *= -BALL_BOUNCE
            
        if self.y <= self.radius:
            self.y = self.radius
            self.velocity[1] *= -BALL_BOUNCE
        elif self.y >= HEIGHT - self.radius:
            self.y = HEIGHT - self.radius
            self.velocity[1] *= -BALL_BOUNCE

    def collide(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance < self.radius + other.radius:
            if distance == 0:  # Avoid division by zero
                distance = 0.001
                dx, dy = 0.001, 0
            
            # Separate the objects
            overlap = (self.radius + other.radius - distance) / 2
            self.x += overlap * dx / distance
            self.y += overlap * dy / distance
            other.x -= overlap * dx / distance
            other.y -= overlap * dy / distance

            # Calculate collision response
            nx, ny = dx / distance, dy / distance
            p = 2 * (self.velocity[0] * nx + self.velocity[1] * ny - 
                    other.velocity[0] * nx - other.velocity[1] * ny) / (self.radius + other.radius)
            
            # Apply impact multiplier only to the ball
            self.velocity[0] = (self.velocity[0] - p * other.radius * nx) * BALL_IMPACT_MULTIPLIER
            self.velocity[1] = (self.velocity[1] - p * other.radius * ny) * BALL_IMPACT_MULTIPLIER
            other.velocity[0] = other.velocity[0] + p * self.radius * nx
            other.velocity[1] = other.velocity[1] + p * self.radius * ny

def reset_game():
    global players, ball
    players = [
        Player(100, HEIGHT // 2, BLUE, 
              {'left': pygame.K_a, 'right': pygame.K_d, 'up': pygame.K_w, 'down': pygame.K_s, 'shoot': pygame.K_SPACE}, 
              AUTO_AIM_PLAYER),
        Player(WIDTH - 100, HEIGHT // 2, RED, 
              {'left': pygame.K_LEFT, 'right': pygame.K_RIGHT, 'up': pygame.K_UP, 'down': pygame.K_DOWN, 'shoot': pygame.K_RETURN}, 
              AUTO_AIM_BALL)
    ]
    ball = Ball(WIDTH // 2, HEIGHT // 2, YELLOW)

def draw_goals():
    # Left goal
    pygame.draw.rect(screen, WHITE, (0, HEIGHT // 3, 10, HEIGHT // 3))
    # Right goal
    pygame.draw.rect(screen, WHITE, (WIDTH - 10, HEIGHT // 3, 10, HEIGHT // 3))

def check_goal():
    # Left goal
    if ball.x - ball.radius <= 0 and HEIGHT // 3 <= ball.y <= HEIGHT * 2 // 3:
        players[1].score += 1
        return 1
    
    # Right goal
    if ball.x + ball.radius >= WIDTH and HEIGHT // 3 <= ball.y <= HEIGHT * 2 // 3:
        players[0].score += 1
        return 2
    
    return 0

def show_winner(winner_idx):
    winner_text = font.render(f"Player {winner_idx + 1} wins!", True, WHITE)
    screen.blit(winner_text, (WIDTH // 2 - winner_text.get_width() // 2, HEIGHT // 2 - 18))
    restart_text = small_font.render("Press R to restart or Q to quit", True, WHITE)
    screen.blit(restart_text, (WIDTH // 2 - restart_text.get_width() // 2, HEIGHT // 2 + 18))
    pygame.display.flip()
    
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    waiting = False
                    reset_game()
                elif event.key == pygame.K_q:
                    pygame.
