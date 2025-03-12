from kivy.app import App
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, Line
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
import random
import math

# Constants
WIDTH, HEIGHT = Window.size
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

class Player(Widget):
    def __init__(self, x, y, color, auto_aim=NO_AUTO_AIM, **kwargs):
        super().__init__(**kwargs)
        self.x, self.y = x, y
        self.radius = 20
        self.color = color
        self.velocity = [0, 0]
        self.health = 100
        self.max_health = 100
        self.bullets = []
        self.score = 0
        self.frozen = 0
        self.auto_aim = auto_aim
        self.previous_health = self.health

    def move(self, dx, dy):
        if self.frozen > 0:
            self.frozen -= 1
            if self.frozen == 0:
                self.health = self.max_health
            return
        self.velocity[0] += dx * PLAYER_SPEED
        self.velocity[1] += dy * PLAYER_SPEED
        self.velocity[0] *= FRICTION
        self.velocity[1] *= FRICTION
        self.x += self.velocity[0]
        self.y += self.velocity[1]
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

class Bullet(Widget):
    def __init__(self, x, y, color, target, shooter_x, shooter_y, **kwargs):
        super().__init__(**kwargs)
        self.x, self.y = x, y
        self.radius = 4
        self.color = color
        angle = math.atan2(target[1] - y, target[0] - x)
        self.velocity = [math.cos(angle) * BULLET_SPEED, math.sin(angle) * BULLET_SPEED]
        self.shooter_x, self.shooter_y = shooter_x, shooter_y
        self.initial_damage = BULLET_DAMAGE

    def move(self):
        self.x += self.velocity[0]
        self.y += self.velocity[1]

    def get_damage(self):
        distance_from_shooter = math.sqrt((self.x - self.shooter_x)**2 + (self.y - self.shooter_y)**2)
        damage = max(1, self.initial_damage - distance_from_shooter * DAMAGE_DECAY)
        return damage

class Ball(Widget):
    def __init__(self, x, y, color, **kwargs):
        super().__init__(**kwargs)
        self.x, self.y = x, y
        self.color = color
        self.radius = 15
        self.velocity = [0, 0]
        self.health = 50
        self.max_health = 50
        self.frozen = 0
        self.random_target = (WIDTH // 2, HEIGHT // 2)

    def move(self):
        if self.frozen > 0:
            self.frozen -= 1
            return
        target_x, target_y = self.random_target
        angle = math.atan2(target_y - self.y, target_x - self.x)
        self.velocity[0] += math.cos(angle) * 0.1
        self.velocity[1] += math.sin(angle) * 0.1
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
        if math.sqrt((self.x - target_x)**2 + (self.y - target_y)**2) < 10:
            self.random_target = (
                WIDTH // 2 + random.randint(-100, 100),
                HEIGHT // 2 + random.randint(-100, 100)
            )

class Game(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.players = [
            Player(100, HEIGHT // 2, (0, 0, 1), AUTO_AIM_PLAYER),
            Player(WIDTH - 100, HEIGHT // 2, (1, 0, 0), AUTO_AIM_BALL)
        ]
        self.ball = Ball(WIDTH // 2, HEIGHT // 2, (1, 1, 0))
        self.goalposts = [
            Rectangle(pos=(0, HEIGHT // 3), size=(10, HEIGHT // 3)),
            Rectangle(pos=(WIDTH - 10, HEIGHT // 3), size=(10, HEIGHT // 3))
        ]
        self.add_widget(self.players[0])
        self.add_widget(self.players[1])
        self.add_widget(self.ball)
        Clock.schedule_interval(self.update, 1 / 60)

    def update(self, dt):
        self.ball.move()
        for player in self.players:
            player.move(0, 0)  # Replace with touch input
            self.ball.collide(player)
        self.check_collisions()
        self.check_goals()
        self.draw()

    def check_collisions(self):
        # Implement collision logic here
        pass

    def check_goals(self):
        # Implement goal logic here
        pass

    def draw(self):
        self.canvas.clear()
        with self.canvas:
            for player in self.players:
                Color(*player.color)
                Ellipse(pos=(player.x - player.radius, player.y - player.radius), size=(player.radius * 2, player.radius * 2))
            Color(*self.ball.color)
            Ellipse(pos=(self.ball.x - self.ball.radius, self.ball.y - self.ball.radius), size=(self.ball.radius * 2, self.ball.radius * 2))
            for goal in self.goalposts:
                Color(1, 1, 1)
                Rectangle(pos=goal.pos, size=goal.size)

class SoccerShooterApp(App):
    def build(self):
        game = Game()
        return game

if __name__ == "__main__":
    SoccerShooterApp().run()
