import streamlit as st
import streamlit.components.v1 as components
import pygame
import math
import random
import threading
import time
import pygbag  # Import pygbag

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
font = pygame.font.Font(None, 24)

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
            if distance == 0:
                distance = 0.001
            angle = math.atan2(dy, dx)
            overlap = self.radius + other.radius - distance
            self.x += math.cos(angle) * overlap / 2
            self.y += math.sin(angle) * overlap / 2
            other.x -= math.cos(angle) * overlap / 2
            other.y -= math.sin(angle) * overlap / 2

            normal_x, normal_y = dx / distance, dy / distance
            tangent_x, tangent_y = -normal_y, normal_x
            dp_tan_1 = self.velocity[0] * tangent_x + self.velocity[1] * tangent_y
            dp_tan_2 = other.velocity[0] * tangent_x + other.velocity[1] * tangent_y
            dp_norm_1 = self.velocity[0] * normal_x + self.velocity[1] * normal_y
            dp_norm_2 = other.velocity[0] * normal_x + other.velocity[1] * normal_y
            m1, m2 = self.radius, other.radius
            new_dp_norm_1 = (dp_norm_1 * (m1 - m2) + 2 * m2 * dp_norm_2) / (m1 + m2)
            new_dp_norm_2 = (dp_norm_2 * (m2 - m1) + 2 * m1 * dp_norm_1) / (m1 + m2)
            self.velocity[0] = tangent_x * dp_tan_1 + normal_x * new_dp_norm_1
            self.velocity[1] = tangent_y * dp_tan_1 + normal_y * new_dp_norm_1
            other.velocity[0] = tangent_x * dp_tan_2 + normal_x * new_dp_norm_2
            other.velocity[1] = tangent_y * dp_tan_2 + normal_y * new_dp_norm_2

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
        self.x = max(self.radius, min(self.x, WIDTH - self.radius))
        self.y = max(self.radius, min(self.y, HEIGHT - self.radius))

        if self.x <= self.radius or self.x >= WIDTH - self.radius:
            self.velocity[0] *= -BALL_BOUNCE
        if self.y <= self.radius or self.y >= HEIGHT - self.radius:
            self.velocity[1] *= -BALL_BOUNCE

    def collide(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        distance = math.sqrt(dx**2 + dy**2)
        if distance < self.radius + other.radius:
            if distance == 0:distance = 0.001
            angle = math.atan2(dy, dx)
            overlap = self.radius + other.radius - distance
            self.x += math.cos(angle) * overlap / 2
            self.y += math.sin(angle) * overlap / 2
            other.x -= math.cos(angle) * overlap / 2
            other.y -= math.sin(angle) * overlap / 2

            normal_x, normal_y = dx / distance, dy / distance
            tangent_x, tangent_y = -normal_y, normal_x
            dp_tan_1 = self.velocity[0] * tangent_x + self.velocity[1] * tangent_y
            dp_tan_2 = other.velocity[0] * tangent_x + other.velocity[1] * tangent_y
            dp_norm_1 = self.velocity[0] * normal_x + self.velocity[1] * normal_y
            dp_norm_2 = other.velocity[0] * normal_x + other.velocity[1] * normal_y
            m1, m2 = self.radius, other.radius
            new_dp_norm_1 = (dp_norm_1 * (m1 - m2) + 2 * m2 * dp_norm_2) / (m1 + m2)
            new_dp_norm_2 = (dp_norm_2 * (m2 - m1) + 2 * m1 * dp_norm_1) / (m1 + m2)
            self.velocity[0] = tangent_x * dp_tan_1 + normal_x * new_dp_norm_1 * BALL_IMPACT_MULTIPLIER
            self.velocity[1] = tangent_y * dp_tan_1 + normal_y * new_dp_norm_1 * BALL_IMPACT_MULTIPLIER
            other.velocity[0] = tangent_x * dp_tan_2 + normal_x * new_dp_norm_2 * BALL_IMPACT_MULTIPLIER
            other.velocity[1] = tangent_y * dp_tan_2 + normal_y * new_dp_norm_2 * BALL_IMPACT_MULTIPLIER

players = [
    Player(100, HEIGHT // 2, BLUE, {'left': pygame.K_a, 'right': pygame.K_d, 'up': pygame.K_w, 'down': pygame.K_s, 'shoot': pygame.K_SPACE}, AUTO_AIM_PLAYER),
    Player(WIDTH - 100, HEIGHT // 2, RED, {'left': pygame.K_LEFT, 'right': pygame.K_RIGHT, 'up': pygame.K_UP, 'down': pygame.K_DOWN, 'shoot': pygame.K_RETURN}, AUTO_AIM_BALL)
]
ball = Ball(WIDTH // 2, HEIGHT // 2, YELLOW)
goalposts = [pygame.Rect(0, HEIGHT // 3, 10, HEIGHT // 3), pygame.Rect(WIDTH - 10, HEIGHT // 3, 10, HEIGHT // 3)]

running = True
while running:
    clock.tick(60)
    screen.fill(BLACK)

    # Help Caption (Auto-Aim Only)
    help_text = [
        "Auto-Aim Controls:",
        "Player 1 (Blue):",
        "  1: No Auto-Aim",
        "  2: Aim Player",
        "  3: Aim Ball",
        "Player 2 (Red):",
        "  4: No Auto-Aim",
        "  5: Aim Player",
        "  6: Aim Ball"
    ]

    y_offset = 10
    for line in help_text:
        text_surface = font.render(line, True, WHITE)
        screen.blit(text_surface, (10, y_offset))
        y_offset += 20

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                players[0].shoot((players[1].x, players[1].y), ball_pos=(ball.x, ball.y), players=players)
            if event.key == pygame.K_RETURN:
                players[1].shoot((players[0].x, players[0].y), ball_pos=(ball.x, ball.y), players=players)
            if event.key == pygame.K_1:
                players[0].auto_aim = NO_AUTO_AIM
            if event.key == pygame.K_2:
                players[0].auto_aim = AUTO_AIM_PLAYER
            if event.key == pygame.K_3:
                players[0].auto_aim = AUTO_AIM_BALL
            if event.key == pygame.K_4:
                players[1].auto_aim = NO_AUTO_AIM
            if event.key == pygame.K_5:
                players[1].auto_aim = AUTO_AIM_PLAYER
            if event.key == pygame.K_6:
                players[1].auto_aim = AUTO_AIM_BALL

    for i, player in enumerate(players):
        player.move()
        ball.collide(player)
        for j in range(i + 1, len(players)):
            player2 = players[j]
            if player.radius + player2.radius > math.sqrt((player.x - player2.x)**2 + (player.y - player2.y)**2):
                player.player_collide(player2)

    all_bullets = players[0].bullets[:] + players[1].bullets[:]

    for i, bullet1 in enumerate(all_bullets):
        for j in range(i + 1, len(all_bullets)):
            bullet2 = all_bullets[j]
            if bullet1.radius + bullet2.radius > math.sqrt((bullet1.x - bullet2.x)**2 + (bullet1.y - bullet2.y)**2):
                if bullet1.get_damage() < bullet2.get_damage():
                    for p in players:
                        if bullet1 in p.bullets:
                            p.bullets.remove(bullet1)
                else:
                    for p in players:
                        if bullet2 in p.bullets:
                            p.bullets.remove(bullet2)

    for player in players:
        for bullet in player.bullets[:]:
            bullet.move()
            for other_player in players:
                if other_player != player and bullet.radius + other_player.radius > math.sqrt((bullet.x - other_player.x)**2 + (bullet.y - other_player.y)**2):
                    damage = bullet.get_damage()
                    other_player.health -= damage
                    player.bullets.remove(bullet)
                    if other_player.health <= 0:
                        other_player.frozen = FREEZE_TIME
                ball.collide(bullet)

    ball.move()

    for idx, goal in enumerate(goalposts):
        if goal.colliderect(pygame.Rect(ball.x - ball.radius, ball.y - ball.radius, ball.radius * 2, ball.radius * 2)):
            players[idx ^ 1].score += 1
            ball.x, ball.y = WIDTH // 2, HEIGHT // 2
            ball.velocity = [0, 0]
            if players[idx ^ 1].score >= GOAL_SCORE:
                winner_text = font.render(f"Player {idx ^ 1 + 1} wins!", True, WHITE)
                winner_rect = winner_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
                screen.blit(winner_text, winner_rect)
                pygame.display.flip()
                pygame.time.delay(3000)
                running = False

    for player in players:
        pygame.draw.circle(screen, player.color, (int(player.x), int(player.y)), player.radius)
        pygame.draw.rect(screen, RED, (player.x - 20, player.y - 30, 40, 5))
        pygame.draw.rect(screen, GREEN, (player.x - 20, player.y - 30, int(40 * player.health / player.max_health), 5))
        score_text = font.render(f"Score: {player.score}", True, WHITE)
        screen.blit(score_text, (player.x - 20, player.y - 45))
    for player in players:
        for bullet in player.bulletspygame.draw.circle(screen, bullet.color, (int(bullet.x), int(bullet.y)), bullet.radius)

    pygame.draw.circle(screen, ball.color, (int(ball.x), int(ball.y)), ball.radius)
    for goal in goalposts:
        pygame.draw.rect(screen, WHITE, goal)

    pygame.display.flip()
pygame.quit()


def run_game():
    main()

if __name__ == "__main__":
    st.title("Ball Game")

    if st.button("Start Game"):
        # Compile with pygbag
        import subprocess
        subprocess.run(["pygbag", __file__, "-o", "pygbag_output"], check=True)

        # Embed the game
        components.html(
            open("pygbag_output/index.html", 'r', encoding='utf-8').read(),
            width=800,
            height=600,
            scrolling=False,
        )
